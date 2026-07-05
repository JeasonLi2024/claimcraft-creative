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
    from api.agents.prompts.templates import COMPLAINT_REWRITE_PROMPT

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
    if llm_service.is_llm_available() and final_content.strip():
        try:
            facts_json = json.dumps(all_fields, ensure_ascii=False, indent=2)
            timeline_json = json.dumps(
                state.get("evidence_chain", []),
                ensure_ascii=False,
                indent=2,
            )
            prompt = COMPLAINT_REWRITE_PROMPT.format(
                tone=tone,
                skeleton=final_content,
                facts_json=facts_json,
                timeline_json=timeline_json,
            )
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
