// 版本历史抽屉：列出所有文书版本 + 版本对比 + 回滚
// 对齐 spec.md Task 4.3.3 / 设计文档 16 节
//
// 数据源：documentApi.listDocumentVersions(runId, documentId)
// 版本对比：选择两个版本后展示行级 diff（LCS，不引入新库）
// 回滚：documentApi.rollbackDocumentVersion(runId, documentId, version)
//
// 关闭按钮 + Escape + 焦点锁定
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  AlertCircle,
  CheckCircle,
  GitCompare,
  History,
  Loader2,
  RotateCcw,
  User,
  Cpu,
  X,
} from "lucide-react"
import type { DocumentVersion } from "@/types/document"
import { documentApi, DocumentApiError } from "@/lib/document-api"

// ---------- 时间格式化 ----------

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return "--"
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleString("zh-CN", { hour12: false })
  } catch {
    return ts
  }
}

// ---------- 行级 diff（LCS，不引入新库） ----------

interface DiffLine {
  type: 'common' | 'removed' | 'added'
  text: string
}

function computeDiff(oldText: string, newText: string): DiffLine[] {
  const oldLines = oldText.split('\n')
  const newLines = newText.split('\n')
  const m = oldLines.length
  const n = newLines.length
  // LCS DP 表（从后向前）
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0))
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (oldLines[i] === newLines[j]) {
        dp[i][j] = dp[i + 1][j + 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1])
      }
    }
  }
  const result: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < m && j < n) {
    if (oldLines[i] === newLines[j]) {
      result.push({ type: 'common', text: oldLines[i] })
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      result.push({ type: 'removed', text: oldLines[i] })
      i++
    } else {
      result.push({ type: 'added', text: newLines[j] })
      j++
    }
  }
  while (i < m) {
    result.push({ type: 'removed', text: oldLines[i] })
    i++
  }
  while (j < n) {
    result.push({ type: 'added', text: newLines[j] })
    j++
  }
  return result
}

// ---------- 创建者类型徽章 ----------

interface CreatedByConfig {
  label: string
  icon: typeof User
  iconClass: string
  badgeClass: string
}

const CREATED_BY_CONFIG: Record<'user' | 'ai', CreatedByConfig> = {
  user: {
    label: '用户',
    icon: User,
    iconClass: 'text-emerald-600',
    badgeClass: 'bg-emerald-50 border-emerald-200 text-emerald-700',
  },
  ai: {
    label: 'AI',
    icon: Cpu,
    iconClass: 'text-amber-600',
    badgeClass: 'bg-amber-50 border-amber-200 text-amber-700',
  },
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

export interface VersionHistoryDrawerProps {
  open: boolean
  onClose: () => void
  /** 运行 ID */
  runId: number
  /** 文书 ID */
  documentId: string
  /** 当前版本号（用于高亮） */
  currentVersion?: number
  /** 回滚成功后的回调（调用方刷新文书内容） */
  onRollbackSuccess?: (version: DocumentVersion) => void
}

export function VersionHistoryDrawer({
  open,
  onClose,
  runId,
  documentId,
  currentVersion,
  onRollbackSuccess,
}: VersionHistoryDrawerProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notImplemented, setNotImplemented] = useState(false)
  const [versions, setVersions] = useState<DocumentVersion[]>([])
  const [compareA, setCompareA] = useState<number | null>(null)
  const [compareB, setCompareB] = useState<number | null>(null)
  const [rollingBack, setRollingBack] = useState<number | null>(null)
  const [rollbackError, setRollbackError] = useState<string | null>(null)
  const drawerRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)

  // 加载版本列表
  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setNotImplemented(false)
    setRollbackError(null)
    documentApi
      .listDocumentVersions(runId, documentId)
      .then((data) => {
        if (cancelled) return
        setVersions(data)
        if (data.length === 0) {
          // 后端未实现时返回空数组，提示用户
          setNotImplemented(true)
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return
        if (e instanceof DocumentApiError && e.notImplemented) {
          setNotImplemented(true)
          setVersions([])
        } else {
          const msg = e instanceof Error ? e.message : "加载版本列表失败"
          setError(msg)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, runId, documentId])

  // Escape + 焦点锁定
  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => titleRef.current?.focus(), 50)

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== "Tab") return
      const focusable = getFocusableElements(drawerRef.current)
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey) {
        if (active === first || !drawerRef.current?.contains(active)) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (active === last || !drawerRef.current?.contains(active)) {
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
  }, [open, onClose])

  // 计算两版本 diff
  const diffLines = useMemo<DiffLine[]>(() => {
    if (compareA == null || compareB == null) return []
    const va = versions.find((v) => v.version === compareA)
    const vb = versions.find((v) => v.version === compareB)
    if (!va || !vb) return []
    return computeDiff(va.content || '', vb.content || '')
  }, [compareA, compareB, versions])

  // 选中对比：再次点击同一版本取消选中
  const handleToggleCompare = useCallback((version: number) => {
    setRollbackError(null)
    setCompareA((prevA) => {
      if (prevA === version) return null
      if (prevA == null) return version
      return prevA
    })
    setCompareB((prevB) => {
      if (prevB === version) return null
      if (prevB == null) return version
      return prevB
    })
  }, [])

  // 回滚到指定版本
  async function handleRollback(version: number) {
    if (rollingBack != null) return
    setRollingBack(version)
    setRollbackError(null)
    try {
      const newVersion = await documentApi.rollbackDocumentVersion(runId, documentId, version)
      onRollbackSuccess?.(newVersion)
      // 刷新版本列表
      try {
        const refreshed = await documentApi.listDocumentVersions(runId, documentId)
        setVersions(refreshed)
      } catch {
        // 静默忽略刷新失败
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "回滚版本失败"
      setRollbackError(msg)
    } finally {
      setRollingBack(null)
    }
  }

  if (!open) return null

  const hasVersions = versions.length > 0
  const canDiff = compareA != null && compareB != null && compareA !== compareB

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label="版本历史"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="关闭版本历史"
        className="absolute inset-0 cursor-default bg-black/40"
      />

      <aside
        ref={drawerRef}
        className="relative flex h-full w-full max-w-lg flex-col bg-white shadow-2xl motion-safe:animate-[drawer-slide-in_0.25s_ease-out]"
      >
        {/* 顶部 */}
        <header className="flex items-center justify-between border-b border-[#EAEAEA] px-4 py-3">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-[#565652]" aria-hidden="true" />
            <h2
              ref={titleRef}
              tabIndex={-1}
              className="text-sm font-semibold text-[#111111] outline-none"
            >
              版本历史
            </h2>
            {hasVersions && (
              <span className="rounded-full bg-[#F7F6F3] px-2 py-0 text-[10px] text-[#787774]">
                共 {versions.length} 个版本
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[#787774] hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57]"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        {/* 操作提示 */}
        <div className="border-b border-[#EAEAEA] bg-[#F7F6F3] px-4 py-2 text-[11px] text-[#787774]">
          <p>
            <GitCompare className="mr-1 inline h-3 w-3 align-text-bottom" aria-hidden="true" />
            点击两个版本可进行对比；点击「回滚」按钮恢复到指定版本（创建新版本）。
          </p>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading && (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
              <Loader2 className="h-5 w-5 animate-spin text-[#3f6b57]" aria-hidden="true" />
              <p className="text-xs text-[#787774]">加载版本列表…</p>
            </div>
          )}

          {!loading && error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
              <div className="flex-1">
                <p className="font-medium">加载失败</p>
                <p className="mt-0.5 break-words text-[11px]">{error}</p>
              </div>
            </div>
          )}

          {!loading && !error && notImplemented && (
            <div
              role="status"
              className="flex flex-col items-center justify-center gap-2 py-12 text-center"
            >
              <History className="h-6 w-6 text-[#787774]" aria-hidden="true" />
              <p className="text-sm text-[#565652]">版本历史暂未启用</p>
              <p className="max-w-xs text-[11px] text-[#787774]">
                后端文档版本端点尚未实现。当前可编辑文书并保存修改；版本对比与回滚功能将在后续版本中启用。
              </p>
            </div>
          )}

          {!loading && !error && !notImplemented && !hasVersions && (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
              <History className="h-6 w-6 text-[#787774]" aria-hidden="true" />
              <p className="text-sm text-[#565652]">暂无历史版本</p>
            </div>
          )}

          {!loading && !error && !notImplemented && hasVersions && (
            <ul className="flex flex-col gap-2">
              {versions.map((v) => {
                const cfg = CREATED_BY_CONFIG[v.created_by_type] || CREATED_BY_CONFIG.ai
                const CreatedByIcon = cfg.icon
                const isCurrent = currentVersion === v.version
                const isCompareA = compareA === v.version
                const isCompareB = compareB === v.version
                const isCompareSelected = isCompareA || isCompareB
                const isRollingBack = rollingBack === v.version
                return (
                  <li key={v.id}>
                    <article
                      className={`rounded-xl border px-3 py-2.5 transition ${
                        isCurrent
                          ? "border-[#3f6b57] bg-[#e7eee9] ring-1 ring-[#3f6b57]/30"
                          : isCompareSelected
                            ? "border-sky-300 bg-sky-50"
                            : "border-[#EAEAEA] bg-white hover:bg-[#F7F6F3]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="font-mono text-xs font-semibold text-[#111111]">
                              v{v.version}
                            </span>
                            <span
                              className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0 text-[10px] ${cfg.badgeClass}`}
                              role="status"
                            >
                              <CreatedByIcon className="h-2.5 w-2.5" aria-hidden="true" />
                              {cfg.label}
                            </span>
                            {isCurrent && (
                              <span
                                className="inline-flex items-center gap-0.5 rounded-full border border-[#3f6b57]/40 bg-[#e7eee9] px-1.5 py-0 text-[10px] font-medium text-[#2f5947]"
                              >
                                <CheckCircle className="h-2.5 w-2.5" aria-hidden="true" />
                                当前
                              </span>
                            )}
                            {isCompareA && (
                              <span className="rounded-full border border-sky-200 bg-sky-50 px-1.5 py-0 text-[10px] font-medium text-sky-700">
                                对比 A
                              </span>
                            )}
                            {isCompareB && (
                              <span className="rounded-full border border-sky-200 bg-sky-50 px-1.5 py-0 text-[10px] font-medium text-sky-700">
                                对比 B
                              </span>
                            )}
                          </div>
                          <p className="mt-1 text-[11px] text-[#787774]">
                            {formatTimestamp(v.created_at)}
                          </p>
                          {v.workflow_version && (
                            <p className="mt-0.5 text-[11px] text-[#787774]">
                              工作流版本：<span className="font-mono">{v.workflow_version}</span>
                            </p>
                          )}
                          {v.changelog && (
                            <p className="mt-0.5 text-[11px] text-[#565652] break-words">
                              {v.changelog}
                            </p>
                          )}
                        </div>

                        <div className="flex flex-shrink-0 flex-col items-end gap-1">
                          <button
                            type="button"
                            onClick={() => handleToggleCompare(v.version)}
                            aria-pressed={isCompareSelected}
                            aria-label={`选择版本 v${v.version} 进行对比`}
                            className="inline-flex min-h-[32px] items-center gap-1 rounded-lg border border-[#EAEAEA] bg-white px-2 py-0.5 text-[11px] text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57]"
                          >
                            <GitCompare className="h-3 w-3" aria-hidden="true" />
                            对比
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRollback(v.version)}
                            disabled={isCurrent || isRollingBack}
                            aria-label={`回滚到版本 v${v.version}`}
                            className="inline-flex min-h-[32px] items-center gap-1 rounded-lg border border-[#EAEAEA] bg-white px-2 py-0.5 text-[11px] text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isRollingBack ? (
                              <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                            ) : (
                              <RotateCcw className="h-3 w-3" aria-hidden="true" />
                            )}
                            回滚
                          </button>
                        </div>
                      </div>
                    </article>
                  </li>
                )
              })}
            </ul>
          )}

          {/* 版本对比 */}
          {canDiff && diffLines.length > 0 && (
            <section
              aria-labelledby="diff-title"
              className="mt-4 rounded-lg border border-[#EAEAEA]"
            >
              <header className="flex items-center justify-between border-b border-[#EAEAEA] px-3 py-2">
                <h3 id="diff-title" className="text-xs font-semibold text-[#565652]">
                  版本对比：v{compareA} → v{compareB}
                </h3>
                <button
                  type="button"
                  onClick={() => {
                    setCompareA(null)
                    setCompareB(null)
                  }}
                  aria-label="清除对比选择"
                  className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center rounded text-[#787774] hover:bg-slate-200"
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </header>
              <div className="max-h-72 overflow-y-auto">
                <ul className="divide-y divide-slate-100">
                  {diffLines.map((line, idx) => {
                    const bgClass =
                      line.type === 'removed'
                        ? 'bg-red-50'
                        : line.type === 'added'
                          ? 'bg-emerald-50'
                          : ''
                    const textClass =
                      line.type === 'removed'
                        ? 'text-red-800'
                        : line.type === 'added'
                          ? 'text-emerald-800'
                          : 'text-slate-700'
                    const prefix =
                      line.type === 'removed' ? '- ' : line.type === 'added' ? '+ ' : '  '
                    const prefixClass =
                      line.type === 'removed'
                        ? 'text-red-500'
                        : line.type === 'added'
                          ? 'text-emerald-600'
                          : 'text-slate-400'
                    return (
                      <li
                        key={`diff-${idx}`}
                        className={`flex items-start gap-1 px-3 py-1 text-xs ${bgClass}`}
                      >
                        <span className={`font-mono ${prefixClass}`} aria-hidden="true">
                          {prefix}
                        </span>
                        <span className={`flex-1 whitespace-pre-wrap break-words ${textClass}`}>
                          {line.text || ' '}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              </div>
              <p className="border-t border-slate-100 px-3 py-1.5 text-[10px] text-[#787774]">
                <span className="text-red-600">- </span>仅 v{compareA} ／
                <span className="ml-2 text-emerald-600">+ </span>仅 v{compareB}
              </p>
            </section>
          )}

          {rollbackError && (
            <div
              role="alert"
              className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
              <div className="flex-1">
                <p className="font-medium">回滚失败</p>
                <p className="mt-0.5 break-words text-[11px]">{rollbackError}</p>
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

export default VersionHistoryDrawer
