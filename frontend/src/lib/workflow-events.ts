// SSE 工作流事件类型定义 + 辅助函数
// 参考 spec 第 4 节 SSE 事件协议与第 6.4 节 Zustand Workflow Slice

// ---------- 节点相关常量 ----------

/** 工作流节点顺序（与后端 graph.py 保持一致） */
export const NODE_ORDER = [
  "preclassify",
  "ocr",
  "classify",
  "extract",
  "review",
  "evidence_chain",
  "complaint",
  "respond_complaint",
] as const

export type WorkflowNode = (typeof NODE_ORDER)[number]
export type EditableStage = WorkflowNode

/** 节点中文标签 */
export const NODE_LABELS: Record<WorkflowNode, string> = {
  preclassify: "预分类",
  ocr: "OCR 识别",
  classify: "分类",
  extract: "字段抽取",
  review: "人工审核",
  evidence_chain: "证据链",
  complaint: "投诉书",
  respond_complaint: "反证答辩书",
}

/** 投诉书语气标签 */
export const TONE_LABELS: Record<string, string> = {
  firm: "坚定",
  neutral: "中性",
  polite: "礼貌",
  strong: "强硬",
  restrained: "克制",
  legal: "法律严谨",
}

// ---------- 节点状态 ----------

export type NodeStatusValue =
  | "idle"
  | "running"
  | "paused"
  | "completed"
  | "error"
  | "skipped"

export interface NodeStatus {
  status: NodeStatusValue
  startedAt?: string
  completedAt?: string
  durationMs?: number
  products?: Record<string, unknown>
  error?: string
  progressStage?: string
  progressMessage?: string
}

export type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error"

// ---------- 暂停编辑 ----------

export type EditableScope = Partial<Record<"evidences" | "extracted_fields" | "timeline_nodes" | "document", string[]>>

export interface StageProducts {
  evidences?: EvidenceStageProduct[]
  extracted_fields?: ExtractFieldEdit[]
  timeline_nodes?: TimelineNodeEdit[]
  document?: DocumentStageEdit | null
}

export interface StagePauseData {
  paused_after: EditableStage
  editable_scope?: EditableScope
  stage_products?: StageProducts
  message?: string
}

export interface EvidenceMetaEdit {
  id: number
  evidence_id?: number
  evidence_category?: string
  ocr_summary?: string
}

export interface OcrTextEdit {
  id: number
  evidence_id?: number
  extracted_text: string
}

export interface ExtractFieldEdit {
  id: number
  evidence_id?: number
  evidence_code?: string
  confidence?: number
  field_name: string
  field_value: string
}

export interface TimelineNodeEdit {
  id: number
  datetime?: string
  event: string
  category?: string
  order?: number
  related_evidence_codes?: string
}

export interface EvidenceStageProduct extends EvidenceMetaEdit, Omit<OcrTextEdit, "id" | "evidence_id"> {
  code?: string
  description?: string
}

export interface DocumentStageEdit {
  id?: number
  title?: string
  content?: string
  tone?: string
  template_type?: string
}

export interface StageEdits {
  evidences?: Array<EvidenceMetaEdit | OcrTextEdit>
  extracted_fields?: ExtractFieldEdit[]
  timeline_nodes?: TimelineNodeEdit[]
  document?: DocumentStageEdit
}

export interface WorkflowStateResponse {
  case_id: number
  thread_id: string | null
  workflow_status: WorkflowReplay["workflow_status"]
  workflow_paused_after: string
  editable_scope: EditableScope
  stage_products: StageProducts
}

// ---------- 产物区块 ----------

export type ProductBlockType =
  | "preclassify"
  | "ocr"
  | "classify"
  | "extract"
  | "evidence_chain"
  | "complaint"
  | "respond_complaint"

export interface ProductBlock {
  id: string
  node: string
  type: ProductBlockType
  products: Record<string, unknown>
  completedAt: string
  collapsed: boolean
}

// ---------- HITL 校正 ----------

export interface ReviewField {
  evidence_id: number
  field_name: string
  current_value: string
  confidence: number
}

export interface ReviewInterruptData {
  event_id: number
  fields_to_review: ReviewField[]
  message: string
  resume_endpoint?: string
}

export interface Correction {
  evidence_id: number
  field_name: string
  corrected_value: string
}

// ---------- 工作流错误 ----------

export interface WorkflowError {
  message: string
  node?: string
  recoverable: boolean
}

// ---------- SSE 事件类型 ----------

export type EventType =
  | "workflow.start"
  | "workflow.heartbeat"
  | "workflow.pause_requested"
  | "workflow.paused"
  | "workflow.resumed"
  | "workflow.cancelled"
  | "workflow.complete"
  | "workflow.error"
  | "workflow.waiting_review"
  | "node.start"
  | "node.progress"
  | "node.complete"
  | "node.error"
  | "complaint.token"
  | "complaint.done"
  | "review.interrupt"
  | "review.resumed"
  | "review.skipped"

export interface WorkflowReplay {
  case_id: number
  thread_id: string | null
  workflow_status: "idle" | "running" | "pausing" | "paused" | "waiting_review" | "succeeded" | "failed"
  workflow_error: string
  paused_after?: string | null
  events: SSEEvent[]
  last_event_id: number
  history_available: boolean
}

/** SSE 事件通用结构（带 index signature 便于 reducer 读取 payload 字段） */
export interface SSEEvent {
  event_id: number
  event_type: EventType
  thread_id?: string
  timestamp?: string
  [key: string]: unknown
}

// ---------- 产物构造与摘要辅助函数 ----------

let blockIdCounter = 0

/** 根据节点名和产物构建 ProductBlock */
export function buildProductBlock(
  node: string,
  products: Record<string, unknown>,
): ProductBlock {
  blockIdCounter += 1
  return {
    id: `${node}-${blockIdCounter}`,
    node,
    type: node as ProductBlockType,
    products,
    completedAt: new Date().toISOString(),
    collapsed: false,
  }
}

/** 生成节点产物摘要字符串 */
export function summarizeProducts(
  node: string,
  products: Record<string, unknown>,
): string {
  if (!products) return ""
  switch (node) {
    case "preclassify": {
      const list = (products.evidence_preclassify_results as unknown[]) || []
      return `${list.length} 条证据已预分类`
    }
    case "ocr": {
      const list = (products.evidence_ocr_results as unknown[]) || []
      return `${list.length} 条证据已识别`
    }
    case "classify": {
      const list = (products.evidence_classify_results as unknown[]) || []
      return `${list.length} 条证据已分类`
    }
    case "extract": {
      const list = (products.evidence_extract_results as unknown[]) || []
      return `${list.length} 条证据已抽取字段`
    }
    case "evidence_chain": {
      const list = (products.evidence_chain as unknown[]) || []
      return `${list.length} 个时间线节点`
    }
    case "complaint":
      return "投诉书已生成"
    case "respond_complaint":
      return "反证答辩书已生成"
    default:
      return ""
  }
}
