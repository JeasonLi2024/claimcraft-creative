import { useEffect, useRef } from "react"
import { useCaseStore } from "@/stores/case-store"
import { NODE_LABELS } from "@/lib/workflow-events"
import { ProductBlock } from "./ProductBlock"
import { ComplaintStreamBlock } from "./ComplaintStreamBlock"
import { ReviewInterruptPanel } from "./ReviewInterruptPanel"
import { StagePausePanel } from "./StagePausePanel"

export function ProductStream({ caseId }: { caseId: number }) {
  const productBlocks = useCaseStore((s) => s.productBlocks)
  const complaintDraft = useCaseStore((s) => s.complaintDraft)
  const reviewInterrupt = useCaseStore((s) => s.reviewInterrupt)
  const pauseData = useCaseStore((s) => s.pauseData)
  const isRunning = useCaseStore((s) => s.isRunning)
  const currentNode = useCaseStore((s) => s.currentNode)
  const errors = useCaseStore((s) => s.errors)
  const bottomRef = useRef<HTMLDivElement>(null)

  const contentLength = complaintDraft?.content.length || 0
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [productBlocks.length, contentLength, reviewInterrupt, pauseData, errors.length])

  return (
    <div className="h-full space-y-3 overflow-y-auto pr-2">
      {errors.length > 0 && (
        <div className="rounded-md border border-[#FDEBEC] bg-[#FDEBEC] px-3 py-2 text-sm text-red-700">
          {errors.map((err, i) => (
            <div key={i}>
              {err.node ? `[${NODE_LABELS[err.node] || err.node}] ` : ""}
              {err.message}
            </div>
          ))}
        </div>
      )}

      {productBlocks.map((block) =>
        block.type === "complaint" || block.type === "respond_complaint" ? (
          <ComplaintStreamBlock key={block.id} block={block} draft={complaintDraft} caseId={caseId} />
        ) : (
          <ProductBlock key={block.id} block={block} />
        ),
      )}

      {reviewInterrupt && <ReviewInterruptPanel data={reviewInterrupt} caseId={caseId} />}
      {pauseData && <StagePausePanel caseId={caseId} />}

      {isRunning && !reviewInterrupt && !pauseData && (
        <div className="py-2 text-center text-sm text-[#787774]">
          <span className="mr-1 inline-block animate-pulse">●</span>
          {currentNode ? `${NODE_LABELS[currentNode] || currentNode} 运行中...` : "处理中..."}
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
