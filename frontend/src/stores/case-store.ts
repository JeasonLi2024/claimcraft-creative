import { create } from "zustand"
import * as api from "@/lib/api"
import type {
  Case, CaseCreateDTO, Evidence, TimelineNode,
  ComplaintData, MaskResult, StatusLog,
  ExtractedField, CasePreset, DashboardStats,
} from "@/types"

interface CaseState {
  currentCase: Case | null
  cases: Case[]
  evidences: Evidence[]
  timelineNodes: TimelineNode[]
  currentTemplate: string
  complaintData: ComplaintData | null
  maskResults: MaskResult[]
  masked: boolean
  statusLogs: StatusLog[]
  stats: DashboardStats | null
  casePresets: CasePreset[]
  presetLoading: boolean
  extractedFieldsMap: Record<string, ExtractedField[]>
  loading: boolean
  error: string | null

  fetchCases: (params?: Record<string, string>) => Promise<Case[]>
  createCase: (data: CaseCreateDTO) => Promise<Case>
  deleteCase: (id: number) => Promise<void>
  fetchCaseDetail: (id: number) => Promise<void>
  transitionCaseStatus: (id: number, data: { to_status: string; remark?: string }) => Promise<Case>
  fetchStatusLogs: (id: number) => Promise<StatusLog[]>

  fetchEvidences: (caseId: number) => Promise<void>
  addEvidence: (caseId: number, data: Partial<Evidence>) => Promise<Evidence>
  removeEvidence: (id: number) => Promise<void>
  uploadEvidence: (caseId: number, file: File) => Promise<Evidence>
  fetchExtractedFields: (evidenceId: number) => Promise<ExtractedField[]>
  updateExtractedField: (id: number, data: { field_value: string }) => Promise<ExtractedField>

  fetchTimeline: (caseId: number) => Promise<void>
  updateTimelineNode: (id: number, data: { event: string }) => Promise<TimelineNode>
  rebuildTimeline: (caseId: number) => Promise<TimelineNode[]>

  fetchComplaint: (caseId: number, templateType: string) => Promise<void>
  regenerateComplaint: (caseId: number, templateType: string) => Promise<void>

  fetchMaskResults: (caseId: number) => Promise<void>
  toggleMasked: () => void
  maskImages: (caseId: number) => Promise<void>

  exportText: (caseId: number, params: { template_type: string; masked: boolean }) => Promise<{ content: string; filename: string }>
  exportPackage: (caseId: number) => Promise<Blob>
  exportPDF: (caseId: number, templateType: string) => Promise<Blob>

  fetchStats: () => Promise<void>
  fetchCasePresets: (caseType: string) => Promise<CasePreset[]>
  applyPreset: (caseId: number, presetId: string) => Promise<void>

  clearError: () => void
}

export const useCaseStore = create<CaseState>()((set, get) => ({
  currentCase: null,
  cases: [],
  evidences: [],
  timelineNodes: [],
  currentTemplate: "platform",
  complaintData: null,
  maskResults: [],
  masked: false,
  statusLogs: [],
  stats: null,
  casePresets: [],
  presetLoading: false,
  extractedFieldsMap: {},
  loading: false,
  error: null,

  clearError: () => set({ error: null }),

  fetchCases: async (params) => {
    set({ loading: true, error: null })
    try {
      const cases = await api.casesApi.list(params)
      set({ cases })
      return cases
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取案件列表失败" })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  createCase: async (data) => {
    set({ error: null })
    try {
      const created = await api.casesApi.create(data)
      set((s) => ({ cases: [created, ...s.cases] }))
      return created
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "创建案件失败" })
      throw e
    }
  },

  deleteCase: async (id) => {
    set({ error: null })
    try {
      await api.casesApi.delete(id)
      set((s) => ({ cases: s.cases.filter((c) => c.id !== id) }))
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "删除案件失败" })
      throw e
    }
  },

  fetchCaseDetail: async (id) => {
    set({ loading: true, error: null })
    try {
      const c = await api.casesApi.get(id)
      set({ currentCase: c })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取案件详情失败" })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  transitionCaseStatus: async (id, data) => {
    set({ error: null })
    try {
      const updated = await api.casesApi.transitionStatus(id, data)
      set((s) => {
        const cases = s.cases.map((c) => (c.id === id ? { ...c, ...updated } : c))
        const currentCase = s.currentCase?.id === id ? { ...s.currentCase, ...updated } : s.currentCase
        return { cases, currentCase: currentCase as Case | null }
      })
      return updated
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "状态流转失败" })
      throw e
    }
  },

  fetchStatusLogs: async (id) => {
    set({ error: null })
    try {
      const logs = await api.casesApi.statusLogs(id)
      set({ statusLogs: logs })
      return logs
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取状态历史失败" })
      throw e
    }
  },

  fetchEvidences: async (caseId) => {
    set({ loading: true, error: null })
    try {
      const evidences = await api.evidenceApi.list(caseId)
      set({ evidences })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取证据列表失败" })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  addEvidence: async (caseId, data) => {
    set({ error: null })
    try {
      const ev = await api.evidenceApi.add(caseId, data)
      set((s) => ({ evidences: [...s.evidences, ev] }))
      return ev
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "添加证据失败" })
      throw e
    }
  },

  removeEvidence: async (id) => {
    set({ error: null })
    try {
      await api.evidenceApi.delete(id)
      set((s) => ({ evidences: s.evidences.filter((ev) => ev.id !== id) }))
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "删除证据失败" })
      throw e
    }
  },

  uploadEvidence: async (caseId, file) => {
    set({ error: null })
    try {
      const ev = await api.evidenceApi.upload(caseId, file)
      set((s) => ({ evidences: [...s.evidences, ev] }))
      return ev
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "上传证据失败" })
      throw e
    }
  },

  fetchExtractedFields: async (evidenceId) => {
    set({ error: null })
    try {
      const fields = await api.evidenceApi.getFields(evidenceId)
      set((s) => ({
        extractedFieldsMap: { ...s.extractedFieldsMap, [evidenceId]: fields },
      }))
      return fields
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取抽取字段失败" })
      throw e
    }
  },

  updateExtractedField: async (id, data) => {
    set({ error: null })
    try {
      const updated = await api.evidenceApi.updateField(id, data)
      set((s) => {
        const map = { ...s.extractedFieldsMap }
        for (const evId of Object.keys(map)) {
          const idx = map[evId].findIndex((f) => f.id === id)
          if (idx !== -1) {
            const list = map[evId].slice()
            list[idx] = { ...list[idx], ...updated }
            map[evId] = list
            break
          }
        }
        return { extractedFieldsMap: map }
      })
      return updated
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "更新抽取字段失败" })
      throw e
    }
  },

  fetchTimeline: async (caseId) => {
    set({ loading: true, error: null })
    try {
      const nodes = await api.timelineApi.list(caseId)
      set({ timelineNodes: nodes })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取时间线失败" })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  updateTimelineNode: async (id, data) => {
    set({ error: null })
    try {
      const updated = await api.timelineApi.updateNode(id, data)
      set((s) => ({
        timelineNodes: s.timelineNodes.map((n) => (n.id === id ? { ...n, ...updated } : n)),
      }))
      return updated
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "更新时间线节点失败" })
      throw e
    }
  },

  rebuildTimeline: async (caseId) => {
    set({ loading: true, error: null })
    try {
      const nodes = await api.timelineApi.rebuild(caseId)
      set({ timelineNodes: nodes })
      return nodes
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "重建时间线失败" })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  fetchComplaint: async (caseId, templateType) => {
    set({ loading: true, error: null })
    try {
      const data = await api.complaintApi.get(caseId, templateType)
      set({ complaintData: data, currentTemplate: templateType })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取投诉文本失败" })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  regenerateComplaint: async (caseId, templateType) => {
    set({ loading: true, error: null })
    try {
      const data = await api.complaintApi.regenerate(caseId, templateType)
      set({ complaintData: data, currentTemplate: templateType })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "重新生成投诉文本失败" })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  fetchMaskResults: async (caseId) => {
    set({ loading: true, error: null })
    try {
      const results = await api.maskApi.getResults(caseId)
      set({ maskResults: results })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取打码结果失败" })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  toggleMasked: () => set((s) => ({ masked: !s.masked })),

  maskImages: async (caseId) => {
    set({ error: null })
    try {
      const items = await api.maskApi.maskImages(caseId)
      const results = Array.isArray(items) ? items : items.results || items.items || []
      set((s) => {
        const evidences = s.evidences.map((ev) => {
          const match = results.find((item: any) => item.id === ev.id)
          if (match) {
            return {
              ...ev,
              masked_image: match.masked_image,
              mask_status: match.mask_status || match.masked_status || "done",
            }
          }
          return ev
        })
        return { evidences }
      })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "图片打码失败" })
      throw e
    }
  },

  exportText: async (caseId, params) => {
    set({ error: null })
    try {
      return await api.exportApi.exportText(caseId, params)
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "导出失败" })
      throw e
    }
  },

  exportPackage: async (caseId) => {
    set({ error: null })
    try {
      return await api.exportApi.exportPackage(caseId)
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "导出证据包失败" })
      throw e
    }
  },

  exportPDF: async (caseId, templateType) => {
    set({ error: null })
    try {
      return await api.exportApi.exportPDF(caseId, templateType)
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "导出 PDF 失败" })
      throw e
    }
  },

  fetchStats: async () => {
    try {
      const stats = await api.statsApi.getDashboard()
      set({ stats })
    } catch (e) {
      console.error("fetchStats error:", e)
    }
  },

  fetchCasePresets: async (caseType) => {
    set({ presetLoading: true, error: null })
    try {
      const presets = await api.casesApi.presets(caseType)
      set({ casePresets: presets })
      return presets
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取案件预设失败", casePresets: [] })
      throw e
    } finally {
      set({ presetLoading: false })
    }
  },

  applyPreset: async (caseId, presetId) => {
    set({ error: null })
    try {
      await api.casesApi.applyPreset(caseId, presetId)
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "套用预设失败" })
      throw e
    }
  },
}))
