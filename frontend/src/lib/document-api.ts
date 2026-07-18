// 文书 API 客户端扩展
// 对齐 spec.md Requirement: DocumentEditor Dual-Pane Layout / Task 4.3.10
//
// 端点（后端均已实现）：
//   POST /api/workflow-runs/{run_id}/documents/{document_id}/paragraphs/{paragraph_id}/regenerate/
//   POST /api/workflow-runs/{run_id}/documents/{document_id}/export-check/
//        → 返回 {passed, issues, missing_elements}
//   GET  /api/workflow-runs/{run_id}/documents/{document_id}/versions/
//   POST /api/workflow-runs/{run_id}/documents/{document_id}/versions/{version}/rollback/
//   GET  /api/workflow-runs/{run_id}/documents/{document_id}/
//
// 各方法仍保留 try/catch 降级：端点缺失（404/405）时回退到 artifact 或空数组，
// 使前端在后端灰度未覆盖时不至于崩溃。
// 全文重新生成通过 workflowRunApi.retryRun。

import apiClient from "./api-client"
import type {
  DocumentDetail,
  DocumentVersion,
  ExportCheckResult,
  Paragraph,
  RegenerateParagraphResponse,
} from "@/types/document"
import type { WorkflowArtifact } from "@/types/workflow"

// ---------- 错误类型 ----------

export class DocumentApiError extends Error {
  /** 错误 code（如 NOT_IMPLEMENTED / NETWORK_ERROR / SERVER_ERROR） */
  code: string
  /** 是否为「后端尚未实现」类错误（前端可降级处理） */
  notImplemented: boolean

  constructor(message: string, code: string, notImplemented = false) {
    super(message)
    this.name = "DocumentApiError"
    this.code = code
    this.notImplemented = notImplemented
  }
}

// ---------- 工具：从 axios 错误提取可读消息 ----------

function describeError(err: unknown, fallback: string): string {
  if (err && typeof err === "object" && "response" in err) {
    const resp = (err as { response?: { status?: number; data?: unknown } }).response
    const status = resp?.status
    const data = resp?.data
    if (typeof data === "object" && data !== null) {
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === "string") return detail
    }
    if (status === 404) return "文书不存在或未归属此运行"
    if (status === 403) return "无权访问此文书"
    if (status && status >= 500) return `服务器错误 (${status})`
    if (status && status >= 400) return `请求失败 (${status})`
  }
  if (err instanceof Error) return err.message || fallback
  return fallback
}

function isNotImplemented(err: unknown): boolean {
  if (err && typeof err === "object" && "response" in err) {
    const status = (err as { response?: { status?: number } }).response?.status
    return status === 404 || status === 405
  }
  return false
}

// ---------- 主 API 对象 ----------

export const documentApi = {
  /**
   * 获取文书详情。
   * 优先调用专用端点；端点不可用时回退到传入的 artifact 构造 DocumentDetail。
   *
   * GET /api/workflow-runs/{run_id}/documents/{document_id}/
   */
  async getDocument(
    runId: number,
    documentId: string,
    fallbackArtifact?: WorkflowArtifact,
  ): Promise<DocumentDetail> {
    try {
      const { data } = await apiClient.get<DocumentDetail>(
        `/workflow-runs/${runId}/documents/${documentId}/`,
      )
      return data
    } catch (err) {
      // 专用端点不存在时，使用 fallback artifact 构造文书
      if (fallbackArtifact) {
        return artifactToDocument(runId, documentId, fallbackArtifact)
      }
      throw new DocumentApiError(
        describeError(err, "获取文书失败"),
        "GET_DOCUMENT_FAILED",
        isNotImplemented(err),
      )
    }
  },

  /**
   * 重新生成段落（Task 4.1 已实现）。
   *
   * POST /api/workflow-runs/{run_id}/documents/{document_id}/paragraphs/{paragraph_id}/regenerate/
   *
   * options.prompt 可选：用户提供的额外指令（如「语气更坚定」）。
   * options.content 可选：用户编辑后的内容；若提供则创建 created_by_type="user" 的新版本。
   */
  async regenerateParagraph(
    runId: number,
    documentId: string,
    paragraphId: string,
    options: { prompt?: string; content?: string } = {},
  ): Promise<RegenerateParagraphResponse> {
    try {
      const { data } = await apiClient.post<RegenerateParagraphResponse>(
        `/workflow-runs/${runId}/documents/${documentId}/paragraphs/${paragraphId}/regenerate/`,
        options,
      )
      return data
    } catch (err) {
      throw new DocumentApiError(
        describeError(err, "段落重新生成失败"),
        "REGENERATE_PARAGRAPH_FAILED",
        isNotImplemented(err),
      )
    }
  },

  /**
   * 导出前质量门（Task 4.2 已实现）。
   *
   * POST /api/workflow-runs/{run_id}/documents/{document_id}/export-check/
   * 返回 {passed, issues, missing_elements, checks_run}
   */
  async exportCheck(runId: number, documentId: string): Promise<ExportCheckResult> {
    try {
      const { data } = await apiClient.post<ExportCheckResult>(
        `/workflow-runs/${runId}/documents/${documentId}/export-check/`,
        {},
      )
      return data
    } catch (err) {
      throw new DocumentApiError(
        describeError(err, "导出检查失败"),
        "EXPORT_CHECK_FAILED",
        isNotImplemented(err),
      )
    }
  },

  /**
   * 列出文书所有版本。
   *
   * GET /api/workflow-runs/{run_id}/documents/{document_id}/versions/
   * （端点缺失时 try/catch 降级为空数组）
   */
  async listDocumentVersions(runId: number, documentId: string): Promise<DocumentVersion[]> {
    try {
      const { data } = await apiClient.get<DocumentVersion[] | { results: DocumentVersion[] }>(
        `/workflow-runs/${runId}/documents/${documentId}/versions/`,
      )
      if (Array.isArray(data)) return data
      return data.results || []
    } catch (err) {
      // 后端未实现版本列表端点时返回空数组 + 标记降级
      if (isNotImplemented(err)) {
        return []
      }
      throw new DocumentApiError(
        describeError(err, "获取版本列表失败"),
        "LIST_VERSIONS_FAILED",
        isNotImplemented(err),
      )
    }
  },

  /**
   * 回滚到指定版本（创建新版本，内容为旧版本）。
   *
   * POST /api/workflow-runs/{run_id}/documents/{document_id}/versions/{version}/rollback/
   */
  async rollbackDocumentVersion(
    runId: number,
    documentId: string,
    version: number,
  ): Promise<DocumentVersion> {
    try {
      const { data } = await apiClient.post<DocumentVersion>(
        `/workflow-runs/${runId}/documents/${documentId}/versions/${version}/rollback/`,
        {},
      )
      return data
    } catch (err) {
      throw new DocumentApiError(
        describeError(err, "回滚版本失败"),
        "ROLLBACK_VERSION_FAILED",
        isNotImplemented(err),
      )
    }
  },
}

// ---------- artifact → document 降级构造 ----------

/**
 * 当 /documents/{id}/ 端点不存在时，从 WorkflowArtifact 构造 DocumentDetail。
 * artifact.payload 期望含 title / content / paragraphs / template_variant 等字段；
 * 文书种类（template_type）由 artifact.kind 推导。
 */
function artifactToDocument(
  runId: number,
  documentId: string,
  artifact: WorkflowArtifact,
): DocumentDetail {
  const payload = (artifact.payload || {}) as {
    title?: string
    content?: string
    // P5：产物内容里是 template_variant（投诉风格），非文书种类；
    // 文书种类（template_type）由 artifact.kind 推导。
    template_variant?: string
    paragraphs?: Array<Paragraph & { paragraph_id?: string }>
  }
  // 文书种类：由产物 kind（complaint_draft / respond_complaint_draft）推导，
  // 与后端文书详情端点 template_type=document_type 语义一致。
  const documentType =
    artifact.kind === 'respond_complaint_draft' ? 'respond_complaint' : 'complaint'
  // 后端段落以 paragraph_id 为键（paragraph_splitter 输出），归一化为前端契约的 id。
  const paragraphs: Paragraph[] = (Array.isArray(payload.paragraphs) ? payload.paragraphs : []).map(
    (p) => ({ ...p, id: p.id || p.paragraph_id || '' }),
  )
  // 若 payload 无 paragraphs 但有 content，将整体内容作为单段
  if (paragraphs.length === 0 && payload.content) {
    paragraphs.push({
      id: 'whole',
      content: payload.content,
      evidence_codes: [],
      legal_references: [],
      created_by_type: 'ai',
    })
  }
  return {
    id: documentId,
    run_id: runId,
    title: payload.title || artifact.summary || '文书',
    template_type: documentType,
    paragraphs,
    current_version: 1,
    created_at: artifact.created_at,
    updated_at: artifact.updated_at || undefined,
  }
}

export default documentApi
