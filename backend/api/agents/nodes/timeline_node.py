# -*- coding: utf-8 -*-
"""时间线重建节点：基础排序 + LLM 事件分类 + 同类归并。

依赖 TimelineNode.category 字段（B6 新增，需先运行迁移）。
"""
import json
import logging
from datetime import timedelta
from typing import Any

from api.agents.state import CaseWorkflowState
from api.services import llm_service

logger = logging.getLogger(__name__)

# 同类事件归并的时间窗口（分钟）
MERGE_WINDOW_MINUTES = 5

# 事件类别
EVENT_CATEGORIES = ["下单", "付款", "发货", "沟通", "退款", "承诺", "违约", "其他"]


def timeline_node(state: CaseWorkflowState) -> dict[str, Any]:
    """时间线重建节点。

    流程：
    1. 调用既有 timeline_service.rebuild_timeline(case) 获取基础节点
    2. 若 LLM 可用，对每个节点分类（写入 category 字段）
    3. 同类 ±5 分钟内的事件归并
    4. 输出 timeline_events 列表
    """
    from api.models import Case, TimelineNode
    from api.services.timeline_service import rebuild_timeline
    from api.agents.prompts.templates import TIMELINE_CLASSIFY_PROMPT

    case_id = state["case_id"]
    errors = []

    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return {
            "timeline_events": [],
            "errors": [f"案件 {case_id} 不存在"],
        }

    # 1. 基础重建
    try:
        rebuild_timeline(case)
    except Exception as e:
        logger.error(f"时间线基础重建失败: {e}", exc_info=True)
        errors.append(f"时间线基础重建失败: {e}")

    # 2. LLM 分类（若可用）
    nodes = list(case.timeline_nodes.all().order_by("datetime"))
    if llm_service.is_llm_available():
        for node in nodes:
            if node.category:  # 已分类跳过
                continue
            try:
                prompt = TIMELINE_CLASSIFY_PROMPT.format(event=node.event)
                category = llm_service.chat_with_retry([
                    {"role": "user", "content": prompt}
                ])
                if isinstance(category, str):
                    category = category.strip()
                    # 校验类别合法
                    if category not in EVENT_CATEGORIES:
                        # 模糊匹配
                        for valid_cat in EVENT_CATEGORIES:
                            if valid_cat in category:
                                category = valid_cat
                                break
                        else:
                            category = "其他"
                    node.category = category
                    node.save(update_fields=["category"])
            except Exception as e:
                logger.warning(f"事件分类失败 (node_id={node.id}): {e}")
                errors.append(f"事件分类失败: {e}")

    # 3. 同类归并（±5 分钟）
    events = []
    for node in nodes:
        events.append({
            "datetime": node.datetime.isoformat() if node.datetime else None,
            "event": node.event,
            "category": node.category or "其他",
            "evidence_codes": node.related_evidence_codes,
            "node_id": node.id,
        })

    # 归并逻辑：同类别 ±5 分钟内的事件合并
    merged_events = _merge_nearby_events(events)

    return {
        "timeline_events": merged_events,
        "errors": errors,
    }


def _merge_nearby_events(events: list[dict]) -> list[dict]:
    """归并同类 ±5 分钟内的事件。

    合并策略：
    - 同类别 + 时间差 ≤ 5 分钟 → 合并为一条
    - 合并后 evidence_codes 用逗号拼接
    - event 文本取第一条，附加 "（合并 N 条）"
    """
    from datetime import datetime as dt_class

    if not events:
        return []

    # 按时间排序
    def parse_dt(ev):
        if not ev.get("datetime"):
            return dt_class.min
        try:
            return dt_class.fromisoformat(ev["datetime"])
        except (ValueError, TypeError):
            return dt_class.min

    sorted_events = sorted(events, key=parse_dt)

    merged = []
    current_group = [sorted_events[0]]

    for ev in sorted_events[1:]:
        prev = current_group[-1]
        prev_dt = parse_dt(prev)
        curr_dt = parse_dt(ev)
        # 同类 + 时间差 ≤ 5 分钟
        if (
            ev["category"] == prev["category"]
            and abs((curr_dt - prev_dt).total_seconds()) <= MERGE_WINDOW_MINUTES * 60
        ):
            current_group.append(ev)
        else:
            merged.append(_merge_group(current_group))
            current_group = [ev]
    merged.append(_merge_group(current_group))

    return merged


def _merge_group(group: list[dict]) -> dict:
    """合并一组事件为单条。"""
    if len(group) == 1:
        return group[0]

    # 合并 evidence_codes（去重）
    all_codes = []
    for ev in group:
        codes = (ev.get("evidence_codes") or "").split(",")
        for c in codes:
            c = c.strip()
            if c and c not in all_codes:
                all_codes.append(c)

    return {
        "datetime": group[0]["datetime"],
        "event": f"{group[0]['event']}（合并 {len(group)} 条同类事件）",
        "category": group[0]["category"],
        "evidence_codes": ",".join(all_codes),
        "node_ids": [g.get("node_id") for g in group if g.get("node_id")],
    }
