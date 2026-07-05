# -*- coding: utf-8 -*-
"""证据链构造节点（async）：LLM 基于多证据字段和时间构造完整证据链。

重构说明（v4 异步化）：
- def → async def，支持节点级 timeout
- Django ORM 调用用 sync_to_async 包装
- LLM 调用用 .ainvoke()（LangChain 原生 async）
- @traceable 装饰器

新增节点（多证据工作流重构），替代原 timeline_node：
- 基础时间线：调用 timeline_service.rebuild_timeline() 重建
- LLM 增强：基于多证据 OCR 文本 + 抽取字段 + 分类结果构造完整证据链
- 降级：LLM 不可用时仅返回基础时间线

证据链节点结构：
{datetime, event, category, evidence_codes, chain_order}
"""
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

logger = logging.getLogger(__name__)


@traceable(name="证据链节点", run_type="chain")
async def evidence_chain_node(state: CaseWorkflowState) -> dict[str, Any]:
    """证据链构造节点（async）：LLM 基于多证据字段和时间构造完整证据链。

    流程：
    1. 调用 rebuild_timeline(case) 重建基础时间线（从 evidence.source_time + 抽取时间字段）
    2. 若 LLM 可用，构造完整证据链（with_structured_output + Pydantic）
    3. LLM 不可用时回退到基础时间线
    """
    from api.models import Case
    from api.services.timeline_service import rebuild_timeline
    from api.agents.schemas import EvidenceChainResult
    from api.agents.prompts.templates import EVIDENCE_CHAIN_PROMPT

    case_id = state["case_id"]
    ocr_results = state.get("evidence_ocr_results", [])
    classify_results = state.get("evidence_classify_results", [])
    extract_results = state.get("evidence_extract_results", [])
    errors = []

    try:
        case = await sync_to_async(Case.objects.get)(pk=case_id)
    except Case.DoesNotExist:
        return {
            "evidence_chain": [],
            "errors": [f"案件 {case_id} 不存在"],
        }

    # 1. 基础时间线重建
    try:
        await sync_to_async(rebuild_timeline)(case)
    except Exception as e:
        logger.error(f"时间线基础重建失败: {e}", exc_info=True)
        errors.append(f"时间线基础重建失败: {e}")

    # 2. LLM 构造完整证据链
    if not llm_service.is_scenario_available("text"):
        # LLM 不可用，仅返回基础时间线
        chain = await _build_fallback_chain(case)
        errors.append("[证据链] LLM 不可用，仅返回基础时间线")
        return {"evidence_chain": chain, "errors": errors}

    # 构造 LLM 输入
    evidences_json = _build_evidences_json(ocr_results, classify_results, extract_results)

    try:
        llm = llm_service.get_scenario_llm("text")
        # DashScope 不兼容 json_schema 模式，改用 function_calling 模式
        structured_llm = llm.with_structured_output(EvidenceChainResult, method="function_calling")
        prompt = EVIDENCE_CHAIN_PROMPT.format(
            case_description=case.description or "",
            evidences_json=evidences_json,
        )
        result = await structured_llm.ainvoke(prompt)
        chain = [
            {
                "datetime": n.datetime,
                "event": n.event,
                "category": n.category,
                "evidence_codes": n.evidence_codes,
                "chain_order": n.chain_order,
            }
            for n in result.nodes
        ]
        logger.info(
            f"证据链构造完成（LLM），共 {len(chain)} 个节点"
        )
    except Exception as e:
        logger.warning(f"LLM 证据链构造失败，回退到基础时间线: {e}")
        errors.append(f"[证据链] LLM 构造失败: {e}")
        chain = await _build_fallback_chain(case)

    return {"evidence_chain": chain, "errors": errors}


def _build_evidences_json(
    ocr_results: list[dict],
    classify_results: list[dict],
    extract_results: list[dict],
) -> str:
    """构造 LLM 输入的证据列表 JSON。"""
    # 构建 evidence_id → category 映射
    category_map = {
        c["evidence_id"]: c.get("evidence_category", "other")
        for c in classify_results
    }
    # 构建 evidence_id → fields 映射
    fields_map = {
        e["evidence_id"]: e.get("fields", [])
        for e in extract_results
    }

    evidences = []
    for o in ocr_results:
        eid = o["evidence_id"]
        evidences.append({
            "evidence_code": o["evidence_code"],
            "ocr_text": (o.get("ocr_corrected_text") or o.get("ocr_raw_text", ""))[:500],
            "category": category_map.get(eid, "other"),
            "fields": fields_map.get(eid, []),
        })

    return json.dumps(evidences, ensure_ascii=False, indent=2)


async def _build_fallback_chain(case) -> list[dict]:
    """LLM 不可用时的回退：从 DB 时间线节点构造链。"""
    from api.models import TimelineNode

    timeline_nodes = await sync_to_async(list)(
        TimelineNode.objects.filter(
            case=case, auto_generated=True
        ).order_by("datetime")
    )

    chain = []
    for i, n in enumerate(timeline_nodes):
        chain.append({
            "datetime": n.datetime.isoformat() if n.datetime else "",
            "event": n.event,
            "category": n.category or "其他",
            "evidence_codes": [
                c.strip()
                for c in (n.related_evidence_codes or "").split(",")
                if c.strip()
            ],
            "chain_order": i,
        })
    return chain
