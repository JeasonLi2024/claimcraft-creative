import { useState, useEffect } from "react"
import { useParams, useNavigate, Link } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import EmptyState from "@/components/EmptyState"
import PillTag from "@/components/PillTag"
import { cn } from "@/lib/utils"
import { Copy, RefreshCw, Loader2, FileText, Check, ArrowLeft } from "lucide-react"

const RESPOND_TEMPLATES = [
  { type: "platform", label: "平台申诉版" },
  { type: "regulatory", label: "监管申诉版" },
  { type: "legal", label: "法律答辩版" },
]

const RESPOND_TYPE_LABELS: Record<string, string> = {
  platform: "平台申诉版",
  regulatory: "监管申诉版",
  legal: "法律答辩版",
}

const TONE_LABELS: Record<string, string> = {
  firm: "坚定反驳",
  restrained: "克制答辩",
  legal: "法律严谨",
}

export default function RespondPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const complaintDraft = useCaseStore((s) => s.complaintDraft)
  const currentCase = useCaseStore((s) => s.currentCase)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)

  const [activeTab, setActiveTab] = useState(RESPOND_TEMPLATES[0].type)
  const [copied, setCopied] = useState(false)
  const [monoFont, setMonoFont] = useState(false)

  useEffect(() => {
    if (caseId) {
      fetchCaseDetail(Number(caseId))
    }
  }, [caseId])

  async function handleCopy() {
    if (!complaintDraft) return
    try {
      await navigator.clipboard.writeText(complaintDraft.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }

  const respondData = complaintDraft
  const isRespondMode = currentCase?.case_mode === "respond"

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Link
        to={caseId ? `/cases/${caseId}/workspace` : "/cases"}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-4 w-4" />
        返回工作台
      </Link>

      <div>
        <h1 className="text-2xl font-bold text-foreground">反证答辩书</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          基于证据自动生成商家反证答辩书，支持多种模板
        </p>
      </div>

      {/* Case mode indicator */}
      {currentCase && !isRespondMode && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-700">
          当前案件为维权投诉模式，反证答辩书适用于商家反证模式案件
        </div>
      )}

      {/* Template tabs */}
      <div className="flex gap-1 rounded-xl bg-muted/50 p-1">
        {RESPOND_TEMPLATES.map((t) => (
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
          disabled={!respondData}
          className="inline-flex items-center gap-1.5 rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50"
        >
          {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
          {copied ? "已复制" : "复制全文"}
        </button>
        <button
          onClick={() => navigate(`/cases/${caseId}/workspace`)}
          className="inline-flex items-center gap-1.5 rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          <RefreshCw className="h-4 w-4" />
          重新生成
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
      {loading && !respondData && (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      )}

      {/* Empty state */}
      {!loading && !respondData && (
        <EmptyState
          icon={<FileText className="h-8 w-8" />}
          title="暂无反证答辩书"
          description="运行工作流后，系统将自动生成反证答辩书。请前往工作台启动工作流。"
        />
      )}

      {/* Respond content */}
      {respondData && (
        <div className="rounded-2xl border border-border/50 bg-card p-6 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-bold text-foreground">{respondData.title}</h2>
            <PillTag
              label={RESPOND_TYPE_LABELS[activeTab] || activeTab}
              variant="primary"
            />
            {respondData.tone && (
              <PillTag
                label={TONE_LABELS[respondData.tone] || respondData.tone}
                variant="default"
              />
            )}
          </div>
          <pre className={cn(
            "whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground",
            monoFont && "font-mono text-xs"
          )}>
            {respondData.content.split(/(E\d+)/).map((part, i) =>
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
