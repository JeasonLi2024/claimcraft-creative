// 统一介入面板：合并 ReviewInterruptPanel + StagePausePanel
// 对齐 spec 第 6.7 节 / Task 2.5.1 + 2.5.4
// 根据 intervention.form_schema 动态渲染表单字段
// 支持焦点锁定 + Escape 关闭 + ARIA dialog 语义
import { useEffect, useMemo, useRef, useState } from "react"
import type { FormEvent } from "react"
import { AlertTriangle, ShieldCheck, X, AlertCircle, Info, RefreshCw } from "lucide-react"
import type { WorkflowIntervention } from "@/types/workflow"
import { InterventionField, type FormField } from "./InterventionField"

// ---------- 介入类型元数据 ----------

interface InterventionTypeConfig {
  label: string
  icon: typeof AlertTriangle
  iconClass: string
  badgeClass: string
}

const INTERVENTION_TYPE_CONFIG: Record<string, InterventionTypeConfig> = {
  quality_review: {
    label: "质量审核",
    icon: ShieldCheck,
    iconClass: "text-amber-600",
    badgeClass: "bg-amber-50 border-amber-200 text-amber-700",
  },
  user_pause: {
    label: "用户暂停",
    icon: AlertTriangle,
    iconClass: "text-sky-600",
    badgeClass: "bg-sky-50 border-sky-200 text-sky-700",
  },
  legal_confirmation: {
    label: "法律风险确认",
    icon: ShieldCheck,
    iconClass: "text-indigo-600",
    badgeClass: "bg-indigo-50 border-indigo-200 text-indigo-700",
  },
  // input-quality-guard Gate 2：证据质量不足需用户决策
  missing_information: {
    label: "证据质量不足",
    icon: AlertTriangle,
    iconClass: "text-orange-600",
    badgeClass: "bg-orange-50 border-orange-200 text-orange-700",
  },
}

// missing_information 诊断字段 → 中文标签（input-quality-guard Gate 2）
const DIAGNOSTICS_LABELS: Record<string, string> = {
  evidence_count: "上传图片",
  avg_preclassify_confidence: "平均识别置信度",
  total_extracted_fields: "提取的结构化字段",
  all_classified_other: "是否全部归类为“其他”",
}

function formatDiagnosticValue(key: string, value: unknown): string {
  if (key === "avg_preclassify_confidence" && typeof value === "number") {
    return `${Math.round(value * 100)}%`
  }
  if (key === "evidence_count" && typeof value === "number") {
    return `${value} 张`
  }
  if (key === "total_extracted_fields" && typeof value === "number") {
    return `${value} 个`
  }
  if (key === "all_classified_other" && typeof value === "boolean") {
    return value ? "是（全部为“其他”类型）" : "否"
  }
  if (value == null) return "--"
  return String(value)
}

const STAGE_NAME_ZH: Record<string, string> = {
  material_understanding: "材料理解",
  fact_checking: "事实核对",
  case_organization: "案件组织",
  document_generation: "文书生成",
  preclassify: "证据预分类",
  ocr: "OCR 识别",
  classify: "证据分类",
  extract: "字段抽取",
  review: "质量审核",
  evidence_chain: "证据链",
  complaint: "投诉书",
  respond_complaint: "反证答辩书",
}

function stageLabel(stage: string | undefined | null): string {
  if (!stage) return "--"
  return STAGE_NAME_ZH[stage] || stage
}

// ---------- form_schema 解析 ----------

interface FormSchemaShape {
  fields?: FormField[]
}

function parseFormFields(schema: Record<string, unknown> | null | undefined): FormField[] {
  if (!schema || typeof schema !== "object") return []
  const fields = (schema as FormSchemaShape).fields
  if (!Array.isArray(fields)) return []
  return fields.filter(
    (f): f is FormField =>
      f != null && typeof f === "object" && typeof (f as FormField).name === "string",
  )
}

// ---------- impact 解析 ----------

interface ImpactShape {
  rerun_nodes?: unknown[]
  stale_artifacts?: unknown[]
  affected_stages?: unknown[]
  [key: string]: unknown
}

function extractImpactList(
  impact: Record<string, unknown> | null | undefined,
): Array<{ key: string; items: string[] }> {
  if (!impact || typeof impact !== "object") return []
  const shape = impact as ImpactShape
  const result: Array<{ key: string; items: string[] }> = []
  const knownKeys: Array<{ key: keyof ImpactShape; label: string }> = [
    { key: "rerun_nodes", label: "将重跑的节点" },
    { key: "stale_artifacts", label: "将过期的产物" },
    { key: "affected_stages", label: "受影响的阶段" },
  ]
  for (const { key, label } of knownKeys) {
    const raw = shape[key]
    if (Array.isArray(raw) && raw.length > 0) {
      result.push({
        key: label,
        items: raw.map((item) => (typeof item === "string" ? item : String(item))),
      })
    }
  }
  // 兜底：显示其他未知键
  for (const [k, v] of Object.entries(shape)) {
    if (knownKeys.some((kx) => kx.key === k)) continue
    if (Array.isArray(v) && v.length > 0) {
      result.push({
        key: k,
        items: v.map((item) => (typeof item === "string" ? item : String(item))),
      })
    }
  }
  return result
}

// ---------- 必填校验 ----------

function isValueFilled(value: unknown): boolean {
  if (value == null) return false
  if (typeof value === "string") return value.trim() !== ""
  if (typeof value === "number") return !Number.isNaN(value)
  if (typeof value === "boolean") return true
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === "object") return Object.keys(value as object).length > 0
  return true
}

// ---------- 焦点锁定工具 ----------

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

function getFocusableElements(container: HTMLElement | null): HTMLElement[] {
  if (!container) return []
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => el.offsetParent !== null || el.getClientRects().length > 0,
  )
}

// ---------- 主组件 ----------

export interface InterventionPanelProps {
  intervention: WorkflowIntervention | null
  onSubmit: (values: Record<string, unknown>) => void
  onCancel: () => void
  revisionConflict?: { baseRevision: number; currentRevision: number } | null
  /**
   * 外部受控草稿值（来自 intervention-store）。
   * 若提供则进入受控模式；否则使用内部 state（兼容旧调用方）。
   */
  draftValues?: Record<string, unknown>
  /** 字段级校验错误（来自 intervention-store） */
  validationErrors?: Record<string, string>
  /** 字段值变更回调（同步到 intervention-store） */
  onDraftChange?: (fieldName: string, value: unknown) => void
  /** evidence_link 字段点击"查看证据"时触发 */
  onJumpToEvidence?: (evidenceId: number) => void
}

export function InterventionPanel({
  intervention,
  onSubmit,
  onCancel,
  revisionConflict = null,
  draftValues,
  validationErrors = {},
  onDraftChange,
  onJumpToEvidence,
}: InterventionPanelProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)

  // 内部 state（仅当未传入 draftValues 时使用）
  const [internalValues, setInternalValues] = useState<Record<string, unknown>>({})
  const isControlled = draftValues !== undefined

  const fields = useMemo(() => parseFormFields(intervention?.form_schema), [intervention])
  const impactSections = useMemo(() => extractImpactList(intervention?.impact), [intervention])

  // intervention 切换时初始化内部 state
  useEffect(() => {
    if (!intervention || isControlled) return
    const init: Record<string, unknown> = {}
    for (const f of fields) {
      init[f.name] = intervention.initial_values?.[f.name] ?? f.initial_value ?? ""
    }
    setInternalValues(init)
  }, [intervention, fields, isControlled])

  const currentValues = isControlled ? (draftValues as Record<string, unknown>) : internalValues

  function handleFieldChange(fieldName: string, value: unknown) {
    if (!isControlled) {
      setInternalValues((prev) => ({ ...prev, [fieldName]: value }))
    }
    onDraftChange?.(fieldName, value)
  }

  // 必填字段是否全部填写
  const requiredFieldsSatisfied = useMemo(() => {
    return fields
      .filter((f) => f.required)
      .every((f) => isValueFilled(currentValues[f.name] ?? f.initial_value))
  }, [fields, currentValues])

  const hasRevisionConflict = Boolean(revisionConflict)
  const submitDisabled = !requiredFieldsSatisfied || hasRevisionConflict

  const typeConfig = intervention
    ? INTERVENTION_TYPE_CONFIG[intervention.intervention_type] ||
      INTERVENTION_TYPE_CONFIG.user_pause
    : INTERVENTION_TYPE_CONFIG.user_pause
  const TypeIcon = typeConfig.icon

  const titleId = "intervention-panel-title"
  const descId = "intervention-panel-desc"

  // 焦点管理 + Escape 关闭 + Tab 焦点锁定
  useEffect(() => {
    if (!intervention) return
    // 首次渲染时聚焦面板标题
    const timer = window.setTimeout(() => titleRef.current?.focus(), 50)

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        e.stopPropagation()
        onCancel()
        return
      }
      if (e.key !== "Tab") return
      const focusable = getFocusableElements(dialogRef.current)
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey) {
        // Shift+Tab：从首个回到末个
        if (active === first || !dialogRef.current?.contains(active)) {
          e.preventDefault()
          last.focus()
        }
      } else {
        // Tab：从末个回到首个
        if (active === last || !dialogRef.current?.contains(active)) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown, true)
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true)
      window.clearTimeout(timer)
    }
  }, [intervention, onCancel])

  if (!intervention) return null

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (submitDisabled) return
    onSubmit(currentValues)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 md:items-center md:p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl md:max-w-2xl md:rounded-2xl"
      >
        {/* 顶部：介入类型图标 + 阶段名 + base_revision + 关闭按钮 */}
        <header className="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
          <div className={`rounded-xl bg-amber-50 p-2 ${typeConfig.iconClass}`}>
            <TypeIcon className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${typeConfig.badgeClass}`}
                role="status"
              >
                {typeConfig.label}
              </span>
              <span className="text-xs text-slate-500">
                阶段：<span className="font-medium text-slate-700">{stageLabel(intervention.stage)}</span>
              </span>
              <span className="font-mono text-[11px] text-slate-500">
                修订 #{intervention.base_revision}
              </span>
            </div>
            <h2
              ref={titleRef}
              id={titleId}
              tabIndex={-1}
              className="mt-2 text-base font-semibold text-slate-900 outline-none"
            >
              需要您确认介入内容
            </h2>
            <p id={descId} className="mt-1 text-xs leading-5 text-slate-600">
              请检查并修正以下字段，提交后工作流将从对应节点继续执行。
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="关闭介入面板"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        {/* revision 冲突提示 */}
        {hasRevisionConflict && revisionConflict && (
          <div
            role="alert"
            className="mx-5 mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
            <div>
              <p className="font-medium">检测到修订冲突</p>
              <p className="mt-0.5">
                您基于修订 #{revisionConflict.baseRevision} 编辑，但当前运行已更新到修订 #{revisionConflict.currentRevision}。
                请关闭面板后重新加载最新数据。
              </p>
            </div>
          </div>
        )}

        {/* 介入原因说明（input-quality-guard Gate 2 等场景） */}
        {intervention.reason && (
          <div
            className="mx-5 mt-4 flex items-start gap-2 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2.5 text-xs leading-5 text-orange-800"
            role="note"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-orange-600" aria-hidden="true" />
            <p>{intervention.reason}</p>
          </div>
        )}

        {/* 诊断数据区块（missing_information：证据分析结果） */}
        {intervention.intervention_type === "missing_information" &&
          intervention.diagnostics &&
          Object.keys(intervention.diagnostics).length > 0 && (
            <div className="mx-5 mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
              <p className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                <Info className="h-3 w-3" aria-hidden="true" />
                证据分析结果
              </p>
              <dl className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
                {Object.entries(intervention.diagnostics)
                  .filter(([k]) => k in DIAGNOSTICS_LABELS)
                  .map(([k, v]) => (
                    <div key={k} className="flex items-baseline justify-between gap-2 text-[12px]">
                      <dt className="text-slate-600">{DIAGNOSTICS_LABELS[k]}</dt>
                      <dd className="font-mono font-medium text-slate-800">
                        {formatDiagnosticValue(k, v)}
                      </dd>
                    </div>
                  ))}
              </dl>
              <p className="mt-2 text-[11px] leading-4 text-slate-500">
                继续生成的文书将主要基于您填写的案件描述，而非实际证据内容，输出质量可能显著偏低。
              </p>
            </div>
          )}

        {/* 主体：动态表单字段 */}
        <form
          id="intervention-panel-form"
          onSubmit={handleSubmit}
          className="flex-1 overflow-y-auto px-5 py-4"
        >
          {fields.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
              本次介入没有需要编辑的字段，可直接提交。
            </div>
          ) : (
            <div className="space-y-4">
              {fields.map((field) => (
                <InterventionField
                  key={field.name}
                  field={field}
                  value={currentValues[field.name] ?? field.initial_value ?? ""}
                  onChange={(v) => handleFieldChange(field.name, v)}
                  error={validationErrors[field.name]}
                  onJumpToEvidence={onJumpToEvidence}
                />
              ))}
            </div>
          )}
        </form>

        {/* 底部：影响范围 + 操作按钮 */}
        <footer className="border-t border-slate-200 bg-slate-50 px-5 py-3">
          {impactSections.length > 0 && (
            <div className="mb-3 space-y-1.5">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                影响范围
              </p>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {impactSections.map((sec) => (
                  <div key={sec.key} className="text-[11px] text-slate-600">
                    <span className="font-medium text-slate-700">{sec.key}：</span>
                    <span className="font-mono">{sec.items.join("、")}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!requiredFieldsSatisfied && (
            <p className="mb-2 flex items-center gap-1 text-[11px] text-amber-700">
              <Info className="h-3 w-3" aria-hidden="true" />
              请填写所有必填字段后再提交。
            </p>
          )}

          <div className="flex flex-wrap items-center justify-end gap-3">
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
            >
              <X className="h-4 w-4" aria-hidden="true" />
              取消
            </button>
            <button
              type="submit"
              form="intervention-panel-form"
              disabled={submitDisabled}
              className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              提交并继续
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}

export default InterventionPanel
