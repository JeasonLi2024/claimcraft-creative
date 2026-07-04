import { useState, useEffect } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { TEMPLATES } from "@/composables/useStatus"
import EmptyState from "@/components/EmptyState"
import { cn } from "@/lib/utils"
import { Copy, RefreshCw, Loader2, FileText, Check } from "lucide-react"

export default function ComplaintPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchComplaint = useCaseStore((s) => s.fetchComplaint)
  const regenerateComplaint = useCaseStore((s) => s.regenerateComplaint)
  const complaintData = useCaseStore((s) => s.complaintData)
  const currentTemplate = useCaseStore((s) => s.currentTemplate)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)

  const [activeTab, setActiveTab] = useState(TEMPLATES[0].type)
  const [copied, setCopied] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [monoFont, setMonoFont] = useState(false)

  useEffect(() => {
    if (caseId) {
      fetchCaseDetail(Number(caseId))
    }
  }, [caseId])

  useEffect(() => {
    if (caseId) {
      fetchComplaint(Number(caseId), activeTab)
    }
  }, [caseId, activeTab])

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">投诉文案</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          基于证据自动生成投诉文本，支持多种模板
        </p>
      </div>

      {/* Template tabs */}
      <div className="flex gap-1 rounded-xl bg-muted/50 p-1">
        {TEMPLATES.map((t) => (
          <button
            key={t.type}
            onClick={() => setActiveTab(t.type)}
            className={cn(
              "relative rounded-lg px-4 py-2 text-sm font-medium transition-all",
              activeTab === t.type
                ? "bg-white text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {t.label}
            {activeTab === t.type && (
              <div className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-secondary" />
            )}
          </button>
        ))}
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleCopy}
          disabled={!complaintData}
          className="inline-flex items-center gap-1.5 rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50"
        >
          {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
          {copied ? "已复制" : "复制全文"}
        </button>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="inline-flex items-center gap-1.5 rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50"
        >
          <RefreshCw className={cn("h-4 w-4", regenerating && "animate-spin")} />
          {regenerating ? "生成中..." : "重新生成"}
        </button>
        <button
          onClick={() => setMonoFont(!monoFont)}
          className={cn(
            "rounded-xl border px-3 py-2 text-xs transition-colors",
            monoFont ? "border-primary bg-primary/5 text-primary" : "border-input text-muted-foreground hover:bg-accent"
          )}
        >
          等宽字体
        </button>
      </div>

      {error && <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      {/* Loading */}
      {loading && !complaintData && (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      )}

      {/* Empty state */}
      {!loading && !complaintData && (
        <EmptyState
          icon={<FileText className="h-8 w-8" />}
          title="暂无投诉文本"
          description="添加证据后，选择模板生成投诉文案"
        />
      )}

      {/* Complaint content */}
      {complaintData && (
        <div className="rounded-2xl border border-border/50 bg-card p-6 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
          <h2 className="mb-3 text-lg font-bold text-foreground">{complaintData.title}</h2>
          <pre className={cn(
            "whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground",
            monoFont && "font-mono text-xs"
          )}>
            {complaintData.content.split(/(E\d+)/).map((part, i) =>
              /^E\d+$/.test(part) ? (
                <span key={i} className="rounded bg-primary/10 px-1 font-semibold text-primary">{part}</span>
              ) : (
                <span key={i}>{part}</span>
              )
            )}
          </pre>
        </div>
      )}
    </div>
  )
}
