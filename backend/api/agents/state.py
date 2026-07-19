# -*- coding: utf-8 -*-
"""案件工作流状态定义（多证据聚合版）。

基于 langgraph-fundamentals skill 要点：
- TypedDict 定义状态结构
- Annotated[list, operator.add] 实现累积式合并
- 节点返回部分更新 dict，不能 mutate 整个 state

重构说明（多证据工作流）：
- 移除单值字段（evidence_id/raw_image_path/ocr_raw_text 等）
- 引入 evidence_ocr_results / evidence_classify_results / evidence_extract_results 累积列表
- timeline_events → evidence_chain（语义升级，含 LLM 辅助链路构造）

v11 升级（Task 0.1，对齐 langgraph-fundamentals）：
- 新增累积字段：warnings / provenance / artifacts / interventions / issues / events
- 新增标量字段：revision / current_stage / current_node / progress / workflow_version /
  state_schema_version / policy_version / prompt_bundle_version
- 新增自定义 reducer 字段：stale_artifact_ids（dedup_add）/ user_confirmed_fields（merge_dict）
- 新增 node_result 字段（默认覆盖，存储当前节点 NodeResult）
- errors 类型从 list[str] 升级为 list[dict]（BREAKING：每项含 code/message/severity/recoverable）
"""
from typing import Annotated, Optional, TypedDict
from operator import add


def dedup_add(left: list[int], right: list[int]) -> list[int]:
    """自定义 reducer：列表追加并去重（保持顺序，首次出现的位置保留）。

    用于 stale_artifact_ids 字段，避免重复 stale 标记。

    Args:
        left: 当前 state 中的列表
        right: 节点返回的待追加列表

    Returns:
        合并后的新列表（不修改入参）
    """
    if not left:
        return list(right)
    if not right:
        return list(left)
    result = list(left)
    seen = set(left)
    for item in right:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def merge_dict(left: dict, right: dict) -> dict:
    """自定义 reducer：按 key 合并 dict（不整体覆盖）。

    用于 user_confirmed_fields 字段，语义：
    {field_key: {evidence_id, field_name, confirmed_at, confirmed_by}}
    新值按 field_key 合并到旧 dict，field_key 相同时新值覆盖旧值。

    Args:
        left: 当前 state 中的 dict
        right: 节点返回的待合并 dict

    Returns:
        合并后的新 dict（不修改入参）
    """
    if not left:
        return dict(right) if right else {}
    if not right:
        return dict(left)
    merged = dict(left)
    merged.update(right)
    return merged


class CaseWorkflowState(TypedDict):
    """案件工作流状态（多证据聚合）。

    所有节点共享此状态，通过返回 dict 的子集来更新。
    list 字段使用 Annotated[list, add] 实现累积合并。
    标量字段默认覆盖（无 reducer）。
    自定义 reducer 字段（dedup_add / merge_dict）满足去重 / 合并语义。
    """
    # ===== 案件上下文 =====
    case_id: int
    # Task 3.1：关联的 WorkflowRun ID（节点通过此 ID 写入 WorkflowArtifact）
    workflow_run_id: Optional[int]
    evidence_ids: list[int]                # 待处理的证据 ID 列表（空则处理案件全部有图证据）
    case_mode: str                          # 案件模式：complain（维权投诉）/ respond（商家反证）

    # ===== 预分类节点输出（累积式） =====
    # list[dict]: {evidence_id, evidence_code, evidence_category, ocr_summary, confidence}
    evidence_preclassify_results: Annotated[list[dict], add]

    # ===== OCR 节点输出（累积式） =====
    # list[EvidenceOcrResult]: {evidence_id, evidence_code, image_path,
    #   ocr_raw_text, ocr_corrected_text, ocr_strategy_used, ocr_status, errors}
    evidence_ocr_results: Annotated[list[dict], add]

    # ===== 分类节点输出（累积式） =====
    # list[EvidenceClassifyResult]: {evidence_id, evidence_code,
    #   evidence_category, category_label, confidence}
    evidence_classify_results: Annotated[list[dict], add]

    # ===== 抽取节点输出（累积式） =====
    # list[EvidenceExtractResult]: {evidence_id, evidence_code, fields, needs_human_review}
    evidence_extract_results: Annotated[list[dict], add]
    needs_human_review: bool                # 任一证据有低置信度字段则为 True

    # ===== 证据链节点输出 =====
    # list[dict]: {datetime, event, category, evidence_codes, chain_order}
    evidence_chain: list[dict]
    # list[dict]: 工具调用日志 {tool_name, args, result_summary}
    evidence_chain_tool_calls: list[dict]

    # ===== 投诉节点输出 =====
    complaint_draft: Optional[dict]         # {"title", "content", "template_type", "tone"}
    # list[dict]: 投诉生成工具调用日志
    complaint_tool_calls: list[dict]

    # ===== HITL 校正节点输出 =====
    review_decision: Optional[dict]          # 人工校正结果

    # ===== 全局错误累积（v11 BREAKING：list[str] → list[dict]） =====
    # list[dict]: {code, message, severity, evidence_id?, stage?, recoverable}
    errors: Annotated[list[dict], add]

    # ===== v11 新增：累积列表字段（Annotated[list, add]） =====
    # list[dict]: 警告列表 {code, message, severity, evidence_id?, stage?}
    warnings: Annotated[list[dict], add]
    # list[dict]: 数据来源追溯 {node, evidence_id?, field_name?, source_ref, ts}
    provenance: Annotated[list[dict], add]
    # list[dict]: 工作流产物记录 {artifact_id, kind, stage, source_refs, summary, created_at}
    artifacts: Annotated[list[dict], add]
    # list[dict]: 介入记录 {intervention_id, type, stage, status, base_revision}
    interventions: Annotated[list[dict], add]
    # list[dict]: 统一问题列表（合并自 warnings + errors）
    #   {code, message, severity, evidence_id?, stage?, recoverable}
    issues: Annotated[list[dict], add]
    # list[dict]: 工作流事件流 {event_type, node, ts, payload}
    events: Annotated[list[dict], add]

    # ===== v11 新增：标量字段（默认覆盖，无 reducer） =====
    revision: int                            # 当前 state revision（节点完成时单调递增）
    current_stage: str                       # 当前业务阶段：材料理解 / 事实核对 / 案件组织 / 文书生成
    current_node: str                        # 当前执行节点名
    progress: float                          # 总体进度 0.0-1.0
    workflow_version: str                    # 工作流版本（如 "v11"）
    state_schema_version: int                # State schema 版本号
    policy_version: str                      # 策略版本
    prompt_bundle_version: str               # Prompt bundle 版本

    # ===== v11 新增：自定义 reducer 字段 =====
    # 去重追加（避免重复 stale 标记）
    stale_artifact_ids: Annotated[list[int], dedup_add]
    # 按 key 合并 dict（不整体覆盖）
    #   {field_key: {evidence_id, field_name, confirmed_at, confirmed_by}}
    user_confirmed_fields: Annotated[dict, merge_dict]

    # ===== v11 新增：默认覆盖字段 =====
    # 当前节点最近一次 NodeResult 输出（含 data/quality/warnings/errors/provenance/metrics）
    # 节点返回 partial update dict 时，将 NodeResult（定义于 api.agents.schemas）
    # 的 model_dump() 存入此字段。运行时类型为 Optional[dict]，避免 TypedDict 直接
    # 依赖 Pydantic 模型导致的循环 import；下游节点与 SSE mapper 通过 dict key 访问。
    node_result: Optional[dict]

    # ===== 输入质量门新增字段（input-quality-guard，默认覆盖无 reducer） =====
    # Gate 2：用户在证据质量硬拦截门（extract_node）确认低质量后继续（complaint_node
    #   读取后注入稀疏数据告知段落，避免 LLM 捏造）。
    low_quality_evidence_acknowledged: bool
    # Gate 2：用户在硬拦截门选择终止；extract_node 返回 Command(goto=END)，
    #   workflow_runner 检测到后 fail_processing（不再生成文书）。
    workflow_aborted_by_user: bool
    # Gate 1：证据内容与案件类型的相关性比例（classify_node 写入，供下游/审计读取）。
    evidence_relevance_ratio: float
    # Gate 1：是否全部证据被分类为 other。
    evidence_all_other: bool
