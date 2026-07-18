import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { Inbox } from "lucide-react"

interface EmptyStateProps {
  icon?: ReactNode
  illustration?: boolean
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

export default function EmptyState({ icon, illustration = true, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center py-16 text-center", className)}>
      {illustration ? (
        <img
          src="/空状态插画.png"
          alt=""
          aria-hidden="true"
          className="mb-5 h-auto w-48 max-w-[70%] object-contain"
        />
      ) : (
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
          {icon || <Inbox className="h-8 w-8" />}
        </div>
      )}
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
