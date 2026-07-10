// 左侧步进轨道：8 节点垂直列表 + 连接状态指示 + 里程碑进度
// 参考 spec 第 6.6 节
import { useCaseStore } from "@/stores/case-store"
import { NODE_ORDER, NODE_LABELS } from "@/lib/workflow-events"
import type { NodeStatusValue, NodeStatus } from "@/lib/workflow-events"

const STAGE_LABELS: Record<string, string> = {
  timeline_rebuild: "重建时间线",
  rag_retrieval: "检索法条",
  rag_done: "检索完成",
  llm_reasoning: "LLM 推理",
  llm_generating: "LLM 生成中",
  skeleton_ready: "骨架已生成",
}

function NodeTrackItem({
  label,
  status,
  isCurrent,
  progressMessage,
  progressStage,
}: {
  label: string
  status: NodeStatusValue
  isCurrent: boolean
  progressMessage?: string
  progressStage?: string
}) {
  const dotClass: Record<NodeStatusValue, string> = {
    completed: "bg-green-500",
    running: "bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)] animate-pulse",
    error: "bg-red-500",
    idle: "bg-slate-700 border border-slate-600",
    skipped: "bg-slate-600",
  }

  const stageLabel = progressStage ? STAGE_LABELS[progressStage] || progressStage : ""

  return (
    <li className="relative pl-5 pb-3 last:pb-0">
      <span
        className={`absolute left-0 top-0.5 w-3 h-3 rounded-full ${dotClass[status]}`}
      />
      <div
        className={`text-xs ${
          isCurrent ? "font-semibold text-white" : "text-slate-300"
        }`}
      >
        {label}
      </div>
      {isCurrent && status === "running" && progressMessage && (
        <div className="text-[10px] text-blue-400 mt-0.5 leading-tight">
          {stageLabel && <span className="text-blue-300">{stageLabel}：</span>}
          {progressMessage}
        </div>
      )}
    </li>
  )
}

export function NodeTrack() {
  const nodeStates = useCaseStore((s) => s.nodeStates)
  const currentNode = useCaseStore((s) => s.currentNode)
  const connectionState = useCaseStore((s) => s.connectionState)
  const reconnectAttempt = useCaseStore((s) => s.reconnectAttempt)

  const connectionLabel =
    connectionState === "connected"
      ? "已连接"
      : connectionState === "connecting"
        ? "连接中"
        : connectionState === "reconnecting"
          ? `重连中(${reconnectAttempt}/5)`
          : connectionState === "error"
            ? "连接失败"
            : "未连接"

  return (
    <aside className="w-32 flex-shrink-0 bg-slate-900 text-slate-100 p-3 rounded-lg">
      <div className="text-xs font-semibold mb-3 text-slate-400">
        节点轨道 · {connectionLabel}
      </div>
      <ol className="relative">
        <div className="absolute left-1.5 top-2 bottom-2 w-0.5 bg-slate-700" />
        {NODE_ORDER.map((node) => {
          const ns: NodeStatus | undefined = nodeStates[node]
          return (
            <NodeTrackItem
              key={node}
              label={NODE_LABELS[node]}
              status={ns?.status || "idle"}
              isCurrent={currentNode === node}
              progressMessage={ns?.progressMessage}
              progressStage={ns?.progressStage}
            />
          )
        })}
      </ol>
    </aside>
  )
}
