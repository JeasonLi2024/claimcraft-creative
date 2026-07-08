import { lazy, useState, useEffect } from "react"
import { Outlet, useLocation, useNavigate, useParams, Link } from "react-router"
import { useAuthStore } from "@/stores/auth-store"
import { useCaseStore } from "@/stores/case-store"
import { useStatus } from "@/composables/useStatus"
import { cn } from "@/lib/utils"
import {
  Home, FileText, BarChart3, Briefcase, Image, Clock,
  MessageSquare, Shield, Download, ChevronRight, LogOut,
  Menu, X, Gavel,
} from "lucide-react"

const sidebarNav = [
  { label: "我的案件", path: "/cases", icon: Briefcase },
  { label: "数据仪表盘", path: "/dashboard", icon: BarChart3 },
]

const caseNavComplain = [
  { label: "工作台", path: "workspace", icon: Home },
  { label: "证据管理", path: "evidence", icon: Image },
  { label: "时间线", path: "timeline", icon: Clock },
  { label: "投诉文本", path: "complaint", icon: MessageSquare },
  { label: "脱敏打码", path: "mask", icon: Shield },
  { label: "导出", path: "export", icon: Download },
]

const caseNavRespond = [
  { label: "工作台", path: "workspace", icon: Home },
  { label: "证据管理", path: "evidence", icon: Image },
  { label: "时间线", path: "timeline", icon: Clock },
  { label: "反证答辩", path: "respond", icon: Gavel },
  { label: "脱敏打码", path: "mask", icon: Shield },
  { label: "导出", path: "export", icon: Download },
]

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = useParams()
  const caseId = params.caseId

  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const currentCase = useCaseStore((s) => s.currentCase)
  const { statusLabel, statusColor } = useStatus()

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const caseNav = currentCase?.case_mode === "respond" ? caseNavRespond : caseNavComplain

  const isActive = (path: string) => location.pathname === path
  const caseBasePath = caseId ? `/cases/${caseId}` : ""
  const userInitial = user?.username?.charAt(0).toUpperCase() || "U"

  function handleLogout() {
    clearAuth()
    navigate("/login")
  }

  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  return (
    <div className="min-h-screen">
      {/* Topbar */}
      <header className="sticky top-0 z-20 border-b border-border bg-background">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between px-4 lg:px-8">
          <Link to={isAuthenticated ? "/cases" : "/login"} className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
              C
            </div>
            <span className="text-lg font-bold tracking-tight text-foreground">ClaimCraft</span>
          </Link>

          <nav className="hidden items-center gap-1 md:flex">
            {sidebarNav.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  isActive(item.path)
                    ? "bg-primary/8 text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            {isAuthenticated && (
              <>
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary text-xs font-bold text-secondary-foreground">
                  {userInitial}
                </div>
                <button
                  onClick={handleLogout}
                  className="hidden rounded-lg px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground md:block"
                  title="退出登录"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </>
            )}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="rounded-lg p-2 text-muted-foreground hover:bg-accent md:hidden"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
        <div className="h-[2px] bg-secondary/30" />
      </header>

      <div className="mx-auto flex max-w-[1400px] gap-6 px-4 lg:px-8">
        {caseId && (
          <aside className="sticky top-[86px] hidden w-52 shrink-0 self-start rounded-2xl bg-muted p-3 lg:block">
            <div className="mb-2 flex items-center gap-1.5 px-2">
              <FileText className="h-4 w-4 text-primary" />
              <span className="truncate text-sm font-semibold text-foreground">
                {currentCase?.title || "案件"}
              </span>
            </div>
            {currentCase && (
              <div className="mb-3 px-2">
                <span className={cn(
                  "inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
                  statusColor(currentCase.status)
                )}>
                  {statusLabel(currentCase.status)}
                </span>
              </div>
            )}
            <nav className="flex flex-col gap-0.5">
              {caseNav.map((item) => {
                const fullPath = `${caseBasePath}/${item.path}`
                const active = location.pathname === fullPath
                return (
                  <Link
                    key={item.path}
                    to={fullPath}
                    className={cn(
                      "flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition-all",
                      active
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-background/50 hover:text-foreground"
                    )}
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                    {active && <ChevronRight className="ml-auto h-3.5 w-3.5 text-primary" />}
                  </Link>
                )
              })}
            </nav>
          </aside>
        )}

        {/* Mobile nav overlay */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-30 lg:hidden" onClick={() => setMobileMenuOpen(false)}>
            <div className="absolute inset-0 bg-black/30" />
            <aside className="absolute right-0 top-0 h-full w-64 bg-white p-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
              <div className="mb-4 flex items-center justify-between">
                <span className="font-bold text-foreground">导航</span>
                <button onClick={() => setMobileMenuOpen(false)}><X className="h-5 w-5" /></button>
              </div>
              <nav className="flex flex-col gap-1">
                {sidebarNav.map((item) => (
                  <Link key={item.path} to={item.path}
                    className={cn("rounded-lg px-3 py-2 text-sm", isActive(item.path) ? "bg-primary/8 text-primary font-medium" : "text-muted-foreground")}>
                    {item.label}
                  </Link>
                ))}
                {caseId && caseNav.map((item) => (
                  <Link key={item.path} to={`${caseBasePath}/${item.path}`}
                    className={cn("rounded-lg px-3 py-2 text-sm", isActive(`${caseBasePath}/${item.path}`) ? "bg-primary/8 text-primary font-medium" : "text-muted-foreground")}>
                    {item.label}
                  </Link>
                ))}
              </nav>
            </aside>
          </div>
        )}

        <main className="min-w-0 flex-1 pb-12 pt-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
