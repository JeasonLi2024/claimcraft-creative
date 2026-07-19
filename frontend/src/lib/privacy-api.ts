// 隐私检查与打码 API 客户端。
// 对齐设计文档 §15.3：新建独立 privacyApi，不再扩展语义模糊的 maskApi。
// 案件详情 / 证据列表仍复用 case-store，此处只负责隐私域接口。
import apiClient from "./api-client"
import type { Evidence } from "@/types/case"
import type { TextRisk } from "@/types/privacy"

export const privacyApi = {
  /** 获取文本风险清单（实时计算，不修改数据库）。GET /cases/{id}/mask/ */
  getTextRisks: (caseId: number): Promise<TextRisk[]> =>
    apiClient
      .get<{ items: TextRisk[] }>(`/cases/${caseId}/mask/`)
      .then((r) => r.data.items || []),

  /** 对案件全部图片证据执行打码。POST /cases/{id}/mask-images/ */
  maskAllImages: (caseId: number): Promise<Evidence[]> =>
    apiClient
      .post<{ items: Evidence[] }>(`/cases/${caseId}/mask-images/`)
      .then((r) => r.data.items || []),

  /** 单张证据（重）打码：失败重试 / 卡住 pending 恢复 / 逐图处理。
   *  POST /evidences/{id}/mask-image/ */
  remaskImage: (evidenceId: number): Promise<Evidence> =>
    apiClient
      .post<Evidence>(`/evidences/${evidenceId}/mask-image/`)
      .then((r) => r.data),
}

export default privacyApi
