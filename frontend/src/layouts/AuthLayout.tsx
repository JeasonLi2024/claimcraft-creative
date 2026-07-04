import type { ReactNode } from "react"

interface AuthLayoutProps {
  children: ReactNode
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      {/* Background gradients */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_0%_20%,rgba(155,150,95,.1),transparent_35%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_100%_80%,rgba(203,192,170,.1),transparent_35%)]" />

      {/* Center card */}
      <div className="relative z-10 w-full max-w-[420px]">
        {/* Brand logo */}
        <div className="mb-6 flex items-center justify-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary text-lg font-bold text-primary-foreground">
            C
          </div>
          <span className="text-xl font-bold tracking-tight text-foreground">ClaimCraft</span>
        </div>
        {children}
      </div>

      {/* Bottom glow */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-80 bg-[radial-gradient(ellipse_at_center,rgba(155,150,95,.06),transparent_60%)]" />
    </div>
  )
}
