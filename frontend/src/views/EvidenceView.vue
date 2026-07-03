<script setup>
import { onMounted, ref, reactive, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()
const route = useRoute()
const caseId = computed(() => route.params.caseId)

// 拖拽上传状态
const isDragover = ref(false)
const uploading = ref(false)
const fileInput = ref(null)

// lightbox 大图
const lightboxSrc = ref(null)

// 各证据 OCR 折叠状态：evidence id -> boolean
const ocrExpanded = reactive({})
// 各证据字段加载中：evidence id -> boolean
const fieldsLoading = reactive({})
// 字段编辑缓存：field id -> 当前输入值
const fieldDraft = reactive({})

onMounted(() => {
  if (caseId.value) {
    store.fetchEvidences(caseId.value).catch(() => {})
  }
})

// 格式化时间为 YYYY-MM-DD HH:mm
function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// OCR 状态文案
function ocrStatusText(status) {
  if (status === 'done') return '已识别'
  if (status === 'failed') return '识别失败'
  return '识别中'
}

// 添加示例证据
async function handleAdd() {
  try {
    await store.addEvidence(caseId.value, {
      evidence_type: '补充材料',
      description: '用户补充上传的截图证据',
      source_time: new Date().toISOString(),
      has_sensitive_info: false,
    })
  } catch (e) {
    // 错误已写入 store.error
  }
}

// 删除证据
async function handleRemove(id) {
  try {
    await store.removeEvidence(id)
  } catch (e) {
    // 错误已写入 store.error
  }
}

// 点击拖拽区触发文件选择
function triggerFilePick() {
  if (uploading.value) return
  fileInput.value?.click()
}

function onFileChange(e) {
  const file = e.target.files?.[0]
  if (file) doUpload(file)
  // 重置以支持重复选择同一文件
  e.target.value = ''
}

function onDragover(e) {
  e.preventDefault()
  if (uploading.value) return
  isDragover.value = true
}

function onDragleave(e) {
  e.preventDefault()
  isDragover.value = false
}

function onDrop(e) {
  e.preventDefault()
  isDragover.value = false
  if (uploading.value) return
  const file = e.dataTransfer.files?.[0]
  if (file) doUpload(file)
}

async function doUpload(file) {
  uploading.value = true
  try {
    await store.uploadEvidence(caseId.value, file)
  } catch (e) {
    // 错误已写入 store.error
  } finally {
    uploading.value = false
  }
}

// lightbox
function openLightbox(src) {
  lightboxSrc.value = src
}
function closeLightbox() {
  lightboxSrc.value = null
}

// OCR 展开/收起
async function toggleOcr(ev) {
  const id = ev.id
  const next = !ocrExpanded[id]
  ocrExpanded[id] = next
  if (next && !store.extractedFieldsMap[id] && !fieldsLoading[id]) {
    fieldsLoading[id] = true
    try {
      await store.fetchExtractedFields(id)
    } catch (e) {
      // 忽略
    } finally {
      fieldsLoading[id] = false
    }
  }
}

function getFields(evId) {
  return store.extractedFieldsMap[evId] || []
}

function ensureFieldDraft(field) {
  if (!(field.id in fieldDraft)) {
    fieldDraft[field.id] = field.field_value ?? ''
  }
  return fieldDraft[field.id]
}

// 字段失焦提交
async function onFieldBlur(field) {
  const newVal = fieldDraft[field.id]
  if (newVal === field.field_value) return
  try {
    await store.updateExtractedField(field.id, { field_value: newVal })
  } catch (e) {
    // 回滚
    fieldDraft[field.id] = field.field_value
  }
}

// 置信度展示
function confText(c) {
  if (c === null || c === undefined) return '-'
  const n = Number(c)
  if (Number.isNaN(n)) return String(c)
  return n.toFixed(2)
}

// 是否有图片
function hasImage(ev) {
  return !!ev.image
}
</script>

<template>
  <section class="section">
    <h2>证据导入</h2>
    <p class="section-lead">管理本案件的所有证据材料，每条证据会自动生成编号（E1、E2...），供投诉文本引用。支持拖拽上传图片自动 OCR 识别。</p>

    <!-- 拖拽上传区 -->
    <div
      class="dropzone"
      :class="{ dragover: isDragover }"
      @click="triggerFilePick"
      @dragover="onDragover"
      @dragleave="onDragleave"
      @drop="onDrop"
    >
      <input ref="fileInput" type="file" accept="image/*" @change="onFileChange" />
      <template v-if="uploading">
        <div class="dz-loading">⏳ 正在上传并识别...</div>
      </template>
      <template v-else>
        <div class="dz-icon">⬆️</div>
        <div class="dz-title">拖拽图片到此处上传，或点击选择文件</div>
        <div class="dz-sub">支持 JPG / PNG 等图片格式，上传后自动进行 OCR 识别</div>
      </template>
    </div>

    <div class="action-row">
      <button class="btn btn-secondary" :disabled="store.loading" @click="handleAdd">
        + 添加示例证据
      </button>
    </div>

    <div v-if="store.error" class="error-box" style="margin-top: 1rem;">
      {{ store.error }}
    </div>

    <div v-if="store.loading && store.evidences.length === 0" class="loading-box">
      加载中...
    </div>

    <div v-else-if="store.evidences.length === 0" class="empty-box">
      暂无证据，点击上方按钮添加示例证据。
    </div>

    <div v-else class="evidence-grid">
      <div v-for="ev in store.evidences" :key="ev.id" class="evidence-item">
        <div class="ev-head">
          <span class="ev-code">{{ ev.code }}</span>
          <div style="display:flex; align-items:center; gap:.4rem; flex-wrap:wrap;">
            <span class="pill">{{ ev.evidence_type }}</span>
            <span
              v-if="hasImage(ev) && ev.ocr_status"
              class="ocr-tag"
              :class="ev.ocr_status"
            >
              {{ ocrStatusText(ev.ocr_status) }}
            </span>
          </div>
        </div>

        <!-- 图片证据：缩略图 -->
        <div v-if="hasImage(ev)" class="ev-thumb" @click="openLightbox(ev.image)">
          <img :src="ev.image" :alt="ev.code" />
        </div>

        <!-- 文本证据：原描述 -->
        <div v-else class="ev-desc">{{ ev.description }}</div>

        <div class="ev-time">来源时间：{{ formatTime(ev.source_time) }}</div>

        <!-- OCR 识别结果可展开区（仅有图片且 ocr 状态非空时显示） -->
        <div v-if="hasImage(ev) && ev.ocr_status" class="ocr-section">
          <button
            class="ocr-toggle"
            :class="{ open: ocrExpanded[ev.id] }"
            @click="toggleOcr(ev)"
          >
            <span class="arrow">▶</span>
            OCR 识别结果
          </button>
          <div v-if="ocrExpanded[ev.id]" class="ocr-body">
            <div class="ocr-text" :class="{ empty: !ev.extracted_text }">
              <template v-if="ev.extracted_text">{{ ev.extracted_text }}</template>
              <template v-else>暂无识别文本</template>
            </div>

            <div v-if="fieldsLoading[ev.id]" class="ocr-loading">加载抽取字段中...</div>
            <template v-else>
              <table v-if="getFields(ev.id).length" class="field-table">
                <thead>
                  <tr>
                    <th>字段名</th>
                    <th>值</th>
                    <th style="text-align:right;">置信度</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="f in getFields(ev.id)" :key="f.id">
                    <td class="field-name">{{ f.field_name }}</td>
                    <td>
                      <input
                        class="field-input"
                        type="text"
                        :value="ensureFieldDraft(f)"
                        @input="fieldDraft[f.id] = $event.target.value"
                        @blur="onFieldBlur(f)"
                      />
                    </td>
                    <td class="field-conf">{{ confText(f.confidence) }}</td>
                  </tr>
                </tbody>
              </table>
              <div v-else class="ocr-loading" style="color: var(--muted);">
                暂无抽取字段
              </div>
            </template>
          </div>
        </div>

        <div style="margin-top: .6rem;">
          <button class="btn btn-danger-text" @click="handleRemove(ev.id)">
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- Lightbox -->
    <div v-if="lightboxSrc" class="lightbox" @click="closeLightbox">
      <img :src="lightboxSrc" alt="证据大图" />
    </div>
  </section>
</template>
