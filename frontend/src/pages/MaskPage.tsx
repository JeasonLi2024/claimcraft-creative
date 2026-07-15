import { useState, useEffect } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useStatus } from "@/composables/useStatus"
import PillTag from "@/components/PillTag"
import EmptyState from "@/components/EmptyState"
import { cn } from "@/lib/utils"
import { Shield, Loader2, Eye, EyeOff, RefreshCw, X } from "lucide-react"

const TYPE_STYLES: Record<string, { variant: "warning" | "danger" | "success" | "default"; label: string }> = {
  phone: { variant: "warning", label: "手机号" },
  id_card: { variant: "danger", label: "身份证号" },
  address: { variant: "success", label: "地址" },
  name: { variant: "default", label: "姓名" },
}

export default function MaskPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((s) => s.fetchCaseDetail)
  const fetchMaskResults = useCaseStore((s) => s.fetchMaskResults)
  const maskImages = useCaseStore((s) => s.maskImages)
  const toggleMasked = useCaseStore((s) => s.toggleMasked)
  const maskResults = useCaseStore((s) => s.maskResults)
  const evidences = useCaseStore((s) => s.evidences)
  const masked = useCaseStore((s) => s.masked)
  const loading = useCaseStore((s) => s.loading)
  const error = useCaseStore((s) => s.error)

  const [maskingImages, setMaskingImages] = useState(false)
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)

  useEffect(() => {
    if (caseId) {
      fetchCaseDetail(Number(caseId))
      fetchMaskResults(Number(caseId))
    }
  }, [caseId])

  async function handleMaskAllImages() {
    if (!caseId) return
    setMaskingImages(true)
    try {
      await maskImages(Number(caseId))
      await fetchMaskResults(Number(caseId))
    } catch {}
    finally { setMaskingImages(false) }
  }

  const imageEvidences = evidences.filter((ev) => ev.image)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">隐私打码</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          自动识别并遮挡敏感信息（手机号、身份证号、地址等）
        </p>
      </div>

      {/* Text mask toggle */}
      <div className="flex items-center justify-between rounded-2xl border border-border/50 bg-card p-4 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
        <div className="flex items-center gap-3">
          {masked ? <EyeOff className="h-5 w-5 text-primary" /> : <Eye className="h-5 w-5 text-muted-foreground" />}
          <span className="text-sm font-medium text-foreground">文本脱敏</span>
          <span className="text-xs text-muted-foreground">开启后显示打码后内容</span>
        </div>
        <button
          onClick={toggleMasked}
          className={cn(
            "relative h-6 w-11 rounded-full transition-colors",
            masked ? "bg-secondary" : "bg-border"
          )}
        >
          <div className={cn(
            "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform",
            masked ? "left-[22px]" : "left-0.5"
          )} />
        </button>
      </div>

      {/* Mask results table */}
      {maskResults.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-border/50 bg-card shadow-[0_10px_30px_rgba(20,35,90,.04)]">
          <div className="p-4">
            <h3 className="text-sm font-semibold text-foreground">文本打码结果</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y border-border/50 bg-muted/30">
                <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">证据编号</th>
                <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">类型</th>
                <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">{masked ? "打码后" : "原文"}</th>
              </tr>
            </thead>
            <tbody>
              {maskResults.map((r, i) => (
                <tr key={i} className={cn("border-b border-border/30", i % 2 === 0 && "bg-muted/10")}>
                  <td className="px-4 py-2.5">
                    <span className="rounded-lg bg-gradient-to-r from-[#2f6bff]/10 to-[#11b981]/10 px-2 py-0.5 text-xs font-bold text-primary">
                      {r.evidence_code}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <PillTag label={TYPE_STYLES[r.type]?.label || "未知"} variant={TYPE_STYLES[r.type]?.variant || "default"} />
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                    {masked ? r.masked : r.original}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Image mask section */}
      <div className="rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-foreground">图片脱敏</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">对图片中的敏感信息进行遮挡处理</p>
          </div>
          {imageEvidences.length > 0 && (
            <button
              onClick={handleMaskAllImages}
              disabled={maskingImages}
              className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              <Shield className={cn("h-4 w-4", maskingImages && "animate-spin")} />
              {maskingImages ? "处理中..." : "一键打码所有图片"}
            </button>
          )}
        </div>

        {imageEvidences.length > 0 ? (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {imageEvidences.map((ev) => (
              <div key={ev.id} className="overflow-hidden rounded-xl border border-border/50">
                <div className="flex items-center justify-between bg-muted/30 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-primary">{ev.code}</span>
                    {ev.mask_status === "done" && <PillTag label="已打码" variant="success" />}
                    {ev.mask_status === "pending" && <PillTag label="处理中" variant="warning" />}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-0.5">
                  <div
                    className="cursor-pointer bg-muted/20"
                    onClick={() => ev.image && setLightboxSrc(ev.image)}
                  >
                    <img src={ev.image || ""} alt="原图" className="h-32 w-full object-cover" />
                    <div className="px-2 py-1 text-center text-[10px] text-muted-foreground">原图</div>
                  </div>
                  <div
                    className="cursor-pointer bg-muted/20"
                    onClick={() => ev.masked_image && setLightboxSrc(ev.masked_image)}
                  >
                    <img src={ev.masked_image || ev.image || ""} alt="打码后" className="h-32 w-full object-cover" />
                    <div className="px-2 py-1 text-center text-[10px] text-muted-foreground">打码后</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-center text-sm text-muted-foreground">暂无图片证据</p>
        )}
      </div>

      {error && <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      {/* Lightbox */}
      {lightboxSrc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" onClick={() => setLightboxSrc(null)}>
          <button className="absolute right-4 top-4 rounded-lg bg-white/10 p-2 text-white hover:bg-white/20">
            <X className="h-6 w-6" />
          </button>
          <img src={lightboxSrc} alt="大图" className="max-h-[90vh] max-w-[90vw] rounded-xl object-contain" />
        </div>
      )}
    </div>
  )
}
