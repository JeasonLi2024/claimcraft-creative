import { cn } from "@/lib/utils"

interface PillTagProps {
  label: string
  variant?: "default" | "primary" | "success" | "warning" | "danger"
  className?: string
}

const variantStyles = {
  default: "bg-muted text-muted-foreground",
  primary: "bg-primary/10 text-primary",
  success: "bg-accent2/10 text-accent2-foreground",
  warning: "bg-[#d6a84b]/10 text-[#a88530]",
  danger: "bg-destructive/10 text-destructive",
}

export default function PillTag({ label, variant = "default", className }: PillTagProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantStyles[variant],
        className
      )}
    >
      {label}
    </span>
  )
}
