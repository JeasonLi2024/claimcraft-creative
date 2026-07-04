import { format, formatDistanceToNow } from "date-fns"
import { zhCN } from "date-fns/locale"

export function useFormat() {
  function formatTime(value: string | null | undefined): string {
    if (!value) return ""
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return value || ""
    return format(d, "yyyy-MM-dd HH:mm", { locale: zhCN })
  }

  function formatRelative(value: string): string {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return value
    return formatDistanceToNow(d, { addSuffix: true, locale: zhCN })
  }

  function confText(c: number | null): string {
    if (c === null || c === undefined) return "-"
    const n = Number(c)
    if (Number.isNaN(n)) return String(c)
    return n.toFixed(2)
  }

  return { formatTime, formatRelative, confText }
}
