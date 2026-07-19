// 工作流控制栏：运行编号 + 状态 + 总进度 + 当前阶段 + 连接状态 + 暂停/取消按钮 + 更多菜单
// 参考 spec 第 6.6 节 / Task 1.8.1
import { useEffect, useRef, useState } from "react"
import {
  AlertCircle,
  Loader2,
  MoreVertical,
  Pause,
  Square,
  Download,
  RotateCcw,
  Wifi,
  WifiOff,
} from "lucide-react"
import type { WorkflowAllowedActions, WorkflowRun, WorkflowRunStatus } from "@/types/workflow"

// ---------- 运行状态徽章 ----------

interface StatusBadgeConfig {
  label: string
  dotClass: string
  textClass: string
  bgClass: string
  borderClass: string
}

const STATUS_BADGE: Record<WorkflowRunStatus, StatusBadgeConfig> = {
  idle: {
    label: "待开始",
    dotClass: "bg-slate-400",
    textClass: "text-slate-700",
    bgClass: "bg-slate-50",
    borderClass: "border-slate-200",
  },
  queued: {
    label: "排队中",
    dotClass: "bg-slate-400",
    textClass: "text-slate-700",
    bgClass: "bg-slate-50",
    borderClass: "border-slate-200",
  },
  running: {
    label: "运行中",
    dotClass: "bg-sky-500",
    textClass: "text-sky-700",
    bgClass: "bg-sky-50",
    borderClass: "border-sky-200",
  },
  pausing: {
    label: "暂停中",
    dotClass: "bg-amber-500",
    textClass: "text-amber-700",
    bgClass: "bg-amber-50",
    borderClass: "border-amber-200",
  },
  waiting_user: {
    label: "等待用户",
    dotClass: "bg-amber-500",
    textClass: "text-amber-700",
    bgClass: "bg-amber-50",
    borderClass: "border-amber-200",
  },
  succeeded: {
    label: "已完成",
    dotClass: "bg-emerald-500",
    textClass: "text-emerald-700",
    bgClass: "bg-emerald-50",
    borderClass: "border-emerald-200",
  },
  failed: {
    label: "失败",
    dotClass: "bg-red-500",
    textClass: "text-red-700",
    bgClass: "bg-red-50",
    borderClass: "border-red-200",
  },
  cancelled: {
    label: "已取消",
    dotClass: "bg-slate-400",
    textClass: "text-slate-700",
    bgClass: "bg-slate-50",
    borderClass: "border-slate-200",
  },
}

// ---------- 业务阶段中文名映射 ----------

const STAGE_NAME_ZH: Record<string, string> = {
  material_understanding: "材料理解",
  fact_checking: "事实核对",
  case_organization: "案件组织",
  document_generation: "文书生成",
}

function stageLabel(stage: string | undefined | null): string {
  if (!stage) return "--"
  return STAGE_NAME_ZH[stage] || stage
}

// ---------- 连接状态指示器 ----------

export type ConnectionStatus =
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "fatal_error"

interface ConnectionConfig {
  label: string
  icon: typeof Wifi
  iconClass: string
  textClass: string
}

const CONNECTION_CONFIG: Record<ConnectionStatus, ConnectionConfig> = {
  connected: {
    label: "已连接",
    icon: Wifi,
    iconClass: "text-emerald-500",
    textClass: "text-emerald-700",
  },
  reconnecting: {
    label: "重连中",
    icon: Wifi,
    iconClass: "text-amber-500 animate-pulse",
    textClass: "text-amber-700",
  },
  disconnected: {
    label: "已断开",
    icon: WifiOff,
    iconClass: "text-red-500",
    textClass: "text-red-700",
  },
  fatal_error: {
    label: "连接异常",
    icon: AlertCircle,
    iconClass: "text-red-500",
    textClass: "text-red-700",
  },
}

// ---------- 进度格式化 ----------

function formatProgress(progress: number | undefined | null): number {
  if (progress == null || Number.isNaN(progress)) return 0
  const clamped = Math.max(0, Math.min(1, progress))
  return Math.round(clamped * 100)
}

// ---------- 更多菜单 ----------

interface MoreMenuItem {
  key: string
  label: string
  icon: typeof RotateCcw
  onSelect?: () => void
  disabled?: boolean
}

interface MoreMenuProps {
  items: MoreMenuItem[]
}

function MoreMenu({ items }: MoreMenuProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    function onClickOutside(e: MouseEvent) {
      if (!containerRef.current) return
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener("mousedown", onClickOutside)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onClickOutside)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  function handleSelect(item: MoreMenuItem) {
    if (item.disabled) return
    setOpen(false)
    item.onSelect?.()
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="更多操作"
        className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg border border-[#EAEAEA] bg-white px-2 text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
      >
        <MoreVertical className="h-4 w-4" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label="更多操作"
          className="absolute right-0 z-30 mt-1 min-w-[160px] overflow-hidden rounded-lg border border-[#EAEAEA] bg-white py-1 shadow-lg"
        >
          {items.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.key}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                onClick={() => handleSelect(item)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-[#111111] transition hover:bg-[#F7F6F3] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Icon className="h-3.5 w-3.5 text-[#787774]" aria-hidden="true" />
                {item.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------- 主组件 ----------

export interface WorkflowCommandBarProps {
  run: WorkflowRun | null
  actions: WorkflowAllowedActions
  connection: ConnectionStatus
  onPause?: () => void
  onCancel?: () => void
  /** 占位：重新开始 */
  onRestart?: () => void
  /** 占位：下载日志 */
  onDownloadLogs?: () => void
}

export function WorkflowCommandBar({
  run,
  actions,
  connection,
  onPause,
  onCancel,
  onRestart,
  onDownloadLogs,
}: WorkflowCommandBarProps) {
  const status: WorkflowRunStatus = run?.status || "idle"
  const statusConfig = STATUS_BADGE[status]
  const connConfig = CONNECTION_CONFIG[connection]
  const ConnIcon = connConfig.icon
  const progressPct = formatProgress(run?.progress)
  const isPausing = status === "pausing"
  const pauseDisabled = !actions.can_pause || isPausing || !onPause
  const cancelDisabled = !actions.can_cancel || !onCancel

  const moreMenuItems: MoreMenuItem[] = [
    {
      key: "restart",
      label: "重新开始",
      icon: RotateCcw,
      onSelect: onRestart,
      disabled: !actions.can_restart_from_stage || !onRestart,
    },
    {
      key: "download-logs",
      label: "下载日志",
      icon: Download,
      onSelect: onDownloadLogs,
      disabled: !onDownloadLogs,
    },
  ]

  return (
    <div
      role="toolbar"
      aria-label="工作流控制栏"
      className="flex flex-col gap-3 rounded-2xl border border-[#EAEAEA] bg-white p-3 shadow-sm md:flex-row md:items-center md:gap-4"
    >
      {/* 左侧：运行编号 + 状态 */}
      <div className="flex items-center gap-2 md:flex-shrink-0">
        <span className="font-mono text-xs text-[#787774]" aria-label="运行编号">
          {run ? `Run #${run.id}` : "未启动"}
        </span>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ${statusConfig.bgClass} ${statusConfig.borderClass} ${statusConfig.textClass}`}
          role="status"
          aria-label={`运行状态：${statusConfig.label}`}
        >
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${statusConfig.dotClass}`} aria-hidden="true" />
          {statusConfig.label}
        </span>
        {/* 暂停为「阶段边界」生效：明确告知用户暂停请求已提交但需当前阶段完成，避免误判为无效 */}
        {isPausing && (
          <span className="text-[11px] text-amber-700">将在当前阶段完成后生效</span>
        )}
      </div>

      {/* 中间：进度 + 当前阶段 */}
      <div className="flex flex-1 flex-col gap-1.5 md:min-w-0">
        <div className="flex items-baseline justify-between gap-3 text-[11px] text-[#787774]">
          <span>
            当前阶段：<span className="font-medium text-[#111111]">{stageLabel(run?.current_stage)}</span>
          </span>
          <span aria-label={`总进度：${progressPct}%`}>{progressPct}%</span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200"
          role="progressbar"
          aria-valuenow={progressPct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="工作流总进度"
        >
          <div
            className={`h-full rounded-full transition-all ${
              status === "failed" ? "bg-red-500" : status === "succeeded" ? "bg-emerald-500" : "bg-sky-500"
            }`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* 右侧：连接状态 + 按钮 */}
      <div className="flex items-center gap-2 md:flex-shrink-0">
        <span
          className={`inline-flex items-center gap-1 rounded-full border border-[#EAEAEA] bg-white px-2 py-1 text-[11px] ${connConfig.textClass}`}
          aria-label={`连接状态：${connConfig.label}`}
        >
          <ConnIcon className={`h-3 w-3 ${connConfig.iconClass}`} aria-hidden="true" />
          <span className="hidden sm:inline">{connConfig.label}</span>
        </span>

        <button
          type="button"
          onClick={onPause}
          disabled={pauseDisabled}
          aria-label={isPausing ? "暂停中" : "暂停工作流"}
          className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPausing ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Pause className="h-3.5 w-3.5" aria-hidden="true" />}
          <span className="hidden sm:inline">{isPausing ? "暂停中" : "暂停"}</span>
        </button>

        <button
          type="button"
          onClick={onCancel}
          disabled={cancelDisabled}
          aria-label="取消工作流"
          className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Square className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">取消</span>
        </button>

        <MoreMenu items={moreMenuItems} />
      </div>
    </div>
  )
}

export default WorkflowCommandBar
