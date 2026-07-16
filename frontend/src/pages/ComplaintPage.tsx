import { useState, useEffect } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { TEMPLATES, useStatus } from "@/composables/useStatus"
import { cn } from "@/lib/utils"
import { Copy, RefreshCw, Loader2, FileText, Check, Sparkles, WandSparkles, Type, Quote } from "lucide-react"

function MarkdownDocument({ content, mono }: { content: string; mono: boolean }) {
  return (
    <div className={cn("space-y-3 text-sm leading-7 text-foreground", mono && "font-mono text-xs leading-6")}>
      {content.split(/\n{2,}/).map((block, index) => {
        const lines = block.split("\n")
        if (block.startsWith("## ")) return <section key={index}><h2 className="mb-2 mt-6 border-b border-border pb-2 text-lg font-semibold">{lines[0].slice(3)}</h2>{lines.slice(1).map((line, lineIndex) => <p key={lineIndex} className="whitespace-pre-wrap">{line}</p>)}</section>
        if (block.startsWith("# ")) return <h1 key={index} className="text-xl font-semibold">{block.slice(2)}</h1>
        if (lines.every((line) => line.trim().startsWith("- "))) return <ul key={index} className="list-disc space-y-2 pl-6">{lines.map((line, lineIndex) => <li key={lineIndex}>{line.replace(/^- /, "").split(/(E\d+)/).map((part, partIndex) => /^E\d+$/.test(part) ? <span key={partIndex} className="rounded-md bg-accent px-1.5 py-0.5 font-semibold text-secondary">{part}</span> : part)}</li>)}</ul>
        return <p key={index} className="whitespace-pre-wrap">{block.split(/(E\d+)/).map((part, partIndex) => /^E\d+$/.test(part) ? <span key={partIndex} className="rounded-md bg-accent px-1.5 py-0.5 font-semibold text-secondary">{part}</span> : part)}</p>
      })}
    </div>
  )
}

export default function ComplaintPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchComplaint = useCaseStore((s) => s.fetchComplaint)
  const regenerateComplaint = useCaseStore((s) => s.regenerateComplaint)
  const complaintData = useCaseStore((s) => s.complaintData)
  const currentCase = useCaseStore((s) => s.currentCase)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)
  const { disputeLabel } = useStatus()
  const [activeTab, setActiveTab] = useState(TEMPLATES[0].type)
  const [copied, setCopied] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [monoFont, setMonoFont] = useState(false)

  useEffect(() => {
    if (caseId) fetchCaseDetail(Number(caseId))
  }, [caseId, fetchCaseDetail])

  useEffect(() => {
    if (caseId) fetchComplaint(Number(caseId), activeTab)
  }, [caseId, activeTab, fetchComplaint])

  async function handleRegenerate() {
    if (!caseId) return
    setRegenerating(true)
    try { await regenerateComplaint(Number(caseId), activeTab) } catch {}
    finally { setRegenerating(false) }
  }

  async function handleCopy() {
    if (!complaintData) return
    try {
      await navigator.clipboard.writeText(complaintData.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }

  const activeTemplate = TEMPLATES.find((template) => template.type === activeTab)
  const evidenceRefs = complaintData?.content.match(/E\d+/g) || []

  return (
    <div className="space-y-5 pb-8">
      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
        <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70"><WandSparkles className="h-3.5 w-3.5 text-[#d8b967]" />智能文书生成</div>
            <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">投诉文案</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">基于案件事实和证据引用生成结构化投诉文本。选择使用场景，核对内容后即可复制或前往导出。</p>
            <div className="mt-6 flex flex-wrap gap-2"><span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{currentCase?.title || "当前案件"}</span>{currentCase?.case_type && <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{disputeLabel(currentCase.case_type)}</span>}</div>
          </div>
          <div className="grid grid-cols-3 gap-3 self-end">
            {[{ label: "可用模板", value: TEMPLATES.length, icon: FileText }, { label: "引用证据", value: new Set(evidenceRefs).size, icon: Quote }, { label: "当前版本", value: complaintData ? 1 : 0, icon: Sparkles }].map((item) => <div key={item.label} className="rounded-2xl border border-white/10 bg-white/8 p-4 backdrop-blur-sm"><div className="flex items-center justify-between text-white/45"><span className="text-xs">{item.label}</span><item.icon className="h-4 w-4" /></div><div className="mt-2 text-2xl font-semibold">{item.value}</div></div>)}
          </div>
        </div>
      </section>

      {error && <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <section className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_310px]">
        <div className="overflow-hidden rounded-[24px] border border-border bg-card shadow-[0_12px_36px_rgba(31,45,38,.05)]">
          <div className="border-b border-border p-5 sm:p-6">
            <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">文书预览</p><h2 className="mt-1 text-xl font-semibold tracking-tight">{complaintData?.title || "等待生成投诉文本"}</h2><p className="mt-1 text-sm text-muted-foreground">当前模板：{activeTemplate?.label}</p></div><div className="flex flex-wrap gap-2"><button onClick={handleCopy} disabled={!complaintData} className="inline-flex items-center gap-2 rounded-xl border border-input px-3.5 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50">{copied ? <Check className="h-4 w-4 text-secondary" /> : <Copy className="h-4 w-4" />}{copied ? "已复制" : "复制全文"}</button><button onClick={handleRegenerate} disabled={regenerating} className="inline-flex items-center gap-2 rounded-xl bg-[#17231d] px-3.5 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"><RefreshCw className={cn("h-4 w-4", regenerating && "animate-spin")} />{regenerating ? "生成中..." : "重新生成"}</button></div></div>
          </div>

          {loading && !complaintData ? <div className="flex h-72 items-center justify-center"><Loader2 className="h-7 w-7 animate-spin text-secondary" /></div> : complaintData ? <div className="p-5 sm:p-7"><MarkdownDocument content={complaintData.content} mono={monoFont} /></div> : <div className="px-6 py-16 text-center"><FileText className="mx-auto h-8 w-8 text-muted-foreground" /><h3 className="mt-3 font-semibold">暂无投诉文本</h3><p className="mt-1 text-sm text-muted-foreground">完善证据和时间线后，点击重新生成创建文稿。</p></div>}
        </div>

        <aside className="space-y-5">
          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_32px_rgba(31,45,38,.05)]"><div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-secondary"><FileText className="h-5 w-5" /></span><div><h2 className="text-sm font-semibold">选择使用场景</h2><p className="text-xs text-muted-foreground">切换后自动加载对应文稿</p></div></div><div className="mt-5 space-y-2">{TEMPLATES.map((template) => <button key={template.type} onClick={() => setActiveTab(template.type)} className={cn("flex w-full items-center justify-between rounded-xl border px-3.5 py-3 text-left text-sm transition-all", activeTab === template.type ? "border-secondary/35 bg-accent font-semibold text-secondary" : "border-border bg-white text-muted-foreground hover:border-secondary/20")}><span>{template.label}</span>{activeTab === template.type && <Check className="h-4 w-4" />}</button>)}</div></section>
          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_32px_rgba(31,45,38,.05)]"><button onClick={() => setMonoFont((value) => !value)} className="flex w-full items-center justify-between"><span className="flex items-center gap-2 text-sm font-semibold"><Type className="h-4 w-4 text-secondary" />等宽字体预览</span><span className={cn("relative h-6 w-11 rounded-full transition-colors", monoFont ? "bg-secondary" : "bg-border")}><span className={cn("absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform", monoFont ? "translate-x-5" : "translate-x-0")} /></span></button><p className="mt-3 text-xs leading-5 text-muted-foreground">开启后更便于检查段落、编号和证据引用格式。</p></section>
        </aside>
      </section>
    </div>
  )
}
