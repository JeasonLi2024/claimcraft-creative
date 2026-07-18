// 法条原文弹窗：展示单条法条引用的详细信息
// 对齐 spec.md Task 4.3.4 / 设计文档 16 节
// 显示：法条名称 + 条款编号 + 原文 + 来源 URL + 「在法条库中查看」按钮
//
// 调用方：段落 legal_references 列表中点击某条法条时打开
import { useEffect, useRef } from "react"
import { BookOpen, ExternalLink, FileText, X } from "lucide-react"
import type { LegalReference } from "@/types/document"

// ---------- 工具：构建在法条库中查看的链接 ----------
// 若 legal_reference.source_url 已提供则直接使用，否则构造占位搜索链接（仅展示用）

function buildLibraryUrl(ref: LegalReference): string | null {
  if (ref.source_url && ref.source_url.trim() !== "") return ref.source_url
  // 后端 LawRetriever 可访问的库链接由后端提供；前端无法直接构造
  return null
}

// ---------- 主组件 ----------

export interface LegalReferenceModalProps {
  reference: LegalReference | null
  onClose: () => void
}

export function LegalReferenceModal({ reference, onClose }: LegalReferenceModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = "legal-reference-modal-title"
  const descId = "legal-reference-modal-desc"

  // Escape 关闭
  useEffect(() => {
    if (!reference) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener("keydown", handleKeyDown, true)
    return () => document.removeEventListener("keydown", handleKeyDown, true)
  }, [reference, onClose])

  if (!reference) return null

  const libraryUrl = buildLibraryUrl(reference)
  const hasText = Boolean(reference.text && reference.text.trim() !== "")
  const fullName = `${reference.law_name} ${reference.article_number}`.trim()

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 md:items-center md:p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="flex max-h-[88vh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl md:max-w-2xl md:rounded-2xl motion-safe:animate-[drawer-slide-in_0.2s_ease-out]"
      >
        {/* 顶部标题栏 */}
        <header className="flex items-center justify-between gap-3 border-b border-[#EAEAEA] px-5 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <div className="rounded-lg bg-[#e7eee9] p-2 text-[#2f5947]">
              <BookOpen className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h2 id={titleId} className="truncate text-sm font-semibold text-[#111111]">
                {fullName || "法条原文"}
              </h2>
              <p id={descId} className="mt-0.5 text-[11px] text-[#787774]">
                查看引用法条原文与来源
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭法条原文弹窗"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[#787774] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57]"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        {/* 主体内容 */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* 元信息 */}
          <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-[#EAEAEA] bg-[#F7F6F3] px-3 py-2">
              <dt className="text-[11px] font-medium uppercase tracking-wide text-[#787774]">
                法条名称
              </dt>
              <dd className="mt-0.5 text-sm text-[#111111]">{reference.law_name}</dd>
            </div>
            <div className="rounded-lg border border-[#EAEAEA] bg-[#F7F6F3] px-3 py-2">
              <dt className="text-[11px] font-medium uppercase tracking-wide text-[#787774]">
                条款编号
              </dt>
              <dd className="mt-0.5 text-sm text-[#111111]">{reference.article_number}</dd>
            </div>
          </dl>

          {/* 法条原文 */}
          <section
            aria-labelledby="legal-text-title"
            className="mt-4 rounded-lg border border-[#EAEAEA] bg-white"
          >
            <header className="flex items-center gap-2 border-b border-[#EAEAEA] px-3 py-2">
              <FileText className="h-3.5 w-3.5 text-[#565652]" aria-hidden="true" />
              <h3 id="legal-text-title" className="text-xs font-semibold text-[#565652]">
                法条原文
              </h3>
            </header>
            <div className="max-h-[50vh] overflow-y-auto px-4 py-3">
              {hasText ? (
                <pre className="whitespace-pre-wrap break-words text-sm leading-7 text-[#111111]">
                  {reference.text}
                </pre>
              ) : (
                <p className="py-6 text-center text-xs text-[#787774]">
                  暂无法条原文。可点击下方「在法条库中查看」查阅完整内容。
                </p>
              )}
            </div>
          </section>
        </div>

        {/* 底部操作 */}
        <footer className="flex flex-wrap items-center justify-end gap-3 border-t border-[#EAEAEA] bg-[#F7F6F3] px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-[#EAEAEA] bg-white px-4 py-2 text-sm font-medium text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57]"
          >
            关闭
          </button>
          {libraryUrl && (
            <a
              href={libraryUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-[#3f6b57] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#2f5947] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57]"
            >
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
              在法条库中查看
            </a>
          )}
        </footer>
      </div>
    </div>
  )
}

export default LegalReferenceModal
