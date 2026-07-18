// 质量徽章：三档业务标签（高可信 / 建议核对 / 必须确认）
// 对齐 spec 第 6.8 节 / Task 2.6.3
import { CheckCircle2, AlertTriangle, ShieldAlert } from "lucide-react"
import type { QualityReport } from "@/types/workflow"

export type QualityTier = "high" | "review" | "must_confirm"

export interface QualityBadgeProps {
  quality: QualityReport | null
  size?: "sm" | "md" | "lg"
}

// ---------- 档位计算 ----------

export function computeQualityTier(quality: QualityReport | null): QualityTier {
  if (!quality) return "must_confirm"
  const score = quality.score ?? 0
  if (quality.status === "fail" || score < 0.6) return "must_confirm"
  if (quality.status === "warn" || score < 0.85) return "review"
  return "high"
}

// ---------- 档位配置 ----------

interface TierConfig {
  label: string
  icon: typeof CheckCircle2
  textClass: string
  bgClass: string
  borderClass: string
}

const TIER_CONFIG: Record<QualityTier, TierConfig> = {
  high: {
    label: "高可信",
    icon: CheckCircle2,
    textClass: "text-emerald-700",
    bgClass: "bg-emerald-50",
    borderClass: "border-emerald-200",
  },
  review: {
    label: "建议核对",
    icon: AlertTriangle,
    textClass: "text-amber-700",
    bgClass: "bg-amber-50",
    borderClass: "border-amber-200",
  },
  must_confirm: {
    label: "必须确认",
    icon: ShieldAlert,
    textClass: "text-red-700",
    bgClass: "bg-red-50",
    borderClass: "border-red-200",
  },
}

const SIZE_CLASS: Record<NonNullable<QualityBadgeProps["size"]>, string> = {
  sm: "text-[10px] px-1.5 py-0.5 gap-1",
  md: "text-xs px-2 py-0.5 gap-1",
  lg: "text-sm px-2.5 py-1 gap-1.5",
}

const ICON_SIZE: Record<NonNullable<QualityBadgeProps["size"]>, string> = {
  sm: "h-2.5 w-2.5",
  md: "h-3 w-3",
  lg: "h-3.5 w-3.5",
}

// ---------- 主组件 ----------

export function QualityBadge({ quality, size = "md" }: QualityBadgeProps) {
  const tier = computeQualityTier(quality)
  const config = TIER_CONFIG[tier]
  const Icon = config.icon

  return (
    <span
      className={`inline-flex items-center rounded-full border font-medium ${SIZE_CLASS[size]} ${config.bgClass} ${config.borderClass} ${config.textClass}`}
      role="status"
      aria-label={`质量等级：${config.label}`}
    >
      <Icon className={ICON_SIZE[size]} aria-hidden="true" />
      {config.label}
    </span>
  )
}

export default QualityBadge
