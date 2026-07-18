/** @deprecated 使用 BusinessStageStepper 代替。本组件保留用于渐进迁移。 */
import { useCaseStore } from "@/stores/case-store"
import { NODE_LABELS, NODE_ORDER } from "@/lib/workflow-events"
import type { NodeStatus, NodeStatusValue, WorkflowNode } from "@/lib/workflow-events"
import { NodeStatusIcon } from "./NodeStatusIcon"

const BUSINESS_LABELS: Record<string, string> = {
  preclassify: "材料初判",
  ocr: "文字识别",
  classify: "证据归类",
  extract: "字段整理",
  review: "人工确认",
  evidence_chain: "事实时间线",
  complaint: "投诉文书",
  respond_complaint: "答辩文书",
}

const GROUP_LABELS: Record<string, string> = {
  preclassify: "材料处理",
  ocr: "材料处理",
  classify: "材料处理",
  extract: "关键信息",
  review: "关键信息",
  evidence_chain: "案件组织",
  complaint: "文书输出",
  respond_complaint: "文书输出",
}

const STAGE_LABELS: Record<string, string> = {
  timeline_rebuild: "重建时间线",
  rag_retrieval: "检索法条",
  rag_done: "检索完成",
  llm_reasoning: "模型推理",
  llm_generating: "模型生成",
  skeleton_ready: "结构完成",
}

function statusText(status: NodeStatusValue) {
  if (status === "completed") return "已完成"
  if (status === "running") return "进行中"
  if (status === "paused") return "已暂停"
  if (status === "error") return "异常"
  if (status === "skipped") return "跳过"
  return "未开始"
}

function TrackCard({ node, ns, current, paused }: { node: WorkflowNode; ns?: NodeStatus; current: boolean; paused: boolean }) {
  const status = ns?.status || "idle"
  const stageLabel = ns?.progressStage ? STAGE_LABELS[ns.progressStage] || ns.progressStage : ""

  return (
    <li className={`rounded-xl border px-3 py-3 transition-colors ${paused ? "border-amber-300 bg-amber-50/10" : "border-slate-700 bg-slate-800/70"} ${current ? "ring-1 ring-sky-400/40" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="rounded-full bg-slate-700/80 px-2 py-1 text-[10px] text-slate-300">{GROUP_LABELS[node]}</span>
        <NodeStatusIcon status={status} />
      </div>
      <div className="mt-2 text-sm font-semibold text-white">{BUSINESS_LABELS[node] || NODE_LABELS[node]}</div>
      <div className="mt-1 text-[11px] text-slate-400">{NODE_LABELS[node]} · {statusText(status)}</div>
      {paused && <div className="mt-2 text-[11px] font-medium text-amber-300">当前暂停点</div>}
      {current && status === "running" && ns?.progressMessage && (
        <div className="mt-2 text-[11px] leading-5 text-sky-300">
          {stageLabel ? `${stageLabel} · ` : ""}
          {ns.progressMessage}
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
  const workflowStatus = useCaseStore((s) => s.workflowStatus)
  const pauseData = useCaseStore((s) => s.pauseData)

  const connectionLabel =
    workflowStatus === "paused"
      ? "已暂停"
      : workflowStatus === "pausing"
        ? "等待本阶段结束"
        : connectionState === "connected"
          ? "已连接"
          : connectionState === "connecting"
            ? "连接中"
            : connectionState === "reconnecting"
              ? `重连中(${reconnectAttempt}/5)`
              : connectionState === "error"
                ? "连接异常"
                : "未连接"

  return (
    <aside className="rounded-2xl bg-slate-900 px-4 py-4 text-slate-100 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold text-slate-400">业务阶段 · {connectionLabel}</div>
        {pauseData?.paused_after && <div className="text-[11px] text-amber-300">暂停于：{BUSINESS_LABELS[pauseData.paused_after] || NODE_LABELS[pauseData.paused_after]}</div>}
      </div>
      <ol className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
        {NODE_ORDER.map((node) => (
          <TrackCard
            key={node}
            node={node}
            ns={nodeStates[node]}
            current={currentNode === node}
            paused={pauseData?.paused_after === node}
          />
        ))}
      </ol>
    </aside>
  )
}
