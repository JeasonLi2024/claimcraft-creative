<script setup>
import { onMounted, ref, computed, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()
const route = useRoute()
const caseId = computed(() => route.params.caseId)

onMounted(() => {
  if (caseId.value) {
    store.fetchCaseDetail(caseId.value).catch(() => {})
  }
})

// 状态定义：主线 4 步 + cancelled 侧支
const MAIN_FLOW = ['draft', 'processing', 'submitted', 'closed']
const STATUS_LABEL = {
  draft: '草稿',
  processing: '处理中',
  submitted: '已提交',
  closed: '已结案',
  cancelled: '已取消',
}
// 状态机：当前状态 → 可流转的目标状态
const TRANSITIONS = {
  draft: ['processing', 'cancelled'],
  processing: ['submitted', 'cancelled'],
  submitted: ['closed'],
  closed: [],
  cancelled: [],
}

const currentStatus = computed(() => store.currentCase?.status || 'draft')
const statusLabel = (s) => STATUS_LABEL[s] || s || '草稿'

// 主线进度：当前及之前的状态标记 done/active
function mainDotClass(key) {
  const cur = currentStatus.value
  if (cur === 'cancelled') return ''
  const curIdx = MAIN_FLOW.indexOf(cur)
  const idx = MAIN_FLOW.indexOf(key)
  if (idx < curIdx) return 'done'
  if (idx === curIdx) return 'active'
  return ''
}

// === 推进状态弹窗 ===
const showTransition = ref(false)
const transitionForm = reactive({
  to_status: '',
  remark: '',
})
const transitioning = ref(false)
const transitionError = ref('')

// 当前状态可选的目标状态
const availableTargets = computed(() => {
  return (TRANSITIONS[currentStatus.value] || []).map((s) => ({
    value: s,
    label: STATUS_LABEL[s] || s,
  }))
})

function openTransition() {
  transitionForm.to_status = ''
  transitionForm.remark = ''
  transitionError.value = ''
  showTransition.value = true
}
function closeTransition() {
  showTransition.value = false
}
async function submitTransition() {
  if (!transitionForm.to_status) {
    transitionError.value = '请选择目标状态'
    return
  }
  transitioning.value = true
  transitionError.value = ''
  try {
    await store.transitionCaseStatus(caseId.value, {
      to_status: transitionForm.to_status,
      remark: transitionForm.remark.trim(),
    })
    showTransition.value = false
    // 重新拉取状态历史
    if (historyExpanded.value) {
      store.fetchStatusLogs(caseId.value).catch(() => {})
    }
  } catch (e) {
    transitionError.value = store.error || '状态流转失败，请稍后重试'
  } finally {
    transitioning.value = false
  }
}

// === 状态历史 ===
const historyExpanded = ref(false)
async function toggleHistory() {
  historyExpanded.value = !historyExpanded.value
  if (historyExpanded.value && store.statusLogs.length === 0) {
    try {
      await store.fetchStatusLogs(caseId.value)
    } catch (e) {
      // 忽略
    }
  }
}
function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}
</script>

<template>
  <section class="section">
    <h2>案件工作台</h2>

    <div v-if="store.loading && !store.currentCase" class="loading-box">
      加载中...
    </div>
    <div v-else-if="store.error && !store.currentCase" class="error-box">
      {{ store.error }}
    </div>

    <template v-else-if="store.currentCase">
      <!-- 状态条 -->
      <div class="status-bar">
        <div class="sb-left">
          <span class="status-tag" :class="currentStatus">{{ statusLabel(currentStatus) }}</span>
          <span class="sb-label">当前状态</span>
        </div>
        <div class="sb-progress">
          <template v-for="(key, idx) in MAIN_FLOW" :key="key">
            <div class="progress-step">
              <span
                class="progress-dot"
                :class="mainDotClass(key)"
              ></span>
              <span
                class="progress-label"
                :class="{ active: key === currentStatus }"
              >{{ statusLabel(key) }}</span>
            </div>
            <span v-if="idx < MAIN_FLOW.length - 1" class="progress-sep">→</span>
          </template>
          <span class="progress-sep">|</span>
          <div class="progress-step">
            <span
              class="progress-dot"
              :class="{ cancelled: currentStatus === 'cancelled' }"
            ></span>
            <span
              class="progress-label"
              :class="{ active: currentStatus === 'cancelled' }"
            >{{ statusLabel('cancelled') }}</span>
          </div>
        </div>
        <div class="sb-right">
          <button
            class="btn btn-primary"
            :disabled="availableTargets.length === 0"
            @click="openTransition"
          >
            推进状态
          </button>
        </div>
      </div>

      <h3 style="font-size: 1.6rem; margin-top: 0;">
        {{ store.currentCase.title }}
      </h3>
      <p class="section-lead">{{ store.currentCase.description }}</p>

      <div class="stats cols-6">
        <div class="stat">
          <div class="num">{{ store.currentCase.evidence_count ?? 0 }} 份</div>
          <div class="label">证据数量</div>
        </div>
        <div class="stat">
          <div class="num">{{ store.currentCase.timeline_count ?? 0 }} 个</div>
          <div class="label">关键节点数</div>
        </div>
        <div class="stat">
          <div class="num">{{ store.currentCase.template_count ?? 0 }} 套</div>
          <div class="label">投诉版本数</div>
        </div>
        <div class="stat">
          <div class="num">{{ statusLabel(currentStatus) }}</div>
          <div class="label">处理状态</div>
        </div>
        <div class="stat">
          <div class="num">{{ store.currentCase.image_evidence_count ?? 0 }} 份</div>
          <div class="label">图片证据数</div>
        </div>
        <div class="stat">
          <div class="num">{{ store.currentCase.extracted_field_count ?? 0 }} 个</div>
          <div class="label">抽取字段数</div>
        </div>
      </div>

      <!-- 状态历史 -->
      <div style="margin-top: 1.2rem;">
        <button
          class="history-toggle"
          :class="{ open: historyExpanded }"
          @click="toggleHistory"
        >
          <span class="arrow">▶</span>
          状态历史
        </button>
        <div v-if="historyExpanded">
          <div v-if="store.statusLogs.length === 0" class="empty-box">
            暂无状态变更记录。
          </div>
          <div v-else class="history-list">
            <div
              v-for="log in store.statusLogs"
              :key="log.id"
              class="history-item"
            >
              <div class="h-transition">
                {{ statusLabel(log.from_status) }}
                <span class="arrow">→</span>
                {{ statusLabel(log.to_status) }}
              </div>
              <div v-if="log.remark" class="h-remark">{{ log.remark }}</div>
              <div class="h-time">{{ formatTime(log.created_at || log.timestamp) }}</div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 推进状态弹窗 -->
    <div v-if="showTransition" class="modal-mask" @click.self="closeTransition">
      <div class="modal-box">
        <div class="modal-head">
          <span class="modal-title">推进状态</span>
          <button class="modal-close" @click="closeTransition">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">当前状态</label>
            <div>
              <span class="status-tag" :class="currentStatus">{{ statusLabel(currentStatus) }}</span>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">目标状态<span class="req">*</span></label>
            <select v-model="transitionForm.to_status" class="form-select">
              <option value="" disabled>请选择目标状态</option>
              <option v-for="t in availableTargets" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
            <div v-if="availableTargets.length === 0" class="form-hint">当前状态已终态，无可流转的目标。</div>
          </div>
          <div class="form-group">
            <label class="form-label">备注</label>
            <textarea
              v-model="transitionForm.remark"
              class="form-textarea"
              placeholder="可填写本次状态变更的备注..."
            ></textarea>
          </div>
          <div v-if="transitionError" class="form-error">{{ transitionError }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-secondary" @click="closeTransition" :disabled="transitioning">取消</button>
          <button class="btn btn-primary" @click="submitTransition" :disabled="transitioning || availableTargets.length === 0">
            {{ transitioning ? '提交中...' : '确认推进' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
