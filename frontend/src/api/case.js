import api from './index'

// 案件相关接口封装
export function getCaseDetail(id) {
  return api.get(`/cases/${id}/`)
}

export function getEvidences(caseId) {
  return api.get(`/cases/${caseId}/evidences/`)
}

export function addEvidence(caseId, data) {
  return api.post(`/cases/${caseId}/evidences/`, data)
}

export function deleteEvidence(id) {
  return api.delete(`/evidences/${id}/`)
}

export function getTimeline(caseId) {
  return api.get(`/cases/${caseId}/timeline/`)
}

export function updateTimelineNode(id, data) {
  return api.patch(`/timeline-nodes/${id}/`, data)
}

export function getComplaint(caseId, templateType) {
  return api.get(`/cases/${caseId}/complaints/`, {
    params: { template: templateType },
  })
}

export function maskCase(caseId) {
  return api.post(`/cases/${caseId}/mask/`)
}

export function exportCase(caseId, data) {
  return api.post(`/cases/${caseId}/export/`, data)
}

// 上传证据图片（multipart）
export function uploadEvidence(caseId, file) {
  const formData = new FormData()
  formData.append('image', file)
  return api.post(`/cases/${caseId}/evidences/upload/`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 获取证据的抽取字段
export function getExtractedFields(evidenceId) {
  return api.get(`/evidences/${evidenceId}/extracted-fields/`)
}

// 更新抽取字段
export function updateExtractedField(id, data) {
  return api.patch(`/extracted-fields/${id}/`, data)
}

// 重建时间线
export function rebuildTimeline(caseId) {
  return api.post(`/cases/${caseId}/timeline/rebuild/`)
}

// 重新生成投诉文本
export function regenerateComplaint(caseId, templateType) {
  return api.post(`/cases/${caseId}/complaints/regenerate/`, {
    template_type: templateType,
  })
}

// === T1: 案件列表 / 状态机 / 打码图片 / 导出 ===
// 案件列表（支持 search / dispute_type / status 等查询参数）
export function fetchCases(params = {}) {
  return api.get('/cases/', { params })
}

// 新建案件
export function createCase(data) {
  return api.post('/cases/', data)
}

// 更新案件（管理接口）
export function updateCase(id, data) {
  return api.patch(`/cases/${id}/manage/`, data)
}

// 删除案件（管理接口）
export function deleteCase(id) {
  return api.delete(`/cases/${id}/manage/`)
}

// 状态流转
export function transitionCaseStatus(id, data) {
  return api.post(`/cases/${id}/status/transition/`, data)
}

// 状态变更日志
export function fetchStatusLogs(id) {
  return api.get(`/cases/${id}/status-logs/`)
}

// 一键打码所有图片
export function maskImages(id) {
  return api.post(`/cases/${id}/mask-images/`)
}

// 证据包导出（ZIP，二进制流）
export function exportPackage(id) {
  return api.get(`/cases/${id}/export/package/`, { responseType: 'blob' })
}

// PDF 文档导出（二进制流，template: platform/regulatory/arbitration）
export function exportPDF(id, template) {
  return api.get(`/cases/${id}/export/pdf/`, {
    params: { template },
    responseType: 'blob',
  })
}

// === T27: 案件模板预设 ===
// 获取指定纠纷类型的可用预设列表
export function fetchCasePresets(caseType) {
  return api.get('/case-presets/', { params: { case_type: caseType } })
}

// 对已创建的案件套用预设骨架
export function applyPreset(caseId, presetId) {
  return api.post(`/cases/${caseId}/apply-preset/`, { preset_id: presetId })
}
