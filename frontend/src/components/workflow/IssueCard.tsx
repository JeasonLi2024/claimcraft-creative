// 单个 Issue 卡片：code + message + severity 图标 + evidence_id 链接 + recoverable 标记
// 对齐 spec 第 6.8 节 / Task 2.6.4
import type { MouseEvent } from "react"
import { AlertOctagon, AlertTriangle, Info, ExternalLink, RotateCcw } from "lucide-react"
import type { Issue, IssueSeverity } from "@/types/workflow"

// ---------- severity 配置 ----------

interface SeverityConfig {
  icon: typeof Info
  iconClass: string
  textClass: string
  borderClass: string
  bgClass: string
  label: string
}

const SEVERITY_CONFIG: Record<IssueSeverity, SeverityConfig> = {
  blocking: {
    icon: AlertOctagon,
    iconClass: "text-red-600",
    textClass: "text-red-700",
    borderClass: "border-red-200",
    bgClass: "bg-red-50",
    label: "阻塞",
  },
  warning: {
    icon: AlertTriangle,
    iconClass: "text-amber-600",
    textClass: "text-amber-700",
    borderClass: "border-amber-200",
    bgClass: "bg-amber-50",
    label: "警告",
  },
  info: {
    icon: Info,
    iconClass: "text-slate-500",
    textClass: "text-slate-700",
    borderClass: "border-slate-200",
    bgClass: "bg-slate-50",
    label: "提示",
  },
}

// ---------- 主组件 ----------

export interface IssueCardProps {
  issue: Issue
  onClick?: () => void
  /** 点击 evidence_id 链接时触发 */
  onEvidenceClick?: (evidenceId: number) => void
}

export function IssueCard({ issue, onClick, onEvidenceClick }: IssueCardProps) {
  const config = SEVERITY_CONFIG[issue.severity]
  const Icon = config.icon
  const isInteractive = Boolean(onClick)
  const hasEvidence = issue.evidence_id != null

  const containerClass = `flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left transition ${
    config.bgClass
  } ${config.borderClass} ${
    isInteractive ? "cursor-pointer hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300" : ""
  }`

  function handleEvidenceClick(e: MouseEvent) {
    e.stopPropagation()
    if (issue.evidence_id != null && onEvidenceClick) {
      onEvidenceClick(issue.evidence_id)
    }
  }

  const content = (
    <>
      <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${config.iconClass}`} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`text-[10px] font-mono uppercase ${config.textClass}`}>
            {issue.code}
          </span>
          <span
            className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[10px] font-medium ${config.borderClass} ${config.textClass}`}
          >
            {config.label}
          </span>
          {issue.recoverable && (
            <span
              className="inline-flex items-center gap-0.5 rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0 text-[10px] font-medium text-emerald-700"
              title="此问题可通过用户介入恢复"
            >
              <RotateCcw className="h-2.5 w-2.5" aria-hidden="true" />
              可恢复
            </span>
          )}
          {issue.stage && (
            <span className="text-[10px] text-slate-500">@ {issue.stage}</span>
          )}
        </div>
        <p className="mt-1 text-sm text-slate-800 break-words">{issue.message}</p>
        {hasEvidence && (
          <button
            type="button"
            onClick={handleEvidenceClick}
            className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-sky-700 transition hover:text-sky-900 focus:outline-none focus-visible:underline"
            aria-label={`查看关联证据 #${issue.evidence_id}`}
          >
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
            证据 #{issue.evidence_id}
          </button>
        )}
      </div>
    </>
  )

  if (isInteractive) {
    return (
      <button type="button" onClick={onClick} className={`${containerClass} w-full`}>
        {content}
      </button>
    )
  }

  return <div className={containerClass}>{content}</div>
}

export default IssueCard
