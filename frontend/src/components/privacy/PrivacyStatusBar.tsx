// 隐私阶段状态条（设计文档 §13.4/§14.2）：图标 + 文字 + 说明 + 主操作。
// 状态不只靠颜色表达——每态均有图标与文字标签。
import { cn } from "@/lib/utils"
import { STAGE_META, type PrivacyStage } from "@/types/privacy"

const TONE_STYLES: Record<
  "neutral" | "warning" | "success" | "danger",
  { wrap: string; icon: string; button: string }
> = {
  neutral: {
    wrap: "border-border bg-card text-foreground",
    icon: "bg-muted text-muted-foreground",
    button: "border border-border bg-white text-foreground hover:bg-muted",
  },
  warning: {
    wrap: "border-[#e5d9b5] bg-[#fef9ec] text-[#6f5a25]",
    icon: "bg-[#f5ecd1] text-[#806622]",
    button: "border border-[#dfd1a7] bg-white/70 text-[#6f5a25] hover:bg-white",
  },
  success: {
    wrap: "border-emerald-200 bg-emerald-50 text-emerald-800",
    icon: "bg-emerald-100 text-emerald-700",
    button: "bg-[#17231d] text-white hover:opacity-90",
  },
  danger: {
    wrap: "border-red-200 bg-red-50 text-red-800",
    icon: "bg-red-100 text-red-700",
    button: "border border-red-300 bg-white text-red-700 hover:bg-red-50",
  },
}

export interface PrivacyStatusBarProps {
  stage: PrivacyStage
  /** 扫描/进度补充说明（如「已处理 2 / 5 张」） */
  progressText?: string
  onPrimary?: () => void
}

export function PrivacyStatusBar({ stage, progressText, onPrimary }: PrivacyStatusBarProps) {
  const meta = STAGE_META[stage]
  const Icon = meta.icon
  const tone = TONE_STYLES[meta.tone]
  return (
    <section
      role="status"
      aria-live="polite"
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-[24px] border px-5 py-4 shadow-[0_12px_36px_rgba(31,45,38,.05)]",
        tone.wrap,
      )}
    >
      <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl", tone.icon)}>
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{meta.title}</p>
        <p className="mt-0.5 text-sm leading-5 opacity-80">
          {meta.description}
          {progressText ? ` ${progressText}` : ""}
        </p>
      </div>
      {onPrimary && (
        <button
          type="button"
          onClick={onPrimary}
          className={cn(
            "inline-flex min-h-[40px] shrink-0 items-center gap-1.5 rounded-xl px-4 text-sm font-semibold transition-colors",
            tone.button,
          )}
        >
          {meta.actionLabel}
        </button>
      )}
    </section>
  )
}

export default PrivacyStatusBar
