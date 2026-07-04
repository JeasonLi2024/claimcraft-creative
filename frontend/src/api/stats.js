import api from './index'

// 数据仪表盘聚合统计
export function fetchStats() {
  return api.get('/stats/')
}
