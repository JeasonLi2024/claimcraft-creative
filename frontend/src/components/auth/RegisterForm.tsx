import { useState } from "react"
import { Link, useNavigate } from "react-router"
import { motion } from "framer-motion"
import {
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
  UserRound,
} from "lucide-react"
import { useAuthStore } from "@/stores/auth-store"
import { authFocusRing } from "@/components/auth/AuthShell"

export default function RegisterForm() {
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const register = useAuthStore((s) => s.register)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError("")

    if (!username.trim() || !email.trim() || !password.trim()) {
      setError("请填写所有字段")
      return
    }

    if (password !== confirmPassword) {
      setError("两次输入的密码不一致")
      return
    }

    if (password.length < 6) {
      setError("密码至少需要 6 个字符")
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
      setError(err.response?.data?.detail || err.message || "注册失败")
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
          <div className="group relative">
            <Mail className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a908b] transition-colors group-focus-within:text-[#3f6b57]" />
            <input
              id="register-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="输入邮箱"
              autoComplete="email"
              className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-4 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
            />
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <label htmlFor="register-password" className="text-sm font-semibold text-[#303431]">
              密码
            </label>
            <span className="text-xs text-[#8a908b]">至少 6 个字符</span>
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
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <label htmlFor="register-confirm-password" className="text-sm font-semibold text-[#303431]">
              确认密码
            </label>
            <span className="text-xs text-[#8a908b]">再次输入以确认</span>
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
              className={`block w-full rounded-xl border border-[#d9ddd5] bg-white py-3.5 pl-11 pr-12 text-sm text-[#181b1a] shadow-[0_8px_24px_rgba(31,45,38,.035)] transition-[border-color,box-shadow] placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10 ${authFocusRing}`}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword((value) => !value)}
              className={`absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-2 text-[#7a817c] transition-colors hover:bg-[#f1f2ee] hover:text-[#181b1a] ${authFocusRing}`}
              aria-label={showConfirmPassword ? "隐藏确认密码" : "显示确认密码"}
            >
              {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
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
