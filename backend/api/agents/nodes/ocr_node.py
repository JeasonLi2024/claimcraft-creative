# -*- coding: utf-8 -*-
"""OCR 节点（async）：循环处理案件所有有图证据 + 多策略 OCR + 同款模型纠错。

重构说明（v4 异步化）：
- def → async def，支持 LangGraph v1.2.0 add_node(timeout=) 节点级超时
- Django ORM 调用用 sync_to_async 包装，避免 SynchronousOnlyOperation
- 多证据并发处理（asyncio.gather），提升吞吐
- @traceable 装饰器，LangSmith UI 显示独立 Run

纠错策略（v8 重构）：
- 纠错下放到 OCR 策略内部自管，确保「识别用啥纠错用啥」
- LLM Vision 策略：用同款 LLM（self._llm）纠错
- PaddleOCR-VL / 本地 PaddleOCR / Tesseract / Mock：不纠错（返回原文）
- ocr_node 不再统一调 LLM 纠错，直接用 pipeline 返回的 corrected_text

降级策略：
- OCR 全部策略失败 → Mock 兜底文本
"""
import asyncio
import logging
from typing import Any

from asgiref.sync import sync_to_async

from api.agents.state import CaseWorkflowState

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


@traceable(name="OCR节点", run_type="chain")
async def ocr_node(state: CaseWorkflowState) -> dict[str, Any]:
    """OCR 节点（async）：循环处理案件所有有图证据，返回累积结果。

    流程：
    1. 确定待处理证据列表（evidence_ids 或案件全部有图证据）
    2. 对每条证据执行 OCRPipeline.recognize()（含同款模型纠错）
    3. 同步更新 Evidence.extracted_text 和 ocr_status
    4. 累积结果到 evidence_ocr_results
    """
    from api.models import Case, Evidence
    from api.services.ocr_service import ocr_image_with_strategy

    case_id = state["case_id"]
    evidence_ids = state.get("evidence_ids", [])
    # 复用预分类节点的 evidence_category（按 evidence_id 索引）
    # 用途：透传给 LLMVisionStrategy 选 OCR prompt（按类型精细处理）
    preclassify_map = {
        r["evidence_id"]: r.get("evidence_category", "")
        for r in state.get("evidence_preclassify_results", [])
    }
    errors = []

    # 1. 确定待处理证据列表
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
        errors.append("无可识别的证据图片")
        return {
            "evidence_ocr_results": [],
            "errors": errors,
        }

    # 2. 获取案件描述（透传给策略用于纠错上下文）
    try:
        case = await sync_to_async(Case.objects.get)(pk=case_id)
        case_description = case.description or ""
    except Case.DoesNotExist:
        case_description = ""

    # 3. 多证据并发 OCR + 同款模型纠错（策略内部自管）
    # 注：ocr_image_with_strategy 已改为 async，直接 await 即可

    # 3.0 过滤纯物证图片（跳过 OCR，但仍出现在 ocr_results 中）
    physical_evidences = [e for e in evidences if e.is_physical_evidence]
    ocr_evidences = [e for e in evidences if not e.is_physical_evidence]

    if physical_evidences:
        logger.info(f"跳过 {len(physical_evidences)} 条纯物证图片的 OCR")

    # 为物证图片构造跳过结果（保留在 ocr_results 中，让下游节点感知到这些证据存在）
    skip_results = [
        {
            "evidence_id": e.id,
            "evidence_code": e.code,
            "image_path": e.image.path if e.image else "",
            "ocr_raw_text": "",
            "ocr_corrected_text": "",
            "ocr_strategy_used": "skipped_physical",
            "ocr_status": "done",
            "evidence_category": preclassify_map.get(e.id, ""),
            "is_physical_evidence": True,
            "errors": [],
        }
        for e in physical_evidences
    ]

    async def _process_one(evidence):
        """处理单条证据的 OCR + 同款模型纠错 + 持久化。"""
        image_path = evidence.image.path
        # 从预分类结果读取 evidence_category，透传给 LLMVisionStrategy 选 prompt
        evidence_category = preclassify_map.get(evidence.id, "")
        logger.info(
            f"开始 OCR 证据 {evidence.code} (id={evidence.id}, "
            f"category={evidence_category or 'unknown'})"
        )

        # 注入 evidence_id metadata 到当前 LangSmith Run（UI 可按证据筛选）
        if ls is not None:
            try:
                rt = ls.get_current_run_tree()
                if rt:
                    rt.metadata["evidence_id"] = evidence.id
                    rt.metadata["evidence_code"] = evidence.code
                    if evidence_category:
                        rt.metadata["evidence_category"] = evidence_category
                    rt.tags.extend([f"evidence-{evidence.code}"])
            except Exception as e:
                logger.debug(f"注入 evidence_id metadata 失败（忽略）: {e}")

        # 3.1 OCR 识别 + 同款模型纠错（pipeline 内部完成）
        # 注：ocr_image_with_strategy 已 async，直接 await
        try:
            raw_text, corrected_text, strategy_used = await ocr_image_with_strategy(
                image_path, case_description, evidence_category
            )
        except Exception as e:
            logger.error(f"证据 {evidence.code} OCR 失败: {e}", exc_info=True)
            errors.append(f"[OCR] 证据 {evidence.code} 识别失败: {e}")
            evidence.ocr_status = "failed"
            await sync_to_async(evidence.save)(update_fields=["ocr_status"])
            return {
                "evidence_id": evidence.id,
                "evidence_code": evidence.code,
                "image_path": image_path,
                "ocr_raw_text": "",
                "ocr_corrected_text": "",
                "ocr_strategy_used": "failed",
                "ocr_status": "failed",
                "evidence_category": evidence_category,
                "errors": [str(e)],
            }

        # 3.2 持久化
        try:
            evidence.extracted_text = corrected_text
            evidence.ocr_status = "done"
            await sync_to_async(evidence.save)(update_fields=["extracted_text", "ocr_status"])
        except Exception as e:
            logger.error(f"更新 Evidence {evidence.code} 失败: {e}", exc_info=True)
            errors.append(f"更新 Evidence {evidence.code} 失败: {e}")

        corrected_flag = "yes" if corrected_text != raw_text else "no"
        logger.info(
            f"证据 {evidence.code} OCR 完成 (strategy={strategy_used}, "
            f"corrected={corrected_flag}, len={len(corrected_text)})"
        )
        return {
            "evidence_id": evidence.id,
            "evidence_code": evidence.code,
            "image_path": image_path,
            "ocr_raw_text": raw_text,
            "ocr_corrected_text": corrected_text,
            "ocr_strategy_used": strategy_used,
            "ocr_status": "done",
            "evidence_category": evidence_category,
            "is_physical_evidence": False,
            "errors": [],
        }

    results = await asyncio.gather(*[_process_one(e) for e in ocr_evidences])
    ocr_results = [r for r in results if isinstance(r, dict)] + skip_results

    return {
        "evidence_ocr_results": ocr_results,
        "errors": errors,
    }
