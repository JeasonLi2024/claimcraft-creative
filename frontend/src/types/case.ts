export interface Case {
  id: number
  title: string
  description: string
  dispute_type: string
  status: 'draft' | 'processing' | 'submitted' | 'closed' | 'cancelled'
  owner: number
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
  dispute_type: string
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
  created_at: string
}

export interface TimelineNode {
  id: number
  case: number
  datetime: string
  event: string
  auto_generated: boolean
  related_evidence_codes: string
  sort_order: number
}

export interface ComplaintData {
  title: string
  content: string
  template_type: string
}

export interface MaskResult {
  evidence_code: string
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
