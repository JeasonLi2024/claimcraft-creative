import type { EmailCodeSendResponse } from "@/types"

export const AUTH_CODE_LENGTH = 6

export function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}

export function getAuthErrorMessage(err: any, fallback: string) {
  const data = err?.response?.data

  if (typeof data?.detail === "string" && data.detail.trim()) {
    return data.detail
  }

  if (data && typeof data === "object") {
    for (const value of Object.values(data)) {
      if (typeof value === "string" && value.trim()) {
        return value
      }
      if (Array.isArray(value) && typeof value[0] === "string" && value[0].trim()) {
        return value[0]
      }
    }
  }

  return err?.message || fallback
}

export function buildCodeDeliveryHint(meta: EmailCodeSendResponse) {
  const expiresAt = new Date(meta.expires_at).toLocaleString("zh-CN")
  return `验证码已发送至 ${meta.target_email}，有效期至 ${expiresAt}。`
}
