// 左侧步进轨道：7 节点垂直列表 + 连接状态指示
// 参考 spec 第 6.6 节
import { useCaseStore } from "@/stores/case-store"
import { NODE_ORDER, NODE_LABELS } from "@/lib/workflow-events"
import type { NodeStatusValue } from "@/lib/workflow-events"

function NodeTrackItem({
  label,
  status,
  isCurrent,
}: {
  label: string
  status: NodeStatusValue
  isCurrent: boolean
}) {
  const dotClass: Record<NodeStatusValue, string> = {
    completed: "bg-green-500",
    running: "bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)] animate-pulse",
    error: "bg-red-500",
    idle: "bg-slate-700 border border-slate-600",
    skipped: "bg-slate-600",
  }

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
    <aside className="w-28 flex-shrink-0 bg-slate-900 text-slate-100 p-3 rounded-lg">
      <div className="text-xs font-semibold mb-3 text-slate-400">
        节点轨道 · {connectionLabel}
      </div>
      <ol className="relative">
        <div className="absolute left-1.5 top-2 bottom-2 w-0.5 bg-slate-700" />
        {NODE_ORDER.map((node) => (
          <NodeTrackItem
            key={node}
            label={NODE_LABELS[node]}
            status={nodeStates[node]?.status || "idle"}
            isCurrent={currentNode === node}
          />
        ))}
      </ol>
    </aside>
  )
}
