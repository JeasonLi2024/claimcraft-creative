# -*- coding: utf-8 -*-
"""工作流快照服务（Task 3.3）。

聚合 WorkflowRun + WorkflowArtifact + WorkflowIntervention + issues + actions
返回权威快照供前端展示（GET /api/workflow-runs/{run_id}/snapshot/）。

对齐 spec.md 阶段 3 描述：
- run：运行基础信息（status, progress, revision, current_stage 等）
- stages：4 业务阶段状态聚合（材料理解 / 事实核对 / 案件组织 / 文书生成）
- active_intervention：当前等待用户提交的介入（status=pending）
- artifacts：所有 current 产物列表
- issues：聚合自 NodeResult.warnings + errors 的统一问题列表
- actions：根据当前 status 计算允许的操作

对齐 spec.md「Requirement: Unified Snapshot API」：
> 系统 SHALL 提供 GET /api/workflow-runs/{run_id}/snapshot/ 端点返回权威快照，
> 聚合运行状态 + 阶段 + 产物 + 介入 + 问题 + 允许操作。
> WHEN 工作流运行中，前端请求 snapshot
> THEN 系统返回 {run, stages, active_intervention, artifacts, issues, actions}，
> 其中 actions 含 can_pause / can_resume / can_cancel / can_retry / can_restart_from_stage
"""
from typing import Optional

from api.models import WorkflowArtifact, WorkflowIntervention, WorkflowRun


# 业务阶段 → 技术节点映射（与 graph.py build_case_workflow 节点顺序对齐）
STAGE_NODE_MAP = {
    'material_understanding': ['preclassify', 'ocr', 'classify'],
    'fact_checking': ['extract', 'review'],
    'case_organization': ['evidence_chain'],
    'document_generation': ['complaint', 'respond_complaint'],
}

# 业务阶段中文显示
STAGE_LABELS = {
    'material_understanding': '材料理解',
    'fact_checking': '事实核对',
    'case_organization': '案件组织',
    'document_generation': '文书生成',
}


class SnapshotService:
    """工作流快照聚合服务。"""

    def get_snapshot(self, run_id: int) -> Optional[dict]:
        """获取指定运行的权威快照。

        Args:
            run_id: WorkflowRun ID

        Returns:
            None 若 run_id 不存在；否则返回结构：
                {
                    run: dict,
                    stages: list[dict],     # 4 业务阶段
                    active_intervention: dict | None,
                    artifacts: list[dict],   # current 产物
                    issues: list[dict],      # 聚合自 blocking_issues + provenance warnings
                    actions: dict,           # can_pause / can_resume / can_cancel / can_retry / can_restart_from_stage / can_submit_intervention
                }
        """
        try:
            run = WorkflowRun.objects.get(pk=run_id)
        except WorkflowRun.DoesNotExist:
            return None

        artifacts = list(
            run.artifacts.filter(status='current').order_by('created_at')
        )
        interventions = list(run.interventions.order_by('-created_at'))
        active_intervention = next(
            (i for i in interventions if i.status == 'pending'), None
        )

        stages = self._aggregate_stages(run, artifacts)
        issues = self._aggregate_issues(run, artifacts)
        actions = self._compute_actions(run, active_intervention)

        return {
            'run': self._serialize_run(run),
            'stages': stages,
            'active_intervention': (
                self._serialize_intervention(active_intervention)
                if active_intervention else None
            ),
            'artifacts': [self._serialize_artifact(a) for a in artifacts],
            'issues': issues,
            'actions': actions,
        }

    # ------------------------------------------------------------------ #
    # 序列化辅助
    # ------------------------------------------------------------------ #

    def _serialize_run(self, run: WorkflowRun) -> dict:
        """序列化 WorkflowRun 基础信息。"""
        return {
            'id': run.id,
            'case_id': run.case_id,
            'thread_id': run.thread_id,
            'status': run.status,
            'current_stage': run.current_stage,
            'current_node': run.current_node,
            'progress': run.progress,
            'revision': run.revision,
            'workflow_version': run.workflow_version,
            'state_schema_version': run.state_schema_version,
            'policy_version': run.policy_version,
            'prompt_bundle_version': run.prompt_bundle_version,
            'selected_evidence_ids': run.selected_evidence_ids,
            'run_options': run.run_options,
            'quality_summary': run.quality_summary,
            'error_message': run.error_message,
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'finished_at': run.finished_at.isoformat() if run.finished_at else None,
            'parent_run_id': run.parent_run_id,
            'created_at': run.created_at.isoformat() if run.created_at else None,
            'updated_at': run.updated_at.isoformat() if run.updated_at else None,
        }

    def _serialize_artifact(self, artifact: WorkflowArtifact) -> dict:
        """序列化 WorkflowArtifact。"""
        return {
            'id': artifact.id,
            'workflow_run_id': artifact.workflow_run_id,
            'case_id': artifact.case_id,
            'evidence_id': artifact.evidence_id,
            'artifact_type': artifact.artifact_type,
            'stage': artifact.stage,
            'node_name': artifact.node_name,
            'version': artifact.version,
            'revision': artifact.revision,
            'status': artifact.status,
            'content': artifact.content,
            'summary': artifact.summary,
            'quality': artifact.quality,
            'provenance': artifact.provenance,
            'source_refs': artifact.source_refs,
            'metrics': artifact.metrics,
            'created_at': artifact.created_at.isoformat() if artifact.created_at else None,
            'stale_at': artifact.stale_at.isoformat() if artifact.stale_at else None,
        }

    def _serialize_intervention(self, intervention: WorkflowIntervention) -> dict:
        """序列化 WorkflowIntervention。

        注意：WorkflowIntervention 模型未直接定义 required / reason 字段，
        它们存储在 impact JSONField 中（由 review_node / stage_gate_node 创建时写入），
        此处从 impact 派生。
        """
        impact = intervention.impact if isinstance(intervention.impact, dict) else {}
        return {
            'id': intervention.id,
            'workflow_run_id': intervention.workflow_run_id,
            'case_id': intervention.case_id,
            'intervention_type': intervention.intervention_type,
            'stage': intervention.stage,
            'status': intervention.status,
            'required': bool(impact.get('required', False)),
            'reason': str(impact.get('reason', '')),
            # input-quality-guard：Gate 2（missing_information）诊断数据存于 impact，
            # 供前端介入面板展示「上传张数 / 有效证据 / 置信度 / 字段数」诊断区块。
            'diagnostics': impact.get('diagnostics', {}) if isinstance(impact.get('diagnostics'), dict) else {},
            'base_revision': intervention.base_revision,
            'form_schema': intervention.form_schema,
            'initial_values': intervention.initial_values,
            'impact': intervention.impact,
            'submitted_values': intervention.submitted_values,
            'created_at': intervention.created_at.isoformat() if intervention.created_at else None,
            'submitted_at': intervention.submitted_at.isoformat() if intervention.submitted_at else None,
            'expires_at': intervention.expires_at.isoformat() if intervention.expires_at else None,
        }

    # ------------------------------------------------------------------ #
    # 阶段聚合
    # ------------------------------------------------------------------ #

    def _aggregate_stages(
        self, run: WorkflowRun, artifacts: list[WorkflowArtifact]
    ) -> list[dict]:
        """聚合 4 业务阶段状态。"""
        stages: list[dict] = []
        for stage, nodes in STAGE_NODE_MAP.items():
            stage_artifacts = [a for a in artifacts if a.stage == stage]
            quality: dict = {}
            if stage_artifacts:
                # 取该阶段最新产物的 quality
                quality = stage_artifacts[-1].quality or {}

            stage_status = self._compute_stage_status(run, stage, stage_artifacts)
            stages.append({
                'name': stage,
                'label': STAGE_LABELS.get(stage, stage),
                'status': stage_status,
                'nodes': list(nodes),
                'progress': self._compute_stage_progress(run, stage),
                'quality': quality,
                'artifact_count': len(stage_artifacts),
                'issue_count': sum(
                    1 for a in stage_artifacts
                    for _ in (a.quality or {}).get('blocking_issues', [])
                ),
            })
        return stages

    @staticmethod
    def _stage_blocked(stage_artifacts: list[WorkflowArtifact]) -> bool:
        latest_quality = (stage_artifacts[-1].quality or {}) if stage_artifacts else {}
        return latest_quality.get('status') == 'blocked'

    def _terminal_stage_status(
        self, run: WorkflowRun, stage: str, stage_order: list, stage_artifacts: list
    ) -> str:
        """run 进入终态（succeeded/failed/cancelled）后收敛阶段状态。

        避免出现 run.status=succeeded 而 current_stage 阶段仍显示 running、
        或 progress=1.0 却 status=running 的矛盾。
        """
        # current_stage 可能为空或非法（异常终态）；缺失时用最后一个阶段兜底
        current = run.current_stage if run.current_stage in stage_order else (
            stage_order[-1] if stage_order else stage
        )
        try:
            cur_idx = stage_order.index(current)
            stage_idx = stage_order.index(stage)
        except ValueError:
            return 'completed' if stage_artifacts else 'skipped'
        if self._stage_blocked(stage_artifacts):
            return 'blocked'
        if run.status == 'succeeded':
            # 成功：执行到的阶段（current 及之前，或已产出产物）判完成，其余跳过
            return 'completed' if (stage_idx <= cur_idx or stage_artifacts) else 'skipped'
        if run.status == 'failed':
            if stage_idx < cur_idx:
                return 'completed'
            if stage_idx == cur_idx:
                return 'failed'
            return 'skipped'
        # cancelled：之前阶段视为完成，current 及之后视为跳过
        return 'completed' if stage_idx < cur_idx else 'skipped'

    def _compute_stage_status(
        self, run: WorkflowRun, stage: str, stage_artifacts: list[WorkflowArtifact]
    ) -> str:
        """计算阶段状态：pending / running / completed / blocked / skipped。"""
        stage_order = list(STAGE_NODE_MAP.keys())
        # 终态收敛：run 结束后不再返回 running
        if run.status in ('succeeded', 'failed', 'cancelled'):
            return self._terminal_stage_status(run, stage, stage_order, stage_artifacts)
        if run.current_stage == stage:
            return 'running'
        if run.current_stage and run.current_stage in stage_order and stage in stage_order:
            if stage_order.index(stage) < stage_order.index(run.current_stage):
                # 过去阶段：先检查是否 blocked（基于最新产物的 quality.status），
                # 再决定 completed / skipped。避免阻塞问题被 completed 提前覆盖。
                latest_quality = (stage_artifacts[-1].quality or {}) if stage_artifacts else {}
                if latest_quality.get('status') == 'blocked':
                    return 'blocked'
                return 'completed' if stage_artifacts else 'skipped'
        if not stage_artifacts:
            return 'pending'
        # 有产物但当前阶段已超过 → 检查是否有 blocking_issues
        latest_quality = (stage_artifacts[-1].quality or {}) if stage_artifacts else {}
        if latest_quality.get('status') == 'blocked':
            return 'blocked'
        return 'completed'

    def _compute_stage_progress(self, run: WorkflowRun, stage: str) -> float:
        """计算阶段进度（0.0-1.0）。

        基于 run.progress（总体进度）按 4 阶段等分映射：
        - 阶段 idx < current_stage idx：1.0（已完成）
        - 阶段 idx > current_stage idx：0.0（未开始）
        - 阶段 idx == current_stage idx：(progress - base) / stage_span
        """
        stage_order = list(STAGE_NODE_MAP.keys())
        terminal = run.status in ('succeeded', 'failed', 'cancelled')
        current = run.current_stage
        # 终态且 current_stage 缺失/非法时用最后一个阶段兜底，保证进度与状态一致
        if terminal and (not current or current not in stage_order):
            current = stage_order[-1] if stage_order else stage
        if not current:
            return 0.0
        try:
            current_idx = stage_order.index(current)
            stage_idx = stage_order.index(stage)
        except ValueError:
            return 0.0
        if stage_idx < current_idx:
            return 1.0
        if stage_idx > current_idx:
            return 0.0
        # 同阶段：成功终态直接判满，其余用 run.progress 的小数部分推算
        if terminal and run.status == 'succeeded':
            return 1.0
        total_stages = len(stage_order)
        base = stage_idx / total_stages
        stage_span = 1.0 / total_stages
        if stage_span <= 0:
            return 0.0
        return min(1.0, (run.progress - base) / stage_span) if run.progress > base else 0.0

    # ------------------------------------------------------------------ #
    # 问题聚合
    # ------------------------------------------------------------------ #

    def _aggregate_issues(
        self, run: WorkflowRun, artifacts: list[WorkflowArtifact]
    ) -> list[dict]:
        """聚合所有产物的 issues（blocking_issues + provenance warnings）。

        对齐 spec.md「新增 Issue 概念」：
        > NodeResult.warnings + errors 统一为 issues，
        > 含 code / message / severity (blocking/warning/info) / evidence_id / stage / recoverable
        """
        issues: list[dict] = []
        for art in artifacts:
            quality = art.quality or {}
            # blocking_issues 已是 list[dict]（每个含 code/message/severity 等）
            for issue in quality.get('blocking_issues', []):
                if not isinstance(issue, dict):
                    continue
                issues.append({
                    **issue,
                    'artifact_id': art.id,
                    'stage': art.stage,
                    'severity': 'blocking',
                })
            # 从 provenance 提取 warnings（如有）
            for prov in (art.provenance or []):
                if isinstance(prov, dict) and prov.get('warning'):
                    issues.append({
                        'code': prov.get('code', 'warning'),
                        'message': prov['warning'],
                        'severity': 'warning',
                        'stage': art.stage,
                        'artifact_id': art.id,
                    })
        # 按严重性排序
        severity_order = {'blocking': 0, 'warning': 1, 'info': 2}
        issues.sort(key=lambda x: severity_order.get(x.get('severity', 'info'), 3))
        return issues

    # ------------------------------------------------------------------ #
    # 允许操作计算
    # ------------------------------------------------------------------ #

    def _compute_actions(
        self, run: WorkflowRun, active_intervention: Optional[WorkflowIntervention]
    ) -> dict:
        """根据当前 status 计算允许的操作。

        对齐 spec.md「actions 字段返回」：
        > 所有 /workflow-runs/* 响应含
        > can_pause / can_resume / can_cancel / can_retry / can_restart_from_stage
        """
        status = run.status
        return {
            'can_pause': status == 'running',
            'can_resume': status == 'pausing' or (
                status == 'waiting_user' and active_intervention is not None
            ),
            'can_cancel': status in ('running', 'pausing', 'waiting_user', 'queued'),
            'can_retry': status in ('failed', 'succeeded'),
            'can_restart_from_stage': status in ('failed', 'succeeded', 'waiting_user'),
            'can_submit_intervention': status == 'waiting_user' and active_intervention is not None,
        }
