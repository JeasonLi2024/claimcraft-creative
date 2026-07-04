<script setup>
import { onMounted, ref, reactive, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()
const router = useRouter()

// 工具栏筛选条件
const search = ref('')
const disputeType = ref('')
const status = ref('')

// 纠纷类型选项
const disputeTypes = [
  { value: '', label: '全部纠纷类型' },
  { value: 'online_shopping', label: '网购纠纷' },
  { value: 'service_breach', label: '服务违约' },
  { value: 'second_hand', label: '二手交易' },
  { value: 'other', label: '其他' },
]
// 状态选项
const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'processing', label: '处理中' },
  { value: 'submitted', label: '已提交' },
  { value: 'closed', label: '已结案' },
  { value: 'cancelled', label: '已取消' },
]

// 状态中文标签
function statusLabel(s) {
  const map = {
    draft: '草稿',
    processing: '处理中',
    submitted: '已提交',
    closed: '已结案',
    cancelled: '已取消',
  }
  return map[s] || s || '草稿'
}
// 纠纷类型中文标签
function disputeLabel(t) {
  const item = disputeTypes.find((d) => d.value === t)
  return item && item.value ? item.label : t || '其他'
}

// 构建查询参数
function buildParams() {
  const params = {}
  if (search.value.trim()) params.search = search.value.trim()
  if (disputeType.value) params.dispute_type = disputeType.value
  if (status.value) params.status = status.value
  return params
}

// 拉取列表
async function loadList() {
  try {
    await store.fetchCases(buildParams())
  } catch (e) {
    // 错误已写入 store.error
  }
}

// 搜索/筛选变化时重新拉取
function onFilterChange() {
  loadList()
}

let searchTimer = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(loadList, 300)
}

onMounted(() => {
  loadList()
})

// 格式化时间
function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

// 进入案件工作台
function openCase(id) {
  router.push(`/cases/${id}/workspace`)
}

// === 删除案件 ===
const deleteTarget = ref(null) // 待删除的案件对象
function askDelete(c, e) {
  e.stopPropagation()
  deleteTarget.value = c
}
function closeDelete() {
  deleteTarget.value = null
}
async function confirmDelete() {
  if (!deleteTarget.value) return
  try {
    await store.deleteCase(deleteTarget.value.id)
    deleteTarget.value = null
  } catch (e) {
    // 错误已写入 store.error
  }
}

// === 新建案件 ===
const showCreate = ref(false)
const createForm = reactive({
  title: '',
  description: '',
  dispute_type: 'online_shopping',
})
const creating = ref(false)
const createError = ref('')

// === T27: 套用预设骨架 ===
const applyPresetFlag = ref(false) // 是否勾选套用预设
const selectedPresetId = ref('')   // 选中的预设 id
// 预设列表来自 store.casePresets；加载中状态来自 store.presetLoading
const presets = computed(() => store.casePresets)
const presetLoading = computed(() => store.presetLoading)
const selectedPreset = computed(() =>
  presets.value.find((p) => String(p.id) === String(selectedPresetId.value))
)

// 拉取指定纠纷类型的预设列表
async function loadPresets(caseType) {
  if (!caseType) {
    store.casePresets = []
    return
  }
  try {
    await store.fetchCasePresets(caseType)
  } catch (e) {
    // 错误已写入 store.error，列表会被清空
  }
}

// 纠纷类型变化时：清空预设选择并重新加载
watch(
  () => createForm.dispute_type,
  (val) => {
    selectedPresetId.value = ''
    // 若用户未勾选套用预设，则不必拉取
    if (!applyPresetFlag.value) return
    loadPresets(val)
  }
)

// 勾选状态变化时：若首次勾选且列表为空，则拉取当前类型预设
watch(applyPresetFlag, (checked) => {
  if (checked && presets.value.length === 0 && !presetLoading.value) {
    loadPresets(createForm.dispute_type)
  }
  if (!checked) {
    // 取消勾选时清空选择
    selectedPresetId.value = ''
  }
})

function openCreate() {
  createForm.title = ''
  createForm.description = ''
  createForm.dispute_type = 'online_shopping'
  createError.value = ''
  applyPresetFlag.value = false
  selectedPresetId.value = ''
  // 重置预设列表，避免上次内容残留
  store.casePresets = []
  showCreate.value = true
}
function closeCreate() {
  showCreate.value = false
}
async function submitCreate() {
  if (!createForm.title.trim()) {
    createError.value = '请填写案件标题'
    return
  }
  // 勾选套用预设时必须选择具体预设
  if (applyPresetFlag.value && !selectedPresetId.value) {
    createError.value = '请选择一个案件预设，或取消勾选"套用预设骨架"'
    return
  }
  creating.value = true
  createError.value = ''
  let created = null
  try {
    created = await store.createCase({
      title: createForm.title.trim(),
      description: createForm.description.trim(),
      dispute_type: createForm.dispute_type,
    })
    // 如勾选套用预设且选择了预设，则在新案件上调用 apply-preset
    if (applyPresetFlag.value && selectedPresetId.value && created && created.id) {
      try {
        await store.applyPreset(created.id, selectedPresetId.value)
      } catch (e) {
        // 套用失败：案件已创建，提示但仍然进入工作台
        createError.value = store.error || '案件已创建，但套用预设失败，请稍后在工作台重试'
      }
    }
    showCreate.value = false
    // 直接进入新案件工作台
    if (created && created.id) {
      router.push(`/cases/${created.id}/workspace`)
    } else {
      loadList()
    }
  } catch (e) {
    createError.value = store.error || '创建失败，请稍后重试'
  } finally {
    creating.value = false
  }
}

// 案件列表（响应 store.cases）
const cases = computed(() => store.cases)
</script>

<template>
  <section class="section">
    <h2>我的案件</h2>
    <p class="section-lead">在这里管理你的所有维权案件，点击卡片进入工作台继续处理。</p>

    <!-- 工具栏 -->
    <div class="case-toolbar" style="margin-top: 1rem;">
      <input
        v-model="search"
        class="search-input"
        type="text"
        placeholder="搜索案件标题或描述..."
        @input="onSearchInput"
      />
      <select v-model="disputeType" class="filter-select" @change="onFilterChange">
        <option v-for="d in disputeTypes" :key="d.value" :value="d.value">{{ d.label }}</option>
      </select>
      <select v-model="status" class="filter-select" @change="onFilterChange">
        <option v-for="s in statusOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
      <div class="spacer"></div>
      <button class="btn btn-primary" @click="openCreate">+ 新建案件</button>
    </div>

    <div v-if="store.error" class="error-box">{{ store.error }}</div>

    <div v-if="store.loading && cases.length === 0" class="loading-box">加载中...</div>
    <div v-else-if="cases.length === 0" class="empty-box">暂无案件，点击右上角"新建案件"开始。</div>

    <div v-else class="case-grid">
      <div
        v-for="c in cases"
        :key="c.id"
        class="case-card"
        @click="openCase(c.id)"
      >
        <button
          class="delete-icon"
          title="删除案件"
          @click="askDelete(c, $event)"
        >🗑</button>
        <div class="card-title">{{ c.title || '未命名案件' }}</div>
        <div class="card-tags">
          <span class="pill">{{ disputeLabel(c.dispute_type) }}</span>
          <span class="status-tag" :class="c.status || 'draft'">{{ statusLabel(c.status) }}</span>
        </div>
        <div v-if="c.description" class="card-desc">{{ c.description }}</div>
        <div class="card-meta">
          <span>证据 {{ c.evidence_count ?? 0 }} 份</span>
          <span>{{ formatTime(c.updated_at || c.created_at) }}</span>
        </div>
      </div>
    </div>

    <!-- 新建案件弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <div class="modal-box">
        <div class="modal-head">
          <span class="modal-title">新建案件</span>
          <button class="modal-close" @click="closeCreate">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">案件标题<span class="req">*</span></label>
            <input
              v-model="createForm.title"
              class="form-input"
              type="text"
              placeholder="例如：淘宝订单退款纠纷"
            />
          </div>
          <div class="form-group">
            <label class="form-label">案件描述</label>
            <textarea
              v-model="createForm.description"
              class="form-textarea"
              placeholder="简要描述纠纷经过..."
            ></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">纠纷类型</label>
            <select v-model="createForm.dispute_type" class="form-select">
              <option value="online_shopping">网购纠纷</option>
              <option value="service_breach">服务违约</option>
              <option value="second_hand">二手交易</option>
              <option value="other">其他</option>
            </select>
          </div>

          <!-- T27: 套用预设骨架 -->
          <div class="check-row">
            <input
              id="apply-preset"
              v-model="applyPresetFlag"
              type="checkbox"
            />
            <label for="apply-preset" style="cursor: pointer; user-select: none;">
              套用预设骨架
              <span class="form-hint" style="display: inline; margin-left: .35rem;">
                （自动填充证据项与时间线模板）
              </span>
            </label>
          </div>

          <div v-if="applyPresetFlag" class="form-group">
            <label class="form-label">
              案件预设<span v-if="presetLoading" class="form-hint" style="margin-left: .4rem;">加载中...</span>
            </label>
            <select
              v-if="!presetLoading && presets.length > 0"
              v-model="selectedPresetId"
              class="form-select"
            >
              <option value="" disabled>请选择预设...</option>
              <option v-for="p in presets" :key="p.id" :value="p.id">
                {{ p.name }}
              </option>
            </select>
            <div v-else-if="!presetLoading && presets.length === 0" class="form-hint">
              该纠纷类型暂无可用预设
            </div>
            <div
              v-if="selectedPreset && selectedPreset.description"
              class="form-hint"
              style="margin-top: .5rem; padding: .55rem .7rem; border-radius: 10px; background: #f5f9ff; border: 1px solid #d6e4ff; color: var(--ink); line-height: 1.6;"
            >
              {{ selectedPreset.description }}
            </div>
          </div>

          <div v-if="createError" class="form-error">{{ createError }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-secondary" @click="closeCreate" :disabled="creating">取消</button>
          <button class="btn btn-primary" @click="submitCreate" :disabled="creating">
            {{ creating ? '创建中...' : '确认创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="deleteTarget" class="modal-mask" @click.self="closeDelete">
      <div class="modal-box">
        <div class="modal-head">
          <span class="modal-title">删除案件</span>
          <button class="modal-close" @click="closeDelete">×</button>
        </div>
        <div class="modal-body">
          <div class="modal-confirm">
            <div class="confirm-text">确认删除案件"{{ deleteTarget.title }}"？</div>
            <div class="confirm-sub">此操作不可恢复，案件相关的证据、时间线、投诉文本都将被删除。</div>
          </div>
          <div v-if="store.error" class="form-error">{{ store.error }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-secondary" @click="closeDelete">取消</button>
          <button class="btn btn-primary" @click="confirmDelete">确认删除</button>
        </div>
      </div>
    </div>
  </section>
</template>
