import { useState, useEffect } from "react"
import { useParams, useNavigate, Link } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useStatus, MAIN_FLOW, TRANSITIONS } from "@/composables/useStatus"
import StatusTag from "@/components/StatusTag"
import PillTag from "@/components/PillTag"
import { cn } from "@/lib/utils"
import {
  FileText, Image, Clock, MessageSquare, Shield, Download,
  ChevronDown, ChevronRight, ArrowRight, Loader2, Briefcase,
} from "lucide-react"

const STAT_ITEMS = [
  { key: "evidence_count", label: "证据数量", icon: FileText },
  { key: "timeline_count", label: "关键节点", icon: Clock },
  { key: "template_count", label: "投诉版本", icon: MessageSquare },
  { key: null, label: "当前状态", icon: Briefcase, isStatus: true },
  { key: "image_evidence_count", label: "图片证据", icon: Image },
  { key: "extracted_field_count", label: "抽取字段", icon: Shield },
] as const

export default function WorkspacePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchStatusLogs = useCaseStore((s) => s.fetchStatusLogs)
  const transitionCaseStatus = useCaseStore((s) => s.transitionCaseStatus)
  const currentCase = useCaseStore((s) => s.currentCase)
  const statusLogs = useCaseStore((s) => s.statusLogs)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)
  const { statusLabel } = useStatus()

  const [showHistory, setShowHistory] = useState(false)
  const [showTransition, setShowTransition] = useState(false)
  const [targetStatus, setTargetStatus] = useState("")
  const [remark, setRemark] = useState("")
  const [transitioning, setTransitioning] = useState(false)

  useEffect(() => {
    if (caseId) {
      fetchCaseDetail(Number(caseId))
      fetchStatusLogs(Number(caseId))
    }
  }, [caseId])

  const caseData = currentCase
  if (loading && !caseData) return <div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>
  if (!caseData) return <p className="text-muted-foreground">加载案件中...</p>

  const currentStatusIdx = MAIN_FLOW.indexOf(caseData.status as any)
  const availableTransitions = TRANSITIONS[caseData.status] || []

  async function handleTransition(e: React.FormEvent) {
    e.preventDefault()
    if (!targetStatus || !caseId) return
    setTransitioning(true)
    try {
      await transitionCaseStatus(Number(caseId), { to_status: targetStatus, remark: remark.trim() || undefined })
      setShowTransition(false)
      setTargetStatus("")
      setRemark("")
      await fetchStatusLogs(Number(caseId))
    } catch {}
    finally { setTransitioning(false) }
  }

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link to="/cases" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary">
        &larr; 返回案件列表
      </Link>

      {/* Status progress bar */}
      <div className="flex items-center gap-2 rounded-2xl border border-border/50 bg-card p-4 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
        <StatusTag status={caseData.status} />
        <span className="text-sm text-muted-foreground">{"当前状态"}</span>
        <div className="ml-2 flex flex-1 items-center gap-1">
          {MAIN_FLOW.map((s, i) => {
            const done = currentStatusIdx >= i
            const current = currentStatusIdx === i
            return (
              <div key={s} className="flex items-center gap-1">
                <div className={cn(
                  "h-3 w-3 rounded-full border-2 transition-all",
                  done ? "border-transparent bg-primary" : "border-border bg-card",
                  current && "ring-4 ring-primary/20 animate-pulse"
                )} title={statusLabel(s)} />
                {i < MAIN_FLOW.length - 1 && (
                  <div className={cn("h-0.5 w-8", done ? "bg-secondary" : "bg-border")} />
                )}
              </div>
            )
          })}
        </div>
        {availableTransitions.length > 0 && (
          <button
            onClick={() => setShowTransition(true)}
            className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90"
          >
            {"推进状态"}
          </button>
        )}
      </div>

      {/* Title + Description */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">{caseData.title}</h1>
        {caseData.description && <p className="mt-2 text-muted-foreground">{caseData.description}</p>}
        <div className="mt-2 flex flex-wrap gap-2">
          <PillTag label={caseData.case_type || "未知类型"} variant="primary" />
        </div>
      </div>

      {/* 6 stat cards */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {STAT_ITEMS.map((item, i) => {
          const value = "isStatus" in item && item.isStatus
            ? statusLabel(caseData.status)
            : item.key
              ? (caseData as any)[item.key] ?? 0
              : 0
          return (
            <div key={i} className="rounded-2xl border border-border/50 bg-card p-4 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">{item.label}</span>
                <item.icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="mt-1 text-2xl font-bold text-foreground">{value}</div>
            </div>
          )
        })}
      </div>

      {/* Status history */}
      <div className="rounded-2xl border border-border/50 bg-card shadow-[0_10px_30px_rgba(20,35,90,.04)]">
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="flex w-full items-center justify-between p-4 text-sm font-semibold text-foreground"
        >
          {"状态变更历史"} ({statusLogs.length})
          {showHistory ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        {showHistory && (
          <div className="border-t border-border/50 p-4">
            {statusLogs.length === 0 ? (
              <p className="text-sm text-muted-foreground">{"暂无状态变更记录"}</p>
            ) : (
              <div className="relative space-y-4 pl-6">
                {/* Gradient line */}
                <div className="absolute bottom-4 left-[11px] top-0 w-0.5 bg-secondary" />
                {[...statusLogs].reverse().map((log) => (
                  <div key={log.id} className="relative flex items-start gap-3">
                    <div className="absolute -left-6 top-0.5 h-3 w-3 rounded-full border-2 border-white bg-secondary shadow-sm" />
                    <div className="flex-1 rounded-xl bg-muted/50 p-3">
                      <div className="flex items-center gap-2 text-sm">
                        <StatusTag status={log.from_status} />
                        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                        <StatusTag status={log.to_status} />
                        {log.timestamp && (
                          <span className="ml-auto text-xs text-muted-foreground">{log.timestamp}</span>
                        )}
                      </div>
                      {log.remark && <p className="mt-1 text-sm text-muted-foreground">{log.remark}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Transition Modal */}
      {showTransition && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowTransition(false)}>
          <div className="w-full max-w-md rounded-2xl border border-border/50 bg-white p-6 shadow-[0_30px_80px_rgba(15,22,40,.35)]" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-foreground">{"推进状态"}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {"当前："}<StatusTag status={caseData.status} />
            </p>
            <form onSubmit={handleTransition} className="mt-4 space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-foreground">{"目标状态"}</label>
                <select
                  value={targetStatus}
                  onChange={(e) => setTargetStatus(e.target.value)}
                  className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
                >
                  <option value="">{"请选择"}</option>
                  {availableTransitions.map((s) => (
                    <option key={s} value={s}>{statusLabel(s)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-foreground">{"备注（可选）"}</label>
                <textarea
                  value={remark}
                  onChange={(e) => setRemark(e.target.value)}
                  rows={3}
                  placeholder="填写状态变更原因..."
                  className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowTransition(false)} className="rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground hover:bg-accent">
                  {"取消"}
                </button>
                <button type="submit" disabled={transitioning || !targetStatus} className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50">
                  {transitioning ? "处理中..." : "确认推进"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Error */}
      {error && <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
    </div>
  )
}
