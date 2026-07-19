// 图片复核清单（设计文档 §13.7）：突出每图状态与下一步动作。
// 无画布编辑器（Phase C），故「查看并调整」= 原图/打码图对比 + 单图重新打码。
import { Images, Loader2, RefreshCw, Shield, ZoomIn } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Evidence } from "@/types/case"
import { MASK_STATUS_META, type ImageMaskStatus } from "@/types/privacy"

export interface ImageReviewGridProps {
  images: Evidence[]
  busyId: number | null
  onRemask: (evidenceId: number) => void
  onPreview: (src: string, label: string) => void
}

function statusOf(evidence: Evidence): ImageMaskStatus {
  const s = evidence.mask_status
  if (s === "pending" || s === "done" || s === "failed") return s
  return "none"
}

function ImageReviewCard({
  evidence,
  busy,
  onRemask,
  onPreview,
}: {
  evidence: Evidence
  busy: boolean
  onRemask: (id: number) => void
  onPreview: (src: string, label: string) => void
}) {
  const status = statusOf(evidence)
  const meta = MASK_STATUS_META[status]
  const StatusIcon = meta.icon
  const isBusy = busy || status === "pending"

  return (
    <article className="overflow-hidden rounded-2xl border border-border">
      <div className="flex items-center justify-between bg-muted/45 px-4 py-3">
        <span className="text-xs font-bold text-secondary">{evidence.code}</span>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
            meta.badgeClass,
          )}
        >
          <StatusIcon className={cn("h-3 w-3", meta.spin && "animate-spin")} aria-hidden="true" />
          {meta.label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-px bg-border">
        <button
          type="button"
          className="relative bg-white text-left"
          onClick={() => evidence.image && onPreview(evidence.image, `${evidence.code} 原图（含未脱敏信息）`)}
          aria-label={`查看 ${evidence.code} 原图，可能包含敏感信息`}
        >
          <img src={evidence.image || ""} alt={`${evidence.code} 原图`} className="h-40 w-full object-cover" />
          <span className="absolute bottom-2 left-2 rounded-md bg-black/55 px-2 py-1 text-[10px] text-white">原图</span>
        </button>
        <button
          type="button"
          disabled={!evidence.masked_image}
          className="relative bg-white text-left disabled:cursor-not-allowed"
          onClick={() => evidence.masked_image && onPreview(evidence.masked_image, `${evidence.code} 打码后`)}
          aria-label={evidence.masked_image ? `查看 ${evidence.code} 打码后图片` : "尚未生成打码图"}
        >
          {evidence.masked_image ? (
            <img src={evidence.masked_image} alt={`${evidence.code} 打码后`} className="h-40 w-full object-cover" />
          ) : (
            <span className="flex h-40 items-center justify-center px-4 text-center text-xs text-muted-foreground">
              {status === "failed" ? "自动定位失败，请人工处理原图" : "尚未生成打码图"}
            </span>
          )}
          <span className="absolute bottom-2 left-2 rounded-md bg-black/55 px-2 py-1 text-[10px] text-white">打码后</span>
        </button>
      </div>

      {/* 下一步动作 */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        {status === "failed" && (
          <p className="mr-auto text-xs leading-5 text-red-600">自动定位失败，可重试或人工处理原图后再分享。</p>
        )}
        {status === "done" && (
          <button
            type="button"
            onClick={() => evidence.masked_image && onPreview(evidence.masked_image, `${evidence.code} 打码后`)}
            className="inline-flex min-h-[36px] items-center gap-1.5 rounded-lg border border-border bg-white px-3 text-xs font-medium hover:bg-muted"
          >
            <ZoomIn className="h-3.5 w-3.5" aria-hidden="true" />
            查看对比
          </button>
        )}
        <button
          type="button"
          onClick={() => onRemask(evidence.id)}
          disabled={isBusy}
          className={cn(
            "inline-flex min-h-[36px] items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-opacity disabled:opacity-50",
            status === "failed"
              ? "border border-red-300 bg-white text-red-700 hover:bg-red-50"
              : "bg-[#17231d] text-white hover:opacity-90",
          )}
        >
          {isBusy ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : status === "failed" ? (
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          ) : status === "done" ? (
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <Shield className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {isBusy
            ? "处理中..."
            : status === "failed"
              ? "重试"
              : status === "done"
                ? "重新打码"
                : "打码此图"}
        </button>
      </div>
    </article>
  )
}

export function ImageReviewGrid({ images, busyId, onRemask, onPreview }: ImageReviewGridProps) {
  if (images.length === 0) {
    return (
      <div className="rounded-2xl bg-muted/55 px-6 py-12 text-center" role="status">
        <Images className="mx-auto h-7 w-7 text-muted-foreground" aria-hidden="true" />
        <p className="mt-3 text-sm text-muted-foreground">当前案件暂无图片证据</p>
      </div>
    )
  }
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {images.map((evidence) => (
        <ImageReviewCard
          key={evidence.id}
          evidence={evidence}
          busy={busyId === evidence.id}
          onRemask={onRemask}
          onPreview={onPreview}
        />
      ))}
    </div>
  )
}

export default ImageReviewGrid
