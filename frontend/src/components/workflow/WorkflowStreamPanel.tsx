// 顶层容器组件：未启动时显示按钮，启动后显示 NodeTrack + ProductStream
// 参考 spec 第 6.5 节
import { useEffect, useState } from "react"
import { Loader2, PauseCircle, RefreshCw } from "lucide-react"
import { useCaseStore } from "@/stores/case-store"
import { NodeTrack } from "./NodeTrack"
import { ProductStream } from "./ProductStream"

export function WorkflowStreamPanel({ caseId }: { caseId: number }) {
  const currentCase = useCaseStore((s) => s.currentCase)
  const activeWorkflowCaseId = useCaseStore((s) => s.activeWorkflowCaseId)
  const isRunning = useCaseStore((s) => s.isRunning)
  const workflowStatus = useCaseStore((s) => s.workflowStatus)
  const threadId = useCaseStore((s) => s.threadId)
  const isRestoring = useCaseStore((s) => s.isRestoringWorkflow)
  const historyAvailable = useCaseStore((s) => s.workflowHistoryAvailable)
  const connectionState = useCaseStore((s) => s.connectionState)
  const startWorkflow = useCaseStore((s) => s.startWorkflow)
  const restoreWorkflow = useCaseStore((s) => s.restoreWorkflow)
  const requestWorkflowPause = useCaseStore((s) => s.requestWorkflowPause)
  const productBlocks = useCaseStore((s) => s.productBlocks)
  const evidences = useCaseStore((s) => s.evidences)
  const reviewInterrupt = useCaseStore((s) => s.reviewInterrupt)
  const pauseData = useCaseStore((s) => s.pauseData)
  const errors = useCaseStore((s) => s.errors)
  const [starting, setStarting] = useState(false)
  const [pausing, setPausing] = useState(false)

  const caseReady = currentCase?.id === caseId
  const stateBelongsToCase = activeWorkflowCaseId === caseId
  const status = stateBelongsToCase ? workflowStatus : currentCase?.workflow_status || "idle"
  const hasWorkflow = caseReady && Boolean(stateBelongsToCase ? threadId : currentCase.thread_id) && status !== "idle"
  const hasContent = stateBelongsToCase && (historyAvailable || productBlocks.length > 0 || Boolean(reviewInterrupt) || Boolean(pauseData) || errors.length > 0)

  useEffect(() => {
    if (caseReady) void restoreWorkflow(caseId)
  }, [caseId, caseReady, currentCase?.thread_id, currentCase?.workflow_status, restoreWorkflow])

  async function handleStart() {
    setStarting(true)
    try {
      await startWorkflow(caseId, [])
    } catch {
      // 错误已写入 store
    } finally {
      setStarting(false)
    }
  }

  async function handlePause() {
    setPausing(true)
    try {
      await requestWorkflowPause(caseId)
    } catch {
    } finally {
      setPausing(false)
    }
  }

  if (!caseReady || isRestoring) {
    return <div className="flex items-center gap-2 py-3 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在恢复工作流状态...</div>
  }

  if (!hasWorkflow) {
    return (
      <div className="pt-2">
        <button
          onClick={handleStart}
          disabled={starting || isRunning}
          aria-label={isRunning ? "工作流运行中" : `启动工作流（共 ${evidences.length} 个证据待处理）`}
          className="inline-flex min-h-[44px] items-center justify-center rounded-md bg-[#111111] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#333333] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {starting ? "启动中..." : isRunning ? "运行中..." : "开始工作流分析"}
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <span className="text-sm text-[#787774]" aria-live="polite">
          工作流实时分析 · {status === "running" ? "分析中" : status === "pausing" ? "本阶段结束后暂停" : status === "paused" ? "已暂停，可编辑后继续" : status === "waiting_review" ? "等待人工审核" : status === "succeeded" ? "分析完成" : "分析失败"}
          {connectionState === "connecting" && " · 连接中"}
          {connectionState === "reconnecting" && " · 重连中"}
          {connectionState === "error" && status === "running" && " · 连接异常"}
        </span>
        {isRunning && (
          <button onClick={handlePause} disabled={pausing || status === "pausing"} aria-label="阶段结束后暂停工作流" className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-70">
            <PauseCircle className="h-3.5 w-3.5" aria-hidden="true" />
            {status === "pausing" || pausing ? "本阶段结束后暂停" : "阶段结束后暂停"}
          </button>
        )}
        {!isRunning && status !== "waiting_review" && status !== "paused" && (
          <button onClick={handleStart} disabled={starting} aria-label={`重新分析工作流（共 ${evidences.length} 个证据）`} className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50">
            <RefreshCw className={starting ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} aria-hidden="true" />
            {starting ? "重新启动中..." : "重新分析"}
          </button>
        )}
      </div>
      {!hasContent && !isRunning ? (
        <div className="rounded-xl border border-dashed border-border bg-muted/30 px-4 py-6 text-sm text-muted-foreground">
          当前案件保留了工作流状态，但详细分析事件已过期或暂不可用。
          {status === "waiting_review" && " 请稍后刷新；如仍无法恢复，请勿重复启动工作流。"}
        </div>
      ) : (
        <div className="flex min-h-[300px] flex-col gap-4 md:min-h-[500px]">
          <NodeTrack />
          <div className="h-[calc(100vh-330px)] min-h-[480px]">
            <ProductStream caseId={caseId} />
          </div>
        </div>
      )}
    </div>
  )
}
