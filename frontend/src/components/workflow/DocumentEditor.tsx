// 文书编辑器：双栏布局 + 自动保存 + 段落级引用 + 重新生成 + AI/用户标记 + 影响确认
// 对齐 spec.md Task 4.3.1 ~ 4.3.9 / 设计文档 16 节 / Requirement: DocumentEditor Dual-Pane Layout
//
// 布局：
//   桌面端 ≥1280px：左文书正文（60-65%）+ 右 DocumentSourcePanel（35-40%）
//   平板 768-1279px：右栏可收起（默认收起，点击展开覆盖）
//   移动端 <768px：上下堆叠（文书在上，依据在下，可滑动切换 tab）
//
// 顶部工具栏：文档标题 + 版本号 + 保存状态 + 全文重新生成按钮 + 版本历史按钮
//
// 自动保存（debounce 1s）：编辑段落后调用 documentApi.regenerateParagraph，
//   创建新 DocumentVersion（created_by_type="user"）
//
// 流式生成：监听 SSE document.delta 事件，正文逐段写入；
//   用户向上滚动后停止自动跟随；底部显示「回到最新内容」按钮
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  AlertCircle,
  Check,
  Clipboard,
  History,
  Loader2,
  MoreVertical,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Sparkles,
  Trash2,
  User,
  Cpu,
  ArrowDown,
  X,
} from "lucide-react"
import type {
  DocumentDetail,
  DocumentVersion,
  LegalReference,
  Paragraph,
} from "@/types/document"
import { documentApi, DocumentApiError } from "@/lib/document-api"
import { workflowRunApi, type RetryRunResponse } from "@/lib/api"
import { useScrollFollow } from "@/hooks/useScrollFollow"
import { cn } from "@/lib/utils"
import { DocumentSourcePanel } from "./DocumentSourcePanel"
import { VersionHistoryDrawer } from "./VersionHistoryDrawer"
import { RegenerateConfirmDialog } from "./RegenerateConfirmDialog"
import { LegalReferenceModal } from "./LegalReferenceModal"

// ---------- 保存状态 ----------

type SaveStatus =
  | { kind: 'idle' }
  | { kind: 'saving' }
  | { kind: 'saved'; at: Date }
  | { kind: 'error'; message: string }

// ---------- 段落菜单状态 ----------

interface ParagraphMenuState {
  paragraphId: string
  open: boolean
}

// ---------- 工具：格式化时间 HH:MM ----------

function formatHM(d: Date): string {
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

// ---------- 主组件 ----------

export interface DocumentEditorProps {
  /** 文书详情（受控传入；调用方负责 getDocument 加载） */
  document: DocumentDetail
  /** 当 SSE document.delta 推送新内容时，调用方更新 document.paragraphs */
  onParagraphsChange?: (paragraphs: Paragraph[]) => void
  /** 点击证据编号跳转 EvidenceSourceViewer */
  onJumpToEvidence?: (evidenceCode: string, paragraphId?: string) => void
  /** 点击导出按钮 */
  onExport?: () => void
  /** 是否正在导出 */
  isExporting?: boolean
  /** 是否正在流式生成（来自 SSE connection 状态） */
  isStreaming?: boolean
  /** 当前用户是否为管理员（控制段落删除按钮可见性） */
  isAdmin?: boolean
  /** from_stage 用于全文重新生成，默认 'complaint' */
  fromStage?: 'complaint' | 'respond_complaint'
  /** 受影响下游产物列表（用于 RegenerateConfirmDialog） */
  affectedArtifacts?: Array<{ id: number; summary: string }>
  /** 全文重新生成成功后的回调（调用方应重定向到新 run） */
  onRegenerateFullSuccess?: (response: RetryRunResponse) => void
  /** 外部已加载的 export-check 结果 */
  exportCheckResult?: import("@/types/document").ExportCheckResult | null
  /** 外部刷新 export-check */
  onRefreshExportCheck?: () => void
}

export function DocumentEditor({
  document,
  onParagraphsChange,
  onJumpToEvidence,
  onExport,
  isExporting = false,
  isStreaming = false,
  isAdmin = false,
  fromStage = 'complaint',
  affectedArtifacts = [],
  onRegenerateFullSuccess,
  exportCheckResult,
  onRefreshExportCheck,
}: DocumentEditorProps) {
  // ---------- 状态 ----------
  const [paragraphs, setParagraphs] = useState<Paragraph[]>(document.paragraphs)
  const [currentVersion, setCurrentVersion] = useState<number>(document.current_version)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>({ kind: 'idle' })
  const [regeneratingParagraphs, setRegeneratingParagraphs] = useState<Set<string>>(new Set())
  const [showVersionDrawer, setShowVersionDrawer] = useState(false)
  const [showRegenerateDialog, setShowRegenerateDialog] = useState(false)
  const [legalRefOpen, setLegalRefOpen] = useState<LegalReference | null>(null)
  const [fullRegenerating, setFullRegenerating] = useState(false)
  const [fullRegenError, setFullRegenError] = useState<string | null>(null)
  const [mobileTab, setMobileTab] = useState<'editor' | 'source'>('editor')
  const [panelCollapsed, setPanelCollapsed] = useState(false)
  const [menuState, setMenuState] = useState<ParagraphMenuState | null>(null)
  const [toast, setToast] = useState<{ message: string; kind: 'info' | 'success' | 'error' } | null>(null)

  // 自动滚动跟随
  const { containerRef, isFollowing, onScroll, scrollToBottom } = useScrollFollow()

  // 文档变更时同步 paragraphs（外部受控加载新文档）
  useEffect(() => {
    setParagraphs(document.paragraphs)
    setCurrentVersion(document.current_version)
    setSaveStatus({ kind: 'idle' })
  }, [document.id, document.paragraphs, document.current_version])

  // 流式生成时自动跟随底部
  useEffect(() => {
    if (isStreaming && isFollowing) {
      scrollToBottom()
    }
  }, [paragraphs.length, isStreaming, isFollowing, scrollToBottom])

  // 关闭段落菜单（点击外部）
  useEffect(() => {
    if (!menuState?.open) return
    function handleClick(e: MouseEvent) {
      const target = e.target as HTMLElement
      if (!target.closest('[data-paragraph-menu]')) {
        setMenuState(null)
      }
    }
    globalThis.document.addEventListener('mousedown', handleClick)
    return () => globalThis.document.removeEventListener('mousedown', handleClick)
  }, [menuState?.open])

  // ---------- 通知 toast ----------
  function showToast(message: string, kind: 'info' | 'success' | 'error' = 'info') {
    setToast({ message, kind })
    setTimeout(() => setToast(null), 3000)
  }

  // ---------- 段落编辑 ----------

  function handleParagraphContentChange(paragraphId: string, content: string) {
    setParagraphs((prev) => {
      const next = prev.map((p) =>
        p.id === paragraphId ? { ...p, content, created_by_type: 'user' as const } : p,
      )
      // 通知外部
      onParagraphsChange?.(next)
      return next
    })
    scheduleSave(paragraphId, content)
  }

  // ---------- 自动保存（debounce 1s） ----------

  const saveTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const scheduleSave = useCallback((paragraphId: string, content: string) => {
    // 清除已有定时器
    const existing = saveTimersRef.current.get(paragraphId)
    if (existing) clearTimeout(existing)
    setSaveStatus({ kind: 'saving' })
    const timer = setTimeout(() => {
      void saveParagraph(paragraphId, content)
    }, 1000)
    saveTimersRef.current.set(paragraphId, timer)
  }, [])

  async function saveParagraph(paragraphId: string, content: string) {
    try {
      const response = await documentApi.regenerateParagraph(
        document.run_id,
        document.id,
        paragraphId,
        { content },
      )
      // 更新段落为用户修改版本
      setParagraphs((prev) =>
        prev.map((p) =>
          p.id === paragraphId
            ? {
                ...p,
                content: response.paragraph.content,
                created_by_type: 'user',
                version: response.version.version,
                created_at: response.version.created_at,
              }
            : p,
        ),
      )
      setCurrentVersion(response.version.version)
      setSaveStatus({ kind: 'saved', at: new Date() })
    } catch (err) {
      const msg =
        err instanceof DocumentApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : '保存失败'
      setSaveStatus({ kind: 'error', message: msg })
    }
  }

  function retrySave() {
    // 重新保存所有未保存段落（最简单：标记为 idle，下次编辑会触发）
    setSaveStatus({ kind: 'idle' })
    showToast('已重置保存状态，编辑后将自动重试', 'info')
  }

  // 卸载时清理定时器
  useEffect(() => {
    return () => {
      saveTimersRef.current.forEach((t) => clearTimeout(t))
      saveTimersRef.current.clear()
    }
  }, [])

  // ---------- 段落操作菜单 ----------

  function openMenu(paragraphId: string) {
    setMenuState({ paragraphId, open: true })
  }

  function closeMenu() {
    setMenuState(null)
  }

  // ---------- AI 重新生成段落 ----------

  async function regenerateParagraph(paragraphId: string) {
    closeMenu()
    setRegeneratingParagraphs((prev) => new Set(prev).add(paragraphId))
    setSaveStatus({ kind: 'saving' })
    try {
      const response = await documentApi.regenerateParagraph(
        document.run_id,
        document.id,
        paragraphId,
        {},
      )
      setParagraphs((prev) =>
        prev.map((p) =>
          p.id === paragraphId
            ? {
                ...p,
                content: response.paragraph.content,
                evidence_codes: response.paragraph.evidence_codes,
                legal_references: response.paragraph.legal_references,
                created_by_type: 'ai',
                version: response.version.version,
                created_at: response.version.created_at,
              }
            : p,
        ),
      )
      setCurrentVersion(response.version.version)
      setSaveStatus({ kind: 'saved', at: new Date() })
      showToast('段落已重新生成', 'success')
    } catch (err) {
      const msg =
        err instanceof DocumentApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : '重新生成失败'
      setSaveStatus({ kind: 'error', message: msg })
      showToast(msg, 'error')
    } finally {
      setRegeneratingParagraphs((prev) => {
        const next = new Set(prev)
        next.delete(paragraphId)
        return next
      })
    }
  }

  // ---------- 复制段落 ----------

  async function copyParagraph(paragraph: Paragraph) {
    closeMenu()
    try {
      await navigator.clipboard.writeText(paragraph.content)
      showToast('段落内容已复制', 'success')
    } catch {
      showToast('复制失败，请手动选择文本', 'error')
    }
  }

  // ---------- 删除段落（仅管理员） ----------

  function deleteParagraph(paragraphId: string) {
    closeMenu()
    if (!isAdmin) return
    setParagraphs((prev) => {
      const next = prev.filter((p) => p.id !== paragraphId)
      onParagraphsChange?.(next)
      return next
    })
    showToast('段落已删除', 'info')
    // 注意：后端暂无段落删除 API，此处仅前端移除；刷新后需重新加载
  }

  // ---------- 全文重新生成 ----------

  async function handleRegenerateFull(preserveUserConfirmed: boolean) {
    setFullRegenError(null)
    setFullRegenerating(true)
    try {
      const response = await workflowRunApi.retryRun(document.run_id, {
        from_stage: fromStage,
        preserve_user_confirmed: preserveUserConfirmed,
      })
      setShowRegenerateDialog(false)
      onRegenerateFullSuccess?.(response)
      showToast('已发起全文重新生成，正在切换到新运行...', 'success')
    } catch (err) {
      const msg = err instanceof Error ? err.message : '全文重新生成失败'
      setFullRegenError(msg)
      showToast(msg, 'error')
    } finally {
      setFullRegenerating(false)
    }
  }

  // ---------- 段落标签（AI/用户） ----------

  function getParagraphStyle(p: Paragraph): {
    bgClass: string
    badgeClass: string
    label: string
    Icon: typeof Cpu
  } {
    if (p.created_by_type === 'user') {
      return {
        bgClass: 'bg-emerald-50/60',
        badgeClass: 'bg-emerald-100 text-emerald-700 border-emerald-200',
        label: '用户',
        Icon: User,
      }
    }
    return {
      bgClass: 'bg-amber-50/60',
      badgeClass: 'bg-amber-100 text-amber-700 border-amber-200',
      label: 'AI',
      Icon: Cpu,
    }
  }

  // ---------- 版本回滚成功 ----------

  function handleRollbackSuccess(version: DocumentVersion) {
    setCurrentVersion(version.version)
    // 如果回滚返回了 content，将 content 切分为段落后更新
    if (version.content) {
      // 简单处理：将回滚内容作为单段（如果原 paragraphs 有结构则保留 id）
      setParagraphs((prev) => {
        if (prev.length === 1) {
          return [{
            ...prev[0],
            content: version.content,
            created_by_type: 'user',
            version: version.version,
            created_at: version.created_at,
          }]
        }
        // 多段时保留段落结构，将 content 按段落分隔符拆分（保守：仅整体替换第一段）
        return prev.map((p, idx) =>
          idx === 0
            ? { ...p, content: version.content, created_by_type: 'user', version: version.version, created_at: version.created_at }
            : p,
        )
      })
    }
    setShowVersionDrawer(false)
    showToast(`已回滚到版本 v${version.version}`, 'success')
  }

  // ---------- 保存状态指示文案 ----------

  const saveStatusText = useMemo(() => {
    switch (saveStatus.kind) {
      case 'idle':
        return ''
      case 'saving':
        return '保存中...'
      case 'saved':
        return `已保存 ${formatHM(saveStatus.at)}`
      case 'error':
        return '保存失败'
    }
  }, [saveStatus])

  const showScrollToBottom = isStreaming && !isFollowing

  return (
    <div className="flex h-full flex-col bg-[#f8f8f5]">
      {/* 顶部工具栏 */}
      <header className="flex flex-wrap items-center gap-2 border-b border-[#EAEAEA] bg-white px-3 py-2 sm:px-4">
        {/* 标题 */}
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-sm font-semibold text-[#111111] sm:text-base">
            {document.title}
          </h1>
          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-[#787774]">
            <span className="font-mono">v{currentVersion}</span>
            {document.template_type && <span>· {document.template_type}</span>}
            {isStreaming && (
              <span className="inline-flex items-center gap-1 text-[#3f6b57]" role="status">
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                生成中
              </span>
            )}
            {/* 保存状态指示 */}
            {saveStatus.kind === 'saving' && (
              <span
                className="inline-flex items-center gap-1 text-[#787774]"
                aria-live="polite"
              >
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                {saveStatusText}
              </span>
            )}
            {saveStatus.kind === 'saved' && (
              <span
                className="inline-flex items-center gap-1 text-emerald-600"
                aria-live="polite"
              >
                <Check className="h-3 w-3" aria-hidden="true" />
                {saveStatusText}
              </span>
            )}
            {saveStatus.kind === 'error' && (
              <button
                type="button"
                onClick={retrySave}
                className="inline-flex items-center gap-1 text-red-600 hover:text-red-700 focus:outline-none focus-visible:underline"
                aria-live="polite"
                role="alert"
              >
                <AlertCircle className="h-3 w-3" aria-hidden="true" />
                {saveStatusText} - 点击重试
              </button>
            )}
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex flex-shrink-0 items-center gap-1.5">
          {/* 版本历史 */}
          <button
            type="button"
            onClick={() => setShowVersionDrawer(true)}
            aria-label="查看版本历史"
            className="inline-flex min-h-[36px] items-center gap-1 rounded-lg border border-[#EAEAEA] bg-white px-2 py-1.5 text-xs text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57]"
          >
            <History className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">版本历史</span>
          </button>

          {/* 全文重新生成 */}
          <button
            type="button"
            onClick={() => setShowRegenerateDialog(true)}
            disabled={fullRegenerating || isStreaming}
            aria-label="全文重新生成"
            className="inline-flex min-h-[36px] items-center gap-1 rounded-lg border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", fullRegenerating && "animate-spin")} aria-hidden="true" />
            <span className="hidden sm:inline">全文重新生成</span>
          </button>

          {/* 桌面端右栏收起/展开 */}
          <button
            type="button"
            onClick={() => setPanelCollapsed((v) => !v)}
            aria-label={panelCollapsed ? '展开依据面板' : '收起依据面板'}
            aria-expanded={!panelCollapsed}
            className="hidden min-h-[36px] items-center justify-center rounded-lg border border-[#EAEAEA] bg-white px-2 py-1.5 text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] xl:inline-flex"
          >
            {panelCollapsed ? (
              <PanelLeftOpen className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <PanelLeftClose className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>
        </div>

        {/* 全文重新生成错误提示 */}
        {fullRegenError && (
          <div
            role="alert"
            className="mt-1 flex w-full items-start gap-2 rounded-md border border-red-200 bg-red-50 px-2 py-1 text-[11px] text-red-700"
          >
            <AlertCircle className="mt-0.5 h-3 w-3 flex-shrink-0" aria-hidden="true" />
            <span className="break-words">{fullRegenError}</span>
          </div>
        )}
      </header>

      {/* 移动端 tab 切换 */}
      <div className="flex border-b border-[#EAEAEA] bg-white md:hidden" role="tablist" aria-label="文书编辑器视图切换">
        <button
          type="button"
          role="tab"
          aria-selected={mobileTab === 'editor'}
          aria-controls="editor-pane-mobile"
          onClick={() => setMobileTab('editor')}
          className={cn(
            "min-h-[44px] flex-1 px-4 text-xs font-medium transition",
            mobileTab === 'editor'
              ? "border-b-2 border-[#3f6b57] text-[#3f6b57]"
              : "text-[#787774]",
          )}
        >
          文书正文
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mobileTab === 'source'}
          aria-controls="source-pane-mobile"
          onClick={() => setMobileTab('source')}
          className={cn(
            "min-h-[44px] flex-1 px-4 text-xs font-medium transition",
            mobileTab === 'source'
              ? "border-b-2 border-[#3f6b57] text-[#3f6b57]"
              : "text-[#787774]",
          )}
        >
          依据与质量
        </button>
      </div>

      {/* 主体：双栏 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧：文书正文 */}
        <main
          id="editor-pane-mobile"
          role="tabpanel"
          aria-label="文书正文"
          className={cn(
            "flex min-w-0 flex-1 flex-col",
            // 移动端 tab 切换
            mobileTab !== 'editor' && 'hidden md:flex',
            // 桌面端右栏收起时占满
            panelCollapsed ? 'xl:w-full' : 'xl:w-[62%]',
          )}
        >
          <div
            ref={containerRef}
            onScroll={onScroll}
            className="relative flex-1 overflow-y-auto px-3 py-4 sm:px-6"
          >
            {paragraphs.length === 0 && !isStreaming && (
              <div className="flex h-full flex-col items-center justify-center gap-2 py-12 text-center text-[#787774]">
                <AlertCircle className="h-6 w-6" aria-hidden="true" />
                <p className="text-sm">暂无文书内容</p>
              </div>
            )}

            <article className="mx-auto max-w-3xl space-y-3">
              {paragraphs.map((p, idx) => {
                const style = getParagraphStyle(p)
                const StyleIcon = style.Icon
                const isRegenerating = regeneratingParagraphs.has(p.id)
                const isMenuOpen = menuState?.paragraphId === p.id && menuState.open
                const tooltipText = [
                  p.created_at ? `创建时间：${new Date(p.created_at).toLocaleString('zh-CN', { hour12: false })}` : '',
                  `创建者：${style.label}`,
                  p.version ? `版本：v${p.version}` : '',
                ].filter(Boolean).join('；')

                return (
                  <div
                    key={p.id}
                    data-paragraph-id={p.id}
                    className={cn(
                      "group relative rounded-lg border border-[#EAEAEA] p-3 transition",
                      style.bgClass,
                      isRegenerating && "ring-2 ring-amber-300",
                    )}
                  >
                    {/* 段落右上角：标签 + 操作按钮 */}
                    <div className="absolute right-2 top-2 flex items-center gap-1">
                      <span
                        className={cn(
                          "inline-flex items-center gap-0.5 rounded-full border px-1.5 py-0 text-[10px] font-medium",
                          style.badgeClass,
                        )}
                        title={tooltipText}
                        aria-label={tooltipText}
                      >
                        <StyleIcon className="h-2.5 w-2.5" aria-hidden="true" />
                        {style.label}
                      </span>

                      {/* 操作菜单 */}
                      <div className="relative" data-paragraph-menu>
                        <button
                          type="button"
                          onClick={() => (isMenuOpen ? closeMenu() : openMenu(p.id))}
                          disabled={isRegenerating}
                          aria-label={`段落 ${idx + 1} 操作`}
                          aria-expanded={isMenuOpen}
                          aria-haspopup="menu"
                          className="inline-flex min-h-[28px] min-w-[28px] items-center justify-center rounded-md text-[#787774] opacity-0 transition hover:bg-white/70 hover:text-[#565652] focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] group-hover:opacity-100 disabled:opacity-30"
                        >
                          <MoreVertical className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                        {isMenuOpen && (
                          <div
                            role="menu"
                            aria-label={`段落 ${idx + 1} 操作菜单`}
                            className="absolute right-0 top-full z-20 mt-1 w-44 overflow-hidden rounded-lg border border-[#EAEAEA] bg-white shadow-lg"
                          >
                            <button
                              type="button"
                              role="menuitem"
                              onClick={() => regenerateParagraph(p.id)}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:bg-[#F7F6F3]"
                            >
                              <Sparkles className="h-3.5 w-3.5 text-amber-600" aria-hidden="true" />
                              AI 重新生成此段
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              onClick={() => copyParagraph(p)}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:bg-[#F7F6F3]"
                            >
                              <Clipboard className="h-3.5 w-3.5 text-[#565652]" aria-hidden="true" />
                              复制段落
                            </button>
                            {isAdmin && (
                              <button
                                type="button"
                                role="menuitem"
                                onClick={() => deleteParagraph(p.id)}
                                className="flex w-full items-center gap-2 border-t border-[#EAEAEA] px-3 py-2 text-left text-xs text-red-600 transition hover:bg-red-50 focus:outline-none focus-visible:bg-red-50"
                              >
                                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                                删除段落
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* 段落内容：可编辑 */}
                    {isRegenerating ? (
                      <div
                        className="flex items-center gap-2 py-2 text-xs text-amber-700"
                        aria-live="polite"
                      >
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        正在生成...
                      </div>
                    ) : (
                      <textarea
                        value={p.content}
                        onChange={(e) => handleParagraphContentChange(p.id, e.target.value)}
                        aria-label={`段落 ${idx + 1} 内容`}
                        className="block min-h-[60px] w-full resize-y border-0 bg-transparent p-0 text-sm leading-7 text-[#111111] outline-none focus:ring-0"
                        spellCheck={false}
                      />
                    )}

                    {/* 证据引用 chips */}
                    {(p.evidence_codes.length > 0 || p.legal_references.length > 0) && (
                      <div className="mt-2 flex flex-wrap items-center gap-1 border-t border-[#EAEAEA] pt-2">
                        {p.evidence_codes.map((code) => (
                          <button
                            key={code}
                            type="button"
                            onClick={() => onJumpToEvidence?.(code, p.id)}
                            className="inline-flex min-h-[24px] items-center gap-0.5 rounded-full border border-sky-200 bg-sky-50 px-1.5 py-0 text-[10px] font-medium text-sky-700 transition hover:bg-sky-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
                            aria-label={`跳转到证据 ${code}`}
                          >
                            {code}
                          </button>
                        ))}
                        {p.legal_references.map((ref, refIdx) => (
                          <button
                            key={`${ref.law_name}-${refIdx}`}
                            type="button"
                            onClick={() => setLegalRefOpen(ref)}
                            className="inline-flex min-h-[24px] items-center gap-0.5 rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0 text-[10px] font-medium text-emerald-700 transition hover:bg-emerald-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
                            aria-label={`查看法条 ${ref.law_name} ${ref.article_number}`}
                          >
                            {ref.law_name} {ref.article_number}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}

              {isStreaming && paragraphs.length === 0 && (
                <div
                  className="flex items-center justify-center gap-2 py-8 text-sm text-[#787774]"
                  aria-live="polite"
                >
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  正在生成文书...
                </div>
              )}
            </article>
          </div>

          {/* 流式生成：回到最新内容按钮 */}
          {showScrollToBottom && (
            <button
              type="button"
              onClick={scrollToBottom}
              className="absolute bottom-4 left-1/2 z-10 inline-flex min-h-[40px] -translate-x-1/2 items-center gap-1.5 rounded-full bg-[#3f6b57] px-4 text-xs font-medium text-white shadow-lg transition hover:bg-[#2f5947] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57]"
              aria-label="回到最新内容"
            >
              <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
              回到最新内容
            </button>
          )}
        </main>

        {/* 右侧：依据与质量面板 */}
        <aside
          id="source-pane-mobile"
          role="tabpanel"
          aria-label="依据与质量"
          className={cn(
            "flex flex-col border-l border-[#EAEAEA] bg-white",
            // 移动端 tab 切换
            mobileTab !== 'source' && 'hidden md:flex',
            // 平板（768-1279px）：默认收起；展开时覆盖
            "md:absolute md:inset-y-0 md:right-0 md:top-0 md:z-30 md:w-[360px] md:shadow-2xl",
            // 默认收起（平板）：translate 隐藏；桌面端始终显示
            panelCollapsed ? "md:translate-x-full" : "md:translate-x-0",
            // 桌面端：恢复静态定位 + 占 38%
            "xl:static xl:w-[38%] xl:translate-x-0 xl:shadow-none",
          )}
        >
          <DocumentSourcePanel
            runId={document.run_id}
            documentId={document.id}
            paragraphs={paragraphs}
            onJumpToEvidence={onJumpToEvidence}
            onShowLegalReference={(ref) => setLegalRefOpen(ref)}
            onExport={onExport}
            isExporting={isExporting}
            exportCheckResult={exportCheckResult}
            onRefreshExportCheck={onRefreshExportCheck}
          />
          {/* 平板端关闭按钮（覆盖时显示） */}
          <button
            type="button"
            onClick={() => setPanelCollapsed(true)}
            aria-label="收起依据面板"
            className="absolute left-0 top-3 hidden min-h-[36px] min-w-[36px] items-center justify-center rounded-r-lg bg-white text-[#565652] shadow-md transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] md:inline-flex xl:hidden"
          >
            <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
          </button>
        </aside>

        {/* 平板端展开按钮（panelCollapsed 时显示） */}
        {panelCollapsed && (
          <button
            type="button"
            onClick={() => setPanelCollapsed(false)}
            aria-label="展开依据面板"
            className="absolute right-0 top-1/2 z-20 hidden min-h-[44px] min-w-[32px] -translate-y-1/2 items-center justify-center rounded-l-lg bg-white text-[#3f6b57] shadow-md transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] md:inline-flex xl:hidden"
          >
            <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* 全文重新生成 loading 遮罩 */}
      {fullRegenerating && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/30"
          role="status"
          aria-live="polite"
        >
          <div className="flex flex-col items-center gap-2 rounded-lg bg-white px-6 py-5 shadow-xl">
            <Loader2 className="h-6 w-6 animate-spin text-[#3f6b57]" aria-hidden="true" />
            <p className="text-sm text-[#111111]">正在重新生成...</p>
            <p className="text-[11px] text-[#787774]">
              下游产物将被标记为过期
            </p>
          </div>
        </div>
      )}

      {/* toast 通知 */}
      {toast && (
        <div
          className={cn(
            "fixed bottom-4 left-1/2 z-50 inline-flex min-h-[40px] max-w-[90vw] -translate-x-1/2 items-center gap-2 rounded-full px-4 text-xs font-medium shadow-lg",
            toast.kind === 'success' && "bg-emerald-600 text-white",
            toast.kind === 'error' && "bg-red-600 text-white",
            toast.kind === 'info' && "bg-[#111111] text-white",
          )}
          role={toast.kind === 'error' ? 'alert' : 'status'}
          aria-live="polite"
        >
          {toast.kind === 'success' && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
          {toast.kind === 'error' && <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />}
          {toast.message}
          <button
            type="button"
            onClick={() => setToast(null)}
            aria-label="关闭通知"
            className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full hover:bg-white/20"
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        </div>
      )}

      {/* 版本历史抽屉 */}
      <VersionHistoryDrawer
        open={showVersionDrawer}
        onClose={() => setShowVersionDrawer(false)}
        runId={document.run_id}
        documentId={document.id}
        currentVersion={currentVersion}
        onRollbackSuccess={handleRollbackSuccess}
      />

      {/* 全文重新生成确认对话框 */}
      <RegenerateConfirmDialog
        open={showRegenerateDialog}
        onClose={() => setShowRegenerateDialog(false)}
        onConfirm={handleRegenerateFull}
        documentTitle={document.title}
        affectedArtifacts={affectedArtifacts}
        isRegenerating={fullRegenerating}
        fromStage={fromStage}
      />

      {/* 法条原文弹窗 */}
      <LegalReferenceModal
        reference={legalRefOpen}
        onClose={() => setLegalRefOpen(null)}
      />
    </div>
  )
}

export default DocumentEditor
