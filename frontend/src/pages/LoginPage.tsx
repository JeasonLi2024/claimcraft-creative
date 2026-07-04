import { useState } from "react"
import { Link, useNavigate } from "react-router"
import { useAuthStore } from "@/stores/auth-store"
import AuthLayout from "@/layouts/AuthLayout"

export default function LoginPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  // If already authenticated, redirect
  if (isAuthenticated) {
    navigate("/cases", { replace: true })
    return null
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    if (!username.trim() || !password.trim()) {
      setError("请输入用户名和密码")
      return
    }
    setLoading(true)
    try {
      await login({ username, password })
      navigate("/cases", { replace: true })
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "登录失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <div className="rounded-[20px] border border-border/50 bg-white/90 p-8 shadow-[0_10px_30px_rgba(20,35,90,.04)] backdrop-blur-sm">
        <h1 className="mb-1 text-center text-2xl font-extrabold text-foreground">
          登录
        </h1>
        <p className="mb-6 text-center text-sm text-muted-foreground">
          欢迎回来，请登录你的 ClaimCraft 账号
        </p>

        {error && (
          <div className="mb-4 rounded-lg bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              用户名
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              autoComplete="username"
              className="block w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              密码
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              autoComplete="current-password"
              className="block w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-all hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "登录中..." : "登录"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          还没有账号？{" "}
          <Link to="/register" className="font-medium text-primary hover:underline">
            去注册
          </Link>
        </p>
      </div>
    </AuthLayout>
  )
}
