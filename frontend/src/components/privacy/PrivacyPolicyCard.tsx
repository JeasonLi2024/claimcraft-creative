// 扫描范围与免责声明（设计文档 §13.5/§14.3）。
// 文案准确：扫描只生成建议、不修改原始证据；未发现不代表绝对不存在。
import { Info, Loader2, RefreshCw, ScanSearch } from "lucide-react"
import { cn } from "@/lib/utils"

export interface PrivacyPolicyCardProps {
  onRescan: () => void
  scanning?: boolean
}

const SCOPE_ITEMS = [
  "文本：证据描述、OCR 文本与摘要、抽取字段、时间线、最新文书",
  "图片：证据图片中的敏感文字区域",
  "识别类型：身份证号、手机号、结构化地址（自动建议，需人工复核）",
]

export function PrivacyPolicyCard({ onRescan, scanning = false }: PrivacyPolicyCardProps) {
  return (
    <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent text-secondary">
            <ScanSearch className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">扫描范围</p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">识别可能的敏感信息</h2>
            <p className="mt-1 text-sm text-muted-foreground">扫描只会生成建议，不会修改原始证据。</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onRescan}
          disabled={scanning}
          className="inline-flex min-h-[40px] items-center gap-2 rounded-xl bg-[#17231d] px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {scanning ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          {scanning ? "扫描中..." : "重新扫描"}
        </button>
      </div>

      <ul className="mt-5 grid gap-2 sm:grid-cols-2">
        {SCOPE_ITEMS.map((text) => (
          <li key={text} className="flex items-start gap-2 rounded-xl border border-border bg-white px-3.5 py-2.5 text-xs leading-5 text-muted-foreground">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-secondary" aria-hidden="true" />
            {text}
          </li>
        ))}
      </ul>

      <div className="mt-4 flex items-start gap-2 rounded-xl border border-[#e5d9b5] bg-[#fef9ec] px-4 py-3 text-xs leading-5 text-[#6f5a25]">
        <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>未发现不代表绝对不存在，请在对外分享前核对图片与最新文书；自动识别不能替代人工检查。</span>
      </div>
    </section>
  )
}

export default PrivacyPolicyCard
