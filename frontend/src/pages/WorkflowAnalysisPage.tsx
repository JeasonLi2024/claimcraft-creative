// 工作流分析工作台：只负责展示工作流全过程（各阶段状态 + 各节点产物 + 质量/问题）。
// 文书编辑不在本页，收敛到投诉页(/complaint)或反证页(/respond)——本页提供跳转入口。
//
// 数据流：
//   listRuns → active_run_id → streamTicket + getSnapshot(归一化) → applySnapshot → SSE
//   SSE 事件：stage.* 本地即时更新；其余结构性事件触发去抖 snapshot 重取（权威来源）
//
// 契约对齐：后端 snapshot / 事件形状经 lib/workflow-adapters 归一化为前端类型。
// 新旧工作流统一在本页展示：WorkflowRun 使用新工作台，历史 thread 使用兼容面板恢复。
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useParams, Link } from "react-router"
import type { ReactNode } from "react"
import {
  Loader2,
  Play,
  History,
  Workflow,
  RefreshCw,
  AlertTriangle,
  FileText,
  PenLine,
} from "lucide-react"

import { useCaseStore } from "@/stores/case-store"
import { useAuthStore } from "@/stores/auth-store"
import { useStatus } from "@/composables/useStatus"
import { useWorkflowRunStore } from "@/stores/workflow-run-store"
import {
  useInterventionStore,
  configureInterventionSubmitHandler,
} from "@/stores/intervention-store"
import { workflowRunApi, isRevisionConflictError } from "@/lib/api"
import { createSSEClient, type SSEClient } from "@/lib/sse-client"
import { normalizeSnapshot } from "@/lib/workflow-adapters"
import { findDocumentArtifact } from "@/lib/workflow-document"
import type { QualityReport, Issue } from "@/types/workflow"

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
import { WorkflowStreamPanel } from "@/components/workflow/WorkflowStreamPanel"

// 文书产物种类 → 中文名（用于「编辑文书」入口卡）
const DOC_KIND_LABELS: Record<string, string> = {
  complaint_draft: "投诉书",
  respond_complaint_draft: "反证答辩书",
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

// ---------- 统一卡片外壳（对齐 Timeline/Export 视觉规范） ----------

function SectionCard({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">{eyebrow}</p>
        <h2 className="mt-1 text-lg font-semibold tracking-tight">{title}</h2>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  )
}

export default function WorkflowAnalysisPage() {
  const { caseId: caseIdParam } = useParams<{ caseId: string }>()
  const caseId = Number(caseIdParam)

  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchEvidences = useCaseStore((s) => s.fetchEvidences)
  const evidences = useCaseStore((s) => s.evidences)
  const currentCase = useCaseStore((s) => s.currentCase)
  const { disputeLabel } = useStatus()

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
          setConnection("connected")
        },
        onEvent: (event) => {
          // 收到事件才证明连接真正健康，此时才清零重连计数。
          // 避免「connect → 立即断开」反复发生时（onConnect 每次清零）永远触不到
          // 重连上限，导致连接状态无限次在「已连接 / 重连中」之间闪烁。
          reconnectAttemptsRef.current = 0
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

  // ---------- 派生：文书产物（仅用于「编辑文书」入口存在性判断） ----------

  const docArtifact = useMemo(() => findDocumentArtifact(artifacts), [artifacts])
  const isRespondMode = currentCase?.case_mode === "respond"
  const editPath = isRespondMode ? "respond" : "complaint"
  const editLabel = isRespondMode ? "反证答辩" : "投诉文本"
  const docKindLabel = docArtifact ? DOC_KIND_LABELS[docArtifact.kind] ?? "文书" : "文书"

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

  // hero 统计
  const heroStats = [
    { label: "分析进度", value: `${Math.round((run?.progress ?? 0) * 100)}%` },
    { label: "工作流产物", value: artifacts.length },
    { label: "待办问题", value: issues.length },
  ]

  return (
    <div className="space-y-5 pb-8">
      {/* 深色 hero：对齐 Timeline/Export */}
      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
        <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70">
              <Workflow className="h-3.5 w-3.5 text-[#d8b967]" />
              智能分析工作流
            </div>
            <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">工作流分析</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">
              依次完成材料理解、事实核对、案件组织与文书生成。本页展示各阶段状态与产物；文书编辑请前往{editLabel}页。
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">
                {currentCase?.title || `案件 #${caseId}`}
              </span>
              {currentCase?.case_type && (
                <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">
                  {disputeLabel(currentCase.case_type)}
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-col justify-between gap-4">
            <div className="flex justify-start gap-2 xl:justify-end">
              <button
                type="button"
                onClick={() => setShowHistory(true)}
                className="inline-flex min-h-[40px] items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-3.5 text-sm font-medium text-white transition-colors hover:bg-white/15"
              >
                <History className="h-4 w-4" aria-hidden="true" />
                运行历史
              </button>
              <button
                type="button"
                onClick={() => setShowConfig(true)}
                className="inline-flex min-h-[40px] items-center gap-2 rounded-xl bg-white px-3.5 text-sm font-semibold text-[#17231d] transition-opacity hover:opacity-90"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                开始分析
              </button>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {heroStats.map((item) => (
                <div key={item.label} className="rounded-2xl border border-white/10 bg-white/8 p-4 backdrop-blur-sm">
                  <span className="text-xs text-white/45">{item.label}</span>
                  <div className="mt-2 text-2xl font-semibold">{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="flex items-center justify-center rounded-[24px] border border-border bg-card py-24 text-muted-foreground">
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
          <SectionCard
            eyebrow="历史分析"
            title="工作流分析记录与输出"
            description="该案件由旧版工作流生成，历史节点、实时状态和具体输出已迁移至本页面展示。"
          >
            <WorkflowStreamPanel caseId={caseId} />
          </SectionCard>
        ) : (
          <div className="rounded-[24px] border border-dashed border-[#bdc6be] bg-card px-6 py-16 text-center">
            <img
              src="/empty-state.webp"
              alt=""
              aria-hidden="true"
              loading="lazy"
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
                className="inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-[#17231d] px-4 text-sm font-semibold text-white hover:opacity-90"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                开始分析
              </button>
              <Link
                to={`/cases/${caseId}/evidence`}
                className="inline-flex min-h-[44px] items-center rounded-xl border border-border bg-white px-4 text-sm font-medium hover:bg-muted"
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

          <SectionCard eyebrow="业务阶段" title="四阶段处理进度" description="材料理解 → 事实核对 → 案件组织 → 文书生成。">
            <BusinessStageStepper stages={stages} currentStage={run.current_stage} />
          </SectionCard>

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
            <SectionCard
              eyebrow="工作流产物"
              title="各阶段节点输出"
              description="按时间展示每个节点生成的产物；展开可查看内容与来源依据。"
            >
              <div className="space-y-4">
                <CurrentActivityPanel run={run} artifacts={artifacts} issues={issues} />
                <ArtifactTimeline artifacts={artifacts} />
              </div>
            </SectionCard>

            <div className="space-y-5">
              <SectionCard eyebrow="质量与问题" title="质量摘要">
                <div className="space-y-4">
                  <QualitySummary quality={quality} warnings={qualityWarnings} />
                  <IssueList
                    issues={issues}
                    onEvidenceClick={handleEvidenceClick}
                    onIssueClick={handleIssueEvidenceClick}
                  />
                </div>
              </SectionCard>

              {docArtifact && (
                <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)]">
                  <div className="flex items-center gap-3">
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-secondary">
                      <FileText className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">文书产物</p>
                      <h2 className="text-sm font-semibold">{docKindLabel}已生成</h2>
                    </div>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-muted-foreground">
                    文书编辑（逐段修改、AI 重写、法律依据核对）已收敛到{editLabel}页。
                  </p>
                  <Link
                    to={`/cases/${caseId}/${editPath}`}
                    className="mt-4 inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl bg-[#17231d] px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                  >
                    <PenLine className="h-4 w-4" aria-hidden="true" />
                    编辑文书
                  </Link>
                </section>
              )}
            </div>
          </div>
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
