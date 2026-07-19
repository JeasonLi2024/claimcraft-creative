// 隐私检查与打码页（编排器）。
// 职责：加载文本风险 + 图片证据 → 派生阶段状态 → 组合隐私组件。
// 保持现有轻量模型（无异步扫描任务/画布编辑器/双轨导出，见 privacy-masking-upgrade-design 阶段 A）。
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router"
import { AlertTriangle, Loader2, Shield, X } from "lucide-react"

import { useCaseStore } from "@/stores/case-store"
import { useStatus } from "@/composables/useStatus"
import { privacyApi } from "@/lib/privacy-api"
import { cn } from "@/lib/utils"
import {
  countHighRisk,
  derivePrivacyStage,
  type TextRisk,
} from "@/types/privacy"

import { PrivacyStageHero } from "@/components/privacy/PrivacyStageHero"
import { PrivacyStatusBar } from "@/components/privacy/PrivacyStatusBar"
import { PrivacyPolicyCard } from "@/components/privacy/PrivacyPolicyCard"
import { TextRiskList } from "@/components/privacy/TextRiskList"
import { ImageReviewGrid } from "@/components/privacy/ImageReviewGrid"
import { PrivacyExportImpact } from "@/components/privacy/PrivacyExportImpact"
import { PrivacyCompletionPanel } from "@/components/privacy/PrivacyCompletionPanel"

export default function MaskPage() {
  const { caseId: caseIdParam } = useParams<{ caseId: string }>()
  const caseId = Number(caseIdParam)
  const navigate = useNavigate()

  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchEvidences = useCaseStore((s) => s.fetchEvidences)
  const evidences = useCaseStore((s) => s.evidences)
  const currentCase = useCaseStore((s) => s.currentCase)
  const { disputeLabel } = useStatus()

  const [textRisks, setTextRisks] = useState<TextRisk[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [scanning, setScanning] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [lightbox, setLightbox] = useState<{ src: string; label: string } | null>(null)

  const mainRef = useRef<HTMLDivElement>(null)

  // ---------- 加载 ----------

  const loadRisks = useCallback(async () => {
    if (!Number.isFinite(caseId)) return
    setScanning(true)
    try {
      setTextRisks(await privacyApi.getTextRisks(caseId))
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载文本风险失败")
    } finally {
      setScanning(false)
    }
  }, [caseId])

  useEffect(() => {
    if (!Number.isFinite(caseId)) return
    let cancelled = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        await Promise.all([fetchCaseDetail(caseId), fetchEvidences(caseId)])
        const risks = await privacyApi.getTextRisks(caseId)
        if (!cancelled) setTextRisks(risks)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载隐私检查失败")
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [caseId, fetchCaseDetail, fetchEvidences])

  // ---------- 派生 ----------

  const imageEvidences = useMemo(() => evidences.filter((e) => e.image), [evidences])
  const imageTotal = imageEvidences.length
  const imageDone = imageEvidences.filter((e) => e.mask_status === "done").length
  const imageFailed = imageEvidences.filter((e) => e.mask_status === "failed").length
  const imageUndone = imageTotal - imageDone
  const highRiskCount = useMemo(() => countHighRisk(textRisks), [textRisks])

  const stage = useMemo(
    () =>
      derivePrivacyStage({
        textRiskCount: textRisks.length,
        imageTotal,
        imageDone,
        imageFailed,
      }),
    [textRisks.length, imageTotal, imageDone, imageFailed],
  )

  const progressText = imageTotal > 0 ? `已处理 ${imageDone} / ${imageTotal} 张。` : undefined

  // 灯箱：支持 Escape 关闭（可访问性 §14.5）
  useEffect(() => {
    if (!lightbox) return
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setLightbox(null)
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [lightbox])

  // ---------- 图片打码 ----------

  const handleRemask = useCallback(
    async (evidenceId: number) => {
      if (busyId != null) return
      setBusyId(evidenceId)
      setError(null)
      try {
        await privacyApi.remaskImage(evidenceId)
      } catch (e) {
        // 后端失败时会把 mask_status 置为 failed，并在 422 响应体带可读 detail。
        const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        setError(detail || (e instanceof Error ? e.message : "单张图片打码失败"))
      } finally {
        // 无论成败都刷新证据，让失败状态也能立即反映到卡片上。
        await fetchEvidences(caseId).catch(() => {})
        setBusyId(null)
      }
    },
    [busyId, caseId, fetchEvidences],
  )

  const handleMaskAll = useCallback(async () => {
    if (bulkBusy) return
    setBulkBusy(true)
    setError(null)
    try {
      await privacyApi.maskAllImages(caseId)
      await fetchEvidences(caseId)
    } catch (e) {
      setError(e instanceof Error ? e.message : "批量打码失败")
    } finally {
      setBulkBusy(false)
    }
  }, [bulkBusy, caseId, fetchEvidences])

  const handleStagePrimary = useCallback(() => {
    if (stage === "empty") {
      void loadRisks()
      return
    }
    if (stage === "masked_done") {
      navigate(`/cases/${caseId}/export`)
      return
    }
    // review_required / partial_failed：有未完成图片则批量打码，否则滚动到清单
    if (imageUndone > 0 || imageFailed > 0) {
      void handleMaskAll()
    } else {
      mainRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
    }
  }, [stage, caseId, imageUndone, imageFailed, loadRisks, handleMaskAll, navigate])

  // ---------- 完成条件 ----------

  const completionConditions = useMemo(
    () => [
      {
        label: imageTotal === 0 ? "无图片证据需打码" : "所有图片已完成打码",
        met: imageTotal === 0 || (imageDone === imageTotal && imageFailed === 0),
      },
      { label: "没有处理失败的图片", met: imageFailed === 0 },
    ],
    [imageTotal, imageDone, imageFailed],
  )

  // ---------- 渲染 ----------

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-secondary" aria-hidden="true" />
      </div>
    )
  }

  return (
    <div className="space-y-5 pb-8">
      <PrivacyStageHero
        caseTitle={currentCase?.title || "当前案件"}
        caseTypeLabel={currentCase?.case_type ? disputeLabel(currentCase.case_type) : undefined}
        pendingCount={textRisks.length + imageUndone}
        maskedImageCount={imageDone}
        highRiskCount={highRiskCount}
      />

      {error && (
        <div role="alert" className="flex items-center gap-2 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {error}
        </div>
      )}

      <PrivacyStatusBar stage={stage} progressText={progressText} onPrimary={handleStagePrimary} />

      <PrivacyPolicyCard onRescan={() => void loadRisks()} scanning={scanning} />

      <section ref={mainRef} className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-5">
          {/* 文本风险清单 */}
          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
            <div className="mb-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">文本检查</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight">
                {textRisks.length > 0 ? `发现 ${textRisks.length} 个可能的敏感项` : "文本风险清单"}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">自动建议，待人工复核；仅显示脱敏预览，不展示原文。</p>
            </div>
            <TextRiskList risks={textRisks} />
          </section>

          {/* 图片复核清单 */}
          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">图片检查</p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight">逐张复核并生成打码版本</h2>
                <p className="mt-1 text-sm text-muted-foreground">对每张图片可单独打码或重试；点击图片查看原图与打码后对比。</p>
              </div>
              {imageUndone > 0 && (
                <button
                  type="button"
                  onClick={() => void handleMaskAll()}
                  disabled={bulkBusy}
                  className="inline-flex min-h-[40px] items-center gap-2 rounded-xl bg-[#17231d] px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {bulkBusy ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Shield className="h-4 w-4" aria-hidden="true" />
                  )}
                  {bulkBusy ? "处理中..." : `打码全部待处理图片（${imageUndone}）`}
                </button>
              )}
            </div>
            <ImageReviewGrid
              images={imageEvidences}
              busyId={busyId}
              onRemask={(id) => void handleRemask(id)}
              onPreview={(src, label) => setLightbox({ src, label })}
            />
          </section>
        </div>

        {/* 右侧栏 */}
        <aside className="space-y-5 xl:sticky xl:top-5">
          <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_32px_rgba(31,45,38,.06)]">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">当前检查概览</p>
            <div className="mt-4 space-y-3 border-y border-border py-4 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">图片打码进度</span>
                <span className="font-medium">{imageTotal > 0 ? `${imageDone} / ${imageTotal}` : "无图片"}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">待处理图片</span>
                <span className="font-medium">{imageUndone}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">处理失败</span>
                <span className={cn("font-medium", imageFailed > 0 && "text-red-600")}>{imageFailed}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">高风险文本项</span>
                <span className={cn("font-medium", highRiskCount > 0 && "text-red-600")}>{highRiskCount}</span>
              </div>
            </div>
          </section>

          <PrivacyExportImpact caseId={caseId} />
        </aside>
      </section>

      <PrivacyCompletionPanel
        caseId={caseId}
        conditions={completionConditions}
        highRiskTextCount={highRiskCount}
      />

      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
          onClick={() => setLightbox(null)}
          role="dialog"
          aria-modal="true"
          aria-label={lightbox.label}
        >
          <button
            type="button"
            onClick={() => setLightbox(null)}
            className="absolute right-4 top-4 rounded-xl bg-white/10 p-2 text-white hover:bg-white/20"
            aria-label="关闭图片预览"
          >
            <X className="h-6 w-6" aria-hidden="true" />
          </button>
          <figure className="flex max-h-[90vh] max-w-[90vw] flex-col items-center gap-3" onClick={(e) => e.stopPropagation()}>
            <img src={lightbox.src} alt={lightbox.label} className="max-h-[80vh] max-w-[90vw] rounded-xl object-contain" />
            <figcaption className="rounded-lg bg-white/10 px-3 py-1.5 text-xs text-white">{lightbox.label}</figcaption>
          </figure>
        </div>
      )}
    </div>
  )
}
