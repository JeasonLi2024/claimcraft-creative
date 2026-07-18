# -*- coding: utf-8 -*-
"""工作流产物服务：在节点完成后创建 WorkflowArtifact 记录。

职责：
- create_artifact: 节点完成后创建 WorkflowArtifact（含 source_refs 上游依赖）
- mark_artifacts_stale: 上游变更时自动传播 stale 状态（Task 3.3 RetryService 使用）
- get_artifacts_by_run: 查询指定运行的所有 current 产物
- get_artifacts_by_stage: 查询指定阶段的 current 产物

依赖关系（source_refs）：
- preclassify_result: 无上游
- ocr_result: 上游 preclassify_result（同证据）
- classify_result: 上游 ocr_result（同证据）
- extract_result: 上游 classify_result（同证据）
- review_result: 上游 extract_result（同证据）
- evidence_chain: 上游所有 extract_result
- complaint_draft / respond_complaint_draft: 上游 evidence_chain + 所有 extract_result
"""
from typing import Optional

from django.utils import timezone

from api.models import WorkflowArtifact


def create_artifact(
    *,
    workflow_run_id: int,
    case_id: int,
    artifact_type: str,
    stage: str,
    node_name: str = '',
    content: Optional[dict] = None,
    summary: Optional[dict] = None,
    quality: Optional[dict] = None,
    provenance: Optional[list] = None,
    metrics: Optional[dict] = None,
    source_refs: Optional[list] = None,
    evidence_id: Optional[int] = None,
    revision: int = 0,
) -> WorkflowArtifact:
    """创建 WorkflowArtifact 记录。

    自动计算 version（同类型同证据的最高版本 +1），将旧版本标记为 superseded。

    Args:
        workflow_run_id: 关联的 WorkflowRun ID
        case_id: 关联的案件 ID（冗余便于按 case 查询）
        artifact_type: 产物类型（见 ARTIFACT_TYPE_CHOICES）
        stage: 所属业务阶段
        node_name: 生成节点名
        content: 产物内容（NodeResult.data 快照）
        summary: 业务摘要（前端卡片展示用）
        quality: 质量评分（NodeResult.quality 快照）
        provenance: 数据来源（NodeResult.provenance 列表快照）
        metrics: 指标（NodeResult.metrics 快照）
        source_refs: 上游依赖（WorkflowArtifact ID 列表，用于 stale 传播）
        evidence_id: 关联证据 ID（多证据聚合产物为 None）
        revision: 创建时的 state.revision

    Returns:
        WorkflowArtifact 实例
    """
    # 计算新版本号：取同类型同证据的最高版本（含已 superseded 的）
    prev_artifacts = WorkflowArtifact.objects.filter(
        workflow_run_id=workflow_run_id,
        artifact_type=artifact_type,
        evidence_id=evidence_id,
    ).exclude(status='current').order_by('-version')
    # 旧 current 标记为 superseded
    WorkflowArtifact.objects.filter(
        workflow_run_id=workflow_run_id,
        artifact_type=artifact_type,
        evidence_id=evidence_id,
        status='current',
    ).update(status='superseded', stale_at=timezone.now())

    new_version = 1
    if prev_artifacts.exists():
        new_version = (prev_artifacts.first().version or 0) + 1

    artifact = WorkflowArtifact.objects.create(
        workflow_run_id=workflow_run_id,
        case_id=case_id,
        evidence_id=evidence_id,
        artifact_type=artifact_type,
        stage=stage,
        node_name=node_name,
        version=new_version,
        revision=revision,
        status='current',
        content=content or {},
        summary=summary or {},
        quality=quality or {},
        provenance=provenance or [],
        metrics=metrics or {},
        source_refs=source_refs or [],
    )
    return artifact


def mark_artifacts_stale(
    workflow_run_id: int,
    artifact_ids: list[int],
    reason: str = 'upstream_changed',
) -> int:
    """将指定产物标记为 stale，并递归传播到依赖它们的下游产物。

    递归逻辑：查找 source_refs 中含 pending 产物 ID 的下游 current 产物，
    将其一并标记为 stale，直至无下游为止。

    实现说明：在 Python 层检查 source_refs 列表成员，避免使用
    `__overlap`（PostgreSQL ArrayField 专用，SQLite 不支持），保证
    SQLite 测试 / MySQL 生产 / PostgreSQL 生产行为一致。

    Args:
        workflow_run_id: 关联的 WorkflowRun ID
        artifact_ids: 需标记为 stale 的产物 ID 列表
        reason: 标记原因（暂未持久化，预留扩展）

    Returns:
        标记为 stale 的产物总数（含递归传播）
    """
    if not artifact_ids:
        return 0

    marked_ids: set[int] = set()
    pending: set[int] = set(artifact_ids)

    # 预加载所有 current 产物（避免 DB-specific lookup 兼容性问题）
    all_current = list(
        WorkflowArtifact.objects.filter(
            workflow_run_id=workflow_run_id,
            status='current',
        )
    )
    current_by_id: dict[int, WorkflowArtifact] = {art.id: art for art in all_current}

    while pending:
        # 找出依赖 pending 产物作为 source_refs 的下游 current 产物
        downstream_ids: list[int] = []
        for art_id, art in current_by_id.items():
            if art_id in marked_ids or art_id in pending:
                continue
            src_refs = art.source_refs or []
            if any(ref in pending for ref in src_refs):
                downstream_ids.append(art_id)

        # 标记当前批次为 stale
        WorkflowArtifact.objects.filter(
            workflow_run_id=workflow_run_id,
            id__in=pending,
            status='current',
        ).update(status='stale', stale_at=timezone.now())
        marked_ids.update(pending)

        pending = set(downstream_ids)

    return len(marked_ids)


def get_artifacts_by_run(
    workflow_run_id: int, only_current: bool = True
) -> list[WorkflowArtifact]:
    """查询指定运行的所有产物。

    Args:
        workflow_run_id: 关联的 WorkflowRun ID
        only_current: True 仅返回 status='current' 的产物；False 返回全部

    Returns:
        WorkflowArtifact 列表（按 created_at 升序）
    """
    qs = WorkflowArtifact.objects.filter(workflow_run_id=workflow_run_id)
    if only_current:
        qs = qs.filter(status='current')
    return list(qs.order_by('created_at'))


def get_artifacts_by_stage(
    workflow_run_id: int, stage: str, only_current: bool = True
) -> list[WorkflowArtifact]:
    """查询指定阶段的产物。

    Args:
        workflow_run_id: 关联的 WorkflowRun ID
        stage: 业务阶段（material_understanding / fact_checking /
            case_organization / document_generation）
        only_current: True 仅返回 status='current' 的产物；False 返回全部

    Returns:
        WorkflowArtifact 列表（按 created_at 升序）
    """
    qs = WorkflowArtifact.objects.filter(
        workflow_run_id=workflow_run_id, stage=stage
    )
    if only_current:
        qs = qs.filter(status='current')
    return list(qs.order_by('created_at'))
