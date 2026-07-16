import { useEffect, useRef, useState } from "react"
import { Link } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { cn } from "@/lib/utils"
import { TONE_LABELS } from "@/lib/workflow-events"
import type { ProductBlock } from "@/lib/workflow-events"

function MarkdownPreview({ content }: { content: string }) {
  return (
    <div className="space-y-2 text-sm leading-7 text-[#111111]">
      {content.split(/\n{2,}/).map((block, index) =>
        block.startsWith("## ") ? (
          <h5 key={index} className="border-b border-blue-100 pb-1 pt-2 font-semibold">
            {block.slice(3)}
          </h5>
        ) : (
          <p key={index} className="whitespace-pre-wrap">
            {block}
          </p>
        ),
      )}
    </div>
  )
}

interface DraftData {
  title: string
  content: string
  tone: string
  node?: "complaint" | "respond_complaint"
  templateType?: string
}

export function ComplaintStreamBlock({
  block,
  draft,
  caseId,
}: {
  block: ProductBlock
  draft: DraftData | null
  caseId: number
}) {
  const [collapsed, setCollapsed] = useState(false)
  const isRunning = useCaseStore((s) => s.isRunning)
  const currentNode = useCaseStore((s) => s.currentNode)
  const isStreaming = isRunning && currentNode === block.type
  const title = block.type === "respond_complaint" ? "反证答辩书" : "投诉书"
  const targetPath = block.type === "respond_complaint" ? `/cases/${caseId}/respond` : `/cases/${caseId}/complaint`

  const contentRef = useRef<HTMLDivElement>(null)
  const renderedLengthRef = useRef(0)

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
        contentRef.current.textContent = full
        renderedLengthRef.current = full.length
      }
    }
  }, [draft?.content])

  useEffect(() => {
    if (!draft?.content && contentRef.current) {
      contentRef.current.textContent = ""
      renderedLengthRef.current = 0
    }
  }, [draft])

  const toneLabel = draft?.tone ? TONE_LABELS[draft.tone] || draft.tone : ""

  return (
    <div className="rounded-r-md border border-[#EAEAEA] border-l-4 border-l-blue-500 bg-[#E1F3FE]">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full items-center justify-between rounded-r-md px-3 py-2 text-left transition-colors hover:bg-blue-100/50"
      >
        <span className="text-sm font-medium text-blue-900">
          {isStreaming ? `${title}生成中...` : `${title}完成`}
        </span>
        <div className="flex items-center gap-2">
          {isStreaming && <span className="text-xs text-blue-600">{draft?.content.length || 0} 字</span>}
          <span className="text-xs text-blue-600">{collapsed ? "展开" : "收起"}</span>
        </div>
      </button>

      {!collapsed && (
        <div className="px-4 pb-4">
          <div className="max-h-96 overflow-y-auto rounded border border-blue-200 bg-white p-4">
            <h4 className="mb-2 text-center font-semibold text-[#111111]">
              {draft?.title || title}
            </h4>
            <div ref={contentRef} className={cn("hidden", isStreaming && "block whitespace-pre-wrap text-sm leading-relaxed text-[#111111]")} />
            {!isStreaming && draft?.content && <MarkdownPreview content={draft.content} />}
            {isStreaming && <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-blue-500 align-middle" />}
          </div>

          {!isStreaming && draft && (
            <div className="mt-3 flex items-center gap-3">
              <Link to={targetPath} className="text-xs text-blue-600 hover:underline">
                查看完整文书 →
              </Link>
              {toneLabel && <span className="text-xs text-[#787774]">语气：{toneLabel}</span>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
