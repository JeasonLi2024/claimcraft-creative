import { defineStore } from 'pinia'
import {
  getCaseDetail,
  getEvidences,
  addEvidence as apiAddEvidence,
  deleteEvidence,
  getTimeline,
  updateTimelineNode as apiUpdateTimelineNode,
  getComplaint,
  maskCase,
  exportCase as apiExportCase,
  uploadEvidence as apiUploadEvidence,
  getExtractedFields as apiGetExtractedFields,
  updateExtractedField as apiUpdateExtractedField,
  rebuildTimeline as apiRebuildTimeline,
  regenerateComplaint as apiRegenerateComplaint,
} from '../api/case'

// ClaimCraft 案件状态管理
export const useCaseStore = defineStore('case', {
  state: () => ({
    currentCase: null,
    evidences: [],
    timelineNodes: [],
    currentTemplate: 'platform',
    complaintData: null,
    maskResults: [],
    masked: false,
    loading: false,
    error: null,
    // 证据 id -> 抽取字段列表
    extractedFieldsMap: {},
  }),
  actions: {
    async fetchCaseDetail(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await getCaseDetail(id)
        this.currentCase = data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '获取案件详情失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    async fetchEvidences(caseId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await getEvidences(caseId)
        this.evidences = data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '获取证据列表失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    async addEvidence(caseId, payload) {
      this.error = null
      try {
        const { data } = await apiAddEvidence(caseId, payload)
        this.evidences.push(data)
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '添加证据失败'
        throw e
      }
    },
    async removeEvidence(id) {
      this.error = null
      try {
        await deleteEvidence(id)
        this.evidences = this.evidences.filter((ev) => ev.id !== id)
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '删除证据失败'
        throw e
      }
    },
    async fetchTimeline(caseId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await getTimeline(caseId)
        this.timelineNodes = data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '获取时间线失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    async updateTimelineNode(id, payload) {
      this.error = null
      try {
        const { data } = await apiUpdateTimelineNode(id, payload)
        const idx = this.timelineNodes.findIndex((n) => n.id === id)
        if (idx !== -1) {
          this.timelineNodes[idx] = { ...this.timelineNodes[idx], ...data }
        }
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '更新时间线节点失败'
        throw e
      }
    },
    async fetchComplaint(caseId, templateType) {
      this.loading = true
      this.error = null
      try {
        const { data } = await getComplaint(caseId, templateType)
        this.currentTemplate = templateType
        this.complaintData = data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '获取投诉文本失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    async fetchMaskResults(caseId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await maskCase(caseId)
        this.maskResults = data.items || []
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '获取打码结果失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    toggleMasked() {
      this.masked = !this.masked
    },
    async exportCase(caseId, payload) {
      this.error = null
      try {
        const { data } = await apiExportCase(caseId, payload)
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '导出失败'
        throw e
      }
    },
    // 上传证据图片
    async uploadEvidence(caseId, file) {
      this.error = null
      try {
        const { data } = await apiUploadEvidence(caseId, file)
        this.evidences.push(data)
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '上传证据失败'
        throw e
      }
    },
    // 重建时间线
    async rebuildTimeline(caseId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await apiRebuildTimeline(caseId)
        this.timelineNodes = data
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '重建时间线失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    // 重新生成投诉文本
    async regenerateComplaint(caseId, templateType) {
      this.loading = true
      this.error = null
      try {
        const { data } = await apiRegenerateComplaint(caseId, templateType)
        this.currentTemplate = templateType
        this.complaintData = data
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '重新生成投诉文本失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    // 获取证据的抽取字段
    async fetchExtractedFields(evidenceId) {
      this.error = null
      try {
        const { data } = await apiGetExtractedFields(evidenceId)
        this.extractedFieldsMap = {
          ...this.extractedFieldsMap,
          [evidenceId]: data,
        }
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '获取抽取字段失败'
        throw e
      }
    },
    // 更新抽取字段
    async updateExtractedField(id, data) {
      this.error = null
      try {
        const { data: updated } = await apiUpdateExtractedField(id, data)
        // 在 map 中就地替换对应字段
        for (const evId of Object.keys(this.extractedFieldsMap)) {
          const list = this.extractedFieldsMap[evId]
          const idx = list.findIndex((f) => f.id === id)
          if (idx !== -1) {
            const newList = list.slice()
            newList[idx] = { ...list[idx], ...updated }
            this.extractedFieldsMap = {
              ...this.extractedFieldsMap,
              [evId]: newList,
            }
            break
          }
        }
        return updated
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '更新抽取字段失败'
        throw e
      }
    },
  },
})
