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
