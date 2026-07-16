# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from api.models import Case, ComplaintTemplate, Evidence, ExtractedField, RespondTemplate, TimelineNode

try:
    from langgraph.types import Overwrite
except ImportError:
    @dataclass(frozen=True)
    class Overwrite:
        value: object


class StagePauseValidationError(Exception):
    pass


LOW_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_TEMPLATE_TYPE = 'platform'
CATEGORY_LABELS = {
    'chat_screenshot': '聊天截图',
    'product_order': '商品订单',
    'logistics_tracking': '物流跟踪',
    'payment_record': '支付凭证',
    'invoice': '发票',
    'service_contract': '服务合同',
    'work_record': '施工记录',
    'communication_record': '沟通记录',
    'contract_document': '合同文件',
    'medical_record': '医疗记录',
    'other': '其他',
}
STAGE_EDITABLE_SCOPES = {
    'preclassify': {'evidences': ['evidence_category', 'ocr_summary']},
    'ocr': {'evidences': ['extracted_text']},
    'classify': {'evidences': ['evidence_category']},
    'extract': {'extracted_fields': ['field_name', 'field_value']},
    'review': {'extracted_fields': ['field_name', 'field_value']},
    'evidence_chain': {'timeline_nodes': ['event']},
    'complaint': {'document': ['title', 'content', 'tone']},
    'respond_complaint': {'document': ['title', 'content', 'tone']},
}
LIMITS = {
    'evidence_category': 50,
    'ocr_summary': 2000,
    'extracted_text': 20000,
    'field_name': 50,
    'field_value': 500,
    'event': 4000,
    'title': 200,
    'content': 20000,
    'tone': 20,
}


def is_stage_pause_interrupt_value(value):
    return isinstance(value, dict) and value.get('interrupt_type') == 'stage_pause'


def get_stage_editable_scope(paused_after):
    scope = STAGE_EDITABLE_SCOPES.get(paused_after, {})
    return {name: list(fields) for name, fields in scope.items()}


def build_stage_pause_payload(paused_after):
    return {
        'interrupt_type': 'stage_pause',
        'paused_after': paused_after,
        'editable_scope': get_stage_editable_scope(paused_after),
        'message': f'已在 {paused_after} 节点完成后安全暂停，可修改阶段产物后继续。',
    }


def snapshot_interrupts(snapshot):
    items = []
    direct = getattr(snapshot, 'interrupts', None)
    if isinstance(direct, (list, tuple)):
        items.extend(direct)
    elif direct is not None:
        items.append(direct)
    for task in getattr(snapshot, 'tasks', None) or []:
        current = getattr(task, 'interrupts', None)
        if isinstance(current, (list, tuple)):
            items.extend(current)
        elif current is not None:
            items.append(current)
    return items


def interrupt_value(interrupt):
    if isinstance(interrupt, dict):
        return interrupt.get('value', interrupt)
    return getattr(interrupt, 'value', interrupt)


def get_case_snapshot_values(case):
    if not case.thread_id:
        return {}
    from api.agents import build_case_workflow
    snapshot = build_case_workflow().get_state({'configurable': {'thread_id': case.thread_id}})
    values = getattr(snapshot, 'values', None)
    return values if isinstance(values, dict) else {}


def _validate_str(value, field_name, limit_key, allow_blank):
    if not isinstance(value, str):
        raise StagePauseValidationError(f'{field_name} 必须是字符串')
    normalized = value.strip()
    if not normalized and not allow_blank:
        raise StagePauseValidationError(f'{field_name} 不能为空')
    if len(normalized) > LIMITS[limit_key]:
        raise StagePauseValidationError(f'{field_name} 长度不能超过 {LIMITS[limit_key]}')
    return normalized


def _ensure_list(value, field_name):
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise StagePauseValidationError(f'{field_name} 必须是数组')
    return value


def _require_int(value, field_name):
    if not isinstance(value, int):
        raise StagePauseValidationError(f'{field_name} 必须是整数')
    return value


def _collect_evidence_ids(snapshot_values, *row_sets):
    ids = {value for value in snapshot_values.get('evidence_ids', []) if isinstance(value, int)}
    for rows in row_sets:
        for row in rows:
            evidence_id = row.get('evidence_id') if isinstance(row, dict) else None
            if isinstance(evidence_id, int):
                ids.add(evidence_id)
    return ids


def _allowed_evidence_ids(snapshot_values):
    return _collect_evidence_ids(
        snapshot_values,
        snapshot_values.get('evidence_preclassify_results') or [],
        snapshot_values.get('evidence_ocr_results') or [],
        snapshot_values.get('evidence_classify_results') or [],
        snapshot_values.get('evidence_extract_results') or [],
    )


def build_stage_resume_payload(case, edits):
    paused_after = (case.workflow_paused_after or '').strip()
    if paused_after not in STAGE_EDITABLE_SCOPES:
        raise StagePauseValidationError('案件当前没有可恢复的阶段暂停点')
    state_updates = _apply_stage_edits(case, paused_after, edits or {}, get_case_snapshot_values(case))
    return {
        'interrupt_type': 'stage_pause',
        'action': 'continue',
        'paused_after': paused_after,
        'state_updates': state_updates,
    }


def _apply_evidence_edits(case, items, allowed_fields, snapshot_values):
    rows = _ensure_list(items, 'evidences')
    allowed_ids = _allowed_evidence_ids(snapshot_values)
    edited_ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise StagePauseValidationError('evidences 必须是对象数组')
        evidence_id = _require_int(row.get('id'), 'evidences.id')
        if allowed_ids and evidence_id not in allowed_ids:
            raise StagePauseValidationError(f'证据 {evidence_id} 不在当前工作流范围内')
        evidence = Evidence.objects.select_for_update().filter(pk=evidence_id, case=case).first()
        if evidence is None:
            raise StagePauseValidationError(f'证据 {evidence_id} 不存在')
        update_fields = []
        for key, value in row.items():
            if key == 'id':
                continue
            if key not in allowed_fields:
                raise StagePauseValidationError(f'当前阶段不允许修改 evidences.{key}')
            if key == 'evidence_category':
                evidence.evidence_category = _validate_str(value, 'evidences.evidence_category', 'evidence_category', True)
                update_fields.append('evidence_category')
            elif key == 'ocr_summary':
                evidence.ocr_summary = _validate_str(value, 'evidences.ocr_summary', 'ocr_summary', True)
                update_fields.append('ocr_summary')
            elif key == 'extracted_text':
                evidence.extracted_text = _validate_str(value, 'evidences.extracted_text', 'extracted_text', True)
                update_fields.append('extracted_text')
        if update_fields:
            evidence.save(update_fields=sorted(set(update_fields + ['updated_at'])))
            edited_ids.add(evidence_id)
    return edited_ids


def _apply_extracted_field_edits(case, items, enabled):
    rows = _ensure_list(items, 'extracted_fields')
    if rows and not enabled:
        raise StagePauseValidationError('当前阶段不允许编辑 extracted_fields')
    edited_ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise StagePauseValidationError('extracted_fields 必须是对象数组')
        field = ExtractedField.objects.select_for_update().filter(pk=_require_int(row.get('id'), 'extracted_fields.id'), evidence__case=case).first()
        if field is None:
            raise StagePauseValidationError(f'抽取字段 {row.get("id")} 不存在')
        unknown_keys = set(row) - {'id', 'field_name', 'field_value'}
        if unknown_keys:
            raise StagePauseValidationError(f'当前阶段不允许修改 extracted_fields.{sorted(unknown_keys)[0]}')
        update_fields = []
        if 'field_name' in row:
            field.field_name = _validate_str(row.get('field_name'), 'extracted_fields.field_name', 'field_name', False)
            update_fields.append('field_name')
        if 'field_value' in row:
            field.field_value = _validate_str(row.get('field_value'), 'extracted_fields.field_value', 'field_value', True)
            update_fields.append('field_value')
        if update_fields:
            field.confidence = 1.0
            update_fields.append('confidence')
            field.save(update_fields=sorted(set(update_fields)))
            edited_ids.add(field.id)
    return edited_ids


def _apply_timeline_edits(case, items, enabled):
    rows = _ensure_list(items, 'timeline_nodes')
    if rows and not enabled:
        raise StagePauseValidationError('当前阶段不允许编辑 timeline_nodes')
    for row in rows:
        if not isinstance(row, dict):
            raise StagePauseValidationError('timeline_nodes 必须是对象数组')
        node = TimelineNode.objects.select_for_update().filter(pk=_require_int(row.get('id'), 'timeline_nodes.id'), case=case).first()
        if node is None:
            raise StagePauseValidationError(f'时间线节点 {row.get("id")} 不存在')
        unknown_keys = set(row) - {'id', 'event'}
        if unknown_keys:
            raise StagePauseValidationError(f'当前阶段不允许修改 timeline_nodes.{sorted(unknown_keys)[0]}')
        if 'event' in row:
            node.event = _validate_str(row.get('event'), 'timeline_nodes.event', 'event', False)
            node.save(update_fields=['event'])


def _apply_document_edits(case, paused_after, document, snapshot_values, enabled):
    if document in ({}, None):
        return
    if not enabled:
        raise StagePauseValidationError('当前阶段不允许编辑 document')
    if not isinstance(document, dict):
        raise StagePauseValidationError('document 必须是对象')
    unknown_keys = set(document) - {'title', 'content', 'tone'}
    if unknown_keys:
        raise StagePauseValidationError(f'当前阶段不允许修改 document.{sorted(unknown_keys)[0]}')
    draft = snapshot_values.get('complaint_draft') or {}
    template_type = draft.get('template_type') or DEFAULT_TEMPLATE_TYPE
    if paused_after == 'complaint':
        template = ComplaintTemplate.objects.select_for_update().filter(case=case, template_type=template_type).order_by('id').first()
        if template is None:
            template = ComplaintTemplate(case=case, template_type=template_type, title=draft.get('title') or '投诉标题', content=draft.get('content') or '', tone=draft.get('tone') or '')
            template.save()
    else:
        template = RespondTemplate.objects.select_for_update().filter(case=case, template_type=template_type).order_by('id').first()
        if template is None:
            template = RespondTemplate(case=case, template_type=template_type, title=draft.get('title') or '反证答辩书', content=draft.get('content') or '', tone=draft.get('tone') or '')
            template.save()
    update_fields = []
    if 'title' in document:
        template.title = _validate_str(document.get('title'), 'document.title', 'title', False)
        update_fields.append('title')
    if 'content' in document:
        template.content = _validate_str(document.get('content'), 'document.content', 'content', False)
        update_fields.append('content')
    if 'tone' in document and hasattr(template, 'tone'):
        template.tone = _validate_str(document.get('tone'), 'document.tone', 'tone', True)
        update_fields.append('tone')
    if update_fields:
        template.save(update_fields=sorted(set(update_fields)))


def _build_preclassify_updates(case, snapshot_values, edited_ids):
    rows = list(snapshot_values.get('evidence_preclassify_results') or [])
    evidence_map = {ev.id: ev for ev in Evidence.objects.filter(case=case, pk__in=_collect_evidence_ids(snapshot_values, rows))}
    result = []
    for row in rows:
        evidence = evidence_map.get(row.get('evidence_id'))
        if evidence is None:
            continue
        current = dict(row)
        current['evidence_category'] = evidence.evidence_category
        current['ocr_summary'] = evidence.ocr_summary
        if evidence.id in edited_ids:
            current['confidence'] = 1.0
        result.append(current)
    return {'evidence_preclassify_results': Overwrite(result)}


def _build_ocr_updates(case, snapshot_values, edited_ids):
    rows = list(snapshot_values.get('evidence_ocr_results') or [])
    evidence_map = {ev.id: ev for ev in Evidence.objects.filter(case=case, pk__in=_collect_evidence_ids(snapshot_values, rows))}
    result = []
    for row in rows:
        evidence = evidence_map.get(row.get('evidence_id'))
        if evidence is None:
            continue
        current = dict(row)
        if evidence.id in edited_ids:
            current['ocr_corrected_text'] = evidence.extracted_text
            if not current.get('ocr_raw_text'):
                current['ocr_raw_text'] = evidence.extracted_text
        result.append(current)
    return {'evidence_ocr_results': Overwrite(result)}


def _build_classify_updates(case, snapshot_values, edited_ids):
    rows = list(snapshot_values.get('evidence_classify_results') or [])
    evidence_map = {ev.id: ev for ev in Evidence.objects.filter(case=case, pk__in=_collect_evidence_ids(snapshot_values, rows))}
    result = []
    for row in rows:
        evidence = evidence_map.get(row.get('evidence_id'))
        if evidence is None:
            continue
        current = dict(row)
        current['evidence_category'] = evidence.evidence_category or 'other'
        current['category_label'] = CATEGORY_LABELS.get(current['evidence_category'], '其他')
        if evidence.id in edited_ids:
            current['confidence'] = 1.0
        result.append(current)
    return {'evidence_classify_results': Overwrite(result)}


def _build_extract_updates(case, snapshot_values, edited_field_ids):
    rows = list(snapshot_values.get('evidence_extract_results') or [])
    evidence_ids = [row.get('evidence_id') for row in rows if row.get('evidence_id')]
    fields = list(ExtractedField.objects.filter(evidence__case=case, evidence_id__in=evidence_ids).select_related('evidence').order_by('id'))
    by_evidence = {}
    needs_human_review = False
    for field in fields:
        payload = {
            'id': field.id,
            'field_name': field.field_name,
            'field_value': field.field_value,
            'confidence': field.confidence,
            'field_category': field.field_category or '其他',
            'source': 'review' if field.id in edited_field_ids or field.confidence >= 1.0 else 'original',
        }
        by_evidence.setdefault(field.evidence_id, []).append(payload)
        if field.confidence < LOW_CONFIDENCE_THRESHOLD:
            needs_human_review = True
    result = []
    for row in rows:
        current = dict(row)
        current['fields'] = by_evidence.get(row.get('evidence_id'), [])
        current['needs_human_review'] = any(item.get('confidence', 1.0) < LOW_CONFIDENCE_THRESHOLD for item in current['fields'])
        result.append(current)
    return {
        'evidence_extract_results': Overwrite(result),
        'needs_human_review': needs_human_review,
    }


def _build_evidence_chain_updates(case):
    nodes = list(TimelineNode.objects.filter(case=case).order_by('order', 'datetime', 'id'))
    return {
        'evidence_chain': [
            {
                'datetime': node.datetime.isoformat() if node.datetime else '',
                'event': node.event,
                'category': node.category or '其他',
                'evidence_codes': [code.strip() for code in (node.related_evidence_codes or '').split(',') if code.strip()],
                'chain_order': node.order,
                'summary': '',
            }
            for node in nodes
        ]
    }


def _build_document_updates(case, paused_after, snapshot_values, document_edit):
    draft = snapshot_values.get('complaint_draft') or {}
    template_type = draft.get('template_type') or DEFAULT_TEMPLATE_TYPE
    if paused_after == 'complaint':
        template = ComplaintTemplate.objects.filter(case=case, template_type=template_type).order_by('id').first()
        if template is None:
            raise StagePauseValidationError('投诉书记录不存在，无法继续')
        return {'complaint_draft': {'title': template.title, 'content': template.content, 'template_type': template.template_type, 'tone': template.tone, 'legal_references': draft.get('legal_references', [])}}
    template = RespondTemplate.objects.filter(case=case, template_type=template_type).order_by('id').first()
    if template is None:
        raise StagePauseValidationError('答辩书记录不存在，无法继续')
    tone = draft.get('tone', '')
    if isinstance(document_edit, dict) and 'tone' in document_edit:
        tone = _validate_str(document_edit.get('tone'), 'document.tone', 'tone', True)
    return {'complaint_draft': {'title': template.title, 'content': template.content, 'template_type': template.template_type, 'tone': tone}}


@transaction.atomic
def _apply_stage_edits(case, paused_after, edits, snapshot_values):
    if not isinstance(edits, dict):
        raise StagePauseValidationError('edits 必须是对象')
    scope = STAGE_EDITABLE_SCOPES[paused_after]
    for key, payload in edits.items():
        if key not in scope and payload not in ({}, [], None):
            raise StagePauseValidationError(f'{paused_after} 阶段不允许编辑 {key}')
    evidence_ids = _apply_evidence_edits(case, edits.get('evidences', []), set(scope.get('evidences', [])), snapshot_values)
    field_ids = _apply_extracted_field_edits(case, edits.get('extracted_fields', []), bool(scope.get('extracted_fields')))
    _apply_timeline_edits(case, edits.get('timeline_nodes', []), bool(scope.get('timeline_nodes')))
    _apply_document_edits(case, paused_after, edits.get('document', {}), snapshot_values, bool(scope.get('document')))
    if paused_after == 'preclassify':
        return _build_preclassify_updates(case, snapshot_values, evidence_ids)
    if paused_after == 'ocr':
        return _build_ocr_updates(case, snapshot_values, evidence_ids)
    if paused_after == 'classify':
        return _build_classify_updates(case, snapshot_values, evidence_ids)
    if paused_after in {'extract', 'review'}:
        return _build_extract_updates(case, snapshot_values, field_ids)
    if paused_after == 'evidence_chain':
        return _build_evidence_chain_updates(case)
    return _build_document_updates(case, paused_after, snapshot_values, edits.get('document', {}))
