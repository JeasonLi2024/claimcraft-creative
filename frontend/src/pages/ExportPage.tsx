import { useState, useEffect } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { TEMPLATES } from "@/composables/useStatus"
import EmptyState from "@/components/EmptyState"
import { cn } from "@/lib/utils"
import { Download, FileText, Archive, FileDown, Loader2, CheckCircle2, AlertCircle } from "lucide-react"

const FORMATS = [
  { id: "text", label: "文本包", icon: FileText, desc: "生成结构化文本文件，包含投诉文案、证据列表、时间线" },
  { id: "zip", label: "ZIP 证据包", icon: Archive, desc: "打包所有证据图片和文本为 ZIP 压缩包" },
  { id: "pdf", label: "PDF 文档", icon: FileDown, desc: "生成正式 PDF 格式的投诉材料文档" },
]

export default function ExportPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const exportText = useCaseStore((s) => s.exportText)
  const exportPackage = useCaseStore((s) => s.exportPackage)
  const exportPDF = useCaseStore((s) => s.exportPDF)
  const currentCase = useCaseStore((s) => s.currentCase)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)

  const [selectedFormat, setSelectedFormat] = useState("text")
  const [selectedTemplate, setSelectedTemplate] = useState(TEMPLATES[0].type)
  const [masked, setMasked] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [result, setResult] = useState<{ type: string; filename?: string; content?: string } | null>(null)

  useEffect(() => {
    if (caseId) fetchCaseDetail(Number(caseId))
  }, [caseId])

  function triggerDownload(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleExport() {
    if (!caseId) return
    setExporting(true)
    setResult(null)
    try {
      if (selectedFormat === "text") {
        const data = await exportText(Number(caseId), { template_type: selectedTemplate, masked })
        setResult({ type: "text", filename: data.filename, content: data.content })
      } else if (selectedFormat === "zip") {
        const blob = await exportPackage(Number(caseId), selectedTemplate)
        triggerDownload(blob, `case-${caseId}-evidence.zip`)
        setResult({ type: "zip", filename: `case-${caseId}-evidence.zip` })
      } else if (selectedFormat === "pdf") {
        const blob = await exportPDF(Number(caseId), selectedTemplate)
        triggerDownload(blob, `case-${caseId}-complaint.pdf`)
        setResult({ type: "pdf", filename: `case-${caseId}-complaint.pdf` })
      }
    } catch {}
    finally { setExporting(false) }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">导出中心</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          将案件材料导出为不同格式，方便提交或存档
        </p>
      </div>

      {/* Format selection */}
      <div className="grid gap-4 sm:grid-cols-3">
        {FORMATS.map((fmt) => (
          <button
            key={fmt.id}
            onClick={() => { setSelectedFormat(fmt.id); setResult(null) }}
            className={cn(
              "flex flex-col items-start rounded-2xl border-2 p-5 text-left transition-all",
              selectedFormat === fmt.id
                ? "border-primary bg-primary/5"
                : "border-border/50 bg-card hover:border-primary/30"
            )}
          >
            <fmt.icon className={cn("h-8 w-8", selectedFormat === fmt.id ? "text-primary" : "text-muted-foreground")} />
            <h3 className="mt-3 font-semibold text-foreground">{fmt.label}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{fmt.desc}</p>
          </button>
        ))}
      </div>

      {/* Options */}
      {selectedFormat === "text" && (
        <div className="space-y-4 rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
          <h3 className="text-sm font-semibold text-foreground">文本包选项</h3>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">投诉模板</label>
            <div className="flex gap-1 rounded-xl bg-muted/50 p-1">
              {TEMPLATES.map((t) => (
                <button
                  key={t.type}
                  onClick={() => setSelectedTemplate(t.type)}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-sm font-medium transition-all",
                    selectedTemplate === t.type ? "bg-white text-foreground shadow-sm" : "text-muted-foreground"
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={masked} onChange={(e) => setMasked(e.target.checked)} className="rounded" />
            <span className="text-foreground">对敏感信息进行打码</span>
          </label>
        </div>
      )}

      {selectedFormat === "pdf" && (
        <div className="rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
          <h3 className="text-sm font-semibold text-foreground">PDF 选项</h3>
          <div className="mt-3">
            <label className="mb-1.5 block text-sm font-medium text-foreground">投诉模板</label>
            <select
              value={selectedTemplate}
              onChange={(e) => setSelectedTemplate(e.target.value)}
              className="w-full max-w-xs rounded-xl border border-input bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
            >
              {TEMPLATES.map((t) => (
                <option key={t.type} value={t.type}>{t.label}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {selectedFormat === "zip" && (
        <div className="space-y-4 rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
          <h3 className="text-sm font-semibold text-foreground">ZIP 选项</h3>
          <p className="text-sm text-muted-foreground">
            ZIP 证据包将包含所有证据图片和 OCR 识别结果，适合提交给平台或监管部门。
          </p>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">投诉模板</label>
            <select
              value={selectedTemplate}
              onChange={(e) => setSelectedTemplate(e.target.value)}
              className="w-full max-w-xs rounded-xl border border-input bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
            >
              {TEMPLATES.map((t) => (
                <option key={t.type} value={t.type}>{t.label}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Export button */}
      <button
        onClick={handleExport}
        disabled={exporting}
        className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
      >
        <Download className={cn("h-4 w-4", exporting && "animate-bounce")} />
        {exporting ? "导出中..." : "导出"}
      </button>

      {error && <div className="flex items-center gap-2 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive"><AlertCircle className="h-4 w-4" />{error}</div>}

      {/* Result */}
      {result && (
        <div className="flex items-center gap-3 rounded-2xl border border-secondary/30 bg-secondary/5 p-4">
          <CheckCircle2 className="h-5 w-5 text-secondary" />
          <div>
            <p className="text-sm font-semibold text-foreground">导出成功</p>
            {result.filename && <p className="text-xs text-muted-foreground">{result.filename}</p>}
          </div>
        </div>
      )}

      {/* Text preview */}
      {result?.type === "text" && result.content && (
        <div className="rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
          <h3 className="mb-3 text-sm font-semibold text-foreground">导出预览</h3>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-muted/30 p-4 text-xs text-muted-foreground">
            {result.content}
          </pre>
        </div>
      )}
    </div>
  )
}
