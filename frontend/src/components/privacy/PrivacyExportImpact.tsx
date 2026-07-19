// 导出影响说明（设计文档 §13.9/§12.1）：明确当前 PDF/Word/ZIP 仍使用原图，
// 只有文本预览可脱敏。避免用户误以为 /mask 结果会自动替换正式原图。
import { Link } from "react-router"
import { ChevronRight, FileText, ShieldAlert } from "lucide-react"

export interface PrivacyExportImpactProps {
  caseId: number
}

const IMPACTS = [
  { title: "PDF / Word", detail: "原始证据版，证据图片使用原图。" },
  { title: "ZIP 材料包", detail: "包含原图；已有打码图作为附加副本。" },
  { title: "文本预览", detail: "仅在开启脱敏选项时对文本进行脱敏。" },
]

export function PrivacyExportImpact({ caseId }: PrivacyExportImpactProps) {
  return (
    <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_32px_rgba(31,45,38,.05)]">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-secondary">
          <FileText className="h-5 w-5" aria-hidden="true" />
        </span>
        <div>
          <h2 className="text-sm font-semibold">对导出的影响</h2>
          <p className="text-xs text-muted-foreground">原图与隐私分享版的区别</p>
        </div>
      </div>

      <ul className="mt-4 space-y-3">
        {IMPACTS.map((item) => (
          <li key={item.title} className="text-sm">
            <p className="font-medium text-foreground">{item.title}</p>
            <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{item.detail}</p>
          </li>
        ))}
      </ul>

      <div className="mt-4 flex items-start gap-2 rounded-xl border border-[#e5d9b5] bg-[#fef9ec] px-3.5 py-3 text-xs leading-5 text-[#6f5a25]">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>本页的打码结果不会自动替换正式 PDF/Word 中的原图，请按接收对象谨慎选择导出方式。</span>
      </div>

      <Link
        to={`/cases/${caseId}/export`}
        className="mt-4 inline-flex min-h-[40px] w-full items-center justify-center gap-1.5 rounded-xl border border-border bg-white px-4 text-sm font-semibold transition-colors hover:bg-muted"
      >
        前往导出
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </Link>
    </section>
  )
}

export default PrivacyExportImpact
