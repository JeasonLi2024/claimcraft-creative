import { cn } from "@/lib/utils"
import { useStatus } from "@/composables/useStatus"

interface StatusTagProps {
  status: string
  className?: string
}

export default function StatusTag({ status, className }: StatusTagProps) {
  const { statusLabel, statusColor } = useStatus()

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-lg border px-2.5 py-0.5 text-xs font-semibold",
        statusColor(status),
        className
      )}
    >
      {statusLabel(status)}
    </span>
  )
}
