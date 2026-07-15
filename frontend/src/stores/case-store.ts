import { create } from "zustand"
import * as api from "@/lib/api"
import { WorkflowSSEClient } from "@/lib/sse-client"
import {
  buildProductBlock,
  type SSEEvent,
  type NodeStatus,
  type ProductBlock,
  type ReviewInterruptData,
  type Correction,
  type WorkflowError,
  type ConnectionState,
} from "@/lib/workflow-events"
import type {
  Case, CaseCreateDTO, Evidence, TimelineNode,
  ComplaintData, MaskResult, StatusLog,
  ExtractedField, CasePreset, DashboardStats,
} from "@/types"

// SSE 客户端实例存储在模块变量中（不放 state，避免被序列化/响应式追踪）
let workflowSSEClient: WorkflowSSEClient | null = null

interface CaseState {
  currentCase: Case | null
  cases: Case[]
  evidences: Evidence[]
  timelineNodes: TimelineNode[]
  currentTemplate: string
  complaintData: ComplaintData | null
  respondData: ComplaintData | null
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
  fetchRespond: (caseId: number, templateType: string) => Promise<void>
  regenerateRespond: (caseId: number, templateType: string) => Promise<void>

  fetchMaskResults: (caseId: number) => Promise<void>
  toggleMasked: () => void
  maskImages: (caseId: number) => Promise<void>

  exportText: (caseId: number, params: { template_type: string; masked: boolean }) => Promise<{ content: string; filename: string }>
  exportPackage: (caseId: number, templateType: string) => Promise<Blob>
  exportPDF: (caseId: number, templateType: string) => Promise<Blob>

  fetchStats: () => Promise<void>
  fetchCasePresets: (caseType: string) => Promise<CasePreset[]>
  applyPreset: (caseId: number, presetId: string) => Promise<void>

  clearError: () => void

  // ---------- Workflow Slice ----------
  isRunning: boolean
  threadId: string | null
  currentNode: string | null
  nodeStates: Record<string, NodeStatus>
  productBlocks: ProductBlock[]
  complaintDraft: { title: string; content: string; tone: string } | null
  reviewInterrupt: ReviewInterruptData | null
  errors: WorkflowError[]
  connectionState: ConnectionState
  reconnectAttempt: number

  startWorkflow: (caseId: number, evidenceIds: number[]) => Promise<void>
  submitReviewCorrections: (caseId: number, corrections: Correction[]) => Promise<void>
  clearWorkflow: () => void
  applySSEEvent: (event: SSEEvent) => void
}

export const useCaseStore = create<CaseState>()((set, get) => ({
  currentCase: null,
  cases: [],
  evidences: [],
  timelineNodes: [],
  currentTemplate: "platform",
  complaintData: null,
  respondData: null,
  maskResults: [],
  masked: false,
  statusLogs: [],
  stats: null,
  casePresets: [],
  presetLoading: false,
  extractedFieldsMap: {},
  loading: false,
  error: null,

  // Workflow slice initial state
  isRunning: false,
  threadId: null,
  currentNode: null,
  nodeStates: {},
  productBlocks: [],
  complaintDraft: null,
  reviewInterrupt: null,
  errors: [],
  connectionState: "idle",
  reconnectAttempt: 0,

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

  fetchRespond: async (caseId, templateType) => {
    set({ loading: true, error: null })
    try {
      const data = await api.respondApi.get(caseId, templateType)
      set({ respondData: data })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "获取反证答辩书失败" })
      throw e
    } finally {
      set({ loading: false })
    }
  },

  regenerateRespond: async (caseId, templateType) => {
    set({ loading: true, error: null })
    try {
      const data = await api.respondApi.regenerate(caseId, templateType)
      set({ respondData: data })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "重新生成反证答辩书失败" })
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

  exportPackage: async (caseId, templateType) => {
    set({ error: null })
    try {
      return await api.exportApi.exportPackage(caseId, templateType)
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

  // ---------- Workflow Slice 实现 ----------

  startWorkflow: async (caseId, evidenceIds) => {
    set({
      error: null,
      connectionState: "connecting",
      isRunning: true,
      productBlocks: [],
      nodeStates: {},
      complaintDraft: null,
      reviewInterrupt: null,
      errors: [],
      currentNode: null,
      reconnectAttempt: 0,
    })
    try {
      const { thread_id } = await api.workflowApi.start(caseId, evidenceIds)
      set({ threadId: thread_id, connectionState: "connected" })

      // 关闭旧连接（如有）
      workflowSSEClient?.close()

      const streamUrl = api.workflowApi.streamUrl(caseId, thread_id)
      workflowSSEClient = new WorkflowSSEClient(streamUrl, {
        onEvent: (event) => get().applySSEEvent(event),
        onConnect: () => set({ connectionState: "connected", reconnectAttempt: 0 }),
        onReconnect: (attempt) =>
          set({ connectionState: "reconnecting", reconnectAttempt: attempt }),
        onFatalError: (message) =>
          set((s) => ({
            connectionState: "error",
            isRunning: false,
            errors: [...s.errors, { message, recoverable: false }],
          })),
      })
      workflowSSEClient.connect()
    } catch (e: any) {
      set({
        connectionState: "error",
        isRunning: false,
        error: e.response?.data?.detail || e.message || "启动工作流失败",
      })
      throw e
    }
  },

  submitReviewCorrections: async (caseId, corrections) => {
    set({ error: null })
    try {
      await api.workflowApi.resume(caseId, corrections)
      // resume 成功后关闭校正面板，等待 review.resumed 事件
      set({ reviewInterrupt: null })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "提交校正失败" })
      throw e
    }
  },

  clearWorkflow: () => {
    workflowSSEClient?.close()
    workflowSSEClient = null
    set({
      isRunning: false,
      threadId: null,
      currentNode: null,
      nodeStates: {},
      productBlocks: [],
      complaintDraft: null,
      reviewInterrupt: null,
      errors: [],
      connectionState: "idle",
      reconnectAttempt: 0,
    })
  },

  applySSEEvent: (event) => {
    const eventType = event.event_type
    switch (eventType) {
      case "workflow.start": {
        set({
          isRunning: true,
          threadId: (event.thread_id as string) || get().threadId,
          connectionState: "connected",
        })
        break
      }
      case "workflow.resumed": {
        set({ connectionState: "connected", isRunning: true })
        break
      }
      case "node.start": {
        const node = event.node as string
        set((s) => ({
          currentNode: node,
          nodeStates: {
            ...s.nodeStates,
            [node]: { status: "running", startedAt: event.ts as string },
          },
        }))
        break
      }
      case "node.progress": {
        // 里程碑进度通知：更新当前节点的进度阶段信息
        const node = event.node as string
        const stage = event.stage as string
        const message = event.message as string
        set((s) => ({
          nodeStates: {
            ...s.nodeStates,
            [node]: {
              ...s.nodeStates[node],
              status: "running",
              progressStage: stage,
              progressMessage: message,
            },
          },
        }))
        break
      }
      case "node.complete": {
        const node = event.node as string
        const products = (event.products as Record<string, unknown>) || {}
        const productBlock = buildProductBlock(node, products)
        set((s) => ({
          currentNode: null,
          nodeStates: {
            ...s.nodeStates,
            [node]: {
              status: "completed",
              completedAt: event.ts as string,
              durationMs: event.duration_ms as number,
              products,
            },
          },
          productBlocks: [
            ...s.productBlocks.map((b, i) =>
              i === s.productBlocks.length - 1 ? { ...b, collapsed: true } : b,
            ),
            { ...productBlock, collapsed: false },
          ],
        }))
        break
      }
      case "node.error": {
        const node = event.node as string
        set((s) => ({
          nodeStates: {
            ...s.nodeStates,
            [node]: {
              ...s.nodeStates[node],
              status: "error",
              error: event.message as string,
            },
          },
          errors: [
            ...s.errors,
            {
              message: event.message as string,
              node,
              recoverable: event.recoverable as boolean,
            },
          ],
        }))
        break
      }
      case "complaint.token": {
        const delta = (event.delta as string) || ""
        set((s) => ({
          complaintDraft: {
            title: s.complaintDraft?.title || "",
            content: (s.complaintDraft?.content || "") + delta,
            tone: s.complaintDraft?.tone || "",
          },
        }))
        break
      }
      case "complaint.done": {
        set({
          complaintDraft: {
            title: (event.title as string) || "",
            content: (event.final_content as string) || "",
            tone: (event.tone as string) || "",
          },
        })
        break
      }
      case "review.interrupt": {
        set({ reviewInterrupt: event as unknown as ReviewInterruptData })
        break
      }
      case "review.resumed": {
        set({ reviewInterrupt: null })
        break
      }
      case "review.skipped": {
        const nodeStates = { ...get().nodeStates }
        nodeStates["review"] = { status: "skipped" }
        set({ nodeStates })
        break
      }
      case "workflow.complete": {
        set({ isRunning: false, currentNode: null, connectionState: "idle" })
        break
      }
      case "workflow.error": {
        set((s) => ({
          isRunning: false,
          currentNode: null,
          connectionState: "error",
          errors: [
            ...s.errors,
            {
              message: (event.message as string) || "工作流错误",
              node: event.node as string | undefined,
              recoverable: (event.recoverable as boolean) ?? false,
            },
          ],
        }))
        break
      }
      case "workflow.heartbeat": {
        // 心跳事件，无需状态变更
        break
      }
      default: {
        // 未知事件类型，忽略
        break
      }
    }
  },
}))
