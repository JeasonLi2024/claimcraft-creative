// 节点状态图标：根据状态渲染对应颜色的圆点
import type { NodeStatusValue } from "@/lib/workflow-events"

const STATUS_DOT_CLASS: Record<NodeStatusValue, string> = {
  completed: "bg-green-500",
  running: "bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)] animate-pulse",
  paused: "bg-amber-400 ring-2 ring-amber-200",
  error: "bg-red-500",
  idle: "bg-slate-600 border border-slate-500",
  skipped: "bg-slate-500",
}

export function NodeStatusIcon({ status }: { status: NodeStatusValue }) {
  return (
    <span
      className={`inline-block w-2.5 h-2.5 rounded-full ${STATUS_DOT_CLASS[status]}`}
    />
  )
}
