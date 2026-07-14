import AuthShell from "@/components/auth/AuthShell"
import RegisterForm from "@/components/auth/RegisterForm"

export default function RegisterPage() {
  return (
    <AuthShell
      eyebrow="创建账号"
      title="注册 ClaimCraft"
      description="创建账号后即可进入案件工作区，开始整理证据、时间线和投诉材料。"
    >
      <RegisterForm />
    </AuthShell>
  )
}
