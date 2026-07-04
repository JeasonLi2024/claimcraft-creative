import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

import CaseListView from '../views/CaseListView.vue'
import WorkspaceView from '../views/WorkspaceView.vue'
import EvidenceView from '../views/EvidenceView.vue'
import TimelineView from '../views/TimelineView.vue'
import ComplaintView from '../views/ComplaintView.vue'
import MaskView from '../views/MaskView.vue'
import ExportView from '../views/ExportView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'

// T1 路由：根路径重定向到案件列表，所有案件相关视图通过 :caseId 进入
// T26 新增：登录/注册路由（public），路由守卫拦截未认证访问
const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/register', name: 'register', component: RegisterView, meta: { public: true } },
  { path: '/', redirect: '/cases' },
  { path: '/cases', name: 'cases', component: CaseListView },
  { path: '/dashboard', name: 'dashboard', component: DashboardView },
  { path: '/cases/:caseId/workspace', name: 'workspace', component: WorkspaceView },
  { path: '/cases/:caseId/evidence', name: 'evidence', component: EvidenceView },
  { path: '/cases/:caseId/timeline', name: 'timeline', component: TimelineView },
  { path: '/cases/:caseId/complaint', name: 'complaint', component: ComplaintView },
  { path: '/cases/:caseId/mask', name: 'mask', component: MaskView },
  { path: '/cases/:caseId/export', name: 'export', component: ExportView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：未认证访问受保护路由 → 跳转登录
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  if (to.meta.public || authStore.isAuthenticated) {
    next()
  } else {
    next('/login')
  }
})

export default router
