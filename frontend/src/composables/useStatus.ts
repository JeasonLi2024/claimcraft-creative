export const STATUS_LABEL: Record<string, string> = {
  draft: "草稿",
  processing: "处理中",
  submitted: "已提交",
  closed: "已结案",
  cancelled: "已取消",
}

export const STATUS_COLOR: Record<string, string> = {
  draft: "bg-status-draft/10 text-status-draft border-status-draft/20",
  processing: "bg-status-processing/10 text-status-processing border-status-processing/20",
  submitted: "bg-status-submitted/10 text-status-submitted border-status-submitted/20",
  closed: "bg-status-closed/10 text-status-closed border-status-closed/20",
  cancelled: "bg-status-cancelled/10 text-status-cancelled border-status-cancelled/20",
}

export const DISPUTE_TYPES = [
  { value: "", label: "全部纠纷类型" },
  { value: "online_shopping", label: "网购纠纷" },
  { value: "service_breach", label: "服务违约" },
  { value: "second_hand", label: "二手交易" },
  { value: "other", label: "其他" },
]

export const MAIN_FLOW = ["draft", "processing", "submitted", "closed"] as const

export const TRANSITIONS: Record<string, string[]> = {
  draft: ["processing", "cancelled"],
  processing: ["submitted", "cancelled"],
  submitted: ["closed"],
  closed: [],
  cancelled: [],
}

export const TEMPLATES = [
  { type: "platform", label: "平台客服版" },
  { type: "regulatory", label: "监管投诉版" },
  { type: "arbitration", label: "仲裁准备版" },
]

export function useStatus() {
  function statusLabel(s: string): string {
    return STATUS_LABEL[s] || s || "草稿"
  }
  function statusColor(s: string): string {
    return STATUS_COLOR[s] || STATUS_COLOR.draft
  }
  function disputeLabel(t: string): string {
    const item = DISPUTE_TYPES.find((d) => d.value === t)
    return item && item.value ? item.label : t || "其他"
  }
  return { statusLabel, statusColor, disputeLabel }
}
