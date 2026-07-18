// Issue 列表：按 severity 分组（阻塞 → 警告 → 提示）
// 对齐 spec 第 6.8 节 / Task 2.6.4
import { useMemo } from "react"
import { AlertOctagon, AlertTriangle, Info } from "lucide-react"
import type { Issue, IssueSeverity } from "@/types/workflow"
import { IssueCard } from "./IssueCard"

// ---------- 分组配置 ----------

interface GroupConfig {
  key: IssueSeverity
  label: string
  icon: typeof Info
  textClass: string
  borderClass: string
}

const GROUP_ORDER: GroupConfig[] = [
  {
    key: "blocking",
    label: "阻塞问题",
    icon: AlertOctagon,
    textClass: "text-red-700",
    borderClass: "border-red-200",
  },
  {
    key: "warning",
    label: "警告",
    icon: AlertTriangle,
    textClass: "text-amber-700",
    borderClass: "border-amber-200",
  },
  {
    key: "info",
    label: "提示",
    icon: Info,
    textClass: "text-slate-700",
    borderClass: "border-slate-200",
  },
]

// ---------- 主组件 ----------

export interface IssueListProps {
  issues: Issue[]
  onIssueClick?: (issue: Issue) => void
  /** 点击 issue 内 evidence_id 链接时触发 */
  onEvidenceClick?: (evidenceId: number) => void
}

export function IssueList({ issues, onIssueClick, onEvidenceClick }: IssueListProps) {
  const grouped = useMemo(() => {
    const map: Record<IssueSeverity, Issue[]> = {
      blocking: [],
      warning: [],
      info: [],
    }
    for (const issue of issues) {
      map[issue.severity].push(issue)
    }
    return map
  }, [issues])

  const total = issues.length

  if (total === 0) {
    return (
      <div
        className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-6 text-center text-sm text-emerald-700"
        role="status"
      >
        没有待处理的问题
      </div>
    )
  }

  return (
    <div className="space-y-4" role="region" aria-label={`问题列表，共 ${total} 个`}>
      {GROUP_ORDER.map((group) => {
        const items = grouped[group.key]
        if (items.length === 0) return null
        const Icon = group.icon
        return (
          <section key={group.key} aria-labelledby={`issue-group-${group.key}`}>
            <div className="mb-2 flex items-center gap-2">
              <Icon className={`h-4 w-4 ${group.textClass}`} aria-hidden="true" />
              <h4
                id={`issue-group-${group.key}`}
                className={`text-xs font-semibold uppercase tracking-wide ${group.textClass}`}
              >
                {group.label}
              </h4>
              <span
                className={`inline-flex h-5 min-w-[20px] items-center justify-center rounded-full border px-1.5 text-[10px] font-medium ${group.borderClass} ${group.textClass}`}
                aria-label={`${items.length} 个`}
              >
                {items.length}
              </span>
            </div>
            <ul className="space-y-2">
              {items.map((issue, idx) => (
                <li key={`${issue.code}-${idx}`}>
                  <IssueCard
                    issue={issue}
                    onClick={onIssueClick ? () => onIssueClick(issue) : undefined}
                    onEvidenceClick={onEvidenceClick}
                  />
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

export default IssueList
