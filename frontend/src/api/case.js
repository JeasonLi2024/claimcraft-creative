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
