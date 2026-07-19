# -*- coding: utf-8 -*-
"""字段抽取节点（async）：LangExtract（首选）→ with_structured_output（降级）→ 正则（兜底）。

重构说明（v4 异步化）：
- def → async def，支持节点级 timeout
- Django ORM 调用用 sync_to_async 包装
- LangExtract / 正则抽取用 sync_to_async 包装（同步库）
- with_structured_output 用 .ainvoke()（LangChain 原生 async）
- 多证据并发处理（asyncio.gather）
- @traceable 装饰器

重构说明（多证据工作流 + langextract）：
- 优先使用 Google langextract（通过 OpenAI 兼容接口调用 Qwen3 + 少样本示例）
- LANGEXTRACT_API_KEY 未配置时降级到 LangChain with_structured_output + Pydantic
- LLM 完全不可用时仅用正则
- 循环处理每条证据，根据分类结果注入 case_type 上下文

LangExtract 优势：
- 精确源定位（char_interval）便于人工校正
- 少样本示例约束输出格式，无需复杂 prompt 工程
- 长文档优化（extraction_passes + 并行处理）
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from asgiref.sync import sync_to_async
from langgraph.graph import END
from langgraph.types import Command, interrupt

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

try:
    import langsmith as ls
except ImportError:
    ls = None

logger = logging.getLogger(__name__)

# 触发 HITL 的置信度阈值
LOW_CONFIDENCE_THRESHOLD = 0.7

# 证据类别 → 案件类型映射
CATEGORY_TO_CASE_TYPE = {
    "chat_screenshot": "聊天记录",
    "product_order": "商品订单",
    "logistics_tracking": "物流跟踪",
    "payment_record": "支付凭证",
    "invoice": "发票",
    "other": "其他",
}

# 字段名 → 字段分类映射（用于 ExtractedField.field_category）
# 按 7 类聚合：订单信息/支付信息/物流信息/发票信息/联系信息/时间信息/其他
FIELD_CATEGORY_MAP = {
    "订单号": "订单信息", "商家名称": "订单信息", "商品名称": "订单信息",
    "金额": "支付信息", "交易流水号": "支付信息", "支付方式": "支付信息",
    "付款时间": "支付信息", "收款方": "支付信息", "退款金额": "支付信息",
    "物流单号": "物流信息", "地址": "物流信息",
    "手机号": "联系信息", "邮箱": "联系信息",
    "时间": "时间信息", "开票日期": "时间信息",
    "发票代码": "发票信息", "发票号码": "发票信息", "购买方": "发票信息",
    "销售方": "发票信息", "税率": "发票信息", "税额": "发票信息",
    "价税合计": "发票信息",
    "承诺话术": "其他",
}

# 缓存命中阈值：若已有 ≥此数量的高置信度字段且 source_hash 未变，跳过 LLM 抽取
CACHE_HIT_FIELD_COUNT = 3
CACHE_HIT_CONFIDENCE = 0.9

# ============================================================================
# Gate 2：证据质量硬性拦截门（input-quality-guard）
# ============================================================================
# 预分类平均置信度低于此值视为「LLM 本身也没把握」。
CRITICAL_PRECLASSIFY_CONFIDENCE = 0.5


def _is_evidence_critically_insufficient(
    classify_results: list[dict],
    preclassify_results: list[dict],
    total_fields: int,
) -> bool:
    """判断证据质量是否低到必须阻断流程的程度（Gate 2，严格 AND）。

    三条件同时满足才触发：
    1. 所有证据均被分类为 other（all_other）
    2. 预分类平均置信度 < CRITICAL_PRECLASSIFY_CONFIDENCE（LLM 本身没把握）
    3. 全流程未提取到任何有效字段（total_fields == 0）

    任一不满足即不触发（如：物证图片全 other 但描述充分 fields>0 → 不触发）。
    """
    if not classify_results:
        # 无证据是另一个问题（preclassify_node 已处理），此处不拦截
        return False

    all_other = all(
        r.get("evidence_category") == "other" for r in classify_results
    )
    if not all_other:
        return False

    if preclassify_results:
        avg_confidence = sum(
            r.get("confidence", 0.0) for r in preclassify_results
        ) / len(preclassify_results)
    else:
        avg_confidence = 0.0

    return avg_confidence < CRITICAL_PRECLASSIFY_CONFIDENCE and total_fields == 0


@traceable(name="字段抽取节点", run_type="chain")
async def extract_node(state: CaseWorkflowState) -> "dict[str, Any] | Command":
    """字段抽取节点（async）：循环处理每条证据。

    优先级链：
    1. LangExtract（Qwen3 + OpenAI 兼容接口 + 少样本示例）—— 精度最高
    2. with_structured_output + Pydantic —— LangExtract 不可用时降级
    3. 正则兜底 —— LLM 完全不可用时
    """
    from api.models import Case, Evidence, ExtractedField
    from api.agents.tools.regex_tools import extract_fields_regex, merge_fields
    from api.agents.prompts.templates import EXTRACT_FIELDS_PROMPT
    from api.agents.schemas import ExtractResult
    from api.agents.examples import (
        is_langextract_available, get_examples, get_model_id,
        get_extraction_passes, get_prompt_description,
        get_api_key, get_base_url, get_provider,
    )
    import hashlib

    case_id = state["case_id"]
    ocr_results = state.get("evidence_ocr_results", [])
    classify_results = state.get("evidence_classify_results", [])
    errors = []
    start_time = datetime.now(timezone.utc)

    if not ocr_results:
        errors.append("[抽取] 无 OCR 结果")
        error_dicts = convert_string_errors_to_dicts(errors, stage="extract")
        node_result = build_node_result(
            node_name="extract",
            data={"evidence_count": 0},
            quality=QualityReport(
                score=0.0,
                coverage=0.0,
                status="fail",
                blocking_issues=[],
                details={"reason": "no_ocr_results"},
            ),
            warnings=[],
            errors=error_dicts,
            provenance=[],
            start_time=start_time,
            model_calls=0,
        )
        return make_node_partial_update(
            node_name="extract",
            stage="fact_checking",
            progress=0.45,
            state=state,
            node_result=node_result,
            legacy_fields={
                "evidence_extract_results": [],
                "needs_human_review": False,
                "errors": error_dicts,
            },
        )

    # 过滤纯物证图片（无文字内容，跳过字段抽取）
    physical_results = [
        {
            "evidence_id": o["evidence_id"],
            "evidence_code": o["evidence_code"],
            "fields": [],
            "needs_human_review": False,
            "source_hash": "",
            "cache_hit": False,
            "skipped_physical": True,
        }
        for o in ocr_results
        if o.get("is_physical_evidence")
    ]
    ocr_results = [o for o in ocr_results if not o.get("is_physical_evidence")]

    if physical_results:
        logger.info(f"跳过 {len(physical_results)} 条纯物证图片的字段抽取")

    # 构建 evidence_id → category 映射
    category_map = {
        c["evidence_id"]: c.get("evidence_category", "other")
        for c in classify_results
    }

    # 判断 langextract 可用性
    use_langextract = is_langextract_available()
    use_structured_output = (not use_langextract) and llm_service.is_scenario_available("text")

    if use_langextract:
        logger.info(f"使用 LangExtract (Qwen3) 进行字段抽取 (model={get_model_id()})")
    elif use_structured_output:
        logger.info("LangExtract 不可用，降级到 with_structured_output + Pydantic")
    else:
        logger.info("LLM 不可用，仅用正则抽取")

    any_needs_review = False

    # 多证据并发抽取
    async def _process_one(ocr):
        nonlocal any_needs_review
        evidence_id = ocr["evidence_id"]
        evidence_code = ocr["evidence_code"]
        text = ocr.get("ocr_corrected_text") or ocr.get("ocr_raw_text", "")
        category = category_map.get(evidence_id, "other")

        # 注入 evidence_id metadata 到当前 LangSmith Run（UI 可按证据筛选）
        if ls is not None:
            try:
                rt = ls.get_current_run_tree()
                if rt:
                    rt.metadata["evidence_id"] = evidence_id
                    rt.metadata["evidence_code"] = evidence_code
                    rt.metadata["evidence_category"] = category
                    rt.tags.extend([f"evidence-{evidence_code}", f"category-{category}"])
            except Exception as e:
                logger.debug(f"注入 evidence_id metadata 失败（忽略）: {e}")

        # 计算 OCR 文本哈希（用于缓存比对，避免重复抽取）
        source_hash = hashlib.md5(text.encode("utf-8")).hexdigest() if text else ""

        # 0. 缓存检查：若该证据已有 ≥3 个高置信度字段且 source_hash 未变，跳过抽取
        cached_fields = await _check_extract_cache(evidence_id, source_hash)
        if cached_fields is not None:
            logger.info(f"证据 {evidence_code} 缓存命中（source_hash 未变），跳过抽取")
            # HITL 判断仍基于缓存字段的置信度
            needs_review = any(
                f.get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD
                for f in cached_fields
            )
            if needs_review:
                any_needs_review = True
            return {
                "evidence_id": evidence_id,
                "evidence_code": evidence_code,
                "fields": cached_fields,
                "needs_human_review": needs_review,
                "source_hash": source_hash,
                "cache_hit": True,
            }

        # 1. 正则抽取（始终作为兜底）
        regex_fields = await sync_to_async(extract_fields_regex)(text)

        # 2. LLM 抽取（langextract 或 with_structured_output，按 category 选少样本）
        llm_fields = []
        if not text.strip():
            pass  # 空文本跳过 LLM
        elif use_langextract:
            llm_fields = await _extract_with_langextract(
                text, evidence_code, errors, category
            )
        elif use_structured_output:
            llm_fields = await _extract_with_structured_output(
                text, evidence_code, category, errors
            )

        # 3. 合并去重
        merged = await sync_to_async(merge_fields)(regex_fields, llm_fields)

        # 4. 为每个字段补充 field_category（按字段名映射）
        for f in merged:
            f["field_category"] = FIELD_CATEGORY_MAP.get(f["field_name"], "其他")

        # 5. HITL 判断
        needs_review = any(
            f.get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD for f in merged
        )
        if needs_review:
            any_needs_review = True

        # 6. 持久化（幂等：先 delete 再 create，写入 field_category + source_hash）
        # Task 2.4：首次抽取的字段 user_confirmed=False（用户尚未校正）
        try:
            evidence = await sync_to_async(Evidence.objects.get)(pk=evidence_id, case_id=case_id)
            await sync_to_async(evidence.extracted_fields.all().delete)()
            for f in merged:
                await sync_to_async(ExtractedField.objects.create)(
                    evidence=evidence,
                    field_name=f["field_name"],
                    field_value=f["field_value"],
                    confidence=f.get("confidence", 0.7),
                    field_category=f.get("field_category", "其他"),
                    source_hash=source_hash,
                    user_confirmed=False,
                )
        except Evidence.DoesNotExist:
            errors.append(f"证据 {evidence_id} 不存在，无法持久化抽取字段")
        except Exception as e:
            logger.error(f"持久化抽取字段失败: {e}", exc_info=True)
            errors.append(f"持久化抽取字段失败: {e}")

        logger.info(
            f"证据 {evidence_code} 抽取完成 ({len(merged)} 字段, "
            f"category={category}, needs_review={needs_review})"
        )
        return {
            "evidence_id": evidence_id,
            "evidence_code": evidence_code,
            "fields": merged,
            "needs_human_review": needs_review,
            "source_hash": source_hash,
            "cache_hit": False,
        }

    results = await asyncio.gather(*[_process_one(ocr) for ocr in ocr_results])
    extract_results = [r for r in results if isinstance(r, dict)] + physical_results

    # 计算 quality：字段完整率 + 低置信度数量
    total_evidences = len(extract_results)
    evidences_with_fields = sum(1 for er in extract_results if er.get("fields"))
    total_fields = sum(len(er.get("fields", [])) for er in extract_results)
    low_confidence_count = sum(
        1 for er in extract_results
        for f in er.get("fields", [])
        if f.get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD
    )
    # 字段完整率 = 1 - 低置信度占比
    field_quality_score = 1.0 - (low_confidence_count / max(total_fields, 1))
    coverage = evidences_with_fields / max(total_evidences, 1)
    quality_status = "fail" if any_needs_review else ("pass" if field_quality_score >= 0.7 else "warn")
    error_dicts = convert_string_errors_to_dicts(errors, stage="extract")
    # provenance: 字段来源 evidence_id + 区域
    provenance = [
        {
            "node": "extract",
            "evidence_id": er.get("evidence_id"),
            "field_name": f.get("field_name"),
            "source_ref": f"extract:{er.get('evidence_code', '')}:{f.get('field_name', '')}",
            "ts": start_time.isoformat(),
        }
        for er in extract_results
        for f in er.get("fields", [])
    ]
    node_result = build_node_result(
        node_name="extract",
        data={
            "evidence_count": total_evidences,
            "total_fields": total_fields,
            "low_confidence_count": low_confidence_count,
            "needs_human_review": any_needs_review,
        },
        quality=QualityReport(
            score=field_quality_score,
            coverage=coverage,
            status=quality_status,
            blocking_issues=[],
            details={
                "total_fields": total_fields,
                "low_confidence_count": low_confidence_count,
                "needs_human_review": any_needs_review,
            },
        ),
        warnings=[],
        errors=error_dicts,
        provenance=provenance,
        start_time=start_time,
        model_calls=len(ocr_results),
    )

    # ========================================================================
    # Gate 2：证据质量硬性拦截门（input-quality-guard）
    # 三条件（全 other + 预分类均值 < 0.5 + 零字段）同时满足时 interrupt，
    # 让用户选择「确认继续」或「终止重传」，避免 LLM 在无有效输入上捏造内容。
    # 幂等：create_intervention 用 update_or_create；resume 时整节点重跑，
    # 抽取命中缓存（source_hash 未变）跳过 LLM，不重复建介入记录。
    # ========================================================================
    preclassify_results = state.get("evidence_preclassify_results", [])
    if _is_evidence_critically_insufficient(
        classify_results, preclassify_results, total_fields
    ):
        from api.services.intervention_service import create_intervention

        if preclassify_results:
            avg_confidence = sum(
                r.get("confidence", 0.0) for r in preclassify_results
            ) / len(preclassify_results)
        else:
            avg_confidence = 0.0
        base_revision = state.get("revision", 0)
        workflow_run_id = state.get("workflow_run_id")
        evidence_count = len(classify_results)
        reason = (
            f"上传的 {evidence_count} 张图片均无法识别为有效证据材料"
            f"（平均识别置信度 {avg_confidence:.0%}），且未能提取任何结构化字段。"
            "如继续生成，文书内容将主要基于案件描述而非实际证据。"
        )
        diagnostics = {
            "evidence_count": evidence_count,
            "avg_preclassify_confidence": round(avg_confidence, 3),
            "total_extracted_fields": total_fields,
            "all_classified_other": True,
        }
        form_schema = {
            "fields": [
                {
                    "name": "action",
                    "label": "处理方式",
                    "type": "radio",
                    "required": True,
                    "initial_value": "confirm_continue",
                    "options": [
                        {
                            "value": "confirm_continue",
                            "label": "我了解风险，继续生成（输出质量可能较低）",
                        },
                        {
                            "value": "abort",
                            "label": "终止本次工作流，我将重新上传证据",
                        },
                    ],
                },
                {
                    "name": "notes",
                    "label": "补充说明（可选）",
                    "type": "textarea",
                    "required": False,
                },
            ]
        }
        initial_values = {
            "action": "confirm_continue",
            "evidence_count": evidence_count,
            "avg_confidence": round(avg_confidence, 3),
            "total_fields": total_fields,
        }
        # reason / required / diagnostics 写入 impact：WorkflowIntervention 模型无这些
        # 字段，snapshot_service 从 impact 派生后透出给前端面板。
        impact = {
            "downstream_nodes": ["evidence_chain", "complaint", "respond_complaint"],
            "rerun_required": False,
            "required": True,
            "reason": reason,
            "diagnostics": diagnostics,
        }

        intervention = await sync_to_async(create_intervention)(
            workflow_run_id=workflow_run_id,
            case_id=case_id,
            intervention_type="missing_information",
            stage="fact_checking",
            base_revision=base_revision,
            form_schema=form_schema,
            initial_values=initial_values,
            impact=impact,
        )

        payload = {
            "interrupt_type": "missing_information",
            "intervention_id": intervention.id,
            "intervention_kind": "missing_information",
            "required": True,
            "stage": "fact_checking",
            "reason": reason,
            "base_revision": base_revision,
            "form_schema": form_schema,
            "initial_values": initial_values,
            "impact": impact,
            "diagnostics": diagnostics,
        }

        resume_value = interrupt(payload)

        # ===== resume 后执行 =====
        # 解析用户选择（对齐 views.py submit → Command(resume={..., submitted_values})）
        if isinstance(resume_value, dict):
            submitted = resume_value.get("submitted_values")
            submitted = submitted if isinstance(submitted, dict) else {}
            action = submitted.get("action") or resume_value.get("action") or "confirm_continue"
        else:
            action = "confirm_continue"

        if action == "abort":
            logger.info("[抽取] 用户在 Gate 2 选择终止工作流（证据质量不足）")
            abort_errors = error_dicts + convert_string_errors_to_dicts(
                ["用户终止：证据质量不足，请重新上传证据"], stage="extract"
            )
            partial = make_node_partial_update(
                node_name="extract",
                stage="fact_checking",
                progress=0.45,
                state=state,
                node_result=node_result,
                legacy_fields={
                    "evidence_extract_results": extract_results,
                    "needs_human_review": False,
                    "errors": abort_errors,
                    "workflow_aborted_by_user": True,
                },
            )
            # 直接路由到 END，跳过 evidence_chain / complaint，避免生成文书。
            # workflow_runner 结束后读取 workflow_aborted_by_user 并 fail_processing。
            return Command(update=partial, goto=END)

        # confirm_continue：记录用户已知晓低质量，complaint_node 据此注入稀疏告知
        logger.info("[抽取] 用户在 Gate 2 确认在低质量证据下继续工作流")
        return make_node_partial_update(
            node_name="extract",
            stage="fact_checking",
            progress=0.45,
            state=state,
            node_result=node_result,
            legacy_fields={
                "evidence_extract_results": extract_results,
                "needs_human_review": any_needs_review,
                "errors": error_dicts,
                "low_quality_evidence_acknowledged": True,
            },
        )

    return make_node_partial_update(
        node_name="extract",
        stage="fact_checking",
        progress=0.45,
        state=state,
        node_result=node_result,
        legacy_fields={
            "evidence_extract_results": extract_results,
            "needs_human_review": any_needs_review,
            "errors": error_dicts,
        },
    )


async def _check_extract_cache(evidence_id: int, source_hash: str) -> list[dict] | None:
    """检查该证据是否已有可复用的抽取结果（source_hash 未变 + 高置信度）。

    缓存命中条件：
    1. 该证据已存在 ≥ CACHE_HIT_FIELD_COUNT 个 ExtractedField
    2. 所有字段的 source_hash 与当前一致（OCR 文本未变）
    3. 至少 1 个字段 confidence >= CACHE_HIT_CONFIDENCE

    Args:
        evidence_id: 证据 ID
        source_hash: 当前 OCR 文本的 MD5

    Returns:
        命中时返回字段列表 [{field_name, field_value, confidence, field_category, source}]
        未命中返回 None
    """
    if not source_hash:
        return None
    from api.models import ExtractedField

    try:
        existing = await sync_to_async(list)(
            ExtractedField.objects.filter(
                evidence_id=evidence_id, source_hash=source_hash
            )
        )
    except Exception as e:
        logger.debug(f"缓存检查失败（忽略，按未命中处理）: {e}")
        return None

    if len(existing) < CACHE_HIT_FIELD_COUNT:
        return None

    # 至少 1 个高置信度字段才视为有效缓存
    if not any(f.confidence >= CACHE_HIT_CONFIDENCE for f in existing):
        return None

    # 命中：构造字段列表（保持向后兼容字段格式）
    return [
        {
            "field_name": f.field_name,
            "field_value": f.field_value,
            "confidence": f.confidence,
            "field_category": f.field_category or "其他",
            "source": "cache",
        }
        for f in existing
    ]


async def _extract_with_langextract(
    text: str, evidence_code: str, errors: list[str], category: str = ""
) -> list[dict]:
    """使用 LangExtract (Qwen3 + OpenAI 兼容接口 + 少样本示例) 抽取字段。

    通过 langextract.factory.ModelConfig 显式指定 provider=openai，
    支持任意 OpenAI 兼容接口（SiliconFlow / DashScope / 自建网关）。
    官方文档：https://github.com/google/langextract

    Args:
        text: OCR 识别后的文本
        evidence_code: 证据编号（用于日志）
        errors: 错误累积列表
        category: 证据类别（用于按类型过滤少样本示例）

    Returns:
        list[dict]: [{field_name, field_value, confidence, source}]
    """
    import langextract as lx
    from langextract.factory import ModelConfig
    from api.agents.examples import (
        get_examples, get_model_id, get_extraction_passes, get_prompt_description,
        get_api_key, get_base_url, get_provider,
    )

    # 构造 provider_kwargs（OpenAI 兼容接口）
    provider_kwargs = {"api_key": get_api_key()}
    if get_base_url():
        provider_kwargs["base_url"] = get_base_url()

    config = ModelConfig(
        model_id=get_model_id(),
        provider=get_provider(),
        provider_kwargs=provider_kwargs,
    )

    try:
        # 按证据类别选少样本示例（同类 + 1 个通用示例）
        examples = get_examples(category)
        logger.info(
            f"LangExtract 调用 (evidence={evidence_code}, category={category or 'all'}, "
            f"examples={len(examples)})"
        )
        result = await sync_to_async(lx.extract)(
            text_or_documents=text,
            prompt_description=get_prompt_description(),
            examples=examples,
            config=config,
            extraction_passes=get_extraction_passes(),
        )

        fields = []
        for ext in result.extractions:
            # 过滤未定位的抽取（LLM 幻觉）
            char_interval = getattr(ext, "char_interval", None)
            if char_interval is None:
                logger.debug(f"证据 {evidence_code} 跳过未定位的抽取: {ext.extraction_class}={ext.extraction_text}")
                continue

            attributes = getattr(ext, "attributes", {}) or {}
            confidence = float(attributes.get("confidence", 0.85))
            normalized_value = attributes.get("normalized_value")

            fields.append({
                "field_name": ext.extraction_class,
                "field_value": normalized_value or ext.extraction_text,
                "confidence": confidence,
                "source": "langextract",
            })

        logger.info(f"证据 {evidence_code} LangExtract 抽取完成 ({len(fields)} 字段)")
        return fields

    except Exception as e:
        logger.warning(f"证据 {evidence_code} LangExtract 抽取失败: {e}", exc_info=True)
        errors.append(f"[抽取] 证据 {evidence_code} LangExtract 失败: {e}")
        return []


async def _extract_with_structured_output(
    text: str, evidence_code: str, category: str, errors: list[str]
) -> list[dict]:
    """使用 LangChain with_structured_output + Pydantic 抽取字段（降级方案）。

    Args:
        text: OCR 识别后的文本
        evidence_code: 证据编号（用于日志）
        category: 证据类别（chat_screenshot/product_order/...）
        errors: 错误累积列表

    Returns:
        list[dict]: [{field_name, field_value, confidence, source}]
    """
    from api.agents.schemas import ExtractResult
    from api.agents.prompts.templates import EXTRACT_FIELDS_PROMPT

    try:
        llm = llm_service.get_scenario_llm("text")
        # DashScope 不兼容 json_schema 模式，改用 function_calling 模式
        structured_llm = llm.with_structured_output(ExtractResult, method="function_calling")
        case_type = CATEGORY_TO_CASE_TYPE.get(category, "其他")
        prompt = EXTRACT_FIELDS_PROMPT.format(text=text, case_type=case_type)
        result = await structured_llm.ainvoke(prompt)
        fields = [
            {
                "field_name": f.field_name,
                "field_value": f.field_value,
                "confidence": f.confidence,
                "source": "llm",
            }
            for f in result.fields
        ]
        logger.info(f"证据 {evidence_code} with_structured_output 抽取完成 ({len(fields)} 字段)")
        return fields

    except Exception as e:
        logger.warning(f"证据 {evidence_code} with_structured_output 抽取失败: {e}")
        errors.append(f"[抽取] 证据 {evidence_code} LLM 抽取失败: {e}")
        return []
