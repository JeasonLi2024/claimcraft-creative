# -*- coding: utf-8 -*-
"""SSE 里程碑进度发送辅助函数。

节点内部通过 langgraph 的 get_stream_writer() 发送自定义事件，
SSEEventMapper 的 on_custom_event 处理器将其映射为 node.progress SSE 事件。

使用方式（在节点函数内部）：
    from api.agents.utils.progress import emit_progress

    await emit_progress(stage="rag_retrieval", message="正在检索相关法条...")
    # ... 执行 RAG 检索 ...
    await emit_progress(stage="rag_done", message="检索完成，命中 50 条候选",
                       detail={"candidate_count": 50, "top1_score": 0.89})
    # ... 执行 LLM 工具调用 ...
    await emit_progress(stage="tool_call", message="调用工具: lookup_law",
                       detail={"tool": "lookup_law", "args_summary": "欺诈 退一赔三"})

设计要点：
- 里程碑式通知，仅在关键阶段切换时发送（非高频）
- 包含 stage（阶段标识）、message（人类可读）、detail（结构化明细）
- get_stream_writer 不可用时静默降级（不影响节点执行）
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def emit_progress(
    stage: str,
    message: str = "",
    detail: dict[str, Any] | None = None,
):
    """发送里程碑进度通知（通过 langgraph get_stream_writer）。

    在节点内部调用，SSEEventMapper 会将 on_custom_event 映射为 node.progress，
    前端可消费展示当前执行阶段。

    Args:
        stage: 阶段标识（如 "rag_retrieval"、"tool_call"、"generating"）
        message: 人类可读的进度消息（如"正在检索相关法条..."）
        detail: 结构化明细（如 {"candidate_count": 50}）

    降级行为：
        - get_stream_writer 不可用（非 LangGraph 运行上下文）→ 静默跳过
        - 发送失败 → 记录 warning 日志，不中断节点执行
    """
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
        if writer is None:
            return
        payload = {
            "stage": stage,
            "message": message,
            "detail": detail or {},
        }
        writer(payload)
    except Exception as e:
        logger.debug(f"[emit_progress] 发送进度失败（不影响执行）: {e}")
