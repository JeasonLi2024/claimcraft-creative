import { useEffect, useMemo, useRef, useState } from "react"
import { Link, useNavigate } from "react-router"
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
  Loader2,
  LogOut,
  Mail,
  Palette,
  RefreshCcw,
  ShieldCheck,
  Smartphone,
  Trash2,
  Upload,
  UserRound,
} from "lucide-react"
import { authApi } from "@/lib/api"
import { AUTH_CODE_LENGTH, getAuthErrorMessage } from "@/components/auth/auth-form-utils"
import PasswordRuleChecklist from "@/components/auth/PasswordRuleChecklist"
import { useAuthStore } from "@/stores/auth-store"
import type { EmailCodeSendResponse, UserPreferences, UserSession } from "@/types"

type ProfileFormState = {
  display_name: string
  bio: string
  locale: string
  timezone: string
}

const defaultPreferences: UserPreferences = {
  workflow_reminders: true,
  export_reminder: true,
  compact_case_cards: false,
  default_case_mode: "complain",
  default_template_type: "platform",
}

function SettingSwitch({ checked, onChange, label, disabled = false }: { checked: boolean; onChange: () => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onChange}
      disabled={disabled}
      aria-label={label}
      aria-pressed={checked}
      className={`relative h-6 w-11 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${checked ? "bg-[#3f6b57]" : "bg-[#cfd5cc]"}`}
    >
      <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-5" : "translate-x-0"}`} />
    </button>
  )
}

function formatDate(value?: string | null) {
  if (!value) return "暂无记录"
  return new Date(value).toLocaleString("zh-CN")
}

function getErrorMessage(err: any, fallback: string) {
  const data = err?.response?.data
  if (data?.detail) return data.detail
  if (Array.isArray(data?.avatar) && data.avatar[0]) return data.avatar[0]
  if (Array.isArray(data?.code) && data.code[0]) return data.code[0]
  if (Array.isArray(data?.new_email) && data.new_email[0]) return data.new_email[0]
  return err?.message || fallback
}

function buildSendCodeSummary(result: EmailCodeSendResponse) {
  return `${result.detail}，目标邮箱：${result.target_email}，有效期至 ${formatDate(result.expires_at)}。`
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const fetchMe = useAuthStore((s) => s.fetchMe)
  const setUser = useAuthStore((s) => s.setUser)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const currentSessionId = useAuthStore((s) => s.currentSessionId)

  const [profileForm, setProfileForm] = useState<ProfileFormState>({
    display_name: "",
    bio: "",
    locale: "zh-CN",
    timezone: "Asia/Shanghai",
  })
  const [preferences, setPreferences] = useState<UserPreferences>(defaultPreferences)
  const [sessions, setSessions] = useState<UserSession[]>([])
  const [loading, setLoading] = useState(true)
  const [profileSaving, setProfileSaving] = useState(false)
  const [preferenceSaving, setPreferenceSaving] = useState(false)
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [sessionLoading, setSessionLoading] = useState(false)
  const [logoutAllLoading, setLogoutAllLoading] = useState(false)
  const [savedSection, setSavedSection] = useState<"profile" | "preferences" | null>(null)
  const [pageError, setPageError] = useState("")
  const [passwordError, setPasswordError] = useState("")
  const [passwordSuccess, setPasswordSuccess] = useState("")
  const [avatarMessage, setAvatarMessage] = useState("")
  const [avatarError, setAvatarError] = useState("")
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [avatarDeleting, setAvatarDeleting] = useState(false)
  const [currentEmailCode, setCurrentEmailCode] = useState("")
  const [currentEmailMeta, setCurrentEmailMeta] = useState<EmailCodeSendResponse | null>(null)
  const [currentEmailMessage, setCurrentEmailMessage] = useState("")
  const [currentEmailError, setCurrentEmailError] = useState("")
  const [currentEmailSending, setCurrentEmailSending] = useState(false)
  const [currentEmailVerifying, setCurrentEmailVerifying] = useState(false)
  const [changePasswordCode, setChangePasswordCode] = useState("")
  const [changePasswordCodeMeta, setChangePasswordCodeMeta] = useState<EmailCodeSendResponse | null>(null)
  const [changePasswordCodeMessage, setChangePasswordCodeMessage] = useState("")
  const [changePasswordCodeError, setChangePasswordCodeError] = useState("")
  const [changePasswordCodeSending, setChangePasswordCodeSending] = useState(false)
  const [changePasswordCodeVerifying, setChangePasswordCodeVerifying] = useState(false)
  const [changePasswordCodeVerified, setChangePasswordCodeVerified] = useState(false)
  const [changeEmailForm, setChangeEmailForm] = useState({
    new_email: "",
    code: "",
  })
  const [changeEmailMeta, setChangeEmailMeta] = useState<EmailCodeSendResponse | null>(null)
  const [changeEmailMessage, setChangeEmailMessage] = useState("")
  const [changeEmailError, setChangeEmailError] = useState("")
  const [changeEmailRequesting, setChangeEmailRequesting] = useState(false)
  const [changeEmailConfirming, setChangeEmailConfirming] = useState(false)
  const [passwordForm, setPasswordForm] = useState({
    old_password: "",
    new_password: "",
    new_password_confirm: "",
    logout_other_sessions: true,
  })
  const lastAutoVerifiedChangePasswordCodeRef = useRef("")

  useEffect(() => {
    async function bootstrap() {
      setLoading(true)
      setPageError("")
      try {
        await fetchMe()
        const [preferencesData, sessionData] = await Promise.all([
          authApi.getPreferences(),
          authApi.listSessions(),
        ])
        setPreferences(preferencesData)
        setSessions(sessionData)
      } catch (err: any) {
        setPageError(getErrorMessage(err, "加载账户中心失败"))
      } finally {
        setLoading(false)
      }
    }

    void bootstrap()
  }, [fetchMe])

  useEffect(() => {
    if (!user) return
    setProfileForm({
      display_name: user.display_name || user.username,
      bio: user.bio || "",
      locale: user.locale || "zh-CN",
      timezone: user.timezone || "Asia/Shanghai",
    })
    setPreferences(user.preferences || defaultPreferences)
  }, [user])

  useEffect(() => {
    setChangePasswordCode("")
    setChangePasswordCodeMeta(null)
    setChangePasswordCodeMessage("")
    setChangePasswordCodeError("")
    setChangePasswordCodeVerified(false)
    lastAutoVerifiedChangePasswordCodeRef.current = ""
  }, [user?.email])

  useEffect(() => {
    if (
      !changePasswordCodeMeta
      || changePasswordCodeVerified
      || changePasswordCode.length !== AUTH_CODE_LENGTH
      || changePasswordCodeVerifying
    ) {
      return
    }
    void handleVerifyChangePasswordCode("auto")
  }, [
    changePasswordCode,
    changePasswordCodeMeta,
    changePasswordCodeVerified,
    changePasswordCodeVerifying,
  ])

  const initial = user?.display_name?.charAt(0).toUpperCase() || user?.username?.charAt(0).toUpperCase() || "U"
  const currentSession = useMemo(
    () => sessions.find((session) => session.id === currentSessionId) || sessions.find((session) => session.is_current),
    [currentSessionId, sessions],
  )

  const passwordConfirmMatched =
    !!passwordForm.new_password_confirm && passwordForm.new_password === passwordForm.new_password_confirm
  const passwordConfirmMismatch =
    !!passwordForm.new_password_confirm && passwordForm.new_password !== passwordForm.new_password_confirm

  function markSaved(section: "profile" | "preferences") {
    setSavedSection(section)
    window.setTimeout(() => setSavedSection(null), 1800)
  }

  function resetChangePasswordVerificationState() {
    setChangePasswordCode("")
    setChangePasswordCodeMeta(null)
    setChangePasswordCodeMessage("")
    setChangePasswordCodeError("")
    setChangePasswordCodeVerified(false)
    lastAutoVerifiedChangePasswordCodeRef.current = ""
  }

  function updatePreference(key: keyof UserPreferences, value?: boolean | UserPreferences["default_case_mode"] | UserPreferences["default_template_type"]) {
    setPreferences((current) => ({
      ...current,
      [key]: value ?? (!current[key as keyof UserPreferences] as never),
    }))
  }

  async function reloadSessions() {
    setSessionLoading(true)
    setPageError("")
    try {
      setSessions(await authApi.listSessions())
    } catch (err: any) {
      setPageError(getErrorMessage(err, "获取会话列表失败"))
    } finally {
      setSessionLoading(false)
    }
  }

  async function handleProfileSave(e: React.FormEvent) {
    e.preventDefault()
    setProfileSaving(true)
    setPageError("")
    try {
      const nextUser = await authApi.updateMe(profileForm)
      setUser(nextUser)
      markSaved("profile")
    } catch (err: any) {
      setPageError(getErrorMessage(err, "保存个人资料失败"))
    } finally {
      setProfileSaving(false)
    }
  }

  async function handlePreferenceSave() {
    setPreferenceSaving(true)
    setPageError("")
    try {
      const nextPreferences = await authApi.updatePreferences(preferences)
      setPreferences(nextPreferences)
      if (user) {
        setUser({ ...user, preferences: nextPreferences })
      }
      markSaved("preferences")
    } catch (err: any) {
      setPageError(getErrorMessage(err, "保存偏好失败"))
    } finally {
      setPreferenceSaving(false)
    }
  }

  async function handlePasswordChange(e: React.FormEvent) {
    e.preventDefault()
    if (!changePasswordCodeVerified) {
      setPasswordError("请先完成当前邮箱验证码校验，再提交修改密码")
      setPasswordSuccess("")
      return
    }

    setPasswordSaving(true)
    setPasswordError("")
    setPasswordSuccess("")
    try {
      const result = await authApi.changePassword({
        ...passwordForm,
        current_session_id: currentSessionId,
      })
      setPasswordForm({
        old_password: "",
        new_password: "",
        new_password_confirm: "",
        logout_other_sessions: true,
      })
      resetChangePasswordVerificationState()
      setPasswordSuccess(
        passwordForm.logout_other_sessions
          ? `密码已更新，已撤销 ${result.revoked_other_sessions} 个其他设备会话`
          : "密码已更新",
      )
      await reloadSessions()
    } catch (err: any) {
      const data = err.response?.data
      setPasswordError(
        data?.old_password?.[0]
          || data?.new_password?.[0]
          || data?.new_password_confirm?.[0]
          || data?.detail
          || err.message
          || "修改密码失败",
      )
    } finally {
      setPasswordSaving(false)
    }
  }

  async function handleSendChangePasswordCode() {
    setChangePasswordCodeSending(true)
    setChangePasswordCodeError("")
    setChangePasswordCodeMessage("")
    setPasswordError("")
    try {
      const result = await authApi.sendChangePasswordCode()
      setChangePasswordCodeMeta(result)
      setChangePasswordCode("")
      setChangePasswordCodeVerified(false)
      setChangePasswordCodeMessage(buildSendCodeSummary(result))
      lastAutoVerifiedChangePasswordCodeRef.current = ""
    } catch (err: any) {
      setChangePasswordCodeError(getAuthErrorMessage(err, "发送修改密码验证码失败"))
    } finally {
      setChangePasswordCodeSending(false)
    }
  }

  async function handleVerifyChangePasswordCode(trigger: "auto" | "manual") {
    if (changePasswordCodeVerified || changePasswordCode.length !== AUTH_CODE_LENGTH) {
      return
    }

    if (trigger === "auto") {
      if (changePasswordCode === lastAutoVerifiedChangePasswordCodeRef.current) {
        return
      }
      lastAutoVerifiedChangePasswordCodeRef.current = changePasswordCode
    }

    setChangePasswordCodeVerifying(true)
    setChangePasswordCodeError("")
    try {
      const result = await authApi.verifyChangePasswordCode({ code: changePasswordCode })
      setChangePasswordCodeVerified(true)
      setChangePasswordCodeMessage(result.detail || "邮箱验证码校验成功")
    } catch (err: any) {
      setChangePasswordCodeVerified(false)
      setChangePasswordCodeError(getAuthErrorMessage(err, "修改密码验证码校验失败"))
    } finally {
      setChangePasswordCodeVerifying(false)
    }
  }

  async function handleRevokeSession(sessionId: number) {
    setSessionLoading(true)
    setPageError("")
    try {
      await authApi.revokeSession(sessionId)
      await reloadSessions()
      if (sessionId === currentSessionId) {
        clearAuth()
        navigate("/login", { replace: true })
      }
    } catch (err: any) {
      setPageError(getErrorMessage(err, "撤销会话失败"))
      setSessionLoading(false)
    }
  }

  async function handleLogoutAll() {
    setLogoutAllLoading(true)
    setPageError("")
    try {
      await authApi.logoutAll()
      clearAuth()
      navigate("/login", { replace: true })
    } catch (err: any) {
      setPageError(getErrorMessage(err, "退出全部设备失败"))
    } finally {
      setLogoutAllLoading(false)
    }
  }

  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return

    setAvatarUploading(true)
    setAvatarError("")
    setAvatarMessage("")
    try {
      const result = await authApi.uploadAvatar(file)
      setUser(result.user)
      setAvatarMessage(result.detail)
    } catch (err: any) {
      setAvatarError(getErrorMessage(err, "头像上传失败"))
    } finally {
      setAvatarUploading(false)
    }
  }

  async function handleAvatarDelete() {
    setAvatarDeleting(true)
    setAvatarError("")
    setAvatarMessage("")
    try {
      const result = await authApi.deleteAvatar()
      setUser(result.user)
      setAvatarMessage(result.detail)
    } catch (err: any) {
      setAvatarError(getErrorMessage(err, "头像删除失败"))
    } finally {
      setAvatarDeleting(false)
    }
  }

  async function handleSendCurrentEmailCode() {
    setCurrentEmailSending(true)
    setCurrentEmailError("")
    setCurrentEmailMessage("")
    try {
      const result = await authApi.sendCurrentEmailCode()
      setCurrentEmailMeta(result)
      setCurrentEmailMessage(buildSendCodeSummary(result))
    } catch (err: any) {
      setCurrentEmailError(getErrorMessage(err, "发送当前邮箱验证码失败"))
    } finally {
      setCurrentEmailSending(false)
    }
  }

  async function handleVerifyCurrentEmail(e: React.FormEvent) {
    e.preventDefault()
    setCurrentEmailVerifying(true)
    setCurrentEmailError("")
    setCurrentEmailMessage("")
    try {
      const result = await authApi.verifyCurrentEmailCode({ code: currentEmailCode })
      setUser(result.user)
      setCurrentEmailCode("")
      setCurrentEmailMeta(null)
      setCurrentEmailMessage(result.detail)
    } catch (err: any) {
      setCurrentEmailError(getErrorMessage(err, "当前邮箱验证失败"))
    } finally {
      setCurrentEmailVerifying(false)
    }
  }

  async function handleRequestEmailChange(e: React.FormEvent) {
    e.preventDefault()
    setChangeEmailRequesting(true)
    setChangeEmailError("")
    setChangeEmailMessage("")
    try {
      const result = await authApi.requestEmailChange({ new_email: changeEmailForm.new_email })
      setChangeEmailMeta(result)
      setChangeEmailForm((current) => ({ ...current, new_email: result.target_email, code: "" }))
      setChangeEmailMessage(buildSendCodeSummary(result))
    } catch (err: any) {
      setChangeEmailError(getErrorMessage(err, "发送新邮箱验证码失败"))
    } finally {
      setChangeEmailRequesting(false)
    }
  }

  async function handleConfirmEmailChange(e: React.FormEvent) {
    e.preventDefault()
    setChangeEmailConfirming(true)
    setChangeEmailError("")
    setChangeEmailMessage("")
    try {
      const result = await authApi.confirmEmailChange(changeEmailForm)
      setUser(result.user)
      setChangeEmailForm({ new_email: "", code: "" })
      setChangeEmailMeta(null)
      setChangeEmailMessage(result.detail)
    } catch (err: any) {
      setChangeEmailError(getErrorMessage(err, "确认新邮箱失败"))
    } finally {
      setChangeEmailConfirming(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/cases" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />
        返回我的案件
      </Link>

      <section className="relative overflow-hidden rounded-[26px] bg-[#18211d] p-6 text-white sm:p-8 lg:p-10">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[#557461]/35 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 left-1/3 h-64 w-64 rounded-full bg-[#9d8758]/20 blur-3xl" />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center">
          <span className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-white/20 bg-white/10 text-3xl font-semibold shadow-xl backdrop-blur">
            {user?.avatar_url ? (
              <img src={user.avatar_url} alt="用户头像" className="h-full w-full object-cover" />
            ) : (
              initial
            )}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-[#a9c9b7]">个人账户</p>
            <h1 className="mt-2 truncate text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
              {user?.display_name || user?.username || "ClaimCraft 用户"}
            </h1>
            <p className="mt-2 text-sm text-white/55">管理账户资料、头像、邮箱验证、密码与设备会话。</p>
          </div>
          <div className="rounded-xl border border-white/15 bg-white/8 px-4 py-3 text-sm backdrop-blur">
            <p className="text-[10px] text-white/45">当前会话</p>
            <p className="mt-1 flex items-center gap-2 font-semibold">
              <ShieldCheck className="h-4 w-4 text-[#a9c9b7]" />
              {currentSession?.device_name || "已登录并受保护"}
            </p>
          </div>
        </div>
      </section>

      {pageError && (
        <div className="rounded-xl border border-[#e9c8c3] bg-[#fff6f4] px-4 py-3 text-sm text-[#ad4438]">
          {pageError}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <section className="rounded-2xl border border-border bg-white p-5 shadow-[0_10px_30px_rgba(31,45,38,.035)] sm:p-6">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                <CircleUserRound className="h-5 w-5" />
              </span>
              <div>
                <h2 className="font-semibold">基本信息</h2>
                <p className="text-xs text-muted-foreground">来自服务端的账户资料，可直接保存</p>
              </div>
            </div>

            <div className="mt-6 rounded-2xl border border-[#d9ddd5] bg-[#fcfcfa] p-4 sm:p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-4">
                  <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-[#e7eee9] text-2xl font-semibold text-[#2f5947]">
                    {user?.avatar_url ? (
                      <img src={user.avatar_url} alt="头像预览" className="h-full w-full object-cover" />
                    ) : (
                      initial
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[#26312b]">头像管理</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      支持 `jpg / jpeg / png / webp`。上传后系统会自动生成展示图。
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      最近更新：{formatDate(user?.avatar_updated_at)}
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-[#d9ddd5] px-4 py-2.5 text-sm font-semibold transition-colors hover:bg-[#f5f6f2]">
                    {avatarUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                    {avatarUploading ? "上传中..." : user?.avatar_url ? "更换头像" : "上传头像"}
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      disabled={avatarUploading || avatarDeleting}
                      onChange={(e) => void handleAvatarChange(e)}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => void handleAvatarDelete()}
                    disabled={!user?.avatar_url || avatarUploading || avatarDeleting}
                    className="inline-flex items-center gap-2 rounded-xl border border-[#e7c8c4] px-4 py-2.5 text-sm font-semibold text-[#b2483d] transition-colors hover:bg-[#fff6f4] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {avatarDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    删除头像
                  </button>
                </div>
              </div>

              {avatarMessage && (
                <div className="mt-4 rounded-xl border border-[#cfe0d3] bg-[#f4fbf5] px-4 py-3 text-sm text-[#2f5947]">
                  {avatarMessage}
                </div>
              )}
              {avatarError && (
                <div className="mt-4 rounded-xl border border-[#e9c8c3] bg-[#fff6f4] px-4 py-3 text-sm text-[#ad4438]">
                  {avatarError}
                </div>
              )}
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl bg-[#f5f6f2] p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground"><UserRound className="h-3.5 w-3.5" />用户名</div>
                <p className="mt-2 break-all text-sm font-semibold">{user?.username || "未获取"}</p>
              </div>
              <div className="rounded-xl bg-[#f5f6f2] p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground"><Mail className="h-3.5 w-3.5" />邮箱</div>
                <p className="mt-2 break-all text-sm font-semibold">{user?.email || "尚未设置邮箱"}</p>
              </div>
              <div className="rounded-xl bg-[#f5f6f2] p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck className="h-3.5 w-3.5" />邮箱验证</div>
                <p className={`mt-2 text-sm font-semibold ${user?.email_verified ? "text-[#3f6b57]" : "text-[#b2483d]"}`}>
                  {user?.email_verified ? "已验证" : "未验证"}
                </p>
              </div>
              <div className="rounded-xl bg-[#f5f6f2] p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground"><KeyRound className="h-3.5 w-3.5" />最近登录</div>
                <p className="mt-2 text-sm font-semibold">{formatDate(user?.last_login)}</p>
              </div>
            </div>

            <form onSubmit={handleProfileSave} className="mt-5 grid gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-2 block text-sm font-semibold">显示名称</label>
                  <input
                    value={profileForm.display_name}
                    onChange={(e) => setProfileForm((current) => ({ ...current, display_name: e.target.value }))}
                    className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold">时区</label>
                  <input
                    value={profileForm.timezone}
                    onChange={(e) => setProfileForm((current) => ({ ...current, timezone: e.target.value }))}
                    className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10"
                  />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-2 block text-sm font-semibold">语言区域</label>
                  <input
                    value={profileForm.locale}
                    onChange={(e) => setProfileForm((current) => ({ ...current, locale: e.target.value }))}
                    className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold">注册时间</label>
                  <div className="rounded-xl border border-[#d9ddd5] bg-[#f8f8f5] px-4 py-3 text-sm text-[#555d58]">
                    {formatDate(user?.date_joined)}
                  </div>
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold">个人简介</label>
                <textarea
                  rows={3}
                  value={profileForm.bio}
                  onChange={(e) => setProfileForm((current) => ({ ...current, bio: e.target.value }))}
                  className="w-full resize-none rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10"
                />
              </div>
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-muted-foreground">用户名保持只读。邮箱验证与修改入口在下方“邮箱验证”模块中处理。</p>
                <button type="submit" disabled={profileSaving} className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-[#2b302d] disabled:opacity-60">
                  {profileSaving ? "保存中..." : savedSection === "profile" ? "已保存" : "保存资料"}
                </button>
              </div>
            </form>
          </section>

          <section className="rounded-2xl border border-border bg-white p-5 shadow-[0_10px_30px_rgba(31,45,38,.035)] sm:p-6">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                <Mail className="h-5 w-5" />
              </span>
              <div>
                <h2 className="font-semibold">邮箱验证</h2>
                <p className="text-xs text-muted-foreground">支持验证当前邮箱，以及对新邮箱发码并在确认后正式替换。</p>
              </div>
            </div>

            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-[#d9ddd5] bg-[#fcfcfa] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-[#26312b]">验证当前邮箱</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      当前邮箱：{user?.email || "未绑定邮箱"}
                    </p>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${user?.email_verified ? "bg-[#e7eee9] text-[#2f5947]" : "bg-[#fff3f0] text-[#b2483d]"}`}>
                    {user?.email_verified ? "已验证" : "待验证"}
                  </span>
                </div>

                {currentEmailMessage && (
                  <div className="mt-4 rounded-xl border border-[#cfe0d3] bg-[#f4fbf5] px-4 py-3 text-sm text-[#2f5947]">
                    {currentEmailMessage}
                  </div>
                )}
                {currentEmailError && (
                  <div className="mt-4 rounded-xl border border-[#e9c8c3] bg-[#fff6f4] px-4 py-3 text-sm text-[#ad4438]">
                    {currentEmailError}
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => void handleSendCurrentEmailCode()}
                  disabled={!user?.email || currentEmailSending}
                  className="mt-4 rounded-xl border border-[#d9ddd5] px-4 py-2.5 text-sm font-semibold transition-colors hover:bg-[#f5f6f2] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {currentEmailSending ? "发送中..." : "发送验证码"}
                </button>

                {currentEmailMeta && (
                  <p className="mt-3 text-xs leading-5 text-muted-foreground">
                    已通过 `{currentEmailMeta.provider}` 发送，验证码有效至 {formatDate(currentEmailMeta.expires_at)}。
                  </p>
                )}

                <form onSubmit={handleVerifyCurrentEmail} className="mt-4 space-y-3">
                  <div>
                    <label className="mb-2 block text-sm font-semibold">输入 6 位验证码</label>
                    <input
                      value={currentEmailCode}
                      maxLength={6}
                      onChange={(e) => setCurrentEmailCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                      className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm tracking-[0.3em] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10"
                      placeholder="000000"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={currentEmailVerifying || currentEmailCode.length !== 6}
                    className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-[#2b302d] disabled:opacity-60"
                  >
                    {currentEmailVerifying ? "验证中..." : "确认验证当前邮箱"}
                  </button>
                </form>
              </div>

              <div className="rounded-2xl border border-[#d9ddd5] bg-[#fcfcfa] p-4">
                <div>
                  <p className="text-sm font-semibold text-[#26312b]">修改为新邮箱</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    新邮箱验证通过前，系统正式邮箱仍保持为当前值，不会提前改写。
                  </p>
                </div>

                {changeEmailMessage && (
                  <div className="mt-4 rounded-xl border border-[#cfe0d3] bg-[#f4fbf5] px-4 py-3 text-sm text-[#2f5947]">
                    {changeEmailMessage}
                  </div>
                )}
                {changeEmailError && (
                  <div className="mt-4 rounded-xl border border-[#e9c8c3] bg-[#fff6f4] px-4 py-3 text-sm text-[#ad4438]">
                    {changeEmailError}
                  </div>
                )}

                <form onSubmit={handleRequestEmailChange} className="mt-4 space-y-3">
                  <div>
                    <label className="mb-2 block text-sm font-semibold">新邮箱地址</label>
                    <input
                      type="email"
                      value={changeEmailForm.new_email}
                      onChange={(e) => setChangeEmailForm((current) => ({ ...current, new_email: e.target.value }))}
                      className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10"
                      placeholder="new-mail@example.com"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={changeEmailRequesting || !changeEmailForm.new_email.trim()}
                    className="rounded-xl border border-[#d9ddd5] px-4 py-2.5 text-sm font-semibold transition-colors hover:bg-[#f5f6f2] disabled:opacity-60"
                  >
                    {changeEmailRequesting ? "发送中..." : "向新邮箱发送验证码"}
                  </button>
                </form>

                {changeEmailMeta && (
                  <p className="mt-3 text-xs leading-5 text-muted-foreground">
                    新邮箱验证码已通过 `{changeEmailMeta.provider}` 发送，有效至 {formatDate(changeEmailMeta.expires_at)}。
                  </p>
                )}

                <form onSubmit={handleConfirmEmailChange} className="mt-4 space-y-3">
                  <div>
                    <label className="mb-2 block text-sm font-semibold">确认验证码</label>
                    <input
                      value={changeEmailForm.code}
                      maxLength={6}
                      onChange={(e) => setChangeEmailForm((current) => ({ ...current, code: e.target.value.replace(/\D/g, "").slice(0, 6) }))}
                      className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm tracking-[0.3em] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10"
                      placeholder="000000"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={changeEmailConfirming || changeEmailForm.code.length !== 6 || !changeEmailForm.new_email.trim()}
                    className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-[#2b302d] disabled:opacity-60"
                  >
                    {changeEmailConfirming ? "确认中..." : "确认切换到新邮箱"}
                  </button>
                </form>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-border bg-white p-5 shadow-[0_10px_30px_rgba(31,45,38,.035)] sm:p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                  <Palette className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="font-semibold">使用偏好</h2>
                  <p className="text-xs text-muted-foreground">现在直接保存在服务端，可跨设备同步</p>
                </div>
              </div>
              {savedSection === "preferences" && <span className="flex items-center gap-1 text-xs font-semibold text-[#3f6b57]"><Check className="h-3.5 w-3.5" />已保存</span>}
            </div>

            <div className="mt-6 divide-y divide-border">
              {[
                { key: "workflow_reminders" as const, icon: Bell, title: "工作流提醒", text: "在案件需要复核或继续处理时显示提示" },
                { key: "export_reminder" as const, icon: FileText, title: "导出前安全提醒", text: "导出材料前提示检查敏感信息" },
                { key: "compact_case_cards" as const, icon: BriefcaseBusiness, title: "紧凑案件卡片", text: "减少案件列表卡片的纵向信息密度" },
              ].map(({ key, icon: Icon, title, text }) => (
                <div key={key} className="flex items-center gap-4 py-4 first:pt-0 last:pb-0">
                  <Icon className="h-5 w-5 shrink-0 text-secondary" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold">{title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{text}</p>
                  </div>
                  <SettingSwitch checked={preferences[key]} onChange={() => updatePreference(key)} label={title} disabled={preferenceSaving} />
                </div>
              ))}
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-2 block text-sm font-semibold">默认案件模式</label>
                <select
                  value={preferences.default_case_mode}
                  onChange={(e) => updatePreference("default_case_mode", e.target.value as UserPreferences["default_case_mode"])}
                  className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none"
                >
                  <option value="complain">维权投诉</option>
                  <option value="respond">商家反证</option>
                </select>
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold">默认文稿模板</label>
                <select
                  value={preferences.default_template_type}
                  onChange={(e) => updatePreference("default_template_type", e.target.value as UserPreferences["default_template_type"])}
                  className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none"
                >
                  <option value="platform">平台客服版</option>
                  <option value="regulatory">监管投诉版</option>
                  <option value="arbitration">仲裁准备版</option>
                </select>
              </div>
            </div>

            <button onClick={handlePreferenceSave} disabled={preferenceSaving} className="mt-6 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-[#2b302d] disabled:opacity-60">
              {preferenceSaving ? "保存中..." : "保存偏好设置"}
            </button>
          </section>

          <section className="rounded-2xl border border-border bg-white p-5 shadow-[0_10px_30px_rgba(31,45,38,.035)] sm:p-6">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                <KeyRound className="h-5 w-5" />
              </span>
              <div>
                <h2 className="font-semibold">密码与安全</h2>
                <p className="text-xs text-muted-foreground">修改密码前需先完成当前邮箱验证码校验，并可让其他设备失效</p>
              </div>
            </div>

            {passwordError && <div className="mt-5 rounded-xl border border-[#e9c8c3] bg-[#fff6f4] px-4 py-3 text-sm text-[#ad4438]">{passwordError}</div>}
            {passwordSuccess && <div className="mt-5 rounded-xl border border-[#cfe0d3] bg-[#f4fbf5] px-4 py-3 text-sm text-[#2f5947]">{passwordSuccess}</div>}

            <div className="mt-6 rounded-2xl border border-[#d9ddd5] bg-[#fcfcfa] p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-sm font-semibold text-[#26312b]">步骤 1：验证当前邮箱</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    将验证码发送到当前绑定邮箱 `{user?.email || "未绑定邮箱"}`，校验通过后才允许提交新密码。
                  </p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${changePasswordCodeVerified ? "bg-[#e7eee9] text-[#2f5947]" : "bg-[#fff3f0] text-[#b2483d]"}`}>
                  {changePasswordCodeVerified ? "已通过校验" : "待校验"}
                </span>
              </div>

              {changePasswordCodeMessage && (
                <div className="mt-4 rounded-xl border border-[#cfe0d3] bg-[#f4fbf5] px-4 py-3 text-sm text-[#2f5947]">
                  {changePasswordCodeMessage}
                </div>
              )}

              {changePasswordCodeError && (
                <div className="mt-4 rounded-xl border border-[#e9c8c3] bg-[#fff6f4] px-4 py-3 text-sm text-[#ad4438]">
                  {changePasswordCodeError}
                </div>
              )}

              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
                <button
                  type="button"
                  onClick={() => void handleSendChangePasswordCode()}
                  disabled={!user?.email || changePasswordCodeSending}
                  className="rounded-xl border border-[#d9ddd5] px-4 py-2.5 text-sm font-semibold transition-colors hover:bg-[#f5f6f2] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {changePasswordCodeSending ? "发送中..." : changePasswordCodeVerified ? "重新发送验证码" : "发送验证码"}
                </button>
                {changePasswordCodeMeta && (
                  <p className="text-xs leading-5 text-muted-foreground">
                    已通过 `{changePasswordCodeMeta.provider}` 发送，验证码有效至 {formatDate(changePasswordCodeMeta.expires_at)}。
                  </p>
                )}
              </div>

              {changePasswordCodeMeta && (
                <div className="mt-4">
                  <div className="mb-2 flex items-center justify-between">
                    <label className="text-sm font-semibold">6 位验证码</label>
                    <span className={`text-xs ${changePasswordCodeVerified ? "text-[#2f5947]" : "text-[#8a908b]"}`}>
                      {changePasswordCodeVerified ? "校验通过" : "输入满 6 位后自动校验"}
                    </span>
                  </div>
                  <div className="relative">
                    <input
                      value={changePasswordCode}
                      maxLength={AUTH_CODE_LENGTH}
                      disabled={changePasswordCodeVerified}
                      onChange={(e) => setChangePasswordCode(e.target.value.replace(/\D/g, "").slice(0, AUTH_CODE_LENGTH))}
                      className={`w-full rounded-xl border px-4 py-3 pr-12 text-sm tracking-[0.3em] focus:outline-none focus:ring-3 ${
                        changePasswordCodeVerified
                          ? "border-[#d9ddd5] bg-[#f1f2ee] text-[#6c706b] caret-transparent"
                          : "border-[#d9ddd5] bg-white focus:border-[#3f6b57] focus:ring-[#3f6b57]/10"
                      }`}
                      placeholder="000000"
                    />
                    <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2">
                      {changePasswordCodeVerifying ? (
                        <Loader2 className="h-4 w-4 animate-spin text-[#3f6b57]" />
                      ) : changePasswordCodeVerified ? (
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#2f5947] text-white">
                          <Check className="h-3.5 w-3.5" />
                        </span>
                      ) : null}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs leading-5 text-muted-foreground">如未自动校验，可手动再验证一次。</p>
                    <button
                      type="button"
                      onClick={() => void handleVerifyChangePasswordCode("manual")}
                      disabled={changePasswordCodeVerifying || changePasswordCodeVerified || changePasswordCode.length !== AUTH_CODE_LENGTH}
                      className="rounded-xl border border-[#d9ddd5] px-4 py-2.5 text-sm font-semibold transition-colors hover:bg-[#f5f6f2] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {changePasswordCodeVerifying ? "验证中..." : "手动验证验证码"}
                    </button>
                  </div>
                </div>
              )}
            </div>

            <form onSubmit={handlePasswordChange} className="mt-6 grid gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-2 block text-sm font-semibold">当前密码</label>
                  <input
                    type="password"
                    value={passwordForm.old_password}
                    onChange={(e) => setPasswordForm((current) => ({ ...current, old_password: e.target.value }))}
                    className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold">新密码</label>
                  <input
                    type="password"
                    value={passwordForm.new_password}
                    onChange={(e) => setPasswordForm((current) => ({ ...current, new_password: e.target.value }))}
                    className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10"
                  />
                  {passwordForm.new_password && (
                    <div className="mt-3 rounded-xl border border-[#e6e8e2] bg-[#f7f8f4] px-4 py-3">
                      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#7a817c]">密码要求</p>
                      <PasswordRuleChecklist
                        password={passwordForm.new_password}
                        username={user?.username || ""}
                        email={user?.email || ""}
                      />
                    </div>
                  )}
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold">确认新密码</label>
                <input
                  type="password"
                  value={passwordForm.new_password_confirm}
                  onChange={(e) => setPasswordForm((current) => ({ ...current, new_password_confirm: e.target.value }))}
                  className={`w-full rounded-xl border bg-white px-4 py-3 text-sm focus:outline-none focus:ring-3 ${
                    passwordConfirmMismatch
                      ? "border-[#d67f72] focus:border-[#d67f72] focus:ring-[#d67f72]/10"
                      : passwordConfirmMatched
                        ? "border-[#8ec1a0] focus:border-[#3f6b57] focus:ring-[#3f6b57]/10"
                        : "border-[#d9ddd5] focus:border-[#3f6b57] focus:ring-[#3f6b57]/10"
                  }`}
                />
                {passwordConfirmMismatch && (
                  <p className="mt-2 text-xs text-[#b2483d]">两次输入的新密码暂不一致，请继续检查。</p>
                )}
                {passwordConfirmMatched && (
                  <p className="mt-2 inline-flex items-center gap-1 text-xs text-[#2f5947]">
                    <Check className="h-3.5 w-3.5" />
                    两次输入的新密码一致
                  </p>
                )}
              </div>
              <label className="flex items-center gap-3 rounded-xl bg-[#f5f6f2] px-4 py-3 text-sm">
                <input
                  type="checkbox"
                  checked={passwordForm.logout_other_sessions}
                  onChange={(e) => setPasswordForm((current) => ({ ...current, logout_other_sessions: e.target.checked }))}
                  className="h-4 w-4 rounded border-[#c7cdc6] text-[#3f6b57] focus:ring-[#3f6b57]"
                />
                修改密码后让其他设备会话失效
              </label>
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={passwordSaving || !changePasswordCodeVerified || passwordForm.new_password !== passwordForm.new_password_confirm}
                  className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-[#2b302d] disabled:opacity-60"
                >
                  {passwordSaving ? "提交中..." : "更新密码"}
                </button>
              </div>
            </form>
          </section>

          <section className="rounded-2xl border border-border bg-white p-5 shadow-[0_10px_30px_rgba(31,45,38,.035)] sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                  <Smartphone className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="font-semibold">设备会话</h2>
                  <p className="text-xs text-muted-foreground">查看活跃或近期设备，并支持单设备撤销</p>
                </div>
              </div>
              <button onClick={() => void reloadSessions()} disabled={sessionLoading} className="inline-flex items-center gap-2 rounded-xl border border-[#d9ddd5] px-3 py-2 text-sm font-medium hover:bg-[#f5f6f2] disabled:opacity-60">
                <RefreshCcw className={`h-4 w-4 ${sessionLoading ? "animate-spin" : ""}`} />
                刷新
              </button>
            </div>

            <div className="mt-6 space-y-3">
              {sessions.length === 0 && <div className="rounded-xl bg-[#f5f6f2] px-4 py-3 text-sm text-muted-foreground">暂无设备会话记录</div>}
              {sessions.map((session) => (
                <div key={session.id} className="flex flex-col gap-3 rounded-2xl border border-[#d9ddd5] bg-[#fcfcfa] p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-[#26312b]">{session.device_name || `会话 #${session.id}`}</p>
                      {session.is_current && <span className="rounded-full bg-[#e7eee9] px-2 py-0.5 text-[11px] font-semibold text-[#2f5947]">当前设备</span>}
                      {session.revoked_at && <span className="rounded-full bg-[#fff3f0] px-2 py-0.5 text-[11px] font-semibold text-[#b2483d]">已撤销</span>}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">类型：{session.device_type || "unknown"} · 最近活动：{formatDate(session.last_seen_at)}</p>
                    <p className="mt-1 text-xs text-muted-foreground">创建时间：{formatDate(session.created_at)} · 过期时间：{formatDate(session.expires_at)}</p>
                  </div>
                  {!session.revoked_at && (
                    <button
                      onClick={() => void handleRevokeSession(session.id)}
                      disabled={sessionLoading}
                      className="rounded-xl border border-[#e7c8c4] px-3 py-2 text-sm font-semibold text-[#b2483d] transition-colors hover:bg-[#fff6f4] disabled:opacity-60"
                    >
                      撤销此设备
                    </button>
                  )}
                </div>
              ))}
            </div>
          </section>
        </div>

        <aside className="space-y-4">
          <section className="rounded-2xl border border-border bg-white p-5">
            <p className="text-xs font-semibold text-secondary">快捷入口</p>
            <div className="mt-3 space-y-1">
              <Link to="/cases" className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium hover:bg-accent">
                <BriefcaseBusiness className="h-4 w-4 text-secondary" />
                <span className="flex-1">我的案件</span>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </Link>
              <Link to="/dashboard" className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium hover:bg-accent">
                <FileText className="h-4 w-4 text-secondary" />
                <span className="flex-1">数据仪表盘</span>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </Link>
            </div>
          </section>

          <section className="rounded-2xl bg-[#e7eee9] p-5">
            <ShieldCheck className="h-6 w-6 text-[#2f5947]" />
            <h3 className="mt-5 font-semibold text-[#26362e]">账户安全建议</h3>
            <p className="mt-2 text-xs leading-5 text-[#566c60]">公共设备完成操作后，请尽快退出当前设备或执行“退出全部设备”。</p>
            <button onClick={() => void handleLogoutAll()} disabled={logoutAllLoading} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#26362e] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#31453b] disabled:opacity-60">
              {logoutAllLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
              退出全部设备
            </button>
          </section>

          <a href="mailto:support@claimcraft.local" className="flex items-center gap-3 rounded-2xl border border-border bg-white p-5 text-sm font-medium transition-colors hover:bg-[#f5f6f2]">
            <Mail className="h-4 w-4 text-secondary" />
            <span className="flex-1">联系产品支持</span>
            <ExternalLink className="h-4 w-4 text-muted-foreground" />
          </a>
        </aside>
      </div>
    </div>
  )
}
