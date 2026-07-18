# -*- coding: utf-8 -*-
"""案件生命周期与工作流状态的统一事务服务。

Task 3.4.2 兼容策略（Case.workflow_status 枚举统一）：
========================================

背景：spec.md MODIFIED Requirements: Case Workflow Status 要求将
`Case.workflow_status` 枚举从旧值
`idle / running / pausing / paused / waiting_review / succeeded / failed`
统一为新值
`idle / queued / running / pausing / waiting_user / succeeded / failed / cancelled`
（`paused` + `waiting_review` 合并为 `waiting_user`，新增 `queued` / `cancelled`）。

实施策略（避免破坏旧 API + 避免数据库迁移）：
1. **不修改 `Case.WORKFLOW_STATUS_CHOICES` 与 `Case.workflow_status` 字段**：
   `Case.workflow_status` 继续存储旧值（idle / running / pausing / paused /
   waiting_review / succeeded / failed），不触发 Django 迁移，不影响旧数据。
2. **`WorkflowRun.status` 已使用新枚举**（Task 3.1 已落地）。
3. **旧 API 端点（`/cases/<id>/workflow/*`）直接返回 `Case.workflow_status` 旧值**，
   不做转换，保持 100% 向后兼容。
4. **新 API 端点（Task 3.2 的 `/workflow-runs/*`）在序列化 `Case.workflow_status`
   时调用 `map_legacy_status_to_new()` 转换为新值返回**；新 API 内部使用
   `WorkflowRun.status`（新枚举），仅在需要回填 Case 旧字段时调用
   `map_workflow_status_to_legacy()` 转回旧值。
5. **`waiting_user` 反向映射需 `intervention_type` 区分**：
   - `user_pause` → 旧 `paused`
   - `quality_review` → 旧 `waiting_review`
   - `None` / 其他 → 默认 `paused`

参见 `map_workflow_status_to_legacy()` / `map_legacy_status_to_new()`。
"""
from dataclasses import dataclass
from typing import Optional

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


ACTIVE_WORKFLOW_STATUSES = {'running', 'pausing'}
RESUMABLE_WORKFLOW_STATUSES = {'waiting_review', 'paused'}
NON_ARCHIVABLE_WORKFLOW_STATUSES = ACTIVE_WORKFLOW_STATUSES | RESUMABLE_WORKFLOW_STATUSES


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
    case.workflow_pause_requested = False
    case.workflow_paused_after = ''
    case.workflow_started_at = timezone.now()
    case.workflow_finished_at = None
    case.workflow_error = ''
    case.workflow_revision += 1
    case.save(update_fields=[
        'workflow_status', 'workflow_pause_requested', 'workflow_paused_after',
        'workflow_started_at', 'workflow_finished_at',
        'workflow_error', 'workflow_revision', 'updated_at',
    ])
    return result


@transaction.atomic
def request_pause(case_id: int) -> Case:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status in ('closed', 'cancelled'):
        raise LifecycleError('已归档或已取消的案件不能暂停工作流')
    if case.workflow_status != 'running':
        raise LifecycleError('仅运行中的工作流允许请求暂停')
    case.workflow_pause_requested = True
    case.workflow_status = 'pausing'
    case.save(update_fields=['workflow_pause_requested', 'workflow_status', 'updated_at'])
    return case


@transaction.atomic
def mark_paused(case_id: int, paused_after: str) -> bool:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status in ('closed', 'cancelled'):
        return False
    if case.workflow_paused_after == paused_after:
        return True
    if not case.workflow_pause_requested:
        return False
    case.workflow_pause_requested = False
    case.workflow_status = 'paused'
    case.workflow_paused_after = paused_after
    case.save(update_fields=[
        'workflow_pause_requested', 'workflow_status',
        'workflow_paused_after', 'updated_at',
    ])
    return True


@transaction.atomic
def clear_pause_boundary(case_id: int, paused_after: str) -> Case:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.workflow_paused_after == paused_after:
        case.workflow_paused_after = ''
        case.save(update_fields=['workflow_paused_after', 'updated_at'])
    return case


@transaction.atomic
def cancel_workflow(case_id: int) -> Case:
    """取消已暂停的工作流执行，但不取消案件本身。"""
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status in ('closed', 'cancelled'):
        raise LifecycleError('已归档或已取消的案件不能取消工作流')
    if case.workflow_status not in {'paused', 'idle'}:
        raise LifecycleError('仅已暂停或未启动的工作流允许取消')
    case.workflow_status = 'idle'
    case.workflow_pause_requested = False
    case.workflow_paused_after = ''
    case.workflow_finished_at = timezone.now()
    case.workflow_error = ''
    case.save(update_fields=[
        'workflow_status', 'workflow_pause_requested', 'workflow_paused_after',
        'workflow_finished_at', 'workflow_error', 'updated_at',
    ])
    return case


@transaction.atomic
def mark_waiting_review(case_id: int) -> Case:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status not in ('closed', 'cancelled'):
        case.workflow_status = 'waiting_review'
        case.workflow_pause_requested = False
        case.workflow_paused_after = ''
        case.save(update_fields=[
            'workflow_status', 'workflow_pause_requested',
            'workflow_paused_after', 'updated_at',
        ])
    return case


@transaction.atomic
def resume_processing(case_id: int) -> Case:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status in ('closed', 'cancelled'):
        raise LifecycleError('已归档或已取消的案件不能恢复工作流')
    if case.workflow_status not in RESUMABLE_WORKFLOW_STATUSES:
        raise LifecycleError('当前工作流不处于可恢复状态')
    case.workflow_status = 'running'
    case.workflow_pause_requested = False
    case.workflow_error = ''
    case.save(update_fields=[
        'workflow_status', 'workflow_pause_requested',
        'workflow_error', 'updated_at',
    ])
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
        case.workflow_pause_requested = False
        case.workflow_paused_after = ''
        case.workflow_finished_at = timezone.now()
        case.workflow_error = '工作流结束但未生成有效文稿'
        case.save(update_fields=[
            'workflow_status', 'workflow_pause_requested', 'workflow_paused_after',
            'workflow_finished_at', 'workflow_error', 'updated_at',
        ])
        return TransitionResult(case=case, changed=False)

    case.workflow_status = 'succeeded'
    case.workflow_pause_requested = False
    case.workflow_paused_after = ''
    case.workflow_finished_at = timezone.now()
    case.workflow_error = ''
    case.document_stale = False
    case.save(update_fields=[
        'workflow_status', 'workflow_pause_requested', 'workflow_paused_after',
        'workflow_finished_at', 'workflow_error',
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
        case.workflow_pause_requested = False
        case.workflow_paused_after = ''
        case.workflow_finished_at = timezone.now()
        case.workflow_error = (error or '工作流处理失败')[:2000]
        case.save(update_fields=[
            'workflow_status', 'workflow_pause_requested', 'workflow_paused_after',
            'workflow_finished_at', 'workflow_error', 'updated_at',
        ])
    return case


@transaction.atomic
def archive_case(case_id: int, *, actor) -> TransitionResult:
    case = Case.objects.select_for_update().get(pk=case_id)
    if case.status == 'closed':
        return TransitionResult(case=case, changed=False)
    if case.workflow_status in NON_ARCHIVABLE_WORKFLOW_STATUSES:
        raise LifecycleError('工作流尚未结束，暂不能归档')
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
    case.workflow_pause_requested = False
    case.workflow_paused_after = ''
    case.workflow_finished_at = timezone.now()
    case.save(update_fields=[
        'workflow_status', 'workflow_pause_requested', 'workflow_paused_after',
        'workflow_finished_at', 'updated_at',
    ])
    return result


def mark_document_stale(case_id: int) -> None:
    """已形成文稿后材料发生变更时，标记文稿需要重新生成。"""
    Case.objects.filter(pk=case_id, status='submitted').update(document_stale=True)


# ===== Task 3.1：WorkflowRun 状态转换函数（不删除现有 Case 状态转换函数，保留双写兼容）=====


def start_workflow_run(run_id: int, started_at=None) -> None:
    """启动 WorkflowRun：status=running, started_at=now。

    Args:
        run_id: WorkflowRun ID
        started_at: 启动时间（None 表示当前时间）
    """
    from api.models import WorkflowRun
    WorkflowRun.objects.filter(pk=run_id).update(
        status='running',
        started_at=started_at or timezone.now(),
    )


def pause_workflow_run(run_id: int) -> None:
    """暂停 WorkflowRun：status=pausing。"""
    from api.models import WorkflowRun
    WorkflowRun.objects.filter(pk=run_id).update(status='pausing')


def wait_user_workflow_run(run_id: int) -> None:
    """WorkflowRun 进入等待用户介入：status=waiting_user。"""
    from api.models import WorkflowRun
    WorkflowRun.objects.filter(pk=run_id).update(status='waiting_user')


def complete_workflow_run(run_id: int, quality_summary: dict = None) -> None:
    """WorkflowRun 成功完成：status=succeeded, finished_at=now。

    Args:
        run_id: WorkflowRun ID
        quality_summary: 质量摘要（可选）
    """
    from api.models import WorkflowRun
    update_fields = {
        'status': 'succeeded',
        'finished_at': timezone.now(),
    }
    if quality_summary:
        update_fields['quality_summary'] = quality_summary
    WorkflowRun.objects.filter(pk=run_id).update(**update_fields)


def fail_workflow_run(run_id: int, error_message: str) -> None:
    """WorkflowRun 失败：status=failed, finished_at=now, error_message=str(e)。

    Args:
        run_id: WorkflowRun ID
        error_message: 错误信息（截断至 2000 字符）
    """
    from api.models import WorkflowRun
    WorkflowRun.objects.filter(pk=run_id).update(
        status='failed',
        finished_at=timezone.now(),
        error_message=(error_message or '')[:2000],
    )


def cancel_workflow_run(run_id: int) -> None:
    """WorkflowRun 取消：status=cancelled, finished_at=now。"""
    from api.models import WorkflowRun
    WorkflowRun.objects.filter(pk=run_id).update(
        status='cancelled',
        finished_at=timezone.now(),
    )


def update_run_progress(
    run_id: int,
    *,
    revision: int = None,
    current_stage: str = None,
    current_node: str = None,
    progress: float = None,
) -> None:
    """增量更新 WorkflowRun 进度字段（仅更新非 None 字段）。

    Args:
        run_id: WorkflowRun ID
        revision: state revision（可选）
        current_stage: 当前业务阶段（可选）
        current_node: 当前节点名（可选）
        progress: 进度 0.0-1.0（可选）
    """
    fields: dict = {}
    if revision is not None:
        fields['revision'] = revision
    if current_stage is not None:
        fields['current_stage'] = current_stage
    if current_node is not None:
        fields['current_node'] = current_node
    if progress is not None:
        fields['progress'] = progress
    if not fields:
        return
    from api.models import WorkflowRun
    WorkflowRun.objects.filter(pk=run_id).update(**fields)


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
    elif case.workflow_status == 'paused':
        next_action = 'resume_paused_workflow'
    elif case.workflow_status in ACTIVE_WORKFLOW_STATUSES:
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
        'can_archive': document_done and masking_done and case.workflow_status not in NON_ARCHIVABLE_WORKFLOW_STATUSES and case.status == 'submitted',
    }


# ===== Task 3.4.2: Case.workflow_status 枚举映射（旧值 ↔ 新值）=====
#
# 兼容策略详见模块 docstring。
# - Case.workflow_status 字段保持旧值不变（不修改 choices，不触发迁移）
# - WorkflowRun.status 使用新枚举（Task 3.1 已落地）
# - 旧 API 直接返回旧值；新 API 通过 map_legacy_status_to_new() 转换后返回
# - waiting_user 反向映射需 intervention_type 区分 paused / waiting_review


# 旧 → 新状态映射（向后兼容）
LEGACY_TO_NEW_STATUS = {
    'idle': 'idle',
    'running': 'running',
    'pausing': 'pausing',
    'paused': 'waiting_user',
    'waiting_review': 'waiting_user',
    'succeeded': 'succeeded',
    'failed': 'failed',
}

NEW_TO_LEGACY_STATUS_DEFAULT = {
    'idle': 'idle',
    'queued': 'idle',
    'running': 'running',
    'pausing': 'pausing',
    'waiting_user': 'paused',  # 默认映射为 paused，具体可由 intervention_type 区分
    'succeeded': 'succeeded',
    'failed': 'failed',
    'cancelled': 'failed',
}


def map_workflow_status_to_legacy(status: str, intervention_type: Optional[str] = None) -> str:
    """新状态 → 旧状态映射（旧 API 兼容）。

    Args:
        status: 新状态值（idle / queued / running / pausing / waiting_user /
            succeeded / failed / cancelled）
        intervention_type: 介入类型（用于区分 paused / waiting_review），仅在
            `status='waiting_user'` 时生效：
            - 'user_pause' → 旧 'paused'
            - 'quality_review' → 旧 'waiting_review'
            - None / 其他 → 默认 'paused'

    Returns:
        旧状态值。未知新状态原样返回（防御性 fallback）。
    """
    if status == 'waiting_user':
        if intervention_type == 'quality_review':
            return 'waiting_review'
        return 'paused'
    return NEW_TO_LEGACY_STATUS_DEFAULT.get(status, status)


def map_legacy_status_to_new(legacy_status: str) -> str:
    """旧状态 → 新状态映射。

    Args:
        legacy_status: 旧状态值（idle / running / pausing / paused /
            waiting_review / succeeded / failed）

    Returns:
        新状态值。`paused` 与 `waiting_review` 都映射为 `waiting_user`；
        未知旧状态原样返回（防御性 fallback）。
    """
    return LEGACY_TO_NEW_STATUS.get(legacy_status, legacy_status)
