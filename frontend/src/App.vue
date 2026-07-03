<script setup>
import { useRoute } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()

// 左侧导航项配置
const navItems = [
  { path: '/workspace', label: '案件工作台' },
  { path: '/evidence', label: '证据导入' },
  { path: '/timeline', label: '时间线校正' },
  { path: '/complaint', label: '投诉文本' },
  { path: '/mask', label: '隐私打码' },
  { path: '/export', label: '导出与提交' },
]

const currentPath = computed(() => route.path)
</script>

<template>
  <div class="app-root">
    <nav class="topbar">
      <div class="topbar-inner">
        <div class="brand">
          <span class="brand-mark">C</span>
          <span>ClaimCraft</span>
        </div>
        <a class="back-link" href="../claimcraft-creative.html">返回介绍页</a>
      </div>
    </nav>

    <div class="app-shell">
      <aside class="sidebar">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: currentPath === item.path }"
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
