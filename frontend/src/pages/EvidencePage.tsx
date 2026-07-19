import { useState, useEffect, useRef } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useFormat } from "@/composables/useFormat"
import { useStatus } from "@/composables/useStatus"
import PillTag from "@/components/PillTag"
import { cn } from "@/lib/utils"
import {
  Upload, ChevronRight, Trash2, X, Loader2,
  Clock, Package, Images, Sparkles, Layers3,
  Lock,
} from "lucide-react"

export default function EvidencePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchEvidences = useCaseStore((s) => s.fetchEvidences)
  const uploadEvidence = useCaseStore((s) => s.uploadEvidence)
  const removeEvidence = useCaseStore((s) => s.removeEvidence)
  const evidences = useCaseStore((s) => s.evidences)
  const currentCase = useCaseStore((s) => s.currentCase)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)
  const { formatTime } = useFormat()
  const { disputeLabel } = useStatus()

  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
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
  const [demoDeleteToast, setDemoDeleteToast] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (caseId) {
      fetchCaseDetail(Number(caseId))
      fetchEvidences(Number(caseId))
    }
  }, [caseId])

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
      // 并行提交：每张图片独立调用一次 /evidences/upload/ 接口，
      // 避免单次 multipart 请求体超过 Nginx client_max_body_size 限制
      await Promise.all(
        pendingFiles.map((item) => {
          const options = item.isPhysicalEvidence
            ? { isPhysicalEvidence: true, physicalNote: item.physicalNote.trim() }
            : undefined
          return uploadEvidence(Number(caseId), item.file, options)
        })
      )
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
    if (currentCase?.is_demo) {
      setDemoDeleteToast(true)
      setTimeout(() => setDemoDeleteToast(false), 3000)
      return
    }
    try { await removeEvidence(evId) } catch {}
  }

  const isDemo = !!currentCase?.is_demo

  const imageCount = evidences.filter((ev) => !!ev.image).length
  const physicalCount = evidences.filter((ev) => ev.is_physical_evidence).length
  return (
    <div className="space-y-5 pb-8">
      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
        <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70"><Sparkles className="h-3.5 w-3.5 text-[#d8b967]" />智能材料整理</div>
            <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">证据管理</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">集中上传和管理订单、沟通记录、支付凭证与实物照片。工作流分析、历史运行和分析产物统一在分析页面查看。</p>
            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{currentCase?.title || "当前案件"}</span>
              {currentCase?.case_type && <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{disputeLabel(currentCase.case_type)}</span>}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 self-end">
            {[
              { label: "全部材料", value: evidences.length, icon: Layers3 },
              { label: "图片证据", value: imageCount, icon: Images },
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

      {isDemo && (
        <div className="flex items-center gap-3 rounded-xl border border-[#e5d9b5] bg-[#fef9ec] px-4 py-3 text-sm">
          <Lock className="h-4 w-4 shrink-0 text-[#9a7b2f]" />
          <span className="text-[#7a6425]">这是示例案件，已有证据不可删除，但仍可上传新证据或编辑案件信息。</span>
        </div>
      )}

      <section>
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
            <h2 className="mt-1 text-lg font-semibold text-foreground">{uploading ? "正在上传证据图片" : "拖拽图片到这里，或点击选择文件"}</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">支持批量上传 JPG、PNG、WEBP；实物照片可在下一步标记为纯物证。</p>
            <div className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#17231d] px-4 py-2 text-sm font-semibold text-white">选择图片<ChevronRight className="h-4 w-4" /></div>
          </div>
          <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => { handleFileSelect(e.target.files); e.currentTarget.value = "" }} />
        </div>
      </section>
      {loading && evidences.length === 0 && <div className="flex h-36 items-center justify-center"><Loader2 className="h-7 w-7 animate-spin text-secondary" /></div>}

      {evidences.length > 0 && (
        <div className="flex flex-wrap items-end justify-between gap-3 pt-2">
          <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">证据清单</p><h2 className="mt-1 text-xl font-semibold tracking-tight">已整理 {evidences.length} 份材料</h2></div>
          <div className="flex items-center gap-2 rounded-xl bg-muted/60 px-3 py-2 text-xs text-muted-foreground"><Images className="h-3.5 w-3.5" />点击图片可查看原图</div>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        {evidences.map((ev) => {
          return (
            <article key={ev.id} className="group/card rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_34px_rgba(31,45,38,.055)] transition-all hover:-translate-y-0.5 hover:border-secondary/25 hover:shadow-[0_18px_44px_rgba(31,45,38,.09)] sm:p-6">
              {/* Header: code + type + OCR + delete */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center rounded-lg bg-[#17231d] px-2.5 py-1 text-xs font-bold text-white">
                    {ev.code}
                  </span>
                  <PillTag label={ev.evidence_type || "未知"} variant="default" />
                  {ev.is_physical_evidence && (
                    <PillTag label="物证" variant="warning" />
                  )}
                </div>
                <button
                  onClick={() => handleDelete(ev.id)}
                  disabled={isDemo}
                  className={cn(
                    "rounded-xl border border-transparent p-2 transition-colors",
                    isDemo
                      ? "cursor-not-allowed text-muted-foreground/40"
                      : "text-muted-foreground hover:border-destructive/15 hover:bg-destructive/8 hover:text-destructive"
                  )}
                  aria-label={isDemo ? "示例案件证据不可删除" : `删除证据 ${ev.code}`}
                  title={isDemo ? "示例案件证据不可删除" : undefined}
                >
                  {isDemo ? <Lock className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
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
      {/* Demo delete toast */}
      {demoDeleteToast && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl border border-[#e5d9b5] bg-[#fef9ec] px-5 py-3 text-sm font-medium text-[#7a6425] shadow-[0_10px_40px_rgba(120,90,30,.12)]">
          示例案件的证据不可删除
        </div>
      )}
    </div>
  )
}
