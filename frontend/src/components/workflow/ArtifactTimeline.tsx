// 工作流产物时间线：按时间顺序（旧→新）渲染 ArtifactCard
// 对齐 spec.md Task 3.6.3 + Task 3.6.5（全局 stale 提示条）
// 数据源：workflow-run-store.artifacts
import { useMemo } from "react"
import { AlertTriangle, Inbox } from "lucide-react"
import type { WorkflowArtifact } from "@/types/workflow"
import { useWorkflowRunStore } from "@/stores/workflow-run-store"
import { ArtifactCard } from "./ArtifactCard"

// ---------- 时间解析辅助 ----------

function toTimestamp(ts: string | null | undefined): number {
  if (!ts) return 0
  try {
    const t = new Date(ts).getTime()
    return Number.isNaN(t) ? 0 : t
  } catch {
    return 0
  }
}

// ---------- 主组件 ----------

export interface ArtifactTimelineProps {
  /** 覆盖 artifacts（默认从 workflow-run-store 读取） */
  artifacts?: WorkflowArtifact[]
  /** 点击「查看详情」时触发 */
  onViewDetails?: (artifact: WorkflowArtifact) => void
  /** 点击「标记为过期」时触发（仅 active 状态可操作） */
  onMarkStale?: (artifactId: number) => void
  /** 默认展开某张卡（如最近一张） */
  defaultExpandedIndex?: number
}

export function ArtifactTimeline({
  artifacts: artifactsProp,
  onViewDetails,
  onMarkStale,
  defaultExpandedIndex,
}: ArtifactTimelineProps) {
  const storeArtifacts = useWorkflowRunStore((s) => s.artifacts)
  const artifacts = artifactsProp ?? storeArtifacts

  // 按时间排序（旧→新），同时间按 id 升序
  const ordered = useMemo(() => {
    return [...artifacts].sort((a, b) => {
      const ta = toTimestamp(a.created_at)
      const tb = toTimestamp(b.created_at)
      if (ta !== tb) return ta - tb
      return a.id - b.id
    })
  }, [artifacts])

  const staleCount = useMemo(
    () => artifacts.filter((a) => a.status === "stale").length,
    [artifacts],
  )

  // ---------- 空状态 ----------

  if (artifacts.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-[#EAEAEA] bg-white px-4 py-10 text-center"
        aria-live="polite"
      >
        <Inbox className="h-6 w-6 text-[#787774]" aria-hidden="true" />
        <p className="text-sm text-[#565652]">暂无产物</p>
        <p className="text-[11px] text-[#787774]">
          工作流节点完成后会在此显示产物卡片
        </p>
      </div>
    )
  }

  return (
    <section aria-label="产物时间线" className="flex flex-col gap-3">
      {/* Task 3.6.5：全局 stale 警告条 */}
      {staleCount > 0 && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
          <div className="flex-1">
            <p className="font-medium">
              当前有 {staleCount} 个产物已过期
            </p>
            <p className="mt-0.5 text-[11px] text-amber-700">
              上游节点已变更，建议重新生成以避免使用过期结果
            </p>
          </div>
        </div>
      )}

      {/* 产物时间线 */}
      <ol className="flex flex-col gap-3">
        {ordered.map((artifact, idx) => (
          <li key={artifact.id} className="relative">
            {/* 时间线连接线（除最后一项外） */}
            {idx < ordered.length - 1 && (
              <span
                aria-hidden="true"
                className="absolute left-5 top-12 bottom-[-12px] w-px bg-[#EAEAEA]"
              />
            )}
            <div className="relative">
              <ArtifactCard
                artifact={artifact}
                onViewDetails={onViewDetails}
                onMarkStale={onMarkStale}
                defaultExpanded={defaultExpandedIndex === idx}
              />
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

export default ArtifactTimeline
