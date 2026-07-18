# -*- coding: utf-8 -*-
"""工作流介入服务。

职责：
- create_intervention：创建介入记录（幂等，使用 update_or_create）
- submit_intervention：用户提交介入（含 revision 冲突检测）
- cancel_intervention：取消介入
- validate_revision_conflict：校验 base_revision 与 case/workflow_run 当前 revision 是否冲突

幂等性：按 (workflow_run + intervention_type + stage + base_revision) update_or_create，
resume 时不会创建重复记录（对齐 langgraph-human-in-the-loop skill 要求）。

Task 3.1 落地（已完成）：
- 新增 workflow_run 外键（替代 case 外键），case 字段保留为冗余便于按 case 查询历史介入
- create_intervention 优先使用 workflow_run_id；如未指定则回退到 case_id（兼容旧调用方）
- submit_intervention 优先从 WorkflowRun.revision 读取当前 revision 进行冲突检测，
  如 workflow_run 为 None 则回退到 case.workflow_revision（兼容旧记录）

-----
Overwrite 使用模式（Task 2.4 文档化，对齐 langgraph-persistence skill）：
介入提交后如需直接修改 state 列表字段（如 `evidence_extract_results`），**必须**
使用 `langgraph.types.Overwrite` 包装新值，不能直接传 list。原因：state 中
`evidence_extract_results` 等字段声明了 `Annotated[list, add]` reducer，直接传
list 会被追加到旧值（导致下游读到双倍字段），而 `Overwrite([...])` 会替换整个列表。

参考实现：`backend/api/agents/nodes/review_node.py` 的 Command.update 中
`"evidence_extract_results": Overwrite(updated_results)`。

适用场景：
- review_node resume：用人工校正后的结果整体替换 `evidence_extract_results`
- Task 3.3 RetryService：使用 `graph.update_state(config, {"<list_field>": Overwrite(...)})`
  在 fork 时替换列表字段
- 任何节点需要「替换而非追加」list 字段时

注意：仅 list 字段需要 `Overwrite`，标量字段（如 `revision / current_stage`）和
自定义 reducer dict 字段（如 `user_confirmed_fields`，使用 merge_dict reducer）
直接传值即可，不需要 `Overwrite` 包装。
"""
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from api.models import WorkflowIntervention


class RevisionConflictError(Exception):
    """base_revision 与当前 case/workflow_run revision 不匹配。"""

    def __init__(self, base_revision: int, current_revision: int):
        self.base_revision = base_revision
        self.current_revision = current_revision
        super().__init__(
            f'Revision conflict: base_revision={base_revision}, '
            f'current_revision={current_revision}'
        )


def create_intervention(
    *,
    case_id: Optional[int] = None,
    workflow_run_id: Optional[int] = None,
    intervention_type: str,
    stage: str,
    base_revision: int,
    form_schema: dict,
    initial_values: dict,
    impact: dict,
    created_by_id: Optional[int] = None,
    expires_in_hours: int = 24,
) -> WorkflowIntervention:
    """创建介入记录（幂等）。

    优先使用 workflow_run_id（Task 3.1 后主关联）；如未指定则回退到 case_id
    （兼容旧调用方）。当传入 workflow_run_id 时，case_id 若未指定则从
    workflow_run.case 派生并写入冗余字段。

    幂等性约束：
    - 传入 workflow_run_id：按 (workflow_run + type + stage + base_revision) update_or_create
    - 仅传 case_id：按 (case + type + stage + base_revision) update_or_create（兼容旧逻辑）

    Args:
        case_id: 案件 ID（可选，传入 workflow_run_id 时可省略）
        workflow_run_id: 工作流运行 ID（Task 3.1 后主关联）
        intervention_type: quality_review / user_pause
        stage: 触发阶段
        base_revision: 触发时的 state.revision
        form_schema: 前端动态表单 schema
        initial_values: 初始值
        impact: 影响范围
        created_by_id: 创建用户 ID
        expires_in_hours: 过期时间（小时），默认 24h

    Returns:
        WorkflowIntervention 实例
    """
    if not workflow_run_id and not case_id:
        raise ValueError('workflow_run_id 和 case_id 至少指定其一')

    expires_at = timezone.now() + timedelta(hours=expires_in_hours)

    # 派生 case_id（如未指定但从 workflow_run 派生）
    if not case_id and workflow_run_id:
        from api.models import WorkflowRun
        case_id = WorkflowRun.objects.values_list('case_id', flat=True).get(
            pk=workflow_run_id
        )

    defaults = {
        'form_schema': form_schema,
        'initial_values': initial_values,
        'impact': impact,
        'status': 'pending',
        'expires_at': expires_at,
        'created_by_id': created_by_id,
        'submitted_values': {},
        'submitted_at': None,
        'cancelled_at': None,
    }

    if workflow_run_id:
        # Task 3.1 主路径：基于 workflow_run 幂等
        # 同时写入 case_id 冗余字段（便于按 case 查询）
        intervention, _created = WorkflowIntervention.objects.update_or_create(
            workflow_run_id=workflow_run_id,
            intervention_type=intervention_type,
            stage=stage,
            base_revision=base_revision,
            defaults={
                **defaults,
                'case_id': case_id,
            },
        )
    else:
        # 兼容旧调用方（无 workflow_run）：基于 case 幂等
        intervention, _created = WorkflowIntervention.objects.update_or_create(
            case_id=case_id,
            intervention_type=intervention_type,
            stage=stage,
            base_revision=base_revision,
            defaults=defaults,
        )
    return intervention


@transaction.atomic
def submit_intervention(
    intervention_id: int,
    submitted_values: dict,
    submitted_by_id: Optional[int] = None,
) -> WorkflowIntervention:
    """用户提交介入（含 revision 冲突检测）。

    Task 3.1：优先从 WorkflowRun.revision 读取当前 revision 进行冲突检测，
    如 workflow_run 为 None 则回退到 case.workflow_revision（兼容旧记录）。

    Args:
        intervention_id: 介入记录 ID
        submitted_values: 用户提交的值
        submitted_by_id: 提交用户 ID

    Returns:
        更新后的 WorkflowIntervention 实例

    Raises:
        WorkflowIntervention.DoesNotExist: 如介入记录不存在
        ValueError: 如介入状态非 pending
        RevisionConflictError: 如 base_revision 与当前 revision 不匹配
    """
    intervention = WorkflowIntervention.objects.select_for_update().get(
        pk=intervention_id
    )

    if intervention.status != 'pending':
        raise ValueError(
            f'介入状态非 pending（当前: {intervention.status}）无法提交'
        )

    # Task 3.1：revision 冲突检测优先从 workflow_run.revision 读取
    # 如 workflow_run 为 None 则回退到 case.workflow_revision（兼容旧记录）
    current_revision = None
    if intervention.workflow_run_id:
        current_revision = intervention.workflow_run.revision
    elif intervention.case_id:
        current_revision = getattr(intervention.case, 'workflow_revision', None)

    if current_revision is not None:
        validate_revision_conflict(intervention, current_revision)

    intervention.submitted_values = submitted_values
    intervention.submitted_by_id = submitted_by_id
    intervention.submitted_at = timezone.now()
    intervention.status = 'submitted'
    intervention.save(update_fields=[
        'submitted_values', 'submitted_by_id', 'submitted_at', 'status',
    ])
    return intervention


@transaction.atomic
def cancel_intervention(
    intervention_id: int,
    cancelled_by_id: Optional[int] = None,
) -> WorkflowIntervention:
    """取消介入记录。

    Args:
        intervention_id: 介入记录 ID
        cancelled_by_id: 取消用户 ID（当前未持久化，预留以备 Task 3.1 扩展）

    Returns:
        更新后的 WorkflowIntervention 实例

    Raises:
        WorkflowIntervention.DoesNotExist: 如介入记录不存在
        ValueError: 如介入状态非 pending
    """
    intervention = WorkflowIntervention.objects.select_for_update().get(
        pk=intervention_id
    )

    if intervention.status != 'pending':
        raise ValueError(
            f'介入状态非 pending（当前: {intervention.status}）无法取消'
        )

    intervention.status = 'cancelled'
    intervention.cancelled_at = timezone.now()
    intervention.save(update_fields=['status', 'cancelled_at'])
    return intervention


def validate_revision_conflict(
    intervention: WorkflowIntervention,
    current_revision: int,
) -> None:
    """校验 base_revision 与当前 revision 是否冲突。

    Args:
        intervention: 介入记录
        current_revision: 当前 case / workflow_run 的 revision

    Raises:
        RevisionConflictError: 如不匹配
    """
    if intervention.base_revision != current_revision:
        raise RevisionConflictError(
            intervention.base_revision, current_revision
        )
