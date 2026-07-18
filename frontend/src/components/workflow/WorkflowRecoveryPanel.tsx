// 工作流错误恢复中心：重试 / 跳过 / 手动补录 / 重新上传 / 技术详情
// 对齐 spec.md Task 3.6.4
// 触发条件：workflow-run-store.run.status === 'failed'
// 重试调用：POST /api/workflow-runs/{run_id}/retry/ with from_stage
import { useEffect, useMemo, useState } from "react"
import {
  AlertOctagon,
  ChevronDown,
  ChevronRight,
  Cog,
  ExternalLink,
  FileEdit,
  Loader2,
  RefreshCw,
  SkipForward,
  Upload,
} from "lucide-react"
import type { FormEvent } from "react"
import { workflowRunApi, type RetryRunResponse } from "@/lib/api"
import type { BusinessStageKey, WorkflowRun } from "@/types/workflow"
import { useWorkflowRunStore } from "@/stores/workflow-run-store"

// ---------- 业务阶段映射 ----------

const STAGE_OPTIONS: Array<{ value: BusinessStageKey; label: string; nodes: string[] }> = [
  {
    value: "material_understanding",
    label: "材料理解",
    nodes: ["preclassify", "ocr", "classify"],
  },
  {
    value: "fact_checking",
    label: "事实核对",
    nodes: ["extract", "review"],
  },
  {
    value: "case_organization",
    label: "案件组织",
    nodes: ["evidence_chain"],
  },
  {
    value: "document_generation",
    label: "文书生成",
    nodes: ["complaint", "respond_complaint"],
  },
]

// ---------- 恢复动作配置 ----------

type RecoveryAction = "retry" | "skip" | "manual" | "reupload"

interface RecoveryActionConfig {
  label: string
  description: string
  icon: typeof RefreshCw
  iconClass: string
  btnClass: string
}

const RECOVERY_ACTIONS: Record<RecoveryAction, RecoveryActionConfig> = {
  retry: {
    label: "重试",
    description: "从指定阶段重新执行（基于 LangGraph Time Travel）",
    icon: RefreshCw,
    iconClass: "text-sky-600",
    btnClass:
      "border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100 focus-visible:ring-sky-300",
  },
  skip: {
    label: "跳过",
    description: "跳过失败阶段并继续后续流程（可能影响产物质量）",
    icon: SkipForward,
    iconClass: "text-amber-600",
    btnClass:
      "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 focus-visible:ring-amber-300",
  },
  manual: {
    label: "手动补录",
    description: "由用户手工补录失败节点的产物",
    icon: FileEdit,
    iconClass: "text-violet-600",
    btnClass:
      "border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 focus-visible:ring-violet-300",
  },
  reupload: {
    label: "重新上传",
    description: "重新上传证据材料后重试",
    icon: Upload,
    iconClass: "text-slate-600",
    btnClass:
      "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100 focus-visible:ring-slate-300",
  },
}

// ---------- 主组件 ----------

export interface WorkflowRecoveryPanelProps {
  /** 当前失败运行（默认从 workflow-run-store.run 读取） */
  run?: WorkflowRun
  /** 重试成功回调（调用方负责切换到 fork 后的新运行） */
  onRetrySuccess?: (response: RetryRunResponse) => void | Promise<void>
  /** 跳过回调（由调用方实现，可调用专门的 skip 端点或直接 cancel） */
  onSkip?: (runId: number) => void | Promise<void>
  /** 手动补录回调 */
  onManual?: (runId: number) => void
  /** 重新上传回调 */
  onReupload?: (runId: number) => void
  /** 默认展开技术详情 */
  defaultDetailsExpanded?: boolean
}

export function WorkflowRecoveryPanel({
  run: runProp,
  onRetrySuccess,
  onSkip,
  onManual,
  onReupload,
  defaultDetailsExpanded = false,
}: WorkflowRecoveryPanelProps) {
  const storeRun = useWorkflowRunStore((s) => s.run)
  const run = runProp ?? storeRun

  const [selectedStage, setSelectedStage] = useState<BusinessStageKey>(
    "material_understanding",
  )
  const [preserveUserConfirmed, setPreserveUserConfirmed] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detailsExpanded, setDetailsExpanded] = useState(defaultDetailsExpanded)

  // 自动选择 run.current_stage 对应的阶段（如果可识别）
  useEffect(() => {
    if (!run?.current_stage) return
    const matched = STAGE_OPTIONS.find(
      (opt) =>
        opt.value === run.current_stage ||
        opt.nodes.includes(run.current_stage),
    )
    if (matched) {
      setSelectedStage(matched.value)
    }
  }, [run?.current_stage])

  const errorMessage = useMemo(() => {
    return run?.error_message || "工作流执行失败，请选择恢复方式"
  }, [run?.error_message])

  // 仅在运行失败时显示
  if (run && run.status !== "failed") return null

  const runId = run?.id

  async function handleRetry(e: FormEvent) {
    e.preventDefault()
    if (!runId) return
    setSubmitting(true)
    setError(null)
    try {
      const response = await workflowRunApi.retryRun(runId, {
        from_stage: selectedStage,
        preserve_user_confirmed: preserveUserConfirmed,
      })
      await onRetrySuccess?.(response)
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : typeof err === "string"
            ? err
            : "重试失败，请稍后重试或联系技术支持"
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSkip() {
    if (!runId) return
    setSubmitting(true)
    setError(null)
    try {
      await onSkip?.(runId)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "跳过失败"
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  function handleManual() {
    if (!runId) return
    onManual?.(runId)
  }

  function handleReupload() {
    if (!runId) return
    onReupload?.(runId)
  }

  return (
    <section
      role="alertdialog"
      aria-label="工作流错误恢复中心"
      className="rounded-2xl border border-red-200 bg-white shadow-sm"
    >
      {/* 头部 */}
      <header className="flex items-start gap-3 border-b border-red-100 px-4 py-3">
        <div className="rounded-lg bg-red-50 p-2">
          <AlertOctagon className="h-4 w-4 text-red-600" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-[#111111]">工作流执行失败</h2>
            {run && (
              <span className="font-mono text-[10px] text-[#787774]">Run #{run.id}</span>
            )}
            {run?.current_stage && (
              <span className="rounded-full border border-red-200 bg-red-50 px-1.5 py-0 text-[10px] text-red-700">
                失败阶段：{STAGE_OPTIONS.find((s) => s.value === run.current_stage)?.label ?? run.current_stage}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs leading-5 text-red-700 break-words">{errorMessage}</p>
        </div>
      </header>

      {/* 错误提示 */}
      {error && (
        <div
          role="alert"
          className="mx-4 mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          <AlertOctagon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
          <div className="flex-1">
            <p className="font-medium">操作失败</p>
            <p className="mt-0.5 text-[11px] break-words">{error}</p>
          </div>
        </div>
      )}

      {/* 重试表单 */}
      <form onSubmit={handleRetry} className="px-4 py-4">
        <fieldset className="mb-4">
          <legend className="mb-2 text-xs font-semibold text-[#111111]">
            重试起始阶段
          </legend>
          <div className="grid grid-cols-2 gap-2">
            {STAGE_OPTIONS.map((opt) => {
              const checked = selectedStage === opt.value
              return (
                <label
                  key={opt.value}
                  className={`flex cursor-pointer flex-col gap-0.5 rounded-lg border px-2.5 py-1.5 text-xs transition ${
                    checked
                      ? "border-sky-300 bg-sky-50 ring-1 ring-sky-200"
                      : "border-[#EAEAEA] bg-white hover:bg-[#F7F6F3]"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <input
                      type="radio"
                      name="from-stage"
                      value={opt.value}
                      checked={checked}
                      onChange={() => setSelectedStage(opt.value)}
                      className="h-3 w-3 border-[#EAEAEA] text-sky-600 focus:ring-sky-500"
                    />
                    <span className="font-medium text-[#111111]">{opt.label}</span>
                  </div>
                  <span className="ml-4 text-[10px] text-[#787774]">
                    {opt.nodes.join(" · ")}
                  </span>
                </label>
              )
            })}
          </div>
        </fieldset>

        <label className="mb-4 flex cursor-pointer items-center gap-2 text-xs text-[#565652]">
          <input
            type="checkbox"
            checked={preserveUserConfirmed}
            onChange={(e) => setPreserveUserConfirmed(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-[#EAEAEA] text-sky-600 focus:ring-sky-500"
          />
          <span>
            保留用户已确认字段
            <span className="ml-1 text-[10px] text-[#787774]">（避免重复审核）</span>
          </span>
        </label>

        {/* 操作按钮组 */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <button
            type="submit"
            disabled={submitting || !runId}
            aria-label="从此阶段重试"
            className={`inline-flex min-h-[44px] flex-col items-start gap-0 rounded-lg border px-3 py-2 text-left text-xs transition focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 ${RECOVERY_ACTIONS.retry.btnClass}`}
          >
            <span className="flex items-center gap-1.5 font-semibold">
              {submitting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {RECOVERY_ACTIONS.retry.label}
            </span>
            <span className="mt-0.5 text-[10px] font-normal opacity-80">
              从 {STAGE_OPTIONS.find((s) => s.value === selectedStage)?.label} 开始
            </span>
          </button>

          <button
            type="button"
            onClick={handleSkip}
            disabled={submitting || !runId || !onSkip}
            className={`inline-flex min-h-[44px] flex-col items-start gap-0 rounded-lg border px-3 py-2 text-left text-xs transition focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 ${RECOVERY_ACTIONS.skip.btnClass}`}
          >
            <span className="flex items-center gap-1.5 font-semibold">
              <SkipForward className="h-3.5 w-3.5" aria-hidden="true" />
              {RECOVERY_ACTIONS.skip.label}
            </span>
            <span className="mt-0.5 text-[10px] font-normal opacity-80">
              跳过失败阶段
            </span>
          </button>

          <button
            type="button"
            onClick={handleManual}
            disabled={submitting || !runId || !onManual}
            className={`inline-flex min-h-[44px] flex-col items-start gap-0 rounded-lg border px-3 py-2 text-left text-xs transition focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 ${RECOVERY_ACTIONS.manual.btnClass}`}
          >
            <span className="flex items-center gap-1.5 font-semibold">
              <FileEdit className="h-3.5 w-3.5" aria-hidden="true" />
              {RECOVERY_ACTIONS.manual.label}
            </span>
            <span className="mt-0.5 text-[10px] font-normal opacity-80">
              手工补录产物
            </span>
          </button>

          <button
            type="button"
            onClick={handleReupload}
            disabled={submitting || !runId || !onReupload}
            className={`inline-flex min-h-[44px] flex-col items-start gap-0 rounded-lg border px-3 py-2 text-left text-xs transition focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 ${RECOVERY_ACTIONS.reupload.btnClass}`}
          >
            <span className="flex items-center gap-1.5 font-semibold">
              <Upload className="h-3.5 w-3.5" aria-hidden="true" />
              {RECOVERY_ACTIONS.reupload.label}
            </span>
            <span className="mt-0.5 text-[10px] font-normal opacity-80">
              重新上传证据
            </span>
          </button>
        </div>
      </form>

      {/* 技术详情（可折叠） */}
      <div className="border-t border-[#EAEAEA]">
        <button
          type="button"
          onClick={() => setDetailsExpanded((v) => !v)}
          aria-expanded={detailsExpanded}
          className="flex w-full items-center justify-between px-4 py-2 text-left text-xs font-medium text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
        >
          <span className="flex items-center gap-1.5">
            <Cog className="h-3.5 w-3.5" aria-hidden="true" />
            技术详情
          </span>
          {detailsExpanded ? (
            <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          )}
        </button>
        {detailsExpanded && run && (
          <dl className="grid grid-cols-1 gap-1 border-t border-[#EAEAEA] bg-[#F7F6F3] px-4 py-3 text-[11px] sm:grid-cols-2">
            <DetailItem label="运行编号" value={run.id != null ? `#${run.id}` : "--"} />
            <DetailItem label="Thread ID" value={run.thread_id || "--"} mono />
            <DetailItem label="工作流版本" value={run.workflow_version || "--"} mono />
            <DetailItem label="State Schema 版本" value={String(run.state_schema_version ?? "--")} mono />
            <DetailItem label="Policy 版本" value={run.policy_version || "--"} mono />
            <DetailItem label="Prompt 包版本" value={run.prompt_bundle_version || "--"} mono />
            <DetailItem label="当前阶段" value={run.current_stage || "--"} mono />
            <DetailItem label="当前节点" value={run.current_node || "--"} mono />
            <DetailItem label="修订版本" value={String(run.revision ?? "--")} mono />
            <DetailItem label="开始时间" value={formatTime(run.started_at)} />
            {run.completed_at && (
              <DetailItem label="完成时间" value={formatTime(run.completed_at)} />
            )}
            {run.error_message && (
              <div className="sm:col-span-2">
                <dt className="text-[10px] font-medium uppercase tracking-wide text-[#787774]">
                  错误堆栈
                </dt>
                <dd className="mt-0.5 overflow-x-auto rounded bg-white p-2 font-mono text-[10px] text-red-700 break-words whitespace-pre-wrap">
                  {run.error_message}
                </dd>
              </div>
            )}
          </dl>
        )}
        {detailsExpanded && !run && (
          <p className="border-t border-[#EAEAEA] px-4 py-3 text-[11px] text-[#787774]">
            无运行信息
          </p>
        )}
        {detailsExpanded && (
          <div className="flex items-center justify-end gap-2 border-t border-[#EAEAEA] px-4 py-2">
            <a
              href={buildLogsUrl(run)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-sky-700 transition hover:text-sky-900 focus:outline-none focus-visible:underline"
            >
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
              查看完整日志
            </a>
          </div>
        )}
      </div>
    </section>
  )
}

// ---------- 内部子组件 ----------

function DetailItem({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="flex-shrink-0 text-[10px] font-medium uppercase tracking-wide text-[#787774]">
        {label}
      </dt>
      <dd className={`min-w-0 flex-1 truncate text-[#111111] ${mono ? "font-mono" : ""}`}>
        {value}
      </dd>
    </div>
  )
}

// ---------- 辅助函数 ----------

function formatTime(ts: string | null | undefined): string {
  if (!ts) return "--"
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleString("zh-CN", { hour12: false })
  } catch {
    return ts
  }
}

function buildLogsUrl(run: WorkflowRun | null | undefined): string {
  if (!run?.id) return "#"
  // 占位：实际日志 URL 由部署环境决定
  return `/admin/workflow-runs/${run.id}/logs/`
}

export default WorkflowRecoveryPanel
