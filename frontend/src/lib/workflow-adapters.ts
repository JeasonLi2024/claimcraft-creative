// 工作流契约适配层
//
// 背景：新工作流 UI 组件消费「前端规范形状」（types/workflow.ts），而后端
// snapshot / SSE 序列化使用另一套字段名与枚举（见 backend/api/services/snapshot_service.py）。
// 本模块在 API / SSE 边界做一次归一化，使组件无需感知后端字段差异。
//
// 主要映射：
//   run:          finished_at → completed_at；started_at(null) → ''
//   stage:        name(键) → key；label → name(显示)；quality.score → quality_score；status 'blocked' → 'failed'
//   artifact:     workflow_run_id → run_id；artifact_type → kind；content → payload；
//                 status 'current'→'active' / 'superseded'→'archived'；stale_at → updated_at
//   intervention: workflow_run_id → run_id
//
// 同一套归一化同时用于 snapshot 与 SSE 事件内嵌对象（artifact.created 等）。

import type {
  WorkflowRun,
  WorkflowRunStatus,
  WorkflowStage,
  WorkflowArtifact,
  WorkflowArtifactKind,
  WorkflowArtifactStatus,
  WorkflowIntervention,
  InterventionType,
  InterventionStatus,
  Issue,
  IssueSeverity,
  WorkflowAllowedActions,
  BusinessStageKey,
} from "@/types/workflow"
import type { SnapshotResponse } from "@/stores/workflow-run-store"

// ---------- 安全读取工具 ----------

type Raw = Record<string, unknown>

function asRaw(v: unknown): Raw {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Raw) : {}
}
function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback
}
function asNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" && !Number.isNaN(v) ? v : fallback
}
function asStringOrNull(v: unknown): string | null {
  return typeof v === "string" ? v : null
}
function asNumberOrNull(v: unknown): number | null {
  return typeof v === "number" && !Number.isNaN(v) ? v : null
}
function asBool(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback
}
function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : []
}
function asNumberArray(v: unknown): number[] {
  return asArray(v).filter((x): x is number => typeof x === "number")
}

// ---------- 枚举映射 ----------

const ARTIFACT_STATUS_MAP: Record<string, WorkflowArtifactStatus> = {
  current: "active",
  active: "active",
  stale: "stale",
  superseded: "archived",
  archived: "archived",
}

function mapArtifactStatus(raw: unknown): WorkflowArtifactStatus {
  return ARTIFACT_STATUS_MAP[asString(raw)] ?? "active"
}

const STAGE_STATUS_MAP: Record<string, WorkflowStage["status"]> = {
  pending: "pending",
  running: "running",
  completed: "completed",
  failed: "failed",
  skipped: "skipped",
  // 后端可能返回 'blocked'（质量门阻塞）；UI 无独立态，按 failed 呈现（红色 + 待处理）
  blocked: "failed",
}

function mapStageStatus(raw: unknown): WorkflowStage["status"] {
  return STAGE_STATUS_MAP[asString(raw)] ?? "pending"
}

// ---------- 单实体归一化 ----------

export function normalizeRun(raw: unknown): WorkflowRun {
  const r = asRaw(raw)
  return {
    id: asNumber(r.id),
    case_id: asNumber(r.case_id),
    thread_id: asString(r.thread_id),
    status: asString(r.status, "queued") as WorkflowRunStatus,
    workflow_version: asString(r.workflow_version),
    state_schema_version: asNumber(r.state_schema_version, 1),
    policy_version: asString(r.policy_version),
    prompt_bundle_version: asString(r.prompt_bundle_version),
    revision: asNumber(r.revision, 1),
    current_stage: asString(r.current_stage),
    current_node: asString(r.current_node),
    progress: asNumber(r.progress),
    // 后端字段名为 started_at / finished_at
    started_at: asString(r.started_at),
    completed_at: asStringOrNull(r.finished_at ?? r.completed_at),
    error_message: asStringOrNull(r.error_message),
  }
}

export function normalizeStage(raw: unknown): WorkflowStage {
  const r = asRaw(raw)
  const quality = asRaw(r.quality)
  // 后端 stage.name 存的是业务阶段键；label 是中文显示名
  const key = asString(r.key || r.name) as BusinessStageKey
  return {
    key,
    name: asString(r.label || r.name, key),
    status: mapStageStatus(r.status),
    quality_score: asNumberOrNull(r.quality_score ?? quality.score),
    issue_count: asNumber(r.issue_count),
    progress: asNumber(r.progress),
    nodes: asArray(r.nodes).map((n) => asString(n)),
  }
}

export function normalizeArtifact(raw: unknown): WorkflowArtifact {
  const r = asRaw(raw)
  return {
    id: asNumber(r.id),
    run_id: asNumber(r.run_id ?? r.workflow_run_id),
    kind: asString(r.kind || r.artifact_type) as WorkflowArtifactKind,
    stage: asString(r.stage),
    status: mapArtifactStatus(r.status),
    source_refs: asNumberArray(r.source_refs),
    summary: asString(r.summary),
    payload: asRaw(r.payload ?? r.content),
    created_at: asString(r.created_at),
    updated_at: asStringOrNull(r.updated_at ?? r.stale_at),
  }
}

export function normalizeIntervention(raw: unknown): WorkflowIntervention | null {
  if (!raw || typeof raw !== "object") return null
  const r = asRaw(raw)
  if (asNumberOrNull(r.id) == null) return null
  return {
    id: asNumber(r.id),
    run_id: asNumber(r.run_id ?? r.workflow_run_id),
    intervention_type: asString(r.intervention_type, "quality_review") as InterventionType,
    stage: asString(r.stage),
    status: asString(r.status, "pending") as InterventionStatus,
    base_revision: asNumber(r.base_revision),
    form_schema: asRaw(r.form_schema),
    initial_values: asRaw(r.initial_values),
    impact: asRaw(r.impact),
    created_at: asString(r.created_at),
    submitted_at: asStringOrNull(r.submitted_at),
    // input-quality-guard：后端从 impact 派生 reason/diagnostics，回退到 impact 内嵌值
    reason: asString(r.reason) || asString(asRaw(r.impact).reason) || undefined,
    diagnostics: asRaw(r.diagnostics ?? asRaw(r.impact).diagnostics),
  }
}

export function normalizeIssue(raw: unknown): Issue {
  const r = asRaw(raw)
  return {
    code: asString(r.code, "issue"),
    message: asString(r.message),
    severity: asString(r.severity, "info") as IssueSeverity,
    evidence_id: asNumberOrNull(r.evidence_id),
    stage: asStringOrNull(r.stage),
    recoverable: asBool(r.recoverable),
  }
}

function normalizeActions(raw: unknown): WorkflowAllowedActions {
  const r = asRaw(raw)
  return {
    can_pause: asBool(r.can_pause),
    can_resume: asBool(r.can_resume),
    can_cancel: asBool(r.can_cancel),
    can_retry: asBool(r.can_retry),
    can_restart_from_stage: asBool(r.can_restart_from_stage),
  }
}

// ---------- 快照归一化 ----------

export function normalizeSnapshot(raw: unknown): SnapshotResponse {
  const r = asRaw(raw)
  return {
    run: normalizeRun(r.run),
    stages: asArray(r.stages).map(normalizeStage),
    active_intervention: normalizeIntervention(r.active_intervention),
    artifacts: asArray(r.artifacts).map(normalizeArtifact),
    issues: asArray(r.issues).map(normalizeIssue),
    actions: normalizeActions(r.actions),
  }
}
