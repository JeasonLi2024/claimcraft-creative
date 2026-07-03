<script setup>
import { onMounted, ref } from 'vue'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()

const formats = [
  { key: 'pdf', title: 'PDF 文档', desc: '适合打印或正式提交（Demo 暂不支持）', disabled: true },
  { key: 'image', title: '图片包', desc: '证据截图打包导出（Demo 暂不支持）', disabled: true },
  { key: 'text', title: '文本包', desc: '投诉文本 + 证据清单 + 时间线', disabled: false },
]

const selectedFormat = ref('text')

const templates = [
  { type: 'platform', label: '平台客服版' },
  { type: 'regulatory', label: '监管投诉版' },
  { type: 'arbitration', label: '仲裁准备版' },
]
const selectedTemplate = ref('platform')

const masked = ref(false)

const exporting = ref(false)
const exportResult = ref(null)
const exportError = ref('')

onMounted(() => {
  // 预取案件详情，用于导出清单展示证据数量
  if (!store.currentCase) {
    store.fetchCaseDetail(1).catch(() => {})
  }
})

function selectFormat(fmt) {
  if (fmt.disabled) {
    exportError.value = 'Demo 环境暂不支持，请选择文本包'
    return
  }
  exportError.value = ''
  selectedFormat.value = fmt.key
}

async function handleExport() {
  if (selectedFormat.value !== 'text') {
    exportError.value = 'Demo 环境暂不支持，请选择文本包'
    return
  }
  exporting.value = true
  exportError.value = ''
  exportResult.value = null
  try {
    const result = await store.exportCase(1, {
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
    // 触发浏览器下载
    const blob = new Blob([result.content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'claimcraft_export.txt'
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

function templateLabel(type) {
  return templates.find((t) => t.type === type)?.label || type
}
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
        :class="{ selected: selectedFormat === fmt.key, disabled: fmt.disabled }"
        @click="selectFormat(fmt)"
      >
        <div class="fmt-title">{{ fmt.title }}</div>
        <div class="fmt-desc">{{ fmt.desc }}</div>
      </button>
    </div>

    <div v-if="exportError" class="error-box" style="margin-top: 1rem;">
      {{ exportError }}
    </div>

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

    <div style="margin-top: 1.4rem;">
      <button
        class="btn btn-primary"
        :disabled="exporting || selectedFormat !== 'text'"
        @click="handleExport"
      >
        {{ exporting ? '导出中...' : '导出' }}
      </button>
    </div>

    <div v-if="store.error && !exportError" class="error-box" style="margin-top: 1rem;">
      {{ store.error }}
    </div>

    <div v-if="exportResult" class="export-summary">
      <h3>导出成功</h3>
      <ul>
        <li>证据数量：{{ exportResult.evidenceCount }} 份</li>
        <li>模板版本：{{ templateLabel(exportResult.template) }}</li>
        <li>打码状态：{{ exportResult.masked ? '已打码' : '未打码' }}</li>
        <li>文件名：{{ exportResult.filename }}</li>
      </ul>
      <p class="muted" style="margin-top: .6rem; font-size: .9rem;">
        文件已开始下载，若未自动下载请检查浏览器拦截提示。
      </p>
    </div>
  </section>
</template>
