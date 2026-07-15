import { useState, useEffect, useRef } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useFormat } from "@/composables/useFormat"
import { useStatus } from "@/composables/useStatus"
import PillTag from "@/components/PillTag"
import { WorkflowStreamPanel } from "@/components/workflow/WorkflowStreamPanel"
import { cn } from "@/lib/utils"
import type { ExtractedField } from "@/types/case"
import {
  Upload, ChevronDown, ChevronRight, Trash2, X, Loader2,
  Clock, Package, Images, ScanText, CheckCircle2, Sparkles, ShieldCheck,
  Search, Layers3,
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
  // v10: 上传弹窗（物证图片支持，每张图片独立标记）
  interface PendingFile {
    file: File
    previewUrl: string
    isPhysicalEvidence: boolean
    physicalNote: string
  }
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])
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

  // v10: 拖拽/选择后打开上传弹窗，让用户为每张图片独立标记是否为物证并填写说明
  function handleFileSelect(files: FileList | null) {
    if (!files || !caseId) return
    const imgs = Array.from(files).filter((f) => f.type.startsWith("image/"))
    if (imgs.length === 0) return
    const items: PendingFile[] = imgs.map((file) => ({
      file,
      previewUrl: URL.createObjectURL(file),
      isPhysicalEvidence: false,
      physicalNote: "",
    }))
    setPendingFiles(items)
    setUploadDialogOpen(true)
  }

  // 切换某张图片的物证标记
  function togglePhysical(idx: number) {
    setPendingFiles((prev) =>
      prev.map((item, i) =>
        i === idx ? { ...item, isPhysicalEvidence: !item.isPhysicalEvidence } : item
      )
    )
  }

  // 更新某张图片的物证说明
  function updatePhysicalNote(idx: number, note: string) {
    setPendingFiles((prev) =>
      prev.map((item, i) =>
        i === idx ? { ...item, physicalNote: note } : item
      )
    )
  }

  // 删除某张待上传图片
  function removePendingFile(idx: number) {
    setPendingFiles((prev) => {
      const target = prev[idx]
      if (target) URL.revokeObjectURL(target.previewUrl)
      return prev.filter((_, i) => i !== idx)
    })
  }

  async function handleConfirmUpload() {
    if (!caseId || pendingFiles.length === 0) return
    setUploading(true)
    try {
      for (const item of pendingFiles) {
        const options = item.isPhysicalEvidence
          ? { isPhysicalEvidence: true, physicalNote: item.physicalNote.trim() }
          : undefined
        await uploadEvidence(Number(caseId), item.file, options)
      }
      // 关闭弹窗并释放预览 URL
      pendingFiles.forEach((item) => URL.revokeObjectURL(item.previewUrl))
      setUploadDialogOpen(false)
      setPendingFiles([])
    } catch {}
    finally { setUploading(false) }
  }

  function handleCancelUpload() {
    pendingFiles.forEach((item) => URL.revokeObjectURL(item.previewUrl))
    setUploadDialogOpen(false)
    setPendingFiles([])
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

  const imageCount = evidences.filter((ev) => !!ev.image).length
  const physicalCount = evidences.filter((ev) => ev.is_physical_evidence).length
  const recognizedCount = evidences.filter((ev) => ev.ocr_status === "done").length

  return (
    <div className="space-y-5 pb-8">
      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
        <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70"><Sparkles className="h-3.5 w-3.5 text-[#d8b967]" />智能材料整理</div>
            <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">证据管理</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">集中上传订单、沟通记录、支付凭证与实物照片。系统会自动识别文字、提取关键信息，并用于构建案件时间线。</p>
            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{currentCase?.title || "当前案件"}</span>
              {currentCase?.case_type && <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{disputeLabel(currentCase.case_type)}</span>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 self-end">
            {[
              { label: "全部材料", value: evidences.length, icon: Layers3 },
              { label: "图片证据", value: imageCount, icon: Images },
              { label: "识别完成", value: recognizedCount, icon: CheckCircle2 },
              { label: "物证照片", value: physicalCount, icon: Package },
            ].map((item) => (
              <div key={item.label} className="rounded-2xl border border-white/10 bg-white/8 p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between text-white/45"><span className="text-xs">{item.label}</span><item.icon className="h-4 w-4" /></div>
                <div className="mt-2 text-2xl font-semibold">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {error && <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <section className="grid items-stretch gap-5 xl:grid-cols-[minmax(0,1fr)_310px]">
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFileSelect(e.dataTransfer.files) }}
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            "group flex min-h-56 cursor-pointer flex-col items-start gap-5 rounded-[24px] border-2 border-dashed p-6 transition-all sm:flex-row sm:items-center sm:p-8",
            dragOver ? "border-secondary bg-accent shadow-[0_16px_40px_rgba(63,107,87,.10)]" : "border-[#cdd5ce] bg-card hover:-translate-y-0.5 hover:border-secondary/50 hover:bg-[#fafcf9] hover:shadow-md"
          )}
        >
          <span className={cn("flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl transition-colors", dragOver ? "bg-secondary text-white" : "bg-accent text-secondary group-hover:bg-secondary group-hover:text-white")}>
            {uploading ? <Loader2 className="h-7 w-7 animate-spin" /> : <Upload className="h-7 w-7" />}
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">添加案件材料</p>
            <h2 className="mt-1 text-lg font-semibold text-foreground">{uploading ? "正在上传并识别" : "拖拽图片到这里，或点击选择文件"}</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">支持批量上传 JPG、PNG、WEBP；实物照片可在下一步标记为纯物证。</p>
            <div className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#17231d] px-4 py-2 text-sm font-semibold text-white">选择图片<ChevronRight className="h-4 w-4" /></div>
          </div>
          <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => { handleFileSelect(e.target.files); e.currentTarget.value = "" }} />
        </div>

        <div className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_32px_rgba(31,45,38,.05)]">
          <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-secondary"><ScanText className="h-5 w-5" /></span><div><h2 className="text-sm font-semibold">上传后自动处理</h2><p className="text-xs text-muted-foreground">无需逐项手工录入</p></div></div>
          <div className="mt-5 space-y-4">
            {["识别图片中的文字与日期", "归类订单、支付和沟通信息", "提取字段并关联案件时间线"].map((text, index) => (
              <div key={text} className="flex items-start gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-secondary">{index + 1}</span><p className="pt-0.5 text-sm leading-5 text-muted-foreground">{text}</p></div>
            ))}
          </div>
          <div className="mt-5 rounded-xl bg-muted/60 p-3 text-xs leading-5 text-muted-foreground"><ShieldCheck className="mb-1.5 h-4 w-4 text-secondary" />原图和识别结果仅用于当前案件材料整理。</div>
        </div>
      </section>

      {/* 关键操作紧邻材料上传区，启动后在原位展示实时分析结果 */}
      {caseId && <WorkflowStreamPanel caseId={Number(caseId)} />}

      {loading && evidences.length === 0 && <div className="flex h-36 items-center justify-center"><Loader2 className="h-7 w-7 animate-spin text-secondary" /></div>}

      {evidences.length > 0 && (
        <div className="flex flex-wrap items-end justify-between gap-3 pt-2">
          <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">证据清单</p><h2 className="mt-1 text-xl font-semibold tracking-tight">已整理 {evidences.length} 份材料</h2></div>
          <div className="flex items-center gap-2 rounded-xl bg-muted/60 px-3 py-2 text-xs text-muted-foreground"><Search className="h-3.5 w-3.5" />点击图片可查看原图，展开卡片可核对识别结果</div>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        {evidences.map((ev) => {
          const isExpanded = expandedOcr.has(ev.id)
          const fields = extractedFieldsMap[ev.id] || []

          return (
            <article key={ev.id} className="group/card rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_34px_rgba(31,45,38,.055)] transition-all hover:-translate-y-0.5 hover:border-secondary/25 hover:shadow-[0_18px_44px_rgba(31,45,38,.09)] sm:p-6">
              {/* Header: code + type + OCR + delete */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center rounded-lg bg-[#17231d] px-2.5 py-1 text-xs font-bold text-white">
                    {ev.code}
                  </span>
                  <PillTag label={ev.evidence_type || "未知"} variant="default" />
                  {ev.evidence_category && (
                    <PillTag
                      label={EVIDENCE_CATEGORY_LABELS[ev.evidence_category] || ev.evidence_category}
                      variant="primary"
                    />
                  )}
                  {ev.is_physical_evidence && (
                    <PillTag label="物证" variant="warning" />
                  )}
                  <PillTag label={ocrStatusLabel(ev.ocr_status)} variant={ocrStatusVariant(ev.ocr_status)} />
                </div>
                <button
                  onClick={() => handleDelete(ev.id)}
                  className="rounded-xl border border-transparent p-2 text-muted-foreground transition-colors hover:border-destructive/15 hover:bg-destructive/8 hover:text-destructive"
                  aria-label={`删除证据 ${ev.code}`}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              {/* Image or text */}
              {ev.image ? (
                <div
                  className="relative mt-4 cursor-zoom-in overflow-hidden rounded-2xl bg-muted"
                  onClick={() => setLightboxSrc(ev.image)}
                >
                  <img
                    src={ev.image}
                    alt={ev.code}
                    loading="lazy"
                    className="h-52 w-full object-cover transition-transform duration-500 group-hover/card:scale-[1.025]"
                  />
                  <span className="pointer-events-none absolute bottom-3 right-3 rounded-lg bg-black/55 px-2 py-1 text-[11px] font-medium text-white backdrop-blur">查看原图</span>
                </div>
              ) : (
                <p className="mt-4 line-clamp-3 rounded-2xl bg-muted/60 p-4 text-sm leading-6 text-muted-foreground">
                  {ev.description || "无文本内容"}
                </p>
              )}

              {/* v10: 物证说明（用户填写） */}
              {ev.is_physical_evidence && ev.physical_note && (
                <div className="mt-2 rounded-xl bg-amber-50 p-3">
                  <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-amber-700">
                    <Package className="h-3.5 w-3.5" />
                    物证说明
                  </div>
                  <p className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">
                    {ev.physical_note}
                  </p>
                </div>
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
                    className="flex w-full items-center justify-between rounded-xl bg-muted/55 px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
                  >
                    <span className="flex items-center gap-2"><ScanText className="h-4 w-4 text-secondary" />{ev.is_physical_evidence ? "图片说明" : "识别与抽取结果"}<span className="text-xs font-normal text-muted-foreground">{fields.length} 个字段</span></span>
                    {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
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
            </article>
          )
        })}
      </div>

      {/* v10: 上传弹窗 - 每张图片独立标记物证 */}
      {uploadDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm" onClick={handleCancelUpload}>
          <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-[24px] border border-border bg-card p-6 shadow-[0_28px_90px_rgba(20,30,25,.28)]" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">添加案件材料</p>
                <h3 className="mt-1 text-lg font-semibold text-foreground">确认上传证据</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  共 {pendingFiles.length} 张图片，可分别为每张图片标记是否为纯物证
                </p>
              </div>
              <button
                onClick={handleCancelUpload}
                className="rounded-xl p-2 text-muted-foreground hover:bg-accent"
                aria-label="关闭上传弹窗"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* 文件列表（每张图片独立配置） */}
            <div className="flex-1 space-y-3 overflow-y-auto pr-1">
              {pendingFiles.map((item, idx) => (
                <div
                  key={idx}
                  className={cn(
                    "rounded-xl border p-3 transition-colors",
                    item.isPhysicalEvidence
                      ? "border-amber-300 bg-amber-50/50"
                      : "border-border/50 bg-muted/20"
                  )}
                >
                  <div className="flex gap-3">
                    {/* 图片缩略图 */}
                    <img
                      src={item.previewUrl}
                      alt={item.file.name}
                      className="h-20 w-20 flex-shrink-0 rounded-lg object-cover"
                    />

                    <div className="flex-1 min-w-0">
                      {/* 文件名 + 删除按钮 */}
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="truncate text-sm font-medium text-foreground">
                            {item.file.name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {(item.file.size / 1024).toFixed(0)} KB
                          </p>
                        </div>
                        <button
                          onClick={() => removePendingFile(idx)}
                          className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>

                      {/* 物证勾选 */}
                      <label className="mt-2 flex items-start gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={item.isPhysicalEvidence}
                          onChange={() => togglePhysical(idx)}
                          className="mt-0.5 rounded"
                        />
                        <div className="flex items-center gap-1">
                          <Package className="h-3.5 w-3.5 text-amber-500" />
                          <span className="font-medium text-foreground">标记为纯物证图片</span>
                          <span className="text-xs text-muted-foreground">（无文字内容，跳过 OCR）</span>
                        </div>
                      </label>

                      {/* 物证说明（仅勾选时显示） */}
                      {item.isPhysicalEvidence && (
                        <div className="mt-2">
                          <textarea
                            value={item.physicalNote}
                            onChange={(e) => updatePhysicalNote(idx, e.target.value)}
                            placeholder="描述此物证的损坏程度、现场环境、物证特征等，例如：商品收到时屏幕已碎裂，包装完好无损"
                            rows={2}
                            maxLength={500}
                            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-xs focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 resize-none"
                          />
                          <p className="mt-0.5 text-right text-[10px] text-muted-foreground">
                            {item.physicalNote.length}/500
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {pendingFiles.length === 0 && (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  已无待上传图片
                </div>
              )}
            </div>

            {/* 操作按钮 */}
            <div className="mt-4 flex justify-end gap-2 border-t border-border/50 pt-4">
              <button
                onClick={handleCancelUpload}
                disabled={uploading}
                className="rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
              >
                取消
              </button>
              <button
                onClick={handleConfirmUpload}
                disabled={
                  uploading ||
                  pendingFiles.length === 0 ||
                  pendingFiles.some((f) => f.isPhysicalEvidence && !f.physicalNote.trim())
                }
                className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {uploading ? "上传中..." : `上传 ${pendingFiles.length} 张`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Lightbox */}
      {lightboxSrc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
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
