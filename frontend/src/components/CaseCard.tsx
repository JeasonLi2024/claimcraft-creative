import { Link } from "react-router"
import { cn } from "@/lib/utils"
import { useStatus } from "@/composables/useStatus"
import { useFormat } from "@/composables/useFormat"
import StatusTag from "./StatusTag"
import {
  ArrowUpRight,
  Clock,
  FileCheck2,
  FileText,
  GitBranch,
  MessageSquareText,
  ShieldCheck,
  Trash2,
} from "lucide-react"
import type { Case } from "@/types"

interface CaseCardProps {
  caseData: Case
  onDelete?: (id: number) => void
  className?: string
}

const typeAccent: Record<string, string> = {
  shopping: "from-[#dce9e1] to-[#eef3ef] text-[#315a48]",
  service: "from-[#ebe5d8] to-[#f5f1e8] text-[#705d39]",
  secondhand: "from-[#e1e5ea] to-[#f0f2f4] text-[#485665]",
  other: "from-[#e8e5ea] to-[#f3f1f4] text-[#62556a]",
}

export default function CaseCard({ caseData, onDelete, className }: CaseCardProps) {
  const { disputeLabel } = useStatus()
  const { formatTime } = useFormat()
  const progressItems = [
    { label: "证据", value: caseData.evidence_count, icon: FileText },
    { label: "节点", value: caseData.timeline_count, icon: GitBranch },
    { label: "文稿", value: caseData.template_count, icon: MessageSquareText },
  ]
  const progress = caseData.status === "closed" ? 100 : caseData.status === "submitted" ? 78 : caseData.status === "processing" ? 48 : caseData.status === "cancelled" ? 0 : 18

  return (
    <article className={cn("group relative overflow-hidden rounded-2xl border border-[#d9ddd5] bg-white transition-all duration-300 hover:-translate-y-1 hover:border-[#b8c3ba] hover:shadow-[0_22px_55px_rgba(31,45,38,.10)]", className)}>
      <div className={`h-1.5 bg-gradient-to-r ${typeAccent[caseData.case_type] || typeAccent.other}`} />
      <Link to={`/cases/${caseData.id}/workspace`} className="block p-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#3f6b57] sm:p-6">
        <div className="flex items-start justify-between gap-4 pr-8">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-lg bg-gradient-to-r px-2.5 py-1 text-[11px] font-semibold ${typeAccent[caseData.case_type] || typeAccent.other}`}>{disputeLabel(caseData.case_type)}</span>
              <StatusTag status={caseData.status} />
              <span className="rounded-lg bg-[#f1f2ee] px-2 py-1 text-[10px] font-medium text-[#69706b]">{caseData.case_mode === "respond" ? "商家反证" : "维权投诉"}</span>
            </div>
            <h3 className="mt-4 line-clamp-1 text-lg font-semibold tracking-[-0.02em] text-[#181b1a] transition-colors group-hover:text-[#2f5947]">{caseData.title}</h3>
          </div>
          <span className="absolute right-5 top-8 flex h-8 w-8 items-center justify-center rounded-full border border-[#d9ddd5] bg-white text-[#737a75] transition-all group-hover:border-[#3f6b57] group-hover:bg-[#3f6b57] group-hover:text-white"><ArrowUpRight className="h-4 w-4" /></span>
        </div>

        <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-[#69706b]">{caseData.description || "尚未补充案件描述，进入工作区完善争议经过与诉求。"}</p>

        <div className="mt-5 grid grid-cols-3 gap-2">
          {progressItems.map(({ label, value, icon: Icon }) => (
            <div key={label} className="rounded-xl bg-[#f5f6f2] px-3 py-2.5">
              <div className="flex items-center gap-1.5 text-[10px] text-[#858b86]"><Icon className="h-3 w-3" />{label}</div>
              <p className="mt-1 text-base font-semibold text-[#303531]">{value || 0}</p>
            </div>
          ))}
        </div>

        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between text-[10px] text-[#858b86]"><span>材料整理进度</span><span>{progress}%</span></div>
          <div className="h-1.5 overflow-hidden rounded-full bg-[#e8ebe6]"><div className="h-full rounded-full bg-[#3f6b57] transition-all" style={{ width: `${progress}%` }} /></div>
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-[#e7eae5] pt-4 text-xs text-[#7a817c]">
          <span className="flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" />{formatTime(caseData.updated_at || caseData.created_at)}</span>
          <span className="flex items-center gap-1.5 font-medium text-[#3f6b57]">继续整理<FileCheck2 className="h-3.5 w-3.5" /></span>
        </div>
      </Link>

      {onDelete && (
        <button onClick={() => onDelete(caseData.id)} className="absolute right-4 top-[76px] rounded-lg p-2 text-[#8b918c] opacity-0 transition-all hover:bg-[#fff0ee] hover:text-[#b5493e] focus:opacity-100 group-hover:opacity-100" title="删除案件" aria-label={`删除案件：${caseData.title}`}><Trash2 className="h-4 w-4" /></button>
      )}
      {caseData.extracted_field_count > 0 && <div className="pointer-events-none absolute bottom-[73px] right-5 hidden items-center gap-1 text-[9px] text-[#65806f] sm:flex"><ShieldCheck className="h-3 w-3" />已抽取 {caseData.extracted_field_count} 个字段</div>}
    </article>
  )
}
