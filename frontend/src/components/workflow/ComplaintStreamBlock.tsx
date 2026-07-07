// 投诉书 token 流式区块：蓝色主题 + useRef 直接操作 DOM 追加 token
// 参考 spec 第 6.9 节
import { useState, useEffect, useRef } from "react"
import { Link } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { TONE_LABELS } from "@/lib/workflow-events"
import type { ProductBlock } from "@/lib/workflow-events"

interface ComplaintDraft {
  title: string
  content: string
  tone: string
}

export function ComplaintStreamBlock({
  block,
  draft,
  caseId,
}: {
  block: ProductBlock
  draft: ComplaintDraft | null
  caseId: number
}) {
  const [collapsed, setCollapsed] = useState(false)
  const isRunning = useCaseStore((s) => s.isRunning)
  const currentNode = useCaseStore((s) => s.currentNode)
  const isStreaming = isRunning && currentNode === "complaint"

  const contentRef = useRef<HTMLDivElement>(null)
  const renderedLengthRef = useRef(0)

  // 性能优化：增量追加 token，避免每 token re-render
  useEffect(() => {
    if (draft?.content && contentRef.current) {
      const full = draft.content
      if (full.length > renderedLengthRef.current) {
        const newPart = full.slice(renderedLengthRef.current)
        if (newPart) {
          contentRef.current.appendChild(document.createTextNode(newPart))
          renderedLengthRef.current = full.length
        }
      } else if (full.length < renderedLengthRef.current) {
        // 内容被重置（如重新启动），清空重渲染
        contentRef.current.textContent = full
        renderedLengthRef.current = full.length
      }
    }
  }, [draft?.content])

  // 当 draft 被清空时重置
  useEffect(() => {
    if (!draft?.content && contentRef.current) {
      contentRef.current.textContent = ""
      renderedLengthRef.current = 0
    }
  }, [draft])

  const toneLabel = draft?.tone ? TONE_LABELS[draft.tone] || draft.tone : ""

  return (
    <div className="border-l-4 border-blue-500 rounded-r-md bg-[#E1F3FE] border border-[#EAEAEA]">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-blue-100/50 transition-colors rounded-r-md"
      >
        <span className="text-sm font-medium text-blue-900">
          {isStreaming ? "投诉书生成中..." : "投诉书完成"}
        </span>
        <div className="flex items-center gap-2">
          {isStreaming && (
            <span className="text-xs text-blue-600">
              {draft?.content.length || 0} 字
            </span>
          )}
          {!collapsed ? (
            <span className="text-xs text-blue-600">收起</span>
          ) : (
            <span className="text-xs text-blue-600">展开</span>
          )}
        </div>
      </button>

      {!collapsed && (
        <div className="px-4 pb-4">
          <div className="bg-white border border-blue-200 rounded p-4 max-h-96 overflow-y-auto">
            <h4 className="text-center font-semibold mb-2 text-[#111111]">
              {draft?.title || "投诉书"}
            </h4>
            <div
              ref={contentRef}
              className="whitespace-pre-wrap text-sm text-[#111111] leading-relaxed"
            />
            {isStreaming && (
              <span className="inline-block w-0.5 h-4 bg-blue-500 animate-pulse ml-0.5 align-middle" />
            )}
          </div>

          {!isStreaming && draft && (
            <div className="mt-3 flex items-center gap-3">
              <Link
                to={`/cases/${caseId}/complaint`}
                className="text-xs text-blue-600 hover:underline"
              >
                查看完整投诉书 →
              </Link>
              {toneLabel && (
                <span className="text-xs text-[#787774]">语气：{toneLabel}</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
