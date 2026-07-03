<script setup>
import { onMounted, computed } from 'vue'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()

onMounted(() => {
  store.fetchMaskResults(1).catch(() => {})
})

// 推断敏感信息类型：根据原文内容判断
function detectType(text) {
  if (!text) return '未知'
  // 手机号：1 开头 11 位
  if (/1[3-9]\d{9}/.test(text)) return '手机号'
  // 身份证号：18 位（末位可能 X）
  if (/\d{17}[\dXx]/.test(text)) return '身份证号'
  // 地址：含"市"
  if (/[\u4e00-\u9fa5]{2,6}市/.test(text)) return '地址'
  return '其他'
}

// 类型对应的 pill 样式
function typeClass(text) {
  const t = detectType(text)
  if (t === '手机号') return 'pill amber'
  if (t === '身份证号') return 'pill red'
  if (t === '地址') return 'pill green'
  return 'pill'
}

// 当前应展示的内容：masked=true 显示打码后，否则显示原文
function displayText(item) {
  return store.masked ? item.masked : item.original
}
</script>

<template>
  <section class="section">
    <h2>隐私打码</h2>
    <p class="section-lead">系统识别出证据中的手机号、地址、身份证号等敏感信息，支持一键切换打码状态。</p>

    <div class="toggle-row" style="margin-top: 1rem;">
      <div>
        <strong>一键打码</strong>
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

    <div v-if="store.error" class="error-box">
      {{ store.error }}
    </div>

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
  </section>
</template>
