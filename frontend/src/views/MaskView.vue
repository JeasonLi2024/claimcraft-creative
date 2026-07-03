<script setup>
import { onMounted, computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()
const route = useRoute()
const caseId = computed(() => route.params.caseId)

onMounted(() => {
  // 文本打码结果
  store.fetchMaskResults(caseId.value).catch(() => {})
  // 图片证据列表（用于图片打码区）
  store.fetchEvidences(caseId.value).catch(() => {})
})

// 推断敏感信息类型：根据原文内容判断
function detectType(text) {
  if (!text) return '未知'
  if (/1[3-9]\d{9}/.test(text)) return '手机号'
  if (/\d{17}[\dXx]/.test(text)) return '身份证号'
  if (/[\u4e00-\u9fa5]{2,6}市/.test(text)) return '地址'
  return '其他'
}
function typeClass(text) {
  const t = detectType(text)
  if (t === '手机号') return 'pill amber'
  if (t === '身份证号') return 'pill red'
  if (t === '地址') return 'pill green'
  return 'pill'
}
function displayText(item) {
  return store.masked ? item.masked : item.original
}

// === 图片打码 ===
// 仅显示有图片的证据
const imageEvidences = computed(() => {
  return store.evidences.filter((ev) => !!ev.image)
})

function maskStatusLabel(s) {
  if (s === 'done') return '已打码'
  if (s === 'pending') return '打码中'
  return '未打码'
}

const masking = ref(false)
const lightboxSrc = ref(null)

async function handleMaskAll() {
  if (masking.value) return
  masking.value = true
  try {
    await store.maskImages(caseId.value)
  } catch (e) {
    // 错误已写入 store.error
  } finally {
    masking.value = false
  }
}

function openLightbox(src) {
  lightboxSrc.value = src
}
function closeLightbox() {
  lightboxSrc.value = null
}
</script>

<template>
  <section class="section">
    <h2>隐私打码</h2>
    <p class="section-lead">系统识别出证据中的手机号、地址、身份证号等敏感信息，支持一键切换打码状态；图片证据可一键打码生成对比图。</p>

    <!-- 文本打码开关 -->
    <div class="toggle-row" style="margin-top: 1rem;">
      <div>
        <strong>一键打码（文本）</strong>
        <div class="muted" style="font-size: .9rem;">
          开启后显示打码后内容，关闭后显示原文
        </div>
      </div>
      <button
        class="toggle"
        :class="{ on: store.masked }"
        :aria-pressed="store.masked"
        @click="store.toggleMasked()"
      ></button>
    </div>

    <div v-if="store.error" class="error-box">{{ store.error }}</div>

    <!-- 文本打码结果 -->
    <div v-if="store.loading && store.maskResults.length === 0" class="loading-box">
      加载中...
    </div>
    <div v-else-if="store.maskResults.length === 0" class="empty-box">
      暂未识别到含敏感信息的证据。
    </div>
    <table v-else class="mask-table">
      <thead>
        <tr>
          <th>证据编号</th>
          <th>类型</th>
          <th>{{ store.masked ? '打码后' : '原文' }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, idx) in store.maskResults" :key="idx">
          <td><strong style="color: var(--accent);">{{ item.evidence_code }}</strong></td>
          <td><span :class="typeClass(item.original)">{{ detectType(item.original) }}</span></td>
          <td class="mono-cell">{{ displayText(item) }}</td>
        </tr>
      </tbody>
    </table>

    <!-- 图片打码区 -->
    <div class="mask-image-section">
      <div class="action-row" style="margin-top: 0;">
        <div>
          <h3 style="margin-top: 0;">图片打码</h3>
          <div class="muted" style="font-size: .9rem;">
            对图片证据中的敏感信息进行打码处理，支持原图与打码后图片对比。
          </div>
        </div>
        <button
          class="btn btn-primary"
          :disabled="masking || imageEvidences.length === 0"
          @click="handleMaskAll"
        >
          {{ masking ? '⏳ 打码中...' : '一键打码所有图片' }}
        </button>
      </div>

      <div v-if="imageEvidences.length === 0" class="empty-box">
        暂无图片证据可打码。
      </div>
      <div v-else class="mask-image-grid">
        <div v-for="ev in imageEvidences" :key="ev.id" class="mask-image-item">
          <div class="mi-head">
            <span class="mi-code">{{ ev.code }}</span>
            <span class="pill">{{ ev.evidence_type }}</span>
            <span
              class="mask-status-tag"
              :class="ev.mask_status || 'none'"
            >
              <span v-if="ev.mask_status === 'pending'" class="spinner"></span>
              {{ maskStatusLabel(ev.mask_status) }}
            </span>
          </div>
          <div class="mi-images">
            <div class="mi-thumb">
              <div class="mi-cap">原图</div>
              <img :src="ev.image" :alt="ev.code + ' 原图'" @click="openLightbox(ev.image)" />
            </div>
            <div v-if="ev.masked_image && ev.mask_status === 'done'" class="mi-thumb">
              <div class="mi-cap">打码后</div>
              <img :src="ev.masked_image" :alt="ev.code + ' 打码后'" @click="openLightbox(ev.masked_image)" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Lightbox -->
    <div v-if="lightboxSrc" class="lightbox" @click="closeLightbox">
      <img :src="lightboxSrc" alt="证据大图" />
    </div>
  </section>
</template>
