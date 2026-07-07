# -*- coding: utf-8 -*-
"""证据分类节点（async）：高置信度直接采纳 + 低置信度子集并行 LLM 细化。

v9 重构说明（视觉预分类 + 摘要驱动）：
- 高置信度预分类结果（>= PRECLASSIFY_CONFIDENCE_THRESHOLD）直接采纳，跳过 LLM 调用
- 低置信度子集（< 阈值）并行调用文本 LLM 用 ocr_summary 细化（prompt 更短、更快）
- LLM 不可用时全部回退为预分类结果（即便置信度低）
- 多证据并发（asyncio.gather） refine

分类类别（与 preclassify_node 保持一致）：
- chat_screenshot（聊天截图）
- product_order（商品订单）
- logistics_tracking（物流跟踪）
- payment_record（支付凭证）
- invoice（发票）—— 仅高置信度预分类可能产出，LLM refine schema 不支持
- other（其他）
"""
import asyncio
import logging
from typing import Any

from api.agents.state import CaseWorkflowState
from api.services import llm_service

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def deco(fn):
            return fn
        return args[0] if args and callable(args[0]) else deco

logger = logging.getLogger(__name__)

# 证据类别 → 中文标签映射
CATEGORY_LABELS = {
    "chat_screenshot": "聊天截图",
    "product_order": "商品订单",
    "logistics_tracking": "物流跟踪",
    "payment_record": "支付凭证",
    "invoice": "发票",
    "other": "其他",
}

# 触发 LLM 细化的置信度阈值（< 此值时进入低置信度子集并行 refine）
# 注：与 preclassify_node.PRECLASSIFY_CONFIDENCE_THRESHOLD 保持一致
LOW_CONFIDENCE_THRESHOLD = 0.8


@traceable(name="证据分类节点", run_type="chain")
async def classify_node(state: CaseWorkflowState) -> dict[str, Any]:
    """证据分类节点（async）：高置信度直接采纳 + 低置信度子集并行 LLM 细化。

    流程：
    1. 从 state.evidence_preclassify_results 获取预分类结果
    2. 高置信度（>= 阈值）直接采纳
    3. 低置信度子集并行调用文本 LLM 用 ocr_summary 细化
    4. LLM 不可用时全部回退为预分类结果
    """
    preclassify_results = state.get("evidence_preclassify_results", [])
    ocr_results = state.get("evidence_ocr_results", [])
    errors = []

    if not preclassify_results:
        # 预分类未产出（如 Captioner 不可用），全部降级为 other
        logger.warning("[分类] 无预分类结果，全部标记为 other")
        results = [
            {
                "evidence_id": r.get("evidence_id"),
                "evidence_code": r.get("evidence_code"),
                "evidence_category": "other",
                "category_label": "其他",
                "confidence": 0.0,
            }
            for r in ocr_results
        ]
        return {
            "evidence_classify_results": results,
            "errors": ["[分类] 无预分类结果，全部标记为 other"],
        }

    # 1. 筛选高/低置信度子集
    high_confidence = [r for r in preclassify_results if r.get("confidence", 0.0) >= LOW_CONFIDENCE_THRESHOLD]
    low_confidence = [r for r in preclassify_results if r.get("confidence", 0.0) < LOW_CONFIDENCE_THRESHOLD]

    logger.info(
        f"[分类] 预分类结果: 高置信度 {len(high_confidence)} 条直接采纳, "
        f"低置信度 {len(low_confidence)} 条进入 LLM 细化"
    )

    # 2. 高置信度直接采纳
    classify_results = []
    for r in high_confidence:
        category = r.get("evidence_category", "other")
        classify_results.append({
            "evidence_id": r["evidence_id"],
            "evidence_code": r["evidence_code"],
            "evidence_category": category,
            "category_label": CATEGORY_LABELS.get(category, "其他"),
            "confidence": r.get("confidence", 0.0),
        })

    # 3. 低置信度子集处理
    if not low_confidence:
        # 全部高置信度，跳过 LLM 调用
        logger.info("[分类] 全部高置信度，跳过 LLM 细化")
    elif not llm_service.is_scenario_available("text"):
        # LLM 不可用，低置信度也直接采纳预分类结果
        logger.info("[分类] LLM 不可用，低置信度子集直接采纳预分类结果")
        errors.append("[分类] LLM 不可用，低置信度子集直接采纳预分类结果")
        for r in low_confidence:
            category = r.get("evidence_category", "other")
            classify_results.append({
                "evidence_id": r["evidence_id"],
                "evidence_code": r["evidence_code"],
                "evidence_category": category,
                "category_label": CATEGORY_LABELS.get(category, "其他"),
                "confidence": r.get("confidence", 0.0),
            })
    else:
        # 并行 LLM 细化低置信度子集
        refined = await _refine_low_confidence_batch(
            low_confidence, ocr_results, errors
        )
        classify_results.extend(refined)

    # 4. 按 evidence_id 排序（与 OCR 结果顺序一致，便于下游消费）
    ocr_order = {r["evidence_id"]: i for i, r in enumerate(ocr_results)}
    classify_results.sort(key=lambda x: ocr_order.get(x["evidence_id"], 0))

    logger.info(f"[分类] 完成，共 {len(classify_results)} 条")
    return {
        "evidence_classify_results": classify_results,
        "errors": errors,
    }


async def _refine_low_confidence_batch(
    low_confidence: list[dict],
    ocr_results: list[dict],
    errors: list[str],
) -> list[dict]:
    """并行 LLM 细化低置信度子集。

    使用 ocr_summary 替代全文，prompt 更短，单次调用更快。
    每条证据独立 LLM 调用，asyncio.gather 并发执行。

    Args:
        low_confidence: 低置信度预分类结果列表
        ocr_results: OCR 结果（用于读取 ocr_summary 或 corrected_text 作为细化输入）
        errors: 错误累积列表

    Returns:
        list[dict]: 细化后的分类结果
    """
    from api.agents.prompts.templates import EVIDENCE_CLASSIFY_PROMPT
    from api.agents.schemas import EvidenceClassification

    # 构建 evidence_id → ocr_text 映射（优先 ocr_summary，回退 corrected_text）
    ocr_text_map = {
        r["evidence_id"]: r.get("ocr_corrected_text") or r.get("ocr_raw_text", "")
        for r in ocr_results
    }

    async def _refine_one(item):
        """对单条证据调用 LLM 细化分类。"""
        evidence_id = item["evidence_id"]
        evidence_code = item["evidence_code"]
        # 优先用预分类产出的 ocr_summary，更短更聚焦
        ocr_summary = item.get("ocr_summary", "")
        if not ocr_summary:
            ocr_summary = ocr_text_map.get(evidence_id, "")[:500]  # 兜底截断

        prompt = EVIDENCE_CLASSIFY_PROMPT.format(
            evidence_code=evidence_code,
            ocr_text=ocr_summary,
        )
        try:
            llm = llm_service.get_scenario_llm("text")
            # DashScope 不兼容 json_schema 模式，改用 function_calling 模式
            structured_llm = llm.with_structured_output(
                EvidenceClassification,
                method="function_calling",
            )
            result = await structured_llm.ainvoke(prompt)
            category = result.evidence_category
            return {
                "evidence_id": evidence_id,
                "evidence_code": evidence_code,
                "evidence_category": category,
                "category_label": result.category_label or CATEGORY_LABELS.get(category, "其他"),
                "confidence": result.confidence,
            }
        except Exception as e:
            logger.warning(
                f"[分类] 证据 {evidence_code} LLM 细化失败: {e}，回退到预分类结果"
            )
            errors.append(f"[分类] 证据 {evidence_code} LLM 细化失败: {e}")
            # 回退：保留原预分类结果
            category = item.get("evidence_category", "other")
            return {
                "evidence_id": evidence_id,
                "evidence_code": evidence_code,
                "evidence_category": category,
                "category_label": CATEGORY_LABELS.get(category, "其他"),
                "confidence": item.get("confidence", 0.0),
            }

    # 并行执行所有低置信度证据的 LLM 细化
    refined = await asyncio.gather(*[_refine_one(item) for item in low_confidence])
    return [r for r in refined if isinstance(r, dict)]
