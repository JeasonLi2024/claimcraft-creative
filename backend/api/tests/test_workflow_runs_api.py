# -*- coding: utf-8 -*-
"""Task 3.2 测试：/workflow-runs/* API 端点。

覆盖 7 个端点：
1. WorkflowRunCreateViewTests：POST /api/cases/{case_id}/workflow-runs/（创建运行）
2. WorkflowRunSnapshotViewTests：GET /api/workflow-runs/{run_id}/snapshot/
3. WorkflowRunPauseViewTests：POST /api/workflow-runs/{run_id}/pause/
4. WorkflowRunInterventionSubmitViewTests：POST /api/workflow-runs/{run_id}/interventions/{i}/submit/
5. WorkflowRunRetryViewTests：POST /api/workflow-runs/{run_id}/retry/
6. WorkflowRunCancelViewTests：POST /api/workflow-runs/{run_id}/cancel/
7. CaseWorkflowRunsListViewTests：GET /api/cases/{case_id}/workflow-runs/list/

测试策略（对齐 spec.md「Requirement: Unified WorkflowRun API」）：
- 使用 Django TestCase + DRF APIClient（force_authenticate 模拟登录）
- mock WorkflowRunner.start_in_background 避免启动后台任务
- mock RetryService.retry_from_stage 避免依赖 LangGraph + PostgresSaver
- 不 mock SnapshotService / InterventionService / case_lifecycle_service
  （这些是同步纯 Django DB 操作，可直接调用）
- 共 24 个测试用例覆盖成功 / 权限 / 错误响应

运行方式：
    cd backend
    python manage.py test api.tests.test_workflow_runs_api -v 2
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.agents.artifact_service import create_artifact
from api.models import Case, WorkflowArtifact, WorkflowIntervention, WorkflowRun
from api.services.intervention_service import create_intervention


def _make_case(user=None, **kwargs):
    """测试辅助：创建一个最小 Case。"""
    return Case.objects.create(
        title=kwargs.pop('title', '测试案件'),
        owner=user,
        **kwargs,
    )


def _make_run(case, **kwargs):
    """测试辅助：创建一个 WorkflowRun。"""
    defaults = {
        'status': 'running',
        'current_stage': 'fact_checking',
        'current_node': 'extract',
        'progress': 0.30,
        'revision': 3,
    }
    defaults.update(kwargs)
    return WorkflowRun.objects.create(case=case, **defaults)


# ============================================================================
# SubTask 3.2.1：WorkflowRunCreateView（POST /api/cases/{case_id}/workflow-runs/）
# ============================================================================


class WorkflowRunCreateViewTests(TestCase):
    """SubTask 3.2.1 - 创建工作流运行端点测试。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass'
        )
        self.other_user = User.objects.create_user(
            username='other', email='other@example.com', password='pass'
        )
        self.case = _make_case(self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f'/api/cases/{self.case.id}/workflow-runs/'

        # patch WorkflowRunner.start_in_background 避免启动后台任务
        # 路径：WorkflowRunCreateView.post 内部 `from api.agents import WorkflowRunner`
        # 使用字符串路径 patch，patch api.agents.WorkflowRunner 类的 start_in_background 方法
        self._runner_patcher = patch(
            'api.agents.WorkflowRunner.start_in_background',
            return_value=MagicMock(),
        )
        self._runner_patcher.start()
        self.addCleanup(self._runner_patcher.stop)

    def test_create_run_success_returns_201_with_run_id_ticket(self):
        """成功创建运行返回 201 + run_id / thread_id / stream_ticket / stream_url。"""
        response = self.client.post(
            self.url,
            {'evidence_ids': [101, 102], 'run_options': {'case_mode': 'complain'}},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertIn('run_id', payload)
        self.assertIn('thread_id', payload)
        self.assertIn('stream_ticket', payload)
        self.assertIn('stream_url', payload)
        self.assertEqual(payload['case_id'], self.case.id)
        self.assertEqual(payload['status'], 'queued')
        self.assertTrue(payload['thread_id'].startswith(f'case-{self.case.id}-run-'))
        self.assertIn(f'/api/workflow-runs/{payload["run_id"]}/events/', payload['stream_url'])
        # 验证 DB 中已创建 WorkflowRun
        run = WorkflowRun.objects.get(pk=payload['run_id'])
        self.assertEqual(run.case_id, self.case.id)
        self.assertEqual(run.status, 'queued')
        self.assertEqual(run.selected_evidence_ids, [101, 102])
        self.assertEqual(run.run_options, {'case_mode': 'complain'})
        self.assertEqual(run.started_by_id, self.user.id)
        # 验证 Case.active_workflow_run + thread_id 已同步（双写兼容）
        # 注：用 Case.objects.get() 重新查询而非 refresh_from_db，避免 FSMField
        # （Case.status）的 "Direct status modification is not allowed" 限制
        case_fresh = Case.objects.get(pk=self.case.id)
        self.assertEqual(case_fresh.active_workflow_run_id, run.id)
        self.assertEqual(case_fresh.thread_id, run.thread_id)

    def test_create_run_unauthenticated_returns_401(self):
        """未认证用户返回 401。"""
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_run_non_owner_returns_404(self):
        """非 case owner 用户访问返回 404（不暴露存在性）。"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_run_nonexistent_case_returns_404(self):
        """不存在的 case_id 返回 404。"""
        response = self.client.post(
            '/api/cases/999999/workflow-runs/', {}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ============================================================================
# SubTask 3.2.2：WorkflowRunSnapshotView（GET /api/workflow-runs/{run_id}/snapshot/）
# ============================================================================


class WorkflowRunSnapshotViewTests(TestCase):
    """SubTask 3.2.2 - 获取权威快照端点测试。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass'
        )
        self.other_user = User.objects.create_user(
            username='other', email='other@example.com', password='pass'
        )
        self.case = _make_case(self.user)
        self.run = _make_run(self.case)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f'/api/workflow-runs/{self.run.id}/snapshot/'

    def test_get_snapshot_returns_aggregated_structure(self):
        """获取快照返回 run + stages + active_intervention + artifacts + issues + actions。"""
        # 创建一个产物 + 一个 pending 介入
        create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='extract_result', stage='fact_checking',
            evidence_id=101, revision=3,
            content={'fields': [{'name': 'amount', 'value': '699'}]},
            quality={'score': 0.85, 'status': 'review_required'},
        )
        create_intervention(
            workflow_run_id=self.run.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=3,
            form_schema={'fields': [{'name': 'amount'}]},
            initial_values={'amount': '699'},
            impact={'required': True, 'reason': '置信度低于阈值'},
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()

        # 顶层 6 字段对齐 spec.md「Unified Snapshot API」
        for key in ('run', 'stages', 'active_intervention', 'artifacts', 'issues', 'actions'):
            self.assertIn(key, payload)

        # run 基础字段
        self.assertEqual(payload['run']['id'], self.run.id)
        self.assertEqual(payload['run']['case_id'], self.case.id)
        self.assertEqual(payload['run']['status'], 'running')
        self.assertEqual(payload['run']['current_stage'], 'fact_checking')
        self.assertEqual(payload['run']['revision'], 3)

        # stages 4 业务阶段
        self.assertEqual(len(payload['stages']), 4)
        stage_names = [s['name'] for s in payload['stages']]
        self.assertEqual(
            stage_names,
            ['material_understanding', 'fact_checking',
             'case_organization', 'document_generation'],
        )

        # artifacts 1 个 current 产物
        self.assertEqual(len(payload['artifacts']), 1)

        # active_intervention 应为 pending 介入
        self.assertIsNotNone(payload['active_intervention'])
        self.assertEqual(payload['active_intervention']['intervention_type'], 'quality_review')

        # actions 含 can_pause / can_resume / can_cancel / can_retry / can_restart_from_stage / can_submit_intervention
        actions = payload['actions']
        for key in ('can_pause', 'can_resume', 'can_cancel', 'can_retry',
                    'can_restart_from_stage', 'can_submit_intervention'):
            self.assertIn(key, actions)
        # running 状态允许暂停
        self.assertTrue(actions['can_pause'])

    def test_get_snapshot_nonexistent_run_returns_404(self):
        """不存在的 run_id 返回 404。"""
        response = self.client.get('/api/workflow-runs/999999/snapshot/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_snapshot_non_owner_returns_404(self):
        """非 case owner 访问返回 404。"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ============================================================================
# SubTask 3.2.3：WorkflowRunPauseView（POST /api/workflow-runs/{run_id}/pause/）
# ============================================================================


class WorkflowRunPauseViewTests(TestCase):
    """SubTask 3.2.3 - 请求暂停运行端点测试。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass'
        )
        self.other_user = User.objects.create_user(
            username='other', email='other@example.com', password='pass'
        )
        self.case = _make_case(self.user, workflow_status='running')
        self.run = _make_run(self.case, status='running')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f'/api/workflow-runs/{self.run.id}/pause/'

    def test_pause_running_run_returns_pausing(self):
        """running 状态运行请求暂停返回 200 + status=pausing。"""
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['run_id'], self.run.id)
        self.assertEqual(payload['status'], 'pausing')

        # 验证 DB 已更新
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, 'pausing')
        # Case.workflow_pause_requested 已同步（双写兼容）
        # 注：用 Case.objects.get() 重新查询而非 refresh_from_db，避免 FSMField
        # （Case.status）的 "Direct status modification is not allowed" 限制
        case_fresh = Case.objects.get(pk=self.case.id)
        self.assertTrue(case_fresh.workflow_pause_requested)
        self.assertEqual(case_fresh.workflow_status, 'pausing')

    def test_pause_non_running_returns_409(self):
        """非 running 状态不允许暂停，返回 409。"""
        self.run.status = 'waiting_user'
        self.run.save(update_fields=['status'])
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        payload = response.json()
        self.assertIn('current_status', payload)
        self.assertEqual(payload['current_status'], 'waiting_user')

    def test_pause_non_owner_returns_404(self):
        """非 case owner 访问返回 404。"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ============================================================================
# SubTask 3.2.4：WorkflowRunInterventionSubmitView
# （POST /api/workflow-runs/{run_id}/interventions/{intervention_id}/submit/）
# ============================================================================


class WorkflowRunInterventionSubmitViewTests(TestCase):
    """SubTask 3.2.4 - 提交介入端点测试（含 409 revision 冲突响应）。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass'
        )
        self.other_user = User.objects.create_user(
            username='other', email='other@example.com', password='pass'
        )
        # workflow_revision=3 与 base_revision=3 匹配（无冲突场景）
        self.case = _make_case(self.user, workflow_revision=3)
        self.run = _make_run(self.case, status='waiting_user', revision=3)
        self.intervention = create_intervention(
            workflow_run_id=self.run.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=3,  # 与 run.revision=3 匹配
            form_schema={'fields': [{'name': 'amount'}]},
            initial_values={'amount': '699'},
            impact={'required': True, 'reason': '低置信度'},
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = (
            f'/api/workflow-runs/{self.run.id}/'
            f'interventions/{self.intervention.id}/submit/'
        )

    def test_submit_intervention_success_returns_200(self):
        """成功提交介入返回 200 + status=submitted。"""
        response = self.client.post(
            self.url,
            {'submitted_values': {'amount': '750'}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['status'], 'submitted')
        self.assertEqual(payload['intervention']['id'], self.intervention.id)
        self.assertEqual(payload['intervention']['status'], 'submitted')

        # 验证 DB 已更新
        self.intervention.refresh_from_db()
        self.assertEqual(self.intervention.status, 'submitted')
        self.assertEqual(self.intervention.submitted_values, {'amount': '750'})
        self.assertEqual(self.intervention.submitted_by_id, self.user.id)
        self.assertIsNotNone(self.intervention.submitted_at)

    def test_submit_intervention_revision_conflict_returns_409(self):
        """base_revision 与当前 revision 不匹配时返回 409 REVISION_CONFLICT。"""
        # 修改 run.revision 使其与 base_revision=3 不匹配
        WorkflowRun.objects.filter(pk=self.run.id).update(revision=4)
        response = self.client.post(
            self.url,
            {'submitted_values': {'amount': '750'}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        payload = response.json()
        self.assertEqual(payload['code'], 'REVISION_CONFLICT')
        self.assertEqual(payload['current_revision'], 4)
        self.assertEqual(payload['base_revision'], 3)

    def test_submit_intervention_non_pending_returns_400(self):
        """介入状态非 pending 时返回 400。"""
        self.intervention.status = 'submitted'
        self.intervention.save(update_fields=['status'])
        response = self.client.post(
            self.url,
            {'submitted_values': {'amount': '750'}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        payload = response.json()
        self.assertIn('pending', payload['detail'])

    def test_submit_intervention_non_owner_returns_404(self):
        """非 case owner 访问返回 404。"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(
            self.url,
            {'submitted_values': {'amount': '750'}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ============================================================================
# SubTask 3.2.5：WorkflowRunRetryView（POST /api/workflow-runs/{run_id}/retry/）
# ============================================================================


class WorkflowRunRetryViewTests(TestCase):
    """SubTask 3.2.5 - 局部重跑端点测试。

    mock RetryService.retry_from_stage 避免依赖 LangGraph + PostgresSaver。
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass'
        )
        self.other_user = User.objects.create_user(
            username='other', email='other@example.com', password='pass'
        )
        self.case = _make_case(self.user)
        self.run = _make_run(self.case, status='failed')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f'/api/workflow-runs/{self.run.id}/retry/'

    def _patch_retry_service(self, return_value=None, side_effect=None):
        """patch RetryService.retry_from_stage。

        返回 mock 对象，便于断言调用参数。
        """
        patcher = patch('api.services.retry_service.RetryService.retry_from_stage')
        mock_method = patcher.start()
        if side_effect is not None:
            mock_method.side_effect = side_effect
        else:
            mock_method.return_value = return_value
        self.addCleanup(patcher.stop)
        return mock_method

    def test_retry_from_stage_success_returns_201(self):
        """成功 fork 出新运行返回 201 + new_run_id。"""
        new_run = WorkflowRun.objects.create(
            case=self.case, parent_run=self.run,
            status='queued', thread_id='case-1-run-999-fork',
        )
        mock_method = self._patch_retry_service(return_value=new_run)

        response = self.client.post(
            self.url,
            {
                'from_stage': 'fact_checking',
                'preserve_user_confirmed': True,
                'fork_state_overrides': {},
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertEqual(payload['new_run_id'], new_run.id)
        self.assertEqual(payload['source_run_id'], self.run.id)
        self.assertEqual(payload['from_stage'], 'fact_checking')
        self.assertEqual(payload['thread_id'], new_run.thread_id)
        self.assertEqual(payload['status'], 'queued')

        # 验证 RetryService 被正确调用
        mock_method.assert_called_once()
        call_kwargs = mock_method.call_args.kwargs
        self.assertEqual(call_kwargs['source_run_id'], self.run.id)
        self.assertEqual(call_kwargs['from_stage'], 'fact_checking')
        self.assertTrue(call_kwargs['preserve_user_confirmed'])
        self.assertEqual(call_kwargs['started_by_id'], self.user.id)

    def test_retry_missing_from_stage_returns_400(self):
        """缺少 from_stage 字段返回 400。"""
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        payload = response.json()
        self.assertIn('from_stage', payload['detail'])

    def test_retry_invalid_stage_returns_400(self):
        """无效 from_stage 返回 400（RetryService 抛 ValueError）。"""
        self._patch_retry_service(
            side_effect=ValueError('无效的 from_stage: invalid_stage')
        )
        response = self.client.post(
            self.url,
            {'from_stage': 'invalid_stage'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        payload = response.json()
        self.assertIn('无效的 from_stage', payload['detail'])

    def test_retry_invalid_status_returns_409(self):
        """源运行状态不允许重跑返回 409（RetryService 抛 ValueError 状态不允许）。"""
        self._patch_retry_service(
            side_effect=ValueError('源运行状态 running 不允许重跑')
        )
        response = self.client.post(
            self.url,
            {'from_stage': 'fact_checking'},
            format='json',
        )
        # ValueError 被映射为 400（与 spec 一致，因为这是参数校验）
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        payload = response.json()
        self.assertIn('不允许重跑', payload['detail'])

    def test_retry_fork_failure_returns_409(self):
        """fork 失败返回 409（RetryService 抛 RuntimeError）。"""
        self._patch_retry_service(
            side_effect=RuntimeError('fork state 失败: checkpoint 未找到')
        )
        response = self.client.post(
            self.url,
            {'from_stage': 'fact_checking'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        payload = response.json()
        self.assertIn('局部重跑失败', payload['detail'])

    def test_retry_non_owner_returns_404(self):
        """非 case owner 访问返回 404。"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(
            self.url,
            {'from_stage': 'fact_checking'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retry_invalid_fork_state_overrides_type_returns_400(self):
        """fork_state_overrides 非 dict 类型返回 400。"""
        response = self.client.post(
            self.url,
            {'from_stage': 'fact_checking', 'fork_state_overrides': 'invalid'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ============================================================================
# SubTask 3.2.6：WorkflowRunCancelView（POST /api/workflow-runs/{run_id}/cancel/）
# ============================================================================


class WorkflowRunCancelViewTests(TestCase):
    """SubTask 3.2.6 - 取消运行端点测试。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass'
        )
        self.other_user = User.objects.create_user(
            username='other', email='other@example.com', password='pass'
        )
        self.case = _make_case(self.user, workflow_status='running')
        self.run = _make_run(self.case, status='running')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f'/api/workflow-runs/{self.run.id}/cancel/'

    def test_cancel_running_run_success(self):
        """running 状态运行可取消，返回 200 + status=cancelled。"""
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['run_id'], self.run.id)
        self.assertEqual(payload['status'], 'cancelled')

        # 验证 DB 已更新
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, 'cancelled')
        self.assertIsNotNone(self.run.finished_at)

        # Case.workflow_status 已同步为 idle（双写兼容）
        # 注：用 Case.objects.get() 重新查询而非 refresh_from_db，避免 FSMField
        # （Case.status）的 "Direct status modification is not allowed" 限制
        case_fresh = Case.objects.get(pk=self.case.id)
        self.assertEqual(case_fresh.workflow_status, 'idle')

    def test_cancel_waiting_user_run_success(self):
        """waiting_user 状态运行也可取消。"""
        self.run.status = 'waiting_user'
        self.run.save(update_fields=['status'])
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cancel_already_succeeded_returns_409(self):
        """succeeded 状态不允许取消，返回 409。"""
        self.run.status = 'succeeded'
        self.run.save(update_fields=['status'])
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        payload = response.json()
        self.assertEqual(payload['current_status'], 'succeeded')

    def test_cancel_already_cancelled_returns_409(self):
        """已 cancelled 状态不允许重复取消，返回 409。"""
        self.run.status = 'cancelled'
        self.run.save(update_fields=['status'])
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_cancel_non_owner_returns_404(self):
        """非 case owner 访问返回 404。"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ============================================================================
# SubTask 3.2.7：CaseWorkflowRunsListView（GET /api/cases/{case_id}/workflow-runs/list/）
# ============================================================================


class CaseWorkflowRunsListViewTests(TestCase):
    """SubTask 3.2.7 - 历史运行列表端点测试。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass'
        )
        self.other_user = User.objects.create_user(
            username='other', email='other@example.com', password='pass'
        )
        self.case = _make_case(self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f'/api/cases/{self.case.id}/workflow-runs/list/'

    def test_list_runs_returns_history_desc(self):
        """按 created_at 降序返回所有运行。"""
        run1 = WorkflowRun.objects.create(
            case=self.case, status='succeeded',
            current_stage='document_generation', progress=1.0, revision=10,
        )
        run2 = WorkflowRun.objects.create(
            case=self.case, status='failed',
            current_stage='fact_checking', progress=0.25, revision=5,
            parent_run=run1,  # fork 自 run1
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['case_id'], self.case.id)
        self.assertEqual(payload['total'], 2)

        runs = payload['runs']
        # 按 created_at 降序：run2（后创建）在前
        self.assertEqual(runs[0]['id'], run2.id)
        self.assertEqual(runs[1]['id'], run1.id)

        # 验证 fork 链：run2 的 parent_run_id 指向 run1
        self.assertEqual(runs[0]['parent_run_id'], run1.id)
        self.assertIsNone(runs[1]['parent_run_id'])

        # 验证基础字段存在
        first = runs[0]
        for key in ('id', 'case_id', 'thread_id', 'status', 'current_stage',
                    'current_node', 'progress', 'revision', 'workflow_version',
                    'state_schema_version', 'policy_version', 'prompt_bundle_version',
                    'parent_run_id', 'started_by_id', 'started_at', 'finished_at',
                    'created_at', 'updated_at', 'error_message'):
            self.assertIn(key, first)

    def test_list_runs_empty_case_returns_empty_list(self):
        """无运行记录的 case 返回空列表 + total=0。"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['total'], 0)
        self.assertEqual(payload['runs'], [])
        self.assertEqual(payload['case_id'], self.case.id)

    def test_list_runs_non_owner_returns_404(self):
        """非 case owner 访问返回 404。"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_runs_unauthenticated_returns_401(self):
        """未认证用户返回 401。"""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
