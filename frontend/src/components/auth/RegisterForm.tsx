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
import PasswordRuleChecklist from "@/components/auth/PasswordRuleChecklist"
import { AUTH_CODE_LENGTH, buildCodeDeliveryHint, getAuthErrorMessage, isValidEmail } from "@/components/auth/auth-form-utils"
import type { EmailCodeSendResponse } from "@/types"

export default function RegisterForm() {
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [verificationCode, setVerificationCode] = useState("")
  const [verificationMeta, setVerificationMeta] = useState<EmailCodeSendResponse | null>(null)
  const [verificationMessage, setVerificationMessage] = useState("")
  const [verificationError, setVerificationError] = useState("")
  const [verificationSending, setVerificationSending] = useState(false)
  const [verificationChecking, setVerificationChecking] = useState(false)
  const [emailVerified, setEmailVerified] = useState(false)
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const lastAutoVerifiedCodeRef = useRef("")
  const navigate = useNavigate()
  const register = useAuthStore((s) => s.register)

  const showVerificationField = verificationMeta !== null
  const confirmPasswordMatched = !!confirmPassword && password === confirmPassword
  const confirmPasswordMismatch = !!confirmPassword && password !== confirmPassword

  function resetEmailVerificationState(nextEmail: string) {
    setEmail(nextEmail)
    setVerificationCode("")
    setVerificationMeta(null)
    setVerificationMessage("")
    setVerificationError("")
    setVerificationSending(false)
    setVerificationChecking(false)
    setEmailVerified(false)
    lastAutoVerifiedCodeRef.current = ""
  }

  async function handleSendVerificationCode() {
    const trimmedEmail = email.trim()
    setError("")
    setVerificationError("")
    setVerificationMessage("")

    if (!isValidEmail(trimmedEmail)) {
      setVerificationError("请输入有效的邮箱地址")
      return
    }

    setVerificationSending(true)
    try {
      const result = await authApi.sendRegisterCode({ email: trimmedEmail })
      setVerificationMeta(result)
      setVerificationCode("")
      setVerificationMessage(buildCodeDeliveryHint(result))
      setEmailVerified(false)
      lastAutoVerifiedCodeRef.current = ""
    } catch (err: any) {
      setVerificationError(getAuthErrorMessage(err, "发送注册验证码失败"))
    } finally {
      setVerificationSending(false)
    }
  }

  async function handleVerifyCode(trigger: "auto" | "manual") {
    if (!showVerificationField || emailVerified || verificationCode.length !== AUTH_CODE_LENGTH) {
      return
    }

    if (trigger === "auto") {
      if (verificationCode === lastAutoVerifiedCodeRef.current) {
        return
      }
      lastAutoVerifiedCodeRef.current = verificationCode
    }

    setVerificationChecking(true)
    setVerificationError("")
    try {
      const result = await authApi.verifyRegisterCode({
        email: email.trim(),
        code: verificationCode,
      })
      setEmailVerified(true)
      setVerificationMessage(result.detail || "邮箱验证成功")
    } catch (err: any) {
      setEmailVerified(false)
      setVerificationError(getAuthErrorMessage(err, "验证码校验失败"))
    } finally {
      setVerificationChecking(false)
    }
  }

  useEffect(() => {
    if (!showVerificationField || emailVerified || verificationCode.length !== AUTH_CODE_LENGTH || verificationChecking) {
      return
    }
    void handleVerifyCode("auto")
  }, [emailVerified, showVerificationField, verificationChecking, verificationCode])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError("")

    if (!username.trim() || !email.trim() || !password.trim()) {
      setError("请填写所有字段")
      return
    }

    if (!emailVerified) {
      setError("请先完成邮箱验证码校验")
      return
    }

    if (password !== confirmPassword) {
      setError("两次输入的密码不一致")
      return
    }

    if (password.length < 8) {
      setError("密码至少需要 8 个字符")
      return
    }

    setLoading(true)
    try {
      await register({
        username: username.trim(),
        email: email.trim(),
        password,
        password_confirm: confirmPassword,
      })
      navigate("/cases", { replace: true })
    } catch (err: any) {
      setError(getAuthErrorMessage(err, "注册失败"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          role="alert"
          className="mb-5 flex items-start gap-3 rounded-xl border border-[#e8c9c5] bg-[#fff7f5] px-4 py-3 text-sm text-[#a13f34]"
        >
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#a13f34] text-[10px] font-bold text-white">
            !
          </span>
          {error}
        </motion.div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <label htmlFor="register-username" className="mb-2 block text-sm font-semibold text-[#303431]">
            用户名
          </label>
          <div className="group relative">
            <UserRound className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
            <input
              id="register-username"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="输入用户名"
              autoComplete="username"
              autoFocus
              className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-4 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
            />
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <label htmlFor="register-email" className="text-sm font-semibold text-[#303431]">
              邮箱
            </label>
            <span className="text-xs text-[#8a908b]">用于账号通知与验证</span>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="group relative min-w-0 flex-1">
              <Mail className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
              <input
                id="register-email"
                type="email"
                value={email}
                onChange={(event) => {
                  const nextEmail = event.target.value
                  if (nextEmail.trim().toLowerCase() !== email.trim().toLowerCase()) {
                    resetEmailVerificationState(nextEmail)
                    return
                  }
                  setEmail(nextEmail)
                }}
                placeholder="输入邮箱"
                autoComplete="email"
                className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-4 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
              />
            </div>
            <button
              type="button"
              onClick={() => void handleSendVerificationCode()}
              disabled={verificationSending || emailVerified || !isValidEmail(email)}
              className={`inline-flex shrink-0 items-center justify-center rounded-xl border px-4 py-3.5 text-sm font-semibold transition-colors ${authFocusRing} ${
                emailVerified
                  ? "cursor-not-allowed border-[#d9ddd5] bg-[#f1f2ee] text-[#8a908b]"
                  : "border-[#cfd5cc] bg-white text-[#303431] hover:bg-[#f1f2ee] disabled:cursor-not-allowed disabled:bg-[#f5f6f2] disabled:text-[#9a9f9b]"
              }`}
            >
              {verificationSending ? "发送中..." : emailVerified ? "已验证" : "获取验证码"}
            </button>
          </div>

          {verificationMessage && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-3 flex items-start gap-3 rounded-xl border border-[#cfe0d3] bg-[#f4fbf5] px-4 py-3 text-sm text-[#2f5947]"
            >
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#2f5947] text-white">
                <Check className="h-3.5 w-3.5" />
              </span>
              {verificationMessage}
            </motion.div>
          )}

          {verificationError && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-3 flex items-start gap-3 rounded-xl border border-[#e8c9c5] bg-[#fff7f5] px-4 py-3 text-sm text-[#a13f34]"
            >
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#a13f34] text-[10px] font-bold text-white">
                !
              </span>
              {verificationError}
            </motion.div>
          )}

          {showVerificationField && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 rounded-2xl border border-[#d9ddd5] bg-[#fcfcfa] p-4"
            >
              <div className="mb-2 flex items-center justify-between">
                <label htmlFor="register-code" className="text-sm font-semibold text-[#303431]">
                  邮箱验证码
                </label>
                <span className={`text-xs ${emailVerified ? "text-[#2f5947]" : "text-[#8a908b]"}`}>
                  {emailVerified ? "校验通过" : "输入满 6 位后自动校验"}
                </span>
              </div>
              <div className="group relative">
                <ShieldCheck className={`pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 transition-colors ${emailVerified ? "text-[#2f5947]" : "text-[#8a908b] group-focus-within:text-[#3f6b57]"}`} />
                <input
                  id="register-code"
                  type="text"
                  inputMode="numeric"
                  maxLength={AUTH_CODE_LENGTH}
                  value={verificationCode}
                  onChange={(event) => setVerificationCode(event.target.value.replace(/\D/g, "").slice(0, AUTH_CODE_LENGTH))}
                  placeholder="000000"
                  disabled={emailVerified}
                  className={`block w-full rounded-xl border py-3.5 pl-11 pr-12 text-sm tracking-[0.32em] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:tracking-[0.32em] focus:outline-none ${authFocusRing} ${
                    emailVerified
                      ? "border-[#d9ddd5] bg-[#f1f2ee] text-[#6c706b] caret-transparent"
                      : "border-[#d9ddd5] bg-white text-[#181b1a] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:ring-3 focus:ring-[#3f6b57]/10"
                  }`}
                />
                <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2">
                  {verificationChecking ? (
                    <Loader2 className="h-4 w-4 animate-spin text-[#3f6b57]" />
                  ) : emailVerified ? (
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#2f5947] text-white">
                      <Check className="h-3.5 w-3.5" />
                    </span>
                  ) : null}
                </span>
              </div>
            </motion.div>
          )}
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <label htmlFor="register-password" className="text-sm font-semibold text-[#303431]">
              密码
            </label>
            <span className="text-xs text-[#8a908b]">至少 8 个字符</span>
          </div>
          <div className="group relative">
            <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
            <input
              id="register-password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="设置密码"
              autoComplete="new-password"
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
          {password && (
            <div className="mt-3 rounded-xl border border-[#e6e8e2] bg-[#f7f8f4] px-4 py-3">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#7a817c]">密码要求</p>
              <PasswordRuleChecklist password={password} username={username} email={email} />
            </div>
          )}
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <label htmlFor="register-confirm-password" className="text-sm font-semibold text-[#303431]">
              确认密码
            </label>
            <span className={`text-xs ${confirmPasswordMatched ? "text-[#2f5947]" : "text-[#8a908b]"}`}>
              {confirmPasswordMatched ? "两次密码一致" : "再次输入以确认"}
            </span>
          </div>
          <div className="group relative">
            <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
            <input
              id="register-confirm-password"
              type={showConfirmPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="再次输入密码"
              autoComplete="new-password"
              className={`block w-full rounded-xl border bg-white py-3.5 pl-11 pr-20 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:outline-none focus:ring-3 ${authFocusRing} ${
                confirmPasswordMismatch
                  ? "border-[#d67f72] focus:border-[#d67f72] focus:ring-[#d67f72]/10"
                  : confirmPasswordMatched
                    ? "border-[#8ec1a0] focus:border-[#3f6b57] focus:ring-[#3f6b57]/10"
                    : "border-[#d9ddd5] focus:border-[#3f6b57] focus:ring-[#3f6b57]/10"
              }`}
            />
            {confirmPasswordMatched && (
              <span className="pointer-events-none absolute right-12 top-1/2 -translate-y-1/2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#2f5947] text-white">
                  <Check className="h-3.5 w-3.5" />
                </span>
              </span>
            )}
            <button
              type="button"
              onClick={() => setShowConfirmPassword((value) => !value)}
              className={`absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-2 text-[#7a817c] transition-colors hover:bg-[#f1f2ee] hover:text-[#181b1a] ${authFocusRing}`}
              aria-label={showConfirmPassword ? "隐藏确认密码" : "显示确认密码"}
            >
              {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {confirmPasswordMismatch && (
            <p className="mt-2 text-xs text-[#b2483d]">两次输入的密码暂不一致，请继续检查。</p>
          )}
        </div>

        <button
          type="submit"
          disabled={loading}
          className={`group flex w-full items-center justify-center gap-3 rounded-xl bg-[#181b1a] px-4 py-3.5 text-sm font-semibold text-[#f8f8f5] shadow-[0_14px_30px_rgba(24,27,26,.18)] transition-[transform,background-color,box-shadow] hover:-translate-y-0.5 hover:bg-[#2b302d] hover:shadow-[0_18px_38px_rgba(24,27,26,.22)] active:translate-y-0 disabled:pointer-events-none disabled:opacity-60 ${authFocusRing}`}
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              正在创建账号...
            </>
          ) : (
            <>
              创建账号并进入工作区
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </>
          )}
        </button>
      </form>

      <div className="my-8 flex items-center gap-4">
        <div className="h-px flex-1 bg-[#d9ddd5]" />
        <span className="text-xs text-[#9a9f9b]">已经有 ClaimCraft 账号？</span>
        <div className="h-px flex-1 bg-[#d9ddd5]" />
      </div>
      <Link
        to="/login"
        className={`flex w-full items-center justify-center rounded-xl border border-[#cfd5cc] bg-white px-4 py-3 text-sm font-semibold text-[#303431] transition-colors hover:bg-[#f1f2ee] ${authFocusRing}`}
      >
        去登录
      </Link>

      <div className="mt-10 flex items-center justify-between border-t border-[#d9ddd5] pt-5 text-xs text-[#8a908b]">
        <Link to="/home" className={`inline-flex items-center gap-1.5 rounded-md hover:text-[#181b1a] ${authFocusRing}`}>
          <ArrowLeft className="h-3.5 w-3.5" />
          返回首页
        </Link>
        <span className="inline-flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-[#3f6b57]" />
          安全创建并进入工作区
        </span>
      </div>
    </>
  )
}
