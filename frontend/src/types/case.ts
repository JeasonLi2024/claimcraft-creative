import type { UserSummary } from "./auth"

export type CaseMode = 'complain' | 'respond'

export interface Case {
  id: number
  title: string
  description: string
  case_type: string
  case_mode?: CaseMode
  status: 'draft' | 'processing' | 'submitted' | 'closed' | 'cancelled'
  owner: UserSummary
  evidence_count: number
  timeline_count: number
  template_count: number
  image_evidence_count: number
  extracted_field_count: number
  created_at: string
  updated_at: string
}

export interface CaseCreateDTO {
  title: string
  description: string
  case_type: string
  case_mode?: CaseMode
}

export interface Evidence {
  id: number
  case: number
  code: string
  evidence_type: string
  description: string
  source_time: string
  image: string | null
  extracted_text: string | null
  ocr_status: 'pending' | 'done' | 'failed' | null
  mask_status: 'none' | 'pending' | 'done' | null
  masked_image: string | null
  // v9 新增：视觉预分类+摘要字段
  evidence_category: string  // chat_screenshot/product_order/logistics_tracking/payment_record/invoice/other
  ocr_summary: string        // 100-200字摘要，由 Captioner 生成
  // v10 新增：纯物证图片支持
  is_physical_evidence: boolean  // 是否为纯物证图片（无文字内容，跳过 OCR）
  physical_note: string          // 用户提供的物证说明
  created_at: string
}

export interface TimelineNode {
  id: number
  case: number
  datetime: string
  event: string
  auto_generated: boolean
  related_evidence_codes: string
  category: string
  order: number
}

export interface ComplaintData {
  title: string
  content: string
  template_type: string
  tone?: string
}

export interface RespondData {
  title: string
  content: string
  template_type: string
  tone?: string
}

export interface MaskResult {
  evidence_code: string
  type: string
  original: string
  masked: string
}

export interface StatusLog {
  id: number
  case: number
  from_status: string
  to_status: string
  remark: string
  created_at: string | null
  timestamp: string | null
}

export interface ExtractedField {
  id: number
  evidence: number
  field_name: string
  field_value: string
  confidence: number | null
  // v9 新增：字段分类（订单信息/支付信息/物流信息/发票信息/联系信息/时间信息/其他）
  field_category: string
  // v9 新增：源 OCR 文本 MD5，用于缓存比对
  source_hash: string
}

export interface CasePreset {
  id: number
  name: string
  description: string
  case_type: string
}

export interface DashboardStats {
  case_total: number
  evidence_total: number
  extracted_field_total: number
  case_type_distribution: Array<{ case_type: string; count: number }>
  status_distribution: Array<{ status: string; count: number }>
  cases_recent_30days: Array<{ day: string; count: number }>
  status_transitions: Array<{ to_status: string; count: number }>
}
