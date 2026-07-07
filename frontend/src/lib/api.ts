import apiClient from "./api-client"
import type {
  User, LoginDTO, RegisterDTO, AuthResponse,
  Case, CaseCreateDTO, Evidence, TimelineNode,
  ComplaintData, MaskResult, StatusLog,
  ExtractedField, CasePreset, DashboardStats,
} from "@/types"
import type { Correction } from "@/lib/workflow-events"

// Auth
export const authApi = {
  login: (data: LoginDTO) =>
    apiClient.post<AuthResponse>("/auth/login/", data).then((r) => r.data),
  register: (data: RegisterDTO) =>
    apiClient.post<AuthResponse>("/auth/register/", data).then((r) => r.data),
  me: () =>
    apiClient.get<User>("/auth/me/").then((r) => r.data),
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
  upload: (caseId: number, file: File) => {
    const formData = new FormData()
    formData.append("image", file)
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
  regenerate: (caseId: number, templateType: string) =>
    apiClient.post<ComplaintData>(`/cases/${caseId}/complaints/regenerate/`, { template_type: templateType }).then((r) => r.data),
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
  exportPackage: (caseId: number) =>
    apiClient.get(`/cases/${caseId}/export/package/`, { responseType: "blob" }).then((r) => r.data),
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
        `/cases/${caseId}/workflow/start/`,
        { evidence_ids: evidenceIds },
      )
      .then((r) => r.data),

  streamUrl: (caseId: number, threadId: string) =>
    `/api/cases/${caseId}/workflow/stream/?thread_id=${threadId}`,

  resume: (caseId: number, corrections: Correction[]) =>
    apiClient
      .post<{ status: string; thread_id: string }>(
        `/cases/${caseId}/workflow/resume/`,
        { corrections },
      )
      .then((r) => r.data),
}
