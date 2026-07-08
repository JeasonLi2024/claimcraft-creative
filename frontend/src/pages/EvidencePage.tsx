import { useState, useEffect, useRef, useCallback } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useFormat } from "@/composables/useFormat"
import { useStatus } from "@/composables/useStatus"
import PillTag from "@/components/PillTag"
import EmptyState from "@/components/EmptyState"
import { WorkflowStreamPanel } from "@/components/workflow/WorkflowStreamPanel"
import { cn } from "@/lib/utils"
import type { ExtractedField } from "@/types/case"
import {
  Upload, Plus, ChevronDown, ChevronRight, Trash2, ImagePlus,
  X, Loader2, FileText, Eye, Clock,
} from "lucide-react"

// v9: 证据类别 → 中文标签映射（与后端 classify_node 保持一致）
const EVIDENCE_CATEGORY_LABELS: Record<string, string> = {
  chat_screenshot: "聊天截图",
  product_order: "商品订单",
  logistics_tracking: "物流跟踪",
  payment_record: "支付凭证",
  invoice: "发票",
  service_contract: "服务合同",
  work_record: "施工记录",
  communication_record: "沟通记录",
  contract_document: "合同文件",
  medical_record: "医疗记录",
  other: "其他",
}

// v9: 字段分类展示顺序（与后端 FIELD_CATEGORY_MAP 保持一致）
const FIELD_CATEGORY_ORDER = [
  "订单信息", "支付信息", "物流信息", "发票信息", "联系信息", "时间信息", "其他",
]

// v9: 按字段分类分组（field_category 为空时归入「其他」）
function groupFieldsByCategory(fields: ExtractedField[]) {
  const groups: Record<string, ExtractedField[]> = {}
  for (const f of fields) {
    const cat = f.field_category || "其他"
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(f)
  }
  // 按预定义顺序输出，未在顺序中的类别追加到末尾
  return FIELD_CATEGORY_ORDER
    .filter((cat) => groups[cat]?.length)
    .map((cat) => ({ category: cat, fields: groups[cat] }))
}

export default function EvidencePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchEvidences = useCaseStore((s) => s.fetchEvidences)
  const uploadEvidence = useCaseStore((s) => s.uploadEvidence)
  const addEvidence = useCaseStore((s) => s.addEvidence)
  const removeEvidence = useCaseStore((s) => s.removeEvidence)
  const fetchExtractedFields = useCaseStore((s) => s.fetchExtractedFields)
  const updateExtractedField = useCaseStore((s) => s.updateExtractedField)
  const evidences = useCaseStore((s) => s.evidences)
  const extractedFieldsMap = useCaseStore((s) => s.extractedFieldsMap)
  const currentCase = useCaseStore((s) => s.currentCase)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)
  const { formatTime } = useFormat()
  const { disputeLabel } = useStatus()

  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [expandedOcr, setExpandedOcr] = useState<Set<number>>(new Set())
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (caseId) {
      fetchCaseDetail(Number(caseId))
      fetchEvidences(Number(caseId))
    }
  }, [caseId])

  function toggleOcr(evId: number) {
    setExpandedOcr((prev) => {
      const next = new Set(prev)
      if (next.has(evId)) {
        next.delete(evId)
      } else {
        next.add(evId)
        // Fetch fields on first expand
        fetchExtractedFields(evId)
      }
      return next
    })
  }

  async function handleFileUpload(files: FileList | null) {
    if (!files || !caseId) return
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        if (file.type.startsWith("image/")) {
          await uploadEvidence(Number(caseId), file)
        }
      }
    } catch {}
    finally { setUploading(false) }
  }

  async function handleAddSample() {
    if (!caseId) return
    try {
      await addEvidence(Number(caseId), {
        description: "示例证据 - 聊天截图",
        evidence_type: "screenshot",
        source_time: new Date().toISOString(),
      })
    } catch {}
  }

  async function handleDelete(evId: number) {
    try { await removeEvidence(evId) } catch {}
  }

  async function handleFieldBlur(fieldId: number, newValue: string) {
    try { await updateExtractedField(fieldId, { field_value: newValue }) } catch {}
  }

  const ocrStatusVariant = (status: string | null) => {
    if (status === "done") return "success"
    if (status === "pending") return "warning"
    if (status === "failed") return "danger"
    return "default"
  }

  const ocrStatusLabel = (status: string | null) => {
    if (status === "done") return "OCR 完成"
    if (status === "pending") return "OCR 处理中"
    if (status === "failed") return "OCR 失败"
    return "未识别"
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{"证据管理"}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {"上传截图、文本等证据材料，系统将自动进行 OCR 识别和信息抽取"}
        </p>
      </div>

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFileUpload(e.dataTransfer.files) }}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 transition-all",
          dragOver
            ? "border-primary bg-primary/5"
            : "border-border/50 hover:border-primary/30 hover:bg-accent/30"
        )}
      >
        {uploading ? (
          <Loader2 className="mb-2 h-8 w-8 animate-spin text-primary" />
        ) : (
          <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        )}
        <p className="text-sm font-medium text-foreground">
          {uploading ? "正在上传并识别..." : "拖拽图片到此处上传"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{"支持 JPG、PNG、WEBP 格式"}</p>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => handleFileUpload(e.target.files)}
        />
      </div>

      <button
        onClick={handleAddSample}
        className="inline-flex items-center gap-1.5 rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
      >
        <Plus className="h-4 w-4" />
        {"添加示例证据"}
      </button>

      {/* Error */}
      {error && <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      {/* Loading */}
      {loading && evidences.length === 0 && (
        <div className="flex h-48 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      )}

      {/* Empty state */}
      {!loading && evidences.length === 0 && (
        <EmptyState
          icon={<ImagePlus className="h-8 w-8" />}
          title="还没有证据"
          description="上传截图或添加文本证据，系统将自动进行 OCR 识别"
        />
      )}

      {/* Evidence grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        {evidences.map((ev) => {
          const isExpanded = expandedOcr.has(ev.id)
          const fields = extractedFieldsMap[ev.id] || []

          return (
            <div key={ev.id} className="rounded-[18px] border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
              {/* Header: code + type + OCR + delete */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center rounded-lg bg-gradient-to-r from-[#2f6bff]/10 to-[#11b981]/10 px-2.5 py-0.5 text-xs font-bold text-primary">
                    {ev.code}
                  </span>
                  <PillTag label={ev.evidence_type || "未知"} variant="default" />
                  {ev.evidence_category && (
                    <PillTag
                      label={EVIDENCE_CATEGORY_LABELS[ev.evidence_category] || ev.evidence_category}
                      variant="primary"
                    />
                  )}
                  <PillTag label={ocrStatusLabel(ev.ocr_status)} variant={ocrStatusVariant(ev.ocr_status)} />
                </div>
                <button
                  onClick={() => handleDelete(ev.id)}
                  className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              {/* Image or text */}
              {ev.image ? (
                <div
                  className="mt-3 cursor-pointer overflow-hidden rounded-xl"
                  onClick={() => setLightboxSrc(ev.image)}
                >
                  <img
                    src={ev.image}
                    alt={ev.code}
                    loading="lazy"
                    className="h-40 w-full rounded-xl object-cover transition-transform hover:scale-[1.02]"
                  />
                </div>
              ) : (
                <p className="mt-3 line-clamp-3 rounded-xl bg-muted/50 p-3 text-sm text-muted-foreground">
                  {ev.description || "无文本内容"}
                </p>
              )}

              {/* Source time */}
              {ev.source_time && (
                <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" />
                  <span className="font-mono">{formatTime(ev.source_time)}</span>
                </div>
              )}

              {/* OCR expandable section */}
              {(ev.ocr_status === "done" || fields.length > 0 || !!ev.ocr_summary) && (
                <div className="mt-3">
                  <button
                    onClick={() => toggleOcr(ev.id)}
                    className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                  >
                    {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    {"OCR 识别结果"} ({fields.length} {"个字段"})
                  </button>

                  {isExpanded && (
                    <div className="mt-2 space-y-2">
                      {/* v9: 视觉摘要（Captioner 生成，100-200字） */}
                      {ev.ocr_summary && (
                        <div className="rounded-xl bg-primary/5 p-3">
                          <div className="mb-1 text-xs font-semibold text-primary">{"视觉摘要"}</div>
                          <p className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">
                            {ev.ocr_summary}
                          </p>
                        </div>
                      )}

                      {ev.extracted_text && (
                        <p className="rounded-xl bg-muted/30 p-3 text-xs text-muted-foreground whitespace-pre-wrap">
                          {ev.extracted_text}
                        </p>
                      )}

                      {/* v9: 字段表 - 按 field_category 分组展示 */}
                      {fields.length > 0 && (
                        <div className="space-y-3">
                          {groupFieldsByCategory(fields).map((group) => (
                            <div key={group.category} className="overflow-hidden rounded-xl border border-border/50">
                              <div className="border-b border-border/50 bg-muted/40 px-3 py-1.5 text-xs font-semibold text-foreground/80">
                                {group.category}{" "}
                                <span className="ml-1 text-muted-foreground">({group.fields.length})</span>
                              </div>
                              <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                  <thead>
                                    <tr className="border-b border-border/30 bg-muted/20">
                                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">{"字段名"}</th>
                                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">{"值"}</th>
                                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">{"置信度"}</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {group.fields.map((field, i) => (
                                      <tr key={field.id} className={cn("border-b border-border/30", i % 2 === 0 && "bg-muted/10")}>
                                        <td className="px-3 py-2 font-medium text-foreground">{field.field_name}</td>
                                        <td className="px-3 py-2">
                                          <input
                                            type="text"
                                            defaultValue={field.field_value}
                                            onBlur={(e) => handleFieldBlur(field.id, e.target.value)}
                                            className="w-full rounded-lg border border-transparent bg-transparent px-2 py-1 text-foreground focus:border-primary focus:bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
                                          />
                                        </td>
                                        <td className="px-3 py-2 text-muted-foreground">
                                          {field.confidence !== null ? (field.confidence * 100).toFixed(1) + "%" : "-"}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Workflow Stream Panel */}
      {caseId && <WorkflowStreamPanel caseId={Number(caseId)} />}

      {/* Lightbox */}
      {lightboxSrc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setLightboxSrc(null)}
        >
          <button className="absolute right-4 top-4 rounded-lg bg-white/10 p-2 text-white hover:bg-white/20">
            <X className="h-6 w-6" />
          </button>
          <img
            src={lightboxSrc}
            alt="证据大图"
            className="max-h-[90vh] max-w-[90vw] rounded-xl object-contain"
          />
        </div>
      )}
    </div>
  )
}
