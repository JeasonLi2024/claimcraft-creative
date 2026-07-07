# -*- coding: utf-8 -*-
"""视觉预分类+摘要节点（async）：Qwen3-Omni Captioner 一次性输出证据类型+文本摘要。

新增节点（v9 工作流优化）：
- 输入：state.evidence_ids 或案件全部有图证据
- 输出：state.evidence_preclassify_results（每条证据的预分类+摘要+置信度）
- 模型：Qwen/Qwen3-Omni-30B-A3B-Captioner（SiliconFlow）
- 降级：Captioner 不可用时全部标记 other、summary=""、confidence=0.0

性能优化：
- 多图并行 asyncio.gather
- 图片压缩接入（复用 ocr_strategies._encode_and_compress_image，防解压炸弹）

安全最佳实践（DJANGO-UPLOAD-001）：
- 用户上传图片视为不可信，PIL 打开前设置 Image.MAX_IMAGE_PIXELS 防解压炸弹
- image_path 来自 Django storage 管理，非用户直接输入路径
"""
import asyncio
import json
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

# 预分类置信度阈值（>= 此值时 classify 节点直接采纳，跳过 LLM 细化）
PRECLASSIFY_CONFIDENCE_THRESHOLD = 0.8

# 合法的证据类别白名单（防止 LLM 输出越界值）
VALID_CATEGORIES = {
    "chat_screenshot", "product_order", "logistics_tracking",
    "payment_record", "invoice", "other",
}


@traceable(name="视觉预分类节点", run_type="chain")
async def preclassify_node(state: CaseWorkflowState) -> dict[str, Any]:
    """视觉预分类+摘要节点（async）：用 Captioner 一次性输出类型+摘要+置信度。

    流程：
    1. 确定待处理证据列表（evidence_ids 或案件全部有图证据）
    2. 多图并行调用 captioner LLM（ainvoke）
    3. 解析 JSON 输出，校验类别合法性
    4. 持久化 evidence_category + ocr_summary 到 Evidence
    5. 累积结果到 evidence_preclassify_results
    """
    from api.models import Case, Evidence
    from api.agents.prompts.templates import PRECLASSIFY_PROMPT
    from api.services.ocr_strategies import _encode_and_compress_image
    from api.services.ocr_config import get_llm_ocr_max_image_mb
    from langchain_core.messages import HumanMessage

    case_id = state["case_id"]
    evidence_ids = state.get("evidence_ids", [])
    errors = []

    # 1. 确定待处理证据列表（与 ocr_node 同模式）
    if evidence_ids:
        evidences = await sync_to_async(list)(
            Evidence.objects.filter(pk__in=evidence_ids, case_id=case_id)
            .exclude(image="")
            .exclude(image__isnull=True)
            .order_by("order", "code")
        )
    else:
        evidences = await sync_to_async(list)(
            Evidence.objects.filter(case_id=case_id)
            .exclude(image="")
            .exclude(image__isnull=True)
            .order_by("order", "code")
        )

    if not evidences:
        errors.append("[预分类] 无可识别的证据图片")
        return {
            "evidence_preclassify_results": [],
            "errors": errors,
        }

    # 2. Captioner 可用性检查（不可用时全部降级为 other）
    if not llm_service.is_scenario_available("captioner"):
        logger.info("[预分类] Captioner 不可用，全部标记为 other")
        results = [
            {
                "evidence_id": e.id,
                "evidence_code": e.code,
                "evidence_category": "other",
                "ocr_summary": "",
                "confidence": 0.0,
            }
            for e in evidences
        ]
        # 持久化降级结果
        for e, r in zip(evidences, results):
            try:
                e.evidence_category = r["evidence_category"]
                e.ocr_summary = r["ocr_summary"]
                await sync_to_async(e.save)(
                    update_fields=["evidence_category", "ocr_summary"]
                )
            except Exception as ex:
                logger.error(f"持久化预分类降级结果失败 {e.code}: {ex}", exc_info=True)
                errors.append(f"[预分类] 持久化 {e.code} 失败: {ex}")
        return {
            "evidence_preclassify_results": results,
            "errors": errors + ["[预分类] Captioner 不可用，全部标记为 other"],
        }

    # 3. 获取 captioner LLM 实例 + 案件描述
    try:
        case = await sync_to_async(Case.objects.get)(pk=case_id)
        case_description = case.description or ""
    except Case.DoesNotExist:
        case_description = ""

    captioner_llm = llm_service.get_scenario_llm("captioner")
    max_image_mb = get_llm_ocr_max_image_mb()  # 复用 OCR 的图片大小上限

    # 4. 多图并行调用 captioner（与 ocr_node 同模式）
    async def _process_one(evidence):
        """处理单条证据的视觉预分类+摘要+持久化。"""
        image_path = evidence.image.path
        logger.info(f"开始预分类证据 {evidence.code} (id={evidence.id})")

        # 注入 evidence_id metadata 到 LangSmith Run
        if ls is not None:
            try:
                rt = ls.get_current_run_tree()
                if rt:
                    rt.metadata["evidence_id"] = evidence.id
                    rt.metadata["evidence_code"] = evidence.code
                    rt.tags.extend([f"evidence-{evidence.code}"])
            except Exception as e:
                logger.debug(f"注入 evidence_id metadata 失败（忽略）: {e}")

        # 4.1 读取图片并压缩（防解压炸弹 + 降延迟）
        try:
            image_data, mime = await _encode_and_compress_image(image_path, max_image_mb)
        except Exception as e:
            logger.error(f"证据 {evidence.code} 图片读取失败: {e}", exc_info=True)
            errors.append(f"[预分类] 证据 {evidence.code} 图片读取失败: {e}")
            return _fallback_result(evidence, "图片读取失败")

        # 4.2 构造多模态消息 + 调用 captioner LLM
        message = HumanMessage(content=[
            {"type": "text", "text": PRECLASSIFY_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{image_data}"}},
        ])
        try:
            response = await captioner_llm.ainvoke([message])
            text = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.warning(f"证据 {evidence.code} Captioner 调用失败: {e}", exc_info=True)
            errors.append(f"[预分类] 证据 {evidence.code} Captioner 失败: {e}")
            return _fallback_result(evidence, "Captioner 调用失败")

        # 4.3 解析 JSON 输出（容错：剥离 markdown code fence）
        result = _parse_preclassify_json(text, evidence.code, errors)
        category = result["evidence_category"]
        summary = result["ocr_summary"]
        confidence = result["confidence"]

        # 4.4 持久化到 Evidence
        try:
            evidence.evidence_category = category
            evidence.ocr_summary = summary
            await sync_to_async(evidence.save)(
                update_fields=["evidence_category", "ocr_summary"]
            )
        except Exception as e:
            logger.error(f"持久化预分类结果失败 {evidence.code}: {e}", exc_info=True)
            errors.append(f"[预分类] 持久化 {evidence.code} 失败: {e}")

        logger.info(
            f"证据 {evidence.code} 预分类完成 (category={category}, "
            f"confidence={confidence:.2f}, summary_len={len(summary)})"
        )
        return {
            "evidence_id": evidence.id,
            "evidence_code": evidence.code,
            "evidence_category": category,
            "ocr_summary": summary,
            "confidence": confidence,
        }

    results = await asyncio.gather(*[_process_one(e) for e in evidences])
    preclassify_results = [r for r in results if isinstance(r, dict)]

    return {
        "evidence_preclassify_results": preclassify_results,
        "errors": errors,
    }


def _fallback_result(evidence, reason: str) -> dict:
    """构造降级结果（Captioner 不可用或调用失败时）。"""
    return {
        "evidence_id": evidence.id,
        "evidence_code": evidence.code,
        "evidence_category": "other",
        "ocr_summary": "",
        "confidence": 0.0,
        "_fallback_reason": reason,
    }


def _parse_preclassify_json(text: str, evidence_code: str, errors: list) -> dict:
    """解析 captioner LLM 的 JSON 输出（容错处理）。

    Args:
        text: LLM 原始输出（可能含 markdown code fence ```json ... ```）
        evidence_code: 证据编号（用于日志）
        errors: 错误累积列表

    Returns:
        dict: {evidence_category, ocr_summary, confidence}
    """
    # 剥离 markdown code fence
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 移除首行 ```json 或 ``` 标记
        lines = cleaned.split("\n")
        if len(lines) >= 2:
            cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"证据 {evidence_code} 预分类 JSON 解析失败: {e}, raw={text[:200]}")
        errors.append(f"[预分类] 证据 {evidence_code} JSON 解析失败")
        return {"evidence_category": "other", "ocr_summary": "", "confidence": 0.0}

    # 校验类别合法性（白名单防 LLM 越界输出）
    category = data.get("evidence_category", "other")
    if category not in VALID_CATEGORIES:
        logger.warning(f"证据 {evidence_code} 预分类类别非法: {category}, 回退 other")
        category = "other"

    summary = str(data.get("summary", "")).strip()
    # 置信度强制 float + 范围裁剪
    try:
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        logger.warning(f"证据 {evidence_code} 置信度非法: {data.get('confidence')}")
        confidence = 0.0

    return {
        "evidence_category": category,
        "ocr_summary": summary,
        "confidence": confidence,
    }
