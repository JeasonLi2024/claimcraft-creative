// 完成确认区（设计文档 §13.10/§14.3）。
// 诚实语义：本阶段无持久化「已确认」模型，这里是本地复核确认——阅读免责说明并满足条件后，
// 启用「前往导出」。不声称材料已绝对安全。
import { useState } from "react"
import { useNavigate } from "react-router"
import { Check, CircleAlert, ShieldAlert } from "lucide-react"
import { cn } from "@/lib/utils"

export interface CompletionCondition {
  label: string
  met: boolean
}

export interface PrivacyCompletionPanelProps {
  caseId: number
  conditions: CompletionCondition[]
  /** 高风险文本项数量：仅作提示，不阻断确认。 */
  highRiskTextCount?: number
}

export function PrivacyCompletionPanel({
  caseId,
  conditions,
  highRiskTextCount = 0,
}: PrivacyCompletionPanelProps) {
  const navigate = useNavigate()
  const [acknowledged, setAcknowledged] = useState(false)
  const allMet = conditions.every((c) => c.met)
  const canConfirm = allMet && acknowledged

  return (
    <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">完成本轮复核</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">确认前请核对以下条件</h2>
      </div>

      <ul className="mt-5 space-y-2.5">
        {conditions.map((c) => (
          <li key={c.label} className="flex items-start gap-2.5 text-sm">
            <span
              className={cn(
                "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                c.met
                  ? "border-emerald-200 bg-emerald-50 text-emerald-600"
                  : "border-[#e5d9b5] bg-[#fef9ec] text-[#a07d2a]",
              )}
            >
              {c.met ? (
                <Check className="h-3 w-3" aria-hidden="true" />
              ) : (
                <CircleAlert className="h-3 w-3" aria-hidden="true" />
              )}
            </span>
            <span className={cn("leading-5", c.met ? "text-foreground" : "text-muted-foreground")}>
              {c.label}
            </span>
          </li>
        ))}
      </ul>

      {highRiskTextCount > 0 && (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-[#e5d9b5] bg-[#fef9ec] px-3.5 py-3 text-xs leading-5 text-[#6f5a25]">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            另有 {highRiskTextCount} 个高风险文本项（如身份证号），文本项不阻断确认，但强烈建议在对外分享前核对。
          </span>
        </div>
      )}

      <label className="mt-5 flex items-start gap-2.5 rounded-xl border border-border bg-white px-3.5 py-3 text-sm leading-5">
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(e) => setAcknowledged(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-input text-secondary focus:ring-secondary"
        />
        <span className="text-muted-foreground">
          我已阅读自动识别说明并检查了图片其他区域，理解未发现不代表绝对不存在。
        </span>
      </label>

      <button
        type="button"
        disabled={!canConfirm}
        onClick={() => navigate(`/cases/${caseId}/export`)}
        className="mt-5 inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl bg-[#17231d] px-5 text-sm font-semibold text-white transition-all hover:-translate-y-0.5 hover:opacity-95 disabled:translate-y-0 disabled:opacity-50"
      >
        确认本轮隐私复核
      </button>
      <p className="mt-2 text-center text-[11px] text-muted-foreground">
        确认为本地复核记录，不会更改原始证据；正式 PDF/Word 仍使用原图。
      </p>
    </section>
  )
}

export default PrivacyCompletionPanel
