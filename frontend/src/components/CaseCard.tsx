import { cn } from "@/lib/utils"
import { useStatus } from "@/composables/useStatus"
import { useFormat } from "@/composables/useFormat"
import StatusTag from "./StatusTag"
import { FileText, Clock, Trash2 } from "lucide-react"
import type { Case } from "@/types"

interface CaseCardProps {
  caseData: Case
  onDelete?: (id: number) => void
  className?: string
}

export default function CaseCard({ caseData, onDelete, className }: CaseCardProps) {
  const { disputeLabel } = useStatus()
  const { formatTime } = useFormat()

  return (
    <div
      className={cn(
        "group relative rounded-2xl border border-border/50 bg-card p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-lg",
        className
      )}
    >
      {/* Delete button */}
      {onDelete && (
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onDelete(caseData.id) }}
          className="absolute right-3 top-3 rounded-lg p-1.5 text-muted-foreground opacity-0 transition-all hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
          title="删除案件"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      )}

      {/* Title */}
      <h3 className="pr-8 text-base font-semibold text-foreground transition-colors group-hover:text-primary">
        {caseData.title}
      </h3>

      {/* Description */}
      <p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
        {caseData.description || "暂无描述"}
      </p>

      {/* Tags */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {caseData.dispute_type && (
          <span className="rounded-lg bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">
            {disputeLabel(caseData.dispute_type)}
          </span>
        )}
        <StatusTag status={caseData.status} />
      </div>

      {/* Meta */}
      <div className="mt-4 flex items-center gap-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <FileText className="h-3.5 w-3.5" />
          {caseData.evidence_count} 条证据
        </span>
        <span className="flex items-center gap-1">
          <Clock className="h-3.5 w-3.5" />
          {formatTime(caseData.updated_at || caseData.created_at)}
        </span>
      </div>
    </div>
  )
}
