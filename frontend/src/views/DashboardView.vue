<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import * as echarts from 'echarts'
import { useCaseStore } from '../stores/case'

const caseStore = useCaseStore()
const pieChartRef = ref(null)
const statusChartRef = ref(null)
const trendChartRef = ref(null)
const transitionChartRef = ref(null)
let charts = []

const caseTypeLabels = {
  shopping: '网购纠纷',
  service: '服务违约',
  secondhand: '二手交易',
  other: '其他',
}
const statusLabels = {
  draft: '草稿',
  processing: '处理中',
  submitted: '已提交',
  closed: '已结案',
  cancelled: '已取消',
}
const statusColors = {
  draft: '#9ca3af',
  processing: '#2f6bff',
  submitted: '#f59e0b',
  closed: '#11b981',
  cancelled: '#ef4444',
}

const stats = computed(() => caseStore.stats || {})

// 处理中案件数：从 status_distribution 中提取 status=processing 的 count
const processingCount = computed(() => {
  const dist = stats.value.status_distribution || []
  const item = dist.find((d) => d.status === 'processing')
  return item ? item.count : 0
})

function initCharts() {
  if (!caseStore.stats) return

  // 饼图：案件类型分布
  if (pieChartRef.value) {
    const chart = echarts.init(pieChartRef.value)
    const data = (caseStore.stats.case_type_distribution || []).map((item) => ({
      name: caseTypeLabels[item.case_type] || item.case_type,
      value: item.count,
    }))
    chart.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, textStyle: { fontSize: 12 } },
      color: ['#2f6bff', '#11b981', '#f59e0b', '#ef4444'],
      series: [
        {
          type: 'pie',
          radius: ['40%', '65%'],
          label: { show: true, formatter: '{b}: {c}' },
          data,
        },
      ],
    })
    charts.push(chart)
  }

  // 柱状图：状态分布
  if (statusChartRef.value) {
    const chart = echarts.init(statusChartRef.value)
    const data = (caseStore.stats.status_distribution || []).map((item) => ({
      name: statusLabels[item.status] || item.status,
      value: item.count,
      itemStyle: { color: statusColors[item.status] || '#2f6bff' },
    }))
    chart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: data.map((d) => d.name) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [{ type: 'bar', data, barWidth: '50%' }],
    })
    charts.push(chart)
  }

  // 折线图：30 天趋势
  if (trendChartRef.value) {
    const chart = echarts.init(trendChartRef.value)
    const data = caseStore.stats.cases_recent_30days || []
    chart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: data.map((d) => d.day) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'line',
          data: data.map((d) => d.count),
          smooth: true,
          areaStyle: { color: 'rgba(47, 107, 255, 0.15)' },
          lineStyle: { color: '#2f6bff', width: 2 },
          itemStyle: { color: '#2f6bff' },
        },
      ],
    })
    charts.push(chart)
  }

  // 柱状图：状态转换统计
  if (transitionChartRef.value) {
    const chart = echarts.init(transitionChartRef.value)
    const data = caseStore.stats.status_transitions || []
    chart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: data.map((d) => statusLabels[d.to_status] || d.to_status),
      },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'bar',
          data: data.map((d) => d.count),
          itemStyle: { color: '#11b981' },
          barWidth: '50%',
        },
      ],
    })
    charts.push(chart)
  }
}

function handleResize() {
  charts.forEach((c) => c.resize())
}

onMounted(async () => {
  await caseStore.fetchStats()
  await nextTick()
  initCharts()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  charts.forEach((c) => c.dispose())
  charts = []
})
</script>

<template>
  <div class="dashboard-view">
    <h1>数据仪表盘</h1>

    <!-- 顶部统计卡片 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-value">{{ stats.case_total || 0 }}</div>
        <div class="stat-label">案件总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.evidence_total || 0 }}</div>
        <div class="stat-label">证据总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.extracted_field_total || 0 }}</div>
        <div class="stat-label">抽取字段总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ processingCount }}</div>
        <div class="stat-label">处理中案件数</div>
      </div>
    </div>

    <!-- 图表网格 2x2 -->
    <div class="chart-grid">
      <div class="chart-card">
        <h3>案件类型分布</h3>
        <div ref="pieChartRef" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <h3>案件状态分布</h3>
        <div ref="statusChartRef" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <h3>最近 30 天案件创建趋势</h3>
        <div ref="trendChartRef" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <h3>状态转换统计</h3>
        <div ref="transitionChartRef" class="chart-container"></div>
      </div>
    </div>
  </div>
</template>
