# -*- coding: utf-8 -*-
"""Task 2.4 测试：revision 冲突检测 + 用户确认字段 + Overwrite 使用。

覆盖 5 个核心场景：
1. validate_revision_conflict 对 base_revision=5 + current_revision=5 不抛异常
2. validate_revision_conflict 对 base_revision=5 + current_revision=6 抛 RevisionConflictError
3. 占位端点对 RevisionConflictError 返回 409（DRF APIClient）
4. review_node resume 时 ExtractedField.user_confirmed=True（mock update 调用）
5. review_node resume 时 state["user_confirmed_fields"] 含已校正字段（合并 reducer 行为）

测试使用 Django TestCase（SQLite）+ unittest.mock，无需 MySQL / Postgres / langgraph checkpointer。
对齐 `langgraph-human-in-the-loop` skill 幂等性要求与 `langgraph-persistence` skill `Overwrite` 使用要求。
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Case, ExtractedField, WorkflowIntervention
from api.services.intervention_service import (
    RevisionConflictError,
    create_intervention,
    submit_intervention,
    validate_revision_conflict,
)


# ---------------------------------------------------------------------------
# 测试 1 & 2：validate_revision_conflict 函数行为
# ---------------------------------------------------------------------------


class ValidateRevisionConflictFunctionTests(TestCase):
    """SubTask 2.4.1 - validate_revision_conflict 单元测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = Case.objects.create(title='测试案件', owner=self.user)
        # base_revision=5 的介入记录
        self.intervention = create_intervention(
            case_id=self.case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=5,
            form_schema={},
            initial_values={},
            impact={},
        )

    def test_validate_revision_conflict_passes_when_revision_matches(self):
        """测试 1：base_revision=5 + current_revision=5 不抛异常。"""
        # 不应抛出任何异常
        validate_revision_conflict(self.intervention, current_revision=5)

    def test_validate_revision_conflict_raises_on_mismatch(self):
        """测试 2：base_revision=5 + current_revision=6 抛 RevisionConflictError。"""
        with self.assertRaises(RevisionConflictError) as ctx:
            validate_revision_conflict(self.intervention, current_revision=6)

        self.assertEqual(ctx.exception.base_revision, 5)
        self.assertEqual(ctx.exception.current_revision, 6)
        # 异常消息含两个 revision 数字，便于前端展示
        self.assertIn('5', str(ctx.exception))
        self.assertIn('6', str(ctx.exception))


# ---------------------------------------------------------------------------
# 测试 3：占位端点对 RevisionConflictError 返回 409
# ---------------------------------------------------------------------------


class SubmitInterventionEndpointConflictTests(TestCase):
    """SubTask 2.4.2 - 占位端点 409 冲突响应测试。

    端点：POST /api/cases/<case_id>/interventions/<intervention_id>/submit/
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass'
        )
        # workflow_revision=5，与 base_revision=6 不匹配，触发冲突
        self.case = Case.objects.create(
            title='测试案件', owner=self.user, workflow_revision=5
        )
        self.intervention = create_intervention(
            case_id=self.case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=6,  # 与 case.workflow_revision=5 不匹配
            form_schema={},
            initial_values={},
            impact={},
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = (
            f'/api/cases/{self.case.id}/'
            f'interventions/{self.intervention.id}/submit/'
        )

    def test_endpoint_returns_409_on_revision_conflict(self):
        """测试 3：RevisionConflictError 时端点返回 409 + REVISION_CONFLICT code。"""
        response = self.client.post(
            self.url,
            {'submitted_values': {'amount': '750'}},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        payload = response.json()
        self.assertEqual(payload['code'], 'REVISION_CONFLICT')
        self.assertIn('5', payload['detail'])  # current_revision=5
        self.assertIn('6', payload['detail'])  # base_revision=6
        self.assertEqual(payload['current_revision'], 5)

    def test_endpoint_returns_200_when_revision_matches(self):
        """对比测试：revision 匹配时端点返回 200 + submitted。"""
        # 重新创建一个 base_revision=5 的介入（匹配 case.workflow_revision=5）
        matched = create_intervention(
            case_id=self.case.id,
            intervention_type='quality_review',
            stage='evidence_chain',  # 不同 stage 避免唯一约束冲突
            base_revision=5,
            form_schema={},
            initial_values={},
            impact={},
        )
        url = f'/api/cases/{self.case.id}/interventions/{matched.id}/submit/'

        response = self.client.post(
            url,
            {'submitted_values': {'amount': '750'}},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['status'], 'submitted')
        self.assertEqual(payload['intervention']['status'], 'submitted')
        self.assertEqual(payload['intervention']['id'], matched.id)


# ---------------------------------------------------------------------------
# 测试 4 & 5：review_node resume 行为（mock DB + interrupt）
# ---------------------------------------------------------------------------


class ReviewNodeResumeMarkUserConfirmedTests(TestCase):
    """SubTask 2.4.4 - review_node resume 时标记 user_confirmed + 写 state 字段。

    使用 mock 隔离 langgraph interrupt + DB 调用，专注验证：
    - ExtractedField.objects.filter(...).update(...) 调用含 user_confirmed=True / confirmed_at
    - Command.update 字典含 user_confirmed_fields key（merge_dict reducer 合并）
    """

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = Case.objects.create(title='测试案件', owner=self.user)

    def _make_state_with_low_confidence_fields(self):
        """构造含低置信度字段的 state（触发 HITL）。"""
        return {
            'case_id': self.case.id,
            'evidence_ids': [101],
            'evidence_preclassify_results': [],
            'evidence_ocr_results': [],
            'evidence_classify_results': [],
            'evidence_extract_results': [
                {
                    'evidence_id': 101,
                    'evidence_code': 'E1',
                    'fields': [
                        {
                            'field_name': '金额',
                            'field_value': '699',
                            'confidence': 0.3,  # 低于 0.7，触发 HITL
                        }
                    ],
                    'needs_human_review': True,
                }
            ],
            'needs_human_review': True,
            'evidence_chain': [],
            'complaint_draft': None,
            'review_decision': None,
            'errors': [],
            'revision': 5,
        }

    def _run_review_node_resume(self, state, corrections):
        """运行 review_node 的 resume 路径，返回 Command.update 字典。

        mock 以下依赖：
        - api.agents.nodes.review_node.create_intervention：返回 mock intervention
        - api.agents.nodes.review_node.interrupt：返回用户校正数据
        - ExtractedField.objects.filter().update：捕获调用参数
        - Evidence.objects.get + evidence.extracted_fields.all：返回 mock 字段
        """
        # 注意：因为 nodes/__init__.py 第 6 行 `from api.agents.nodes.review_node
        # import review_node` 把 `review_node` 名字绑定到了函数（覆盖了子模块属性），
        # `patch.object(module, ...)` 模式无法定位模块。这里改用字符串路径 patch，
        # 直接定位到 `api.agents.nodes.review_node` 模块对象的属性，绕过覆盖问题。
        # 用 importlib.import_module 拿到真实模块对象（不受 __init__.py 覆盖影响）。
        import importlib
        review_node_mod = importlib.import_module('api.agents.nodes.review_node')

        # mock intervention（含 id 即可）
        mock_intervention = MagicMock()
        mock_intervention.id = 999

        # mock ExtractedField.objects.filter(...).update 调用
        update_call_kwargs = {}

        def _capture_update(**kwargs):
            update_call_kwargs.update(kwargs)
            return 1  # 影响 1 行

        mock_filter_qs = MagicMock()
        mock_filter_qs.update = _capture_update

        # mock Evidence.objects.get 返回含 extracted_fields.all() 的对象
        mock_field_obj = MagicMock()
        mock_field_obj.field_name = '金额'
        mock_field_obj.field_value = '750'  # 用户校正后的值
        mock_field_obj.confidence = 1.0

        mock_evidence = MagicMock()
        mock_evidence.extracted_fields.all.return_value = [mock_field_obj]

        async def _run():
            # 注意：create_intervention 在 review_node 中被 sync_to_async 包装，
            # 故 mock 必须是同步 MagicMock（不能用 AsyncMock，否则 sync_to_async
            # 会抛 "can only be applied to sync functions"）。
            with patch('api.agents.nodes.review_node.create_intervention', new=MagicMock(return_value=mock_intervention)):
                with patch('api.agents.nodes.review_node.interrupt', return_value={'corrections': corrections}):
                    with patch('api.models.ExtractedField') as MockExtractedField:
                        MockExtractedField.objects.filter.return_value = mock_filter_qs
                        with patch('api.models.Evidence') as MockEvidence:
                            MockEvidence.objects.get = AsyncMock(return_value=mock_evidence)
                            with patch('api.models.Evidence.DoesNotExist', new=Exception):
                                cmd = await review_node_mod.review_node(state)
                                return cmd, update_call_kwargs

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    def test_review_node_resume_marks_user_confirmed_true(self):
        """测试 4：resume 时 ExtractedField.update 含 user_confirmed=True + confirmed_at。"""
        state = self._make_state_with_low_confidence_fields()
        corrections = [
            {
                'evidence_id': 101,
                'field_name': '金额',
                'field_value': '750',  # 用户校正后的值
            }
        ]

        cmd, update_kwargs = self._run_review_node_resume(state, corrections)

        # 验证 update 调用含 user_confirmed=True / confirmed_at / field_value / confidence
        self.assertEqual(update_kwargs.get('field_value'), '750')
        self.assertEqual(update_kwargs.get('confidence'), 1.0)
        self.assertTrue(update_kwargs.get('user_confirmed'))
        self.assertIsNotNone(update_kwargs.get('confirmed_at'))
        # confirmed_at 应为 datetime 实例（DB 写入时为 datetime，state 中转为 ISO 字符串）
        import datetime as dt
        self.assertIsInstance(update_kwargs.get('confirmed_at'), dt.datetime)

    def test_review_node_resume_appends_user_confirmed_fields_to_state(self):
        """测试 5：Command.update 含 user_confirmed_fields（merge_dict reducer 合并）。"""
        state = self._make_state_with_low_confidence_fields()
        corrections = [
            {
                'evidence_id': 101,
                'field_name': '金额',
                'field_value': '750',
            }
        ]

        cmd, _ = self._run_review_node_resume(state, corrections)

        # cmd 是 Command 实例，update 字段在 cmd.update
        self.assertTrue(hasattr(cmd, 'update'))
        update_dict = cmd.update

        # 1. user_confirmed_fields 存在
        self.assertIn('user_confirmed_fields', update_dict)

        confirmed = update_dict['user_confirmed_fields']
        # 2. key 格式为 "{evidence_id}:{field_name}"
        expected_key = '101:金额'
        self.assertIn(expected_key, confirmed)

        entry = confirmed[expected_key]
        # 3. 含 evidence_id / field_name / confirmed_at（ISO 8601）/ confirmed_by
        self.assertEqual(entry['evidence_id'], 101)
        self.assertEqual(entry['field_name'], '金额')
        self.assertEqual(entry['confirmed_by'], 'user')
        # confirmed_at 为 ISO 8601 字符串（JSON 可序列化）
        self.assertIsInstance(entry['confirmed_at'], str)
        # 可被 datetime.fromisoformat 解析回 datetime
        parsed = datetime.fromisoformat(entry['confirmed_at'])
        self.assertIsNotNone(parsed)

    def test_user_confirmed_fields_merges_via_merge_dict_reducer(self):
        """测试 5b：user_confirmed_fields 通过 merge_dict reducer 合并（不整体覆盖）。

        模拟两次 review_node resume（不同字段），验证 merge_dict 行为：
        第一次：{101:金额} → state.user_confirmed_fields = {101:金额}
        第二次：{102:地址} → state.user_confirmed_fields = {101:金额, 102:地址}
        """
        from api.agents.state import merge_dict

        # 第一次 resume：校正 101:金额
        first_update = {
            '101:金额': {
                'evidence_id': 101,
                'field_name': '金额',
                'confirmed_at': '2026-07-17T10:00:00+00:00',
                'confirmed_by': 'user',
            }
        }
        # 第二次 resume：校正 102:地址
        second_update = {
            '102:地址': {
                'evidence_id': 102,
                'field_name': '地址',
                'confirmed_at': '2026-07-17T11:00:00+00:00',
                'confirmed_by': 'user',
            }
        }

        # 模拟 state 中已有的 user_confirmed_fields（来自第一次 resume）
        existing = {}
        # 第一次合并
        existing = merge_dict(existing, first_update)
        self.assertEqual(set(existing.keys()), {'101:金额'})

        # 第二次合并（不覆盖第一次的字段）
        existing = merge_dict(existing, second_update)
        self.assertEqual(set(existing.keys()), {'101:金额', '102:地址'})

        # 同 key 时新值覆盖旧值（用户再次校正同一字段）
        third_update = {
            '101:金额': {
                'evidence_id': 101,
                'field_name': '金额',
                'confirmed_at': '2026-07-17T12:00:00+00:00',
                'confirmed_by': 'user',
            }
        }
        existing = merge_dict(existing, third_update)
        self.assertEqual(len(existing), 2)
        self.assertEqual(
            existing['101:金额']['confirmed_at'],
            '2026-07-17T12:00:00+00:00',
        )


# ---------------------------------------------------------------------------
# 测试 6：submit_intervention 实际启用 revision 冲突检测（占位用 Case.workflow_revision）
# ---------------------------------------------------------------------------


class SubmitInterventionRevisionCheckTests(TestCase):
    """SubTask 2.4.1 - submit_intervention 启用 revision 冲突检测（占位版）。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')

    def test_submit_intervention_passes_when_workflow_revision_matches(self):
        """case.workflow_revision 与 base_revision 匹配时提交成功。"""
        case = Case.objects.create(
            title='测试案件', owner=self.user, workflow_revision=5
        )
        intervention = create_intervention(
            case_id=case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=5,
            form_schema={},
            initial_values={},
            impact={},
        )

        result = submit_intervention(
            intervention_id=intervention.id,
            submitted_values={'amount': '750'},
            submitted_by_id=self.user.id,
        )

        self.assertEqual(result.status, 'submitted')
        self.assertEqual(result.submitted_values, {'amount': '750'})

    def test_submit_intervention_raises_conflict_on_mismatch(self):
        """case.workflow_revision 与 base_revision 不匹配时抛 RevisionConflictError。"""
        case = Case.objects.create(
            title='测试案件', owner=self.user, workflow_revision=5
        )
        intervention = create_intervention(
            case_id=case.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=6,  # 与 workflow_revision=5 不匹配
            form_schema={},
            initial_values={},
            impact={},
        )

        with self.assertRaises(RevisionConflictError) as ctx:
            submit_intervention(
                intervention_id=intervention.id,
                submitted_values={'amount': '750'},
            )

        self.assertEqual(ctx.exception.base_revision, 6)
        self.assertEqual(ctx.exception.current_revision, 5)


# ---------------------------------------------------------------------------
# 测试 7：ExtractedField 模型新增字段验证
# ---------------------------------------------------------------------------


class ExtractedFieldNewFieldsTests(TestCase):
    """SubTask 2.4.3 - ExtractedField 新增字段验证。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = Case.objects.create(title='测试案件', owner=self.user)
        from api.models import Evidence
        self.evidence = Evidence.objects.create(
            case=self.case,
            code='E1',
            evidence_type='订单页',
            description='测试证据',
            source_time=timezone.now(),
        )

    def test_extracted_field_has_user_confirmed_field(self):
        """ExtractedField 模型含 user_confirmed 字段（默认 False）。"""
        field_names = [
            f.name for f in ExtractedField._meta.get_fields()
            if 'confirm' in f.name
        ]
        self.assertIn('user_confirmed', field_names)
        self.assertIn('confirmed_at', field_names)

    def test_extracted_field_defaults(self):
        """新建 ExtractedField 默认 user_confirmed=False / confirmed_at=None。"""
        field = ExtractedField.objects.create(
            evidence=self.evidence,
            field_name='金额',
            field_value='699',
            confidence=0.9,
        )
        self.assertFalse(field.user_confirmed)
        self.assertIsNone(field.confirmed_at)

    def test_extracted_field_can_be_marked_confirmed(self):
        """可设置 user_confirmed=True + confirmed_at。"""
        from django.utils import timezone as djtz
        now = djtz.now()

        field = ExtractedField.objects.create(
            evidence=self.evidence,
            field_name='金额',
            field_value='699',
            confidence=0.9,
        )
        field.user_confirmed = True
        field.confirmed_at = now
        field.save(update_fields=['user_confirmed', 'confirmed_at'])

        refreshed = ExtractedField.objects.get(pk=field.pk)
        self.assertTrue(refreshed.user_confirmed)
        self.assertIsNotNone(refreshed.confirmed_at)


# 测试用 timezone 引用（供 ExtractedFieldNewFieldsTests.setUp 使用）
from django.utils import timezone
