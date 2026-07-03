<script setup>
import { useRoute } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()

// 当前案件上下文（在案件相关路由下存在）
const caseId = computed(() => route.params.caseId)

// 左侧导航项：cases 始终可见；其余项仅在案件上下文下显示
// 路径根据 caseId 动态生成，确保进入案件后导航链接仍带 caseId
const navItems = computed(() => {
  const items = [
    { name: 'cases', label: '我的案件', path: '/cases' },
  ]
  if (caseId.value) {
    items.push(
      { name: 'workspace', label: '案件工作台', path: `/cases/${caseId.value}/workspace` },
      { name: 'evidence', label: '证据导入', path: `/cases/${caseId.value}/evidence` },
      { name: 'timeline', label: '时间线校正', path: `/cases/${caseId.value}/timeline` },
      { name: 'complaint', label: '投诉文本', path: `/cases/${caseId.value}/complaint` },
      { name: 'mask', label: '隐私打码', path: `/cases/${caseId.value}/mask` },
      { name: 'export', label: '导出与提交', path: `/cases/${caseId.value}/export` },
    )
  }
  return items
})

const currentName = computed(() => route.name)
</script>

<template>
  <div class="app-root">
    <nav class="topbar">
      <div class="topbar-inner">
        <div class="brand">
          <span class="brand-mark">C</span>
          <span>ClaimCraft</span>
        </div>
        <div class="topbar-actions">
          <router-link to="/cases" class="my-cases-link">我的案件</router-link>
          <a class="back-link" href="../claimcraft-creative.html">返回介绍页</a>
        </div>
      </div>
    </nav>

    <div class="app-shell">
      <aside class="sidebar">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="item.path"
          class="nav-item"
          :class="{ active: currentName === item.name }"
        >
          {{ item.label }}
        </router-link>
      </aside>

      <main class="main-content">
        <router-view />
      </main>
    </div>
  </div>
</template>
