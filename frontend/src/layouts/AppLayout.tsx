import { useState, useEffect, useRef } from "react"
import { Outlet, useLocation, useNavigate, useParams, Link } from "react-router"
import { useAuthStore } from "@/stores/auth-store"
import { useCaseStore } from "@/stores/case-store"
import { useStatus } from "@/composables/useStatus"
import { cn } from "@/lib/utils"
import {
  Home, FileText, BarChart3, Briefcase, Image, Clock,
  MessageSquare, Shield, Download, ChevronRight, ChevronLeft, ChevronDown, LogOut,
  Menu, X, Gavel, UserRound, Settings, LayoutDashboard, Workflow, ExternalLink,
} from "lucide-react"

const sidebarNav = [
  { label: "我的案件", path: "/cases", icon: Briefcase },
  { label: "数据仪表盘", path: "/dashboard", icon: BarChart3 },
]

const caseNavComplain = [
  { label: "工作台", path: "workspace", icon: Home },
  { label: "证据管理", path: "evidence", icon: Image },
  { label: "工作流分析", path: "analysis", icon: Workflow },
  { label: "时间线", path: "timeline", icon: Clock },
  { label: "投诉文本", path: "complaint", icon: MessageSquare },
  { label: "脱敏打码", path: "mask", icon: Shield },
  { label: "导出", path: "export", icon: Download },
]

const caseNavRespond = [
  { label: "工作台", path: "workspace", icon: Home },
  { label: "证据管理", path: "evidence", icon: Image },
  { label: "工作流分析", path: "analysis", icon: Workflow },
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
  const logout = useAuthStore((s) => s.logout)
  const currentCase = useCaseStore((s) => s.currentCase)
  const { statusLabel, statusColor } = useStatus()

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [profileMenuOpen, setProfileMenuOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const profileMenuRef = useRef<HTMLDivElement>(null)

  const caseNav = currentCase?.case_mode === "respond" ? caseNavRespond : caseNavComplain

  const isActive = (path: string) => location.pathname === path
  const caseBasePath = caseId ? `/cases/${caseId}` : ""
  const userInitial = user?.username?.charAt(0).toUpperCase() || "U"

  async function handleLogout() {
    await logout()
    navigate("/login")
  }

  useEffect(() => {
    setMobileMenuOpen(false)
    setProfileMenuOpen(false)
  }, [location.pathname])

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target as Node)) {
        setProfileMenuOpen(false)
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setProfileMenuOpen(false)
    }
    document.addEventListener("mousedown", handlePointerDown)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("mousedown", handlePointerDown)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [])

  return (
    <div className="min-h-screen">
      {/* Topbar */}
      <header className="sticky top-0 z-20 border-b border-border bg-background">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between px-4 lg:px-8">
          <Link to="/home" className="flex items-center gap-2">
            <img src="/logo.webp" alt="ClaimCraft logo" className="h-8 w-8 rounded-lg object-cover" />
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
              <div ref={profileMenuRef} className="relative">
                <button
                  type="button"
                  onClick={() => setProfileMenuOpen((open) => !open)}
                  className={cn(
                    "flex items-center gap-2 rounded-xl border px-1.5 py-1 transition-all",
                    profileMenuOpen
                      ? "border-secondary/35 bg-accent shadow-sm"
                      : "border-transparent hover:border-border hover:bg-card"
                  )}
                  aria-haspopup="menu"
                  aria-expanded={profileMenuOpen}
                  aria-label="打开个人账户菜单"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary text-xs font-bold text-secondary-foreground shadow-sm">
                    {userInitial}
                  </span>
                  <span className="hidden max-w-28 truncate text-sm font-semibold text-foreground sm:block">
                    {user?.username || "用户"}
                  </span>
                  <ChevronDown className={cn("hidden h-3.5 w-3.5 text-muted-foreground transition-transform sm:block", profileMenuOpen && "rotate-180")} />
                </button>

                {profileMenuOpen && (
                  <div role="menu" className="absolute right-0 top-[calc(100%+10px)] z-50 w-72 overflow-hidden rounded-2xl border border-border bg-white shadow-[0_24px_70px_rgba(24,33,29,.18)]">
                    <div className="border-b border-border bg-[#f5f6f2] p-4">
                      <div className="flex items-center gap-3">
                        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-secondary text-sm font-bold text-secondary-foreground">
                          {userInitial}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-foreground">{user?.username || "ClaimCraft 用户"}</p>
                          <p className="mt-0.5 truncate text-xs text-muted-foreground">{user?.email || "尚未设置邮箱"}</p>
                        </div>
                      </div>
                    </div>
                    <div className="p-2">
                      <Link role="menuitem" to="/profile" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent">
                        <UserRound className="h-4 w-4 text-secondary" /><span className="flex-1">个人信息管理</span><ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                      </Link>
                      <Link role="menuitem" to="/cases" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent">
                        <Briefcase className="h-4 w-4 text-secondary" /><span className="flex-1">我的案件</span>
                      </Link>
                      <Link role="menuitem" to="/dashboard" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent">
                        <LayoutDashboard className="h-4 w-4 text-secondary" /><span className="flex-1">数据仪表盘</span>
                      </Link>
                    </div>
                    <div className="border-t border-border p-2">
                      <button role="menuitem" onClick={handleLogout} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium text-destructive transition-colors hover:bg-destructive/8">
                        <LogOut className="h-4 w-4" />退出当前账号
                      </button>
                    </div>
                  </div>
                )}
              </div>
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

      {/* 桌面端 case 左侧抽屉（全高 + 可滑出隐藏） */}
      {caseId && (
        <aside
          className={cn(
            "fixed left-0 top-14 z-10 hidden h-[calc(100vh-3.5rem)] w-72 border-r border-border bg-muted transition-transform duration-300 ease-in-out lg:block",
            sidebarCollapsed ? "-translate-x-full" : "translate-x-0"
          )}
          aria-label="案件导航抽屉"
        >
          <div className="flex h-full w-72 flex-col p-4">
            {/* 顶部操作行：折叠按钮独占一行，与案件标题错开 */}
            <div className="mb-3 flex items-center justify-between rounded-xl border border-border bg-background/60 px-3 py-2">
              <span className="text-xs font-medium text-muted-foreground">导航</span>
              <button
                type="button"
                onClick={() => setSidebarCollapsed(true)}
                className="flex items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                aria-label="收起侧边栏"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                <span>收起</span>
              </button>
            </div>

            {/* 案件标题 */}
            <div className="mb-3 flex items-center gap-2 px-2">
              <FileText className="h-5 w-5 shrink-0 text-primary" />
              <span className="truncate text-base font-semibold text-foreground">
                {currentCase?.title || "案件"}
              </span>
            </div>

            {/* 案件状态 */}
            {currentCase && (
              <div className="mb-4 px-2">
                <span className={cn(
                  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
                  statusColor(currentCase.status)
                )}>
                  {statusLabel(currentCase.status)}
                </span>
              </div>
            )}

            {/* 导航 */}
            <nav className="flex flex-1 flex-col gap-1 overflow-y-auto">
              {caseNav.map((item) => {
                const fullPath = `${caseBasePath}/${item.path}`
                const active = location.pathname === fullPath
                return (
                  <Link
                    key={item.path}
                    to={fullPath}
                    className={cn(
                      "flex items-center gap-3 rounded-xl px-4 py-2.5 text-base font-medium transition-all",
                      active
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-background/50 hover:text-foreground"
                    )}
                  >
                    <item.icon className="h-5 w-5 shrink-0" />
                    <span className="flex-1">{item.label}</span>
                    {active && <ChevronRight className="h-4 w-4 text-primary" />}
                  </Link>
                )
              })}
            </nav>

            {/* 底部声明：分析引擎基于 LangChain 开发 */}
            <a
              href="https://www.langchain.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 -mx-4 -mb-4 flex items-center gap-2 bg-background/70 px-4 py-3 text-[11px] text-muted-foreground transition-colors hover:bg-background/90 hover:text-foreground"
            >
              <span>分析工作流基于</span>
              <img
                src="/langchain-icon.svg"
                alt=""
                aria-hidden="true"
                className="h-3.5 w-3.5 shrink-0"
              />
              <span>LangChain</span>
              <span>开发</span>
              <ExternalLink className="ml-auto h-2.5 w-2.5 opacity-50" />
            </a>
          </div>
        </aside>
      )}

      {/* 折叠状态下的展开按钮 */}
      {caseId && sidebarCollapsed && (
        <button
          type="button"
          onClick={() => setSidebarCollapsed(false)}
          className="fixed left-0 top-1/2 z-10 hidden -translate-y-1/2 items-center rounded-r-full border border-l-0 border-border bg-background p-2 text-muted-foreground shadow-md transition-colors hover:bg-accent hover:text-foreground lg:flex"
          aria-label="展开侧边栏"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      )}

      {/* 主内容容器 */}
      <div className={cn(
        "mx-auto max-w-[1400px] px-4 transition-[padding] duration-300 ease-in-out lg:px-8",
        caseId && !sidebarCollapsed ? "lg:pl-80" : ""
      )}>
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
                <div className="mb-3 rounded-xl bg-muted p-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary text-xs font-bold text-secondary-foreground">{userInitial}</span>
                    <div className="min-w-0"><p className="truncate text-sm font-semibold">{user?.username || "用户"}</p><p className="truncate text-xs text-muted-foreground">{user?.email || "尚未设置邮箱"}</p></div>
                  </div>
                </div>
                {sidebarNav.map((item) => (
                  <Link key={item.path} to={item.path}
                    className={cn("rounded-lg px-3 py-2 text-sm", isActive(item.path) ? "bg-primary/8 text-primary font-medium" : "text-muted-foreground")}>
                    {item.label}
                  </Link>
                ))}
                <Link to="/profile" className={cn("flex items-center gap-2 rounded-lg px-3 py-2 text-sm", isActive("/profile") ? "bg-primary/8 text-primary font-medium" : "text-muted-foreground")}><Settings className="h-4 w-4" />个人信息管理</Link>
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

        <main className="min-w-0 pb-12 pt-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
