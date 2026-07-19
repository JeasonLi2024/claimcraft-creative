import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { TEMPLATES, useStatus } from "@/composables/useStatus"
import { cn } from "@/lib/utils"
import {
  AlertCircle,
  Archive,
  Check,
  CheckCircle2,
  ChevronRight,
  Download,
  Eye,
  FileDown,
  FileText,
  FileType2,
  Image,
  Info,
  Loader2,
  PackageCheck,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react"

type ExportFormat = "text" | "zip" | "pdf" | "word"

type FormatDefinition = {
  id: ExportFormat
  label: string
  eyebrow: string
  icon: typeof FileText
  description: string
  output: string
  imagePolicy: string
  privacyTone: "safe" | "warning" | "neutral"
}

const FORMATS: FormatDefinition[] = [
  {
    id: "text",
    label: "文本预览",
    eyebrow: "在线核对",
    icon: Eye,
    description: "在页面中查看最新文书、证据清单与时间线，不生成下载文件。",
    output: "页面预览",
    imagePolicy: "不包含图片",
    privacyTone: "safe",
  },
  {
    id: "zip",
    label: "ZIP 原始材料包",
    eyebrow: "完整归档",
    icon: Archive,
    description: "打包最新文书、时间线、证据清单和全部原始素材。",
    output: ".zip 文件",
    imagePolicy: "包含原图；已有打码图作为附加副本",
    privacyTone: "warning",
  },
  {
    id: "pdf",
    label: "PDF 正式文档",
    eyebrow: "固定版式",
    icon: FileDown,
    description: "使用 XeLaTeX 中文模板生成适合打印和提交的固定版式文档。",
    output: ".pdf 文件",
    imagePolicy: "证据页使用原图",
    privacyTone: "warning",
  },
  {
    id: "word",
    label: "Word 可编辑文档",
    eyebrow: "继续编辑",
    icon: FileType2,
    description: "使用 Pandoc 生成 DOCX，可在兼容软件中继续修改。",
    output: ".docx 文件",
    imagePolicy: "证据页使用原图",
    privacyTone: "warning",
  },
]

const FORMAT_NOTES: Record<ExportFormat, { title: string; items: string[] }> = {
  text: {
    title: "文本预览的处理范围",
    items: ["读取用户修改后的最新文书", "同时展示证据描述与事件时间线", "可按现有规则处理手机号、身份证号和结构化地址"],
  },
  zip: {
    title: "原始材料包内容",
    items: ["包含最新文书、时间线、证据清单和 manifest", "images/ 目录保存用户上传的原图", "已有打码图另存于 images/masked/，不会替换原图"],
  },
  pdf: {
    title: "PDF 生成说明",
    items: ["读取用户修改后的最新文书", "使用 XeLaTeX 中文模板生成固定版式", "证据图片使用原图，不读取打码图"],
  },
  word: {
    title: "Word 生成说明",
    items: ["读取用户修改后的最新文书", "使用 Pandoc 生成可编辑 DOCX", "证据图片使用原图，不读取打码图"],
  },
}

export default function ExportPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((state) => state.fetchCaseDetail)
  const exportText = useCaseStore((state) => state.exportText)
  const exportPackage = useCaseStore((state) => state.exportPackage)
  const exportPDF = useCaseStore((state) => state.exportPDF)
  const exportWord = useCaseStore((state) => state.exportWord)
  const currentCase = useCaseStore((state) => state.currentCase)
  const loading = useCaseStore((state) => state.loading)
  const error = useCaseStore((state) => state.error)
  const { disputeLabel } = useStatus()
  const [selectedFormat, setSelectedFormat] = useState<ExportFormat>("text")
  const [selectedTemplate, setSelectedTemplate] = useState(TEMPLATES[0].type)
  const [masked, setMasked] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const exportLockRef = useRef(false)
  const [result, setResult] = useState<{ type: ExportFormat; filename?: string; content?: string } | null>(null)

  useEffect(() => {
    if (caseId) fetchCaseDetail(Number(caseId))
  }, [caseId, fetchCaseDetail])

  function triggerDownload(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = filename
    anchor.style.display = "none"
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }

  async function executeExport() {
    if (!caseId || exportLockRef.current) return
    exportLockRef.current = true
    setExporting(true)
    setResult(null)
    try {
      if (selectedFormat === "text") {
        const data = await exportText(Number(caseId), { template_type: selectedTemplate, masked })
        setResult({ type: "text", filename: data.filename, content: data.content })
      } else if (selectedFormat === "zip") {
        const file = await exportPackage(Number(caseId), selectedTemplate)
        triggerDownload(file.blob, file.filename)
        setResult({ type: "zip", filename: file.filename })
      } else if (selectedFormat === "pdf") {
        const file = await exportPDF(Number(caseId), selectedTemplate)
        triggerDownload(file.blob, file.filename)
        setResult({ type: "pdf", filename: file.filename })
      } else {
        const file = await exportWord(Number(caseId), selectedTemplate)
        triggerDownload(file.blob, file.filename)
        setResult({ type: "word", filename: file.filename })
      }
    } catch {
      // Store 已将可读错误写入 error，页面统一展示。
    } finally {
      exportLockRef.current = false
      setExporting(false)
    }
  }

  function handlePrimaryAction() {
    if (selectedFormat === "text") {
      void executeExport()
      return
    }
    setConfirmOpen(true)
  }

  function selectFormat(format: ExportFormat) {
    setSelectedFormat(format)
    setResult(null)
    setConfirmOpen(false)
  }

  const selectedFormatData = FORMATS.find((format) => format.id === selectedFormat) || FORMATS[0]
  const selectedTemplateLabel = TEMPLATES.find((template) => template.type === selectedTemplate)?.label || "当前模板"
  const selectedNote = FORMAT_NOTES[selectedFormat]
  const includesOriginalImages = selectedFormat !== "text"
  const privacySummary = selectedFormat === "text"
    ? (masked ? "文本规则脱敏预览" : "原始文本预览")
    : selectedFormat === "zip"
      ? "包含原图与已有打码副本"
      : "证据图片使用原图"

  if (loading && !currentCase) {
    return <div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-secondary" /></div>
  }

  return (
    <div className="space-y-5 pb-8">
      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
        <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70"><Sparkles className="h-3.5 w-3.5 text-[#d8b967]" />案件材料交付</div>
            <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">导出中心</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">核对输出格式、文书场景和图片使用方式。下载类文件当前均保留原始证据图片，请按接收对象谨慎分享。</p>
            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{currentCase?.title || "当前案件"}</span>
              {currentCase?.case_type && <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{disputeLabel(currentCase.case_type)}</span>}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 self-end">
            {[
              { label: "证据材料", value: currentCase?.evidence_count || 0, icon: Archive },
              { label: "时间节点", value: currentCase?.timeline_count || 0, icon: FileText },
              { label: "输出方式", value: FORMATS.length, icon: PackageCheck },
            ].map((item) => (
              <div key={item.label} className="rounded-2xl border border-white/10 bg-white/8 p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between text-white/45"><span className="text-xs">{item.label}</span><item.icon className="h-4 w-4" /></div>
                <div className="mt-2 text-2xl font-semibold">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {error && <div role="alert" className="flex items-center gap-2 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive"><AlertCircle className="h-4 w-4 shrink-0" />{error}</div>}

      <section className="flex items-start gap-3 rounded-2xl border border-[#e5d9b5] bg-[#fef9ec] px-4 py-3.5 text-sm text-[#6f5a25]">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">请先区分原始材料与脱敏预览</p>
          <p className="mt-1 leading-5 text-[#806c3a]">PDF、Word 和 ZIP 均包含原始证据图片；隐私打码页生成的图片不会自动替换这些文件中的原图。文本预览可按现有规则隐藏部分结构化敏感信息。</p>
        </div>
        {caseId && <Link to={`/cases/${caseId}/mask`} className="hidden shrink-0 items-center gap-1 rounded-lg border border-[#dfd1a7] bg-white/60 px-3 py-2 text-xs font-semibold transition-colors hover:bg-white sm:inline-flex">查看隐私打码<ChevronRight className="h-3.5 w-3.5" /></Link>}
      </section>

      <section className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_330px]">
        <div className="space-y-5">
          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">第一步</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight">选择输出方式</h2>
              <p className="mt-1 text-sm text-muted-foreground">先确认需要在线核对、完整归档、固定版式还是继续编辑。</p>
            </div>
            <div role="radiogroup" aria-label="输出方式" className="mt-5 grid gap-3 md:grid-cols-2">
              {FORMATS.map((format) => {
                const selected = selectedFormat === format.id
                return (
                  <button
                    key={format.id}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => selectFormat(format.id)}
                    className={cn(
                      "relative flex min-h-44 flex-col rounded-2xl border p-5 text-left transition-all",
                      selected ? "border-secondary/40 bg-accent shadow-[0_12px_30px_rgba(63,107,87,.08)]" : "border-border bg-white hover:-translate-y-0.5 hover:border-secondary/25 hover:shadow-md",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span className={cn("flex h-11 w-11 items-center justify-center rounded-xl", selected ? "bg-secondary text-white" : "bg-muted text-muted-foreground")}><format.icon className="h-5 w-5" /></span>
                      <span className={cn("rounded-full px-2.5 py-1 text-[10px] font-semibold", format.privacyTone === "warning" ? "bg-[#f5ecd1] text-[#7a6425]" : "bg-muted text-muted-foreground")}>{format.imagePolicy}</span>
                    </div>
                    <p className="mt-4 text-[10px] font-semibold uppercase tracking-[0.14em] text-secondary">{format.eyebrow}</p>
                    <h3 className="mt-1 font-semibold">{format.label}</h3>
                    <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{format.description}</p>
                    {selected && <span className="absolute right-4 top-4 flex h-5 w-5 items-center justify-center rounded-full bg-secondary text-white"><Check className="h-3 w-3" /></span>}
                  </button>
                )
              })}
            </div>
          </section>

          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">第二步</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight">确认内容与隐私选项</h2>
              <p className="mt-1 text-sm text-muted-foreground">所有方式都会读取当前已保存的最新文书内容。</p>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <label className="block rounded-2xl border border-border bg-white p-4" htmlFor="export-template">
                <span className="flex items-center gap-2 text-sm font-semibold"><FileText className="h-4 w-4 text-secondary" />文书使用场景</span>
                <span className="mt-1 block text-xs leading-5 text-muted-foreground">决定导出的文书版本，不会重新生成文书。</span>
                <select id="export-template" value={selectedTemplate} onChange={(event) => { setSelectedTemplate(event.target.value); setResult(null) }} className="mt-3 w-full rounded-xl border border-input bg-background px-4 py-3 text-sm outline-none transition-shadow focus:border-secondary focus:ring-3 focus:ring-secondary/15">
                  {TEMPLATES.map((template) => <option key={template.type} value={template.type}>{template.label}</option>)}
                </select>
              </label>

              <div className={cn("rounded-2xl border p-4", selectedFormat === "text" ? "border-border bg-white" : "border-border bg-muted/30")}>
                <button type="button" role="switch" aria-checked={masked} onClick={() => selectedFormat === "text" && setMasked((value) => !value)} disabled={selectedFormat !== "text"} className="flex w-full items-center justify-between gap-4 text-left disabled:cursor-not-allowed">
                  <span className="flex min-w-0 items-start gap-3">
                    <ShieldCheck className={cn("mt-0.5 h-5 w-5 shrink-0", masked && selectedFormat === "text" ? "text-secondary" : "text-muted-foreground")} />
                    <span>
                      <span className="block text-sm font-semibold">结构化敏感信息脱敏</span>
                      <span className="mt-1 block text-xs leading-5 text-muted-foreground">{selectedFormat === "text" ? "处理手机号、身份证号和结构化地址；不代表已覆盖全部隐私。" : "当前下载格式不支持切换为脱敏图片版本。"}</span>
                    </span>
                  </span>
                  <span className={cn("relative h-6 w-11 shrink-0 rounded-full transition-colors", masked && selectedFormat === "text" ? "bg-secondary" : "bg-border")}><span className={cn("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform", masked && selectedFormat === "text" ? "translate-x-[22px]" : "translate-x-0.5")} /></span>
                </button>
              </div>
            </div>

            <div className={cn("mt-4 rounded-2xl border p-4", includesOriginalImages ? "border-[#e5d9b5] bg-[#fef9ec]" : "border-border bg-muted/35")}>
              <div className="flex items-start gap-3">
                {includesOriginalImages ? <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#8a702d]" /> : <Info className="mt-0.5 h-4 w-4 shrink-0 text-secondary" />}
                <div>
                  <h3 className="text-sm font-semibold">{selectedNote.title}</h3>
                  <ul className="mt-2 space-y-1.5 text-xs leading-5 text-muted-foreground">
                    {selectedNote.items.map((item) => <li key={item} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-current" />{item}</li>)}
                  </ul>
                </div>
              </div>
            </div>
          </section>

          {result?.type === "text" && result.content && (
            <section className="overflow-hidden rounded-[24px] border border-border bg-card shadow-[0_12px_36px_rgba(31,45,38,.05)]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-5 sm:p-6">
                <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">核对结果</p><h2 className="mt-1 text-lg font-semibold">{masked ? "脱敏文本预览" : "原始文本预览"}</h2><p className="mt-1 text-xs text-muted-foreground">{result.filename} · 仅在当前页面展示</p></div>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-secondary"><CheckCircle2 className="h-3.5 w-3.5" />预览已生成</span>
              </div>
              <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap break-words bg-[#fbfcf9] p-5 text-xs leading-6 text-[#555e58] sm:p-6">{result.content}</pre>
            </section>
          )}
        </div>

        <aside className="space-y-5 xl:sticky xl:top-5">
          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.06)]">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">输出确认</p>
            <div className="mt-4 flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent text-secondary"><selectedFormatData.icon className="h-6 w-6" /></span>
              <div className="min-w-0"><h2 className="truncate font-semibold">{selectedFormatData.label}</h2><p className="text-xs text-muted-foreground">{selectedTemplateLabel}</p></div>
            </div>
            <div className="mt-5 space-y-3 border-y border-border py-4 text-sm">
              <div className="flex justify-between gap-3"><span className="text-muted-foreground">案件材料</span><span className="font-medium">{currentCase?.evidence_count || 0} 份</span></div>
              <div className="flex justify-between gap-3"><span className="text-muted-foreground">输出结果</span><span className="text-right font-medium">{selectedFormatData.output}</span></div>
              <div className="flex justify-between gap-3"><span className="text-muted-foreground">图片策略</span><span className="max-w-40 text-right font-medium">{selectedFormatData.imagePolicy}</span></div>
              <div className="flex justify-between gap-3"><span className="text-muted-foreground">隐私状态</span><span className="max-w-40 text-right font-medium">{privacySummary}</span></div>
            </div>
            <button type="button" onClick={handlePrimaryAction} disabled={exporting} aria-busy={exporting} className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-[#17231d] px-5 py-3 text-sm font-semibold text-white transition-all hover:-translate-y-0.5 hover:opacity-95 disabled:translate-y-0 disabled:opacity-50">
              {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : selectedFormat === "text" ? <Eye className="h-4 w-4" /> : <Download className="h-4 w-4" />}
              {exporting ? "正在整理材料..." : selectedFormat === "text" ? "生成文本预览" : "确认并下载"}
            </button>
            {result && result.type !== "text" && <div role="status" aria-live="polite" className="mt-4 flex gap-2 rounded-xl bg-accent p-3 text-xs leading-5 text-secondary"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /><span>文件已开始下载{result.filename ? `：${result.filename}` : ""}</span></div>}
          </section>

          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_32px_rgba(31,45,38,.05)]">
            <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted text-muted-foreground"><Image className="h-5 w-5" /></span><div><h2 className="text-sm font-semibold">分享前建议</h2><p className="text-xs text-muted-foreground">确认接收对象与材料用途</p></div></div>
            <ol className="mt-5 space-y-4 text-sm text-muted-foreground">
              {["先在文书页核对最新内容", "包含原图的文件仅发给必要接收方", "公开分享前前往隐私打码页逐图检查"].map((text, index) => <li key={text} className="flex items-start gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-secondary">{index + 1}</span><span className="pt-0.5 leading-5">{text}</span></li>)}
            </ol>
          </section>
        </aside>
      </section>

      {confirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#111713]/55 p-4 backdrop-blur-sm" onClick={() => setConfirmOpen(false)}>
          <div role="dialog" aria-modal="true" aria-labelledby="export-confirm-title" className="w-full max-w-md rounded-[24px] border border-white/30 bg-[#f8f8f5] p-6 shadow-[0_30px_90px_rgba(15,22,18,.32)]" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-4">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#f5ecd1] text-[#806622]"><ShieldAlert className="h-5 w-5" /></span>
              <button type="button" onClick={() => setConfirmOpen(false)} className="rounded-lg p-2 text-muted-foreground hover:bg-muted" aria-label="关闭下载确认"><X className="h-4 w-4" /></button>
            </div>
            <h2 id="export-confirm-title" className="mt-5 text-xl font-semibold tracking-tight">确认下载包含原图的文件？</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">即将生成“{selectedFormatData.label}”。该文件会保留用户上传的原始证据图片，可能包含姓名、手机号、地址或账号等隐私信息。</p>
            <div className="mt-4 rounded-xl border border-[#e5d9b5] bg-[#fef9ec] p-3 text-xs leading-5 text-[#735f2c]">隐私打码页已有的处理结果不会替换此文件中的原图。请仅向确有必要的接收方发送。</div>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" onClick={() => setConfirmOpen(false)} className="rounded-xl border border-border bg-white px-4 py-2.5 text-sm font-semibold hover:bg-muted">返回检查</button>
              <button type="button" onClick={() => { setConfirmOpen(false); void executeExport() }} className="inline-flex items-center gap-2 rounded-xl bg-[#17231d] px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90"><Download className="h-4 w-4" />仍然下载</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
