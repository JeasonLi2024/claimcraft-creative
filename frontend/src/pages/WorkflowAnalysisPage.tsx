// 工作流分析工作台（新前端统一工作流 UI 的接入页）
//
// 数据流：
//   listRuns → active_run_id → streamTicket + getSnapshot(归一化) → applySnapshot → SSE
//   SSE 事件：stage.* 本地即时更新；其余结构性事件触发去抖 snapshot 重取（权威来源）
//
// 契约对齐：后端 snapshot / 事件形状经 lib/workflow-adapters 归一化为前端类型。
// 新旧工作流统一在本页展示：WorkflowRun 使用新工作台，历史 thread 使用兼容面板恢复。
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useParams, Link } from "react-router"
import { Loader2, Play, History, Workflow, RefreshCw, AlertTriangle } from "lucide-react"

import { useCaseStore } from "@/stores/case-store"
import { useAuthStore } from "@/stores/auth-store"
import { useWorkflowRunStore } from "@/stores/workflow-run-store"
import {
  useInterventionStore,
  configureInterventionSubmitHandler,
} from "@/stores/intervention-store"
import { workflowRunApi, isRevisionConflictError } from "@/lib/api"
import { documentApi } from "@/lib/document-api"
import { createSSEClient, type SSEClient } from "@/lib/sse-client"
import { normalizeSnapshot } from "@/lib/workflow-adapters"
import type { QualityReport, Issue, WorkflowArtifact } from "@/types/workflow"
import type { DocumentDetail } from "@/types/document"

import { WorkflowCommandBar, type ConnectionStatus } from "@/components/workflow/WorkflowCommandBar"
import { BusinessStageStepper } from "@/components/workflow/BusinessStageStepper"
import { CurrentActivityPanel } from "@/components/workflow/CurrentActivityPanel"
import { QualitySummary } from "@/components/workflow/QualitySummary"
import { IssueList } from "@/components/workflow/IssueList"
import { InterventionPanel } from "@/components/workflow/InterventionPanel"
import { ArtifactTimeline } from "@/components/workflow/ArtifactTimeline"
import { RunConfigurationDrawer } from "@/components/workflow/RunConfigurationDrawer"
import { RunHistoryDrawer } from "@/components/workflow/RunHistoryDrawer"
import { WorkflowRecoveryPanel } from "@/components/workflow/WorkflowRecoveryPanel"
import { DocumentEditor } from "@/components/workflow/DocumentEditor"
import { WorkflowStreamPanel } from "@/components/workflow/WorkflowStreamPanel"

// 文书产物类型 → DocumentEditor.fromStage
const DOC_ARTIFACT_KINDS = new Set<WorkflowArtifact["kind"]>([
  "complaint_draft",
  "respond_complaint_draft",
])

function findDocumentArtifact(artifacts: WorkflowArtifact[]): WorkflowArtifact | null {
  // 取最近一个文书产物（document_generation 阶段）
  for (let i = artifacts.length - 1; i >= 0; i--) {
    const a = artifacts[i]
    if (DOC_ARTIFACT_KINDS.has(a.kind) || a.stage === "document_generation") return a
  }
  return null
}

// store 连接态 → CommandBar 连接态
function toConnectionStatus(c: string): ConnectionStatus {
  if (c === "connected") return "connected"
  if (c === "reconnecting" || c === "connecting") return "reconnecting"
  if (c === "error") return "fatal_error"
  return "disconnected"
}

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled"])
// 触发 snapshot 去抖重取的结构性事件（stage.started/progress 仅本地更新，不在此列）
const REFETCH_EVENTS = new Set([
  "stage.completed",
  "stage.quality_changed",
  "review.interrupt",
  "review.resumed",
])

export default function WorkflowAnalysisPage() {
  const { caseId: caseIdParam } = useParams<{ caseId: string }>()
  const caseId = Number(caseIdParam)

  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchEvidences = useCaseStore((s) => s.fetchEvidences)
  const evidences = useCaseStore((s) => s.evidences)
  const currentCase = useCaseStore((s) => s.currentCase)

  const run = useWorkflowRunStore((s) => s.run)
  const runId = useWorkflowRunStore((s) => s.runId)
  const stages = useWorkflowRunStore((s) => s.stages)
  const artifacts = useWorkflowRunStore((s) => s.artifacts)
  const issues = useWorkflowRunStore((s) => s.issues)
  const actions = useWorkflowRunStore((s) => s.actions)
  const activeIntervention = useWorkflowRunStore((s) => s.activeIntervention)
  const connection = useWorkflowRunStore((s) => s.connection)
  const fatalError = useWorkflowRunStore((s) => s.fatalError)
  const applySnapshot = useWorkflowRunStore((s) => s.applySnapshot)
  const applySSEEvent = useWorkflowRunStore((s) => s.applySSEEvent)
  const setConnection = useWorkflowRunStore((s) => s.setConnection)
  const resetRunStore = useWorkflowRunStore((s) => s.reset)

  const setIntervention = useInterventionStore((s) => s.setIntervention)
  const setCurrentRevision = useInterventionStore((s) => s.setCurrentRevision)
  const draftValues = useInterventionStore((s) => s.draftValues)
  const validationErrors = useInterventionStore((s) => s.validationErrors)
  const revisionConflict = useInterventionStore((s) => s.revisionConflict)
  const updateDraftValue = useInterventionStore((s) => s.updateDraftValue)
  const submitDraft = useInterventionStore((s) => s.submitDraft)
  const setRevisionConflict = useInterventionStore((s) => s.setRevisionConflict)

  const accessToken = useAuthStore((s) => s.accessToken)

  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState<string | null>(null)
  const [showConfig, setShowConfig] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  // 连接与重取相关的可变引用
  const clientRef = useRef<SSEClient | null>(null)
  const intentionalCloseRef = useRef(false)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const refetchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const runIdRef = useRef<number | null>(null)

  useEffect(() => {
    runIdRef.current = runId
  }, [runId])

  // ---------- snapshot 重取（权威来源） ----------

  const refetchSnapshot = useCallback(
    async (targetRunId: number) => {
      try {
        const raw = await workflowRunApi.getSnapshot(targetRunId)
        applySnapshot(normalizeSnapshot(raw))
      } catch {
        // 重取失败不阻塞 UI，下一次事件会再次触发
      }
    },
    [applySnapshot],
  )

  const scheduleRefetch = useCallback(
    (targetRunId: number) => {
      if (refetchTimerRef.current) clearTimeout(refetchTimerRef.current)
      refetchTimerRef.current = setTimeout(() => {
        void refetchSnapshot(targetRunId)
      }, 400)
    },
    [refetchSnapshot],
  )

  // ---------- SSE 连接 ----------

  const closeClient = useCallback(() => {
    intentionalCloseRef.current = true
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    clientRef.current?.close()
    clientRef.current = null
  }, [])

  const connectStream = useCallback(
    (targetRunId: number, streamUrl: string) => {
      // 关闭旧连接
      if (clientRef.current) {
        intentionalCloseRef.current = true
        clientRef.current.close()
        clientRef.current = null
      }
      intentionalCloseRef.current = false
      setConnection("connecting")

      const client = createSSEClient({
        url: streamUrl,
        accessToken: accessToken ?? undefined,
        onConnect: () => {
          reconnectAttemptsRef.current = 0
          setConnection("connected")
        },
        onEvent: (event) => {
          const result = applySSEEvent(event)
          const type = String(event.event_type ?? "")
          if (result.needsSnapshotRefetch || REFETCH_EVENTS.has(type)) {
            scheduleRefetch(targetRunId)
          }
        },
        onDisconnect: (reason) => {
          if (intentionalCloseRef.current || reason === "aborted") {
            setConnection("disconnected")
            return
          }
          // 运行未结束则退避重连（最多 5 次），并重新签发票据
          const currentRun = useWorkflowRunStore.getState().run
          if (currentRun && TERMINAL_STATUSES.has(currentRun.status)) {
            setConnection("disconnected")
            return
          }
          if (reconnectAttemptsRef.current >= 5) {
            setConnection("error")
            return
          }
          reconnectAttemptsRef.current += 1
          setConnection("reconnecting")
          const delay = Math.min(1000 * 2 ** (reconnectAttemptsRef.current - 1), 15000)
          reconnectTimerRef.current = setTimeout(() => {
            void reconnectStream(targetRunId)
          }, delay)
        },
        onError: () => setConnection("error"),
        getActiveRunId: () => runIdRef.current,
        getExpectedRevision: () => useWorkflowRunStore.getState().snapshotRevision,
        onRevisionGap: () => scheduleRefetch(targetRunId),
      })
      clientRef.current = client
      void client.connect()
    },
    [accessToken, applySSEEvent, scheduleRefetch, setConnection],
  )

  // 重新签发票据后重连（用于运行中断线或运行切换）
  const reconnectStream = useCallback(
    async (targetRunId: number) => {
      try {
        const { stream_url } = await workflowRunApi.streamTicket(targetRunId)
        connectStream(targetRunId, stream_url)
      } catch {
        setConnection("error")
      }
    },
    [connectStream, setConnection],
  )

  // ---------- 加载运行 + 首次连接 ----------

  const loadRun = useCallback(
    async (targetRunId: number, streamUrl?: string) => {
      await refetchSnapshot(targetRunId)
      const status = useWorkflowRunStore.getState().run?.status
      // 已结束的运行只读展示，不建立 SSE
      if (status && TERMINAL_STATUSES.has(status)) {
        setConnection("disconnected")
        return
      }
      if (streamUrl) {
        connectStream(targetRunId, streamUrl)
      } else {
        await reconnectStream(targetRunId)
      }
    },
    [refetchSnapshot, connectStream, reconnectStream, setConnection],
  )

  // 初始化：案件详情 + 证据 + 活动运行
  useEffect(() => {
    if (!Number.isFinite(caseId)) return
    let cancelled = false
    setLoading(true)
    setPageError(null)
    ;(async () => {
      try {
        await Promise.all([fetchCaseDetail(caseId), fetchEvidences(caseId)])
        const list = await workflowRunApi.listRuns(caseId)
        if (cancelled) return
        const active = list.active_run_id ?? list.runs[0]?.id ?? null
        if (active != null) {
          await loadRun(active)
        }
      } catch (e) {
        if (!cancelled) {
          setPageError(e instanceof Error ? e.message : "加载工作流分析失败")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  // 卸载清理：断开连接 + 重置 store + 注销介入提交处理器
  useEffect(() => {
    return () => {
      closeClient()
      if (refetchTimerRef.current) clearTimeout(refetchTimerRef.current)
      configureInterventionSubmitHandler(null)
      resetRunStore()
      setIntervention(null)
    }
  }, [closeClient, resetRunStore, setIntervention])

  // 同步 activeIntervention → 介入 store（草稿持久化 + revision 冲突检测）
  useEffect(() => {
    setIntervention(activeIntervention)
  }, [activeIntervention, setIntervention])

  const snapshotRevision = useWorkflowRunStore((s) => s.snapshotRevision)
  useEffect(() => {
    setCurrentRevision(snapshotRevision)
  }, [snapshotRevision, setCurrentRevision])

  // 介入提交处理器：提交 → 归一化重取 + 重连；409 冲突落到 revisionConflict
  useEffect(() => {
    configureInterventionSubmitHandler(async (intervention, values) => {
      try {
        const resp = await workflowRunApi.submitIntervention(
          intervention.run_id,
          intervention.id,
          values,
        )
        await refetchSnapshot(intervention.run_id)
        if (resp.stream_url) connectStream(intervention.run_id, resp.stream_url)
      } catch (e) {
        if (isRevisionConflictError(e)) {
          setRevisionConflict({
            baseRevision: intervention.base_revision,
            currentRevision: e.response.data.current_revision,
          })
        }
        throw e
      }
    })
    return () => configureInterventionSubmitHandler(null)
  }, [refetchSnapshot, connectStream, setRevisionConflict])

  // ---------- 派生：质量概览 ----------

  const quality = useMemo<QualityReport | null>(() => {
    const scored = stages.filter((s) => typeof s.quality_score === "number")
    const blocking = issues.filter((i) => i.severity === "blocking")
    if (scored.length === 0 && issues.length === 0) return null
    const avg =
      scored.length > 0
        ? scored.reduce((sum, s) => sum + (s.quality_score ?? 0), 0) / scored.length
        : 0
    const status: QualityReport["status"] =
      blocking.length > 0 ? "fail" : issues.length > 0 ? "warn" : "pass"
    return {
      score: avg,
      coverage: avg,
      status,
      blocking_issues: blocking,
      details: {},
    }
  }, [stages, issues])

  // Gate 1（input-quality-guard）：从 issues 派生「证据类型匹配度偏低」橙色告警，
  // 由 classify_node 以 code=material.evidence_low_relevance 的 warning 发出。
  const qualityWarnings = useMemo(() => {
    return issues
      .filter((i) => i.code === "material.evidence_low_relevance")
      .map((i) => ({ title: "证据类型匹配度偏低", detail: i.message }))
  }, [issues])

  // ---------- 派生：文书产物 ----------

  const docArtifact = useMemo(() => findDocumentArtifact(artifacts), [artifacts])
  const documentVersionId = docArtifact
    ? (docArtifact.payload as { document_version_id?: number }).document_version_id
    : undefined
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null)
  const [isExportingDocument, setIsExportingDocument] = useState(false)
  const loadedDocKeyRef = useRef<string | null>(null)

  useEffect(() => {
    if (!runId || !docArtifact) {
      setDocumentDetail(null)
      loadedDocKeyRef.current = null
      return
    }
    const docId = documentVersionId != null ? String(documentVersionId) : String(docArtifact.id)
    const key = `${runId}:${docId}`
    if (loadedDocKeyRef.current === key) return
    loadedDocKeyRef.current = key
    let cancelled = false
    ;(async () => {
      try {
        const detail = await documentApi.getDocument(runId, docId, docArtifact)
        if (!cancelled) setDocumentDetail(detail)
      } catch {
        if (!cancelled) setDocumentDetail(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [runId, docArtifact, documentVersionId])

  // ---------- 动作 ----------

  const handlePause = useCallback(async () => {
    if (!runId) return
    try {
      await workflowRunApi.pauseRun(runId)
      scheduleRefetch(runId)
    } catch {
      /* 忽略：状态将由 snapshot 校正 */
    }
  }, [runId, scheduleRefetch])

  const handleCancel = useCallback(async () => {
    if (!runId) return
    try {
      await workflowRunApi.cancelRun(runId)
      scheduleRefetch(runId)
    } catch {
      /* 忽略 */
    }
  }, [runId, scheduleRefetch])

  const handleEvidenceClick = useCallback(
    (evidenceId: number) => {
      // 跳转证据管理页（锚点由证据页自行处理）
      window.location.assign(`/cases/${caseId}/evidence#evidence-${evidenceId}`)
    },
    [caseId],
  )

  const handleIssueEvidenceClick = useCallback(
    (issue: Issue) => {
      if (typeof issue.evidence_id === "number") handleEvidenceClick(issue.evidence_id)
    },
    [handleEvidenceClick],
  )

  // 切换到指定运行（历史抽屉）
  const handleSwitchRun = useCallback(
    async (targetRunId: number) => {
      closeClient()
      resetRunStore()
      setShowHistory(false)
      await loadRun(targetRunId)
    },
    [closeClient, resetRunStore, loadRun],
  )

  // 新建运行成功（配置抽屉）
  const handleCreateRun = useCallback(
    async (resp: { run_id: number; stream_url: string }) => {
      closeClient()
      resetRunStore()
      setShowConfig(false)
      await loadRun(resp.run_id, resp.stream_url)
    },
    [closeClient, resetRunStore, loadRun],
  )

  const handleDocumentExport = useCallback(async () => {
    if (!documentDetail || !runId || isExportingDocument) return
    setIsExportingDocument(true)
    try {
      const check = await documentApi.exportCheck(runId, documentDetail.id)
      if (check.passed) {
        window.location.assign(`/cases/${caseId}/export`)
      }
    } finally {
      setIsExportingDocument(false)
    }
  }, [caseId, documentDetail, isExportingDocument, runId])

  // 恢复面板重试成功 → 切换到 fork 出的新运行
  const handleRetrySuccess = useCallback(
    async (resp: { run_id: number; stream_url: string }) => {
      closeClient()
      resetRunStore()
      await loadRun(resp.run_id, resp.stream_url)
    },
    [closeClient, resetRunStore, loadRun],
  )

  const isFailed = run?.status === "failed"
  const hasLegacyWorkflow = Boolean(
    currentCase?.thread_id && currentCase.workflow_status && currentCase.workflow_status !== "idle",
  )

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">
      {/* 头部 */}
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#e7eee9] text-[#2f5947]">
            <Workflow className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-lg font-semibold text-foreground">工作流分析</h1>
            <p className="text-sm text-muted-foreground">
              {currentCase?.title ?? `案件 #${caseId}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowHistory(true)}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-xl border border-[#d9ddd5] bg-white px-3.5 text-sm font-medium hover:bg-[#f1f2ee]"
          >
            <History className="h-4 w-4" aria-hidden="true" />
            运行历史
          </button>
          <button
            type="button"
            onClick={() => setShowConfig(true)}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-[#181b1a] px-3.5 text-sm font-semibold text-white hover:bg-[#2b302d]"
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            开始分析
          </button>
        </div>
      </header>

      {loading ? (
        <div className="flex items-center justify-center py-24 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" aria-hidden="true" />
          正在加载运行状态…
        </div>
      ) : pageError ? (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          <AlertTriangle className="h-4 w-4" aria-hidden="true" />
          {pageError}
        </div>
      ) : !run ? (
        hasLegacyWorkflow ? (
          <section className="space-y-4 rounded-2xl border border-[#e2e6df] bg-white p-4 sm:p-5" aria-label="历史工作流分析">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#2f5947]">历史分析</p>
              <h2 className="mt-1 text-lg font-semibold">工作流分析记录与输出</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                该案件由旧版工作流生成，历史节点、实时状态和具体输出已迁移至本页面展示。
              </p>
            </div>
            <WorkflowStreamPanel caseId={caseId} />
          </section>
        ) : (
          <div className="rounded-2xl border border-dashed border-[#bdc6be] bg-white px-6 py-16 text-center">
            <img
              src="/空状态插画.png"
              alt=""
              aria-hidden="true"
              className="mx-auto mb-5 w-48 max-w-[70%] object-contain"
            />
            <h3 className="text-lg font-semibold">尚未发起工作流分析</h3>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
              选择参与分析的证据并开始，系统将依次完成材料理解、事实核对、案件组织与文书生成。
            </p>
            <div className="mt-6 flex justify-center gap-3">
              <button
                type="button"
                onClick={() => setShowConfig(true)}
                className="inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-[#181b1a] px-4 text-sm font-semibold text-white hover:bg-[#2b302d]"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                开始分析
              </button>
              <Link
                to={`/cases/${caseId}/evidence`}
                className="inline-flex min-h-[44px] items-center rounded-xl border border-[#d9ddd5] bg-white px-4 text-sm font-medium hover:bg-[#f1f2ee]"
              >
                先去上传证据
              </Link>
            </div>
          </div>
        )
      ) : (
        <div className="space-y-5">
          {fatalError && (
            <div
              role="alert"
              className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            >
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              {fatalError}
              <button
                type="button"
                onClick={() => runId && void reconnectStream(runId)}
                className="ml-auto inline-flex items-center gap-1 rounded-lg border border-red-300 px-2 py-1 text-xs font-medium hover:bg-red-100"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                重连
              </button>
            </div>
          )}

          <WorkflowCommandBar
            run={run}
            actions={actions}
            connection={toConnectionStatus(connection)}
            onPause={handlePause}
            onCancel={handleCancel}
          />

          <BusinessStageStepper stages={stages} currentStage={run.current_stage} />

          {activeIntervention && (
            <InterventionPanel
              intervention={activeIntervention}
              draftValues={draftValues}
              validationErrors={validationErrors}
              revisionConflict={revisionConflict}
              onDraftChange={updateDraftValue}
              onJumpToEvidence={(evidenceId) => handleEvidenceClick(evidenceId)}
              onSubmit={() => {
                void submitDraft().catch(() => {})
              }}
              onCancel={() => setIntervention(null)}
            />
          )}

          {isFailed && (
            <WorkflowRecoveryPanel run={run} onRetrySuccess={handleRetrySuccess} />
          )}

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <div className="space-y-5">
              <CurrentActivityPanel run={run} artifacts={artifacts} issues={issues} />
              <ArtifactTimeline artifacts={artifacts} />
            </div>
            <div className="space-y-5">
              <QualitySummary quality={quality} warnings={qualityWarnings} />
              <IssueList issues={issues} onEvidenceClick={handleEvidenceClick} onIssueClick={handleIssueEvidenceClick} />
            </div>
          </div>

          {documentDetail && (
            <section aria-label="文书工作台" className="rounded-2xl border border-[#e2e6df] bg-white p-1">
              <DocumentEditor
                document={documentDetail}
                fromStage={
                  docArtifact?.kind === "respond_complaint_draft" ? "respond_complaint" : "complaint"
                }
                isStreaming={connection === "connected" && run.status === "running"}
                onExport={() => { void handleDocumentExport() }}
                isExporting={isExportingDocument}
                onJumpToEvidence={() => window.location.assign(`/cases/${caseId}/evidence`)}
                onRegenerateFullSuccess={(resp) => void handleRetrySuccess(resp)}
              />
            </section>
          )}
        </div>
      )}

      {/* 抽屉 */}
      <RunConfigurationDrawer
        open={showConfig}
        onClose={() => setShowConfig(false)}
        caseId={caseId}
        evidences={evidences}
        defaultSelectedEvidenceIds={evidences.map((e) => e.id)}
        onCreateRun={(resp) => handleCreateRun(resp)}
      />
      <RunHistoryDrawer
        open={showHistory}
        onClose={() => setShowHistory(false)}
        caseId={caseId}
        activeRunId={runId}
        onSwitchRun={handleSwitchRun}
      />
    </div>
  )
}
