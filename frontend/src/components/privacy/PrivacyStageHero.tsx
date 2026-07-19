// 隐私阶段 Hero：深墨色阶段头 + 3 项可执行指标（设计文档 §13.2/§13.3）。
// 指标诚实反映完成度：待复核项 / 已打码图片 / 高风险项（不用「涉及类型」）。
import { ScanFace, ShieldCheck, ShieldAlert, Sparkles } from "lucide-react"

export interface PrivacyStageHeroProps {
  caseTitle: string
  caseTypeLabel?: string
  pendingCount: number
  maskedImageCount: number
  highRiskCount: number
}

export function PrivacyStageHero({
  caseTitle,
  caseTypeLabel,
  pendingCount,
  maskedImageCount,
  highRiskCount,
}: PrivacyStageHeroProps) {
  const metrics = [
    { label: "待复核项", value: pendingCount, icon: ScanFace },
    { label: "已打码图片", value: maskedImageCount, icon: ShieldCheck },
    { label: "高风险项", value: highRiskCount, icon: ShieldAlert },
  ]
  return (
    <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
      <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
      <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70">
            <Sparkles className="h-3.5 w-3.5 text-[#d8b967]" aria-hidden="true" />
            隐私风险检查
          </div>
          <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">隐私检查与打码</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">
            系统先识别可能的敏感信息并生成遮罩建议，请在对外分享前逐项复核。自动识别不能替代人工检查。
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{caseTitle || "当前案件"}</span>
            {caseTypeLabel && (
              <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{caseTypeLabel}</span>
            )}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 self-end">
          {metrics.map((item) => (
            <div key={item.label} className="rounded-2xl border border-white/10 bg-white/8 p-4 backdrop-blur-sm">
              <div className="flex items-center justify-between text-white/45">
                <span className="text-xs">{item.label}</span>
                <item.icon className="h-4 w-4" aria-hidden="true" />
              </div>
              <div className="mt-2 text-2xl font-semibold">{item.value}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default PrivacyStageHero
