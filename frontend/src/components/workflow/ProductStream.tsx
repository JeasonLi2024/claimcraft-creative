// 主区产物流容器：遍历产物区块 + 审核中断面板 + 加载指示 + 自动滚动
// 参考 spec 第 6.7 节
import { useEffect, useRef } from "react"
import { useCaseStore } from "@/stores/case-store"
import { NODE_LABELS } from "@/lib/workflow-events"
import { ProductBlock } from "./ProductBlock"
import { ComplaintStreamBlock } from "./ComplaintStreamBlock"
import { ReviewInterruptPanel } from "./ReviewInterruptPanel"

export function ProductStream({ caseId }: { caseId: number }) {
  const productBlocks = useCaseStore((s) => s.productBlocks)
  const complaintDraft = useCaseStore((s) => s.complaintDraft)
  const reviewInterrupt = useCaseStore((s) => s.reviewInterrupt)
  const isRunning = useCaseStore((s) => s.isRunning)
  const currentNode = useCaseStore((s) => s.currentNode)
  const errors = useCaseStore((s) => s.errors)
  const bottomRef = useRef<HTMLDivElement>(null)

  const contentLength = complaintDraft?.content.length || 0
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [productBlocks.length, contentLength, reviewInterrupt, errors.length])

  return (
    <div className="flex-1 overflow-y-auto pr-2 space-y-2">
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
        block.type === "complaint" ? (
          <ComplaintStreamBlock
            key={block.id}
            block={block}
            draft={complaintDraft}
            caseId={caseId}
          />
        ) : (
          <ProductBlock key={block.id} block={block} />
        ),
      )}

      {reviewInterrupt && (
        <ReviewInterruptPanel data={reviewInterrupt} caseId={caseId} />
      )}

      {isRunning && !reviewInterrupt && (
        <div className="text-center py-2 text-sm text-[#787774]">
          <span className="inline-block animate-pulse mr-1">●</span>
          {currentNode ? `${NODE_LABELS[currentNode] || currentNode} 运行中...` : "处理中..."}
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
