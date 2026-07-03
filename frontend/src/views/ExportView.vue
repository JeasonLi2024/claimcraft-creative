<script setup>
import { onMounted, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()
const route = useRoute()
const caseId = computed(() => route.params.caseId)

// 导出格式：文本包 / 证据包(ZIP) / PDF 文档（全部启用）
const formats = [
  { key: 'text', title: '文本包', desc: '投诉文本 + 证据清单 + 时间线' },
  { key: 'zip', title: '证据包（ZIP）', desc: '打包导出全部证据材料' },
  { key: 'pdf', title: 'PDF 文档', desc: '适合打印或正式提交' },
]
const selectedFormat = ref('text')

// 文本包模板
const templates = [
  { type: 'platform', label: '平台客服版' },
  { type: 'regulatory', label: '监管投诉版' },
  { type: 'arbitration', label: '仲裁准备版' },
]
const selectedTemplate = ref('platform')
const masked = ref(false)

// PDF 模板
const pdfTemplates = [
  { value: 'platform', label: '平台客服版' },
  { value: 'regulatory', label: '监管投诉版' },
  { value: 'arbitration', label: '仲裁准备版' },
]
const selectedPdfTemplate = ref('platform')

const exporting = ref(false)
const exportResult = ref(null)
const exportError = ref('')

onMounted(() => {
  if (!store.currentCase && caseId.value) {
    store.fetchCaseDetail(caseId.value).catch(() => {})
  }
})

function selectFormat(fmt) {
  selectedFormat.value = fmt.key
  exportError.value = ''
}

function templateLabel(type) {
  return templates.find((t) => t.type === type)?.label || type
}

// 触发浏览器下载二进制流
function downloadBlob(data, filename, mime) {
  const blob = new Blob([data], { type: mime })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}

// 文本包导出（保留原有 .txt 流程）
async function handleTextExport() {
  exporting.value = true
  exportError.value = ''
  exportResult.value = null
  try {
    const result = await store.exportCase(caseId.value, {
      template_type: selectedTemplate.value,
      masked: masked.value,
    })
    exportResult.value = {
      content: result.content,
      filename: result.filename || 'claimcraft_export.txt',
      evidenceCount: store.currentCase?.evidence_count ?? 0,
      template: selectedTemplate.value,
      masked: masked.value,
    }
    const blob = new Blob([result.content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = result.filename || 'claimcraft_export.txt'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    exportError.value = store.error || '导出失败，请稍后重试'
  } finally {
    exporting.value = false
  }
}

// 证据包导出（ZIP）
async function handleZipExport() {
  exporting.value = true
  exportError.value = ''
  exportResult.value = null
  try {
    const data = await store.exportPackage(caseId.value)
    downloadBlob(data, `case_${caseId.value}_package.zip`, 'application/zip')
    exportResult.value = {
      filename: `case_${caseId.value}_package.zip`,
      kind: 'zip',
      evidenceCount: store.currentCase?.evidence_count ?? 0,
    }
  } catch (e) {
    exportError.value = store.error || '导出证据包失败，请稍后重试'
  } finally {
    exporting.value = false
  }
}

// PDF 文档导出
async function handlePdfExport() {
  exporting.value = true
  exportError.value = ''
  exportResult.value = null
  try {
    const data = await store.exportPDF(caseId.value, selectedPdfTemplate.value)
    downloadBlob(data, `case_${caseId.value}.pdf`, 'application/pdf')
    exportResult.value = {
      filename: `case_${caseId.value}.pdf`,
      kind: 'pdf',
      template: selectedPdfTemplate.value,
    }
  } catch (e) {
    exportError.value = store.error || '导出 PDF 失败，请稍后重试'
  } finally {
    exporting.value = false
  }
}

// 统一导出入口
function handleExport() {
  if (selectedFormat.value === 'text') return handleTextExport()
  if (selectedFormat.value === 'zip') return handleZipExport()
  if (selectedFormat.value === 'pdf') return handlePdfExport()
}

const exportButtonLabel = computed(() => {
  if (exporting.value) return '导出中...'
  if (selectedFormat.value === 'zip') return '下载证据包 (ZIP)'
  if (selectedFormat.value === 'pdf') return '下载 PDF'
  return '导出'
})
</script>

<template>
  <section class="section">
    <h2>导出与提交</h2>
    <p class="section-lead">选择导出格式与模板版本，可勾选是否打码敏感信息，导出后可直接提交给相应渠道。</p>

    <h3 style="margin-top: 1.2rem;">导出格式</h3>
    <div class="export-format-grid">
      <button
        v-for="fmt in formats"
        :key="fmt.key"
        class="format-card"
        :class="{ selected: selectedFormat === fmt.key }"
        @click="selectFormat(fmt)"
      >
        <div class="fmt-title">{{ fmt.title }}</div>
        <div class="fmt-desc">{{ fmt.desc }}</div>
      </button>
    </div>

    <div v-if="exportError" class="error-box" style="margin-top: 1rem;">
      {{ exportError }}
    </div>

    <!-- 文本包：模板 + 打码选项 -->
    <template v-if="selectedFormat === 'text'">
      <h3 style="margin-top: 1.4rem;">模板版本</h3>
      <div class="template-tabs" style="margin-top: .6rem;">
        <button
          v-for="t in templates"
          :key="t.type"
          class="template-tab"
          :class="{ active: selectedTemplate === t.type }"
          @click="selectedTemplate = t.type"
        >
          {{ t.label }}
        </button>
      </div>

      <label class="check-row">
        <input type="checkbox" v-model="masked" />
        <span>导出时对敏感信息打码（手机号 / 地址 / 身份证号）</span>
      </label>
    </template>

    <!-- PDF：模板下拉 -->
    <template v-if="selectedFormat === 'pdf'">
      <h3 style="margin-top: 1.4rem;">PDF 模板</h3>
      <div class="export-template-row">
        <label class="form-label" style="margin-bottom: 0;">选择模板版本</label>
        <select v-model="selectedPdfTemplate" class="form-select">
          <option v-for="t in pdfTemplates" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
      </div>
      <div class="form-hint">不同模板适用于不同提交渠道（平台客服 / 监管投诉 / 仲裁准备）。</div>
    </template>

    <!-- ZIP：说明 -->
    <template v-if="selectedFormat === 'zip'">
      <h3 style="margin-top: 1.4rem;">证据包说明</h3>
      <div class="form-hint">
        将导出本案件全部证据材料（含图片、打码后图片、证据清单）打包为 ZIP 文件。
      </div>
    </template>

    <div style="margin-top: 1.4rem;">
      <button
        class="btn btn-primary"
        :disabled="exporting"
        @click="handleExport"
      >
        {{ exportButtonLabel }}
      </button>
    </div>

    <div v-if="store.error && !exportError" class="error-box" style="margin-top: 1rem;">
      {{ store.error }}
    </div>

    <div v-if="exportResult" class="export-summary">
      <h3>导出成功</h3>
      <ul>
        <li>文件名：{{ exportResult.filename }}</li>
        <li v-if="exportResult.kind === 'text'">证据数量：{{ exportResult.evidenceCount }} 份</li>
        <li v-if="exportResult.kind === 'text'">模板版本：{{ templateLabel(exportResult.template) }}</li>
        <li v-if="exportResult.kind === 'text'">打码状态：{{ exportResult.masked ? '已打码' : '未打码' }}</li>
        <li v-if="exportResult.kind === 'pdf'">模板版本：{{ templateLabel(exportResult.template) }}</li>
        <li v-if="exportResult.kind === 'zip'">证据数量：{{ exportResult.evidenceCount }} 份</li>
      </ul>
      <p class="muted" style="margin-top: .6rem; font-size: .9rem;">
        文件已开始下载，若未自动下载请检查浏览器拦截提示。
      </p>
    </div>
  </section>
</template>
