import { useEffect } from "react"
import { useCaseStore } from "@/stores/case-store"
import { useScrollFollow } from "@/hooks/useScrollFollow"
import { NODE_LABELS } from "@/lib/workflow-events"
import type { WorkflowNode } from "@/lib/workflow-events"
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

  // 自动滚动跟随：用户向上滚动后停止跟随，回到底部时恢复
  const { containerRef, isFollowing, onScroll, scrollToBottom } = useScrollFollow()

  const contentLength = complaintDraft?.content.length || 0
  useEffect(() => {
    // 仅在跟随状态下滚动到底部，避免抢夺用户滚动位置
    if (isFollowing) {
      scrollToBottom()
    }
  }, [productBlocks.length, contentLength, reviewInterrupt, pauseData, errors.length, isFollowing, scrollToBottom])

  return (
    <div className="relative h-full">
      <div
        ref={containerRef}
        onScroll={onScroll}
        className="h-full space-y-3 overflow-y-auto pr-2"
      >
        {errors.length > 0 && (
          <div
            role="alert"
            className="rounded-md border border-[#FDEBEC] bg-[#FDEBEC] px-3 py-2 text-sm text-red-700"
          >
            {errors.map((err, i) => (
              <div key={i}>
                {err.node ? `[${NODE_LABELS[err.node as WorkflowNode] || err.node}] ` : ""}
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
          <div
            aria-live="polite"
            className="py-2 text-center text-sm text-[#787774]"
          >
            <span className="mr-1 inline-block animate-pulse" aria-hidden="true">●</span>
            {currentNode ? `${NODE_LABELS[currentNode as WorkflowNode] || currentNode} 运行中...` : "处理中..."}
          </div>
        )}
      </div>

      {!isFollowing && (
        <button
          type="button"
          onClick={scrollToBottom}
          aria-label="回到最新内容"
          className="absolute bottom-4 right-4 z-10 inline-flex min-h-[44px] items-center gap-1.5 rounded-full bg-blue-500/80 px-4 text-sm font-medium text-white shadow-lg backdrop-blur transition hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
        >
          <span aria-hidden="true">↓</span>
          回到最新内容
        </button>
      )}
    </div>
  )
}
