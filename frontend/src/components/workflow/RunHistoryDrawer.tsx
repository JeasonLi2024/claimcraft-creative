// 运行历史抽屉：历史运行列表 + 版本对比占位 + 切换运行
// 对齐 spec.md Task 3.6.1
//
// 数据源：workflowRunApi.listRuns(caseId) → WorkflowRunSummaryItem[]
// 切换运行：workflow-run-store.reset() → workflowRunApi.getSnapshot(runId) → 重建 SSE
import { useEffect, useState } from "react"
import {
  AlertCircle,
  CheckCircle,
  Clock,
  GitBranch,
  GitCompare,
  Loader2,
  RotateCcw,
  X,
} from "lucide-react"
import { workflowRunApi, type WorkflowRunSummaryItem } from "@/lib/api"

// ---------- 状态映射 ----------

interface StatusConfig {
  label: string
  dotClass: string
  textClass: string
}

const STATUS_CONFIG: Record<string, StatusConfig> = {
  idle: { label: "待开始", dotClass: "bg-slate-400", textClass: "text-slate-600" },
  queued: { label: "排队中", dotClass: "bg-slate-400", textClass: "text-slate-600" },
  running: { label: "运行中", dotClass: "bg-sky-500", textClass: "text-sky-700" },
  pausing: { label: "暂停中", dotClass: "bg-amber-500", textClass: "text-amber-700" },
  waiting_user: { label: "等待用户", dotClass: "bg-amber-500", textClass: "text-amber-700" },
  succeeded: { label: "已完成", dotClass: "bg-emerald-500", textClass: "text-emerald-700" },
  failed: { label: "失败", dotClass: "bg-red-500", textClass: "text-red-700" },
  cancelled: { label: "已取消", dotClass: "bg-slate-400", textClass: "text-slate-600" },
}

function statusOf(status: string): StatusConfig {
  return STATUS_CONFIG[status] ?? {
    label: status || "未知",
    dotClass: "bg-slate-400",
    textClass: "text-slate-600",
  }
}

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return "--"
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleString("zh-CN", { hour12: false })
  } catch {
    return ts
  }
}

function formatProgress(progress: number): number {
  const clamped = Math.max(0, Math.min(1, progress || 0))
  return Math.round(clamped * 100)
}

// ---------- 主组件 ----------

export interface RunHistoryDrawerProps {
  open: boolean
  onClose: () => void
  /** 案件 ID */
  caseId: number
  /** 当前活动 run_id（用于高亮） */
  activeRunId: number | null
  /** 切换到指定运行：调用方实现 reset store + getSnapshot + reconnect SSE */
  onSwitchRun?: (runId: number) => void | Promise<void>
}

export function RunHistoryDrawer({
  open,
  onClose,
  caseId,
  activeRunId,
  onSwitchRun,
}: RunHistoryDrawerProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [runs, setRuns] = useState<WorkflowRunSummaryItem[]>([])
  const [switchingId, setSwitchingId] = useState<number | null>(null)
  const [selectedForCompare, setSelectedForCompare] = useState<number | null>(null)

  // 加载历史运行列表
  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError(null)
    workflowRunApi
      .listRuns(caseId)
      .then((data) => {
        if (cancelled) return
        setRuns(data.runs || [])
      })
      .catch((e: unknown) => {
        if (cancelled) return
        const msg = e instanceof Error ? e.message : "加载历史运行失败"
        setError(msg)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, caseId])

  // Escape 关闭
  useEffect(() => {
    if (!open) return
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  // 切换运行：调用方负责 reset store + getSnapshot + reconnect SSE
  async function handleSwitch(runId: number) {
    if (runId === activeRunId) return
    setSwitchingId(runId)
    try {
      await onSwitchRun?.(runId)
      onClose()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "切换运行失败"
      setError(msg)
    } finally {
      setSwitchingId(null)
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label="历史运行列表"
    >
      {/* 遮罩 */}
      <button
        type="button"
        onClick={onClose}
        aria-label="关闭历史运行"
        className="absolute inset-0 cursor-default bg-black/40"
      />

      {/* 抽屉主体 */}
      <aside className="relative flex h-full w-full max-w-md flex-col bg-white shadow-2xl motion-safe:animate-[drawer-slide-in_0.25s_ease-out]">
        {/* 头部 */}
        <header className="flex items-center justify-between border-b border-[#EAEAEA] px-4 py-3">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-[#565652]" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-[#111111]">历史运行</h2>
            {runs.length > 0 && (
              <span className="rounded-full bg-[#F7F6F3] px-2 py-0 text-[10px] text-[#787774]">
                共 {runs.length} 个
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[#787774] hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading && (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
              <Loader2 className="h-5 w-5 animate-spin text-sky-500" aria-hidden="true" />
              <p className="text-xs text-[#787774]">加载历史运行…</p>
            </div>
          )}

          {!loading && error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
              <div className="flex-1">
                <p className="font-medium">加载失败</p>
                <p className="mt-0.5 text-[11px] break-words">{error}</p>
              </div>
            </div>
          )}

          {!loading && !error && runs.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
              <Clock className="h-6 w-6 text-[#787774]" aria-hidden="true" />
              <p className="text-sm text-[#565652]">暂无历史运行</p>
              <p className="text-[11px] text-[#787774]">
                首次启动工作流后会在此显示历史记录
              </p>
            </div>
          )}

          {!loading && !error && runs.length > 0 && (
            <ul className="flex flex-col gap-2">
              {runs.map((run) => {
                const cfg = statusOf(run.status)
                const isActive = run.id === activeRunId
                const isSwitching = switchingId === run.id
                const isDisabled = isSwitching || isActive
                return (
                  <li key={run.id}>
                    <article
                      className={`rounded-xl border px-3 py-2.5 transition ${
                        isActive
                          ? "border-sky-300 bg-sky-50 ring-1 ring-sky-200"
                          : "border-[#EAEAEA] bg-white hover:bg-[#F7F6F3]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="font-mono text-xs font-semibold text-[#111111]">
                              Run #{run.id}
                            </span>
                            <span
                              className={`inline-flex items-center gap-1 rounded-full border border-[#EAEAEA] bg-white px-1.5 py-0 text-[10px] ${cfg.textClass}`}
                              role="status"
                            >
                              <span
                                className={`inline-block h-1.5 w-1.5 rounded-full ${cfg.dotClass}`}
                                aria-hidden="true"
                              />
                              {cfg.label}
                            </span>
                            {run.parent_run_id != null && (
                              <span
                                className="inline-flex items-center gap-0.5 rounded-full border border-violet-200 bg-violet-50 px-1.5 py-0 text-[10px] text-violet-700"
                                title={`由 Run #${run.parent_run_id} 局部重跑 fork`}
                              >
                                <GitBranch className="h-2.5 w-2.5" aria-hidden="true" />
                                fork #{run.parent_run_id}
                              </span>
                            )}
                            {isActive && (
                              <span
                                className="inline-flex items-center gap-0.5 rounded-full border border-sky-200 bg-sky-50 px-1.5 py-0 text-[10px] font-medium text-sky-700"
                              >
                                <CheckCircle className="h-2.5 w-2.5" aria-hidden="true" />
                                当前
                              </span>
                            )}
                          </div>
                          <p className="mt-1 text-[11px] text-[#787774]">
                            工作流版本：{run.workflow_version || "--"} · 修订 #{run.revision}
                          </p>
                          <p className="mt-0.5 text-[11px] text-[#787774]">
                            开始：{formatTimestamp(run.started_at)}
                          </p>
                          {run.finished_at && (
                            <p className="mt-0.5 text-[11px] text-[#787774]">
                              完成：{formatTimestamp(run.finished_at)}
                            </p>
                          )}
                          {run.error_message && (
                            <p className="mt-1 text-[11px] text-red-700 break-words">
                              错误：{run.error_message}
                            </p>
                          )}
                        </div>

                        {/* 操作按钮 */}
                        <div className="flex flex-shrink-0 flex-col items-end gap-1">
                          <button
                            type="button"
                            onClick={() => handleSwitch(run.id)}
                            disabled={isDisabled}
                            aria-label={isActive ? "当前运行" : `切换到 Run #${run.id}`}
                            className="inline-flex min-h-[32px] items-center gap-1 rounded-lg border border-[#EAEAEA] bg-white px-2 py-0.5 text-[11px] font-medium text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isSwitching ? (
                              <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                            ) : (
                              <RotateCcw className="h-3 w-3" aria-hidden="true" />
                            )}
                            {isActive ? "当前" : "切换"}
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setSelectedForCompare((prev) => (prev === run.id ? null : run.id))
                            }
                            aria-pressed={selectedForCompare === run.id}
                            className="inline-flex min-h-[32px] items-center gap-1 rounded-lg border border-[#EAEAEA] bg-white px-2 py-0.5 text-[11px] text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
                          >
                            <GitCompare className="h-3 w-3" aria-hidden="true" />
                            对比
                          </button>
                        </div>
                      </div>

                      {/* 进度条 */}
                      <div
                        className="mt-2 h-1 w-full overflow-hidden rounded-full bg-slate-200"
                        role="progressbar"
                        aria-valuenow={formatProgress(run.progress)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`Run #${run.id} 进度`}
                      >
                        <div
                          className={`h-full rounded-full transition-all ${
                            run.status === "failed"
                              ? "bg-red-500"
                              : run.status === "succeeded"
                                ? "bg-emerald-500"
                                : "bg-sky-500"
                          }`}
                          style={{ width: `${formatProgress(run.progress)}%` }}
                        />
                      </div>
                    </article>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* 版本对比占位 */}
        {selectedForCompare != null && (
          <footer className="border-t border-[#EAEAEA] bg-[#F7F6F3] px-4 py-3">
            <div className="flex items-start gap-2">
              <GitCompare className="mt-0.5 h-4 w-4 text-[#565652]" aria-hidden="true" />
              <div className="flex-1">
                <p className="text-xs font-medium text-[#111111]">
                  已选择 Run #{selectedForCompare} 进行对比
                </p>
                <p className="mt-0.5 text-[11px] text-[#787774]">
                  版本对比功能即将上线（占位）
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedForCompare(null)}
                aria-label="取消对比"
                className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center rounded text-[#787774] hover:bg-slate-200"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </div>
          </footer>
        )}
      </aside>
    </div>
  )
}

export default RunHistoryDrawer
