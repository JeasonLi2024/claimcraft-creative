import { useEffect } from "react"
import { useCaseStore } from "@/stores/case-store"
import HeroSection from "@/components/HeroSection"
import { useStatus, STATUS_COLOR } from "@/composables/useStatus"
import { Briefcase, FileText, Layers, Loader2, TrendingUp } from "lucide-react"
import {
  PieChart, Pie, Cell, BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts"

const CHART_COLORS = ["#d6d5c2", "#5e4545", "#b0b3a2", "#9b965f", "#f79b45"]

export default function DashboardPage() {
  const fetchStats = useCaseStore((s) => s.fetchStats)
  const stats = useCaseStore((s) => s.stats)
  const loading = useCaseStore((s) => s.loading)
  const { statusLabel } = useStatus()

  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  const statCards = stats
    ? [
        { label: "案件总数", value: stats.case_total, icon: Briefcase, color: "text-primary" },
        { label: "证据总数", value: stats.evidence_total, icon: FileText, color: "text-accent2-foreground" },
        { label: "抽取字段", value: stats.extracted_field_total, icon: Layers, color: "text-secondary" },
        { label: "处理中", value: stats.status_distribution?.find((s: any) => s.status === "processing")?.count || 0, icon: TrendingUp, color: "text-primary" },
      ]
    : []

  const caseTypeData = stats?.case_type_distribution?.map((item: any) => ({
    name: item.case_type || "未知",
    value: item.count,
  })) || []

  const statusKeys = Object.keys(STATUS_COLOR)
  const statusData = stats?.status_distribution?.map((item: any) => ({
    name: statusLabel(item.status),
    count: item.count,
    fill: CHART_COLORS[statusKeys.indexOf(item.status)] || "#9b965f",
  })) || []

  const trendData = stats?.cases_recent_30days?.map((item: any) => ({
    day: item.day?.slice(5) || "",
    count: item.count,
  })) || []

  const transitionData = stats?.status_transitions?.map((item: any) => ({
    name: statusLabel(item.to_status),
    count: item.count,
  })) || []

  return (
    <div className="space-y-6">
      <HeroSection title="数据仪表盘" subtitle="洞察案件分布与处理趋势" />

      {/* Stat Cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {statCards.map((card, i) => (
          <div
            key={i}
            className="rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{card.label}</span>
              <card.icon className={`h-5 w-5 ${card.color}`} />
            </div>
            <div className={`mt-2 text-3xl font-bold ${card.color}`}>{card.value}</div>
          </div>
        ))}
      </div>

      {/* Loading */}
      {loading && !stats && (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      )}

      {/* Charts Grid */}
      {stats && (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Case Type Pie */}
          {caseTypeData.length > 0 && (
            <div className="rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
              <h3 className="mb-4 text-sm font-semibold text-foreground">案件类型分布</h3>
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie data={caseTypeData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} innerRadius={60} paddingAngle={2}>
                    {caseTypeData.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Status Bar */}
          {statusData.length > 0 && (
            <div className="rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
              <h3 className="mb-4 text-sm font-semibold text-foreground">案件状态分布</h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={statusData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="count" name="案件数" radius={[6, 6, 0, 0]}>
                    {statusData.map((entry: any, i: number) => (
                      <Cell key={i} fill={entry.fill || CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Trend Line */}
          {trendData.length > 0 && (
            <div className="rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
              <h3 className="mb-4 text-sm font-semibold text-foreground">近 30 天趋势</h3>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="count" name="新案件" stroke="#9b965f" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Transition Bar */}
          {transitionData.length > 0 && (
            <div className="rounded-2xl border border-border/50 bg-card p-5 shadow-[0_10px_30px_rgba(20,35,90,.04)]">
              <h3 className="mb-4 text-sm font-semibold text-foreground">状态转换统计</h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={transitionData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={60} />
                  <Tooltip />
                  <Bar dataKey="count" name="转换次数" fill="#9b965f" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* No data */}
      {!loading && stats && statCards.every((c) => c.value === 0) && (
        <div className="rounded-2xl border border-border/50 bg-card p-12 text-center text-muted-foreground">
          <p className="text-lg font-semibold text-foreground">暂无数据</p>
          <p className="mt-1">创建案件并添加证据后，数据将在此展示</p>
        </div>
      )}
    </div>
  )
}
