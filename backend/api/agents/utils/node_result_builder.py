# -*- coding: utf-8 -*-
"""NodeResult 构造辅助（Task 1.2）。

为 8 个业务节点（preclassify / ocr / classify / extract / review /
evidence_chain / complaint / respond_complaint）提供共享的 NodeResult
构造逻辑，避免 8 份重复代码。

提供：
- now_iso(): 当前 UTC 时间的 ISO 8601 字符串
- convert_string_errors_to_dicts(): 节点内部累积的字符串错误列表 →
  state.errors 期望的 list[dict] 格式（对齐 Task 0.1 BREAKING 变更）
- build_node_result(): 构造 NodeResult.model_dump() dict
- make_node_partial_update(): 构造节点返回的 partial update dict，含
  node_result / revision / current_node / current_stage / progress /
  provenance / warnings / issues / events + 调用方提供的旧字段
"""
from datetime import datetime, timezone
from typing import Any

from api.agents.schemas import (
    Issue,
    Metrics,
    NodeResult,
    ProvenanceItem,
    QualityReport,
    Warning,
)


def now_iso() -> str:
    """当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def convert_string_errors_to_dicts(
    errors: list[str],
    default_code: str = "node.error",
    stage: str | None = None,
) -> list[dict]:
    """将节点内部累积的字符串错误列表转换为 state.errors 期望的 list[dict] 格式。

    对齐 Task 0.1 BREAKING 变更：errors 从 list[str] 升级为 list[dict]，
    每项含 {code, message, severity, evidence_id, stage, recoverable}。

    Args:
        errors: 节点内部累积的字符串错误列表（如 ["[OCR] 证据 EV001 失败: ..."]）
        default_code: 默认错误代码
        stage: 节点阶段标识（如 "ocr"）

    Returns:
        list[dict]: 错误字典列表，可直接作为 state.errors 返回值
    """
    return [
        {
            "code": default_code,
            "message": err,
            "severity": "warning",
            "evidence_id": None,
            "stage": stage,
            "recoverable": True,
        }
        for err in errors
        if err  # 过滤空字符串
    ]


def build_node_result(
    node_name: str,
    data: dict,
    quality: QualityReport,
    warnings: list[Warning] | list[dict] | None = None,
    errors: list[Issue] | list[dict] | None = None,
    provenance: list[ProvenanceItem] | list[dict] | None = None,
    start_time: datetime | None = None,
    model_calls: int = 0,
    api_calls: int = 0,
    tokens_used: int = 0,
    retries: int = 0,
) -> dict:
    """构造 NodeResult.model_dump() dict。

    Args:
        node_name: 节点名（如 "preclassify"）
        data: 节点主体数据 dict（业务字段摘要）
        quality: QualityReport 质量报告
        warnings: 警告列表（Warning 对象或 dict，Pydantic 自动 coerce）
        errors: 错误列表（Issue 对象或 dict，Pydantic 自动 coerce）
        provenance: 数据来源追溯列表（ProvenanceItem 对象或 dict）
        start_time: 节点开始时间（用于计算 duration_ms）
        model_calls: LLM 调用次数
        api_calls: 外部 API 调用次数
        tokens_used: token 消耗
        retries: 重试次数

    Returns:
        dict: NodeResult.model_dump()，可作为 state["node_result"] 值
    """
    if start_time is None:
        start_time = datetime.now(timezone.utc)
    duration_ms = int(
        (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    )

    nr = NodeResult(
        node=node_name,
        data=data,
        quality=quality,
        warnings=warnings or [],
        errors=errors or [],
        provenance=provenance or [],
        metrics=Metrics(
            duration_ms=duration_ms,
            model_calls=model_calls,
            api_calls=api_calls,
            tokens_used=tokens_used,
            retries=retries,
        ),
    )
    return nr.model_dump()


def _merge_issues(
    warnings: list[dict],
    errors: list[dict],
) -> list[dict]:
    """合并 warnings + errors 为统一 issues 列表（对齐 Task 2.3.3 设计）。"""
    issues: list[dict] = []
    for w in warnings:
        issues.append({
            "code": w.get("code", "warning"),
            "message": w.get("message", ""),
            "severity": w.get("severity", "warning"),
            "evidence_id": w.get("evidence_id"),
            "stage": w.get("stage"),
            "recoverable": True,
        })
    for e in errors:
        issues.append({
            "code": e.get("code", "node.error"),
            "message": e.get("message", ""),
            "severity": e.get("severity", "warning"),
            "evidence_id": e.get("evidence_id"),
            "stage": e.get("stage"),
            "recoverable": e.get("recoverable", True),
        })
    return issues


def make_node_partial_update(
    node_name: str,
    stage: str,
    progress: float,
    state: dict,
    node_result: dict,
    legacy_fields: dict,
    issues: list[dict] | None = None,
    extra_events: list[dict] | None = None,
) -> dict:
    """构造节点返回的 partial update dict。

    含义：
    - 旧字段保留（legacy_fields，如 evidence_preclassify_results / errors）
    - 新增字段：node_result / revision / current_node / current_stage / progress /
      provenance / warnings / issues / events

    Args:
        node_name: 节点名（如 "preclassify"）
        stage: 业务阶段（material_understanding / fact_checking /
            case_organization / document_generation）
        progress: 总体进度 0.0-1.0
        state: 当前 state（用于读取 revision 进行递增）
        node_result: NodeResult.model_dump() dict（由 build_node_result 构造）
        legacy_fields: 节点原有的返回字段（如 evidence_preclassify_results），
            其中 errors 字段必须为 list[dict] 格式（对齐 Task 0.1 BREAKING）
        issues: 统一问题列表（可空；默认合并自 node_result.warnings + errors）
        extra_events: 额外事件列表（默认追加 node.completed 事件）

    Returns:
        dict: partial update dict，可直接 return
    """
    ts = now_iso()
    revision = state.get("revision", 0) + 1

    # 从 node_result 提取 provenance / warnings / errors（model_dump 后为 list[dict]）
    provenance = node_result.get("provenance", [])
    warnings = node_result.get("warnings", [])
    errors = node_result.get("errors", [])

    # issues：默认合并自 warnings + errors
    if issues is None:
        issues = _merge_issues(warnings, errors)

    # events：默认追加 node.completed
    if extra_events is not None:
        events = list(extra_events)
    else:
        events = []
    events.append({
        "event_type": "node.completed",
        "node": node_name,
        "ts": ts,
        "payload": {"revision": revision, "progress": progress},
    })

    return {
        # 旧字段保留（向后兼容）
        **legacy_fields,
        # 新增字段（Task 1.2）
        "node_result": node_result,
        "revision": revision,
        "current_node": node_name,
        "current_stage": stage,
        "progress": progress,
        "provenance": provenance,
        "warnings": warnings,
        "issues": issues,
        "events": events,
    }
