<script setup>
import { onMounted } from 'vue'
import { useCaseStore } from '../stores/case'

const store = useCaseStore()

onMounted(() => {
  store.fetchCaseDetail(1).catch(() => {})
})
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
      <h3 style="font-size: 1.6rem; margin-top: 0;">
        {{ store.currentCase.title }}
      </h3>
      <p class="section-lead">{{ store.currentCase.description }}</p>

      <div class="stats cols-6">
        <div class="stat">
          <div class="num">{{ store.currentCase.evidence_count }} 份</div>
          <div class="label">证据数量</div>
        </div>
        <div class="stat">
          <div class="num">{{ store.currentCase.timeline_count }} 个</div>
          <div class="label">关键节点数</div>
        </div>
        <div class="stat">
          <div class="num">{{ store.currentCase.template_count }} 套</div>
          <div class="label">投诉版本数</div>
        </div>
        <div class="stat">
          <div class="num">处理中</div>
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
    </template>
  </section>
</template>
