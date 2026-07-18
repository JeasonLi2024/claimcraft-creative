// 运行配置抽屉：基础模式（证据 + 模板）+ 高级设置（strategy/prompt/case mode）
// 对齐 spec.md Task 3.6.2
// 提交：POST /api/cases/{case_id}/workflow-runs/ → workflowRunApi.createRun
import { useEffect, useMemo, useState } from "react"
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Loader2,
  Play,
  Settings2,
  Sparkles,
  X,
} from "lucide-react"
import type { FormEvent } from "react"
import { workflowRunApi, type CreateRunResponse } from "@/lib/api"
import type { Evidence } from "@/types"

// ---------- 模板类型映射 ----------

interface TemplateOption {
  value: string
  label: string
  description: string
}

const TEMPLATE_OPTIONS: TemplateOption[] = [
  {
    value: "complaint",
    label: "消费者投诉书",
    description: "标准 12315 投诉书模板，适用于平台投诉",
  },
  {
    value: "respond_complaint",
    label: "反证答辩书",
    description: "商家反证答辩模板，适用于商家回应",
  },
]

// ---------- 高级设置默认值 ----------

const DEFAULT_ADVANCED = {
  strategy_version: "default",
  prompt_bundle_version: "2026.07",
  case_mode: "standard",
} as const

// ---------- 主组件 ----------

export interface RunConfigurationDrawerProps {
  open: boolean
  onClose: () => void
  /** 案件 ID */
  caseId: number
  /** 案件证据列表（用于基础模式多选） */
  evidences: Evidence[]
  /** 默认选中的证据 ID（如全选） */
  defaultSelectedEvidenceIds?: number[]
  /** 创建成功回调（调用方负责 applySnapshot + connect SSE） */
  onCreateRun?: (response: CreateRunResponse, evidenceIds: number[]) => void | Promise<void>
}

export function RunConfigurationDrawer({
  open,
  onClose,
  caseId,
  evidences,
  defaultSelectedEvidenceIds,
  onCreateRun,
}: RunConfigurationDrawerProps) {
  const [selectedEvidenceIds, setSelectedEvidenceIds] = useState<Set<number>>(new Set())
  const [templateType, setTemplateType] = useState<string>(TEMPLATE_OPTIONS[0].value)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [strategyVersion, setStrategyVersion] = useState<string>(DEFAULT_ADVANCED.strategy_version)
  const [promptBundleVersion, setPromptBundleVersion] = useState<string>(
    DEFAULT_ADVANCED.prompt_bundle_version,
  )
  const [caseMode, setCaseMode] = useState<string>(DEFAULT_ADVANCED.case_mode)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 打开时重置表单 + 初始化证据选择
  useEffect(() => {
    if (!open) return
    setError(null)
    if (defaultSelectedEvidenceIds && defaultSelectedEvidenceIds.length > 0) {
      setSelectedEvidenceIds(new Set(defaultSelectedEvidenceIds))
    } else {
      // 默认全选
      setSelectedEvidenceIds(new Set(evidences.map((e) => e.id)))
    }
  }, [open, defaultSelectedEvidenceIds, evidences])

  // Escape 关闭
  useEffect(() => {
    if (!open) return
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open, onClose])

  const selectedCount = selectedEvidenceIds.size
  const canSubmit = selectedCount > 0 && !submitting

  const summaryText = useMemo(() => {
    if (selectedCount === 0) return "请至少选择一条证据"
    return `将使用 ${selectedCount} 条证据 · ${TEMPLATE_OPTIONS.find((t) => t.value === templateType)?.label ?? templateType}`
  }, [selectedCount, templateType])

  function toggleEvidence(id: number) {
    setSelectedEvidenceIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  function toggleAll() {
    setSelectedEvidenceIds((prev) => {
      if (prev.size === evidences.length) {
        return new Set()
      }
      return new Set(evidences.map((e) => e.id))
    })
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return

    setSubmitting(true)
    setError(null)
    try {
      const evidenceIds = Array.from(selectedEvidenceIds).sort((a, b) => a - b)
      const response = await workflowRunApi.createRun(caseId, {
        evidence_ids: evidenceIds,
        run_options: {
          template_type: templateType,
          strategy_version: strategyVersion,
          prompt_bundle_version: promptBundleVersion,
          case_mode: caseMode,
        },
      })
      await onCreateRun?.(response, evidenceIds)
      onClose()
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : typeof err === "string"
            ? err
            : "创建运行失败，请稍后重试"
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label="启动工作流配置"
    >
      {/* 遮罩 */}
      <button
        type="button"
        onClick={onClose}
        aria-label="关闭配置抽屉"
        className="absolute inset-0 cursor-default bg-black/40"
      />

      <aside className="relative flex h-full w-full max-w-md flex-col bg-white shadow-2xl motion-safe:animate-[drawer-slide-in_0.25s_ease-out]">
        {/* 头部 */}
        <header className="flex items-center justify-between border-b border-[#EAEAEA] px-4 py-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-sky-500" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-[#111111]">启动工作流</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[#787774] hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        <form className="flex flex-1 flex-col overflow-hidden" onSubmit={handleSubmit}>
          {/* 内容区 */}
          <div className="flex-1 overflow-y-auto px-4 py-4">
            {/* 错误提示 */}
            {error && (
              <div
                role="alert"
                className="mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
              >
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
                <div className="flex-1">
                  <p className="font-medium">创建失败</p>
                  <p className="mt-0.5 text-[11px] break-words">{error}</p>
                </div>
              </div>
            )}

            {/* 基础模式：证据选择 */}
            <fieldset className="mb-5">
              <legend className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold text-[#111111]">
                  证据选择
                  <span className="ml-1 font-normal text-[#787774]">
                    （已选 {selectedCount}/{evidences.length}）
                  </span>
                </span>
                <button
                  type="button"
                  onClick={toggleAll}
                  className="text-[11px] text-sky-700 transition hover:text-sky-900 focus:outline-none focus-visible:underline"
                >
                  {selectedCount === evidences.length && evidences.length > 0
                    ? "取消全选"
                    : "全选"}
                </button>
              </legend>

              {evidences.length === 0 ? (
                <p className="rounded-lg border border-dashed border-[#EAEAEA] bg-[#F7F6F3] px-3 py-3 text-center text-[11px] text-[#787774]">
                  暂无证据，请先在案件页面上传证据
                </p>
              ) : (
                <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto rounded-lg border border-[#EAEAEA] bg-white p-1.5">
                  {evidences.map((ev) => {
                    const checked = selectedEvidenceIds.has(ev.id)
                    return (
                      <li key={ev.id}>
                        <label
                          className={`flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs transition hover:bg-[#F7F6F3] ${
                            checked ? "bg-sky-50" : ""
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleEvidence(ev.id)}
                            className="h-3.5 w-3.5 rounded border-[#EAEAEA] text-sky-600 focus:ring-sky-500"
                          />
                          <span className="flex-1 truncate text-[#111111]">
                            {ev.code || `证据 #${ev.id}`}
                            {ev.description && (
                              <span className="ml-1 text-[#787774]">· {ev.description}</span>
                            )}
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              )}
            </fieldset>

            {/* 基础模式：模板类型 */}
            <fieldset className="mb-5">
              <legend className="mb-2 text-xs font-semibold text-[#111111]">文书模板</legend>
              <div className="flex flex-col gap-1.5">
                {TEMPLATE_OPTIONS.map((opt) => {
                  const checked = templateType === opt.value
                  return (
                    <label
                      key={opt.value}
                      className={`flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-xs transition ${
                        checked
                          ? "border-sky-300 bg-sky-50 ring-1 ring-sky-200"
                          : "border-[#EAEAEA] bg-white hover:bg-[#F7F6F3]"
                      }`}
                    >
                      <input
                        type="radio"
                        name="template-type"
                        value={opt.value}
                        checked={checked}
                        onChange={() => setTemplateType(opt.value)}
                        className="mt-0.5 h-3.5 w-3.5 border-[#EAEAEA] text-sky-600 focus:ring-sky-500"
                      />
                      <span className="flex-1">
                        <span className="block font-medium text-[#111111]">{opt.label}</span>
                        <span className="mt-0.5 block text-[11px] text-[#787774]">
                          {opt.description}
                        </span>
                      </span>
                    </label>
                  )
                })}
              </div>
            </fieldset>

            {/* 高级设置（可折叠） */}
            <div className="rounded-lg border border-[#EAEAEA]">
              <button
                type="button"
                onClick={() => setAdvancedOpen((v) => !v)}
                aria-expanded={advancedOpen}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-[#111111] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
              >
                <span className="flex items-center gap-1.5">
                  <Settings2 className="h-3.5 w-3.5 text-[#787774]" aria-hidden="true" />
                  高级设置
                </span>
                {advancedOpen ? (
                  <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                )}
              </button>
              {advancedOpen && (
                <div className="space-y-3 border-t border-[#EAEAEA] px-3 py-3">
                  <div>
                    <label
                      htmlFor="cfg-strategy-version"
                      className="mb-1 block text-[11px] font-medium text-[#565652]"
                    >
                      策略版本
                    </label>
                    <input
                      id="cfg-strategy-version"
                      type="text"
                      value={strategyVersion}
                      onChange={(e) => setStrategyVersion(e.target.value)}
                      placeholder="default"
                      className="w-full rounded-lg border border-[#EAEAEA] bg-white px-2.5 py-1.5 text-xs text-[#111111] focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="cfg-prompt-version"
                      className="mb-1 block text-[11px] font-medium text-[#565652]"
                    >
                      Prompt 包版本
                    </label>
                    <input
                      id="cfg-prompt-version"
                      type="text"
                      value={promptBundleVersion}
                      onChange={(e) => setPromptBundleVersion(e.target.value)}
                      placeholder="2026.07"
                      className="w-full rounded-lg border border-[#EAEAEA] bg-white px-2.5 py-1.5 text-xs text-[#111111] focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="cfg-case-mode"
                      className="mb-1 block text-[11px] font-medium text-[#565652]"
                    >
                      案件模式
                    </label>
                    <select
                      id="cfg-case-mode"
                      value={caseMode}
                      onChange={(e) => setCaseMode(e.target.value)}
                      className="w-full rounded-lg border border-[#EAEAEA] bg-white px-2.5 py-1.5 text-xs text-[#111111] focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
                    >
                      <option value="standard">标准模式</option>
                      <option value="strict">严格模式（更强质量门）</option>
                      <option value="fast">快速模式（跳过可选审核）</option>
                    </select>
                  </div>
                  <p className="text-[10px] text-[#787774]">
                    默认值通常无需调整。修改后若与后端不兼容将自动回退。
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* 底部操作区 */}
          <footer className="border-t border-[#EAEAEA] bg-white px-4 py-3">
            <p className="mb-2 text-[11px] text-[#787774]" aria-live="polite">
              {summaryText}
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-[#EAEAEA] bg-white px-3 py-1.5 text-xs font-medium text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={!canSubmit}
                aria-label="启动工作流"
                className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-sky-600 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-sky-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <Play className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {submitting ? "启动中…" : "启动"}
              </button>
            </div>
          </footer>
        </form>
      </aside>
    </div>
  )
}

export default RunConfigurationDrawer
