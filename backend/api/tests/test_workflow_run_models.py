# -*- coding: utf-8 -*-
"""Task 3.1 测试：WorkflowRun / WorkflowArtifact 模型 + 介入服务重构 + 产物服务。

覆盖：
1. WorkflowRunTests：模型基础 + thread_id 自动生成 + 版本快照 + 状态转换 + 关联
2. WorkflowArtifactTests：版本自增 + superseded + stale 传播 + 查询
3. WorkflowInterventionRefactorTests：workflow_run 外键 + 兼容回退 + revision 冲突
4. ArtifactServiceTests：artifact_service 接口测试

测试使用 Django TestCase（SQLite，由 settings 在 manage.py test 时自动启用），
对齐 `langgraph-human-in-the-loop` / `langgraph-persistence` skill 要求。
"""
from django.contrib.auth.models import User
from django.test import TestCase

from api.agents.artifact_service import (
    create_artifact,
    get_artifacts_by_run,
    get_artifacts_by_stage,
    mark_artifacts_stale,
)
from api.agents.version import WorkflowVersion
from api.models import Case, WorkflowArtifact, WorkflowIntervention, WorkflowRun
from api.services.intervention_service import (
    RevisionConflictError,
    create_intervention,
    submit_intervention,
)


def _make_case(user=None, **kwargs):
    """测试辅助：创建一个最小 Case。"""
    return Case.objects.create(
        title=kwargs.pop('title', '测试案件'),
        owner=user,
        **kwargs,
    )


class WorkflowRunTests(TestCase):
    """WorkflowRun 模型基础测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)

    def test_create_workflow_run_auto_generates_thread_id(self):
        """创建后 thread_id == f'case-{case_id}-run-{id}'。"""
        run = WorkflowRun.objects.create(case=self.case)
        self.assertEqual(run.thread_id, f'case-{self.case.id}-run-{run.id}')
        self.assertTrue(run.thread_id)

    def test_create_workflow_run_auto_fills_version_snapshot(self):
        """创建后版本字段已自动填充（对齐 WorkflowVersion 常量）。"""
        run = WorkflowRun.objects.create(case=self.case)
        run.refresh_from_db()
        self.assertEqual(run.workflow_version, WorkflowVersion.WORKFLOW_VERSION)
        self.assertEqual(run.state_schema_version, WorkflowVersion.STATE_SCHEMA_VERSION)
        self.assertEqual(run.policy_version, WorkflowVersion.POLICY_VERSION)
        self.assertEqual(run.prompt_bundle_version, WorkflowVersion.PROMPT_BUNDLE_VERSION)

    def test_workflow_run_status_transitions(self):
        """status 从 queued → running → waiting_user → succeeded 顺利转换。"""
        run = WorkflowRun.objects.create(case=self.case)
        # 默认 queued（create 时显式覆盖为 running 由 _create_workflow_run，但测试单独构造 queued）
        run.status = 'queued'
        run.save()
        self.assertEqual(run.status, 'queued')

        run.status = 'running'
        run.save()
        self.assertEqual(run.status, 'running')

        run.status = 'waiting_user'
        run.save()
        self.assertEqual(run.status, 'waiting_user')

        run.status = 'succeeded'
        run.save()
        run.refresh_from_db()
        self.assertEqual(run.status, 'succeeded')

    def test_case_active_workflow_run_fk(self):
        """Case.active_workflow_run 指向当前运行（外键关联）。"""
        run = WorkflowRun.objects.create(case=self.case)
        # 用 update 直接更新 DB，避免 FSMField 状态保护
        Case.objects.filter(pk=self.case.id).update(active_workflow_run=run)
        # 重新查询以避免 FSMField 的 refresh_from_db 限制
        case_fresh = Case.objects.get(pk=self.case.id)
        self.assertEqual(case_fresh.active_workflow_run_id, run.id)
        # 反向关联：run.active_for_cases 应包含此 case
        self.assertIn(case_fresh, run.active_for_cases.all())

    def test_parent_run_for_fork(self):
        """parent_run 指向原运行（Task 3.3 fork 场景）。"""
        parent = WorkflowRun.objects.create(case=self.case)
        child = WorkflowRun.objects.create(case=self.case, parent_run=parent)
        self.assertEqual(child.parent_run_id, parent.id)
        # 反向关联：parent.forked_runs 应包含 child
        self.assertIn(child, parent.forked_runs.all())


class WorkflowArtifactTests(TestCase):
    """WorkflowArtifact 模型 + artifact_service 基础测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)
        self.run = WorkflowRun.objects.create(case=self.case)

    def test_create_artifact_increments_version(self):
        """同类型同证据连续创建 3 次，version=1,2,3。"""
        versions = []
        for _ in range(3):
            art = create_artifact(
                workflow_run_id=self.run.id,
                case_id=self.case.id,
                artifact_type='ocr_result',
                stage='material_understanding',
                node_name='ocr',
                evidence_id=101,
                content={'text': 'hello'},
            )
            versions.append(art.version)
        self.assertEqual(versions, [1, 2, 3])

    def test_create_artifact_marks_previous_superseded(self):
        """创建新版本时旧版本 status='superseded'。"""
        first = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='extract_result',
            stage='fact_checking',
            node_name='extract',
            evidence_id=102,
            content={'fields': []},
        )
        self.assertEqual(first.status, 'current')

        second = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='extract_result',
            stage='fact_checking',
            node_name='extract',
            evidence_id=102,
            content={'fields': [{'name': 'amount'}]},
        )
        self.assertEqual(second.status, 'current')
        self.assertEqual(second.version, 2)

        first.refresh_from_db()
        self.assertEqual(first.status, 'superseded')
        self.assertIsNotNone(first.stale_at)

    def test_mark_artifacts_stale_propagates_downstream(self):
        """上游变更传播到下游 source_refs。"""
        # 构造依赖链：preclassify_result -> ocr_result -> classify_result
        pre = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='preclassify_result',
            stage='material_understanding',
            node_name='preclassify',
            evidence_id=201,
        )
        ocr = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='ocr_result',
            stage='material_understanding',
            node_name='ocr',
            evidence_id=201,
            source_refs=[pre.id],
        )
        classify = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='classify_result',
            stage='material_understanding',
            node_name='classify',
            evidence_id=201,
            source_refs=[ocr.id],
        )

        # 标记 pre 为 stale，应递归传播到 ocr + classify
        marked = mark_artifacts_stale(self.run.id, [pre.id])
        self.assertGreaterEqual(marked, 1)

        pre.refresh_from_db()
        ocr.refresh_from_db()
        classify.refresh_from_db()
        self.assertEqual(pre.status, 'stale')
        self.assertEqual(ocr.status, 'stale')
        self.assertEqual(classify.status, 'stale')

    def test_get_artifacts_by_run_filters_status(self):
        """get_artifacts_by_run(only_current=True) 仅返回 current。"""
        art1 = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='ocr_result',
            stage='material_understanding',
            evidence_id=301,
        )
        # 第二次创建使 art1 变为 superseded
        art2 = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='ocr_result',
            stage='material_understanding',
            evidence_id=301,
        )

        current_only = get_artifacts_by_run(self.run.id, only_current=True)
        self.assertEqual(len(current_only), 1)
        self.assertEqual(current_only[0].id, art2.id)

        all_arts = get_artifacts_by_run(self.run.id, only_current=False)
        self.assertEqual(len(all_arts), 2)
        self.assertIn(art1, all_arts)
        self.assertIn(art2, all_arts)


class WorkflowInterventionRefactorTests(TestCase):
    """Task 3.1 WorkflowIntervention 重构测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user, workflow_revision=1)
        self.run = WorkflowRun.objects.create(case=self.case, revision=1)

    def test_create_intervention_with_workflow_run(self):
        """传入 workflow_run_id 创建介入（Task 3.1 主路径）。"""
        intervention = create_intervention(
            workflow_run_id=self.run.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=1,
            form_schema={'fields': [{'name': 'amount'}]},
            initial_values={'amount': '699'},
            impact={'stale_artifacts': ['complaint_draft']},
        )
        self.assertEqual(intervention.workflow_run_id, self.run.id)
        # case_id 应自动从 workflow_run 派生
        self.assertEqual(intervention.case_id, self.case.id)
        self.assertEqual(intervention.intervention_type, 'quality_review')
        self.assertEqual(intervention.status, 'pending')

    def test_create_intervention_falls_back_to_case(self):
        """仅传 case_id 创建介入（兼容旧调用方）。"""
        intervention = create_intervention(
            case_id=self.case.id,
            intervention_type='user_pause',
            stage='evidence_chain',
            base_revision=2,
            form_schema={},
            initial_values={},
            impact={},
        )
        self.assertIsNone(intervention.workflow_run_id)
        self.assertEqual(intervention.case_id, self.case.id)
        self.assertEqual(intervention.intervention_type, 'user_pause')

    def test_create_intervention_idempotent_with_workflow_run(self):
        """基于 workflow_run 的 update_or_create 幂等性。"""
        kwargs = dict(
            workflow_run_id=self.run.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=1,
            form_schema={'fields': [{'name': 'amount'}]},
            initial_values={'amount': '699'},
            impact={},
        )
        first = create_intervention(**kwargs)
        second = create_intervention(**kwargs)
        self.assertEqual(WorkflowIntervention.objects.count(), 1)
        self.assertEqual(first.id, second.id)

    def test_submit_intervention_reads_workflow_run_revision(self):
        """submit 时从 WorkflowRun.revision 读取进行冲突检测。"""
        # base_revision 与 run.revision 一致，应成功提交
        intervention = create_intervention(
            workflow_run_id=self.run.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=1,
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

        # 构造 revision 冲突：将 run.revision 提升到 2，base_revision 仍为 1
        self.run.revision = 2
        self.run.save(update_fields=['revision'])
        intervention2 = create_intervention(
            workflow_run_id=self.run.id,
            intervention_type='quality_review',
            stage='evidence_chain',  # 不同 stage 避免与第一条冲突
            base_revision=1,         # 旧 base_revision
            form_schema={},
            initial_values={},
            impact={},
        )
        with self.assertRaises(RevisionConflictError) as ctx:
            submit_intervention(
                intervention_id=intervention2.id,
                submitted_values={},
            )
        self.assertEqual(ctx.exception.base_revision, 1)
        self.assertEqual(ctx.exception.current_revision, 2)

    def test_submit_intervention_falls_back_to_case_revision(self):
        """workflow_run=None 时回退到 case.workflow_revision。"""
        # 构造仅关联 case 的旧版介入
        intervention = create_intervention(
            case_id=self.case.id,
            intervention_type='user_pause',
            stage='evidence_chain',
            base_revision=1,
            form_schema={},
            initial_values={},
            impact={},
        )
        # case.workflow_revision=1 与 base_revision=1 一致，应成功提交
        result = submit_intervention(
            intervention_id=intervention.id,
            submitted_values={'notes': 'ok'},
        )
        self.assertEqual(result.status, 'submitted')

        # 修改 case.workflow_revision 制造冲突
        self.case.workflow_revision = 5
        self.case.save(update_fields=['workflow_revision'])
        intervention2 = create_intervention(
            case_id=self.case.id,
            intervention_type='user_pause',
            stage='complaint',  # 不同 stage
            base_revision=1,
            form_schema={},
            initial_values={},
            impact={},
        )
        with self.assertRaises(RevisionConflictError):
            submit_intervention(
                intervention_id=intervention2.id,
                submitted_values={},
            )


class ArtifactServiceTests(TestCase):
    """artifact_service 接口测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)
        self.run = WorkflowRun.objects.create(case=self.case)

    def test_create_artifact_basic(self):
        """基本创建：返回 WorkflowArtifact 实例，默认 status=current, version=1。"""
        art = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='preclassify_result',
            stage='material_understanding',
            node_name='preclassify',
            content={'category': 'chat_screenshot'},
            summary={'title': '聊天截图分类'},
            quality={'score': 0.92, 'status': 'pass'},
            provenance=[{'node': 'preclassify', 'ts': '2026-07-17T10:00:00Z'}],
            metrics={'duration_ms': 320, 'model_calls': 1},
            evidence_id=401,
            revision=3,
        )
        self.assertEqual(art.workflow_run_id, self.run.id)
        self.assertEqual(art.case_id, self.case.id)
        self.assertEqual(art.artifact_type, 'preclassify_result')
        self.assertEqual(art.stage, 'material_understanding')
        self.assertEqual(art.node_name, 'preclassify')
        self.assertEqual(art.version, 1)
        self.assertEqual(art.revision, 3)
        self.assertEqual(art.status, 'current')
        self.assertEqual(art.content, {'category': 'chat_screenshot'})
        self.assertEqual(art.summary, {'title': '聊天截图分类'})
        self.assertEqual(art.quality, {'score': 0.92, 'status': 'pass'})
        self.assertEqual(art.provenance, [{'node': 'preclassify', 'ts': '2026-07-17T10:00:00Z'}])
        self.assertEqual(art.metrics, {'duration_ms': 320, 'model_calls': 1})
        self.assertEqual(art.evidence_id, 401)

    def test_create_artifact_with_source_refs(self):
        """含 source_refs 上游依赖创建。"""
        upstream = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='preclassify_result',
            stage='material_understanding',
            evidence_id=501,
        )
        downstream = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='ocr_result',
            stage='material_understanding',
            source_refs=[upstream.id],
            evidence_id=501,
        )
        self.assertEqual(downstream.source_refs, [upstream.id])

    def test_mark_artifacts_stale_cascades(self):
        """递归传播 stale：A -> B -> C，标记 A 后 B/C 都变 stale。"""
        a = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='preclassify_result',
            stage='material_understanding',
            evidence_id=601,
        )
        b = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='ocr_result',
            stage='material_understanding',
            source_refs=[a.id],
            evidence_id=601,
        )
        c = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='classify_result',
            stage='material_understanding',
            source_refs=[b.id],
            evidence_id=601,
        )

        marked = mark_artifacts_stale(self.run.id, [a.id])
        # 应至少标记 3 个（a + b + c）
        self.assertEqual(marked, 3)

        for art in (a, b, c):
            art.refresh_from_db()
            self.assertEqual(art.status, 'stale')
            self.assertIsNotNone(art.stale_at)

    def test_get_artifacts_by_stage(self):
        """按阶段查询产物。"""
        art1 = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='preclassify_result',
            stage='material_understanding',
            evidence_id=701,
        )
        art2 = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='extract_result',
            stage='fact_checking',
            evidence_id=701,
        )

        material_arts = get_artifacts_by_stage(self.run.id, 'material_understanding')
        fact_arts = get_artifacts_by_stage(self.run.id, 'fact_checking')
        self.assertEqual(len(material_arts), 1)
        self.assertEqual(material_arts[0].id, art1.id)
        self.assertEqual(len(fact_arts), 1)
        self.assertEqual(fact_arts[0].id, art2.id)

        # 不存在的阶段
        empty = get_artifacts_by_stage(self.run.id, 'document_generation')
        self.assertEqual(empty, [])
