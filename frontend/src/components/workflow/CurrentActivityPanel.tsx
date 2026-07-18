// 当前活动面板：展示当前正在做什么 + 最近产物 + 需要注意的内容 + 文书流式生成占位
// 参考 spec 第 6.7 节 / Task 1.8.2
import { useMemo } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  Pause,
  PenLine,
  TriangleAlert as WarningIcon,
} from "lucide-react"
import type { Issue, IssueSeverity, WorkflowArtifact, WorkflowArtifactKind, WorkflowRun } from "@/types/workflow"

// ---------- 节点/产物中文标签 ----------

const NODE_LABELS_ZH: Record<string, string> = {
  preclassify: "预分类",
  ocr: "OCR 识别",
  classify: "证据分类",
  extract: "字段抽取",
  review: "人工审核",
  evidence_chain: "证据链构建",
  complaint: "投诉书生成",
  respond_complaint: "反证答辩书生成",
}

const ARTIFACT_KIND_LABELS: Record<WorkflowArtifactKind, string> = {
  preclassify_result: "预分类结果",
  ocr_result: "OCR 识别结果",
  classify_result: "证据分类结果",
  extract_result: "字段抽取结果",
  evidence_chain: "证据链",
  complaint_draft: "投诉书",
  respond_complaint_draft: "反证答辩书",
}

const ARTIFACT_STATUS_LABELS: Record<WorkflowArtifact["status"], string> = {
  active: "有效",
  stale: "已过期",
  archived: "已归档",
}

function nodeLabel(node: string | undefined | null): string {
  if (!node) return "等待开始"
  return NODE_LABELS_ZH[node] || node
}

// ---------- 时间格式化 ----------

function formatTime(iso: string | undefined | null): string {
  if (!iso) return "--"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "--"
  const now = Date.now()
  const diff = now - date.getTime()
  if (diff < 60_000) return "刚刚"
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
}

// ---------- Issue 分组 ----------

interface IssueGroup {
  severity: IssueSeverity
  items: Issue[]
}

const ISSUE_GROUP_CONFIG: Record<
  IssueSeverity,
  {
    title: string
    bgClass: string
    borderClass: string
    textClass: string
    icon: typeof AlertTriangle
    iconClass: string
    role: "alert" | "status" | "none"
  }
> = {
  blocking: {
    title: "阻塞问题",
    bgClass: "bg-red-50",
    borderClass: "border-red-300",
    textClass: "text-red-800",
    icon: AlertTriangle,
    iconClass: "text-red-600",
    role: "alert",
  },
  warning: {
    title: "警告",
    bgClass: "bg-amber-50",
    borderClass: "border-amber-300",
    textClass: "text-amber-800",
    icon: WarningIcon,
    iconClass: "text-amber-600",
    role: "status",
  },
  info: {
    title: "提示",
    bgClass: "bg-slate-50",
    borderClass: "border-slate-200",
    textClass: "text-slate-700",
    icon: Info,
    iconClass: "text-slate-500",
    role: "none",
  },
}

function groupIssues(issues: Issue[]): IssueGroup[] {
  const groups: Record<IssueSeverity, Issue[]> = {
    blocking: [],
    warning: [],
    info: [],
  }
  for (const issue of issues) {
    groups[issue.severity].push(issue)
  }
  return (["blocking", "warning", "info"] as IssueSeverity[])
    .map((severity) => ({ severity, items: groups[severity] }))
    .filter((g) => g.items.length > 0)
}

// ---------- 单个 Issue 卡片 ----------

function IssueCard({ issue, group }: { issue: Issue; group: IssueGroup }) {
  const config = ISSUE_GROUP_CONFIG[group.severity]
  const Icon = config.icon
  return (
    <li
      role={config.role}
      className={`rounded-lg border ${config.borderClass} ${config.bgClass} px-3 py-2`}
    >
      <div className="flex items-start gap-2">
        <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${config.iconClass}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className={`text-xs font-semibold ${config.textClass}`}>
            {issue.code}
            {issue.stage && <span className="ml-1 font-normal opacity-75">· {issue.stage}</span>}
          </div>
          <p className={`mt-0.5 text-xs leading-5 ${config.textClass}`}>{issue.message}</p>
          <div className="mt-1 text-[10px] opacity-70">
            {issue.recoverable ? "可恢复" : "不可恢复"}
            {issue.evidence_id != null && ` · 证据 #${issue.evidence_id}`}
          </div>
        </div>
      </div>
    </li>
  )
}

// ---------- 最近产物卡片 ----------

function ArtifactItem({ artifact }: { artifact: WorkflowArtifact }) {
  const kindLabel = ARTIFACT_KIND_LABELS[artifact.kind] || artifact.kind
  const statusLabel = ARTIFACT_STATUS_LABELS[artifact.status] || artifact.status
  const isStale = artifact.status === "stale"
  return (
    <li className="rounded-lg border border-[#EAEAEA] bg-white px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-[#111111]">{kindLabel}</span>
        <span
          className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
            isStale
              ? "bg-amber-100 text-amber-700"
              : artifact.status === "archived"
                ? "bg-slate-100 text-slate-600"
                : "bg-emerald-50 text-emerald-700"
          }`}
        >
          {statusLabel}
        </span>
      </div>
      {artifact.summary && (
        <p className="mt-1 line-clamp-2 text-xs leading-5 text-[#565652]">{artifact.summary}</p>
      )}
      <div className="mt-1 text-[10px] text-[#787774]">{formatTime(artifact.updated_at || artifact.created_at)}</div>
    </li>
  )
}

// ---------- 文书流式生成占位（Task 4.3 实现） ----------

interface DocumentStreamPlaceholderProps {
  visible: boolean
}

function DocumentStreamPlaceholder({ visible }: DocumentStreamPlaceholderProps) {
  if (!visible) return null
  return (
    <section
      className="rounded-xl border border-sky-200 bg-sky-50/60 p-3"
      aria-label="文书流式生成"
    >
      <div className="flex items-center gap-2">
        <PenLine className="h-4 w-4 text-sky-600" aria-hidden="true" />
        <span className="text-xs font-semibold text-sky-700">文书流式生成中</span>
        <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-sky-500" aria-hidden="true" />
      </div>
      <p className="mt-2 text-[11px] leading-5 text-sky-700">
        正在逐段生成文书内容… 文书流式展示将在 Task 4.3 接入。
      </p>
    </section>
  )
}

// ---------- 主组件 ----------

export interface CurrentActivityPanelProps {
  run: WorkflowRun | null
  artifacts: WorkflowArtifact[]
  issues: Issue[]
}

export function CurrentActivityPanel({ run, artifacts, issues }: CurrentActivityPanelProps) {
  const status = run?.status
  const isRunning = status === "running"
  const isPaused = status === "pausing" || status === "waiting_user"

  // 最近 3 个产物（按时间倒序）
  const recentArtifacts = useMemo(() => {
    const sorted = [...artifacts].sort((a, b) => {
      const ta = new Date(a.updated_at || a.created_at).getTime()
      const tb = new Date(b.updated_at || b.created_at).getTime()
      return tb - ta
    })
    return sorted.slice(0, 3)
  }, [artifacts])

  const issueGroups = useMemo(() => groupIssues(issues), [issues])

  // 文书流式生成占位：当前节点为文书生成节点时展示
  const isDocumentStreaming =
    isRunning &&
    (run?.current_node === "complaint" || run?.current_node === "respond_complaint")

  const currentNodeLabel = nodeLabel(run?.current_node)
  const activityText = !run
    ? "尚未启动工作流"
    : isRunning
      ? `正在执行：${currentNodeLabel}`
      : isPaused
        ? `已暂停：${currentNodeLabel}`
        : status === "succeeded"
          ? "工作流已完成"
          : status === "failed"
            ? `执行失败${run.error_message ? `：${run.error_message}` : ""}`
            : status === "cancelled"
              ? "工作流已取消"
              : "等待开始"

  return (
    <section
      aria-label="当前活动"
      aria-live="polite"
      className="flex flex-col gap-3 rounded-2xl border border-[#EAEAEA] bg-white p-3 shadow-sm"
    >
      {/* 1. 当前正在做什么 */}
      <div className="flex items-center gap-2">
        {isRunning ? (
          <Loader2 className="h-4 w-4 animate-spin text-sky-500" aria-hidden="true" />
        ) : isPaused ? (
          <Pause className="h-4 w-4 text-amber-500" aria-hidden="true" />
        ) : status === "succeeded" ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-500" aria-hidden="true" />
        ) : status === "failed" || status === "cancelled" ? (
          <AlertTriangle className="h-4 w-4 text-red-500" aria-hidden="true" />
        ) : (
          <span className="inline-block h-2 w-2 rounded-full bg-slate-400" aria-hidden="true" />
        )}
        <span className="text-sm font-medium text-[#111111]">{activityText}</span>
      </div>

      {/* 2. 最近完成的产物 */}
      <div>
        <h4 className="mb-2 text-xs font-semibold text-[#565652]">最近完成的产物</h4>
        {recentArtifacts.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[#EAEAEA] bg-[#F7F6F3] px-3 py-2 text-xs text-[#787774]">
            暂无产物
          </p>
        ) : (
          <ul className="space-y-2">
            {recentArtifacts.map((artifact) => (
              <ArtifactItem key={artifact.id} artifact={artifact} />
            ))}
          </ul>
        )}
      </div>

      {/* 3. 需要用户注意的内容 */}
      <div>
        <h4 className="mb-2 text-xs font-semibold text-[#565652]">需要注意的内容</h4>
        {issueGroups.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[#EAEAEA] bg-[#F7F6F3] px-3 py-2 text-xs text-[#787774]">
            暂无需要关注的内容
          </p>
        ) : (
          <ul className="space-y-2">
            {issueGroups.map((group) => {
              const config = ISSUE_GROUP_CONFIG[group.severity]
              return (
                <li key={group.severity}>
                  <div className={`mb-1 flex items-center gap-1.5 px-1 text-[11px] font-semibold ${config.textClass}`}>
                    <config.icon className={`h-3.5 w-3.5 ${config.iconClass}`} aria-hidden="true" />
                    {config.title}（{group.items.length}）
                  </div>
                  <ul className="space-y-1.5">
                    {group.items.map((issue, idx) => (
                      <IssueCard key={`${issue.code}-${idx}`} issue={issue} group={group} />
                    ))}
                  </ul>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {/* 4. 文书流式生成占位（Task 4.3 实现） */}
      <DocumentStreamPlaceholder visible={isDocumentStreaming} />
    </section>
  )
}

export default CurrentActivityPanel
