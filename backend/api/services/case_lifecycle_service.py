# -*- coding: utf-8 -*-
"""案件生命周期与工作流状态的统一事务服务。"""
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django_fsm import can_proceed

from api.models import Case, CaseStatusLog


class LifecycleError(Exception):
    """案件生命周期操作不满足业务约束。"""


@dataclass(frozen=True)
class TransitionResult:
    case: Case
    changed: bool


def _transition_locked(
    case: Case,
    target: str,
    *,
    trigger: str,
    actor=None,
    remark: str = '',
    thread_id: str = '',
    metadata: dict | None = None,
) -> TransitionResult:
    """转换已加锁的案件；目标已达成时按幂等成功处理。"""
    if case.status == target:
        return TransitionResult(case=case, changed=False)

    if target == 'processing':
        method = case.to_processing
    elif target == 'submitted':
        method = case.to_submitted
    elif target == 'closed':
        method = case.to_closed
    elif target == 'cancelled' and case.status == 'draft':
        method = case.cancel_from_draft
    elif target == 'cancelled' and case.status == 'processing':
        method = case.cancel_from_processing
    else:
        raise LifecycleError(f'当前状态 {case.status} 不允许转换至 {target}')

    if not can_proceed(method):
        raise LifecycleError(f'当前状态 {case.status} 不允许转换至 {target}')

    old_status = case.status
    method(by=actor)
    case.save(update_fields=['status', 'updated_at'])
    CaseStatusLog.objects.create(
        case=case,
        from_status=old_status,
        to_status=target,
        remark=remark,
        trigger=trigger,
        actor=actor,
        thread_id=thread_id,
        metadata=metadata or {},
    )
    return TransitionResult(case=case, changed=True)


@transaction.atomic
def start_processing(case_id: int, *, actor=None, thread_id: str = '') -> TransitionResult:
    """工作流被接受后进入处理态，并记录一次新的运行版本。"""
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status in ('closed', 'cancelled'):
        raise LifecycleError('已归档或已取消的案件不能启动工作流')

    result = (
        _transition_locked(
            case,
            'processing',
            trigger='workflow_started',
            actor=actor,
            remark='系统：案件分析工作流已启动',
            thread_id=thread_id,
        )
        if case.status == 'draft'
        else TransitionResult(case=case, changed=False)
    )
    case.workflow_status = 'running'
    case.workflow_started_at = timezone.now()
    case.workflow_finished_at = None
    case.workflow_error = ''
    case.workflow_revision += 1
    case.save(update_fields=[
        'workflow_status', 'workflow_started_at', 'workflow_finished_at',
        'workflow_error', 'workflow_revision', 'updated_at',
    ])
    return result


@transaction.atomic
def mark_waiting_review(case_id: int) -> Case:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status not in ('closed', 'cancelled'):
        case.workflow_status = 'waiting_review'
        case.save(update_fields=['workflow_status', 'updated_at'])
    return case


@transaction.atomic
def resume_processing(case_id: int) -> Case:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status in ('closed', 'cancelled'):
        raise LifecycleError('已归档或已取消的案件不能恢复工作流')
    case.workflow_status = 'running'
    case.workflow_error = ''
    case.save(update_fields=['workflow_status', 'workflow_error', 'updated_at'])
    return case


def _has_valid_document(case: Case) -> bool:
    manager = case.respond_templates if case.case_mode == 'respond' else case.complaint_templates
    return manager.exclude(title='').exclude(content='').exclude(content__icontains='暂无模板').exists()


@transaction.atomic
def complete_processing(case_id: int, *, thread_id: str = '') -> TransitionResult:
    """仅在存在有效文稿时完成工作流并自动进入可交付态。"""
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status in ('closed', 'cancelled'):
        return TransitionResult(case=case, changed=False)
    if not _has_valid_document(case):
        case.workflow_status = 'failed'
        case.workflow_finished_at = timezone.now()
        case.workflow_error = '工作流结束但未生成有效文稿'
        case.save(update_fields=[
            'workflow_status', 'workflow_finished_at', 'workflow_error', 'updated_at',
        ])
        return TransitionResult(case=case, changed=False)

    case.workflow_status = 'succeeded'
    case.workflow_finished_at = timezone.now()
    case.workflow_error = ''
    case.document_stale = False
    case.save(update_fields=[
        'workflow_status', 'workflow_finished_at', 'workflow_error',
        'document_stale', 'updated_at',
    ])
    if case.status == 'processing':
        return _transition_locked(
            case,
            'submitted',
            trigger='document_generated',
            remark='系统：工作流已生成有效文稿',
            thread_id=thread_id,
            metadata={'workflow_revision': case.workflow_revision},
        )
    return TransitionResult(case=case, changed=False)


@transaction.atomic
def fail_processing(case_id: int, error: str) -> Case:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status not in ('closed', 'cancelled'):
        case.workflow_status = 'failed'
        case.workflow_finished_at = timezone.now()
        case.workflow_error = (error or '工作流处理失败')[:2000]
        case.save(update_fields=[
            'workflow_status', 'workflow_finished_at', 'workflow_error', 'updated_at',
        ])
    return case


@transaction.atomic
def archive_case(case_id: int, *, actor) -> TransitionResult:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status == 'closed':
        return TransitionResult(case=case, changed=False)
    if case.workflow_status == 'running':
        raise LifecycleError('工作流正在运行，暂不能归档')
    if not _has_valid_document(case):
        raise LifecycleError('尚未生成有效文稿，不能归档')
    sensitive_unmasked = case.evidences.filter(
        has_sensitive_info=True,
        image__isnull=False,
    ).exclude(mask_status='done').exists()
    if sensitive_unmasked:
        raise LifecycleError('仍有包含敏感信息的图片未完成脱敏')

    result = _transition_locked(
        case,
        'closed',
        trigger='user_archived',
        actor=actor,
        remark='用户确认材料无误并完成归档',
    )
    case.archived_at = timezone.now()
    case.save(update_fields=['archived_at', 'updated_at'])
    return result


@transaction.atomic
def cancel_case(case_id: int, *, actor, reason: str = '') -> TransitionResult:
    case = Case.objects.select_for_update().get(pk=case_id)
    result = _transition_locked(
        case,
        'cancelled',
        trigger='user_cancelled',
        actor=actor,
        remark=reason or '用户取消案件',
    )
    case.workflow_status = 'idle'
    case.workflow_finished_at = timezone.now()
    case.save(update_fields=['workflow_status', 'workflow_finished_at', 'updated_at'])
    return result


def mark_document_stale(case_id: int) -> None:
    """已形成文稿后材料发生变更时，标记文稿需要重新生成。"""
    Case.objects.filter(pk=case_id, status='submitted').update(document_stale=True)


def get_case_progress(case: Case) -> dict:
    """根据真实业务数据计算工作台进度和下一步动作。"""
    evidence_done = case.evidences.exists()
    timeline_done = case.timeline_nodes.exists()
    document_done = _has_valid_document(case)
    sensitive = case.evidences.filter(has_sensitive_info=True, image__isnull=False)
    masking_required = sensitive.exists()
    masking_done = not masking_required or not sensitive.exclude(mask_status='done').exists()

    steps = [evidence_done, timeline_done, document_done, masking_done and document_done]
    if not evidence_done:
        next_action = 'upload_evidence'
    elif case.workflow_status == 'waiting_review':
        next_action = 'review_extracted_fields'
    elif case.workflow_status == 'running':
        next_action = 'wait_for_workflow'
    elif not timeline_done or not document_done or case.document_stale:
        next_action = 'start_workflow'
    elif not masking_done:
        next_action = 'mask_sensitive_images'
    elif case.status == 'submitted':
        next_action = 'archive_case'
    else:
        next_action = 'view_materials'

    return {
        'evidence': 'completed' if evidence_done else 'pending',
        'timeline': 'completed' if timeline_done else 'pending',
        'document': 'stale' if case.document_stale else ('completed' if document_done else 'pending'),
        'masking': 'not_required' if not masking_required else ('completed' if masking_done else 'pending'),
        'percent': round(sum(steps) / len(steps) * 100),
        'next_action': next_action,
        'can_archive': document_done and masking_done and case.workflow_status != 'running' and case.status == 'submitted',
    }
