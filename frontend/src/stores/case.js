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
  fetchCases as apiFetchCases,
  createCase as apiCreateCase,
  updateCase as apiUpdateCase,
  deleteCase as apiDeleteCase,
  transitionCaseStatus as apiTransitionCaseStatus,
  fetchStatusLogs as apiFetchStatusLogs,
  maskImages as apiMaskImages,
  exportPackage as apiExportPackage,
  exportPDF as apiExportPDF,
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
    // T1: 案件列表 + 状态变更日志
    cases: [],
    statusLogs: [],
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
    // === T1: 案件列表 / 状态机 / 图片打码 / 包导出 ===
    async fetchCases(params) {
      this.loading = true
      this.error = null
      try {
        const { data } = await apiFetchCases(params)
        // 兼容分页结构 { results: [...] } 或直接数组
        const list = Array.isArray(data) ? data : data.results || []
        this.cases = list
        return list
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '获取案件列表失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    async createCase(data) {
      this.error = null
      try {
        const { data: created } = await apiCreateCase(data)
        this.cases = [created, ...this.cases]
        return created
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '创建案件失败'
        throw e
      }
    },
    async updateCase(id, data) {
      this.error = null
      try {
        const { data: updated } = await apiUpdateCase(id, data)
        const idx = this.cases.findIndex((c) => c.id === id)
        if (idx !== -1) {
          this.cases[idx] = { ...this.cases[idx], ...updated }
        }
        if (this.currentCase && this.currentCase.id === id) {
          this.currentCase = { ...this.currentCase, ...updated }
        }
        return updated
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '更新案件失败'
        throw e
      }
    },
    async deleteCase(id) {
      this.error = null
      try {
        await apiDeleteCase(id)
        this.cases = this.cases.filter((c) => c.id !== id)
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '删除案件失败'
        throw e
      }
    },
    async transitionCaseStatus(id, data) {
      this.error = null
      try {
        const { data: updated } = await apiTransitionCaseStatus(id, data)
        // 更新列表中对应项
        const idx = this.cases.findIndex((c) => c.id === id)
        if (idx !== -1) {
          this.cases[idx] = { ...this.cases[idx], ...updated }
        }
        // 更新当前案件状态
        if (this.currentCase && this.currentCase.id === id) {
          this.currentCase = { ...this.currentCase, ...updated }
        }
        return updated
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '状态流转失败'
        throw e
      }
    },
    async fetchStatusLogs(id) {
      this.error = null
      try {
        const { data } = await apiFetchStatusLogs(id)
        const list = Array.isArray(data) ? data : data.results || []
        this.statusLogs = list
        return list
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '获取状态历史失败'
        throw e
      }
    },
    async maskImages(caseId) {
      this.error = null
      try {
        const { data } = await apiMaskImages(caseId)
        // 更新 evidences 中图片证据的 masked_image / mask_status
        // 兼容后端返回 { results: [...] } 或数组
        const items = Array.isArray(data) ? data : data.results || data.items || []
        items.forEach((item) => {
          const idx = this.evidences.findIndex((ev) => ev.id === item.id)
          if (idx !== -1) {
            this.evidences[idx] = {
              ...this.evidences[idx],
              masked_image: item.masked_image,
              mask_status: item.masked_status || item.mask_status || 'done',
            }
          }
        })
        return items
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '图片打码失败'
        throw e
      }
    },
    async exportPackage(caseId) {
      this.error = null
      try {
        const res = await apiExportPackage(caseId)
        return res.data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '导出证据包失败'
        throw e
      }
    },
    async exportPDF(caseId, template) {
      this.error = null
      try {
        const res = await apiExportPDF(caseId, template)
        return res.data
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || '导出 PDF 失败'
        throw e
      }
    },
  },
})
