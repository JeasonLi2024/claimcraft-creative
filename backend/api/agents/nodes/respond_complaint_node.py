# -*- coding: utf-8 -*-
"""反证答辩书生成节点（async）：Jinja2 骨架 + LLM 重写（v10 反向维权）。

与 complaint_node.py 平行，主要差异：
- 输出"商家反证答辩书"而非"消费者投诉书"
- 持久化到 RespondTemplate 表（而非 ComplaintTemplate）
- 语气策略：反证模式默认 firm（坚定反驳不实指控）
- 复用 evidence_chain 节点输出 + 7 个法律工具 + 主动预检索法条
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

# 反证模式默认语气：坚定反驳不实指控
DEFAULT_RESPOND_TONE = "firm"
# 金额阈值（用于在 firm 之上进一步强调）
FIRM_TONE_AMOUNT_THRESHOLD = 1000


@traceable(name="反证答辩书生成节点", run_type="chain")
async def respond_complaint_node(state: CaseWorkflowState) -> dict[str, Any]:
    """反证答辩书生成节点（async）。

    流程：
    1. 调用 complaint_service.generate_complaint() 获取 Jinja2 骨架（复用同一生成器）
    2. 反证模式默认语气 firm
    3. 若 LLM 可用，重写正文为商家反证答辩书
    4. 写回 RespondTemplate 表（upsert）
    5. 输出 respond_draft
    """
    from api.models import Case, RespondTemplate
    from api.services.complaint_service import generate_complaint
    from api.agents.prompts.templates import (
        RESPOND_COMPLAINT_PROMPT,
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

    # 2. Jinja2 骨架（复用 generate_complaint，骨架本身不含立场）
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

    # 4. 语气选择：反证模式默认 firm（坚定反驳）
    tone = _select_respond_tone(all_fields)
    # 用户偏好覆盖默认语气（store 长期记忆）
    if user_pref_tone in ("firm", "restrained", "legal"):
        tone = user_pref_tone
        logger.info(f"应用用户偏好语气: {tone}")

    # 5. LLM 重写（若可用）
    final_content = skeleton.get("content", "")
    if llm_service.is_llm_available() and final_content.strip():
        try:
            facts_json = json.dumps(all_fields, ensure_ascii=False, indent=2)
            timeline_json = json.dumps(
                state.get("evidence_chain", []),
                ensure_ascii=False,
                indent=2,
            )

            # v10 工具集启用判断
            from api.agents.tools.law_tools import (
                is_tools_enabled, get_all_law_tools, _get_max_iterations,
                invoke_llm_with_tools, pre_retrieve_law_articles,
            )
            tools_enabled = is_tools_enabled()

            # 主动预检索法条（强制首次，失败降级）
            case_keywords = _extract_respond_keywords(case, all_fields)
            law_articles = await pre_retrieve_law_articles(case_keywords, top_k=5)
            law_articles_section = _format_respond_law_section(law_articles)

            if tools_enabled:
                tools_section = TOOLS_ENABLED_SECTION
            else:
                tools_section = TOOLS_DISABLED_SECTION

            prompt = RESPOND_COMPLAINT_PROMPT.format(
                tone=tone,
                skeleton=final_content,
                facts_json=facts_json,
                timeline_json=timeline_json,
                tools_section=tools_section,
                law_articles_section=law_articles_section,
                scenario_description=SCENARIO_DESCRIPTIONS.get(
                    case.case_type, SCENARIO_DESCRIPTIONS["other"]
                ),
            )

            if tools_enabled:
                # 绑定 7 个工具 + 多轮工具调用循环（与 complaint_node 一致）
                tools = get_all_law_tools()
                rewritten, tool_call_log = await invoke_llm_with_tools(
                    prompt=prompt,
                    tools=tools,
                    max_iterations=_get_max_iterations(),
                    errors=errors,
                    node_name="反证答辩生成",
                )
                logger.info(
                    f"[反证答辩生成] 工具调用完成，共 {len(tool_call_log)} 次"
                )
            else:
                # 原逻辑：单次 LLM 重写
                rewritten = await sync_to_async(llm_service.chat_with_retry)([
                    {"role": "user", "content": prompt}
                ])

            if isinstance(rewritten, str) and rewritten.strip():
                final_content = rewritten.strip()
        except Exception as e:
            logger.warning(f"LLM 反证答辩重写失败，使用骨架: {e}")
            errors.append(f"LLM 反证答辩重写失败: {e}")

    # 6. 持久化到 RespondTemplate 表（upsert）
    try:
        await sync_to_async(lambda c=case, tt=template_type, sk=skeleton, fc=final_content:
            RespondTemplate.objects.update_or_create(
                case=c,
                template_type=tt,
                defaults={
                    "title": sk.get("title", "反证答辩书"),
                    "content": fc,
                },
            )
        )()
    except Exception as e:
        logger.error(f"持久化 RespondTemplate 失败: {e}", exc_info=True)
        errors.append(f"持久化 RespondTemplate 失败: {e}")

    return {
        "complaint_draft": {
            "title": skeleton.get("title", "反证答辩书"),
            "content": final_content,
            "template_type": template_type,
            "tone": tone,
        },
        "errors": errors,
    }


def _select_respond_tone(extracted_fields: list[dict]) -> str:
    """反证模式语气选择：默认 firm（坚定反驳不实指控）。

    金额较大时可进一步强调，但仍保持 firm。
    用户偏好可在调用方覆盖。

    Args:
        extracted_fields: 抽取字段列表

    Returns:
        "firm"（默认）| "restrained"（金额极小，可降低强度）
    """
    for f in extracted_fields:
        if f.get("field_name") == "金额":
            try:
                amount = float(f.get("field_value", "0"))
                # 金额极小（≤ 阈值）时也可考虑 restrained，但反证模式默认坚定
                # 这里保持 firm 作为默认，避免被指控时显得软弱
                if amount <= FIRM_TONE_AMOUNT_THRESHOLD:
                    return "firm"
                return "firm"
            except (ValueError, TypeError):
                continue
    return DEFAULT_RESPOND_TONE


def _extract_respond_keywords(case, all_fields: list[dict]) -> list[str]:
    """从案件描述和抽取字段提取用于 RAG 检索的关键词（反证视角）。

    与 complaint 视角的关键词略不同，更强调商家抗辩视角
    （如：商品质量、合同履约、消费者违约等）。
    """
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
                    keywords.append("违约责任")
                    keywords.append("合同履行")
            except (ValueError, TypeError):
                pass
        elif field_name in ("商品名", "商品名称"):
            keywords.append(field_value)

    # 案件类型相关关键词（反证视角）
    case_type = case.case_type if case else ""
    type_keywords_map = {
        "shopping": ["商品质量", "退换货", "消费者违约"],
        "service": ["服务履约", "合同义务"],
        "secondhand": ["二手交易", "描述相符"],
    }
    keywords.extend(type_keywords_map.get(case_type, []))

    return keywords


def _format_respond_law_section(law_articles: list[dict]) -> str:
    """格式化法条注入反证答辩书 prompt 的片段。

    复用 COMPLAINT_LAW_ARTICLES_SECTION_TEMPLATE，因为格式相同。
    """
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
        logger.warning(f"[反证答辩生成] 法条片段格式化失败: {e}")
        return COMPLAINT_LAW_ARTICLES_EMPTY_SECTION
