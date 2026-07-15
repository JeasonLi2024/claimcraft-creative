import { useEffect, useState } from "react"
import { Link, useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { MAIN_FLOW, useStatus } from "@/composables/useStatus"
import StatusTag from "@/components/StatusTag"
import { cn } from "@/lib/utils"
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clock3,
  FileCheck2,
  FileText,
  Gavel,
  History,
  Image,
  Layers3,
  Loader2,
  MessageSquareText,
  ScanText,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react"

const FLOW_LABELS: Record<string, string> = {
  draft: "材料准备",
  processing: "系统处理中",
  submitted: "文稿已生成",
  closed: "案件已归档",
}

export default function WorkspacePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchStatusLogs = useCaseStore((s) => s.fetchStatusLogs)
  const currentCase = useCaseStore((s) => s.currentCase)
  const statusLogs = useCaseStore((s) => s.statusLogs)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)
  const { statusLabel, disputeLabel } = useStatus()
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    if (!caseId) return
    fetchCaseDetail(Number(caseId))
    fetchStatusLogs(Number(caseId))
  }, [caseId, fetchCaseDetail, fetchStatusLogs])

  const caseData = currentCase
  if (loading && !caseData) {
    return <div className="flex h-72 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-secondary" /></div>
  }
  if (!caseData || !caseId) return <p className="text-muted-foreground">加载案件中...</p>

  const isRespond = caseData.case_mode === "respond"
  const documentPath = isRespond ? "respond" : "complaint"
  const documentLabel = isRespond ? "反证答辩" : "投诉文本"
  const documentDescription = isRespond ? "基于事实与证据生成结构化答辩内容" : "基于事实与证据生成可用的投诉文稿"

  const workflowSteps = [
    {
      id: "evidence",
      title: "上传证据材料",
      description: "添加订单、聊天记录、付款凭证等，系统会自动识别关键信息。",
      path: "evidence",
      icon: Upload,
      count: caseData.evidence_count,
      countLabel: `${caseData.evidence_count} 份证据`,
      complete: caseData.evidence_count > 0,
    },
    {
      id: "timeline",
      title: "核对事实时间线",
      description: "按时间顺序整理关键事件，确认事实脉络准确、完整。",
      path: "timeline",
      icon: Clock3,
      count: caseData.timeline_count,
      countLabel: `${caseData.timeline_count} 个节点`,
      complete: caseData.timeline_count > 0,
    },
    {
      id: "document",
      title: `生成${documentLabel}`,
      description: documentDescription,
      path: documentPath,
      icon: isRespond ? Gavel : MessageSquareText,
      count: caseData.template_count,
      countLabel: `${caseData.template_count} 个版本`,
      complete: caseData.template_count > 0,
    },
    {
      id: "export",
      title: "检查脱敏并导出",
      description: "检查敏感信息处理结果，整理并下载最终材料。",
      path: caseData.image_evidence_count > 0 ? "mask" : "export",
      icon: ShieldCheck,
      count: 0,
      countLabel: "最终交付",
      complete: caseData.status === "closed",
    },
  ]

  const nextStepIndex = workflowSteps.findIndex((step) => !step.complete)
  const activeStepIndex = nextStepIndex === -1 ? workflowSteps.length - 1 : nextStepIndex
  const nextStep = workflowSteps[activeStepIndex]
  const completedSteps = workflowSteps.filter((step) => step.complete).length
  const progress = Math.round((completedSteps / workflowSteps.length) * 100)
  const currentStatusIdx = MAIN_FLOW.indexOf(caseData.status as (typeof MAIN_FLOW)[number])
  const isTerminal = caseData.status === "closed" || caseData.status === "cancelled"

  return (
    <div className="space-y-5 pb-8">
      <Link to="/cases" className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />返回案件列表
      </Link>

      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_24px_70px_rgba(26,40,33,.16)]">
        <div className="absolute -right-16 -top-24 h-64 w-64 rounded-full bg-[#6c9b7f]/20 blur-3xl" />
        <div className="absolute bottom-0 right-[28%] h-32 w-32 rounded-full bg-[#d4b25c]/10 blur-2xl" />
        <div className="relative grid gap-8 p-6 sm:p-8 xl:grid-cols-[1fr_340px] xl:p-9">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/8 px-3 py-1 text-xs text-white/75">
                <Sparkles className="h-3.5 w-3.5 text-[#d4b25c]" />案件工作台
              </span>
              <span className="rounded-full border border-white/15 px-3 py-1 text-xs text-white/65">{disputeLabel(caseData.case_type)}</span>
              <StatusTag status={caseData.status} />
            </div>
            <h1 className="mt-5 max-w-3xl text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">{caseData.title}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">
              {caseData.description || "在这里按步骤完成证据整理、事实核对与文稿生成。"}
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-3 text-xs text-white/55">
              <span className="flex items-center gap-1.5"><Image className="h-4 w-4 text-white/75" />{caseData.evidence_count} 份证据</span>
              <span className="flex items-center gap-1.5"><ScanText className="h-4 w-4 text-white/75" />{caseData.extracted_field_count} 个抽取字段</span>
              <span className="flex items-center gap-1.5"><Layers3 className="h-4 w-4 text-white/75" />{caseData.timeline_count} 个事实节点</span>
            </div>
          </div>

          <div className="rounded-2xl border border-white/12 bg-white/8 p-5 backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-[0.16em] text-white/45">建议下一步</span>
              <span className="text-xs text-white/45">{completedSteps}/{workflowSteps.length} 已完成</span>
            </div>
            <div className="mt-4 flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-[#17231d]">
                <nextStep.icon className="h-5 w-5" />
              </span>
              <div>
                <h2 className="font-semibold">{isTerminal ? "查看案件材料" : nextStep.title}</h2>
                <p className="mt-1 text-xs leading-5 text-white/55">{isTerminal ? "案件流程已结束，所有材料仍可随时查看。" : nextStep.description}</p>
              </div>
            </div>
            <Link
              to={`/cases/${caseId}/${nextStep.path}`}
              className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-[#17231d] transition-all hover:-translate-y-0.5 hover:bg-[#f2f5f1]"
            >
              {isTerminal ? "查看材料" : "现在开始"}<ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {error && <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">推荐流程</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight text-foreground">一步一步完成案件准备</h2>
              <p className="mt-1 text-sm text-muted-foreground">系统会根据已有材料判断进度，并自动推荐接下来的操作。</p>
            </div>
            <div className="min-w-28 text-right">
              <span className="text-sm font-semibold text-foreground">{progress}%</span>
              <div className="mt-2 h-1.5 w-28 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-secondary transition-all" style={{ width: `${progress}%` }} />
              </div>
            </div>
          </div>

          <div className="mt-6 grid gap-3 lg:grid-cols-2">
            {workflowSteps.map((step, index) => {
              const active = index === activeStepIndex && !isTerminal
              return (
                <Link
                  key={step.id}
                  to={`/cases/${caseId}/${step.path}`}
                  className={cn(
                    "group relative flex min-h-40 flex-col rounded-2xl border p-5 transition-all",
                    active
                      ? "border-secondary/35 bg-[#f0f5f1] shadow-[0_12px_30px_rgba(63,107,87,.09)]"
                      : "border-border bg-white hover:-translate-y-0.5 hover:border-secondary/25 hover:shadow-md"
                  )}
                >
                  <div className="flex items-start justify-between gap-4">
                    <span className={cn("flex h-10 w-10 items-center justify-center rounded-xl", step.complete ? "bg-secondary text-white" : active ? "bg-[#dce8df] text-secondary" : "bg-muted text-muted-foreground")}>
                      {step.complete ? <Check className="h-5 w-5" /> : <step.icon className="h-5 w-5" />}
                    </span>
                    <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", step.complete ? "bg-accent text-secondary" : active ? "bg-secondary text-white" : "bg-muted text-muted-foreground")}>
                      {step.complete ? "已完成" : active ? "下一步" : step.countLabel}
                    </span>
                  </div>
                  <div className="mt-4">
                    <p className="text-xs font-medium text-muted-foreground">步骤 {index + 1}</p>
                    <h3 className="mt-0.5 font-semibold text-foreground">{step.title}</h3>
                    <p className="mt-1.5 text-sm leading-5 text-muted-foreground">{step.description}</p>
                  </div>
                  <ArrowRight className="absolute bottom-5 right-5 h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-secondary" />
                </Link>
              )
            })}
          </div>
        </section>

        <aside className="space-y-5">
          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)]">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-secondary"><Bot className="h-5 w-5" /></span>
              <div>
                <h2 className="text-sm font-semibold text-foreground">系统流程状态</h2>
                <p className="text-xs text-muted-foreground">由材料处理结果自动更新</p>
              </div>
            </div>

            {caseData.status === "cancelled" ? (
              <div className="mt-5 rounded-xl bg-destructive/8 p-4">
                <p className="text-sm font-semibold text-destructive">案件已取消</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">当前案件不再继续流转，已有材料会继续保留。</p>
              </div>
            ) : (
              <div className="relative mt-5 space-y-0">
                {MAIN_FLOW.map((status, index) => {
                  const done = currentStatusIdx > index
                  const current = currentStatusIdx === index
                  return (
                    <div key={status} className="relative flex min-h-14 gap-3">
                      {index < MAIN_FLOW.length - 1 && <div className={cn("absolute left-[9px] top-5 h-[calc(100%-4px)] w-px", done ? "bg-secondary" : "bg-border")} />}
                      <span className={cn("relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 bg-white", done || current ? "border-secondary" : "border-border")}>
                        {done ? <Check className="h-3 w-3 text-secondary" /> : current ? <CircleDot className="h-2.5 w-2.5 text-secondary" /> : null}
                      </span>
                      <div>
                        <p className={cn("text-sm font-medium", done || current ? "text-foreground" : "text-muted-foreground")}>{FLOW_LABELS[status]}</p>
                        {current && <p className="mt-0.5 text-xs text-secondary">当前 · {statusLabel(status)}</p>}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            <div className="mt-2 flex gap-2 rounded-xl bg-muted/70 p-3 text-xs leading-5 text-muted-foreground">
              <Bot className="mt-0.5 h-4 w-4 shrink-0 text-secondary" />
              <p>无需手动推进状态。当证据处理、文稿生成或归档完成时，系统将自动更新。</p>
            </div>
          </section>

          <section className="overflow-hidden rounded-[24px] border border-border bg-card shadow-[0_12px_36px_rgba(31,45,38,.05)]">
            <button onClick={() => setShowHistory((value) => !value)} className="flex w-full items-center justify-between p-5 text-left">
              <span className="flex items-center gap-2 text-sm font-semibold text-foreground"><History className="h-4 w-4 text-secondary" />状态记录 <span className="font-normal text-muted-foreground">{statusLogs.length}</span></span>
              {showHistory ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
            </button>
            {showHistory && (
              <div className="border-t border-border px-5 py-4">
                {statusLogs.length === 0 ? (
                  <div className="py-3 text-center"><FileCheck2 className="mx-auto h-6 w-6 text-muted-foreground/50" /><p className="mt-2 text-xs text-muted-foreground">暂无状态变更记录</p></div>
                ) : (
                  <div className="space-y-4">
                    {[...statusLogs].reverse().map((log) => (
                      <div key={log.id} className="border-l-2 border-accent pl-3">
                        <div className="flex flex-wrap items-center gap-1.5 text-xs"><span className="font-medium text-foreground">{statusLabel(log.from_status)}</span><ArrowRight className="h-3 w-3 text-muted-foreground" /><span className="font-medium text-secondary">{statusLabel(log.to_status)}</span></div>
                        {log.remark && <p className="mt-1 text-xs leading-5 text-muted-foreground">{log.remark}</p>}
                        {log.timestamp && <p className="mt-1 text-[11px] text-muted-foreground/75">{log.timestamp}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

          <Link to={`/cases/${caseId}/export`} className="group flex items-center gap-3 rounded-2xl border border-border bg-card p-4 transition-all hover:border-secondary/30 hover:shadow-md">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-muted text-muted-foreground"><FileText className="h-4 w-4" /></span>
            <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-foreground">案件材料总览</p><p className="text-xs text-muted-foreground">预览并导出已整理内容</p></div>
            <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
          </Link>
        </aside>
      </div>
    </div>
  )
}
