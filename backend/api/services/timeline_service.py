# -*- coding: utf-8 -*-
"""时间线相关业务逻辑。"""
import re
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from api.models import TimelineNode

TIME_FIELD_KEYWORDS = ("时间", "日期", "下单", "支付", "付款", "发货", "签收", "申请", "退款", "履行")
DATE_PATTERNS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y年%m月%d日 %H:%M", "%Y年%m月%d日")

def get_sorted_timeline(case):
    return list(case.timeline_nodes.order_by("datetime", "order", "id"))

def _coerce_tz(dt):
    """将 datetime 归一化到与项目 USE_TZ 约定一致的形态。

    项目 USE_TZ=False + MySQL 后端只接受 naive datetime，且排序时 naive/aware 混用会抛
    ``TypeError: can't compare offset-naive and offset-aware datetimes``。此处统一：
    - USE_TZ=False → 返回 naive（aware 按当前时区换算为本地 naive）
    - USE_TZ=True  → 返回 aware（naive 按当前时区补齐）
    """
    if dt is None:
        return None
    if settings.USE_TZ:
        return (
            timezone.make_aware(dt, timezone.get_current_timezone())
            if timezone.is_naive(dt) else dt
        )
    return (
        timezone.make_naive(dt, timezone.get_current_timezone())
        if timezone.is_aware(dt) else dt
    )

def _parse_datetime(value):
    if not value:
        return None
    text = re.sub(r"\s+", " ", str(value).strip().replace("/", "-").replace(".", "-"))
    for fmt in DATE_PATTERNS:
        try:
            return _coerce_tz(datetime.strptime(text[:19], fmt))
        except ValueError:
            continue
    try:
        return _coerce_tz(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None

def _event_from_field(evidence, field):
    others = list(evidence.extracted_fields.exclude(pk=field.pk).order_by("-confidence"))
    details = [f"{item.field_name}: {item.field_value}" for item in others[:3]]
    base = evidence.description or evidence.ocr_summary or "证据材料记录"
    detail_text = "；".join(details)
    return f"[{evidence.code}] {base}" + (f"（{detail_text}）" if details else "")

@transaction.atomic
def rebuild_timeline(case):
    """优先使用图片/OCR 提取的关键时间，证据源时间作为补充。"""
    case.timeline_nodes.filter(auto_generated=True).delete()
    candidates = []
    for evidence in case.evidences.all().prefetch_related("extracted_fields"):
        for field in evidence.extracted_fields.all():
            name = field.field_name or ""
            if not (field.field_category == "时间信息" or any(key in name for key in TIME_FIELD_KEYWORDS)):
                continue
            dt = _parse_datetime(field.field_value)
            if dt:
                candidates.append((dt, evidence.code, _event_from_field(evidence, field)))
        if evidence.source_time:
            event = evidence.description or evidence.ocr_summary or "证据材料记录"
            # 统一时区形态，避免与 _parse_datetime 结果混排时抛 TypeError
            candidates.append((_coerce_tz(evidence.source_time), evidence.code, f"[{evidence.code}] {event}"))
    seen = set()
    for dt, code, event in sorted(candidates, key=lambda item: item[0]):
        key = (dt.isoformat(), code, event)
        if key in seen:
            continue
        seen.add(key)
        TimelineNode.objects.create(case=case, datetime=dt, event=event, related_evidence_codes=code, category="其他", order=len(seen)-1, auto_generated=True)
    return get_sorted_timeline(case)

@transaction.atomic
def persist_evidence_chain(case, chain):
    """将工作流增强证据链写回页面共用的 TimelineNode 数据源。"""
    case.timeline_nodes.filter(auto_generated=True).delete()
    for index, item in enumerate(sorted(chain, key=lambda node: node.get("chain_order", 0))):
        event = str(item.get("event") or "").strip()
        if not event:
            continue
        summary = str(item.get("summary") or "").strip()
        if summary and summary not in event:
            event = f"{event}\n{summary}"
        TimelineNode.objects.create(case=case, datetime=_parse_datetime(item.get("datetime")), event=event, category=item.get("category") or "其他", related_evidence_codes=",".join(item.get("evidence_codes") or []), order=index, auto_generated=True)
    return get_sorted_timeline(case)
