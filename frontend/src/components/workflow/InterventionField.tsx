// 介入表单单字段编辑组件
// 对齐 spec 第 6.7 节 / Task 2.5.2
// 支持 text / textarea / number / select / evidence_link 五种字段类型
import { RotateCcw, ExternalLink } from "lucide-react"

// ---------- form_schema 字段类型 ----------

export type FormFieldType =
  | "text"
  | "textarea"
  | "number"
  | "select"
  | "evidence_link"

export interface FormFieldOption {
  value: string
  label: string
}

export interface FormField {
  name: string
  label: string
  type: FormFieldType
  required?: boolean
  initial_value?: unknown
  evidence_id?: number | null
  options?: FormFieldOption[]
}

// ---------- 工具函数 ----------

function formatInitialValue(value: unknown): string {
  if (value == null) return ""
  if (typeof value === "string") return value
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function formatValue(value: unknown): string {
  if (value == null) return ""
  if (typeof value === "string") return value
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

// ---------- 主组件 ----------

export interface InterventionFieldProps {
  field: FormField
  value: unknown
  onChange: (value: unknown) => void
  error?: string
  /** evidence_link 类型字段点击"查看证据"按钮时触发 */
  onJumpToEvidence?: (evidenceId: number) => void
}

export function InterventionField({
  field,
  value,
  onChange,
  error,
  onJumpToEvidence,
}: InterventionFieldProps) {
  const errorId = `intervention-field-error-${field.name}`
  const initialText = formatInitialValue(field.initial_value)
  const hasInitial = initialText !== ""
  const isEvidenceLink = field.type === "evidence_link"
  const hasEvidenceJump = isEvidenceLink && field.evidence_id != null && Boolean(onJumpToEvidence)

  const inputClass =
    "w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 focus:ring-amber-200 " +
    (error
      ? "border-red-400 focus:border-red-500"
      : "border-slate-300 focus:border-amber-400")

  const ariaErrorProps = error
    ? { "aria-invalid": true as const, "aria-describedby": errorId }
    : { "aria-invalid": false as const }

  function handleRestoreInitial() {
    onChange(field.initial_value ?? "")
  }

  function handleJumpToEvidence() {
    if (field.evidence_id != null && onJumpToEvidence) {
      onJumpToEvidence(field.evidence_id)
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <label
          htmlFor={`intervention-field-${field.name}`}
          className="text-sm font-medium text-slate-700"
        >
          {field.label}
          {field.required ? <span className="ml-1 text-red-500" aria-hidden="true">*</span> : null}
          {field.required ? <span className="sr-only">（必填）</span> : null}
        </label>
        {hasInitial && (
          <button
            type="button"
            onClick={handleRestoreInitial}
            className="inline-flex items-center gap-1 text-[11px] text-slate-500 transition hover:text-slate-700"
            aria-label={`恢复${field.label}的原值`}
          >
            <RotateCcw className="h-3 w-3" aria-hidden="true" />
            恢复原值
          </button>
        )}
      </div>

      {hasInitial && (
        <p className="text-[11px] text-slate-500">
          原值：<span className="font-mono text-slate-700">{initialText}</span>
        </p>
      )}

      {/* 字段类型渲染 */}
      {(field.type === "text" || isEvidenceLink) && (
        <input
          id={`intervention-field-${field.name}`}
          type="text"
          value={formatValue(value)}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
          {...ariaErrorProps}
        />
      )}

      {field.type === "textarea" && (
        <textarea
          id={`intervention-field-${field.name}`}
          value={formatValue(value)}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          className={`${inputClass} min-h-28 resize-y leading-6`}
          {...ariaErrorProps}
        />
      )}

      {field.type === "number" && (
        <input
          id={`intervention-field-${field.name}`}
          type="number"
          value={formatValue(value)}
          onChange={(e) => {
            const raw = e.target.value
            if (raw === "") {
              onChange("")
              return
            }
            const num = Number(raw)
            onChange(Number.isNaN(num) ? raw : num)
          }}
          className={inputClass}
          {...ariaErrorProps}
        />
      )}

      {field.type === "select" && (
        <select
          id={`intervention-field-${field.name}`}
          value={formatValue(value)}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
          {...ariaErrorProps}
        >
          <option value="">请选择...</option>
          {(field.options || []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      )}

      {/* evidence_link 类型：查看证据按钮 */}
      {hasEvidenceJump && (
        <button
          type="button"
          onClick={handleJumpToEvidence}
          className="inline-flex min-h-[36px] items-center gap-1.5 rounded-md border border-sky-200 bg-sky-50 px-2.5 py-1 text-xs font-medium text-sky-700 transition hover:bg-sky-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
          aria-label={`查看证据 #${field.evidence_id} 的来源`}
        >
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          查看证据 #{field.evidence_id}
        </button>
      )}

      {error && (
        <p id={errorId} role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}

export default InterventionField
