// 顶层容器组件：未启动时显示按钮，启动后显示 NodeTrack + ProductStream
// 参考 spec 第 6.5 节
import { useState } from "react"
import { useCaseStore } from "@/stores/case-store"
import { NodeTrack } from "./NodeTrack"
import { ProductStream } from "./ProductStream"

export function WorkflowStreamPanel({ caseId }: { caseId: number }) {
  const isRunning = useCaseStore((s) => s.isRunning)
  const connectionState = useCaseStore((s) => s.connectionState)
  const startWorkflow = useCaseStore((s) => s.startWorkflow)
  const productBlocks = useCaseStore((s) => s.productBlocks)
  const [showPanel, setShowPanel] = useState(false)
  const [starting, setStarting] = useState(false)

  const hasContent = isRunning || productBlocks.length > 0
  const shouldShowPanel = showPanel || hasContent

  async function handleStart() {
    setShowPanel(true)
    setStarting(true)
    try {
      await startWorkflow(caseId, [])
    } catch {
      // 错误已写入 store
    } finally {
      setStarting(false)
    }
  }

  if (!shouldShowPanel) {
    return (
      <div className="pt-2">
        <button
          onClick={handleStart}
          disabled={starting}
          className="px-4 py-2 bg-[#111111] text-white rounded-md text-sm font-medium hover:bg-[#333333] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {starting ? "启动中..." : "开始工作流分析"}
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {/* 连接状态指示器 */}
      <div className="flex items-center justify-between px-1">
        <span className="text-xs text-[#787774]">
          工作流实时分析
          {connectionState === "connecting" && " · 连接中"}
          {connectionState === "reconnecting" && " · 重连中"}
          {connectionState === "error" && " · 连接异常"}
        </span>
      </div>
      <div className="flex gap-4 h-[calc(100vh-200px)] min-h-[600px]">
        <NodeTrack />
        <ProductStream caseId={caseId} />
      </div>
    </div>
  )
}
