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
from datetime import datetime, timezone
from typing import Any

from asgiref.sync import sync_to_async

from api.agents.state import CaseWorkflowState
from api.agents.schemas import QualityReport
from api.agents.utils.node_result_builder import (
    build_node_result,
    convert_string_errors_to_dicts,
    make_node_partial_update,
)
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
    "service_contract": "服务合同",
    "work_record": "施工记录",
    "communication_record": "沟通记录",
    "contract_document": "合同文件",
    "medical_record": "医疗记录",
    "other": "其他",
}

# 触发 LLM 细化的置信度阈值（< 此值时进入低置信度子集并行 refine）
# 注：与 preclassify_node.PRECLASSIFY_CONFIDENCE_THRESHOLD 保持一致
LOW_CONFIDENCE_THRESHOLD = 0.8

# ============================================================================
# Gate 1：证据-案件类型相关性评分（input-quality-guard）
# ============================================================================
# 案件类型 → 预期证据类别集合。用于评估用户填报的 case_type 与实际证据内容是否吻合。
# "other" 及未列出的类型不做限制（任何类别均视为相关）。
CASE_TYPE_EXPECTED_CATEGORIES: dict[str, set[str]] = {
    "shopping": {
        "chat_screenshot", "product_order", "logistics_tracking",
        "payment_record", "invoice",
    },
    "service": {
        "service_contract", "communication_record", "work_record",
        "chat_screenshot",
    },
    "secondhand": {
        "chat_screenshot", "product_order", "payment_record",
        "communication_record",
    },
}

# 相关性评分低于此阈值时写入 warn（仅警告，不阻塞流程）。
RELEVANCE_WARN_THRESHOLD = 0.3

# 案件类型 → 中文标签（用于相关性警告文案）
CASE_TYPE_LABELS: dict[str, str] = {
    "shopping": "网购纠纷",
    "service": "服务纠纷",
    "secondhand": "二手交易纠纷",
    "other": "其他纠纷",
}


async def _get_case_type(case_id: int) -> str:
    """读取案件类型（用于 Gate 1 相关性评分）。取不到时返回空串（视为不限制）。"""
    from api.models import Case
    try:
        case_type = await sync_to_async(
            lambda: Case.objects.filter(pk=case_id)
            .values_list("case_type", flat=True)
            .first()
        )()
        return case_type or ""
    except Exception as e:  # pragma: no cover - 防御性降级
        logger.debug(f"[分类] 读取案件类型失败（忽略，按不限制处理）: {e}")
        return ""


def _compute_evidence_relevance(
    case_type: str,
    classify_results: list[dict],
) -> dict:
    """计算证据与案件类型的相关性（Gate 1）。

    Args:
        case_type: 用户填报的案件类型（shopping/service/secondhand/other/...）
        classify_results: 分类结果列表，每项含 evidence_category

    Returns:
        {
          "relevance_ratio": float,      # 相关证据占比 0.0-1.0
          "expected_categories": list,   # 该案件类型的预期证据类别（已排序）
          "matched_count": int,          # 命中预期类别的证据数
          "total_count": int,
          "all_other": bool,             # 是否全部归类为 other
        }
    """
    if not classify_results:
        return {
            "relevance_ratio": 0.0,
            "expected_categories": [],
            "matched_count": 0,
            "total_count": 0,
            "all_other": True,
        }

    expected = CASE_TYPE_EXPECTED_CATEGORIES.get(case_type, set())
    all_other = all(
        r.get("evidence_category") == "other" for r in classify_results
    )
    if not expected:
        # "other" 或未知案件类型不做限制，全部视为相关
        return {
            "relevance_ratio": 1.0,
            "expected_categories": [],
            "matched_count": len(classify_results),
            "total_count": len(classify_results),
            "all_other": all_other,
        }

    matched = sum(
        1 for r in classify_results
        if r.get("evidence_category") in expected
    )
    ratio = matched / len(classify_results)
    return {
        "relevance_ratio": round(ratio, 3),
        "expected_categories": sorted(expected),
        "matched_count": matched,
        "total_count": len(classify_results),
        "all_other": all_other,
    }


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
    start_time = datetime.now(timezone.utc)

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
        errors.append("[分类] 无预分类结果，全部标记为 other")
        error_dicts = convert_string_errors_to_dicts(errors, stage="classify")
        provenance = [
            {
                "node": "classify",
                "evidence_id": r.get("evidence_id"),
                "field_name": None,
                "source_ref": f"classify:{r.get('evidence_code', '')}:other",
                "ts": start_time.isoformat(),
            }
            for r in results
        ]
        node_result = build_node_result(
            node_name="classify",
            data={"evidence_count": len(results), "degraded": True},
            quality=QualityReport(
                score=0.0,
                coverage=len(results) / max(len(preclassify_results), 1) if preclassify_results else 0.0,
                status="warn",
                blocking_issues=[],
                details={"degraded": True, "reason": "no_preclassify"},
            ),
            warnings=[],
            errors=error_dicts,
            provenance=provenance,
            start_time=start_time,
            model_calls=0,
        )
        return make_node_partial_update(
            node_name="classify",
            stage="material_understanding",
            progress=0.30,
            state=state,
            node_result=node_result,
            legacy_fields={
                "evidence_classify_results": results,
                "errors": error_dicts,
                # Gate 1：降级路径全部 other，供下游/审计读取
                "evidence_relevance_ratio": 0.0,
                "evidence_all_other": True,
            },
        )

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
    # 计算 quality：平均分类置信度 + 类别分布
    if classify_results:
        avg_confidence = sum(r.get("confidence", 0.0) for r in classify_results) / len(classify_results)
    else:
        avg_confidence = 0.0
    coverage = len(classify_results) / max(len(preclassify_results), 1)
    quality_status = "pass" if avg_confidence >= 0.7 else "warn"
    # 类别分布
    category_distribution: dict[str, int] = {}
    for r in classify_results:
        cat = r.get("evidence_category", "other")
        category_distribution[cat] = category_distribution.get(cat, 0) + 1

    # Gate 1：证据-案件类型相关性评分（仅警告，不阻塞流程）
    case_type = await _get_case_type(state["case_id"])
    relevance = _compute_evidence_relevance(case_type, classify_results)
    relevance_warnings: list[dict] = []
    if relevance["relevance_ratio"] < RELEVANCE_WARN_THRESHOLD:
        # 相关性极低时降为 warn（已经是 warn 则不变）
        quality_status = "warn"
    if relevance["all_other"] and relevance["relevance_ratio"] < RELEVANCE_WARN_THRESHOLD:
        # 触发相关性警告：并入 issues 供前端「材料理解」质量面板呈现橙色提示
        expected_labels = "、".join(
            CATEGORY_LABELS.get(c, c) for c in relevance["expected_categories"]
        ) or "相关证据材料"
        type_label = CASE_TYPE_LABELS.get(case_type, case_type or "未知")
        relevance_warnings.append({
            "code": "material.evidence_low_relevance",
            "message": (
                f"上传的证据类型与所选案件类型（{type_label}）匹配度较低"
                f"（{round(relevance['relevance_ratio'] * 100)}%），"
                f"预期证据类型：{expected_labels}。建议确认上传的图片是否为相关证据材料。"
            ),
            "severity": "warning",
            "evidence_id": None,
            "stage": "classify",
        })

    error_dicts = convert_string_errors_to_dicts(errors, stage="classify")
    provenance = [
        {
            "node": "classify",
            "evidence_id": r.get("evidence_id"),
            "field_name": None,
            "source_ref": f"classify:{r.get('evidence_code', '')}:{r.get('evidence_category', 'other')}",
            "ts": start_time.isoformat(),
        }
        for r in classify_results
    ]
    node_result = build_node_result(
        node_name="classify",
        data={
            "evidence_count": len(classify_results),
            "avg_confidence": avg_confidence,
            "category_distribution": category_distribution,
        },
        quality=QualityReport(
            score=avg_confidence,
            coverage=coverage,
            status=quality_status,
            blocking_issues=[],
            details={
                "avg_confidence": avg_confidence,
                "category_distribution": category_distribution,
                # Gate 1 相关性详情
                "evidence_relevance_ratio": relevance["relevance_ratio"],
                "evidence_all_other": relevance["all_other"],
                "evidence_expected_categories": relevance["expected_categories"],
                "evidence_matched_count": relevance["matched_count"],
                "evidence_total_count": relevance["total_count"],
            },
        ),
        warnings=relevance_warnings,
        errors=error_dicts,
        provenance=provenance,
        start_time=start_time,
        model_calls=len(low_confidence),
    )

    # Gate 1：仅在相关性告警触发时创建 classify_result 产物承载该警告，使其经
    # snapshot（仅聚合 artifacts 的 issues）透出到前端 QualitySummary / IssueList。
    # 正常运行不创建此产物，行为与改造前一致。
    workflow_run_id = state.get("workflow_run_id")
    if relevance_warnings and workflow_run_id:
        try:
            from api.agents.artifact_service import create_artifact
            warning_provenance = list(provenance) + [{
                "node": "classify",
                "code": "material.evidence_low_relevance",
                "warning": relevance_warnings[0]["message"],
                "source_ref": "classify:relevance",
                "ts": start_time.isoformat(),
            }]
            await sync_to_async(create_artifact)(
                workflow_run_id=workflow_run_id,
                case_id=state["case_id"],
                artifact_type="classify_result",
                stage="material_understanding",
                node_name="classify",
                content={
                    "evidence_count": len(classify_results),
                    "category_distribution": category_distribution,
                    "evidence_relevance_ratio": relevance["relevance_ratio"],
                    "evidence_all_other": relevance["all_other"],
                    "evidence_expected_categories": relevance["expected_categories"],
                },
                summary={
                    "evidence_relevance_ratio": relevance["relevance_ratio"],
                    "evidence_all_other": relevance["all_other"],
                },
                quality=node_result.get("quality", {}),
                provenance=warning_provenance,
                revision=state.get("revision", 0) + 1,
            )
        except Exception as e:  # pragma: no cover - 产物创建失败不阻塞主流程
            logger.warning(f"[分类] 创建低相关性告警产物失败（忽略）: {e}")

    return make_node_partial_update(
        node_name="classify",
        stage="material_understanding",
        progress=0.30,
        state=state,
        node_result=node_result,
        legacy_fields={
            "evidence_classify_results": classify_results,
            "errors": error_dicts,
            # Gate 1：供下游节点/审计读取的分类质量概览
            "evidence_relevance_ratio": relevance["relevance_ratio"],
            "evidence_all_other": relevance["all_other"],
        },
    )


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
