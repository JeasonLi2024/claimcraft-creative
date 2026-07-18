// 工作流类型定义
// 对齐后端 NodeResult / QualityReport / Issue / Provenance / Warning / Metrics 模型
// 以及 spec.md 中的 WorkflowRun / WorkflowArtifact / WorkflowIntervention 模型
// 字段名保持 snake_case 以与后端 Pydantic 模型返回的 JSON 一致

// ===== 节点统一输出契约（对齐后端 NodeResult）=====

export type IssueSeverity = 'info' | 'warning' | 'blocking'

export interface Metrics {
  duration_ms: number
  model_calls: number
  api_calls: number
  tokens_used: number
  retries: number
}

export interface ProvenanceItem {
  node: string
  evidence_id?: number | null
  field_name?: string | null
  source_ref: string
  ts: string // ISO 8601
}

export interface Warning {
  code: string
  message: string
  severity: IssueSeverity
  evidence_id?: number | null
  stage?: string | null
}

export interface Issue {
  code: string
  message: string
  severity: IssueSeverity
  evidence_id?: number | null
  stage?: string | null
  recoverable: boolean
}

export interface QualityReport {
  score: number // 0-1
  coverage: number // 0-1
  status: 'pass' | 'warn' | 'fail'
  blocking_issues: Issue[]
  details: Record<string, unknown>
}

export interface NodeResult {
  node: string
  data: Record<string, unknown>
  quality: QualityReport
  warnings: Warning[]
  errors: Issue[]
  provenance: ProvenanceItem[]
  metrics: Metrics
}

// ===== 工作流运行实例（对齐后端 WorkflowRun，Task 3.1 引入）=====

export type WorkflowRunStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'pausing'
  | 'waiting_user'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export interface WorkflowRun {
  id: number
  case_id: number
  thread_id: string // 格式: case-{case_id}-run-{run_id}
  status: WorkflowRunStatus
  workflow_version: string
  state_schema_version: number
  policy_version: string
  prompt_bundle_version: string
  revision: number
  current_stage: string
  current_node: string
  progress: number // 0-1
  started_at: string
  completed_at?: string | null
  error_message?: string | null
}

// ===== 工作流产物（对齐后端 WorkflowArtifact，Task 3.1 引入）=====

export type WorkflowArtifactKind =
  | 'preclassify'
  | 'ocr'
  | 'classify'
  | 'extract'
  | 'evidence_chain'
  | 'complaint'
  | 'respond_complaint'

export type WorkflowArtifactStatus = 'active' | 'stale' | 'archived'

export interface WorkflowArtifact {
  id: number
  run_id: number
  kind: WorkflowArtifactKind
  stage: string // 材料理解 / 事实核对 / 案件组织 / 文书生成
  status: WorkflowArtifactStatus
  source_refs: number[] // 上游 artifact_ids
  summary: string
  payload: Record<string, unknown>
  created_at: string
  updated_at?: string | null
}

// ===== 工作流介入（对齐后端 WorkflowIntervention，Task 2.1 引入）=====

export type InterventionType = 'quality_review' | 'user_pause'
export type InterventionStatus = 'pending' | 'submitted' | 'cancelled' | 'expired'

export interface WorkflowIntervention {
  id: number
  run_id: number
  intervention_type: InterventionType
  stage: string
  status: InterventionStatus
  base_revision: number
  form_schema: Record<string, unknown>
  initial_values: Record<string, unknown>
  impact: Record<string, unknown>
  created_at: string
  submitted_at?: string | null
}

// ===== 业务阶段（4 阶段聚合）=====

export type BusinessStageKey =
  | 'material_understanding' // 材料理解 (preclassify+ocr+classify)
  | 'fact_checking' // 事实核对 (extract+review)
  | 'case_organization' // 案件组织 (evidence_chain)
  | 'document_generation' // 文书生成 (complaint/respond_complaint)

export interface WorkflowStage {
  key: BusinessStageKey
  name: string // 中文显示名
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  quality_score?: number | null
  issue_count: number
  progress: number // 0-1
  nodes: string[] // 包含的节点名列表
}

// ===== 运行快照（Snapshot API 返回）=====

export interface WorkflowAllowedActions {
  can_pause: boolean
  can_resume: boolean
  can_cancel: boolean
  can_retry: boolean
  can_restart_from_stage: boolean
}

export interface WorkflowRunSummary {
  id: number
  case_id: number
  status: WorkflowRunStatus
  current_stage: string
  progress: number
  started_at: string
  completed_at?: string | null
}

export interface SnapshotSchema {
  run: WorkflowRun
  stages: WorkflowStage[]
  artifacts: WorkflowArtifact[]
  active_intervention: WorkflowIntervention | null
  issues: Issue[]
  actions: WorkflowAllowedActions
  latest_event_id?: number | null
  snapshot_revision: number
}

export interface WorkflowRunState {
  current_run: WorkflowRun | null
  stages: WorkflowStage[]
  artifacts: WorkflowArtifact[]
  active_intervention: WorkflowIntervention | null
  issues: Issue[]
  actions: WorkflowAllowedActions
  connection: 'connected' | 'reconnecting' | 'disconnected' | 'fatal_error'
  latest_event_id: number | null
  snapshot_revision: number
}
