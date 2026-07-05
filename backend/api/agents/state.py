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
"""
from typing import Annotated, Optional, TypedDict
from operator import add


class CaseWorkflowState(TypedDict):
    """案件工作流状态（多证据聚合）。

    所有节点共享此状态，通过返回 dict 的子集来更新。
    list 字段使用 Annotated[list, add] 实现累积合并。
    """
    # ===== 案件上下文 =====
    case_id: int
    evidence_ids: list[int]                # 待处理的证据 ID 列表（空则处理案件全部有图证据）

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

    # ===== 投诉节点输出 =====
    complaint_draft: Optional[dict]         # {"title", "content", "template_type", "tone"}

    # ===== HITL 校正节点输出 =====
    review_decision: Optional[dict]          # 人工校正结果

    # ===== 全局错误累积 =====
    errors: Annotated[list[str], add]        # 累积式错误日志，节点返回 {"errors": [...]} 自动追加
