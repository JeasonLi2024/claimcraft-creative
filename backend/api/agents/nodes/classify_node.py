# -*- coding: utf-8 -*-
"""证据分类节点（async）：LLM 根据OCR文本分类证据材料类型。

重构说明（v4 异步化）：
- def → async def，支持节点级 timeout
- LLM 调用用 .ainvoke()（LangChain Runnable 原生 async）
- @traceable 装饰器

新增节点（多证据工作流重构）：
- 输入：state.evidence_ocr_results（多条证据的 OCR 文本）
- 输出：state.evidence_classify_results（每条证据的分类结果）
- LLM 不可用时全部标记为 other

分类类别：
- chat_screenshot（聊天截图）
- product_order（商品订单）
- logistics_tracking（物流跟踪）
- payment_record（支付凭证）
- other（其他）
"""
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
    "other": "其他",
}


@traceable(name="证据分类节点", run_type="chain")
async def classify_node(state: CaseWorkflowState) -> dict[str, Any]:
    """证据分类节点（async）：LLM 根据OCR文本分类证据材料类型。

    流程：
    1. 从 state.evidence_ocr_results 获取所有 OCR 结果
    2. 若 LLM 可用，批量分类（with_structured_output）
    3. LLM 不可用或失败时全部标记为 other
    """
    from api.agents.schemas import ClassifyBatchResult

    ocr_results = state.get("evidence_ocr_results", [])
    errors = []

    if not ocr_results:
        return {
            "evidence_classify_results": [],
            "errors": ["[分类] 无 OCR 结果，跳过分类"],
        }

    # LLM 不可用，全部标记为 other
    if not llm_service.is_scenario_available("text"):
        logger.info("LLM 不可用，证据全部标记为 other")
        results = [
            {
                "evidence_id": r["evidence_id"],
                "evidence_code": r["evidence_code"],
                "evidence_category": "other",
                "category_label": "其他",
                "confidence": 0.0,
            }
            for r in ocr_results
        ]
        return {
            "evidence_classify_results": results,
            "errors": ["[分类] LLM 不可用，全部标记为 other"],
        }

    # 构造批量分类 prompt
    evidences_text = "\n\n".join([
        f"--- 证据 {r['evidence_code']} ---\n{r.get('ocr_corrected_text') or r.get('ocr_raw_text', '')}"
        for r in ocr_results
    ])
    prompt = f"""请对以下 {len(ocr_results)} 条证据分别分类。

{evidences_text}

请为每条证据输出分类结果，results 列表长度必须等于 {len(ocr_results)}。"""

    try:
        llm = llm_service.get_scenario_llm("text")
        # DashScope 不兼容 json_schema 模式，改用 function_calling 模式
        structured_llm = llm.with_structured_output(ClassifyBatchResult, method="function_calling")
        result = await structured_llm.ainvoke(prompt)

        classify_results = []
        for i, r in enumerate(result.results):
            classify_results.append({
                "evidence_id": ocr_results[i]["evidence_id"],
                "evidence_code": ocr_results[i]["evidence_code"],
                "evidence_category": r.evidence_category,
                "category_label": r.category_label or CATEGORY_LABELS.get(r.evidence_category, "其他"),
                "confidence": r.confidence,
            })
        logger.info(f"证据分类完成，共 {len(classify_results)} 条")

    except Exception as e:
        logger.warning(f"LLM 分类失败，全部标记为 other: {e}")
        errors.append(f"[分类] LLM 分类失败: {e}")
        classify_results = [
            {
                "evidence_id": r["evidence_id"],
                "evidence_code": r["evidence_code"],
                "evidence_category": "other",
                "category_label": "其他",
                "confidence": 0.0,
            }
            for r in ocr_results
        ]

    return {
        "evidence_classify_results": classify_results,
        "errors": errors,
    }
