import { useEffect, useRef, useState } from "react"
import { Link, useNavigate } from "react-router"
import { motion } from "framer-motion"
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
  UserRound,
} from "lucide-react"
import { authApi } from "@/lib/api"
import { useAuthStore } from "@/stores/auth-store"
import { authFocusRing } from "@/components/auth/AuthShell"
import { AUTH_CODE_LENGTH, buildCodeDeliveryHint, getAuthErrorMessage, isValidEmail } from "@/components/auth/auth-form-utils"
import type { EmailCodeSendResponse, PasswordResetConfirmResponse } from "@/types"

const loginTabs = [
  {
    id: "password",
    label: "账号 / 邮箱 + 密码",
    description: "使用用户名或邮箱配合密码进入案件工作区。",
  },
  {
    id: "email-code",
    label: "邮箱 + 验证码",
    description: "向已注册邮箱发送 6 位验证码，输入满位后自动登录。",
  },
] as const

type LoginMode = (typeof loginTabs)[number]["id"]

export default function LoginForm() {
  const [mode, setMode] = useState<LoginMode>("password")
  const [account, setAccount] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [passwordError, setPasswordError] = useState("")
  const [passwordLoading, setPasswordLoading] = useState(false)

  const [email, setEmail] = useState("")
  const [emailCode, setEmailCode] = useState("")
  const [emailMeta, setEmailMeta] = useState<EmailCodeSendResponse | null>(null)
  const [emailMessage, setEmailMessage] = useState("")
  const [emailError, setEmailError] = useState("")
  const [emailSending, setEmailSending] = useState(false)
  const [emailLoggingIn, setEmailLoggingIn] = useState(false)
  const lastAutoSubmittedCodeRef = useRef("")

  const [resetPanelOpen, setResetPanelOpen] = useState(false)
  const [resetEmail, setResetEmail] = useState("")
  const [resetCode, setResetCode] = useState("")
  const [resetMeta, setResetMeta] = useState<EmailCodeSendResponse | null>(null)
  const [resetMessage, setResetMessage] = useState("")
  const [resetError, setResetError] = useState("")
  const [resetSending, setResetSending] = useState(false)
  const [resetChecking, setResetChecking] = useState(false)
  const [resetVerified, setResetVerified] = useState(false)
  const [resetSubmitting, setResetSubmitting] = useState(false)
  const [resetResult, setResetResult] = useState<PasswordResetConfirmResponse | null>(null)
  const [resetNewPassword, setResetNewPassword] = useState("")
  const [resetNewPasswordConfirm, setResetNewPasswordConfirm] = useState("")
  const [showResetPassword, setShowResetPassword] = useState(false)
  const [showResetConfirmPassword, setShowResetConfirmPassword] = useState(false)
  const lastAutoResetCodeRef = useRef("")

  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const loginWithEmailCode = useAuthStore((s) => s.loginWithEmailCode)

  const showEmailCodeField = emailMeta !== null
  const showResetCodeField = resetMeta !== null
  const resetPasswordMatched = !!resetNewPasswordConfirm && resetNewPassword === resetNewPasswordConfirm
  const resetPasswordMismatch = !!resetNewPasswordConfirm && resetNewPassword !== resetNewPasswordConfirm

  function resetEmailCodeState(nextEmail: string) {
    setEmail(nextEmail)
    setEmailCode("")
    setEmailMeta(null)
    setEmailMessage("")
    setEmailError("")
    lastAutoSubmittedCodeRef.current = ""
  }

  function resetResetPasswordState(nextEmail = "") {
    setResetEmail(nextEmail)
    setResetCode("")
    setResetMeta(null)
    setResetMessage("")
    setResetError("")
    setResetVerified(false)
    setResetResult(null)
    setResetNewPassword("")
    setResetNewPasswordConfirm("")
    lastAutoResetCodeRef.current = ""
  }

  function openResetPanel() {
    setResetPanelOpen(true)
    if (!resetEmail && isValidEmail(account)) {
      resetResetPasswordState(account.trim())
    }
  }

  function closeResetPanel() {
    setResetPanelOpen(false)
    resetResetPasswordState("")
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPasswordError("")

    if (!account.trim() || !password.trim()) {
      setPasswordError("请输入账号信息和密码")
      return
    }

    setPasswordLoading(true)
    try {
      await login({ account: account.trim(), password })
      navigate("/cases", { replace: true })
    } catch (err: any) {
      setPasswordError(getAuthErrorMessage(err, "登录失败，请检查账号信息"))
    } finally {
      setPasswordLoading(false)
    }
  }

  async function handleSendEmailCode() {
    const trimmedEmail = email.trim()
    setEmailError("")
    setEmailMessage("")

    if (!isValidEmail(trimmedEmail)) {
      setEmailError("请输入有效的邮箱地址")
      return
    }

    setEmailSending(true)
    try {
      const result = await authApi.sendLoginCode({ email: trimmedEmail })
      setEmailMeta(result)
      setEmailCode("")
      setEmailMessage(buildCodeDeliveryHint(result))
      lastAutoSubmittedCodeRef.current = ""
    } catch (err: any) {
      setEmailError(getAuthErrorMessage(err, "发送登录验证码失败"))
    } finally {
      setEmailSending(false)
    }
  }

  async function handleEmailCodeLogin(trigger: "auto" | "manual") {
    if (!showEmailCodeField || emailCode.length !== AUTH_CODE_LENGTH) {
      return
    }

    if (trigger === "auto") {
      if (emailCode === lastAutoSubmittedCodeRef.current) {
        return
      }
      lastAutoSubmittedCodeRef.current = emailCode
    }

    setEmailLoggingIn(true)
    setEmailError("")
    try {
      await loginWithEmailCode({
        email: email.trim(),
        code: emailCode,
      })
      navigate("/cases", { replace: true })
    } catch (err: any) {
      setEmailError(getAuthErrorMessage(err, "验证码登录失败"))
    } finally {
      setEmailLoggingIn(false)
    }
  }

  async function handleSendResetCode() {
    const trimmedEmail = resetEmail.trim()
    setResetError("")
    setResetMessage("")
    setResetResult(null)

    if (!isValidEmail(trimmedEmail)) {
      setResetError("请输入有效的注册邮箱")
      return
    }

    setResetSending(true)
    try {
      const result = await authApi.sendPasswordResetCode({ email: trimmedEmail })
      setResetMeta(result)
      setResetCode("")
      setResetVerified(false)
      setResetMessage(buildCodeDeliveryHint(result))
      lastAutoResetCodeRef.current = ""
    } catch (err: any) {
      setResetError(getAuthErrorMessage(err, "发送重置密码验证码失败"))
    } finally {
      setResetSending(false)
    }
  }

  async function handleVerifyResetCode(trigger: "auto" | "manual") {
    if (!showResetCodeField || resetVerified || resetCode.length !== AUTH_CODE_LENGTH) {
      return
    }

    if (trigger === "auto") {
      if (resetCode === lastAutoResetCodeRef.current) {
        return
      }
      lastAutoResetCodeRef.current = resetCode
    }

    setResetChecking(true)
    setResetError("")
    try {
      const result = await authApi.verifyPasswordResetCode({
        email: resetEmail.trim(),
        code: resetCode,
      })
      setResetVerified(true)
      setResetMessage(result.detail || "邮箱验证码校验成功")
    } catch (err: any) {
      setResetVerified(false)
      setResetError(getAuthErrorMessage(err, "重置密码验证码校验失败"))
    } finally {
      setResetChecking(false)
    }
  }

  async function handleConfirmPasswordReset(event: React.FormEvent) {
    event.preventDefault()
    setResetError("")
    setResetResult(null)

    if (!isValidEmail(resetEmail)) {
      setResetError("请输入有效的注册邮箱")
      return
    }

    if (!resetVerified) {
      setResetError("请先完成邮箱验证码校验")
      return
    }

    if (!resetNewPassword.trim()) {
      setResetError("请输入新的密码")
      return
    }

    if (resetNewPassword !== resetNewPasswordConfirm) {
      setResetError("两次输入的新密码不一致")
      return
    }

    setResetSubmitting(true)
    try {
      const result = await authApi.confirmPasswordReset({
        email: resetEmail.trim(),
        new_password: resetNewPassword,
        new_password_confirm: resetNewPasswordConfirm,
      })
      setResetResult(result)
      setResetMessage(
        result.revoked_sessions > 0
          ? `${result.detail}，已撤销 ${result.revoked_sessions} 个旧会话。`
          : result.detail,
      )
      setAccount(resetEmail.trim())
      setPassword("")
      setMode("password")
      setResetCode("")
      setResetMeta(null)
      setResetVerified(false)
      setResetNewPassword("")
      setResetNewPasswordConfirm("")
      lastAutoResetCodeRef.current = ""
    } catch (err: any) {
      setResetError(getAuthErrorMessage(err, "重置密码失败"))
    } finally {
      setResetSubmitting(false)
    }
  }

  useEffect(() => {
    if (!showEmailCodeField || emailCode.length !== AUTH_CODE_LENGTH || emailLoggingIn) {
      return
    }
    void handleEmailCodeLogin("auto")
  }, [emailCode, emailLoggingIn, showEmailCodeField])

  useEffect(() => {
    if (!showResetCodeField || resetVerified || resetCode.length !== AUTH_CODE_LENGTH || resetChecking) {
      return
    }
    void handleVerifyResetCode("auto")
  }, [resetChecking, resetCode, resetVerified, showResetCodeField])

  return (
    <>
      <div className="mb-6 rounded-2xl border border-[#d9ddd5] bg-[#f5f6f2] p-1.5">
        <div className="grid grid-cols-2 gap-1.5">
          {loginTabs.map((tab) => {
            const active = mode === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setMode(tab.id)}
                className={`rounded-[14px] px-3 py-3 text-sm font-semibold transition-colors ${authFocusRing} ${
                  active
                    ? "bg-white text-[#181b1a] shadow-[0_10px_22px_rgba(31,45,38,.08)]"
                    : "text-[#6c706b] hover:bg-white/70 hover:text-[#181b1a]"
                }`}
                aria-pressed={active}
              >
                {tab.label}
              </button>
            )
          })}
        </div>
      </div>

      <p className="mb-5 text-sm leading-6 text-[#6c706b]">
        {loginTabs.find((tab) => tab.id === mode)?.description}
      </p>

      {mode === "password" ? (
        <>
          {passwordError && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              role="alert"
              className="mb-5 flex items-start gap-3 rounded-xl border border-[#e8c9c5] bg-[#fff7f5] px-4 py-3 text-sm text-[#a13f34]"
            >
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#a13f34] text-[10px] font-bold text-white">
                !
              </span>
              {passwordError}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="account" className="mb-2 block text-sm font-semibold text-[#303431]">
                账号或邮箱
              </label>
              <div className="group relative">
                <UserRound className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
                <input
                  id="account"
                  type="text"
                  value={account}
                  onChange={(event) => setAccount(event.target.value)}
                  placeholder="输入用户名或邮箱"
                  autoComplete="username"
                  autoFocus
                  className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-4 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
                />
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <label htmlFor="password" className="text-sm font-semibold text-[#303431]">
                  密码
                </label>
                <span className="text-xs text-[#8a908b]">请使用注册时设置的密码</span>
              </div>
              <div className="group relative">
                <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="输入密码"
                  autoComplete="current-password"
                  className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-12 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className={`absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-2 text-[#7a817c] transition-colors hover:bg-[#f1f2ee] hover:text-[#181b1a] ${authFocusRing}`}
                  aria-label={showPassword ? "隐藏密码" : "显示密码"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={resetPanelOpen ? closeResetPanel : openResetPanel}
                className={`text-sm font-semibold text-[#3f6b57] transition-colors hover:text-[#2f5947] ${authFocusRing}`}
              >
                {resetPanelOpen ? "收起重置密码" : "忘记密码 / 重置密码"}
              </button>
              <span className="text-xs text-[#8a908b]">需要先验证注册邮箱</span>
            </div>

            <button
              type="submit"
              disabled={passwordLoading}
              className={`group flex w-full items-center justify-center gap-3 rounded-xl bg-[#181b1a] px-4 py-3.5 text-sm font-semibold text-[#f8f8f5] shadow-[0_14px_30px_rgba(24,27,26,.18)] transition-[transform,background-color,box-shadow] hover:-translate-y-0.5 hover:bg-[#2b302d] hover:shadow-[0_18px_38px_rgba(24,27,26,.22)] active:translate-y-0 disabled:pointer-events-none disabled:opacity-60 ${authFocusRing}`}
            >
              {passwordLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在进入工作区...
                </>
              ) : (
                <>
                  登录并继续整理
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </button>
          </form>

          {resetPanelOpen && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-5 space-y-4 rounded-2xl border border-[#d9ddd5] bg-[#fcfcfa] p-4 sm:p-5"
            >
              <div>
                <p className="text-sm font-semibold text-[#303431]">通过邮箱重置密码</p>
                <p className="mt-1 text-xs leading-5 text-[#8a908b]">
                  先向已注册邮箱发送 6 位验证码，校验通过后再设置新密码。
                </p>
              </div>

              {resetMessage && (
                <motion.div
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-start gap-3 rounded-xl border border-[#cfe0d3] bg-[#f4fbf5] px-4 py-3 text-sm text-[#2f5947]"
                >
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#2f5947] text-white">
                    <Check className="h-3.5 w-3.5" />
                  </span>
                  {resetMessage}
                </motion.div>
              )}

              {resetError && (
                <motion.div
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-start gap-3 rounded-xl border border-[#e8c9c5] bg-[#fff7f5] px-4 py-3 text-sm text-[#a13f34]"
                >
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#a13f34] text-[10px] font-bold text-white">
                    !
                  </span>
                  {resetError}
                </motion.div>
              )}

              <form onSubmit={handleConfirmPasswordReset} className="space-y-4">
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <label htmlFor="reset-email" className="text-sm font-semibold text-[#303431]">
                      注册邮箱
                    </label>
                    <span className="text-xs text-[#8a908b]">仅支持已注册邮箱</span>
                  </div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <div className="group relative min-w-0 flex-1">
                      <Mail className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
                      <input
                        id="reset-email"
                        type="email"
                        value={resetEmail}
                        onChange={(event) => {
                          const nextEmail = event.target.value
                          if (nextEmail.trim().toLowerCase() !== resetEmail.trim().toLowerCase()) {
                            resetResetPasswordState(nextEmail)
                            return
                          }
                          setResetEmail(nextEmail)
                        }}
                        placeholder="输入注册邮箱"
                        autoComplete="email"
                        className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-4 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleSendResetCode()}
                      disabled={resetSending || !isValidEmail(resetEmail)}
                      className={`inline-flex shrink-0 items-center justify-center rounded-xl border border-[#cfd5cc] bg-white px-4 py-3.5 text-sm font-semibold text-[#303431] transition-colors hover:bg-[#f1f2ee] disabled:cursor-not-allowed disabled:bg-[#f5f6f2] disabled:text-[#9a9f9b] ${authFocusRing}`}
                    >
                      {resetSending ? "发送中..." : "获取验证码"}
                    </button>
                  </div>
                </div>

                {showResetCodeField && (
                  <div className="rounded-2xl border border-[#d9ddd5] bg-white p-4">
                    <div className="mb-2 flex items-center justify-between">
                      <label htmlFor="reset-code" className="text-sm font-semibold text-[#303431]">
                        邮箱验证码
                      </label>
                      <span className={`text-xs ${resetVerified ? "text-[#2f5947]" : "text-[#8a908b]"}`}>
                        {resetVerified ? "校验通过，可设置新密码" : "输入满 6 位后自动校验"}
                      </span>
                    </div>
                    <div className="group relative">
                      <ShieldCheck className={`pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 transition-colors ${resetVerified ? "text-[#2f5947]" : "text-[#8a908b] group-focus-within:text-[#3f6b57]"}`} />
                      <input
                        id="reset-code"
                        type="text"
                        inputMode="numeric"
                        maxLength={AUTH_CODE_LENGTH}
                        value={resetCode}
                        onChange={(event) => setResetCode(event.target.value.replace(/\D/g, "").slice(0, AUTH_CODE_LENGTH))}
                        placeholder="000000"
                        disabled={resetVerified}
                        className={`block w-full rounded-xl border py-3.5 pl-11 pr-12 text-sm tracking-[0.32em] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:tracking-[0.32em] focus:outline-none ${authFocusRing} ${
                          resetVerified
                            ? "border-[#d9ddd5] bg-[#f1f2ee] text-[#6c706b] caret-transparent"
                            : "border-[#d9ddd5] bg-white text-[#181b1a] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:ring-3 focus:ring-[#3f6b57]/10"
                        }`}
                      />
                      <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2">
                        {resetChecking ? (
                          <Loader2 className="h-4 w-4 animate-spin text-[#3f6b57]" />
                        ) : resetVerified ? (
                          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#2f5947] text-white">
                            <Check className="h-3.5 w-3.5" />
                          </span>
                        ) : null}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-xs leading-5 text-[#8a908b]">如未自动校验，可手动触发一次。</p>
                      <button
                        type="button"
                        onClick={() => void handleVerifyResetCode("manual")}
                        disabled={resetChecking || resetVerified || resetCode.length !== AUTH_CODE_LENGTH}
                        className={`inline-flex items-center justify-center gap-2 rounded-xl border border-[#d9ddd5] px-4 py-2.5 text-sm font-semibold text-[#303431] transition-colors hover:bg-[#f5f6f2] disabled:cursor-not-allowed disabled:opacity-60 ${authFocusRing}`}
                      >
                        {resetChecking ? "校验中..." : "手动校验验证码"}
                      </button>
                    </div>
                  </div>
                )}

                {resetVerified && (
                  <div className="space-y-4 rounded-2xl border border-[#d9ddd5] bg-white p-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label htmlFor="reset-new-password" className="mb-2 block text-sm font-semibold text-[#303431]">
                          新密码
                        </label>
                        <div className="group relative">
                          <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
                          <input
                            id="reset-new-password"
                            type={showResetPassword ? "text" : "password"}
                            value={resetNewPassword}
                            onChange={(event) => setResetNewPassword(event.target.value)}
                            placeholder="输入新密码"
                            autoComplete="new-password"
                            className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-12 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
                          />
                          <button
                            type="button"
                            onClick={() => setShowResetPassword((value) => !value)}
                            className={`absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-2 text-[#7a817c] transition-colors hover:bg-[#f1f2ee] hover:text-[#181b1a] ${authFocusRing}`}
                            aria-label={showResetPassword ? "隐藏新密码" : "显示新密码"}
                          >
                            {showResetPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>

                      <div>
                        <label htmlFor="reset-new-password-confirm" className="mb-2 block text-sm font-semibold text-[#303431]">
                          确认新密码
                        </label>
                        <div className="group relative">
                          <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
                          <input
                            id="reset-new-password-confirm"
                            type={showResetConfirmPassword ? "text" : "password"}
                            value={resetNewPasswordConfirm}
                            onChange={(event) => setResetNewPasswordConfirm(event.target.value)}
                            placeholder="再次输入新密码"
                            autoComplete="new-password"
                            className={`block w-full rounded-xl border bg-white py-3.5 pl-11 pr-20 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:outline-none focus:ring-3 ${authFocusRing} ${
                              resetPasswordMismatch
                                ? "border-[#d67f72] focus:border-[#d67f72] focus:ring-[#d67f72]/10"
                                : resetPasswordMatched
                                  ? "border-[#8ec1a0] focus:border-[#3f6b57] focus:ring-[#3f6b57]/10"
                                  : "border-[#d9ddd5] focus:border-[#3f6b57] focus:ring-[#3f6b57]/10"
                            }`}
                          />
                          {resetPasswordMatched && (
                            <span className="pointer-events-none absolute right-12 top-1/2 -translate-y-1/2">
                              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#2f5947] text-white">
                                <Check className="h-3.5 w-3.5" />
                              </span>
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() => setShowResetConfirmPassword((value) => !value)}
                            className={`absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-2 text-[#7a817c] transition-colors hover:bg-[#f1f2ee] hover:text-[#181b1a] ${authFocusRing}`}
                            aria-label={showResetConfirmPassword ? "隐藏确认新密码" : "显示确认新密码"}
                          >
                            {showResetConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                        {resetPasswordMismatch && (
                          <p className="mt-2 text-xs text-[#b2483d]">两次输入的新密码暂不一致，请继续检查。</p>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-xs leading-5 text-[#8a908b]">重置成功后，旧登录会话将按后端策略被撤销。</p>
                      <button
                        type="submit"
                        disabled={resetSubmitting || !resetPasswordMatched}
                        className={`inline-flex items-center justify-center gap-2 rounded-xl bg-[#181b1a] px-4 py-2.5 text-sm font-semibold text-[#f8f8f5] transition-colors hover:bg-[#2b302d] disabled:pointer-events-none disabled:opacity-60 ${authFocusRing}`}
                      >
                        {resetSubmitting ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            提交中...
                          </>
                        ) : (
                          "确认重置密码"
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </form>
            </motion.div>
          )}
        </>
      ) : (
        <div className="space-y-5">
          {emailMessage && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 rounded-xl border border-[#cfe0d3] bg-[#f4fbf5] px-4 py-3 text-sm text-[#2f5947]"
            >
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#2f5947] text-white">
                <Check className="h-3.5 w-3.5" />
              </span>
              {emailMessage}
            </motion.div>
          )}

          {emailError && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              role="alert"
              className="flex items-start gap-3 rounded-xl border border-[#e8c9c5] bg-[#fff7f5] px-4 py-3 text-sm text-[#a13f34]"
            >
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#a13f34] text-[10px] font-bold text-white">
                !
              </span>
              {emailError}
            </motion.div>
          )}

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label htmlFor="login-email" className="text-sm font-semibold text-[#303431]">
                邮箱
              </label>
              <span className="text-xs text-[#8a908b]">仅支持已注册邮箱</span>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="group relative min-w-0 flex-1">
                <Mail className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(event) => {
                    const nextEmail = event.target.value
                    if (nextEmail.trim().toLowerCase() !== email.trim().toLowerCase()) {
                      resetEmailCodeState(nextEmail)
                      return
                    }
                    setEmail(nextEmail)
                  }}
                  placeholder="输入注册邮箱"
                  autoComplete="email"
                  autoFocus
                  className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-4 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
                />
              </div>
              <button
                type="button"
                onClick={() => void handleSendEmailCode()}
                disabled={emailSending || !isValidEmail(email)}
                className={`inline-flex shrink-0 items-center justify-center rounded-xl border border-[#cfd5cc] bg-white px-4 py-3.5 text-sm font-semibold text-[#303431] transition-colors hover:bg-[#f1f2ee] disabled:cursor-not-allowed disabled:bg-[#f5f6f2] disabled:text-[#9a9f9b] disabled:opacity-100 ${authFocusRing}`}
              >
                {emailSending ? "发送中..." : "获取验证码"}
              </button>
            </div>
          </div>

          {showEmailCodeField && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-3 rounded-2xl border border-[#d9ddd5] bg-[#fcfcfa] p-4"
            >
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label htmlFor="login-email-code" className="text-sm font-semibold text-[#303431]">
                    6 位验证码
                  </label>
                  <span className="text-xs text-[#8a908b]">输入满位数后自动登录</span>
                </div>
                <div className="group relative">
                  <ShieldCheck className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
                  <input
                    id="login-email-code"
                    type="text"
                    inputMode="numeric"
                    maxLength={AUTH_CODE_LENGTH}
                    value={emailCode}
                    onChange={(event) => setEmailCode(event.target.value.replace(/\D/g, "").slice(0, AUTH_CODE_LENGTH))}
                    placeholder="000000"
                    className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-4 text-sm tracking-[0.32em] text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:tracking-[0.32em] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
                  />
                </div>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs leading-5 text-[#8a908b]">如未自动进入，可手动触发一次登录。</p>
                <button
                  type="button"
                  onClick={() => void handleEmailCodeLogin("manual")}
                  disabled={emailLoggingIn || emailCode.length !== AUTH_CODE_LENGTH}
                  className={`inline-flex items-center justify-center gap-2 rounded-xl bg-[#181b1a] px-4 py-2.5 text-sm font-semibold text-[#f8f8f5] transition-colors hover:bg-[#2b302d] disabled:pointer-events-none disabled:opacity-60 ${authFocusRing}`}
                >
                  {emailLoggingIn ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      登录中...
                    </>
                  ) : (
                    "使用验证码登录"
                  )}
                </button>
              </div>
            </motion.div>
          )}
        </div>
      )}

      <div className="my-8 flex items-center gap-4">
        <div className="h-px flex-1 bg-[#d9ddd5]" />
        <span className="text-xs text-[#9a9f9b]">第一次使用 ClaimCraft？</span>
        <div className="h-px flex-1 bg-[#d9ddd5]" />
      </div>
      <Link
        to="/register"
        className={`flex w-full items-center justify-center rounded-xl border border-[#cfd5cc] bg-white px-4 py-3 text-sm font-semibold text-[#303431] transition-colors hover:bg-[#f1f2ee] ${authFocusRing}`}
      >
        创建新账号
      </Link>

      <div className="mt-10 flex items-center justify-between border-t border-[#d9ddd5] pt-5 text-xs text-[#8a908b]">
        <Link to="/home" className={`inline-flex items-center gap-1.5 rounded-md hover:text-[#181b1a] ${authFocusRing}`}>
          <ArrowLeft className="h-3.5 w-3.5" />
          返回首页
        </Link>
        <span className="inline-flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-[#3f6b57]" />
          安全访问案件工作区
        </span>
      </div>
    </>
  )
}
