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
  type WorkflowReplay,
  type StagePauseData,
  type StageEdits,
  type EditableStage,
  type WorkflowStateResponse,
} from "@/lib/workflow-events"
import type {
  Case, CaseCreateDTO, Evidence, TimelineNode,
  ComplaintData, MaskResult, StatusLog,
  ExtractedField, CasePreset, DashboardStats,
} from "@/types"

// SSE 客户端实例存储在模块变量中（不放 state，避免被序列化/响应式追踪）
let workflowSSEClient: WorkflowSSEClient | null = null

function connectWorkflowStream(caseId: number, threadId: string, lastEventId = 0) {
  workflowSSEClient?.close()
  useCaseStore.setState({ connectionState: "connecting", reconnectAttempt: 0 })
  const streamUrl = api.workflowApi.streamUrl(caseId, threadId)
  const token = localStorage.getItem("access_token") || undefined
  workflowSSEClient = new WorkflowSSEClient(
    streamUrl,
    {
      onEvent: (event) => useCaseStore.getState().applySSEEvent(event),
      onConnect: () =>
        useCaseStore.setState({ connectionState: "connected", reconnectAttempt: 0 }),
      onReconnect: (attempt) =>
        useCaseStore.setState({ connectionState: "reconnecting", reconnectAttempt: attempt }),
      onFatalError: (message) =>
        useCaseStore.setState((state) => ({
          connectionState: "error",
          isRunning: false,
          errors: [...state.errors, { message, recoverable: false }],
        })),
      // Task 1.11: 提供 activeRunId / expectedRevision 的实时读取闭包
      getActiveRunId: () => useCaseStore.getState().activeRunId,
      getExpectedRevision: () => useCaseStore.getState().snapshotRevision,
      // Task 1.11: revision 跳跃时触发重新获取权威快照
      onRevisionGap: async () => {
        await useCaseStore.getState().refetchSnapshot()
      },
    },
    token,
    lastEventId,
  )
  workflowSSEClient.connect()
}

function normalizePausedAfter(value: unknown): EditableStage | null {
  const node = typeof value === "string" ? value : ""
  return ["preclassify", "ocr", "classify", "extract", "evidence_chain", "complaint", "respond_complaint"].includes(node)
    ? (node as EditableStage)
    : null
}

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
  uploadEvidence: (
    caseId: number,
    file: File,
    options?: { isPhysicalEvidence?: boolean; physicalNote?: string }
  ) => Promise<Evidence>,
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
  // @deprecated Task 3.5.3：工作流状态已迁移到 `stores/workflow-run-store.ts`。
  // 以下字段保留仅为向后兼容（现有组件仍依赖），新代码应使用 `useWorkflowRunStore`。
  // 迁移完成后将整体移除。
  /** @deprecated 使用 workflow-run-store.run + connection */
  isRunning: boolean
  /** @deprecated 使用 workflow-run-store.run.thread_id */
  threadId: string | null
  /** @deprecated 使用 workflow-run-store.stages + BusinessStageStepper */
  currentNode: string | null
  /** @deprecated 使用 workflow-run-store.stages */
  nodeStates: Record<string, NodeStatus>
  /** @deprecated 使用 workflow-run-store.artifacts */
  productBlocks: ProductBlock[]
  /** @deprecated 使用 workflow-run-store.artifacts（complaint/respond_complaint kind） */
  complaintDraft: { title: string; content: string; tone: string; node?: "complaint" | "respond_complaint"; templateType?: string } | null
  /** @deprecated 使用 workflow-run-store.activeIntervention */
  reviewInterrupt: ReviewInterruptData | null
  /** @deprecated 使用 workflow-run-store.activeIntervention（intervention_type=user_pause） */
  pauseData: StagePauseData | null
  /** @deprecated 使用 workflow-run-store.run.status === 'failed' + issues */
  errors: WorkflowError[]
  /** @deprecated 使用 workflow-run-store.connection */
  connectionState: ConnectionState
  /** @deprecated 由 workflow-run-store.connection 管理 */
  reconnectAttempt: number
  /** @deprecated 使用 workflow-run-store.run.status */
  workflowStatus: NonNullable<Case["workflow_status"]>
  /** @deprecated 由 workflow-run-store 管理 */
  isRestoringWorkflow: boolean
  /** @deprecated 由 workflow-run-store 管理 */
  workflowHistoryAvailable: boolean
  /** @deprecated 使用 workflow-run-store.latestEventId */
  latestEventId: number
  /** @deprecated 由 workflow-run-store 管理（基于 run.id） */
  activeWorkflowCaseId: number | null
  /**
   * @deprecated 使用 workflow-run-store.runId
   *
   * Task 1.11: 当前活跃的 WorkflowRun id。
   * 用于 SSE 事件 run_id 检查：event.run_id 不符时丢弃事件。
   * null 表示尚未设置（旧版本后端未返回 run_id），跳过检查（向后兼容）。
   */
  activeRunId: number | null
  /**
   * @deprecated 使用 workflow-run-store（applySSEEvent 内部管理 refetch）
   *
   * Task 1.11: revision 跳跃时标记为 true，触发 getSnapshot() 重新获取权威快照后清零。
   * 组件可观察此字段显示「正在重新加载」提示。
   */
  needsSnapshotRefetch: boolean
  /**
   * @deprecated 使用 workflow-run-store.snapshotRevision
   *
   * Task 1.11: 当前期望的下一个 revision（即本地最新已处理 revision）。
   * 用于 SSE 事件 revision 检查：跳跃触发重新获取，重复/乱序丢弃。
   * 0 表示尚未处理任何 revision 事件（向后兼容旧版本后端无 revision 字段）。
   */
  snapshotRevision: number

  /** @deprecated 使用 workflowRunApi.createRun + workflow-run-store.applySnapshot */
  startWorkflow: (caseId: number, evidenceIds: number[]) => Promise<void>
  /** @deprecated 使用 workflowRunApi.getSnapshot + workflow-run-store.applySnapshot */
  restoreWorkflow: (caseId: number) => Promise<void>
  /** @deprecated 使用 workflowRunApi.submitIntervention */
  submitReviewCorrections: (caseId: number, corrections: Correction[]) => Promise<void>
  /** @deprecated 使用 workflowRunApi.pauseRun */
  requestWorkflowPause: (caseId: number, reason?: string) => Promise<void>
  /** @deprecated 使用 workflowRunApi.submitIntervention */
  resumePausedWorkflow: (caseId: number, edits: StageEdits) => Promise<void>
  /** @deprecated 使用 workflowRunApi.cancelRun */
  cancelWorkflow: (caseId: number) => Promise<void>
  /** @deprecated 使用 workflowRunApi.getSnapshot */
  fetchWorkflowState: (caseId: number) => Promise<WorkflowStateResponse>
  /** @deprecated 使用 workflow-run-store.reset */
  clearWorkflow: () => void
  /** @deprecated 使用 workflow-run-store.applySSEEvent */
  applySSEEvent: (event: SSEEvent) => void
  /**
   * @deprecated 使用 workflow-run-store（applySSEEvent 内部返回 needsSnapshotRefetch）
   *
   * Task 1.11: 重新获取权威快照（revision 跳跃时调用）。
   * 当前阶段复用 fetchWorkflowState（旧版本 state 端点），
   * Task 3.2 完成后切换为 /api/workflow-runs/{run_id}/snapshot/。
   */
  refetchSnapshot: () => Promise<void>
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
  pauseData: null,
  errors: [],
  connectionState: "idle",
  reconnectAttempt: 0,
  workflowStatus: "idle",
  isRestoringWorkflow: false,
  workflowHistoryAvailable: false,
  latestEventId: 0,
  activeWorkflowCaseId: null,
  // Task 1.11: SSE 同步规则相关字段
  activeRunId: null,
  needsSnapshotRefetch: false,
  snapshotRevision: 0,

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

  uploadEvidence: async (caseId, file, options) => {
    set({ error: null })
    try {
      const ev = await api.evidenceApi.upload(caseId, file, options)
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
    workflowSSEClient?.close()
    workflowSSEClient = null
    set({
      error: null,
      connectionState: "connecting",
      isRunning: true,
      workflowStatus: "running",
      isRestoringWorkflow: false,
      workflowHistoryAvailable: false,
      activeWorkflowCaseId: caseId,
      latestEventId: 0,
      threadId: null,
      productBlocks: [],
      nodeStates: {},
      complaintDraft: null,
      reviewInterrupt: null,
      pauseData: null,
      errors: [],
      currentNode: null,
      reconnectAttempt: 0,
      // Task 1.11: 重置 SSE 同步规则字段
      activeRunId: null,
      needsSnapshotRefetch: false,
      snapshotRevision: 0,
    })
    try {
      const { thread_id } = await api.workflowApi.start(caseId, evidenceIds)
      set({ threadId: thread_id })
      connectWorkflowStream(caseId, thread_id)
    } catch (e: any) {
      set({
        connectionState: "error",
        isRunning: false,
        workflowStatus: "failed",
        error: e.response?.data?.detail || e.message || "启动工作流失败",
      })
      throw e
    }
  },

  restoreWorkflow: async (caseId) => {
    const currentCase = get().currentCase
    if (!currentCase || currentCase.id !== caseId) return
    if (get().isRestoringWorkflow) return
    if (get().activeWorkflowCaseId === caseId && get().threadId === currentCase.thread_id) return

    workflowSSEClient?.close()
    workflowSSEClient = null
    set({
      isRestoringWorkflow: true,
      activeWorkflowCaseId: caseId,
      threadId: currentCase.thread_id || null,
      workflowStatus: currentCase.workflow_status || "idle",
      isRunning: currentCase.workflow_status === "running" || currentCase.workflow_status === "pausing",
      connectionState: "idle",
      latestEventId: 0,
      workflowHistoryAvailable: false,
      currentNode: null,
      nodeStates: {},
      productBlocks: [],
      complaintDraft: null,
      reviewInterrupt: null,
      pauseData: currentCase.workflow_status === "paused" && normalizePausedAfter(currentCase.workflow_paused_after) ? { paused_after: normalizePausedAfter(currentCase.workflow_paused_after) as EditableStage } : null,
      errors: [],
      reconnectAttempt: 0,
      // Task 1.11: 重置 SSE 同步规则字段
      activeRunId: null,
      needsSnapshotRefetch: false,
      snapshotRevision: 0,
    })

    if (!currentCase.thread_id || currentCase.workflow_status === "idle") {
      set({ isRestoringWorkflow: false })
      return
    }

    try {
      const replay: WorkflowReplay = await api.workflowApi.replay(caseId)
      // 路由切换或新一轮工作流启动后，丢弃迟到的旧恢复响应。
      if (get().activeWorkflowCaseId !== caseId || replay.thread_id !== currentCase.thread_id) return
      const replayBatchSize = 40
      for (let index = 0; index < replay.events.length; index += replayBatchSize) {
        replay.events.slice(index, index + replayBatchSize).forEach((event) => get().applySSEEvent(event))
        if (index + replayBatchSize < replay.events.length) {
          await new Promise<void>((resolve) => setTimeout(resolve, 0))
        }
      }
      const status = replay.workflow_status
      const replayError =
        status === "failed" && replay.workflow_error && get().errors.length === 0
          ? [{ message: replay.workflow_error, recoverable: false }]
          : get().errors
      const pausedAfter = normalizePausedAfter(replay.paused_after)
      let pauseState = get().pauseData
      if (status === "paused") {
        const stateData = await get().fetchWorkflowState(caseId)
        const statePausedAfter = normalizePausedAfter(stateData.workflow_paused_after)
        if (statePausedAfter) {
          pauseState = {
            paused_after: statePausedAfter,
            editable_scope: stateData.editable_scope,
            stage_products: stateData.stage_products,
          }
        }
      }
      set({
        workflowStatus: status,
        isRunning: status === "running" || status === "pausing",
        workflowHistoryAvailable: replay.history_available,
        latestEventId: replay.last_event_id,
        errors: replayError,
        pauseData: status === "paused" ? pauseState || (pausedAfter ? { paused_after: pausedAfter } : null) : get().pauseData,
        connectionState: "idle",
      })
      if ((status === "running" || status === "pausing") && replay.thread_id) {
        connectWorkflowStream(caseId, replay.thread_id, replay.last_event_id)
      }
    } catch (e: any) {
      if (get().activeWorkflowCaseId === caseId) {
        set({
          isRunning: false,
          connectionState: "error",
          error: e.response?.data?.detail || e.message || "恢复工作流展示失败",
        })
      }
    } finally {
      if (get().activeWorkflowCaseId === caseId) set({ isRestoringWorkflow: false })
    }
  },

  submitReviewCorrections: async (caseId, corrections) => {
    set({ error: null })
    try {
      const { thread_id } = await api.workflowApi.resume(caseId, corrections)
      set({
        reviewInterrupt: null,
        threadId: thread_id,
        workflowStatus: "running",
        isRunning: true,
      })
      connectWorkflowStream(caseId, thread_id, get().latestEventId)
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "提交校正失败" })
      throw e
    }
  },

  requestWorkflowPause: async (caseId, reason) => {
    set({ error: null })
    try {
      const { thread_id } = await api.workflowApi.pause(caseId, reason)
      set({
        threadId: thread_id,
        workflowStatus: "pausing",
        isRunning: true,
      })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "请求暂停失败" })
      throw e
    }
  },

  resumePausedWorkflow: async (caseId, edits) => {
    set({ error: null })
    try {
      const { thread_id } = await api.workflowApi.resumePaused(caseId, edits)
      set({
        pauseData: null,
        threadId: thread_id,
        workflowStatus: "running",
        isRunning: true,
      })
      connectWorkflowStream(caseId, thread_id, get().latestEventId)
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "继续工作流失败" })
      throw e
    }
  },

  cancelWorkflow: async (caseId) => {
    set({ error: null })
    try {
      await api.workflowApi.cancel(caseId)
      workflowSSEClient?.close()
      workflowSSEClient = null
      set({
        isRunning: false,
        currentNode: null,
        pauseData: null,
        workflowStatus: "idle",
        connectionState: "idle",
      })
    } catch (e: any) {
      set({ error: e.response?.data?.detail || e.message || "取消工作流失败" })
      throw e
    }
  },

  fetchWorkflowState: async (caseId) => {
    const stateData = await api.workflowApi.state(caseId)
    const pausedAfter = normalizePausedAfter(stateData.workflow_paused_after)
    if (pausedAfter) {
      set({
        pauseData: {
          paused_after: pausedAfter,
          editable_scope: stateData.editable_scope,
          stage_products: stateData.stage_products,
        },
        workflowStatus: stateData.workflow_status,
      })
    }
    return stateData
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
      pauseData: null,
      errors: [],
      connectionState: "idle",
      reconnectAttempt: 0,
      workflowStatus: "idle",
      isRestoringWorkflow: false,
      workflowHistoryAvailable: false,
      latestEventId: 0,
      activeWorkflowCaseId: null,
      // Task 1.11: 重置 SSE 同步规则字段
      activeRunId: null,
      needsSnapshotRefetch: false,
      snapshotRevision: 0,
    })
  },

  applySSEEvent: (event) => {
    const state = get()

    // ===== Task 1.11: 四步 SSE 同步规则检查 =====
    // Step 1: run_id 检查（向后兼容：run_id 不存在或 activeRunId 未设置时跳过）
    if (
      typeof event.run_id === "number" &&
      state.activeRunId != null &&
      event.run_id !== state.activeRunId
    ) {
      return
    }

    // Step 2: event_id 检查（已处理过的事件丢弃，原有去重逻辑）
    if (event.event_id <= state.latestEventId) return

    // Step 3: revision 检查（向后兼容：revision 不存在或 snapshotRevision 为 0 时跳过）
    if (typeof event.revision === "number" && state.snapshotRevision > 0) {
      const expected = state.snapshotRevision
      if (event.revision > expected + 1) {
        // revision 跳跃：事件丢失，设置标志并触发 getSnapshot() 重新获取权威快照
        const caseId = state.activeWorkflowCaseId
        set({ needsSnapshotRefetch: true })
        if (caseId != null) {
          // 非阻塞触发快照重新获取，完成后清除标志
          void get().fetchWorkflowState(caseId).then(() => {
            if (get().needsSnapshotRefetch) {
              set({ needsSnapshotRefetch: false })
            }
          })
        }
        return
      }
      if (event.revision <= expected) {
        // 重复或乱序事件，丢弃
        return
      }
    }

    // Step 4: 应用事件（事件类型路由 + state 更新）
    const eventType = event.event_type
    const applyUpdates: Partial<CaseState> = {
      latestEventId: event.event_id,
      workflowHistoryAvailable: true,
    }
    if (typeof event.revision === "number") {
      applyUpdates.snapshotRevision = event.revision
    }
    set(applyUpdates)
    switch (eventType) {
      case "workflow.start": {
        set({
          isRunning: true,
          threadId: (event.thread_id as string) || get().threadId,
          connectionState: "connected",
          workflowStatus: "running",
          pauseData: null,
        })
        break
      }
      case "workflow.pause_requested": {
        set({
          workflowStatus: "pausing",
          isRunning: true,
        })
        break
      }
      case "workflow.paused": {
        const pausedAfter = normalizePausedAfter(event.paused_after)
        const nodeStates = { ...get().nodeStates }
        if (pausedAfter) {
          nodeStates[pausedAfter] = {
            ...nodeStates[pausedAfter],
            status: "paused",
            completedAt: (event.ts as string) || nodeStates[pausedAfter]?.completedAt,
          }
        }
        workflowSSEClient?.close()
        workflowSSEClient = null
        set({
          currentNode: null,
          nodeStates,
          pauseData: pausedAfter
            ? {
                paused_after: pausedAfter,
                editable_scope:
                  event.editable_scope && typeof event.editable_scope === "object" && !Array.isArray(event.editable_scope)
                    ? (event.editable_scope as StagePauseData["editable_scope"])
                    : undefined,
                message: (event.message as string) || undefined,
              }
            : get().pauseData,
          connectionState: "idle",
          workflowStatus: "paused",
          isRunning: false,
        })
        break
      }
      case "workflow.resumed": {
        set({ connectionState: "connected", isRunning: true, workflowStatus: "running", pauseData: null })
        break
      }
      case "workflow.cancelled": {
        workflowSSEClient?.close()
        workflowSSEClient = null
        set({
          connectionState: "idle",
          isRunning: false,
          workflowStatus: "idle",
          currentNode: null,
          pauseData: null,
          reviewInterrupt: null,
        })
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
            node: (event.node as "complaint" | "respond_complaint" | undefined) || s.complaintDraft?.node,
            templateType: (event.template_type as string) || s.complaintDraft?.templateType,
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
            node: (event.node as "complaint" | "respond_complaint" | undefined) || "complaint",
            templateType: (event.template_type as string) || undefined,
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
      case "workflow.waiting_review": {
        workflowSSEClient?.close()
        workflowSSEClient = null
        set({ isRunning: false, currentNode: null, connectionState: "idle", workflowStatus: "waiting_review" })
        break
      }
      case "workflow.complete": {
        workflowSSEClient?.close()
        workflowSSEClient = null
        set({ isRunning: false, currentNode: null, connectionState: "idle", workflowStatus: "succeeded", pauseData: null })
        break
      }
      case "workflow.error": {
        set((s) => ({
          isRunning: false,
          currentNode: null,
          connectionState: "error",
          workflowStatus: "failed",
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

  // Task 1.11: revision 跳跃时重新获取权威快照
  refetchSnapshot: async () => {
    const caseId = get().activeWorkflowCaseId
    if (caseId == null) return
    set({ needsSnapshotRefetch: true })
    try {
      await get().fetchWorkflowState(caseId)
    } finally {
      set({ needsSnapshotRefetch: false })
    }
  },
}))
