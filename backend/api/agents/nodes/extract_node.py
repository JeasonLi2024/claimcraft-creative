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
from typing import Any

from asgiref.sync import sync_to_async

from api.agents.state import CaseWorkflowState
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
    "other": "其他",
}


@traceable(name="字段抽取节点", run_type="chain")
async def extract_node(state: CaseWorkflowState) -> dict[str, Any]:
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

    case_id = state["case_id"]
    ocr_results = state.get("evidence_ocr_results", [])
    classify_results = state.get("evidence_classify_results", [])
    errors = []

    if not ocr_results:
        return {
            "evidence_extract_results": [],
            "needs_human_review": False,
            "errors": ["[抽取] 无 OCR 结果"],
        }

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

        # 注入 evidence_id metadata 到当前 LangSmith Run（UI 可按证据筛选）
        if ls is not None:
            try:
                rt = ls.get_current_run_tree()
                if rt:
                    rt.metadata["evidence_id"] = evidence_id
                    rt.metadata["evidence_code"] = evidence_code
                    rt.tags.extend([f"evidence-{evidence_code}"])
            except Exception as e:
                logger.debug(f"注入 evidence_id metadata 失败（忽略）: {e}")

        # 1. 正则抽取（始终作为兜底）
        regex_fields = await sync_to_async(extract_fields_regex)(text)

        # 2. LLM 抽取（langextract 或 with_structured_output）
        llm_fields = []
        if not text.strip():
            pass  # 空文本跳过 LLM
        elif use_langextract:
            llm_fields = await _extract_with_langextract(text, evidence_code, errors)
        elif use_structured_output:
            llm_fields = await _extract_with_structured_output(
                text, evidence_code, category_map.get(evidence_id, "other"), errors
            )

        # 3. 合并去重
        merged = await sync_to_async(merge_fields)(regex_fields, llm_fields)

        # 4. HITL 判断
        needs_review = any(
            f.get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD for f in merged
        )
        if needs_review:
            any_needs_review = True

        # 5. 持久化（幂等：先 delete 再 create）
        try:
            evidence = await sync_to_async(Evidence.objects.get)(pk=evidence_id, case_id=case_id)
            await sync_to_async(evidence.extracted_fields.all().delete)()
            for f in merged:
                await sync_to_async(ExtractedField.objects.create)(
                    evidence=evidence,
                    field_name=f["field_name"],
                    field_value=f["field_value"],
                    confidence=f.get("confidence", 0.7),
                )
        except Evidence.DoesNotExist:
            errors.append(f"证据 {evidence_id} 不存在，无法持久化抽取字段")
        except Exception as e:
            logger.error(f"持久化抽取字段失败: {e}", exc_info=True)
            errors.append(f"持久化抽取字段失败: {e}")

        logger.info(
            f"证据 {evidence_code} 抽取完成 ({len(merged)} 字段, "
            f"needs_review={needs_review})"
        )
        return {
            "evidence_id": evidence_id,
            "evidence_code": evidence_code,
            "fields": merged,
            "needs_human_review": needs_review,
        }

    results = await asyncio.gather(*[_process_one(ocr) for ocr in ocr_results])
    extract_results = [r for r in results if isinstance(r, dict)]

    return {
        "evidence_extract_results": extract_results,
        "needs_human_review": any_needs_review,
        "errors": errors,
    }


async def _extract_with_langextract(
    text: str, evidence_code: str, errors: list[str]
) -> list[dict]:
    """使用 LangExtract (Qwen3 + OpenAI 兼容接口 + 少样本示例) 抽取字段。

    通过 langextract.factory.ModelConfig 显式指定 provider=openai，
    支持任意 OpenAI 兼容接口（SiliconFlow / DashScope / 自建网关）。
    官方文档：https://github.com/google/langextract

    Args:
        text: OCR 识别后的文本
        evidence_code: 证据编号（用于日志）
        errors: 错误累积列表

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
        result = await sync_to_async(lx.extract)(
            text_or_documents=text,
            prompt_description=get_prompt_description(),
            examples=get_examples(),
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
        structured_llm = llm.with_structured_output(ExtractResult)
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
