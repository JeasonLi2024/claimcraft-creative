<script setup>
import { onMounted, ref, computed } from 'vue'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()

const templates = [
  { type: 'platform', label: '平台客服版' },
  { type: 'regulatory', label: '监管投诉版' },
  { type: 'arbitration', label: '仲裁准备版' },
]

const copied = ref(false)
// 重新生成中状态
const regenerating = ref(false)

onMounted(() => {
  store.fetchComplaint(1, 'platform').catch(() => {})
})

// 切换模板
function switchTemplate(type) {
  if (type === store.currentTemplate) return
  store.fetchComplaint(1, type).catch(() => {})
}

// 重新生成当前模板的投诉文本
async function handleRegenerate() {
  if (regenerating.value) return
  regenerating.value = true
  try {
    await store.regenerateComplaint(1, store.currentTemplate)
  } catch (e) {
    // 错误已写入 store.error
  } finally {
    regenerating.value = false
  }
}

// 将正文中 E1/E2 等证据编号引用替换为高亮 span
// 使用 v-html 渲染，需保证 content 来自后端可信数据
const highlightedContent = computed(() => {
  const content = store.complaintData?.content || ''
  const escaped = escapeHtml(content)
  return escaped.replace(/(E\d+)/g, '<span class="evidence-ref">$1</span>')
})

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// 复制全文
async function copyAll() {
  if (!store.complaintData) return
  const text = `${store.complaintData.title}\n\n${store.complaintData.content}`
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch (e) {
    // 降级方案
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
      copied.value = true
      setTimeout(() => (copied.value = false), 2000)
    } catch (_) {
      // 忽略
    }
    document.body.removeChild(ta)
  }
}
</script>

<template>
  <section class="section">
    <h2>投诉文本</h2>
    <p class="section-lead">系统根据导入材料自动生成投诉文本，并插入证据编号引用。可在三类模板间一键切换。</p>

    <div class="template-tabs" style="margin-top: 1rem;">
      <button
        v-for="t in templates"
        :key="t.type"
        class="template-tab"
        :class="{ active: store.currentTemplate === t.type }"
        @click="switchTemplate(t.type)"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="action-row" style="margin-top: .5rem;">
      <button
        class="btn btn-secondary"
        :disabled="!store.complaintData || regenerating"
        @click="copyAll"
      >
        复制全文
      </button>
      <button
        class="btn btn-secondary"
        :disabled="regenerating"
        @click="handleRegenerate"
      >
        {{ regenerating ? '⏳ 生成中...' : '重新生成' }}
      </button>
      <span v-if="copied" class="copy-tip">已复制</span>
    </div>

    <div v-if="store.error" class="error-box" style="margin-top: 1rem;">
      {{ store.error }}
    </div>

    <div v-if="(store.loading || regenerating) && !store.complaintData" class="loading-box">
      加载中...
    </div>

    <template v-else-if="store.complaintData">
      <div class="complaint-title" style="margin-top: 1.2rem;">
        {{ store.complaintData.title }}
      </div>
      <div class="complaint-body" v-html="highlightedContent"></div>
    </template>
  </section>
</template>
