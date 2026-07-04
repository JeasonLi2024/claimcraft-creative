import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface HeroSectionProps {
  title: string
  subtitle: string
  children?: ReactNode
  className?: string
}

export default function HeroSection({ title, subtitle, children, className }: HeroSectionProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl bg-primary p-8 pb-10 text-primary-foreground shadow-lg md:p-10",
        className
      )}
    >
      {/* Decorative circles */}
      <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary-foreground/5" />
      <div className="pointer-events-none absolute -bottom-16 -left-16 h-48 w-48 rounded-full bg-secondary/10" />

      <div className="relative z-10">
        <h1 className="text-2xl font-extrabold leading-tight md:text-3xl">{title}</h1>
        <p className="mt-2 max-w-lg text-sm text-primary-foreground/70 md:text-base">{subtitle}</p>
        {children && <div className="mt-6">{children}</div>}
      </div>
    </div>
  )
}
