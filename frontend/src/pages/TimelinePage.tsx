import { useState, useEffect } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useFormat } from "@/composables/useFormat"
import PillTag from "@/components/PillTag"
import EmptyState from "@/components/EmptyState"
import { cn } from "@/lib/utils"
import { RefreshCw, Loader2, Clock, Zap, Edit3 } from "lucide-react"

export default function TimelinePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchTimeline = useCaseStore((s) => s.fetchTimeline)
  const updateTimelineNode = useCaseStore((s) => s.updateTimelineNode)
  const rebuildTimeline = useCaseStore((s) => s.rebuildTimeline)
  const timelineNodes = useCaseStore((s) => s.timelineNodes)
  const currentCase = useCaseStore((s) => s.currentCase)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)
  const { formatTime } = useFormat()

  const [rebuilding, setRebuilding] = useState(false)

  useEffect(() => {
    if (caseId) {
      fetchCaseDetail(Number(caseId))
      fetchTimeline(Number(caseId))
    }
  }, [caseId])

  async function handleRebuild() {
    if (!caseId) return
    setRebuilding(true)
    try { await rebuildTimeline(Number(caseId)) } catch {}
    finally { setRebuilding(false) }
  }

  async function handleNodeBlur(nodeId: number, newEvent: string) {
    if (newEvent.trim()) {
      try { await updateTimelineNode(nodeId, { event: newEvent.trim() }) } catch {}
    }
  }

  if (loading && !currentCase) return <div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">事件时间线</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            按时间顺序展示案件关键事件节点，可直接编辑
          </p>
        </div>
        <button
          onClick={handleRebuild}
          disabled={rebuilding}
          className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          <RefreshCw className={cn("h-4 w-4", rebuilding && "animate-spin")} />
          {rebuilding ? "重建中..." : "重新生成时间线"}
        </button>
      </div>

      {error && <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      {timelineNodes.length === 0 && !loading && (
        <EmptyState
          icon={<Clock className="h-8 w-8" />}
          title="暂无时间线节点"
          description="添加证据后，系统将自动生成时间线"
        />
      )}

      {/* Timeline */}
      <div className="relative space-y-0 pl-8">
        {/* Gradient vertical line */}
        {timelineNodes.length > 0 && (
          <div className="absolute bottom-0 left-[15px] top-0 w-0.5 bg-gradient-to-b from-secondary to-secondary/40" />
        )}

        {timelineNodes.map((node) => (
          <div key={node.id} className="relative pb-6">
            {/* Dot */}
            <div className="absolute -left-8 top-1 flex h-[30px] w-[30px] items-center justify-center">
              <div className="h-3 w-3 rounded-full border-2 border-white bg-secondary shadow-sm" />
            </div>

            {/* Content */}
            <div className="rounded-xl border border-border/50 bg-card p-4 shadow-[0_6px_20px_rgba(20,35,90,.03)]">
              {/* Date */}
              <div className="mb-2 flex items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">
                  {formatTime(node.datetime)}
                </span>
                {node.auto_generated ? (
                  <PillTag label="自动" variant="primary" />
                ) : (
                  <PillTag label="手动" variant="default" />
                )}
              </div>

              {/* Editable event */}
              <input
                type="text"
                defaultValue={node.event}
                onBlur={(e) => handleNodeBlur(node.id, e.target.value)}
                className="w-full rounded-lg border border-transparent bg-transparent px-2 py-1 text-sm text-foreground focus:border-primary focus:bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
              />

              {/* Related evidence */}
              {node.related_evidence_codes && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {node.related_evidence_codes.split(",").map((code) => code.trim()).filter(Boolean).map((code) => (
                    <span key={code} className="rounded-md bg-accent px-1.5 py-0.5 text-[11px] font-medium text-accent-foreground">
                      {code}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
