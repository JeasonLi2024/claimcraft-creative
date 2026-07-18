import apiClient from "./api-client"
import type {
  User, UserSummary, UserPreferences, UserProfileUpdateDTO, UserSession,
  LoginDTO, RegisterDTO, AuthResponse, RefreshResponse,
  LogoutAllResponse, ChangePasswordDTO, ChangePasswordResponse,
  AvatarMutationResponse, EmailCodeSendDTO, EmailCodeSendResponse, EmailCodeVerifyDTO,
  RegisterEmailCodeVerifyDTO, EmailCodeVerifyResponse, LoginEmailCodeDTO,
  PasswordResetVerifyDTO, PasswordResetConfirmDTO, PasswordResetConfirmResponse,
  EmailChangeRequestDTO, EmailChangeConfirmDTO, EmailUserMutationResponse,
  Case, CaseCreateDTO, Evidence, TimelineNode,
  ComplaintData, MaskResult, StatusLog,
  ExtractedField, CasePreset, DashboardStats,
} from "@/types"
import type { Correction, StageEdits, WorkflowReplay, WorkflowStateResponse } from "@/lib/workflow-events"
import type {
  WorkflowRun,
  WorkflowStage,
  WorkflowArtifact,
  WorkflowIntervention,
  WorkflowAllowedActions,
  Issue,
} from "@/types/workflow"

// Auth
export const authApi = {
  login: (data: LoginDTO) =>
    apiClient.post<AuthResponse>("/auth/login/", data).then((r) => r.data),
  sendLoginCode: (data: EmailCodeSendDTO) =>
    apiClient.post<EmailCodeSendResponse>("/auth/login/send-code/", data).then((r) => r.data),
  loginWithEmailCode: (data: LoginEmailCodeDTO) =>
    apiClient.post<AuthResponse>("/auth/login/email-code/", data).then((r) => r.data),
  sendPasswordResetCode: (data: EmailCodeSendDTO) =>
    apiClient.post<EmailCodeSendResponse>("/auth/password-reset/send-code/", data).then((r) => r.data),
  verifyPasswordResetCode: (data: PasswordResetVerifyDTO) =>
    apiClient.post<EmailCodeVerifyResponse>("/auth/password-reset/verify-code/", data).then((r) => r.data),
  confirmPasswordReset: (data: PasswordResetConfirmDTO) =>
    apiClient.post<PasswordResetConfirmResponse>("/auth/password-reset/confirm/", data).then((r) => r.data),
  register: (data: RegisterDTO) =>
    apiClient.post<UserSummary>("/auth/register/", data).then((r) => r.data),
  sendRegisterCode: (data: EmailCodeSendDTO) =>
    apiClient.post<EmailCodeSendResponse>("/auth/register/send-code/", data).then((r) => r.data),
  verifyRegisterCode: (data: RegisterEmailCodeVerifyDTO) =>
    apiClient.post<EmailCodeVerifyResponse>("/auth/register/verify-code/", data).then((r) => r.data),
  refresh: (refresh: string) =>
    apiClient.post<RefreshResponse>("/auth/refresh/", { refresh }).then((r) => r.data),
  me: () =>
    apiClient.get<User>("/auth/me/").then((r) => r.data),
  updateMe: (data: UserProfileUpdateDTO) =>
    apiClient.patch<User>("/auth/me/", data).then((r) => r.data),
  getPreferences: () =>
    apiClient.get<UserPreferences>("/auth/me/preferences/").then((r) => r.data),
  updatePreferences: (data: Partial<UserPreferences>) =>
    apiClient.patch<UserPreferences>("/auth/me/preferences/", data).then((r) => r.data),
  sendChangePasswordCode: () =>
    apiClient.post<EmailCodeSendResponse>("/auth/change-password/send-code/", {}).then((r) => r.data),
  verifyChangePasswordCode: (data: EmailCodeVerifyDTO) =>
    apiClient.post<EmailCodeVerifyResponse>("/auth/change-password/verify-code/", data).then((r) => r.data),
  changePassword: (data: ChangePasswordDTO) =>
    apiClient.post<ChangePasswordResponse>("/auth/change-password/", data).then((r) => r.data),
  logout: (refresh: string) =>
    apiClient.post<{ detail: string }>("/auth/logout/", { refresh }).then((r) => r.data),
  logoutAll: () =>
    apiClient.post<LogoutAllResponse>("/auth/logout-all/").then((r) => r.data),
  listSessions: () =>
    apiClient.get<UserSession[]>("/auth/sessions/").then((r) => r.data),
  revokeSession: (sessionId: number) =>
    apiClient.delete<{ detail: string; session_id: number }>(`/auth/sessions/${sessionId}/`).then((r) => r.data),
  uploadAvatar: (file: File) => {
    const formData = new FormData()
    formData.append("avatar", file)
    return apiClient.post<AvatarMutationResponse>("/auth/me/avatar/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then((r) => r.data)
  },
  deleteAvatar: () =>
    apiClient.delete<AvatarMutationResponse>("/auth/me/avatar/").then((r) => r.data),
  sendCurrentEmailCode: () =>
    apiClient.post<EmailCodeSendResponse>("/auth/me/email/send-code/", {}).then((r) => r.data),
  verifyCurrentEmailCode: (data: EmailCodeVerifyDTO) =>
    apiClient.post<EmailUserMutationResponse>("/auth/me/email/verify/", data).then((r) => r.data),
  requestEmailChange: (data: EmailChangeRequestDTO) =>
    apiClient.post<EmailCodeSendResponse>("/auth/me/email/change/request/", data).then((r) => r.data),
  confirmEmailChange: (data: EmailChangeConfirmDTO) =>
    apiClient.post<EmailUserMutationResponse>("/auth/me/email/change/confirm/", data).then((r) => r.data),
}

// Cases
export const casesApi = {
  list: (params?: Record<string, string>) =>
    apiClient.get<Case[] | { results: Case[] }>("/cases/", { params }).then((r) => {
      const data = r.data
      return Array.isArray(data) ? data : data.results || []
    }),
  get: (id: number) =>
    apiClient.get<Case>(`/cases/${id}/`).then((r) => r.data),
  create: (data: CaseCreateDTO) =>
    apiClient.post<Case>("/cases/", data).then((r) => r.data),
  update: (id: number, data: Partial<CaseCreateDTO>) =>
    apiClient.patch<Case>(`/cases/${id}/manage/`, data).then((r) => r.data),
  delete: (id: number) =>
    apiClient.delete(`/cases/${id}/manage/`).then((r) => r.data),
  transitionStatus: (id: number, data: { to_status: string; remark?: string }) =>
    apiClient.post<Case>(`/cases/${id}/status/transition/`, data).then((r) => r.data),
  statusLogs: (id: number) =>
    apiClient.get<StatusLog[] | { results: StatusLog[] }>(`/cases/${id}/status-logs/`).then((r) => {
      const data = r.data as StatusLog[] | { results: StatusLog[] }
      return Array.isArray(data) ? data : data.results || []
    }),
  presets: (caseType: string) =>
    apiClient.get<CasePreset[] | { results: CasePreset[] }>(`/case-presets/`, { params: { case_type: caseType } }).then((r) => {
      const data = r.data as CasePreset[] | { results: CasePreset[] }
      return Array.isArray(data) ? data : data.results || []
    }),
  applyPreset: (caseId: number, presetId: string) =>
    apiClient.post(`/cases/${caseId}/apply-preset/`, { preset_id: presetId }).then((r) => r.data),
}

// Evidence
export const evidenceApi = {
  list: (caseId: number) =>
    apiClient.get<Evidence[]>(`/cases/${caseId}/evidences/`).then((r) => r.data),
  add: (caseId: number, data: Partial<Evidence>) =>
    apiClient.post<Evidence>(`/cases/${caseId}/evidences/`, data).then((r) => r.data),
  delete: (id: number) =>
    apiClient.delete(`/evidences/${id}/`).then((r) => r.data),
  upload: (
    caseId: number,
    file: File,
    options?: { isPhysicalEvidence?: boolean; physicalNote?: string }
  ) => {
    const formData = new FormData()
    formData.append("image", file)
    if (options?.isPhysicalEvidence) {
      formData.append("is_physical_evidence", "true")
    }
    if (options?.physicalNote) {
      formData.append("physical_note", options.physicalNote)
    }
    return apiClient.post<Evidence>(`/cases/${caseId}/evidences/upload/`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then((r) => r.data)
  },
  getFields: (evidenceId: number) =>
    apiClient.get<ExtractedField[]>(`/evidences/${evidenceId}/extracted-fields/`).then((r) => r.data),
  updateField: (id: number, data: { field_value: string }) =>
    apiClient.patch<ExtractedField>(`/extracted-fields/${id}/`, data).then((r) => r.data),
}

// Timeline
export const timelineApi = {
  list: (caseId: number) =>
    apiClient.get<TimelineNode[]>(`/cases/${caseId}/timeline/`).then((r) => r.data),
  updateNode: (id: number, data: { event: string }) =>
    apiClient.patch<TimelineNode>(`/timeline-nodes/${id}/`, data).then((r) => r.data),
  rebuild: (caseId: number) =>
    apiClient.post<TimelineNode[]>(`/cases/${caseId}/timeline/rebuild/`).then((r) => r.data),
}

// Complaint
export const complaintApi = {
  get: (caseId: number, templateType: string) =>
    apiClient.get<ComplaintData>(`/cases/${caseId}/complaints/`, { params: { template_type: templateType } }).then((r) => r.data),
  regenerate: (caseId: number, templateType: string, tone?: string) =>
    apiClient.post<ComplaintData>(`/cases/${caseId}/complaints/regenerate/`, { template_type: templateType, ...(tone ? { tone } : {}) }).then((r) => r.data),
}

// Respond Template (反证答辩书)
export const respondApi = {
  get: (caseId: number, templateType: string) =>
    apiClient.get<ComplaintData>(`/cases/${caseId}/respond-templates/`, { params: { template_type: templateType } }).then((r) => r.data),
  regenerate: (caseId: number, templateType: string) =>
    apiClient.post<ComplaintData>(`/cases/${caseId}/respond-templates/regenerate/`, { template_type: templateType }).then((r) => r.data),
}

// Mask
export const maskApi = {
  getResults: (caseId: number) =>
    apiClient.get<{ items: MaskResult[] }>(`/cases/${caseId}/mask/`).then((r) => r.data.items || []),
  maskImages: (caseId: number) =>
    apiClient.post(`/cases/${caseId}/mask-images/`).then((r) => r.data),
}

// Export
export const exportApi = {
  exportText: (caseId: number, params: { template_type: string; masked: boolean }) =>
    apiClient.post<{ content: string; filename: string }>(`/cases/${caseId}/export/`, params, { responseType: "json" }).then((r) => r.data),
  exportPackage: (caseId: number, templateType: string) =>
    apiClient.get(`/cases/${caseId}/export/package/`, { params: { template_type: templateType }, responseType: "blob" }).then((r) => r.data),
  exportPDF: (caseId: number, templateType: string) =>
    apiClient.get(`/cases/${caseId}/export/pdf/`, { params: { template_type: templateType }, responseType: "blob" }).then((r) => r.data),
}

// Stats
export const statsApi = {
  getDashboard: () =>
    apiClient.get<DashboardStats>("/stats/dashboard/").then((r) => r.data),
}

// Workflow (SSE 工作流流式改造)
export const workflowApi = {
  start: (caseId: number, evidenceIds: number[]) =>
    apiClient
      .post<{ thread_id: string; stream_url: string }>(
        '/cases/' + caseId + '/workflow/start/',
        { evidence_ids: evidenceIds },
      )
      .then((r) => r.data),

  replay: (caseId: number) =>
    apiClient
      .get<WorkflowReplay>('/cases/' + caseId + '/workflow/replay/')
      .then((r) => r.data),

  streamUrl: (caseId: number, threadId: string) =>
    '/api/cases/' + caseId + '/workflow/stream/?thread_id=' + threadId,

  pause: (caseId: number, reason?: string) =>
    apiClient
      .post<{ status: string; thread_id: string }>(
        '/cases/' + caseId + '/workflow/pause/',
        reason ? { reason } : {},
      )
      .then((r) => r.data),

  resume: (caseId: number, corrections: Correction[]) =>
    apiClient
      .post<{ status: string; thread_id: string }>(
        '/cases/' + caseId + '/workflow/resume/',
        { corrections },
      )
      .then((r) => r.data),

  resumePaused: (caseId: number, edits: StageEdits) =>
    apiClient
      .post<{ status: string; thread_id: string }>(
        '/cases/' + caseId + '/workflow/resume/',
        { action: 'continue', edits },
      )
      .then((r) => r.data),

  cancel: (caseId: number) =>
    apiClient
      .post<{ status: string; thread_id: string | null }>('/cases/' + caseId + '/workflow/cancel/')
      .then((r) => r.data),

  state: (caseId: number) =>
    apiClient
      .get<WorkflowStateResponse>('/cases/' + caseId + '/workflow/state/')
      .then((r) => r.data),
}

// Workflow Runs (Task 3.7.1: /workflow-runs/* API 端点)
// 对齐 spec.md Requirement: Unified Snapshot API / Partial Retry / WorkflowRun Model
//
// 7 个端点：
//   POST /api/cases/{case_id}/workflow-runs/                        创建运行
//   GET  /api/workflow-runs/{run_id}/snapshot/                      获取权威快照
//   POST /api/workflow-runs/{run_id}/pause/                         暂停运行
//   POST /api/workflow-runs/{run_id}/interventions/{iid}/submit/    提交介入（409 冲突）
//   POST /api/workflow-runs/{run_id}/retry/                         局部重跑（LangGraph Time Travel）
//   POST /api/workflow-runs/{run_id}/cancel/                         取消运行
//   GET  /api/cases/{case_id}/workflow-runs/                        历史运行列表

export interface CreateRunResponse {
  run_id: number
  thread_id: string
  status: string
  stream_ticket: string
  stream_url: string
}

export interface SnapshotResponse {
  run: WorkflowRun
  stages: WorkflowStage[]
  active_intervention: WorkflowIntervention | null
  artifacts: WorkflowArtifact[]
  issues: Issue[]
  actions: WorkflowAllowedActions
}

export interface PauseRunResponse {
  status: string
  run_id: number
}

export interface SubmitInterventionResponse {
  status: string
  intervention_id: number
  stream_ticket: string
  stream_url: string
}

export interface RetryRunResponse {
  run_id: number
  thread_id: string
  parent_run_id: number
  status: string
  stream_ticket: string
  stream_url: string
}

export interface CancelRunResponse {
  status: string
  run_id: number
}

export interface WorkflowRunSummaryItem {
  id: number
  thread_id: string
  status: string
  current_stage: string
  progress: number
  revision: number
  workflow_version: string
  parent_run_id: number | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  quality_summary: Record<string, unknown>
  error_message: string
}

export interface ListRunsResponse {
  case_id: number
  runs: WorkflowRunSummaryItem[]
  active_run_id: number | null
}

export interface RevisionConflictError {
  code: "REVISION_CONFLICT"
  detail: string
  current_revision: number
}

export function isRevisionConflictError(err: unknown): err is { response: { status: 409; data: RevisionConflictError } } {
  if (typeof err !== "object" || err === null) return false
  const e = err as { response?: { status?: number; data?: unknown } }
  if (!e.response || e.response.status !== 409) return false
  const data = e.response.data
  if (typeof data !== "object" || data === null) return false
  return (data as { code?: unknown }).code === "REVISION_CONFLICT"
}

export const workflowRunApi = {
  /**
   * POST /api/cases/{case_id}/workflow-runs/
   * 创建工作流运行，返回 run_id + stream_ticket（SSE 鉴权票据）
   */
  createRun: (
    caseId: number,
    params: { evidence_ids?: number[]; run_options?: Record<string, unknown> },
  ) =>
    apiClient
      .post<CreateRunResponse>(`/cases/${caseId}/workflow-runs/`, params)
      .then((r) => r.data),

  /**
   * GET /api/workflow-runs/{run_id}/snapshot/
   * 获取权威快照：run + stages + active_intervention + artifacts + issues + actions
   */
  getSnapshot: (runId: number) =>
    apiClient
      .get<SnapshotResponse>(`/workflow-runs/${runId}/snapshot/`)
      .then((r) => r.data),

  /**
   * POST /api/workflow-runs/{run_id}/pause/
   * 请求暂停运行
   */
  pauseRun: (runId: number) =>
    apiClient
      .post<PauseRunResponse>(`/workflow-runs/${runId}/pause/`)
      .then((r) => r.data),

  /**
   * POST /api/workflow-runs/{run_id}/interventions/{intervention_id}/submit/
   * 提交介入修正值。当 base_revision 与当前 revision 不符时返回 409 + REVISION_CONFLICT。
   */
  submitIntervention: (
    runId: number,
    interventionId: number,
    submittedValues: Record<string, unknown>,
  ) =>
    apiClient
      .post<SubmitInterventionResponse>(
        `/workflow-runs/${runId}/interventions/${interventionId}/submit/`,
        { submitted_values: submittedValues },
      )
      .then((r) => r.data),

  /**
   * POST /api/workflow-runs/{run_id}/retry/
   * 局部重跑：基于 LangGraph Time Travel 从 from_stage fork 新运行。
   * 返回新 run_id + parent_run_id + stream_ticket。
   */
  retryRun: (
    runId: number,
    params: {
      from_stage: string
      preserve_user_confirmed?: boolean
      fork_state_overrides?: Record<string, unknown>
    },
  ) =>
    apiClient
      .post<RetryRunResponse>(`/workflow-runs/${runId}/retry/`, params)
      .then((r) => r.data),

  /**
   * POST /api/workflow-runs/{run_id}/cancel/
   * 取消运行
   */
  cancelRun: (runId: number) =>
    apiClient
      .post<CancelRunResponse>(`/workflow-runs/${runId}/cancel/`)
      .then((r) => r.data),

  /**
   * GET /api/cases/{case_id}/workflow-runs/
   * 获取案件所有历史运行列表 + 当前活动 run_id
   */
  listRuns: (caseId: number) =>
    apiClient
      .get<ListRunsResponse>(`/cases/${caseId}/workflow-runs/`)
      .then((r) => r.data),

  /**
   * POST /api/workflow-runs/{run_id}/stream-ticket/
   * 为已存在的运行签发一次性 SSE 票据（页面加载 / 刷新 / 重连 / 切换运行时用）。
   */
  streamTicket: (runId: number) =>
    apiClient
      .post<{ run_id: number; stream_ticket: string; stream_url: string }>(
        `/workflow-runs/${runId}/stream-ticket/`,
      )
      .then((r) => r.data),

  /**
   * 构造 SSE 事件流 URL（用于 FetchStreamSSEClient）。
   * stream_url 通常由 createRun / submitIntervention / retryRun 返回。
   * 此处提供基于 run_id 的默认构造，便于直接连接已有运行。
   */
  buildStreamUrl: (runId: number, ticket: string) =>
    `/api/workflow-runs/${runId}/events/?ticket=${encodeURIComponent(ticket)}`,
}
