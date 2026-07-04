<script setup>
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// 当前案件上下文（在案件相关路由下存在）
const caseId = computed(() => route.params.caseId)

// 公共路由（登录/注册）不渲染应用外壳
const isPublicRoute = computed(() => !!route.meta.public)
const isAuthenticated = computed(() => authStore.isAuthenticated)
const currentUser = computed(() => authStore.user)

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

// 品牌点击跳转：已登录 → /cases，未登录 → /login
const brandTarget = computed(() => (isAuthenticated.value ? '/cases' : '/login'))

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app-root">
    <!-- 公共页面（登录/注册）：不渲染顶部栏与侧边栏 -->
    <template v-if="isPublicRoute">
      <main class="main-content">
        <router-view />
      </main>
    </template>

    <!-- 受保护页面：渲染顶部栏 + 侧边栏 -->
    <template v-else>
      <nav class="topbar">
        <div class="topbar-inner">
          <router-link :to="brandTarget" class="brand brand-link">
            <span class="brand-mark">C</span>
            <span>ClaimCraft</span>
          </router-link>
          <div class="topbar-actions">
            <template v-if="isAuthenticated">
              <router-link to="/dashboard" class="my-cases-link">数据仪表盘</router-link>
              <router-link to="/cases" class="my-cases-link">我的案件</router-link>
              <span class="user-name">{{ currentUser?.username || currentUser?.email || '用户' }}</span>
              <button class="btn btn-secondary logout-btn" @click="handleLogout">退出</button>
              <a class="back-link" href="../claimcraft-creative.html">返回介绍页</a>
            </template>
            <template v-else>
              <router-link to="/login" class="my-cases-link">登录</router-link>
              <router-link to="/register" class="my-cases-link">注册</router-link>
              <a class="back-link" href="../claimcraft-creative.html">返回介绍页</a>
            </template>
          </div>
        </div>
      </nav>

      <div class="app-shell" :class="{ 'no-sidebar': !isAuthenticated }">
        <aside v-if="isAuthenticated" class="sidebar">
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
    </template>
  </div>
</template>
