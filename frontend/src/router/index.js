import { createRouter, createWebHistory } from 'vue-router'

import WorkspaceView from '../views/WorkspaceView.vue'
import EvidenceView from '../views/EvidenceView.vue'
import TimelineView from '../views/TimelineView.vue'
import ComplaintView from '../views/ComplaintView.vue'
import MaskView from '../views/MaskView.vue'
import ExportView from '../views/ExportView.vue'

// 工作台路由：默认重定向到 /workspace
const routes = [
  { path: '/', redirect: '/workspace' },
  { path: '/workspace', name: 'workspace', component: WorkspaceView },
  { path: '/evidence', name: 'evidence', component: EvidenceView },
  { path: '/timeline', name: 'timeline', component: TimelineView },
  { path: '/complaint', name: 'complaint', component: ComplaintView },
  { path: '/mask', name: 'mask', component: MaskView },
  { path: '/export', name: 'export', component: ExportView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
