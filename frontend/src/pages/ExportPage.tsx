import { useEffect, useRef, useState } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { TEMPLATES, useStatus } from "@/composables/useStatus"
import { cn } from "@/lib/utils"
import {
  AlertCircle, Archive, Check, CheckCircle2, Download, FileDown,
  FileText, FileType2, PackageCheck, ShieldCheck, Sparkles,
} from "lucide-react"

const FORMATS = [
  { id: "text", label: "文本预览", icon: FileText, desc: "在线核对当前文书、证据清单与时间线，不下载文件" },
  { id: "zip", label: "ZIP 材料包", icon: Archive, desc: "打包原始素材图片、时间线梳理文件和当前文书文本" },
  { id: "pdf", label: "PDF 文档", icon: FileDown, desc: "使用 LaTeX 中文模板生成排版固定的正式材料" },
  { id: "word", label: "Word 文档", icon: FileType2, desc: "使用 Pandoc 生成可继续修改和提交的 DOCX 文书" },
]

export default function ExportPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((state) => state.fetchCaseDetail)
  const exportText = useCaseStore((state) => state.exportText)
  const exportPackage = useCaseStore((state) => state.exportPackage)
  const exportPDF = useCaseStore((state) => state.exportPDF)
  const exportWord = useCaseStore((state) => state.exportWord)
  const currentCase = useCaseStore((state) => state.currentCase)
  const error = useCaseStore((state) => state.error)
  const { disputeLabel } = useStatus()
  const [selectedFormat, setSelectedFormat] = useState("text")
  const [selectedTemplate, setSelectedTemplate] = useState(TEMPLATES[0].type)
  const [masked, setMasked] = useState(false)
  const [exporting, setExporting] = useState(false)
  const exportLockRef = useRef(false)
  const [result, setResult] = useState<{ type: string; filename?: string; content?: string } | null>(null)

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

  async function handleExport() {
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

  const selectedFormatData = FORMATS.find((format) => format.id === selectedFormat) || FORMATS[0]
  const selectedTemplateLabel = TEMPLATES.find((template) => template.type === selectedTemplate)?.label

  return (
    <div className="space-y-5 pb-8">
      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
        <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70"><Sparkles className="h-3.5 w-3.5 text-[#d8b967]" />案件材料交付</div>
            <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">导出中心</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">根据提交渠道选择材料格式，确认模板和隐私设置后，一次生成可发送或归档的案件文件。</p>
            <div className="mt-6 flex flex-wrap gap-2"><span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{currentCase?.title || "当前案件"}</span>{currentCase?.case_type && <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{disputeLabel(currentCase.case_type)}</span>}</div>
          </div>
          <div className="grid grid-cols-3 gap-3 self-end">
            {[
              { label: "证据材料", value: currentCase?.evidence_count || 0, icon: Archive },
              { label: "时间节点", value: currentCase?.timeline_count || 0, icon: FileText },
              { label: "可选格式", value: FORMATS.length, icon: PackageCheck },
            ].map((item) => <div key={item.label} className="rounded-2xl border border-white/10 bg-white/8 p-4 backdrop-blur-sm"><div className="flex items-center justify-between text-white/45"><span className="text-xs">{item.label}</span><item.icon className="h-4 w-4" /></div><div className="mt-2 text-2xl font-semibold">{item.value}</div></div>)}
          </div>
        </div>
      </section>

      {error && <div role="alert" className="flex items-center gap-2 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive"><AlertCircle className="h-4 w-4" />{error}</div>}

      <section className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_330px]">
        <div className="space-y-5">
          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
            <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">第一步</p><h2 className="mt-1 text-xl font-semibold tracking-tight">选择导出格式</h2><p className="mt-1 text-sm text-muted-foreground">不同格式适合不同的提交和留档方式。</p></div>
            <div role="radiogroup" aria-label="导出格式" className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{FORMATS.map((format) => <button key={format.id} type="button" role="radio" aria-checked={selectedFormat === format.id} onClick={() => { setSelectedFormat(format.id); setResult(null) }} className={cn("relative flex min-h-48 flex-col items-start rounded-2xl border p-5 text-left transition-all", selectedFormat === format.id ? "border-secondary/40 bg-accent shadow-[0_12px_30px_rgba(63,107,87,.08)]" : "border-border bg-white hover:-translate-y-0.5 hover:border-secondary/25 hover:shadow-md")}><span className={cn("flex h-11 w-11 items-center justify-center rounded-xl", selectedFormat === format.id ? "bg-secondary text-white" : "bg-muted text-muted-foreground")}><format.icon className="h-5 w-5" /></span><h3 className="mt-4 font-semibold">{format.label}</h3><p className="mt-1.5 text-xs leading-5 text-muted-foreground">{format.desc}</p>{selectedFormat === format.id && <span className="absolute right-4 top-4 flex h-5 w-5 items-center justify-center rounded-full bg-secondary text-white"><Check className="h-3 w-3" /></span>}</button>)}</div>
          </section>

          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
            <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">第二步</p><h2 className="mt-1 text-xl font-semibold tracking-tight">确认导出选项</h2></div>
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <div><label htmlFor="export-template" className="mb-2 block text-sm font-medium">文书模板</label><select id="export-template" value={selectedTemplate} onChange={(event) => setSelectedTemplate(event.target.value)} className="w-full rounded-xl border border-input bg-background px-4 py-3 text-sm outline-none transition-shadow focus:border-secondary focus:ring-3 focus:ring-secondary/15">{TEMPLATES.map((template) => <option key={template.type} value={template.type}>{template.label}</option>)}</select></div>
              <div className={cn("rounded-2xl border p-4", selectedFormat === "text" ? "border-border" : "border-border bg-muted/35")}><button type="button" role="switch" aria-checked={masked} onClick={() => selectedFormat === "text" && setMasked((value) => !value)} disabled={selectedFormat !== "text"} className="flex w-full items-center justify-between text-left disabled:cursor-not-allowed"><span className="flex items-center gap-3"><ShieldCheck className={cn("h-5 w-5", masked && selectedFormat === "text" ? "text-secondary" : "text-muted-foreground")} /><span><span className="block text-sm font-medium">敏感信息打码</span><span className="mt-0.5 block text-xs text-muted-foreground">仅适用于文本预览</span></span></span><span className={cn("relative h-6 w-11 rounded-full transition-colors", masked && selectedFormat === "text" ? "bg-secondary" : "bg-border")}><span className={cn("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform", masked && selectedFormat === "text" ? "translate-x-[22px]" : "translate-x-0.5")} /></span></button></div>
            </div>
            {selectedFormat === "zip" && <p className="mt-4 rounded-xl bg-muted/55 p-3 text-xs leading-5 text-muted-foreground">ZIP 材料包包含原始素材、时间线和当前文书；若此前已完成图片打码，还会在 images/masked/ 中附带文件名带 masked 标记的打码版本。</p>}
            {selectedFormat === "pdf" && <p className="mt-4 rounded-xl bg-muted/55 p-3 text-xs leading-5 text-muted-foreground">PDF 使用 XeLaTeX 中文模板排版，并读取用户修改后的最新投诉书或反证答辩书；证据图片始终使用原图，不使用打码图。</p>}
            {selectedFormat === "word" && <p className="mt-4 rounded-xl bg-muted/55 p-3 text-xs leading-5 text-muted-foreground">Word 使用 Pandoc 生成 DOCX，读取用户修改后的最新文书并保留原始证据图片，可在 Microsoft Word 或兼容软件中继续编辑。</p>}
          </section>

          {result?.type === "text" && result.content && <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6"><div className="flex items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">导出预览</p><h2 className="mt-1 font-semibold">{result.filename}</h2></div><CheckCircle2 className="h-5 w-5 text-secondary" /></div><pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-2xl bg-muted/45 p-4 text-xs leading-6 text-muted-foreground">{result.content}</pre></section>}
        </div>

        <aside className="sticky top-5 rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.06)]">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">导出确认</p><div className="mt-4 flex items-center gap-3"><span className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent text-secondary"><selectedFormatData.icon className="h-6 w-6" /></span><div><h2 className="font-semibold">{selectedFormatData.label}</h2><p className="text-xs text-muted-foreground">{selectedTemplateLabel}</p></div></div>
          <div className="mt-5 space-y-3 border-y border-border py-4 text-sm"><div className="flex justify-between gap-3"><span className="text-muted-foreground">案件材料</span><span className="font-medium">{currentCase?.evidence_count || 0} 份</span></div><div className="flex justify-between gap-3"><span className="text-muted-foreground">隐私处理</span><span className="font-medium">{selectedFormat === "text" ? (masked ? "文本已打码" : "文本未打码") : selectedFormat === "zip" ? "原图 + 已有打码图" : "仅使用原始图片"}</span></div><div className="flex justify-between gap-3"><span className="text-muted-foreground">输出方式</span><span className="font-medium">{selectedFormat === "text" ? "生成预览" : "直接下载"}</span></div></div>
          <button type="button" onClick={handleExport} disabled={exporting} aria-busy={exporting} className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-[#17231d] px-5 py-3 text-sm font-semibold text-white transition-all hover:-translate-y-0.5 hover:opacity-95 disabled:translate-y-0 disabled:opacity-50"><Download className={cn("h-4 w-4", exporting && "animate-bounce")} />{exporting ? "正在整理材料..." : `导出${selectedFormatData.label}`}</button>
          {result && <div role="status" aria-live="polite" className="mt-4 flex gap-2 rounded-xl bg-accent p-3 text-xs leading-5 text-secondary"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /><span>导出成功{result.filename ? `：${result.filename}` : ""}</span></div>}
        </aside>
      </section>
    </div>
  )
}
