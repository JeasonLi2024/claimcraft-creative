import AuthShell from "@/components/auth/AuthShell"
import LoginForm from "@/components/auth/LoginForm"

export default function LoginPage() {
  return (
    <AuthShell
      eyebrow="欢迎回来"
      title="登录 ClaimCraft"
      description="进入案件工作区，继续整理你的证据和材料。"
    >
      <LoginForm />
    </AuthShell>
  )
}
