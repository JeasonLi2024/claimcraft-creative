# -*- coding: utf-8 -*-
"""Task 3.3 测试：RetryService（基于 LangGraph Time Travel）。

测试覆盖：
1. RetryServiceValidationTests：参数校验（源运行状态 / from_stage 有效性）
2. RetryServiceHelperTests：辅助方法（_get_downstream_list_fields /
   _get_stage_base_progress / _get_downstream_artifact_ids）
3. RetryServiceForkTests：fork 创建新 WorkflowRun + 标记 stale + 更新 active_run
   （mock WorkflowRunner.start_in_background + mark_artifacts_stale，
   不实际启动 graph）
4. RetryServiceTimeTravelTests：验证 LangGraph Time Travel 交互
   （mock build_case_workflow，验证 aget_state_history + aupdate_state 调用）

测试使用 Django TestCase（SQLite）+ MagicMock / AsyncMock 模拟 LangGraph workflow，
不依赖真实 PostgresSaver。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import TestCase

from api.agents.artifact_service import create_artifact
from api.models import Case, WorkflowArtifact, WorkflowRun
from api.services.retry_service import (
    STAGE_TO_LAST_NODE,
    RetryService,
)


def _make_case(user=None, **kwargs):
    """测试辅助：创建一个最小 Case。"""
    return Case.objects.create(
        title=kwargs.pop('title', '测试案件'),
        owner=user,
        **kwargs,
    )


class RetryServiceValidationTests(TestCase):
    """RetryService 参数校验测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)
        self.service = RetryService()

    def test_retry_from_stage_raises_on_nonexistent_source_run(self):
        """源运行不存在时抛 WorkflowRun.DoesNotExist。"""
        with self.assertRaises(WorkflowRun.DoesNotExist):
            async_to_sync(self.service.retry_from_stage)(
                source_run_id=999999,
                from_stage='fact_checking',
            )

    def test_retry_from_stage_validates_source_run_status(self):
        """源运行状态非 failed/succeeded/waiting_user 时抛 ValueError。"""
        # status=running 不允许重跑
        run = WorkflowRun.objects.create(
            case=self.case, status='running',
        )
        with self.assertRaises(ValueError) as ctx:
            async_to_sync(self.service.retry_from_stage)(
                source_run_id=run.id,
                from_stage='fact_checking',
            )
        self.assertIn('不允许重跑', str(ctx.exception))

    def test_retry_from_stage_validates_from_stage(self):
        """无效 from_stage 抛 ValueError。"""
        run = WorkflowRun.objects.create(
            case=self.case, status='failed',
        )
        with self.assertRaises(ValueError) as ctx:
            async_to_sync(self.service.retry_from_stage)(
                source_run_id=run.id,
                from_stage='invalid_stage',
            )
        self.assertIn('无效的 from_stage', str(ctx.exception))

    def test_retry_from_stage_allows_succeeded_status(self):
        """status=succeeded 允许重跑（应通过校验进入 graph 阶段）。"""
        run = WorkflowRun.objects.create(
            case=self.case, status='succeeded',
            thread_id='case-{}-run-{}'.format(self.case.id, 0),  # 占位 thread_id
        )
        # 因 graph 未 mock 会抛 RuntimeError，但校验已通过
        with self.assertRaises(RuntimeError):
            async_to_sync(self.service.retry_from_stage)(
                source_run_id=run.id,
                from_stage='fact_checking',
            )

    def test_retry_from_stage_allows_waiting_user_status(self):
        """status=waiting_user 允许重跑。"""
        run = WorkflowRun.objects.create(
            case=self.case, status='waiting_user',
        )
        with self.assertRaises(RuntimeError):  # graph 未 mock
            async_to_sync(self.service.retry_from_stage)(
                source_run_id=run.id,
                from_stage='material_understanding',
            )


class RetryServiceHelperTests(TestCase):
    """RetryService 辅助方法测试（不触发 graph）。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)
        self.run = WorkflowRun.objects.create(case=self.case, status='failed')
        self.service = RetryService()

    def test_get_downstream_list_fields_includes_future_stages(self):
        """from_stage=fact_checking 时聚合 fact_checking + 之后阶段的字段。"""
        # fact_checking: evidence_extract_results / errors / warnings / issues / provenance
        # case_organization: evidence_chain / evidence_chain_tool_calls
        # document_generation: complaint_tool_calls
        fields = self.service._get_downstream_list_fields('fact_checking')
        self.assertIn('evidence_extract_results', fields)
        self.assertIn('errors', fields)
        self.assertIn('warnings', fields)
        self.assertIn('issues', fields)
        self.assertIn('provenance', fields)
        self.assertIn('evidence_chain', fields)
        self.assertIn('evidence_chain_tool_calls', fields)
        self.assertIn('complaint_tool_calls', fields)
        # 不应包含 material_understanding 的字段
        self.assertNotIn('evidence_preclassify_results', fields)
        self.assertNotIn('evidence_ocr_results', fields)
        self.assertNotIn('evidence_classify_results', fields)

    def test_get_downstream_list_fields_includes_all_for_first_stage(self):
        """from_stage=material_understanding 时聚合所有阶段字段。"""
        fields = self.service._get_downstream_list_fields('material_understanding')
        self.assertIn('evidence_preclassify_results', fields)
        self.assertIn('evidence_ocr_results', fields)
        self.assertIn('evidence_classify_results', fields)
        self.assertIn('evidence_extract_results', fields)
        self.assertIn('evidence_chain', fields)
        self.assertIn('complaint_tool_calls', fields)

    def test_get_downstream_list_fields_invalid_stage_returns_empty(self):
        """无效 from_stage 返回空列表。"""
        self.assertEqual(
            self.service._get_downstream_list_fields('invalid'), []
        )

    def test_get_stage_base_progress_returns_correct_value(self):
        """4 阶段基础进度：0.0 / 0.25 / 0.5 / 0.75。"""
        self.assertEqual(
            self.service._get_stage_base_progress('material_understanding'), 0.0
        )
        self.assertEqual(
            self.service._get_stage_base_progress('fact_checking'), 0.25
        )
        self.assertEqual(
            self.service._get_stage_base_progress('case_organization'), 0.5
        )
        self.assertEqual(
            self.service._get_stage_base_progress('document_generation'), 0.75
        )
        # 无效 stage 默认 0.0
        self.assertEqual(
            self.service._get_stage_base_progress('invalid'), 0.0
        )

    def test_get_downstream_artifact_ids_filters_current_status(self):
        """仅返回 current 状态的下游 artifact IDs。"""
        # 创建一些 current 产物
        create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='extract_result', stage='fact_checking',
            evidence_id=101,
        )
        create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='evidence_chain', stage='case_organization',
        )
        # 创建一个 superseded 产物（不应被返回）
        superseded = create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='complaint_draft', stage='document_generation',
        )
        WorkflowArtifact.objects.filter(pk=superseded.id).update(status='superseded')

        # from_stage=fact_checking：下游 = fact_checking + case_organization + document_generation
        ids = self.service._get_downstream_artifact_ids(
            self.run.id, 'fact_checking'
        )
        # 应有 2 个 current（extract_result + evidence_chain），不含 superseded 的 complaint_draft
        self.assertEqual(len(ids), 2)

    def test_get_downstream_artifact_ids_includes_from_stage(self):
        """下游包含 from_stage 本身的产物。"""
        create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='extract_result', stage='fact_checking',
            evidence_id=201,
        )
        ids = self.service._get_downstream_artifact_ids(
            self.run.id, 'fact_checking'
        )
        self.assertEqual(len(ids), 1)

    def test_stage_to_last_node_map_complete(self):
        """STAGE_TO_LAST_NODE 包含 4 业务阶段。"""
        self.assertEqual(len(STAGE_TO_LAST_NODE), 4)
        self.assertIn('material_understanding', STAGE_TO_LAST_NODE)
        self.assertIn('fact_checking', STAGE_TO_LAST_NODE)
        self.assertIn('case_organization', STAGE_TO_LAST_NODE)
        self.assertIn('document_generation', STAGE_TO_LAST_NODE)
        # 与 graph.py 节点顺序对齐
        self.assertEqual(STAGE_TO_LAST_NODE['material_understanding'], 'classify')
        self.assertEqual(STAGE_TO_LAST_NODE['fact_checking'], 'review')
        self.assertEqual(STAGE_TO_LAST_NODE['case_organization'], 'evidence_chain')
        self.assertEqual(STAGE_TO_LAST_NODE['document_generation'], 'complaint')


class RetryServiceForkTests(TestCase):
    """RetryService fork 流程测试（mock WorkflowRunner + mark_artifacts_stale）。

    本测试组 mock build_case_workflow，模拟 LangGraph Time Travel 的
    aget_state_history + aupdate_state 调用，验证：
    - 创建新 WorkflowRun，parent_run 指向源 run
    - 下游 artifact 标记为 stale
    - Case.active_workflow_run 指向新 run
    - WorkflowRunner.start_in_background 被正确调用（含 fork_config 参数）
    """

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)
        self.source_run = WorkflowRun.objects.create(
            case=self.case,
            status='failed',
            current_stage='document_generation',
            current_node='complaint',
            progress=0.80,
            revision=10,
        )
        # 下游产物（fact_checking + case_organization + document_generation 各 1 个 current）
        create_artifact(
            workflow_run_id=self.source_run.id, case_id=self.case.id,
            artifact_type='extract_result', stage='fact_checking',
            evidence_id=301,
        )
        create_artifact(
            workflow_run_id=self.source_run.id, case_id=self.case.id,
            artifact_type='evidence_chain', stage='case_organization',
        )
        create_artifact(
            workflow_run_id=self.source_run.id, case_id=self.case.id,
            artifact_type='complaint_draft', stage='document_generation',
        )
        self.service = RetryService()

    def _build_mock_workflow(self, target_node='review', fork_thread_id=None):
        """构造 mock workflow：aget_state_history 返回含 target_node 的 checkpoint。"""
        mock_workflow = MagicMock()

        # 构造 state_history 异步迭代器：3 个 checkpoint，第 2 个 current_node=target_node
        target_state = MagicMock()
        target_state.values = {
            'current_node': target_node,
            'revision': 5,
        }
        target_state.config = {
            "configurable": {
                "thread_id": self.source_run.thread_id,
                "checkpoint_id": "target-checkpoint-id",
            }
        }

        other_state_1 = MagicMock()
        other_state_1.values = {'current_node': 'evidence_chain', 'revision': 7}

        other_state_2 = MagicMock()
        other_state_2.values = {'current_node': 'complaint', 'revision': 10}

        async def _fake_history(config):
            # 顺序与实际不同：target_state 在中间
            yield other_state_2
            yield target_state
            yield other_state_1

        mock_workflow.aget_state_history = MagicMock(return_value=_fake_history(None))

        # aupdate_state 返回 fork_config（含新 thread_id）
        actual_fork_thread = fork_thread_id or (
            f"case-{self.case.id}-fork-{self.source_run.id}"
        )
        fork_config = {
            "configurable": {
                "thread_id": actual_fork_thread,
                "checkpoint_id": "fork-checkpoint-id",
            }
        }
        mock_workflow.aupdate_state = AsyncMock(return_value=fork_config)
        return mock_workflow

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_creates_new_workflow_run_with_parent_run(
        self, mock_start, mock_build
    ):
        """创建新 WorkflowRun，parent_run 指向源 run。"""
        mock_build.return_value = self._build_mock_workflow(
            target_node='review', fork_thread_id=None,
        )

        new_run = async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
        )

        self.assertIsNotNone(new_run)
        self.assertEqual(new_run.parent_run_id, self.source_run.id)
        self.assertEqual(new_run.case_id, self.case.id)
        # 版本字段继承自源 run
        self.assertEqual(
            new_run.workflow_version, self.source_run.workflow_version
        )
        self.assertEqual(
            new_run.state_schema_version, self.source_run.state_schema_version
        )
        # 启动配置继承
        self.assertEqual(
            new_run.selected_evidence_ids, self.source_run.selected_evidence_ids
        )
        self.assertEqual(new_run.run_options, self.source_run.run_options)

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_marks_downstream_artifacts_stale(
        self, mock_start, mock_build
    ):
        """下游 artifact 标记为 stale。"""
        mock_build.return_value = self._build_mock_workflow(
            target_node='review',
        )

        async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
        )

        # 源运行的 3 个 current artifact 应全部变为 stale
        # （fact_checking + case_organization + document_generation 都在 fact_checking 下游）
        remaining_current = WorkflowArtifact.objects.filter(
            workflow_run_id=self.source_run.id, status='current'
        ).count()
        self.assertEqual(remaining_current, 0)

        stale_count = WorkflowArtifact.objects.filter(
            workflow_run_id=self.source_run.id, status='stale'
        ).count()
        self.assertEqual(stale_count, 3)

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_updates_case_active_workflow_run(
        self, mock_start, mock_build
    ):
        """Case.active_workflow_run 指向新 run。"""
        mock_build.return_value = self._build_mock_workflow(
            target_node='review',
        )

        new_run = async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
        )

        # 注意：Case.status 是 django_fsm FSMField（protected=True），
        # refresh_from_db() 会触发 setter 保护（"Direct status modification is not allowed"）。
        # 改为重新查询获得全新实例，避免触发 FSMField 的状态保护。
        fresh_case = Case.objects.get(pk=self.case.id)
        self.assertEqual(fresh_case.active_workflow_run_id, new_run.id)

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_invokes_workflow_runner_with_fork_config(
        self, mock_start, mock_build
    ):
        """WorkflowRunner.start_in_background 被调用，且 fork_config 参数非空。"""
        fork_thread_id = f"case-{self.case.id}-fork-{self.source_run.id}-xxx"
        mock_build.return_value = self._build_mock_workflow(
            target_node='review', fork_thread_id=fork_thread_id,
        )

        new_run = async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
        )

        mock_start.assert_called_once()
        call_kwargs = mock_start.call_args.kwargs
        self.assertIn('fork_config', call_kwargs)
        self.assertIsNotNone(call_kwargs['fork_config'])
        # fork_config 应含 fork_thread_id
        self.assertEqual(
            call_kwargs['fork_config'].get('configurable', {}).get('thread_id'),
            fork_thread_id,
        )
        # initial_state / resume 应为 None
        self.assertIsNone(call_kwargs.get('initial_state'))
        self.assertIsNone(call_kwargs.get('resume'))
        # thread_id 参数应为新 run 的 thread_id（已回写为 fork_thread_id）
        self.assertEqual(call_kwargs['thread_id'], new_run.thread_id)
        self.assertEqual(new_run.thread_id, fork_thread_id)

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_overwrites_new_run_thread_id_with_fork_thread_id(
        self, mock_start, mock_build
    ):
        """新 WorkflowRun.thread_id 被回写为 fork_config 中的 thread_id。"""
        fork_thread_id = f"case-{self.case.id}-fork-thread-xyz"
        mock_build.return_value = self._build_mock_workflow(
            target_node='review', fork_thread_id=fork_thread_id,
        )

        new_run = async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
        )

        # new_run.thread_id 应被覆盖为 fork_thread_id
        self.assertEqual(new_run.thread_id, fork_thread_id)
        # DB 中也应同步
        new_run.refresh_from_db()
        self.assertEqual(new_run.thread_id, fork_thread_id)


class RetryServiceTimeTravelTests(TestCase):
    """RetryService LangGraph Time Travel 交互测试（mock graph）。

    验证 retry_from_stage 调用：
    - graph.aget_state_history(source_config) 获取历史 checkpoint
    - graph.aupdate_state(target.config, fork_state, as_node=target_node) fork
    - fork_state 中列表字段使用 Overwrite 包装
    """

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)
        self.source_run = WorkflowRun.objects.create(
            case=self.case, status='failed',
            current_stage='document_generation',
            current_node='complaint',
            progress=0.80,
            revision=10,
        )
        self.service = RetryService()

    def _build_mock_workflow_with_states(self, states):
        """构造 mock workflow：aget_state_history 返回指定 states 列表。"""
        mock_workflow = MagicMock()

        async def _fake_history(config):
            for s in states:
                yield s

        mock_workflow.aget_state_history = MagicMock(return_value=_fake_history(None))

        fork_config = {
            "configurable": {
                "thread_id": f"case-{self.case.id}-fork-{self.source_run.id}",
                "checkpoint_id": "fork-checkpoint-id",
            }
        }
        mock_workflow.aupdate_state = AsyncMock(return_value=fork_config)
        return mock_workflow

    def _make_state(self, current_node, revision):
        """构造 mock state 对象。"""
        state = MagicMock()
        state.values = {'current_node': current_node, 'revision': revision}
        state.config = {
            "configurable": {
                "thread_id": self.source_run.thread_id,
                "checkpoint_id": f"cp-{current_node}-{revision}",
            }
        }
        return state

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_invokes_aget_state_history(self, mock_start, mock_build):
        """验证 retry 调用 aget_state_history。"""
        target = self._make_state('review', revision=5)
        other = self._make_state('complaint', revision=10)
        mock_workflow = self._build_mock_workflow_with_states([other, target])
        mock_build.return_value = mock_workflow

        async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',  # target_node = 'review'
        )

        mock_workflow.aget_state_history.assert_called_once()
        call_args = mock_workflow.aget_state_history.call_args
        # 第一个位置参数应为 source_config
        source_config = call_args.args[0]
        self.assertEqual(
            source_config.get('configurable', {}).get('thread_id'),
            self.source_run.thread_id,
        )

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_invokes_aupdate_state_with_correct_config(
        self, mock_start, mock_build
    ):
        """验证 aupdate_state 使用 target_checkpoint.config 调用。"""
        target = self._make_state('review', revision=5)
        other = self._make_state('complaint', revision=10)
        mock_workflow = self._build_mock_workflow_with_states([other, target])
        mock_build.return_value = mock_workflow

        async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
        )

        mock_workflow.aupdate_state.assert_called_once()
        call_args = mock_workflow.aupdate_state.call_args
        # 第一个位置参数应为 target_checkpoint.config
        first_arg = call_args.args[0]
        self.assertEqual(first_arg, target.config)
        # as_node 关键字参数应为 target_node（'review'）
        self.assertEqual(call_args.kwargs.get('as_node'), 'review')

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_fork_state_uses_overwrite_for_list_fields(
        self, mock_start, mock_build
    ):
        """fork_state 中列表字段使用 Overwrite 包装（避免 reducer 追加）。"""
        try:
            from langgraph.types import Overwrite
        except ImportError:  # pragma: no cover
            self.skipTest("langgraph 未安装，跳过 Overwrite 验证")

        target = self._make_state('review', revision=5)
        mock_workflow = self._build_mock_workflow_with_states([target])
        mock_build.return_value = mock_workflow

        async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
        )

        mock_workflow.aupdate_state.assert_called_once()
        fork_state = mock_workflow.aupdate_state.call_args.args[1]

        # 下游 list 字段应使用 Overwrite([])
        expected_list_fields = self.service._get_downstream_list_fields('fact_checking')
        for field in expected_list_fields:
            self.assertIn(field, fork_state)
            self.assertIsInstance(
                fork_state[field], Overwrite,
                f"字段 {field} 应使用 Overwrite 包装（避免 reducer 追加）"
            )

        # stale_artifact_ids 也应使用 Overwrite
        self.assertIn('stale_artifact_ids', fork_state)
        self.assertIsInstance(fork_state['stale_artifact_ids'], Overwrite)

        # 标量字段应为普通值（非 Overwrite）
        self.assertEqual(fork_state['current_stage'], 'fact_checking')
        self.assertEqual(fork_state['current_node'], '')
        self.assertEqual(fork_state['revision'], 5)
        self.assertEqual(fork_state['progress'], 0.25)

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_preserve_user_confirmed_keeps_field(
        self, mock_start, mock_build
    ):
        """preserve_user_confirmed=True 时不传 user_confirmed_fields 到 fork_state。"""
        try:
            from langgraph.types import Overwrite
        except ImportError:  # pragma: no cover
            self.skipTest("langgraph 未安装")

        target = self._make_state('review', revision=5)
        mock_workflow = self._build_mock_workflow_with_states([target])
        mock_build.return_value = mock_workflow

        async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
            preserve_user_confirmed=True,
        )

        fork_state = mock_workflow.aupdate_state.call_args.args[1]
        # 不应包含 user_confirmed_fields（保留原值）
        self.assertNotIn('user_confirmed_fields', fork_state)

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_not_preserve_user_confirmed_overwrites_field(
        self, mock_start, mock_build
    ):
        """preserve_user_confirmed=False 时 user_confirmed_fields 使用 Overwrite({}) 清空。"""
        try:
            from langgraph.types import Overwrite
        except ImportError:  # pragma: no cover
            self.skipTest("langgraph 未安装")

        target = self._make_state('review', revision=5)
        mock_workflow = self._build_mock_workflow_with_states([target])
        mock_build.return_value = mock_workflow

        async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
            preserve_user_confirmed=False,
        )

        fork_state = mock_workflow.aupdate_state.call_args.args[1]
        self.assertIn('user_confirmed_fields', fork_state)
        self.assertIsInstance(fork_state['user_confirmed_fields'], Overwrite)

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_raises_when_checkpoint_not_found(self, mock_start, mock_build):
        """找不到目标 checkpoint 时抛 RuntimeError。"""
        # 仅含 current_node='complaint' 的 checkpoint，但 from_stage=fact_checking
        # 需要 current_node='review' → 找不到
        other = self._make_state('complaint', revision=10)
        mock_workflow = self._build_mock_workflow_with_states([other])
        mock_build.return_value = mock_workflow

        with self.assertRaises(RuntimeError) as ctx:
            async_to_sync(self.service.retry_from_stage)(
                source_run_id=self.source_run.id,
                from_stage='fact_checking',  # target_node='review'
            )
        self.assertIn('未找到', str(ctx.exception))
        self.assertIn('review', str(ctx.exception))

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_fork_state_overrides_applied(self, mock_start, mock_build):
        """fork_state_overrides 中的 list 值被 Overwrite 包装。"""
        try:
            from langgraph.types import Overwrite
        except ImportError:  # pragma: no cover
            self.skipTest("langgraph 未安装")

        target = self._make_state('review', revision=5)
        mock_workflow = self._build_mock_workflow_with_states([target])
        mock_build.return_value = mock_workflow

        async_to_sync(self.service.retry_from_stage)(
            source_run_id=self.source_run.id,
            from_stage='fact_checking',
            fork_state_overrides={
                'evidence_extract_results': [{'evidence_id': 1, 'fields': []}],
                'current_stage': 'fact_checking',
            },
        )

        fork_state = mock_workflow.aupdate_state.call_args.args[1]
        # list 值被 Overwrite 包装
        self.assertIsInstance(
            fork_state['evidence_extract_results'], Overwrite
        )
        # 标量值直接覆盖
        self.assertEqual(fork_state['current_stage'], 'fact_checking')

    @patch('api.services.retry_service.build_case_workflow')
    @patch('api.agents.workflow_runner.WorkflowRunner.start_in_background')
    def test_retry_cleanup_on_fork_failure(self, mock_start, mock_build):
        """aupdate_state 失败时应清理已创建的 WorkflowRun。"""
        target = self._make_state('review', revision=5)
        mock_workflow = self._build_mock_workflow_with_states([target])
        # 让 aupdate_state 抛错
        mock_workflow.aupdate_state = AsyncMock(
            side_effect=RuntimeError("fork failed")
        )
        mock_build.return_value = mock_workflow

        initial_run_count = WorkflowRun.objects.count()
        with self.assertRaises(RuntimeError) as ctx:
            async_to_sync(self.service.retry_from_stage)(
                source_run_id=self.source_run.id,
                from_stage='fact_checking',
            )
        self.assertIn('fork state 失败', str(ctx.exception))

        # 应清理已创建的 WorkflowRun
        self.assertEqual(WorkflowRun.objects.count(), initial_run_count)
