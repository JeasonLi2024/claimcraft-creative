import { useEffect, useState } from "react"
import { Link } from "react-router"
import {
  ArrowLeft,
  Bell,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  CircleUserRound,
  ExternalLink,
  FileText,
  KeyRound,
  Mail,
  Palette,
  ShieldCheck,
  UserRound,
} from "lucide-react"
import { useAuthStore } from "@/stores/auth-store"

const PREFERENCE_KEY = "claimcraft_profile_preferences"

interface Preferences {
  workflowReminders: boolean
  exportReminder: boolean
  compactCards: boolean
}

const defaultPreferences: Preferences = {
  workflowReminders: true,
  exportReminder: true,
  compactCards: false,
}

function SettingSwitch({ checked, onChange, label }: { checked: boolean; onChange: () => void; label: string }) {
  return (
    <button type="button" onClick={onChange} aria-label={label} aria-pressed={checked} className={`relative h-6 w-11 rounded-full transition-colors ${checked ? "bg-[#3f6b57]" : "bg-[#cfd5cc]"}`}>
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-[22px]" : "translate-x-0.5"}`} />
    </button>
  )
}

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user)
  const fetchMe = useAuthStore((s) => s.fetchMe)
  const [preferences, setPreferences] = useState<Preferences>(() => {
    try {
      const saved = localStorage.getItem(PREFERENCE_KEY)
      return saved ? { ...defaultPreferences, ...JSON.parse(saved) } : defaultPreferences
    } catch { return defaultPreferences }
  })
  const [saved, setSaved] = useState(false)

  useEffect(() => { fetchMe() }, [fetchMe])

  const initial = user?.username?.charAt(0).toUpperCase() || "U"
  const updatePreference = (key: keyof Preferences) => setPreferences((current) => ({ ...current, [key]: !current[key] }))

  function savePreferences() {
    localStorage.setItem(PREFERENCE_KEY, JSON.stringify(preferences))
    setSaved(true)
    window.setTimeout(() => setSaved(false), 1800)
  }

  return (
    <div className="space-y-6">
      <Link to="/cases" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"><ArrowLeft className="h-4 w-4" />返回我的案件</Link>

      <section className="relative overflow-hidden rounded-[26px] bg-[#18211d] p-6 text-white sm:p-8 lg:p-10">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[#557461]/35 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 left-1/3 h-64 w-64 rounded-full bg-[#9d8758]/20 blur-3xl" />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center">
          <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl border border-white/20 bg-white/10 text-3xl font-semibold shadow-xl backdrop-blur">{initial}</span>
          <div className="min-w-0 flex-1"><p className="text-xs font-semibold text-[#a9c9b7]">个人账户</p><h1 className="mt-2 truncate text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">{user?.username || "ClaimCraft 用户"}</h1><p className="mt-2 text-sm text-white/55">管理账户信息、使用偏好与安全状态。</p></div>
          <div className="rounded-xl border border-white/15 bg-white/8 px-4 py-3 text-sm backdrop-blur"><p className="text-[10px] text-white/45">账户状态</p><p className="mt-1 flex items-center gap-2 font-semibold"><ShieldCheck className="h-4 w-4 text-[#a9c9b7]" />已登录并受保护</p></div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <section className="rounded-2xl border border-border bg-white p-5 shadow-[0_10px_30px_rgba(31,45,38,.035)] sm:p-6">
            <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-foreground"><CircleUserRound className="h-5 w-5" /></span><div><h2 className="font-semibold">基本信息</h2><p className="text-xs text-muted-foreground">当前账户从服务端同步的信息</p></div></div>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl bg-[#f5f6f2] p-4"><div className="flex items-center gap-2 text-xs text-muted-foreground"><UserRound className="h-3.5 w-3.5" />用户名</div><p className="mt-2 break-all text-sm font-semibold">{user?.username || "未获取"}</p></div>
              <div className="rounded-xl bg-[#f5f6f2] p-4"><div className="flex items-center gap-2 text-xs text-muted-foreground"><Mail className="h-3.5 w-3.5" />邮箱</div><p className="mt-2 break-all text-sm font-semibold">{user?.email || "尚未设置邮箱"}</p></div>
              <div className="rounded-xl bg-[#f5f6f2] p-4"><div className="flex items-center gap-2 text-xs text-muted-foreground"><KeyRound className="h-3.5 w-3.5" />用户编号</div><p className="mt-2 text-sm font-semibold">#{user?.id || "--"}</p></div>
              <div className="rounded-xl bg-[#f5f6f2] p-4"><div className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck className="h-3.5 w-3.5" />身份状态</div><p className="mt-2 text-sm font-semibold text-[#3f6b57]">已完成身份验证</p></div>
            </div>
            <div className="mt-5 rounded-xl border border-[#e5d9bd] bg-[#fffaf0] p-4 text-xs leading-5 text-[#77623d]">当前后端只提供个人信息读取能力。用户名、邮箱、头像和密码修改入口需要后端补充接口后才能开放。</div>
          </section>

          <section className="rounded-2xl border border-border bg-white p-5 shadow-[0_10px_30px_rgba(31,45,38,.035)] sm:p-6">
            <div className="flex items-center justify-between"><div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-foreground"><Palette className="h-5 w-5" /></span><div><h2 className="font-semibold">使用偏好</h2><p className="text-xs text-muted-foreground">仅保存在当前浏览器，可立即生效</p></div></div>{saved && <span className="flex items-center gap-1 text-xs font-semibold text-[#3f6b57]"><Check className="h-3.5 w-3.5" />已保存</span>}</div>
            <div className="mt-6 divide-y divide-border">
              {[{ key: "workflowReminders" as const, icon: Bell, title: "工作流提醒", text: "在案件需要复核或继续处理时显示提示" }, { key: "exportReminder" as const, icon: FileText, title: "导出前安全提醒", text: "导出材料前提示检查敏感信息" }, { key: "compactCards" as const, icon: BriefcaseBusiness, title: "紧凑案件卡片", text: "减少案件列表卡片的纵向信息密度" }].map(({ key, icon: Icon, title, text }) => <div key={key} className="flex items-center gap-4 py-4 first:pt-0 last:pb-0"><Icon className="h-5 w-5 shrink-0 text-secondary" /><div className="min-w-0 flex-1"><p className="text-sm font-semibold">{title}</p><p className="mt-1 text-xs text-muted-foreground">{text}</p></div><SettingSwitch checked={preferences[key]} onChange={() => updatePreference(key)} label={title} /></div>)}
            </div>
            <button onClick={savePreferences} className="mt-6 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-[#2b302d]">保存偏好设置</button>
          </section>
        </div>

        <aside className="space-y-4">
          <section className="rounded-2xl border border-border bg-white p-5">
            <p className="text-xs font-semibold text-secondary">快捷入口</p>
            <div className="mt-3 space-y-1"><Link to="/cases" className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium hover:bg-accent"><BriefcaseBusiness className="h-4 w-4 text-secondary" /><span className="flex-1">我的案件</span><ChevronRight className="h-4 w-4 text-muted-foreground" /></Link><Link to="/dashboard" className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium hover:bg-accent"><FileText className="h-4 w-4 text-secondary" /><span className="flex-1">数据仪表盘</span><ChevronRight className="h-4 w-4 text-muted-foreground" /></Link></div>
          </section>
          <section className="rounded-2xl bg-[#e7eee9] p-5"><ShieldCheck className="h-6 w-6 text-[#2f5947]" /><h3 className="mt-5 font-semibold text-[#26362e]">账户安全建议</h3><p className="mt-2 text-xs leading-5 text-[#566c60]">请勿与他人共享登录令牌；在公共设备完成操作后及时退出账号。</p></section>
          <a href="mailto:support@claimcraft.local" className="flex items-center gap-3 rounded-2xl border border-border bg-white p-5 text-sm font-medium transition-colors hover:bg-[#f5f6f2]"><Mail className="h-4 w-4 text-secondary" /><span className="flex-1">联系产品支持</span><ExternalLink className="h-4 w-4 text-muted-foreground" /></a>
        </aside>
      </div>
    </div>
  )
}
