// 全文重新生成前确认对话框
// 对齐 spec.md Task 4.3.7 / 设计文档 16 节 / Requirement: DocumentEditor Dual-Pane Layout
//
// 警告用户：此操作将重新生成全文，下游产物将标记为过期
// 提供「保留用户确认字段」复选框
// 用户确认后由调用方调用 workflowRunApi.retryRun(from_stage, preserve_user_confirmed)
import { useEffect, useRef, useState } from "react"
import { AlertTriangle, RefreshCw, X, ShieldCheck } from "lucide-react"

// ---------- 类型 ----------

export interface RegenerateConfirmDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: (preserveUserConfirmed: boolean) => void | Promise<void>
  /** 文书标题，用于提示文案 */
  documentTitle?: string
  /** 受影响下游产物列表（前端无信息时传空数组，组件展示通用文案） */
  affectedArtifacts?: Array<{ id: number; summary: string }>
  /** 是否正在重新生成（true 时禁用按钮 + 展示 loading） */
  isRegenerating?: boolean
  /** from_stage（"complaint" | "respond_complaint"），用于提示文案 */
  fromStage?: 'complaint' | 'respond_complaint'
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

function getFocusableElements(container: HTMLElement | null): HTMLElement[] {
  if (!container) return []
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => el.offsetParent !== null || el.getClientRects().length > 0,
  )
}

// ---------- 主组件 ----------

export function RegenerateConfirmDialog({
  open,
  onClose,
  onConfirm,
  documentTitle,
  affectedArtifacts = [],
  isRegenerating = false,
  fromStage = 'complaint',
}: RegenerateConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  const [preserveUserConfirmed, setPreserveUserConfirmed] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  const titleId = "regenerate-confirm-title"
  const descId = "regenerate-confirm-desc"

  // Escape 关闭 + 焦点锁定
  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => titleRef.current?.focus(), 50)

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        e.stopPropagation()
        if (!submitting && !isRegenerating) onClose()
        return
      }
      if (e.key !== "Tab") return
      const focusable = getFocusableElements(dialogRef.current)
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey) {
        if (active === first || !dialogRef.current?.contains(active)) {
          e.preventDefault()
          last.focus()
        }
      } else {
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
  }, [open, onClose, submitting, isRegenerating])

  // 重置 preserveUserConfirmed
  useEffect(() => {
    if (open) setPreserveUserConfirmed(true)
  }, [open])

  if (!open) return null

  const stageLabel = fromStage === 'respond_complaint' ? '反证答辩书' : '投诉书'
  const hasAffectedList = affectedArtifacts.length > 0
  const busy = submitting || isRegenerating

  async function handleConfirm() {
    if (busy) return
    setSubmitting(true)
    try {
      await onConfirm(preserveUserConfirmed)
      // 由调用方在完成后关闭
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 md:items-center md:p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl md:max-w-lg md:rounded-2xl"
      >
        {/* 顶部标题 */}
        <header className="flex items-start gap-3 border-b border-[#EAEAEA] px-5 py-4">
          <div className="rounded-xl bg-amber-50 p-2 text-amber-600">
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              ref={titleRef}
              id={titleId}
              tabIndex={-1}
              className="text-base font-semibold text-[#111111] outline-none"
            >
              确认全文重新生成
            </h2>
            <p id={descId} className="mt-1 text-xs leading-5 text-[#565652]">
              {documentTitle ? `文书「${documentTitle}」` : '此文书'}将被全文重新生成，操作不可撤销。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="关闭对话框"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[#787774] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] disabled:opacity-50"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        {/* 主体 */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* 警告文案 */}
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800"
          >
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
            <div className="flex-1">
              <p className="font-medium">此操作将重新生成 {stageLabel} 全文</p>
              <p className="mt-0.5 leading-5">
                所有依赖此文书的下游产物将标记为<em className="font-semibold not-italic">过期</em>，
                需要重新生成。
              </p>
            </div>
          </div>

          {/* 受影响下游产物 */}
          <section className="mt-4" aria-labelledby="affected-artifacts-title">
            <h3 id="affected-artifacts-title" className="text-xs font-semibold text-[#565652]">
              受影响的下游产物
            </h3>
            {hasAffectedList ? (
              <ul className="mt-2 space-y-1.5">
                {affectedArtifacts.map((a) => (
                  <li
                    key={a.id}
                    className="flex items-start gap-2 rounded-md border border-[#EAEAEA] bg-[#F7F6F3] px-2.5 py-1.5 text-xs"
                  >
                    <span className="font-mono text-[10px] text-[#787774]" aria-hidden="true">
                      #{a.id}
                    </span>
                    <span className="flex-1 text-[#111111]">{a.summary}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 rounded-md border border-dashed border-[#EAEAEA] bg-[#F7F6F3] px-3 py-2 text-xs text-[#787774]">
                所有依赖此{stageLabel}的下游产物
              </p>
            )}
          </section>

          {/* 保留用户确认字段 */}
          <label
            className="mt-4 flex cursor-pointer items-start gap-2.5 rounded-lg border border-[#EAEAEA] bg-white px-3 py-2.5 transition hover:bg-[#F7F6F3]"
            htmlFor="preserve-user-confirmed"
          >
            <input
              id="preserve-user-confirmed"
              type="checkbox"
              checked={preserveUserConfirmed}
              onChange={(e) => setPreserveUserConfirmed(e.target.checked)}
              disabled={busy}
              className="mt-0.5 h-4 w-4 cursor-pointer accent-[#3f6b57]"
            />
            <span className="flex-1">
              <span className="flex items-center gap-1.5 text-sm font-medium text-[#111111]">
                <ShieldCheck className="h-3.5 w-3.5 text-[#3f6b57]" aria-hidden="true" />
                保留用户确认字段
              </span>
              <span className="mt-0.5 block text-[11px] leading-4 text-[#787774]">
                勾选后用户在事实核对阶段已确认的字段将不被重置，仅重新生成文书。
              </span>
            </span>
          </label>
        </div>

        {/* 底部操作 */}
        <footer className="flex flex-wrap items-center justify-end gap-3 border-t border-[#EAEAEA] bg-[#F7F6F3] px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-[#EAEAEA] bg-white px-4 py-2 text-sm font-medium text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={busy}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-[#3f6b57] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#2f5947] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
                正在重新生成...
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                确认重新生成
              </>
            )}
          </button>
        </footer>
      </div>
    </div>
  )
}

export default RegenerateConfirmDialog
