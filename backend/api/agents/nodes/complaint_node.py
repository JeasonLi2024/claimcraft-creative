# -*- coding: utf-8 -*-
"""投诉生成节点（async）：Jinja2 骨架 + LLM 重写。

重构说明（v4 异步化）：
- def → async def，支持节点级 timeout
- Django ORM 调用用 sync_to_async 包装
- LLM 调用用 sync_to_async(chat_with_retry) 包装
- @traceable 装饰器

语气策略：
- 金额 > 1000 元 → firm（坚定）
- 金额 ≤ 1000 元 → restrained（克制）
"""
import json
import logging
from typing import Any

from asgiref.sync import sync_to_async

from api.agents.state import CaseWorkflowState
from api.agents.utils.progress import emit_progress
from api.services import llm_service

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def deco(fn):
            return fn
        return args[0] if args and callable(args[0]) else deco

logger = logging.getLogger(__name__)

# 金额阈值（决定语气）
FIRM_TONE_AMOUNT_THRESHOLD = 1000


@traceable(name="投诉生成节点", run_type="chain")
async def complaint_node(state: CaseWorkflowState) -> dict[str, Any]:
    """投诉生成节点（async）。

    流程：
    1. 调用既有 complaint_service.generate_complaint() 获取 Jinja2 骨架
    2. 根据金额选择语气
    3. 若 LLM 可用，重写正文
    4. 写回 ComplaintTemplate 表（upsert）
    5. 输出 complaint_draft
    """
    from api.models import Case, ComplaintTemplate
    from api.services.complaint_service import generate_complaint
    from api.agents.prompts.templates import (
        COMPLAINT_REWRITE_PROMPT,
        TOOLS_ENABLED_SECTION,
        TOOLS_DISABLED_SECTION,
        SCENARIO_DESCRIPTIONS,
    )

    case_id = state["case_id"]
    errors = []

    try:
        case = await sync_to_async(Case.objects.get)(pk=case_id)
    except Case.DoesNotExist:
        return {
            "complaint_draft": None,
            "errors": [f"案件 {case_id} 不存在"],
        }

    # 读用户偏好（store 长期记忆，跨案件复用）
    # 延迟 import 避免 graph.py ↔ complaint_node 循环导入
    user_pref_tone = None
    try:
        from api.agents.graph import _get_store
        store = _get_store()
        pref = store.get((str(case.owner_id), "preferences"), "complaint_style")
        if pref and pref.value:
            user_pref_tone = pref.value.get("tone")
    except Exception as e:
        logger.warning(f"读用户偏好失败（忽略，用默认语气）: {e}")

    # 1. 默认模板类型
    template_type = "platform"

    # 2. Jinja2 骨架
    try:
        skeleton = await sync_to_async(generate_complaint)(case, template_type)
    except Exception as e:
        logger.error(f"Jinja2 骨架生成失败: {e}", exc_info=True)
        errors.append(f"Jinja2 骨架生成失败: {e}")
        return {
            "complaint_draft": None,
            "errors": errors,
        }

    # 3. 聚合所有证据字段
    extract_results = state.get("evidence_extract_results", [])
    all_fields = []
    for er in extract_results:
        for f in er.get("fields", []):
            all_fields.append(f)

    # 4. 语气选择（基于金额）
    tone = _select_tone(all_fields)
    # 用户偏好覆盖默认语气（store 长期记忆）
    if user_pref_tone in ("firm", "restrained"):
        tone = user_pref_tone
        logger.info(f"应用用户偏好语气: {tone}")

    # 5. LLM 重写（若可用）
    final_content = skeleton.get("content", "")
    tool_call_log = []
    if llm_service.is_llm_available() and final_content.strip():
        try:
            await emit_progress(stage="skeleton_ready", message="投诉书骨架已生成，准备 LLM 重写...")

            facts_json = json.dumps(all_fields, ensure_ascii=False, indent=2)
            timeline_json = json.dumps(
                state.get("evidence_chain", []),
                ensure_ascii=False,
                indent=2,
            )

            # v10 新增：Tools 工具集启用判断
            from api.agents.tools.law_tools import (
                is_tools_enabled, get_all_law_tools, _get_max_iterations,
                invoke_llm_with_tools, pre_retrieve_law_articles,
            )
            tools_enabled = is_tools_enabled()

            # v10 新增：主动预检索法条（强制首次，失败降级）
            await emit_progress(stage="rag_retrieval", message="正在检索相关法条...")
            case_keywords = _extract_complaint_keywords(case, all_fields)
            law_articles = await pre_retrieve_law_articles(case_keywords, top_k=5)
            law_articles_section = _format_complaint_law_section(law_articles)
            await emit_progress(
                stage="rag_done",
                message=f"法条检索完成，命中 {len(law_articles)} 条",
                detail={"candidate_count": len(law_articles)},
            )

            if tools_enabled:
                tools_section = TOOLS_ENABLED_SECTION
            else:
                tools_section = TOOLS_DISABLED_SECTION

            prompt = COMPLAINT_REWRITE_PROMPT.format(
                tone=tone,
                skeleton=final_content,
                facts_json=facts_json,
                timeline_json=timeline_json,
                tools_section=tools_section,
                law_articles_section=law_articles_section,
                scenario_description=SCENARIO_DESCRIPTIONS.get(case.case_type, SCENARIO_DESCRIPTIONS["other"]),
            )

            if tools_enabled:
                await emit_progress(
                    stage="llm_generating",
                    message="LLM 重写投诉书中（含工具调用）...",
                )
                # v10：绑定 7 个工具 + 多轮工具调用循环（使用通用函数）
                tools = get_all_law_tools()
                rewritten, tool_call_log = await invoke_llm_with_tools(
                    prompt=prompt,
                    tools=tools,
                    max_iterations=_get_max_iterations(),
                    errors=errors,
                    node_name="投诉生成",
                )
                logger.info(
                    f"[投诉生成] 工具调用完成，共 {len(tool_call_log)} 次"
                )
            else:
                await emit_progress(stage="llm_generating", message="LLM 重写投诉书中...")
                # 原逻辑：单次 LLM 重写
                rewritten = await sync_to_async(llm_service.chat_with_retry)([
                    {"role": "user", "content": prompt}
                ])

            if isinstance(rewritten, str) and rewritten.strip():
                final_content = rewritten.strip()
        except Exception as e:
            logger.warning(f"LLM 投诉重写失败，使用骨架: {e}")
            errors.append(f"LLM 投诉重写失败: {e}")

    # 6. 持久化到 ComplaintTemplate 表（upsert）
    try:
        await sync_to_async(lambda c=case, tt=template_type, sk=skeleton, fc=final_content:
            ComplaintTemplate.objects.update_or_create(
                case=c,
                template_type=tt,
                defaults={
                    "title": sk.get("title", "投诉标题"),
                    "content": fc,
                },
            )
        )()
    except Exception as e:
        logger.error(f"持久化 ComplaintTemplate 失败: {e}", exc_info=True)
        errors.append(f"持久化 ComplaintTemplate 失败: {e}")

    return {
        "complaint_draft": {
            "title": skeleton.get("title", "投诉标题"),
            "content": final_content,
            "template_type": template_type,
            "tone": tone,
        },
        "complaint_tool_calls": tool_call_log,
        "errors": errors,
    }


def _select_tone(extracted_fields: list[dict]) -> str:
    """根据金额选择语气。

    Args:
        extracted_fields: 抽取字段列表

    Returns:
        "firm" | "restrained"
    """
    for f in extracted_fields:
        if f.get("field_name") == "金额":
            try:
                amount = float(f.get("field_value", "0"))
                if amount > FIRM_TONE_AMOUNT_THRESHOLD:
                    return "firm"
                return "restrained"
            except (ValueError, TypeError):
                continue
    return "restrained"


def _extract_complaint_keywords(case, all_fields: list[dict]) -> list[str]:
    """从案件描述和抽取字段提取用于 RAG 检索的关键词。"""
    keywords = []
    description = case.description if case else ""

    if description:
        keywords.append(description[:200])

    # 从字段值提取关键词
    for f in all_fields:
        field_name = f.get("field_name", "")
        field_value = f.get("field_value", "")
        if field_name == "金额":
            try:
                amount = float(field_value)
                if amount > 1000:
                    keywords.append("欺诈")
                    keywords.append("退一赔三")
            except (ValueError, TypeError):
                pass
        elif field_name in ("商品名", "商品名称"):
            keywords.append(field_value)

    # 案件类型相关关键词
    case_type = case.case_type if case else ""
    type_keywords_map = {
        "shopping": ["网购", "商品", "退换货"],
        "service": ["服务", "违约"],
        "secondhand": ["二手", "交易"],
    }
    keywords.extend(type_keywords_map.get(case_type, []))

    return keywords


def _format_complaint_law_section(law_articles: list[dict]) -> str:
    """格式化法条注入投诉重写 prompt 的片段。"""
    from api.agents.prompts.templates import (
        COMPLAINT_LAW_ARTICLES_SECTION_TEMPLATE,
        COMPLAINT_LAW_ARTICLES_EMPTY_SECTION,
    )

    if not law_articles:
        return COMPLAINT_LAW_ARTICLES_EMPTY_SECTION

    try:
        law_articles_json = json.dumps(
            [
                {
                    "law_name": a["law_name"],
                    "article_number": a["article_number"],
                    "summary": a["summary"],
                    "content": a["content"][:200],
                }
                for a in law_articles
            ],
            ensure_ascii=False, indent=2
        )
        return COMPLAINT_LAW_ARTICLES_SECTION_TEMPLATE.format(
            law_articles_json=law_articles_json
        )
    except Exception as e:
        logger.warning(f"[投诉生成] 法条片段格式化失败: {e}")
        return COMPLAINT_LAW_ARTICLES_EMPTY_SECTION
