# -*- coding: utf-8 -*-
"""SSE 事件过滤映射器：将 astream_events(v2) 原始事件过滤映射为 SSE 协议事件。

参考 spec 第 5.3 节。负责：
- 识别工作流 8 节点的 on_chain_start / on_chain_end 事件
- 跟踪 current_node 用于 complaint_node 的 token 流过滤
- 计算 duration_ms（节点开始到结束的耗时）
- 从节点输出提取对应 state 字段作为产物
- 仅 complaint / respond_complaint 节点的 on_chat_model_stream 映射为 complaint.token
  其他 LLM 节点的 token 流丢弃（避免事件过载）
- 映射 on_custom_event 为 node.progress（里程碑式阶段通知）

astream_events(v2) 原始事件结构：
    {
        "event": "on_chain_start" | "on_chain_end" | "on_chat_model_stream" | "on_custom_event" | ...,
        "name": <节点名>,
        "data": {"input": ..., "output": ..., "chunk": ...},
        "tags": [...],
        "run_id": "...",
        "metadata": {...}
    }
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    """SSE 事件数据结构（type + payload）。"""
    type: str
    payload: dict[str, Any] = field(default_factory=dict)


def _utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


class SSEEventMapper:
    """将 astream_events(v2) 事件过滤映射为 SSE 协议事件。

    状态说明：
    - current_node：当前正在执行的节点名（on_chain_start 设置，on_chain_end 清空）
    - _node_start_times：节点名 → 开始时间戳，用于计算 duration_ms

    实例非线程安全，每个 WorkflowRunner.run_and_persist 独立持有实例。
    """

    # 工作流 8 节点名称集合（与 graph.py 中 add_node 的名称一致）
    NODE_NAMES: set[str] = {
        "preclassify",
        "ocr",
        "classify",
        "extract",
        "review",
        "evidence_chain",
        "complaint",
        "respond_complaint",
    }

    # 产生 token 流的节点（complaint + respond_complaint）
    _TOKEN_NODES: set[str] = {"complaint", "respond_complaint"}

    # 节点 → 输出 state 字段映射（用于提取产物）
    _FIELD_MAP: dict[str, list[str]] = {
        "preclassify": ["evidence_preclassify_results"],
        "ocr": ["evidence_ocr_results"],
        "classify": ["evidence_classify_results"],
        "extract": ["evidence_extract_results", "needs_human_review"],
        "review": ["review_decision"],
        "evidence_chain": ["evidence_chain", "evidence_chain_tool_calls"],
        "complaint": ["complaint_draft", "complaint_tool_calls"],
        "respond_complaint": ["complaint_draft", "complaint_tool_calls"],
    }

    def __init__(self):
        self.current_node: str | None = None
        self._node_start_times: dict[str, datetime] = {}

    async def map(self, raw_event: dict) -> list[SSEEvent]:
        """过滤映射 astream_events 原始事件，返回 0~N 个 SSE 事件。

        多数事件 1:1 映射，on_chain_end 可能产生 1~2 个事件
        （complaint / respond_complaint 节点额外产生 complaint.done）。
        on_custom_event 产生 node.progress 里程碑通知。

        Args:
            raw_event: astream_events(v2) 产生的原始事件 dict

        Returns:
            SSE 事件列表（可能为空）
        """
        event_type: str = raw_event.get("event", "")
        name: str = raw_event.get("name", "")
        data: dict = raw_event.get("data", {}) or {}

        # 1. 节点开始：on_chain_start 命中工作流节点
        if event_type == "on_chain_start" and name in self.NODE_NAMES:
            self.current_node = name
            self._node_start_times[name] = datetime.now(timezone.utc)
            return [SSEEvent(
                type="node.start",
                payload={
                    "node": name,
                    "input_summary": self._summarize_input(name, data.get("input", {})),
                    "ts": _utcnow_iso(),
                },
            )]

        # 2. 节点完成：on_chain_end 命中工作流节点
        if event_type == "on_chain_end" and name in self.NODE_NAMES:
            sse_events = self._build_node_complete(name, data.get("output", {}))
            self.current_node = None
            return sse_events

        # 3. LLM token 流：complaint / respond_complaint 节点的 on_chat_model_stream
        if event_type == "on_chat_model_stream" and self.current_node in self._TOKEN_NODES:
            chunk = data.get("chunk")
            content = getattr(chunk, "content", None) if chunk else None
            if content:
                return [SSEEvent(
                    type="complaint.token",
                    payload={"delta": content},
                )]
            return []

        # 4. 自定义事件：节点内部通过 get_stream_writer 发送的里程碑进度
        if event_type == "on_custom_event":
            return self._map_custom_event(name, data)

        # 5. HITL 中断：on_interrupt
        if event_type == "on_interrupt":
            interrupt_data = self._extract_interrupt(name, data)
            return [SSEEvent(type="review.interrupt", payload=interrupt_data)]

        # 6. 节点错误：on_chain_error（Saga 降级）
        if event_type == "on_chain_error" and name in self.NODE_NAMES:
            return [SSEEvent(
                type="node.error",
                payload={
                    "node": name,
                    "message": str(data.get("error", ""))[:500],
                    "recoverable": True,  # Saga 错误处理器已降级，工作流继续
                    "ts": _utcnow_iso(),
                },
            )]

        # 其他事件过滤掉（on_chain_start/end 命中非节点、on_chat_model_start 等）
        return []

    def _map_custom_event(self, name: str, data: dict) -> list[SSEEvent]:
        """映射 on_custom_event 为 SSE 事件（node.progress 或 review.skipped）。

        节点内部通过 langgraph.config.get_stream_writer() 发送自定义事件：
        - 进度通知：{"stage": "...", "message": "...", "detail": {...}}
        - 跳过通知：{"event_type": "review.skipped", "message": "..."}

        Args:
            name: 自定义事件名称
            data: 事件数据

        Returns:
            SSE 事件列表
        """
        payload_data = data
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            payload_data = data["data"]

        # review.skipped 事件
        event_type_flag = payload_data.get("event_type", "")
        if event_type_flag == "review.skipped":
            return [SSEEvent(
                type="review.skipped",
                payload={
                    "node": "review",
                    "message": payload_data.get("message", "无需人工校正，跳过审核"),
                    "ts": _utcnow_iso(),
                },
            )]

        # 默认：node.progress 里程碑通知
        stage = payload_data.get("stage", "")
        message = payload_data.get("message", "")
        detail = payload_data.get("detail", {})

        if not stage:
            return []

        node = self.current_node or payload_data.get("node", "")

        return [SSEEvent(
            type="node.progress",
            payload={
                "node": node,
                "stage": stage,
                "message": message,
                "detail": detail,
                "ts": _utcnow_iso(),
            },
        )]

    def _build_node_complete(self, name: str, output: dict) -> list[SSEEvent]:
        """构建 node.complete 事件（complaint / respond_complaint 节点额外加 complaint.done）。"""
        products = self._extract_products(name, output)
        start_time = self._node_start_times.pop(name, None)
        now = datetime.now(timezone.utc)
        if start_time is not None:
            duration_ms = int((now - start_time).total_seconds() * 1000)
        else:
            duration_ms = 0

        sse_events: list[SSEEvent] = [SSEEvent(
            type="node.complete",
            payload={
                "node": name,
                "products": products,
                "duration_ms": duration_ms,
                "ts": now.isoformat(),
            },
        )]

        # complaint / respond_complaint 节点完成额外产生 complaint.done
        if name in self._TOKEN_NODES:
            draft = products.get("complaint_draft") or {}
            sse_events.append(SSEEvent(
                type="complaint.done",
                payload={
                    "final_content": draft.get("content", ""),
                    "title": draft.get("title", ""),
                    "tone": draft.get("tone", ""),
                    "node": name,  # 标识来源节点（complaint 或 respond_complaint）
                    "ts": now.isoformat(),
                },
            ))

        return sse_events

    def _extract_products(self, node: str, output: dict) -> dict:
        """从节点输出中提取对应 state 字段作为产物。

        Args:
            node: 节点名
            output: on_chain_end 的 data.output（节点返回的 dict）

        Returns:
            产物 dict（仅包含该节点对应的 state 字段）
        """
        fields = self._FIELD_MAP.get(node, [])
        result: dict[str, Any] = {}
        for f in fields:
            if f in output:
                result[f] = output[f]
        return result

    def _summarize_input(self, node: str, input_data: dict) -> dict:
        """生成节点输入摘要（供前端展示，避免完整 state 传输）。

        Args:
            node: 节点名
            input_data: on_chain_start 的 data.input

        Returns:
            摘要 dict（evidence_ids 数量 + case_id）
        """
        if not isinstance(input_data, dict):
            return {}
        evidence_ids = input_data.get("evidence_ids", [])
        return {
            "case_id": input_data.get("case_id"),
            "evidence_count": len(evidence_ids) if isinstance(evidence_ids, list) else 0,
        }

    def _extract_interrupt(self, name: str, data: dict) -> dict:
        """从 on_interrupt 事件提取 review.interrupt 数据。

        LangGraph 的 on_interrupt 事件 data 含 interrupt value，
        review_node 的 interrupt value 包含待审核字段列表。
        """
        value = data.get("value")
        if isinstance(value, dict):
            # 统一字段名为 current_value（前端 ReviewField 类型使用 current_value）
            fields_to_review = value.get("fields_to_review", [])
            normalized_fields = []
            for f in fields_to_review:
                if isinstance(f, dict):
                    normalized = dict(f)
                    # 如果有 field_value 但没有 current_value，补一个
                    if "current_value" not in normalized and "field_value" in normalized:
                        normalized["current_value"] = normalized["field_value"]
                    normalized_fields.append(normalized)
                else:
                    normalized_fields.append(f)
            return {
                "fields_to_review": normalized_fields,
                "message": value.get("message", "存在低置信度字段，请人工校正"),
                "resume_endpoint": f"/api/cases/{{case_id}}/workflow/resume/",
            }
        # value 可能是 list 或其它结构，原样包裹
        return {
            "fields_to_review": [],
            "message": str(value) if value else "需要人工审核",
            "resume_endpoint": "/api/cases/{case_id}/workflow/resume/",
            "raw_value": str(value)[:500] if value else None,
        }
