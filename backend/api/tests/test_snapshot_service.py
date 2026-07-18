# -*- coding: utf-8 -*-
"""Task 3.3 测试：SnapshotService。

测试 SnapshotService 的快照聚合能力（对齐 spec.md「Requirement: Unified Snapshot API」）：
1. get_snapshot 返回 None / 完整结构
2. 4 业务阶段聚合（材料理解 / 事实核对 / 案件组织 / 文书生成）
3. issues 来自 blocking_issues + provenance warnings
4. actions 根据 status 计算（running / waiting_user / failed）

测试使用 Django TestCase（SQLite，由 settings 在 manage.py test 时自动启用）。
"""
from django.contrib.auth.models import User
from django.test import TestCase

from api.agents.artifact_service import create_artifact
from api.models import Case, WorkflowArtifact, WorkflowIntervention, WorkflowRun
from api.services.intervention_service import create_intervention
from api.services.snapshot_service import (
    STAGE_LABELS,
    STAGE_NODE_MAP,
    SnapshotService,
)


def _make_case(user=None, **kwargs):
    """测试辅助：创建一个最小 Case。"""
    return Case.objects.create(
        title=kwargs.pop('title', '测试案件'),
        owner=user,
        **kwargs,
    )


class SnapshotServiceTests(TestCase):
    """SnapshotService 基础测试。"""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pass')
        self.case = _make_case(self.user)
        self.run = WorkflowRun.objects.create(
            case=self.case,
            status='running',
            current_stage='fact_checking',
            current_node='extract',
            progress=0.30,
            revision=3,
        )
        self.service = SnapshotService()

    # ------------------------------------------------------------------ #
    # 基础结构
    # ------------------------------------------------------------------ #

    def test_get_snapshot_returns_none_for_nonexistent_run(self):
        """run_id 不存在时返回 None。"""
        self.assertIsNone(self.service.get_snapshot(999999))

    def test_get_snapshot_returns_basic_structure(self):
        """创建 run + artifact + intervention 后返回完整结构。"""
        art = create_artifact(
            workflow_run_id=self.run.id,
            case_id=self.case.id,
            artifact_type='extract_result',
            stage='fact_checking',
            node_name='extract',
            evidence_id=101,
            content={'fields': [{'name': 'amount', 'value': '699'}]},
            quality={'score': 0.85, 'status': 'review_required'},
        )
        intervention = create_intervention(
            workflow_run_id=self.run.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=3,
            form_schema={'fields': [{'name': 'amount'}]},
            initial_values={'amount': '699'},
            impact={'required': True, 'reason': '置信度低于阈值', 'stale_artifacts': []},
        )

        snapshot = self.service.get_snapshot(self.run.id)
        self.assertIsNotNone(snapshot)

        # 顶层 6 字段
        self.assertIn('run', snapshot)
        self.assertIn('stages', snapshot)
        self.assertIn('active_intervention', snapshot)
        self.assertIn('artifacts', snapshot)
        self.assertIn('issues', snapshot)
        self.assertIn('actions', snapshot)

        # run 基础字段
        self.assertEqual(snapshot['run']['id'], self.run.id)
        self.assertEqual(snapshot['run']['case_id'], self.case.id)
        self.assertEqual(snapshot['run']['status'], 'running')
        self.assertEqual(snapshot['run']['current_stage'], 'fact_checking')
        self.assertEqual(snapshot['run']['progress'], 0.30)
        self.assertEqual(snapshot['run']['revision'], 3)

        # artifacts 列表含 1 个 current 产物
        self.assertEqual(len(snapshot['artifacts']), 1)
        self.assertEqual(snapshot['artifacts'][0]['id'], art.id)
        self.assertEqual(snapshot['artifacts'][0]['artifact_type'], 'extract_result')

        # active_intervention 应为 pending 介入
        self.assertIsNotNone(snapshot['active_intervention'])
        self.assertEqual(snapshot['active_intervention']['id'], intervention.id)
        # required / reason 从 impact 派生
        self.assertTrue(snapshot['active_intervention']['required'])
        self.assertEqual(
            snapshot['active_intervention']['reason'], '置信度低于阈值'
        )

    # ------------------------------------------------------------------ #
    # 阶段聚合
    # ------------------------------------------------------------------ #

    def test_get_snapshot_aggregates_4_stages(self):
        """4 业务阶段聚合正确（material_understanding / fact_checking /
        case_organization / document_generation）。"""
        # 创建 4 阶段各 1 个 current 产物
        create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='classify_result', stage='material_understanding',
            evidence_id=201, revision=1,
        )
        create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='extract_result', stage='fact_checking',
            evidence_id=201, revision=2,
        )

        snapshot = self.service.get_snapshot(self.run.id)
        stages = snapshot['stages']
        self.assertEqual(len(stages), 4)

        stage_names = [s['name'] for s in stages]
        self.assertEqual(
            stage_names,
            ['material_understanding', 'fact_checking',
             'case_organization', 'document_generation'],
        )

        # 验证 STAGE_NODE_MAP 中的节点列表正确传播
        self.assertEqual(
            stages[0]['nodes'], STAGE_NODE_MAP['material_understanding']
        )
        # label 中文显示
        self.assertEqual(stages[0]['label'], '材料理解')
        self.assertEqual(stages[1]['label'], '事实核对')
        self.assertEqual(stages[2]['label'], '案件组织')
        self.assertEqual(stages[3]['label'], '文书生成')

        # 当前阶段 = fact_checking，应标记为 running
        fact_stage = next(s for s in stages if s['name'] == 'fact_checking')
        self.assertEqual(fact_stage['status'], 'running')

        # material_understanding 在 fact_checking 之前且有产物 → completed
        material_stage = next(
            s for s in stages if s['name'] == 'material_understanding'
        )
        self.assertEqual(material_stage['status'], 'completed')
        self.assertEqual(material_stage['artifact_count'], 1)

        # case_organization 在 fact_checking 之后且无产物 → pending
        case_stage = next(s for s in stages if s['name'] == 'case_organization')
        self.assertEqual(case_stage['status'], 'pending')
        self.assertEqual(case_stage['artifact_count'], 0)

    def test_get_snapshot_skipped_stage_without_artifacts(self):
        """已完成阶段但无产物时 status='skipped'。"""
        # 设置 current_stage 为更靠后的阶段，但中间阶段无产物
        self.run.current_stage = 'case_organization'
        self.run.save(update_fields=['current_stage'])

        snapshot = self.service.get_snapshot(self.run.id)
        stages = snapshot['stages']

        # fact_checking 在 case_organization 之前且无产物 → skipped
        fact_stage = next(s for s in stages if s['name'] == 'fact_checking')
        self.assertEqual(fact_stage['status'], 'skipped')

    # ------------------------------------------------------------------ #
    # 问题聚合
    # ------------------------------------------------------------------ #

    def test_get_snapshot_aggregates_issues(self):
        """issues 来自 blocking_issues + provenance warnings。"""
        # 产物 1：含 2 个 blocking_issues
        create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='extract_result', stage='fact_checking',
            evidence_id=301,
            quality={
                'score': 0.6,
                'status': 'review_required',
                'blocking_issues': [
                    {'code': 'LOW_CONFIDENCE', 'message': '金额置信度 0.4'},
                    {'code': 'MISSING_FIELD', 'message': '缺少订单号'},
                ],
            },
        )
        # 产物 2：provenance 含 warning
        create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='ocr_result', stage='material_understanding',
            evidence_id=302,
            provenance=[
                {'node': 'ocr', 'warning': 'OCR 降级到 base 模型', 'code': 'OCR_DEGRADED'},
            ],
        )

        snapshot = self.service.get_snapshot(self.run.id)
        issues = snapshot['issues']

        # 应有 3 个 issue（2 blocking + 1 warning）
        self.assertEqual(len(issues), 3)

        # 按严重性排序：blocking 在前
        blocking_count = sum(1 for i in issues if i.get('severity') == 'blocking')
        warning_count = sum(1 for i in issues if i.get('severity') == 'warning')
        self.assertEqual(blocking_count, 2)
        self.assertEqual(warning_count, 1)

        # 第一个应为 blocking
        self.assertEqual(issues[0]['severity'], 'blocking')
        # blocking_issues 应附带 artifact_id / stage
        self.assertEqual(issues[0]['stage'], 'fact_checking')
        self.assertIn('artifact_id', issues[0])

        # warning issue 应含 code 与 message
        warning_issue = next(i for i in issues if i.get('severity') == 'warning')
        self.assertEqual(warning_issue['code'], 'OCR_DEGRADED')
        self.assertIn('OCR', warning_issue['message'])

    # ------------------------------------------------------------------ #
    # actions 计算
    # ------------------------------------------------------------------ #

    def test_get_snapshot_computes_actions_running(self):
        """status=running 时 can_pause=True, can_resume=False, can_retry=False。"""
        snapshot = self.service.get_snapshot(self.run.id)
        actions = snapshot['actions']
        self.assertTrue(actions['can_pause'])
        self.assertFalse(actions['can_resume'])
        self.assertTrue(actions['can_cancel'])
        self.assertFalse(actions['can_retry'])
        self.assertFalse(actions['can_restart_from_stage'])
        self.assertFalse(actions['can_submit_intervention'])

    def test_get_snapshot_computes_actions_waiting_user(self):
        """status=waiting_user + active_intervention 时 can_submit_intervention=True。"""
        self.run.status = 'waiting_user'
        self.run.save(update_fields=['status'])
        create_intervention(
            workflow_run_id=self.run.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=3,
            form_schema={},
            initial_values={},
            impact={'required': True, 'reason': '低置信度'},
        )

        snapshot = self.service.get_snapshot(self.run.id)
        actions = snapshot['actions']
        self.assertFalse(actions['can_pause'])
        self.assertTrue(actions['can_resume'])
        self.assertTrue(actions['can_cancel'])
        self.assertFalse(actions['can_retry'])
        self.assertTrue(actions['can_restart_from_stage'])
        self.assertTrue(actions['can_submit_intervention'])
        # active_intervention 应非空
        self.assertIsNotNone(snapshot['active_intervention'])

    def test_get_snapshot_computes_actions_failed(self):
        """status=failed 时 can_retry=True, can_restart_from_stage=True。"""
        self.run.status = 'failed'
        self.run.save(update_fields=['status'])

        snapshot = self.service.get_snapshot(self.run.id)
        actions = snapshot['actions']
        self.assertFalse(actions['can_pause'])
        self.assertFalse(actions['can_resume'])
        self.assertFalse(actions['can_cancel'])
        self.assertTrue(actions['can_retry'])
        self.assertTrue(actions['can_restart_from_stage'])
        self.assertFalse(actions['can_submit_intervention'])

    def test_get_snapshot_computes_actions_succeeded(self):
        """status=succeeded 时 can_retry=True（允许重新发起）。"""
        self.run.status = 'succeeded'
        self.run.save(update_fields=['status'])

        snapshot = self.service.get_snapshot(self.run.id)
        actions = snapshot['actions']
        self.assertTrue(actions['can_retry'])
        self.assertTrue(actions['can_restart_from_stage'])
        self.assertFalse(actions['can_cancel'])

    # ------------------------------------------------------------------ #
    # 阶段进度计算
    # ------------------------------------------------------------------ #

    def test_stage_progress_completed_for_past_stages(self):
        """过去阶段 progress=1.0，未来阶段 progress=0.0。"""
        self.run.current_stage = 'fact_checking'
        self.run.progress = 0.30
        self.run.save(update_fields=['current_stage', 'progress'])

        snapshot = self.service.get_snapshot(self.run.id)
        stages = {s['name']: s for s in snapshot['stages']}

        # material_understanding 是过去阶段 → 1.0
        self.assertEqual(stages['material_understanding']['progress'], 1.0)
        # case_organization / document_generation 是未来阶段 → 0.0
        self.assertEqual(stages['case_organization']['progress'], 0.0)
        self.assertEqual(stages['document_generation']['progress'], 0.0)

    def test_stage_progress_current_stage_uses_run_progress(self):
        """当前阶段进度 = (run.progress - base) / stage_span。"""
        # 4 阶段等分，fact_checking base=0.25, span=0.25
        # run.progress=0.30 → (0.30 - 0.25) / 0.25 = 0.20
        self.run.current_stage = 'fact_checking'
        self.run.progress = 0.30
        self.run.save(update_fields=['current_stage', 'progress'])

        snapshot = self.service.get_snapshot(self.run.id)
        stages = {s['name']: s for s in snapshot['stages']}
        self.assertAlmostEqual(stages['fact_checking']['progress'], 0.20, places=2)

    def test_stage_blocked_status(self):
        """产物 quality.status='blocked' 时阶段 status='blocked'。"""
        # 设置 current_stage 为更靠后阶段，使 fact_checking 成为「已完成」阶段
        # 但其产物 quality.status=blocked → 应标 blocked 而非 completed
        self.run.current_stage = 'case_organization'
        self.run.save(update_fields=['current_stage'])
        create_artifact(
            workflow_run_id=self.run.id, case_id=self.case.id,
            artifact_type='extract_result', stage='fact_checking',
            evidence_id=401,
            quality={'score': 0.0, 'status': 'blocked',
                     'blocking_issues': [{'code': 'EMPTY', 'message': '无字段'}]},
        )

        snapshot = self.service.get_snapshot(self.run.id)
        fact_stage = next(
            s for s in snapshot['stages'] if s['name'] == 'fact_checking'
        )
        self.assertEqual(fact_stage['status'], 'blocked')
        # issue_count 应反映 blocking_issues 数量
        self.assertEqual(fact_stage['issue_count'], 1)

    # ------------------------------------------------------------------ #
    # 介入序列化
    # ------------------------------------------------------------------ #

    def test_active_intervention_serialization(self):
        """active_intervention 序列化字段完整。"""
        self.run.status = 'waiting_user'
        self.run.save(update_fields=['status'])
        intervention = create_intervention(
            workflow_run_id=self.run.id,
            intervention_type='user_pause',
            stage='evidence_chain',
            base_revision=3,
            form_schema={'fields': [{'name': 'notes', 'type': 'textarea'}]},
            initial_values={'notes': ''},
            impact={'required': False, 'reason': '用户主动暂停'},
        )

        snapshot = self.service.get_snapshot(self.run.id)
        active = snapshot['active_intervention']
        self.assertIsNotNone(active)
        self.assertEqual(active['id'], intervention.id)
        self.assertEqual(active['intervention_type'], 'user_pause')
        self.assertEqual(active['stage'], 'evidence_chain')
        self.assertEqual(active['status'], 'pending')
        self.assertEqual(active['base_revision'], 3)
        self.assertFalse(active['required'])  # impact.required=False
        self.assertEqual(active['reason'], '用户主动暂停')
        self.assertIn('fields', active['form_schema'])

    def test_no_active_intervention_when_none_pending(self):
        """无 pending 介入时 active_intervention=None。"""
        create_intervention(
            workflow_run_id=self.run.id,
            intervention_type='quality_review',
            stage='extract',
            base_revision=3,
            form_schema={},
            initial_values={},
            impact={},
        )
        # 将该介入标记为 submitted
        WorkflowIntervention.objects.filter(
            workflow_run_id=self.run.id
        ).update(status='submitted')

        snapshot = self.service.get_snapshot(self.run.id)
        self.assertIsNone(snapshot['active_intervention'])
