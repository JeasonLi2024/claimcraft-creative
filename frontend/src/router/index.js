import { createRouter, createWebHistory } from 'vue-router'

import CaseListView from '../views/CaseListView.vue'
import WorkspaceView from '../views/WorkspaceView.vue'
import EvidenceView from '../views/EvidenceView.vue'
import TimelineView from '../views/TimelineView.vue'
import ComplaintView from '../views/ComplaintView.vue'
import MaskView from '../views/MaskView.vue'
import ExportView from '../views/ExportView.vue'

// T1 路由：根路径重定向到案件列表，所有案件相关视图通过 :caseId 进入
const routes = [
  { path: '/', redirect: '/cases' },
  { path: '/cases', name: 'cases', component: CaseListView },
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

export default router
