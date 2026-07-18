# -*- coding: utf-8 -*-
"""Task 2.1.5 测试：工作流介入服务。

覆盖 intervention_service 的 5 个核心场景：
1. create_intervention 使用 update_or_create 幂等（连续调用 2 次返回同一记录）
2. submit_intervention 成功更新 status + submitted_values
3. submit_intervention 对非 pending 状态抛 ValueError
4. cancel_intervention 成功更新 status + cancelled_at
5. validate_revision_conflict 对不匹配抛 RevisionConflictError

测试使用 Django TestCase（SQLite，由 settings 在 manage.py test 时自动启用），
无需 MySQL / Postgres。对齐 `langgraph-human-in-the-loop` skill 幂等性要求。
"""
from django.contrib.auth.models import User
from django.test import TestCase

from api.models import Case, WorkflowIntervention
from api.services.intervention_service import (
    RevisionConflictError,
    cancel_intervention,
    create_intervention,
    submit_intervention,
    validate_revision_conflict,
)


class CreateInterventionTests(TestCase):
    """SubTask 2.1.3 - create_intervention 幂等性测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = Case.objects.create(title='测试案件', owner=self.user)

    def test_create_intervention_is_idempotent(self):
        """连续调用 2 次 create_intervention 应返回同一记录（update_or_create）。"""
        kwargs = dict(
            case_id=self.case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=3,
            form_schema={'fields': [{'name': 'amount'}]},
            initial_values={'amount': '699'},
            impact={'stale_artifacts': ['complaint_draft']},
            created_by_id=self.user.id,
        )
        first = create_intervention(**kwargs)
        second = create_intervention(**kwargs)

        self.assertEqual(WorkflowIntervention.objects.count(), 1)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.status, 'pending')
        self.assertEqual(first.intervention_type, 'quality_review')
        self.assertEqual(first.stage, 'extract')
        self.assertEqual(first.base_revision, 3)
        self.assertEqual(first.form_schema, {'fields': [{'name': 'amount'}]})
        self.assertEqual(first.initial_values, {'amount': '699'})
        self.assertEqual(first.impact, {'stale_artifacts': ['complaint_draft']})
        self.assertEqual(first.created_by_id, self.user.id)
        self.assertIsNotNone(first.expires_at)

    def test_create_intervention_different_base_revision_creates_new(self):
        """不同 base_revision 视为不同介入，应创建新记录。"""
        create_intervention(
            case_id=self.case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=1,
            form_schema={},
            initial_values={},
            impact={},
        )
        create_intervention(
            case_id=self.case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=2,
            form_schema={},
            initial_values={},
            impact={},
        )
        self.assertEqual(WorkflowIntervention.objects.count(), 2)

    def test_create_intervention_resets_state_on_recreate(self):
        """update_or_create 应重置 status / submitted_values 等字段。"""
        intervention = create_intervention(
            case_id=self.case.id,
            intervention_type='user_pause',
            stage='evidence_chain',
            base_revision=0,
            form_schema={},
            initial_values={},
            impact={},
        )
        # 模拟之前被提交过
        intervention.status = 'submitted'
        intervention.submitted_values = {'old': 'data'}
        intervention.save()

        # 再次 create 应重置为 pending
        recreated = create_intervention(
            case_id=self.case.id,
            intervention_type='user_pause',
            stage='evidence_chain',
            base_revision=0,
            form_schema={},
            initial_values={},
            impact={},
        )
        self.assertEqual(recreated.id, intervention.id)
        self.assertEqual(recreated.status, 'pending')
        self.assertEqual(recreated.submitted_values, {})
        self.assertIsNone(recreated.submitted_at)
        self.assertIsNone(recreated.cancelled_at)


class SubmitInterventionTests(TestCase):
    """SubTask 2.1.3 - submit_intervention 测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        # Task 2.4：submit_intervention 启用 revision 冲突检测（占位用 Case.workflow_revision）
        # 需将 case.workflow_revision 与 base_revision 对齐，避免误触发 RevisionConflictError
        self.case = Case.objects.create(title='测试案件', owner=self.user, workflow_revision=1)
        self.intervention = create_intervention(
            case_id=self.case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=1,
            form_schema={'fields': [{'name': 'amount'}]},
            initial_values={'amount': '699'},
            impact={},
        )

    def test_submit_intervention_updates_status_and_values(self):
        """submit_intervention 成功更新 status=submitted + submitted_values。"""
        result = submit_intervention(
            intervention_id=self.intervention.id,
            submitted_values={'amount': '750'},
            submitted_by_id=self.user.id,
        )

        self.assertEqual(result.status, 'submitted')
        self.assertEqual(result.submitted_values, {'amount': '750'})
        self.assertEqual(result.submitted_by_id, self.user.id)
        self.assertIsNotNone(result.submitted_at)

        # 验证 DB 持久化
        refreshed = WorkflowIntervention.objects.get(pk=self.intervention.id)
        self.assertEqual(refreshed.status, 'submitted')
        self.assertEqual(refreshed.submitted_values, {'amount': '750'})
        self.assertIsNotNone(refreshed.submitted_at)

    def test_submit_intervention_rejects_non_pending_status(self):
        """submit_intervention 对非 pending 状态抛 ValueError。"""
        self.intervention.status = 'submitted'
        self.intervention.save()

        with self.assertRaises(ValueError) as ctx:
            submit_intervention(
                intervention_id=self.intervention.id,
                submitted_values={'amount': '750'},
            )
        self.assertIn('pending', str(ctx.exception))
        self.assertIn('submitted', str(ctx.exception))

    def test_submit_intervention_rejects_cancelled_status(self):
        """submit_intervention 对 cancelled 状态抛 ValueError。"""
        self.intervention.status = 'cancelled'
        self.intervention.save()

        with self.assertRaises(ValueError):
            submit_intervention(
                intervention_id=self.intervention.id,
                submitted_values={},
            )


class CancelInterventionTests(TestCase):
    """SubTask 2.1.3 - cancel_intervention 测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = Case.objects.create(title='测试案件', owner=self.user)
        self.intervention = create_intervention(
            case_id=self.case.id,
            intervention_type='user_pause',
            stage='evidence_chain',
            base_revision=2,
            form_schema={},
            initial_values={},
            impact={},
        )

    def test_cancel_intervention_updates_status_and_cancelled_at(self):
        """cancel_intervention 成功更新 status=cancelled + cancelled_at。"""
        result = cancel_intervention(intervention_id=self.intervention.id)

        self.assertEqual(result.status, 'cancelled')
        self.assertIsNotNone(result.cancelled_at)

        # 验证 DB 持久化
        refreshed = WorkflowIntervention.objects.get(pk=self.intervention.id)
        self.assertEqual(refreshed.status, 'cancelled')
        self.assertIsNotNone(refreshed.cancelled_at)

    def test_cancel_intervention_rejects_non_pending_status(self):
        """cancel_intervention 对非 pending 状态抛 ValueError。"""
        self.intervention.status = 'submitted'
        self.intervention.save()

        with self.assertRaises(ValueError) as ctx:
            cancel_intervention(intervention_id=self.intervention.id)
        self.assertIn('pending', str(ctx.exception))


class ValidateRevisionConflictTests(TestCase):
    """SubTask 2.1.3 - validate_revision_conflict 测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = Case.objects.create(title='测试案件', owner=self.user)
        self.intervention = create_intervention(
            case_id=self.case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=5,
            form_schema={},
            initial_values={},
            impact={},
        )

    def test_validate_revision_conflict_raises_on_mismatch(self):
        """base_revision 与 current_revision 不匹配抛 RevisionConflictError。"""
        with self.assertRaises(RevisionConflictError) as ctx:
            validate_revision_conflict(self.intervention, current_revision=6)
        self.assertEqual(ctx.exception.base_revision, 5)
        self.assertEqual(ctx.exception.current_revision, 6)
        self.assertIn('5', str(ctx.exception))
        self.assertIn('6', str(ctx.exception))

    def test_validate_revision_conflict_passes_on_match(self):
        """base_revision 与 current_revision 匹配时不抛异常。"""
        # 不应抛出任何异常
        validate_revision_conflict(self.intervention, current_revision=5)


class WorkflowInterventionModelTests(TestCase):
    """WorkflowIntervention 模型基础测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = Case.objects.create(title='测试案件', owner=self.user)

    def test_unique_together_enforced(self):
        """Task 3.1 后 unique_together 改为 (workflow_run, type, stage, base_revision)。

        相同 (workflow_run, type, stage, base_revision) 应拒绝重复 create。
        """
        from api.models import WorkflowRun
        run = WorkflowRun.objects.create(case=self.case)
        WorkflowIntervention.objects.create(
            workflow_run=run,
            case=self.case,
            intervention_type='quality_review',
            stage='extract',
            base_revision=1,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            WorkflowIntervention.objects.create(
                workflow_run=run,
                case=self.case,
                intervention_type='quality_review',
                stage='extract',
                base_revision=1,
            )

    def test_case_only_duplicates_allowed_after_refactor(self):
        """Task 3.1 后 case 唯一约束已移除，仅传 case（workflow_run=None）允许重复。

        因 SQLite/Postgres 唯一约束中 NULL 视为不相等，且 case 字段不再有
        unique_together 约束，相同 (case, type, stage, base_revision) 但 workflow_run=None
        的多条记录应允许创建（向后兼容）。
        """
        WorkflowIntervention.objects.create(
            case=self.case,
            intervention_type='quality_review',
            stage='extract',
            base_revision=1,
        )
        # 不应抛出异常（旧 case unique_together 已移除）
        WorkflowIntervention.objects.create(
            case=self.case,
            intervention_type='quality_review',
            stage='extract',
            base_revision=1,
        )
        self.assertEqual(WorkflowIntervention.objects.count(), 2)

    def test_str_representation(self):
        """__str__ 含 workflow_run_id / case_id / type / stage / status。"""
        intervention = WorkflowIntervention.objects.create(
            case=self.case,
            intervention_type='user_pause',
            stage='evidence_chain',
            base_revision=0,
        )
        text = str(intervention)
        self.assertIn(f'case={self.case.id}', text)
        self.assertIn('type=user_pause', text)
        self.assertIn('stage=evidence_chain', text)
        self.assertIn('status=pending', text)


class WorkflowInterventionSchemaTests(TestCase):
    """WorkflowInterventionSchema 序列化测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = Case.objects.create(title='测试案件', owner=self.user)
        self.intervention = create_intervention(
            case_id=self.case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=2,
            form_schema={'fields': [{'name': 'amount', 'type': 'text'}]},
            initial_values={'amount': '699'},
            impact={'stale_artifacts': ['complaint_draft']},
        )

    def test_from_model_serializes_all_fields(self):
        """from_model 正确序列化所有字段。"""
        from api.agents.schemas import WorkflowInterventionSchema

        schema = WorkflowInterventionSchema.from_model(self.intervention)
        self.assertEqual(schema.id, self.intervention.id)
        self.assertEqual(schema.case_id, self.case.id)
        self.assertEqual(schema.intervention_type, 'quality_review')
        self.assertEqual(schema.stage, 'extract')
        self.assertEqual(schema.status, 'pending')
        self.assertEqual(schema.base_revision, 2)
        self.assertEqual(
            schema.form_schema, {'fields': [{'name': 'amount', 'type': 'text'}]}
        )
        self.assertEqual(schema.initial_values, {'amount': '699'})
        self.assertEqual(schema.impact, {'stale_artifacts': ['complaint_draft']})
        self.assertIsNone(schema.submitted_at)
        self.assertIsNone(schema.cancelled_at)
        self.assertIsNotNone(schema.expires_at)
