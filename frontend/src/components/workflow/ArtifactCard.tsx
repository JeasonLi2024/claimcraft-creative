// 工作流产物卡片：标题 + 状态版本 + 业务摘要 + 关键指标 + 主体内容 + 来源依据 + 操作区
// 对齐 spec.md Task 3.6.3 + Task 3.6.5（过期产物提示）
// 从 workflow-run-store.artifacts 渲染单条产物
import { useState } from "react"
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  GitBranch,
  RefreshCw,
  ShieldAlert,
} from "lucide-react"
import type { WorkflowArtifact, WorkflowArtifactKind, WorkflowArtifactStatus } from "@/types/workflow"

// ---------- artifact kind 中文标签 ----------

const ARTIFACT_KIND_LABELS: Record<WorkflowArtifactKind, string> = {
  preclassify: "证据预分类",
  ocr: "OCR 识别结果",
  classify: "证据分类",
  extract: "字段抽取",
  evidence_chain: "证据链",
  complaint: "投诉书",
  respond_complaint: "反证答辩书",
}

// ---------- status 配置 ----------

interface StatusConfig {
  label: string
  dotClass: string
  textClass: string
  bgClass: string
  borderClass: string
}

const STATUS_CONFIG: Record<WorkflowArtifactStatus, StatusConfig> = {
  active: {
    label: "当前版本",
    dotClass: "bg-emerald-500",
    textClass: "text-emerald-700",
    bgClass: "bg-emerald-50",
    borderClass: "border-emerald-200",
  },
  stale: {
    label: "已过期",
    dotClass: "bg-amber-500",
    textClass: "text-amber-700",
    bgClass: "bg-amber-50",
    borderClass: "border-amber-200",
  },
  archived: {
    label: "已归档",
    dotClass: "bg-slate-400",
    textClass: "text-slate-600",
    bgClass: "bg-slate-50",
    borderClass: "border-slate-200",
  },
}

// ---------- payload 解析 ----------

interface QualityPayload {
  score?: number
  coverage?: number
  status?: string
}

interface MetricsPayload {
  duration_ms?: number
  model_calls?: number
}

interface ProvenanceItem {
  node?: string
  evidence_id?: number
  field_name?: string
  source_ref?: string
  ts?: string
}

function readQuality(payload: Record<string, unknown>): QualityPayload | null {
  const q = payload.quality
  if (q && typeof q === "object") return q as QualityPayload
  return null
}

function readMetrics(payload: Record<string, unknown>): MetricsPayload | null {
  const m = payload.metrics
  if (m && typeof m === "object") return m as MetricsPayload
  return null
}

function readProvenance(payload: Record<string, unknown>): ProvenanceItem[] {
  const p = payload.provenance
  if (!Array.isArray(p)) return []
  return p.filter((x) => x && typeof x === "object") as ProvenanceItem[]
}

function readContent(payload: Record<string, unknown>): string | null {
  // 优先取 content / document / text 字段
  const c = payload.content ?? payload.document ?? payload.text
  if (typeof c === "string") return c
  return null
}

// ---------- 格式化辅助 ----------

function formatScore(score: number | undefined | null): string {
  if (score == null || Number.isNaN(score)) return "--"
  // score 可能是 0-1 或 0-100
  const pct = score <= 1 ? Math.round(score * 100) : Math.round(score)
  return `${pct}%`
}

function formatDuration(ms: number | undefined | null): string {
  if (ms == null || Number.isNaN(ms)) return "--"
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const min = Math.floor(ms / 60000)
  const sec = Math.round((ms % 60000) / 1000)
  return `${min}m${sec}s`
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

// ---------- 主组件 ----------

export interface ArtifactCardProps {
  artifact: WorkflowArtifact
  /** 点击「查看详情」时触发 */
  onViewDetails?: (artifact: WorkflowArtifact) => void
  /** 点击「标记为 stale」时触发（仅 active 状态可操作） */
  onMarkStale?: (artifactId: number) => void
  /** 默认展开内容（用于时间线中突出某项） */
  defaultExpanded?: boolean
}

export function ArtifactCard({
  artifact,
  onViewDetails,
  onMarkStale,
  defaultExpanded = false,
}: ArtifactCardProps) {
  const [contentExpanded, setContentExpanded] = useState(defaultExpanded)
  const [provenanceExpanded, setProvenanceExpanded] = useState(false)

  const statusConfig = STATUS_CONFIG[artifact.status]
  const kindLabel = ARTIFACT_KIND_LABELS[artifact.kind] ?? artifact.kind
  const quality = readQuality(artifact.payload)
  const metrics = readMetrics(artifact.payload)
  const provenance = readProvenance(artifact.payload)
  const content = readContent(artifact.payload)
  const isStale = artifact.status === "stale"
  const canMarkStale = artifact.status === "active" && Boolean(onMarkStale)

  return (
    <article
      className={`overflow-hidden rounded-xl border bg-white shadow-sm transition ${
        isStale ? "border-amber-300 ring-1 ring-amber-200" : statusConfig.borderClass
      }`}
      aria-label={`产物 ${kindLabel}`}
    >
      {/* Task 3.6.5：stale 顶部警告条 */}
      {isStale && (
        <div
          role="alert"
          className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] text-amber-800"
        >
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
          <span>上游已变更，建议重新生成此产物</span>
        </div>
      )}

      {/* 头部：标题 + 状态徽章 */}
      <header className="flex items-start gap-3 px-4 py-3">
        <div className={`rounded-lg p-2 ${statusConfig.bgClass}`}>
          <FileText className={`h-4 w-4 ${statusConfig.textClass}`} aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-900">{kindLabel}</h3>
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${statusConfig.bgClass} ${statusConfig.borderClass} ${statusConfig.textClass}`}
              role="status"
              aria-label={`状态：${statusConfig.label}`}
            >
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${statusConfig.dotClass}`} aria-hidden="true" />
              {statusConfig.label}
            </span>
            <span className="font-mono text-[10px] text-slate-500">
              #{artifact.id}
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-600 break-words">
            {artifact.summary || "无摘要"}
          </p>
        </div>
      </header>

      {/* 关键指标 */}
      {(quality || metrics) && (
        <div className="grid grid-cols-2 gap-px border-y border-slate-100 bg-slate-100 sm:grid-cols-4">
          {quality && (
            <>
              <MetricItem label="质量评分" value={formatScore(quality.score)} />
              <MetricItem label="覆盖率" value={formatScore(quality.coverage)} />
            </>
          )}
          {metrics && (
            <>
              <MetricItem label="耗时" value={formatDuration(metrics.duration_ms)} />
              <MetricItem label="模型调用" value={String(metrics.model_calls ?? "--")} />
            </>
          )}
          {/* 填充空格以保持网格对齐 */}
          {(!quality || !metrics) && (
            <MetricItem label="创建时间" value={formatTimestamp(artifact.created_at)} />
          )}
        </div>
      )}

      {/* 主体内容（可折叠） */}
      {content && (
        <div className="border-b border-slate-100">
          <button
            type="button"
            onClick={() => setContentExpanded((v) => !v)}
            aria-expanded={contentExpanded}
            className="flex w-full items-center justify-between px-4 py-2 text-left text-xs font-medium text-slate-700 transition hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
          >
            <span className="flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
              主体内容
            </span>
            {contentExpanded ? (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>
          {contentExpanded && (
            <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap border-t border-slate-100 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-800">
              {content}
            </pre>
          )}
        </div>
      )}

      {/* 来源依据（可折叠） */}
      {provenance.length > 0 && (
        <div className="border-b border-slate-100">
          <button
            type="button"
            onClick={() => setProvenanceExpanded((v) => !v)}
            aria-expanded={provenanceExpanded}
            className="flex w-full items-center justify-between px-4 py-2 text-left text-xs font-medium text-slate-700 transition hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
          >
            <span className="flex items-center gap-1.5">
              <GitBranch className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
              来源依据（{provenance.length}）
            </span>
            {provenanceExpanded ? (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>
          {provenanceExpanded && (
            <ul className="divide-y divide-slate-100 border-t border-slate-100">
              {provenance.map((item, idx) => (
                <li key={idx} className="px-4 py-2 text-[11px] text-slate-700">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                    {item.node && (
                      <span className="font-mono text-[10px] text-slate-500">@{item.node}</span>
                    )}
                    {item.evidence_id != null && (
                      <span className="text-sky-700">证据 #{item.evidence_id}</span>
                    )}
                    {item.field_name && (
                      <span className="text-slate-600">字段：{item.field_name}</span>
                    )}
                  </div>
                  {item.source_ref && (
                    <p className="mt-0.5 font-mono text-[10px] text-slate-500 break-all">
                      {item.source_ref}
                    </p>
                  )}
                  {item.ts && (
                    <p className="mt-0.5 text-[10px] text-slate-400">
                      <Clock className="mr-1 inline h-2.5 w-2.5" aria-hidden="true" />
                      {formatTimestamp(item.ts)}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* 操作区 */}
      <footer className="flex flex-wrap items-center justify-end gap-2 px-4 py-2.5">
        {onViewDetails && (
          <button
            type="button"
            onClick={() => onViewDetails(artifact)}
            className="inline-flex min-h-[36px] items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
          >
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            查看详情
          </button>
        )}
        {canMarkStale && (
          <button
            type="button"
            onClick={() => onMarkStale?.(artifact.id)}
            className="inline-flex min-h-[36px] items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700 transition hover:bg-amber-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300"
          >
            <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
            标记为过期
          </button>
        )}
        {isStale && (
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-700">
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
            等待重新生成
          </span>
        )}
      </footer>
    </article>
  )
}

// ---------- 内部子组件 ----------

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white px-3 py-2">
      <dt className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-0.5 font-mono text-xs font-semibold text-slate-800">{value}</dd>
    </div>
  )
}

export default ArtifactCard
