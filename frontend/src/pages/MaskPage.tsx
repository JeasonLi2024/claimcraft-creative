import { useEffect, useState } from "react"
import { useParams } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useStatus } from "@/composables/useStatus"
import PillTag from "@/components/PillTag"
import { cn } from "@/lib/utils"
import {
  Images, LockKeyhole, ScanFace, Shield,
  ShieldCheck, Sparkles, X,
} from "lucide-react"

const TYPE_STYLES: Record<string, { variant: "warning" | "danger" | "success" | "default"; label: string }> = {
  phone: { variant: "warning", label: "手机号" },
  id_card: { variant: "danger", label: "身份证号" },
  address: { variant: "success", label: "地址" },
  name: { variant: "default", label: "姓名" },
}

export default function MaskPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const fetchCaseDetail = useCaseStore((state) => state.fetchCaseDetail)
  const fetchEvidences = useCaseStore((state) => state.fetchEvidences)
  const fetchMaskResults = useCaseStore((state) => state.fetchMaskResults)
  const maskImages = useCaseStore((state) => state.maskImages)
  const maskResults = useCaseStore((state) => state.maskResults)
  const evidences = useCaseStore((state) => state.evidences)
  const currentCase = useCaseStore((state) => state.currentCase)
  const error = useCaseStore((state) => state.error)
  const { disputeLabel } = useStatus()
  const [maskingImages, setMaskingImages] = useState(false)
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)

  useEffect(() => {
    if (!caseId) return
    const id = Number(caseId)
    fetchCaseDetail(id)
    fetchEvidences(id)
    fetchMaskResults(id)
  }, [caseId, fetchCaseDetail, fetchEvidences, fetchMaskResults])

  async function handleMaskAllImages() {
    if (!caseId || maskingImages) return
    setMaskingImages(true)
    try {
      await maskImages(Number(caseId))
      await fetchMaskResults(Number(caseId))
    } catch {} finally {
      setMaskingImages(false)
    }
  }

  const imageEvidences = evidences.filter((evidence) => evidence.image)
  const maskedImages = imageEvidences.filter((evidence) => evidence.mask_status === "done").length
  const typeCount = new Set(maskResults.map((result) => result.type)).size

  return (
    <div className="space-y-5 pb-8">
      <section className="relative overflow-hidden rounded-[28px] bg-[#17231d] text-white shadow-[0_22px_65px_rgba(23,35,29,.14)]">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#6f9f83]/20 blur-3xl" />
        <div className="relative grid gap-7 p-6 sm:p-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-white/70"><Sparkles className="h-3.5 w-3.5 text-[#d8b967]" />敏感信息保护</div>
            <h1 className="mt-5 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">隐私打码</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">识别文本和图片中的姓名、手机号、身份证号与地址，在材料提交前集中检查脱敏效果。</p>
            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{currentCase?.title || "当前案件"}</span>
              {currentCase?.case_type && <span className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-white/65">{disputeLabel(currentCase.case_type)}</span>}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 self-end">
            {[
              { label: "敏感字段", value: maskResults.length, icon: ScanFace },
              { label: "涉及类型", value: typeCount, icon: LockKeyhole },
              { label: "图片已处理", value: maskedImages, icon: ShieldCheck },
            ].map((item) => (
              <div key={item.label} className="rounded-2xl border border-white/10 bg-white/8 p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between text-white/45"><span className="text-xs">{item.label}</span><item.icon className="h-4 w-4" /></div>
                <div className="mt-2 text-2xl font-semibold">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {error && <div role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <section className="grid items-stretch gap-5 xl:grid-cols-[minmax(0,1fr)_310px]">
        <div className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-secondary text-white"><ShieldCheck className="h-5 w-5" /></span>
              <div><h2 className="font-semibold">文本脱敏预览</h2><p className="text-sm text-muted-foreground">接口仅下发脱敏结果，原始敏感内容保留在案件证据中</p></div>
            </div>
            <span className="rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-secondary">安全预览</span>
          </div>
        </div>
        <div className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_32px_rgba(31,45,38,.05)]">
          <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-secondary"><ShieldCheck className="h-5 w-5" /></span><div><h2 className="text-sm font-semibold">提交前检查</h2><p className="text-xs text-muted-foreground">避免泄露个人隐私</p></div></div>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">重点核对身份证号码、联系电话、详细住址和图片中的账号信息，确认打码后再导出。</p>
        </div>
      </section>

      <section className="overflow-hidden rounded-[24px] border border-border bg-card shadow-[0_12px_36px_rgba(31,45,38,.05)]">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border p-5 sm:p-6">
          <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">文本检查</p><h2 className="mt-1 text-xl font-semibold tracking-tight">识别到 {maskResults.length} 处敏感信息</h2></div>
          <span className="rounded-full bg-muted px-3 py-1.5 text-xs text-muted-foreground">原始内容不下发</span>
        </div>
        {maskResults.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="bg-muted/40"><th className="px-5 py-3 text-left font-medium text-muted-foreground">证据编号</th><th className="px-5 py-3 text-left font-medium text-muted-foreground">信息类型</th><th className="px-5 py-3 text-left font-medium text-muted-foreground">脱敏结果</th></tr></thead>
              <tbody>{maskResults.map((result, index) => <tr key={`${result.evidence_code}-${index}`} className="border-t border-border"><td className="px-5 py-3"><span className="rounded-lg bg-[#17231d] px-2.5 py-1 text-xs font-bold text-white">{result.evidence_code}</span></td><td className="px-5 py-3"><PillTag label={TYPE_STYLES[result.type]?.label || "待人工确认"} variant={TYPE_STYLES[result.type]?.variant || "default"} /></td><td className="px-5 py-3 font-mono text-xs text-muted-foreground">{result.masked}</td></tr>)}</tbody>
            </table>
          </div>
        ) : <div className="px-6 py-12 text-center"><ScanFace className="mx-auto h-7 w-7 text-muted-foreground" /><p className="mt-3 text-sm text-muted-foreground">暂未识别到需要脱敏的文本信息</p></div>}
      </section>

      <section className="rounded-[24px] border border-border bg-card p-5 shadow-[0_12px_36px_rgba(31,45,38,.05)] sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary">图片检查</p><h2 className="mt-1 text-xl font-semibold tracking-tight">图片脱敏对比</h2><p className="mt-1 text-sm text-muted-foreground">并排查看原图与处理结果，点击图片可放大。</p></div>
          {imageEvidences.length > 0 && <button type="button" onClick={handleMaskAllImages} disabled={maskingImages} className="inline-flex items-center gap-2 rounded-xl bg-[#17231d] px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"><Shield className={cn("h-4 w-4", maskingImages && "animate-pulse")} />{maskingImages ? "处理中..." : "一键打码所有图片"}</button>}
        </div>
        {imageEvidences.length > 0 ? <div className="mt-5 grid gap-5 lg:grid-cols-2">{imageEvidences.map((evidence) => <article key={evidence.id} className="overflow-hidden rounded-2xl border border-border"><div className="flex items-center justify-between bg-muted/45 px-4 py-3"><span className="text-xs font-bold text-secondary">{evidence.code}</span><PillTag label={evidence.mask_status === "done" ? "已打码" : evidence.mask_status === "pending" ? "处理中" : evidence.mask_status === "failed" ? "处理失败" : "待处理"} variant={evidence.mask_status === "done" ? "success" : evidence.mask_status === "failed" ? "danger" : evidence.mask_status === "pending" ? "warning" : "default"} /></div><div className="grid grid-cols-2 gap-px bg-border"><button type="button" className="relative bg-white text-left" onClick={() => evidence.image && setLightboxSrc(evidence.image)}><img src={evidence.image || ""} alt={`${evidence.code} 原图`} className="h-44 w-full object-cover" /><span className="absolute bottom-2 left-2 rounded-md bg-black/55 px-2 py-1 text-[10px] text-white">原图</span></button><button type="button" disabled={!evidence.masked_image} className="relative bg-white text-left disabled:cursor-not-allowed" onClick={() => evidence.masked_image && setLightboxSrc(evidence.masked_image)}>{evidence.masked_image ? <img src={evidence.masked_image} alt={`${evidence.code} 打码后`} className="h-44 w-full object-cover" /> : <span className="flex h-44 items-center justify-center px-4 text-center text-xs text-muted-foreground">{evidence.mask_status === "failed" ? "自动定位失败，请人工处理原图" : "尚未生成打码图"}</span>}<span className="absolute bottom-2 left-2 rounded-md bg-black/55 px-2 py-1 text-[10px] text-white">打码后</span></button></div></article>)}</div> : <div className="mt-5 rounded-2xl bg-muted/55 px-6 py-12 text-center"><Images className="mx-auto h-7 w-7 text-muted-foreground" /><p className="mt-3 text-sm text-muted-foreground">当前案件暂无图片证据</p></div>}
      </section>

      {lightboxSrc && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm" onClick={() => setLightboxSrc(null)}><button className="absolute right-4 top-4 rounded-xl bg-white/10 p-2 text-white hover:bg-white/20" aria-label="关闭图片预览"><X className="h-6 w-6" /></button><img src={lightboxSrc} alt="脱敏图片预览" className="max-h-[90vh] max-w-[90vw] rounded-xl object-contain" /></div>}
    </div>
  )
}
