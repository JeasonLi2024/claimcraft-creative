# -*- coding: utf-8 -*-
"""证据链构造节点（async）：LLM 基于多证据字段和时间构造完整证据链。

v10 增强版（工具强制调用）：
- 节点入口主动预检索 lookup_law（强制首次调用，失败降级）
- LLM 绑定 7 个法律工具（bind_tools + 多轮工具调用循环）
- 工具调用记录写入 state（evidence_chain_tool_calls）

重构说明（v4 异步化）：
- def → async def，支持节点级 timeout
- Django ORM 调用用 sync_to_async 包装
- LLM 调用用 .ainvoke()（LangChain 原生 async）
- @traceable 装饰器

证据链节点结构：
{datetime, event, category, evidence_codes, chain_order, summary}
"""
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from asgiref.sync import sync_to_async

from api.agents.state import CaseWorkflowState
from api.agents.schemas import QualityReport
from api.agents.utils.node_result_builder import (
    build_node_result,
    convert_string_errors_to_dicts,
    make_node_partial_update,
)
from api.agents.utils.progress import emit_progress
from api.services import llm_service

try:
    from langgraph.runtime import Runtime
except ImportError:  # pragma: no cover - langgraph 应已安装
    Runtime = object  # type: ignore[misc,assignment]

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def deco(fn):
            return fn
        return args[0] if args and callable(args[0]) else deco

logger = logging.getLogger(__name__)


# Store namespace 常量（对齐 spec.md Requirement: LangGraph Store Node Access Pattern）
_LEGAL_CACHE_TTL_DAYS = 7


def _legal_cache_namespace(case_id) -> tuple:
    """构造法律检索缓存 namespace：("case", str(case_id), "legal_cache")。"""
    return ("case", str(case_id), "legal_cache")


def _legal_cache_key(query: str) -> str:
    """根据查询文本生成 16 位 sha256 哈希作为 cache key。"""
    return f"legal_{hashlib.sha256(query.encode('utf-8')).hexdigest()[:16]}"


def _is_cache_expired(item, current_prompt_version: str) -> bool:
    """检查缓存是否过期。

    过期条件（满足任一）：
    - expires_at 已过当前 UTC 时间
    - prompt_bundle_version 与当前不一致（缓存基于旧 prompt 版本）

    Args:
        item: Store.get 返回的 Item 对象
        current_prompt_version: 当前 state 中的 prompt_bundle_version

    Returns:
        True 表示缓存已过期需重新生成；False 表示仍有效。
    """
    if item is None:
        return True
    value = getattr(item, "value", None)
    if not isinstance(value, dict):
        return True

    # TTL 检查
    expires_at_str = value.get("expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                return True
        except (ValueError, TypeError):
            # 过期时间解析失败视为过期（防御性）
            return True
    else:
        # 无 expires_at 字段视为过期（防御性）
        return True

    # prompt_bundle_version 一致性检查
    cached_prompt_version = value.get("prompt_bundle_version")
    if current_prompt_version and cached_prompt_version and cached_prompt_version != current_prompt_version:
        return True

    return False


def _get_cached_legal_result(runtime, case_id, query: str, current_prompt_version: str):
    """从 Store 读取缓存的法条检索结果。

    Returns:
        (result_list, was_invalidated): result_list 为 None 表示未命中或已过期。
    """
    if runtime is None or getattr(runtime, "store", None) is None:
        return None, False
    try:
        item = runtime.store.get(
            _legal_cache_namespace(case_id), _legal_cache_key(query)
        )
    except Exception:
        return None, False
    if item is None:
        return None, False
    if _is_cache_expired(item, current_prompt_version):
        # 过期：清理旧条目
        try:
            runtime.store.delete(
                _legal_cache_namespace(case_id), _legal_cache_key(query)
            )
        except Exception:
            pass
        return None, True
    value = getattr(item, "value", None)
    if not isinstance(value, dict):
        return None, False
    result = value.get("result")
    return result, False


def _put_cached_legal_result(
    runtime, case_id, query: str, result, current_prompt_version: str
) -> None:
    """将法条检索结果写入 Store（含 TTL + prompt_bundle_version 元数据）。"""
    if runtime is None or getattr(runtime, "store", None) is None:
        return
    try:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=_LEGAL_CACHE_TTL_DAYS)).isoformat()
        runtime.store.put(
            _legal_cache_namespace(case_id),
            _legal_cache_key(query),
            {
                "result": result,
                "query": query,
                "expires_at": expires_at,
                "prompt_bundle_version": current_prompt_version,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        pass


@traceable(name="证据链节点", run_type="chain")
async def evidence_chain_node(state: CaseWorkflowState, runtime: Runtime = None) -> dict[str, Any]:
    """证据链构造节点（async，Task 5.1 升级签名以访问 runtime.store）。

    流程：
    1. 调用 rebuild_timeline(case) 重建基础时间线
    2. Task 5.1.3：调用 LawRetriever 前先查 Store 缓存（legal_cache namespace）
       - 命中且未过期：跳过 BM25 + 向量检索 + Rerank
       - 未命中或过期：执行 RAG 流程，结果写入 Store（TTL 7 天）
    3. LLM 绑定 7 个工具 + 多轮工具调用循环
    4. 解析 JSON 输出为证据链
    5. LLM 不可用时回退到基础时间线
    """
    from api.models import Case
    from api.services.timeline_service import rebuild_timeline
    from api.agents.prompts.templates import (
        EVIDENCE_CHAIN_PROMPT,
        LAW_ARTICLES_SECTION_TEMPLATE,
        LAW_ARTICLES_EMPTY_SECTION,
        TOOLS_ENABLED_SECTION,
        TOOLS_DISABLED_SECTION,
        SCENARIO_DESCRIPTIONS,
    )

    case_id = state["case_id"]
    ocr_results = state.get("evidence_ocr_results", [])
    classify_results = state.get("evidence_classify_results", [])
    extract_results = state.get("evidence_extract_results", [])
    preclassify_results = state.get("evidence_preclassify_results", [])
    errors = []
    start_time = datetime.now(timezone.utc)
    current_prompt_version = state.get("prompt_bundle_version", "")

    try:
        case = await sync_to_async(Case.objects.get)(pk=case_id)
    except Case.DoesNotExist:
        errors.append(f"案件 {case_id} 不存在")
        error_dicts = convert_string_errors_to_dicts(errors, stage="evidence_chain")
        node_result = build_node_result(
            node_name="evidence_chain",
            data={"chain_nodes": 0},
            quality=QualityReport(
                score=0.0,
                coverage=0.0,
                status="fail",
                blocking_issues=[],
                details={"reason": "case_not_found"},
            ),
            warnings=[],
            errors=error_dicts,
            provenance=[],
            start_time=start_time,
            model_calls=0,
        )
        return make_node_partial_update(
            node_name="evidence_chain",
            stage="case_organization",
            progress=0.70,
            state=state,
            node_result=node_result,
            legacy_fields={
                "evidence_chain": [],
                "evidence_chain_tool_calls": [],
                "errors": error_dicts,
            },
        )

    # 1. 基础时间线重建
    await emit_progress(stage="timeline_rebuild", message="正在重建基础时间线...")
    try:
        await sync_to_async(rebuild_timeline)(case)
    except Exception as e:
        logger.error(f"时间线基础重建失败: {e}", exc_info=True)
        errors.append(f"时间线基础重建失败: {e}")

    # 2. LLM 可用性检查
    if not llm_service.is_scenario_available("text"):
        chain = await _build_fallback_chain(case)
        errors.append("[证据链] LLM 不可用，仅返回基础时间线")
        error_dicts = convert_string_errors_to_dicts(errors, stage="evidence_chain")
        coverage, referenced_count, time_gaps = _compute_chain_quality(chain, ocr_results)
        provenance = _build_chain_provenance(chain, start_time)
        node_result = build_node_result(
            node_name="evidence_chain",
            data={
                "chain_nodes": len(chain),
                "degraded": True,
                "referenced_evidences": referenced_count,
                "time_gaps": time_gaps,
            },
            quality=QualityReport(
                score=coverage,
                coverage=coverage,
                status="warn",
                blocking_issues=[],
                details={
                    "degraded": True,
                    "reason": "llm_unavailable",
                    "referenced_evidences": referenced_count,
                    "time_gaps": time_gaps,
                },
            ),
            warnings=[],
            errors=error_dicts,
            provenance=provenance,
            start_time=start_time,
            model_calls=0,
        )
        return make_node_partial_update(
            node_name="evidence_chain",
            stage="case_organization",
            progress=0.70,
            state=state,
            node_result=node_result,
            legacy_fields={
                "evidence_chain": chain,
                "evidence_chain_tool_calls": [],
                "errors": error_dicts,
            },
        )

    # 构造 LLM 输入
    evidences_json = _build_evidences_json(
        ocr_results, classify_results, extract_results, preclassify_results
    )

    # 3. 主动预检索法条（强制首次，失败降级）
    # Task 5.1.3：先查 Store 缓存（legal_cache namespace），命中则跳过 BM25 + 向量检索 + Rerank
    await emit_progress(stage="rag_retrieval", message="正在检索相关法条（三阶段 RAG）...")
    case_keywords = _extract_case_keywords(case.description, extract_results)
    from api.agents.tools.law_tools import pre_retrieve_law_articles
    # 与 pre_retrieve_law_articles 内部一致的 query 构造方式，保证 cache key 一致
    legal_query = " ".join(case_keywords)
    cached_law_articles, _legal_invalidated = _get_cached_legal_result(
        runtime, case_id, legal_query, current_prompt_version
    )
    if cached_law_articles is not None and isinstance(cached_law_articles, list):
        logger.info(
            f"[证据链] Store 缓存命中 legal_cache (case={case_id}, "
            f"query_hash={_legal_cache_key(legal_query)})，跳过 RAG 检索"
        )
        law_articles = cached_law_articles
    else:
        law_articles = await pre_retrieve_law_articles(case_keywords)
        # 缓存未命中：写入 Store 供后续运行复用
        if law_articles:
            _put_cached_legal_result(
                runtime, case_id, legal_query, law_articles, current_prompt_version
            )
    law_articles_section = _format_law_articles_section(law_articles, errors)
    await emit_progress(
        stage="rag_done",
        message=f"法条检索完成，命中 {len(law_articles)} 条",
        detail={"candidate_count": len(law_articles)},
    )

    # 4. LLM 绑定工具 + 多轮工具调用
    from api.agents.tools.law_tools import (
        is_tools_enabled, get_all_law_tools, _get_max_iterations,
        invoke_llm_with_tools,
    )
    tools_enabled = is_tools_enabled()
    await emit_progress(
        stage="llm_reasoning",
        message="LLM 构造证据链中（含工具调用）..." if tools_enabled else "LLM 构造证据链中...",
    )
    tools_section = TOOLS_ENABLED_SECTION if tools_enabled else TOOLS_DISABLED_SECTION

    prompt = EVIDENCE_CHAIN_PROMPT.format(
        case_description=case.description or "",
        evidences_json=evidences_json,
        law_articles_section=law_articles_section,
        tools_section=tools_section,
        scenario_description=SCENARIO_DESCRIPTIONS.get(case.case_type, SCENARIO_DESCRIPTIONS["other"]),
    )

    tool_call_log = []
    if tools_enabled:
        # v10：绑定 7 个工具 + 多轮工具调用循环
        tools = get_all_law_tools()
        content, tool_call_log = await invoke_llm_with_tools(
            prompt=prompt,
            tools=tools,
            max_iterations=_get_max_iterations(),
            errors=errors,
            node_name="证据链",
        )
    else:
        # 工具禁用：单次 LLM 调用
        try:
            structured_llm = llm_service.get_scenario_llm("text").with_structured_output(
                __import__('api.agents.schemas', fromlist=['EvidenceChainResult']).EvidenceChainResult,
                method="function_calling"
            )
            result = await structured_llm.ainvoke(prompt)
            content = result.json()
        except Exception as e:
            logger.warning(f"[证据链] LLM 调用失败: {e}")
            errors.append(f"[证据链] LLM 调用失败: {e}")
            content = ""

    # 5. 解析 JSON 输出为证据链
    chain = _parse_evidence_chain(content)
    if not chain:
        # JSON 解析失败，回退到基础时间线
        logger.warning("[证据链] JSON 解析失败，回退到基础时间线")
        errors.append("[证据链] LLM 输出 JSON 解析失败，回退到基础时间线")
        chain = await _build_fallback_chain(case)

    # 工作流与 /cases/<id>/timeline/ 共用同一份增强时间线数据。
    try:
        from api.services.timeline_service import persist_evidence_chain
        await sync_to_async(persist_evidence_chain)(case, chain)
    except Exception as e:
        logger.error(f"增强时间线持久化失败: {e}", exc_info=True)
        errors.append(f"增强时间线持久化失败: {e}")

    logger.info(f"证据链构造完成（LLM + 工具），共 {len(chain)} 个节点，工具调用 {len(tool_call_log)} 次")

    error_dicts = convert_string_errors_to_dicts(errors, stage="evidence_chain")
    coverage, referenced_count, time_gaps = _compute_chain_quality(chain, ocr_results)
    quality_status = "pass" if time_gaps == 0 and coverage >= 0.7 else "warn"
    provenance = _build_chain_provenance(chain, start_time)
    node_result = build_node_result(
        node_name="evidence_chain",
        data={
            "chain_nodes": len(chain),
            "referenced_evidences": referenced_count,
            "time_gaps": time_gaps,
            "tool_calls": len(tool_call_log),
        },
        quality=QualityReport(
            score=coverage,
            coverage=coverage,
            status=quality_status,
            blocking_issues=[],
            details={
                "referenced_evidences": referenced_count,
                "time_gaps": time_gaps,
                "tool_calls": len(tool_call_log),
            },
        ),
        warnings=[],
        errors=error_dicts,
        provenance=provenance,
        start_time=start_time,
        model_calls=len(tool_call_log) + 1,  # 工具调用 + 1 次主 LLM 调用
    )
    return make_node_partial_update(
        node_name="evidence_chain",
        stage="case_organization",
        progress=0.70,
        state=state,
        node_result=node_result,
        legacy_fields={
            "evidence_chain": chain,
            "evidence_chain_tool_calls": tool_call_log,
            "errors": error_dicts,
        },
    )


def _format_law_articles_section(law_articles: list[dict], errors: list[str]) -> str:
    """格式化法条注入 prompt 片段。"""
    from api.agents.prompts.templates import (
        LAW_ARTICLES_SECTION_TEMPLATE,
        LAW_ARTICLES_EMPTY_SECTION,
    )

    if not law_articles:
        return LAW_ARTICLES_EMPTY_SECTION

    try:
        law_articles_json = json.dumps(
            [
                {
                    "law_name": a["law_name"],
                    "article_number": a["article_number"],
                    "summary": a["summary"],
                    "content": a["content"][:200],
                    "applicable_scenarios": a.get("applicable_scenarios", []),
                }
                for a in law_articles
            ],
            ensure_ascii=False, indent=2
        )
        return LAW_ARTICLES_SECTION_TEMPLATE.format(law_articles_json=law_articles_json)
    except Exception as e:
        logger.warning(f"[证据链] 法条片段格式化失败: {e}")
        errors.append(f"[证据链] 法条片段格式化失败: {e}")
        return LAW_ARTICLES_EMPTY_SECTION


def _compute_chain_quality(
    chain: list[dict],
    ocr_results: list[dict],
) -> tuple[float, int, int]:
    """计算证据链质量指标：引用覆盖率 + 引用证据数 + 时间断点数。

    Args:
        chain: 证据链节点列表
        ocr_results: OCR 结果（用于计算总证据数）

    Returns:
        (coverage, referenced_count, time_gaps)
        - coverage: 引用覆盖率 = 引用证据数 / 总证据数
        - referenced_count: 链中引用的不同证据数
        - time_gaps: 时间断点数量（datetime 为空或与前一节点间隔异常大）
    """
    # 引用证据集合
    referenced_codes: set[str] = set()
    for node in chain:
        for code in node.get("evidence_codes", []) or []:
            if isinstance(code, str) and code.strip():
                referenced_codes.add(code.strip())
    referenced_count = len(referenced_codes)
    total_evidences = len(ocr_results)
    coverage = referenced_count / max(total_evidences, 1)

    # 时间断点：datetime 为空，或与前一节点间隔 > 7 天
    time_gaps = 0
    prev_dt: datetime | None = None
    for node in chain:
        dt_str = node.get("datetime", "")
        if not dt_str:
            time_gaps += 1
            continue
        try:
            # 兼容 ISO 8601 / 简单格式
            current_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if prev_dt is not None:
                gap = abs((current_dt - prev_dt).total_seconds())
                if gap > 7 * 24 * 3600:  # > 7 天视为断点
                    time_gaps += 1
            prev_dt = current_dt
        except (ValueError, TypeError):
            time_gaps += 1

    return coverage, referenced_count, time_gaps


def _build_chain_provenance(chain: list[dict], start_time: datetime) -> list[dict]:
    """构造证据链 provenance 列表（每个链节点一项，记录证据来源）。"""
    ts = start_time.isoformat()
    provenance: list[dict] = []
    for node in chain:
        codes = node.get("evidence_codes", []) or []
        codes_str = ",".join(codes) if isinstance(codes, list) else str(codes)
        provenance.append({
            "node": "evidence_chain",
            "evidence_id": None,
            "field_name": None,
            "source_ref": f"chain:{node.get('chain_order', 0)}:{codes_str}",
            "ts": ts,
        })
    return provenance


def _parse_evidence_chain(content: str) -> list[dict]:
    """解析 LLM 输出的 JSON 为证据链列表。

    支持格式：
    - 纯 JSON：{"nodes": [...]}
    - Markdown 包裹：```json\n{...}\n```
    - 直接数组：[...]
    """
    if not content or not content.strip():
        return []

    content = content.strip()

    # 去除 Markdown 代码块包裹
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*\n?', '', content)
        content = re.sub(r'\n?```\s*$', '', content)
        content = content.strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # 尝试提取 JSON 部分
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    # 提取 nodes 列表
    nodes = data.get("nodes", []) if isinstance(data, dict) else data
    if not isinstance(nodes, list):
        return []

    chain = []
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            continue
        chain.append({
            "datetime": n.get("datetime", ""),
            "event": n.get("event", ""),
            "category": n.get("category", "其他"),
            "evidence_codes": n.get("evidence_codes", []),
            "chain_order": n.get("chain_order", i),
            "summary": n.get("summary", ""),
        })
    return chain


def _extract_case_keywords(case_description: str, extract_results: list[dict]) -> list[str]:
    """从案件描述和抽取字段提取用于 RAG 检索的关键词。"""
    keywords = []

    if case_description:
        keywords.append(case_description[:200])

    scenario_keywords_map = {
        "欺诈": ["欺诈", "虚假", "假货", "假冒", "以次充好"],
        "食品安全": ["食品", "过期", "变质", "异物"],
        "延迟发货": ["延迟", "未发货", "超时"],
        "质量问题": ["质量", "瑕疵", "故障", "破损"],
        "退款": ["退款", "退货", "退一赔三"],
    }

    field_names = set()
    for er in extract_results:
        for f in er.get("fields", []):
            field_names.add(f.get("field_name", ""))

    for scenario, kws in scenario_keywords_map.items():
        for kw in kws:
            if any(kw in fn for fn in field_names) or kw in (case_description or ""):
                keywords.append(scenario)
                break

    return keywords


def _build_evidences_json(
    ocr_results: list[dict],
    classify_results: list[dict],
    extract_results: list[dict],
    preclassify_results: list[dict],
) -> str:
    """构造 LLM 输入的证据列表 JSON（用 ocr_summary 替代截断全文）。"""
    category_map = {
        c["evidence_id"]: c.get("evidence_category", "other")
        for c in classify_results
    }
    summary_map = {
        r["evidence_id"]: r.get("ocr_summary", "")
        for r in preclassify_results
    }
    fields_map = {
        e["evidence_id"]: e.get("fields", [])
        for e in extract_results
    }

    evidences = []
    for o in ocr_results:
        eid = o["evidence_id"]
        ocr_summary = summary_map.get(eid, "")
        if not ocr_summary:
            ocr_summary = o.get("ocr_corrected_text") or o.get("ocr_raw_text", "")
        evidences.append({
            "evidence_code": o["evidence_code"],
            "ocr_summary": ocr_summary,
            "category": category_map.get(eid, "other"),
            "fields": fields_map.get(eid, []),
            "is_physical_evidence": o.get("is_physical_evidence", False),
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
            "summary": "",
        })
    return chain
