<script setup>
import { onMounted, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()
const route = useRoute()
const caseId = computed(() => route.params.caseId)

// 本地编辑缓存：节点 id -> 当前输入框值
const editing = ref({})

// 重建中状态（独立于 store.loading，避免与初次加载混淆）
const rebuilding = ref(false)

onMounted(() => {
  if (caseId.value) {
    store.fetchTimeline(caseId.value).catch(() => {})
  }
})

// 格式化时间
function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 解析关联证据编号字符串为列表
function parseCodes(codes) {
  if (!codes) return []
  return String(codes)
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

// 初始化输入框值
function ensureEditing(node) {
  if (!(node.id in editing.value)) {
    editing.value[node.id] = node.event
  }
  return editing.value[node.id]
}

// 失焦时提交更新
async function onBlur(node) {
  const newVal = editing.value[node.id]
  if (newVal === node.event) return
  try {
    await store.updateTimelineNode(node.id, { event: newVal })
  } catch (e) {
    // 失败时回滚输入框
    editing.value[node.id] = node.event
  }
}

// 重建时间线
async function handleRebuild() {
  if (rebuilding.value) return
  rebuilding.value = true
  try {
    await store.rebuildTimeline(caseId.value)
  } catch (e) {
    // 错误已写入 store.error
  } finally {
    rebuilding.value = false
  }
}
</script>

<template>
  <section class="section">
    <h2>时间线校正</h2>
    <p class="section-lead">系统已自动按时间顺序拼装事实经过，可直接编辑事件描述，失焦后自动保存。</p>

    <div class="action-row">
      <button
        class="btn btn-primary"
        :disabled="rebuilding"
        @click="handleRebuild"
      >
        {{ rebuilding ? '⏳ 重建中...' : '重新生成时间线' }}
      </button>
    </div>

    <div v-if="store.error" class="error-box" style="margin-top: 1rem;">
      {{ store.error }}
    </div>

    <div v-if="(store.loading || rebuilding) && store.timelineNodes.length === 0" class="loading-box">
      加载中...
    </div>

    <div v-else-if="store.timelineNodes.length === 0" class="empty-box">
      暂无时间线节点。
    </div>

    <div v-else class="line-track">
      <div v-for="node in store.timelineNodes" :key="node.id" class="line-event">
        <div class="date">{{ formatTime(node.datetime) }}</div>
        <input
          class="event-input"
          type="text"
          :value="ensureEditing(node)"
          @input="editing[node.id] = $event.target.value"
          @blur="onBlur(node)"
        />
        <div class="node-meta">
          <span
            class="gen-pill"
            :class="node.auto_generated ? 'auto' : 'manual'"
          >
            {{ node.auto_generated ? '自动' : '手动' }}
          </span>
          <span
            v-for="code in parseCodes(node.related_evidence_codes)"
            :key="code"
            class="pill"
          >
            {{ code }}
          </span>
        </div>
      </div>
    </div>
  </section>
</template>
