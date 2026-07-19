// 隐私检查与打码：类型定义 + 统一标签/样式映射。
// 对齐设计文档 §15.4：所有状态使用字面量联合类型，标签/图标/颜色集中映射，
// 禁止在页面内散落三元表达式；状态不只靠颜色表达（均带文字标签 / aria-label）。
import type { LucideIcon } from "lucide-react"
import {
  Clock,
  FileText,
  HelpCircle,
  IdCard,
  Image as ImageIcon,
  ListTree,
  Loader2,
  MapPin,
  Phone,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react"

// ===== 字面量联合 =====

/** 后端 mask_service 实际产出的敏感类型（不含未实现的「姓名」等）。 */
export type SensitiveType = "id_card" | "phone" | "address" | "unknown"
export type SensitiveRiskLevel = "high" | "medium" | "low"
export type PrivacySourceType =
  | "evidence"
  | "ocr"
  | "ocr_summary"
  | "extracted_field"
  | "timeline"
  | "document"
export type ImageMaskStatus = "none" | "pending" | "done" | "failed"

/** 文本风险项（对齐后端 mask_case_sensitive_info 结果项）。默认只含脱敏预览，不含原文。 */
export interface TextRisk {
  evidence_code: string | null
  source_type: PrivacySourceType
  source_label: string
  source_id: number | null
  type: SensitiveType
  types?: SensitiveType[]
  risk_level: SensitiveRiskLevel
  masked: string
}

// ===== 映射 =====

export const TYPE_META: Record<SensitiveType, { label: string; icon: LucideIcon }> = {
  id_card: { label: "身份证号", icon: IdCard },
  phone: { label: "手机号", icon: Phone },
  address: { label: "地址", icon: MapPin },
  unknown: { label: "待人工确认", icon: HelpCircle },
}

export const RISK_META: Record<
  SensitiveRiskLevel,
  { label: string; badgeClass: string; dotClass: string }
> = {
  high: {
    label: "高风险",
    badgeClass: "border-red-200 bg-red-50 text-red-700",
    dotClass: "bg-red-500",
  },
  medium: {
    label: "中风险",
    badgeClass: "border-[#e5d9b5] bg-[#fef9ec] text-[#7a6425]",
    dotClass: "bg-[#c99a2e]",
  },
  low: {
    label: "低风险",
    badgeClass: "border-border bg-muted text-muted-foreground",
    dotClass: "bg-slate-400",
  },
}

export const SOURCE_META: Record<
  PrivacySourceType,
  { label: string; icon: LucideIcon; order: number }
> = {
  document: { label: "最新文书", icon: FileText, order: 0 },
  evidence: { label: "证据材料", icon: ImageIcon, order: 1 },
  ocr: { label: "OCR 文本", icon: ScanSearch, order: 2 },
  ocr_summary: { label: "OCR 摘要", icon: ScanSearch, order: 3 },
  extracted_field: { label: "抽取字段", icon: ListTree, order: 4 },
  timeline: { label: "时间线", icon: Clock, order: 5 },
}

export const MASK_STATUS_META: Record<
  ImageMaskStatus,
  { label: string; icon: LucideIcon; badgeClass: string; spin?: boolean }
> = {
  none: {
    label: "待处理",
    icon: ScanSearch,
    badgeClass: "border-border bg-muted text-muted-foreground",
  },
  pending: {
    label: "处理中",
    icon: Loader2,
    badgeClass: "border-[#e5d9b5] bg-[#fef9ec] text-[#7a6425]",
    spin: true,
  },
  done: {
    label: "已打码",
    icon: ShieldCheck,
    badgeClass: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  failed: {
    label: "处理失败",
    icon: TriangleAlert,
    badgeClass: "border-red-200 bg-red-50 text-red-700",
  },
}

// ===== 页面阶段状态（设计文档 §13.4，按现有轻量数据派生） =====

export type PrivacyStage =
  | "empty"
  | "review_required"
  | "masked_done"
  | "partial_failed"

export const STAGE_META: Record<
  PrivacyStage,
  {
    title: string
    description: string
    icon: LucideIcon
    tone: "neutral" | "warning" | "success" | "danger"
    actionLabel: string
  }
> = {
  empty: {
    title: "未发现需处理的图片",
    description: "自动识别未发现待打码图片，请仍在分享前核对原图与最新文书。",
    icon: ScanSearch,
    tone: "neutral",
    actionLabel: "重新扫描",
  },
  review_required: {
    title: "已生成自动建议，待人工复核",
    description: "自动识别不能替代人工检查，请逐项核对文本风险并处理图片。",
    icon: TriangleAlert,
    tone: "warning",
    actionLabel: "继续复核",
  },
  masked_done: {
    title: "图片打码已完成",
    description: "当前图片均已生成打码版本，请核对后再对外分享。",
    icon: ShieldCheck,
    tone: "success",
    actionLabel: "前往导出",
  },
  partial_failed: {
    title: "部分图片处理失败",
    description: "失败项不能视为已安全处理，请查看原因并重试或人工处理原图。",
    icon: TriangleAlert,
    tone: "danger",
    actionLabel: "重试失败项",
  },
}

export interface PrivacyStageInput {
  textRiskCount: number
  imageTotal: number
  imageDone: number
  imageFailed: number
}

/** 由现有数据派生页面阶段状态（纯函数，便于测试）。 */
export function derivePrivacyStage(input: PrivacyStageInput): PrivacyStage {
  const { textRiskCount, imageTotal, imageDone, imageFailed } = input
  if (imageFailed > 0) return "partial_failed"
  if (imageTotal === 0 && textRiskCount === 0) return "empty"
  if (imageTotal > 0 && imageDone < imageTotal) return "review_required"
  if (textRiskCount > 0) return "review_required"
  return "masked_done"
}

/** 高风险文本项数量（用于 Hero 指标与完成条件）。 */
export function countHighRisk(risks: TextRisk[]): number {
  return risks.filter((r) => r.risk_level === "high").length
}
