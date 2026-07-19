// 质量摘要：三栏展示完整度 + 可信度 + 风险
// 对齐 spec 第 6.8 节 / Task 2.6.2
import { CheckCircle2, AlertTriangle, ShieldAlert } from "lucide-react"
import type { QualityReport } from "@/types/workflow"

// ---------- 格式化工具 ----------

function formatPercent(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return "--"
  const clamped = Math.max(0, Math.min(1, value))
  return `${Math.round(clamped * 100)}%`
}

interface MetricConfig {
  status: "pass" | "warn" | "fail"
  textClass: string
  bgClass: string
  borderClass: string
  barClass: string
}

function metricConfigFromStatus(status: "pass" | "warn" | "fail"): MetricConfig {
  switch (status) {
    case "pass":
      return {
        status,
        textClass: "text-emerald-700",
        bgClass: "bg-emerald-50",
        borderClass: "border-emerald-200",
        barClass: "bg-emerald-500",
      }
    case "warn":
      return {
        status,
        textClass: "text-amber-700",
        bgClass: "bg-amber-50",
        borderClass: "border-amber-200",
        barClass: "bg-amber-500",
      }
    case "fail":
      return {
        status,
        textClass: "text-red-700",
        bgClass: "bg-red-50",
        borderClass: "border-red-200",
        barClass: "bg-red-500",
      }
  }
}

function coverageStatus(coverage: number): "pass" | "warn" | "fail" {
  if (coverage >= 0.9) return "pass"
  if (coverage >= 0.7) return "warn"
  return "fail"
}

function scoreStatus(score: number, status: QualityReport["status"]): "pass" | "warn" | "fail" {
  if (status === "fail" || score < 0.6) return "fail"
  if (status === "warn" || score < 0.85) return "warn"
  return "pass"
}

function riskStatus(blockingCount: number): "pass" | "warn" | "fail" {
  if (blockingCount === 0) return "pass"
  if (blockingCount <= 2) return "warn"
  return "fail"
}

// ---------- 单指标卡片 ----------

interface MetricCardProps {
  label: string
  value: string
  caption: string
  config: MetricConfig
  progress?: number // 0-1，用于进度条
  icon: typeof CheckCircle2
}

function MetricCard({ label, value, caption, config, progress, icon: Icon }: MetricCardProps) {
  return (
    <div
      className={`flex flex-col rounded-xl border px-3 py-3 ${config.bgClass} ${config.borderClass}`}
      role="group"
      aria-label={`${label}：${value}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {label}
        </span>
        <Icon className={`h-4 w-4 ${config.textClass}`} aria-hidden="true" />
      </div>
      <div className={`mt-1 text-2xl font-semibold ${config.textClass}`} aria-live="polite">
        {value}
      </div>
      {progress != null && (
        <div
          className="mt-2 h-1 w-full overflow-hidden rounded-full bg-white/60"
          role="progressbar"
          aria-valuenow={Math.round(progress * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${label}进度`}
        >
          <div
            className={`h-full rounded-full ${config.barClass}`}
            style={{ width: `${Math.max(0, Math.min(1, progress)) * 100}%` }}
          />
        </div>
      )}
      <p className="mt-2 text-[11px] text-slate-600">{caption}</p>
    </div>
  )
}

// ---------- 主组件 ----------

export interface QualitySummaryWarning {
  title: string
  detail: string
}

export interface QualitySummaryProps {
  quality: QualityReport | null
  /**
   * 额外告警（input-quality-guard Gate 1：证据类型匹配度偏低等）。
   * 由页面从 issues 派生传入，渲染为橙色告警条。
   */
  warnings?: QualitySummaryWarning[]
}

export function QualitySummary({ quality, warnings = [] }: QualitySummaryProps) {
  if (!quality && warnings.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
        暂无质量报告
      </div>
    )
  }

  const coverage = quality?.coverage ?? 0
  const score = quality?.score ?? 0
  const blockingCount = quality?.blocking_issues?.length ?? 0

  const coverageCfg = metricConfigFromStatus(coverageStatus(coverage))
  const scoreCfg = metricConfigFromStatus(scoreStatus(score, quality?.status ?? "warn"))
  const riskCfg = metricConfigFromStatus(riskStatus(blockingCount))

  const riskCaption =
    blockingCount === 0
      ? "无阻塞问题"
      : `${blockingCount} 个阻塞问题需处理`

  return (
    <div className="space-y-3" role="region" aria-label="质量摘要">
      {/* Gate 1：证据类型匹配度偏低等橙色告警 */}
      {warnings.length > 0 && (
        <div className="space-y-2">
          {warnings.map((w, idx) => (
            <div
              key={idx}
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-800"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" aria-hidden="true" />
              <div>
                <p className="font-medium">{w.title}</p>
                {w.detail && <p className="mt-0.5 text-amber-700">{w.detail}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      {quality && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <MetricCard
            label="完整度"
            value={formatPercent(coverage)}
            caption={`字段覆盖率${coverage >= 0.9 ? "良好" : coverage >= 0.7 ? "一般" : "偏低"}`}
            config={coverageCfg}
            progress={coverage}
            icon={CheckCircle2}
          />
          <MetricCard
            label="可信度"
            value={formatPercent(score)}
            caption={
              score >= 0.85 ? "高可信" : score >= 0.6 ? "建议核对" : "必须确认"
            }
            config={scoreCfg}
            progress={score}
            icon={AlertTriangle}
          />
          <MetricCard
            label="风险"
            value={String(blockingCount)}
            caption={riskCaption}
            config={riskCfg}
            icon={ShieldAlert}
          />
        </div>
      )}
    </div>
  )
}

export default QualitySummary
