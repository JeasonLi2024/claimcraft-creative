// 文书编辑器类型定义
// 对齐后端 DocumentVersion / paragraph_splitter / document_quality_service 模型
// 字段名保持 snake_case 以与后端 Pydantic 模型返回的 JSON 一致
// 对齐 spec.md Requirement: DocumentEditor Dual-Pane Layout / Task 4.3

// ===== 段落类型（对齐 ComplaintTemplate.paragraphs）=====

/** 段落类型：事实 / 依据 / 诉求 / 其他 */
export type ParagraphType = 'fact' | 'basis' | 'claim' | 'other'

/** 段落引用的证据来源区域 */
export interface SourceRegion {
  evidence_id?: number
  evidence_code?: string
  /** 区域坐标，0-1 归一化或 0-100 百分比 */
  x?: number
  y?: number
  width?: number
  height?: number
  text?: string
}

/** 法条引用 */
export interface LegalReference {
  law_name: string
  article_number: string
  text?: string
  source_url?: string
}

/** 段落：文书正文的最小编辑单元 */
export interface Paragraph {
  id: string
  content: string
  evidence_codes: string[]
  legal_references: LegalReference[]
  source_regions?: SourceRegion[]
  type?: ParagraphType
  /**
   * 创建此段落版本的来源类型，由前端依据 DocumentVersion.created_by_type 推断；
   * 若未关联版本，默认为 'ai'。
   */
  created_by_type?: 'user' | 'ai'
  /** 创建此段落的版本号（用于版本对比与回滚） */
  version?: number
  /** 创建时间 ISO 8601 */
  created_at?: string
}

// ===== 文书版本（对齐后端 DocumentVersion 模型）=====

export interface DocumentVersion {
  id: string
  document_id: string
  version: number
  content: string
  changelog?: string
  created_by_type: 'user' | 'ai'
  created_by_id?: string
  created_at: string
  workflow_version?: string
}

// ===== 文书详情 =====

/** 输入数据充分性等级（input-quality-guard Gate 3） */
export type DataSufficiencyLevel = 'sufficient' | 'sparse' | 'critically_sparse'

export interface DataSufficiency {
  score: number
  level: DataSufficiencyLevel
  missing_dimensions: string[]
}

export interface DocumentDetail {
  id: string
  run_id: number
  title: string
  template_type?: string
  paragraphs: Paragraph[]
  /** 当前版本号 */
  current_version: number
  /** 创建时间 ISO 8601 */
  created_at?: string
  /** 最后更新时间 ISO 8601 */
  updated_at?: string
  /** 输入数据充分性（Gate 3；null/缺省表示未评估或充分） */
  data_sufficiency?: DataSufficiency | null
}

// ===== 导出前质量门（对齐后端 document_quality_service.run_export_check）=====

export type ExportCheckSeverity = 'blocking' | 'warning' | 'info'

export interface ExportCheckIssue {
  code: string
  severity: ExportCheckSeverity
  message: string
  paragraph_id?: string
  details?: Record<string, unknown>
}

export interface ExportCheckResult {
  passed: boolean
  issues: ExportCheckIssue[]
  missing_elements: string[]
  checks_run: string[]
}

// ===== 段落重新生成响应 =====

export interface RegenerateParagraphResponse {
  document_id: number
  paragraph_id: string
  paragraph: Paragraph
  version: number
  changelog: string
}

// ===== 工具函数 =====

/** ParagraphType 中文标签 */
export const PARAGRAPH_TYPE_LABELS: Record<ParagraphType, string> = {
  fact: '事实',
  basis: '依据',
  claim: '诉求',
  other: '其他',
}

/** DocumentVersion.created_by_type 中文标签 */
export const CREATED_BY_TYPE_LABELS: Record<'user' | 'ai', string> = {
  user: '用户',
  ai: 'AI',
}

/** 必备要素完整性检查项 */
export const REQUIRED_ELEMENTS_LABELS: Record<string, string> = {
  fact_section: '事实段',
  basis_section: '依据段',
  claim_section: '诉求段',
}
