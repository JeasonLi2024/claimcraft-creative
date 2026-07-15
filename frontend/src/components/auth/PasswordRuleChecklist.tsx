import { useMemo } from "react"
import { Check, X } from "lucide-react"

type RuleStatus = "idle" | "valid" | "invalid"

interface PasswordRule {
  key: string
  label: string
  status: RuleStatus
}

const COMMON_WEAK_PASSWORDS = new Set([
  "password", "password1", "password123", "12345678", "11111111",
  "00000000", "88888888", "abc12345", "qwerty12", "iloveyou",
  "admin123", "letmein1", "welcome1", "monkey123", "dragon123",
  "claimcraft", "claimcraft123",
])

function getLocalPart(email: string): string {
  if (!email) return ""
  const at = email.indexOf("@")
  return at > 0 ? email.slice(0, at) : email
}

function evaluateRules(password: string, username: string, email: string): PasswordRule[] {
  const value = password
  const hasInput = value.length > 0
  const localPart = getLocalPart(email).toLowerCase()
  const usernameLower = username.trim().toLowerCase()

  const lengthRule = !hasInput ? "idle" : value.length >= 8 ? "valid" : "invalid"

  const numericRule = !hasInput
    ? "idle"
    : /^\d+$/.test(value)
      ? "invalid"
      : "valid"

  const commonRule = !hasInput
    ? "idle"
    : COMMON_WEAK_PASSWORDS.has(value.toLowerCase())
      ? "invalid"
      : "valid"

  let similarityRule: RuleStatus = "idle"
  if (hasInput) {
    const valueLower = value.toLowerCase()
    let similar = false
    if (usernameLower && usernameLower.length >= 4) {
      if (valueLower.includes(usernameLower)) similar = true
      else if (usernameLower.includes(valueLower) && valueLower.length >= 4) similar = true
    }
    if (!similar && localPart && localPart.length >= 4) {
      if (valueLower.includes(localPart)) similar = true
      else if (localPart.includes(valueLower) && valueLower.length >= 4) similar = true
    }
    similarityRule = similar ? "invalid" : "valid"
  }

  return [
    { key: "length", label: "至少 8 个字符", status: lengthRule },
    { key: "numeric", label: "不能是纯数字", status: numericRule },
    { key: "common", label: "不能是常见弱密码", status: commonRule },
    { key: "similarity", label: "不能与用户名/邮箱过于相似", status: similarityRule },
  ]
}

interface PasswordRuleChecklistProps {
  password: string
  username?: string
  email?: string
  className?: string
}

export default function PasswordRuleChecklist({
  password,
  username = "",
  email = "",
  className = "",
}: PasswordRuleChecklistProps) {
  const rules = useMemo(() => evaluateRules(password, username, email), [password, username, email])

  return (
    <ul className={`grid gap-1.5 ${className}`}>
      {rules.map((rule) => (
        <li key={rule.key} className="flex items-center gap-2 text-xs">
          <span
            aria-hidden="true"
            className={`flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full border transition-colors ${
              rule.status === "valid"
                ? "border-[#2f5947] bg-[#2f5947] text-white"
                : rule.status === "invalid"
                  ? "border-[#b2483d] bg-[#b2483d] text-white"
                  : "border-[#c7cdc6] bg-transparent text-transparent"
            }`}
          >
            {rule.status === "valid" ? <Check className="h-2.5 w-2.5" strokeWidth={3.5} /> : null}
            {rule.status === "invalid" ? <X className="h-2.5 w-2.5" strokeWidth={3.5} /> : null}
          </span>
          <span
            className={`transition-colors ${
              rule.status === "valid"
                ? "text-[#2f5947]"
                : rule.status === "invalid"
                  ? "text-[#b2483d]"
                  : "text-[#8a908b]"
            }`}
          >
            {rule.label}
          </span>
        </li>
      ))}
    </ul>
  )
}
