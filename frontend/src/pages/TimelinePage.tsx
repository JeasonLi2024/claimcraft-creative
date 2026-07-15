import { useState, useEffect } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useFormat } from "@/composables/useFormat"
import { useStatus } from "@/composables/useStatus"
import PillTag from "@/components/PillTag"
import { cn } from "@/lib/utils"
import { RefreshCw, Loader2, Clock3, Edit3, Sparkles, Link2, Route } from "lucide-react"

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
  const { disputeLabel } = useStatus()
  const [rebuilding, setRebuilding] = useState(false)

  useEffect(() => {
    if (caseId) {
      fetchCaseDetail(Number(caseId))
      fetchTimeline(Number(caseId))
    }
  }, [caseId, fetchCaseDetail, fetchTimeline])

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

  if (loading && !currentCase) return <div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-secondary" /></div>

  const autoCount = timelineNodes.filter((node) => node.auto_generated).length
  const linkedCount = timelineNodes.filter((node) => Boolean(node.related_evidence_codes)).length

  return (
    <div className="space-y-5 pb-8">
      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
        <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70"><Sparkles className="h-3.5 w-3.5 text-[#d8b967]" />事实脉络整理</div>
            <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">事件时间线</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">将证据中的订单、付款、沟通和履约事件按时间排序。核对事实描述后，可直接编辑需要修正的节点。</p>
            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{currentCase?.title || "当前案件"}</span>
              {currentCase?.case_type && <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{disputeLabel(currentCase.case_type)}</span>}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 self-end">
            {[{ label: "事实节点", value: timelineNodes.length, icon: Route }, { label: "自动生成", value: autoCount, icon: Sparkles }, { label: "关联证据", value: linkedCount, icon: Link2 }].map((item) => (
              <div key={item.label} className="rounded-2xl border border-white/10 bg-white/8 p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between text-white/45"><span className="text-xs">{item.label}</span><item.icon className="h-4 w-4" /></div>
                <div className="mt-2 text-2xl font-semibold">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {error && <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_310px]">
        <div className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">事实清单</p><h2 className="mt-1 text-xl font-semibold tracking-tight">按发生顺序核对关键事件</h2><p className="mt-1 text-sm text-muted-foreground">点击事件内容即可修改，离开输入框后自动保存。</p></div>
            <button onClick={handleRebuild} disabled={rebuilding} className="inline-flex items-center gap-2 rounded-xl bg-[#17231d] px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50">
              <RefreshCw className={cn("h-4 w-4", rebuilding && "animate-spin")} />{rebuilding ? "重建中..." : "重新生成时间线"}
            </button>
          </div>

          {loading && timelineNodes.length === 0 ? (
            <div className="flex h-48 items-center justify-center"><Loader2 className="h-7 w-7 animate-spin text-secondary" /></div>
          ) : timelineNodes.length === 0 ? (
            <div className="mt-6 rounded-2xl bg-muted/55 px-6 py-12 text-center"><Clock3 className="mx-auto h-7 w-7 text-muted-foreground" /><h3 className="mt-3 font-semibold">暂无时间线节点</h3><p className="mt-1 text-sm text-muted-foreground">上传并识别证据后，系统会在这里整理案件事实。</p></div>
          ) : (
            <div className="relative mt-7 pl-9">
              <div className="absolute bottom-3 left-[14px] top-3 w-px bg-gradient-to-b from-secondary via-secondary/60 to-border" />
              {timelineNodes.map((node, index) => (
                <article key={node.id} className="relative pb-5 last:pb-0">
                  <div className="absolute -left-9 top-5 flex h-7 w-7 items-center justify-center rounded-full border-4 border-card bg-secondary text-[10px] font-semibold text-white shadow-sm">{index + 1}</div>
                  <div className="rounded-2xl border border-border bg-white p-4 transition-all hover:border-secondary/25 hover:shadow-md sm:p-5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-xs font-medium text-secondary">{formatTime(node.datetime)}</span>
                      <PillTag label={node.auto_generated ? "系统整理" : "手动添加"} variant={node.auto_generated ? "primary" : "default"} />
                    </div>
                    <div className="mt-3 flex items-start gap-2 rounded-xl bg-muted/45 p-3"><Edit3 className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" /><input type="text" defaultValue={node.event} onBlur={(e) => handleNodeBlur(node.id, e.target.value)} className="w-full border-0 bg-transparent text-sm leading-6 text-foreground outline-none" /></div>
                    {node.related_evidence_codes && <div className="mt-3 flex flex-wrap items-center gap-1.5"><span className="mr-1 text-xs text-muted-foreground">关联材料</span>{node.related_evidence_codes.split(",").map((code) => code.trim()).filter(Boolean).map((code) => <span key={code} className="rounded-lg bg-accent px-2 py-1 text-[11px] font-semibold text-secondary">{code}</span>)}</div>}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>

        <aside className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_32px_rgba(31,45,38,.05)]">
          <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-secondary"><Clock3 className="h-5 w-5" /></span><div><h2 className="text-sm font-semibold">核对建议</h2><p className="text-xs text-muted-foreground">确保事实链条完整</p></div></div>
          <div className="mt-5 space-y-4">{["确认关键日期与原始凭证一致", "检查付款、发货与沟通先后顺序", "修正含义模糊或缺少主体的描述"].map((text, index) => <div key={text} className="flex items-start gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-secondary">{index + 1}</span><p className="pt-0.5 text-sm leading-5 text-muted-foreground">{text}</p></div>)}</div>
        </aside>
      </section>
    </div>
  )
}
