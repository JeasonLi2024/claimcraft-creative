// 文书工作台容器：加载当前工作流运行的文书产物并挂载可编辑的 DocumentEditor。
// 投诉页(/complaint)与反证页(/respond)复用本组件，仅 kind + hero 文案不同。
//
// 职责边界：本页只负责「编辑单份文书」，不建立 SSE（实时进度由工作流分析页负责）。
// 数据流：fetchCaseDetail → listRuns(active) → getSnapshot → normalizeSnapshot
//         → findDocumentArtifact(kind) → documentApi.getDocument → DocumentEditor
import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate, Link } from "react-router"
import {
  AlertTriangle,
  FileText,
  Loader2,
  Play,
  Quote,
  RefreshCw,
  Sparkles,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

import { useCaseStore } from "@/stores/case-store"
import { useStatus } from "@/composables/useStatus"
import { workflowRunApi, type RetryRunResponse } from "@/lib/api"
import { documentApi } from "@/lib/document-api"
import { normalizeSnapshot } from "@/lib/workflow-adapters"
import { findDocumentArtifact, documentIdForArtifact } from "@/lib/workflow-document"
import type { WorkflowArtifactKind, WorkflowRunStatus } from "@/types/workflow"
import type { DocumentDetail, ExportCheckResult } from "@/types/document"
import { DocumentEditor } from "./DocumentEditor"

// kind → 目标文书产物类型
const TARGET_KIND: Record<"complaint" | "respond_complaint", WorkflowArtifactKind> = {
  complaint: "complaint_draft",
  respond_complaint: "respond_complaint_draft",
}

// 仍在推进、文书可能未定稿的运行状态
const ACTIVE_RUN_STATUSES = new Set<WorkflowRunStatus>([
  "queued",
  "running",
  "pausing",
  "waiting_user",
])

export interface WorkflowDocumentWorkbenchProps {
  caseId: number
  kind: "complaint" | "respond_complaint"
  hero: {
    eyebrow: string
    title: string
    description: string
    icon: LucideIcon
  }
}

export function WorkflowDocumentWorkbench({ caseId, kind, hero }: WorkflowDocumentWorkbenchProps) {
  const navigate = useNavigate()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const currentCase = useCaseStore((s) => s.currentCase)
  const { disputeLabel } = useStatus()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runId, setRunId] = useState<number | null>(null)
  const [runStatus, setRunStatus] = useState<WorkflowRunStatus | null>(null)
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null)
  const [isExporting, setIsExporting] = useState(false)
  const [exportCheckResult, setExportCheckResult] = useState<ExportCheckResult | null>(null)

  const HeroIcon = hero.icon

  // 按指定 run 加载文书
  const loadRun = useCallback(
    async (targetRunId: number) => {
      const snapshot = normalizeSnapshot(await workflowRunApi.getSnapshot(targetRunId))
      setRunId(targetRunId)
      setRunStatus(snapshot.run.status)
      const artifact = findDocumentArtifact(snapshot.artifacts, TARGET_KIND[kind])
      if (!artifact) {
        setDocumentDetail(null)
        return
      }
      try {
        const detail = await documentApi.getDocument(
          targetRunId,
          documentIdForArtifact(artifact),
          artifact,
        )
        setDocumentDetail(detail)
      } catch {
        setDocumentDetail(null)
      }
    },
    [kind],
  )

  // 解析当前活动 run 并加载
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setExportCheckResult(null)
    try {
      await fetchCaseDetail(caseId)
      const list = await workflowRunApi.listRuns(caseId)
      const active = list.active_run_id ?? list.runs[0]?.id ?? null
      if (active == null) {
        setRunId(null)
        setRunStatus(null)
        setDocumentDetail(null)
        return
      }
      await loadRun(active)
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载文书失败")
    } finally {
      setLoading(false)
    }
  }, [caseId, fetchCaseDetail, loadRun])

  useEffect(() => {
    if (!Number.isFinite(caseId)) return
    void load()
  }, [caseId, load])

  // 导出：先跑导出前质量门，通过则跳导出中心；否则把问题交给 DocumentSourcePanel 展示
  const handleExport = useCallback(async () => {
    if (!documentDetail || runId == null || isExporting) return
    setIsExporting(true)
    try {
      const check = await documentApi.exportCheck(runId, documentDetail.id)
      setExportCheckResult(check)
      if (check.passed) navigate(`/cases/${caseId}/export`)
    } catch {
      /* exportCheck 失败：忽略，面板自行降级 */
    } finally {
      setIsExporting(false)
    }
  }, [caseId, documentDetail, isExporting, navigate, runId])

  const handleRefreshExportCheck = useCallback(async () => {
    if (!documentDetail || runId == null) return
    try {
      setExportCheckResult(await documentApi.exportCheck(runId, documentDetail.id))
    } catch {
      /* 忽略 */
    }
  }, [documentDetail, runId])

  // 全文重新生成成功 → 按 fork 出的新 run 重新加载
  const handleRegenerateFullSuccess = useCallback(
    (resp: RetryRunResponse) => {
      setLoading(true)
      setError(null)
      void loadRun(resp.run_id)
        .catch((e) => setError(e instanceof Error ? e.message : "加载文书失败"))
        .finally(() => setLoading(false))
    },
    [loadRun],
  )

  // hero 统计（由文书派生）
  const stats = useMemo(() => {
    const paragraphs = documentDetail?.paragraphs ?? []
    const evidenceCodes = new Set<string>()
    for (const p of paragraphs) for (const code of p.evidence_codes) evidenceCodes.add(code)
    return {
      paragraphCount: paragraphs.length,
      evidenceCount: evidenceCodes.size,
      version: documentDetail?.current_version ?? 0,
    }
  }, [documentDetail])

  const isGenerating = runStatus != null && ACTIVE_RUN_STATUSES.has(runStatus)

  return (
    <div className="space-y-5 pb-8">
      {/* 深色 hero：对齐 Timeline/Export 视觉规范 */}
      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
        <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70">
              <HeroIcon className="h-3.5 w-3.5 text-[#d8b967]" />
              {hero.eyebrow}
            </div>
            <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">{hero.title}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">{hero.description}</p>
            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">
                {currentCase?.title || "当前案件"}
              </span>
              {currentCase?.case_type && (
                <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">
                  {disputeLabel(currentCase.case_type)}
                </span>
              )}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 self-end">
            {[
              { label: "文书段落", value: stats.paragraphCount, icon: FileText },
              { label: "引用证据", value: stats.evidenceCount, icon: Quote },
              { label: "当前版本", value: stats.version, icon: Sparkles },
            ].map((item) => (
              <div key={item.label} className="rounded-2xl border border-white/10 bg-white/8 p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between text-white/45">
                  <span className="text-xs">{item.label}</span>
                  <item.icon className="h-4 w-4" />
                </div>
                <div className="mt-2 text-2xl font-semibold">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {error && (
        <div role="alert" className="flex items-center gap-2 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* 运行仍在推进时的提示（本页不建 SSE，实时进度在分析页） */}
      {isGenerating && (
        <div role="status" className="flex flex-wrap items-center gap-2 rounded-2xl border border-[#e5d9b5] bg-[#fef9ec] px-4 py-3.5 text-sm text-[#6f5a25]">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
          <span className="min-w-0 flex-1">文书可能仍在生成中，前往工作流分析查看实时进度，完成后回到本页编辑。</span>
          <Link
            to={`/cases/${caseId}/analysis`}
            className="shrink-0 rounded-lg border border-[#dfd1a7] bg-white/60 px-3 py-1.5 text-xs font-semibold transition-colors hover:bg-white"
          >
            工作流分析
          </Link>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-[#dfd1a7] bg-white/60 px-3 py-1.5 text-xs font-semibold transition-colors hover:bg-white"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            刷新
          </button>
        </div>
      )}

      {/* 主体：编辑器 / 加载 / 空状态 */}
      {loading ? (
        <div className="flex h-72 items-center justify-center rounded-[24px] border border-border bg-card">
          <Loader2 className="h-7 w-7 animate-spin text-secondary" />
        </div>
      ) : documentDetail ? (
        <section
          aria-label="文书工作台"
          className="relative h-[75vh] min-h-[560px] overflow-hidden rounded-[24px] border border-border bg-card shadow-[0_12px_36px_rgba(31,45,38,.05)]"
        >
          <DocumentEditor
            document={documentDetail}
            fromStage={kind}
            onExport={() => void handleExport()}
            isExporting={isExporting}
            exportCheckResult={exportCheckResult}
            onRefreshExportCheck={() => void handleRefreshExportCheck()}
            onJumpToEvidence={() => navigate(`/cases/${caseId}/evidence`)}
            onRegenerateFullSuccess={handleRegenerateFullSuccess}
          />
        </section>
      ) : (
        <div className="rounded-[24px] border border-dashed border-[#bdc6be] bg-card px-6 py-16 text-center">
          <FileText className="mx-auto h-8 w-8 text-muted-foreground" />
          <h3 className="mt-3 text-lg font-semibold">暂无{hero.title}</h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            该案件尚未生成文书。前往工作流分析选择证据并发起分析，系统完成文书生成后可在此编辑。
          </p>
          <div className="mt-6 flex justify-center">
            <Link
              to={`/cases/${caseId}/analysis`}
              className="inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-[#17231d] px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90"
            >
              <Play className="h-4 w-4" />
              前往工作流分析
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

export default WorkflowDocumentWorkbench
