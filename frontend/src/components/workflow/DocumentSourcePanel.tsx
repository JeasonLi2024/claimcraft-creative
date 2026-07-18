// 文书依据与质量面板（右侧栏）
// 对齐 spec.md Task 4.3.8 / 设计文档 16 节 / Requirement: DocumentEditor Dual-Pane Layout
//
// 包含五个分区：
//   1. 引用证据列表（按段分组，点击跳转 EvidenceSourceViewer）
//   2. 引用法条列表（点击查看原文 LegalReferenceModal）
//   3. 风险提示（来自 export-check / quality_gate_service 的 issues 中 severity=warning/blocking）
//   4. 完整性检查（事实 / 依据 / 诉求三段是否齐全）
//   5. 导出按钮（passed=true 启用，passed=false 禁用 + tooltip）
//
// 导出前自动调用 exportCheck API 刷新状态
import { useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from "lucide-react"
import type {
  ExportCheckResult,
  ExportCheckIssue,
  LegalReference,
  Paragraph,
} from "@/types/document"
import { PARAGRAPH_TYPE_LABELS, REQUIRED_ELEMENTS_LABELS } from "@/types/document"
import { documentApi, DocumentApiError } from "@/lib/document-api"
import { cn } from "@/lib/utils"

// ---------- 工具 ----------

function isParagraphTypeMatch(p: Paragraph, type: 'fact' | 'basis' | 'claim'): boolean {
  return p.type === type
}

/** 判断三段是否齐全：通过 paragraph.type 字段或内容启发式判断 */
function detectSections(paragraphs: Paragraph[]): {
  hasFact: boolean
  hasBasis: boolean
  hasClaim: boolean
} {
  let hasFact = false
  let hasBasis = false
  let hasClaim = false
  for (const p of paragraphs) {
    if (p.type === 'fact') hasFact = true
    else if (p.type === 'basis') hasBasis = true
    else if (p.type === 'claim') hasClaim = true
    else {
      // 启发式：通过内容关键词判断
      const content = p.content || ''
      if (!hasFact && /事实|经过|起因|时间|地点/.test(content)) hasFact = true
      if (!hasBasis && /依据|根据|法条|法律|规定/.test(content)) hasBasis = true
      if (!hasClaim && /诉求|请求|要求|判令|赔偿/.test(content)) hasClaim = true
    }
  }
  return { hasFact, hasBasis, hasClaim }
}

// ---------- severity 配置 ----------

interface RiskConfig {
  label: string
  icon: typeof AlertTriangle
  iconClass: string
  textClass: string
  borderClass: string
  bgClass: string
}

const RISK_CONFIG: Record<'blocking' | 'warning' | 'info', RiskConfig> = {
  blocking: {
    label: '阻塞',
    icon: XCircle,
    iconClass: 'text-red-600',
    textClass: 'text-red-700',
    borderClass: 'border-red-200',
    bgClass: 'bg-red-50',
  },
  warning: {
    label: '警告',
    icon: AlertTriangle,
    iconClass: 'text-amber-600',
    textClass: 'text-amber-700',
    borderClass: 'border-amber-200',
    bgClass: 'bg-amber-50',
  },
  info: {
    label: '提示',
    icon: FileText,
    iconClass: 'text-slate-500',
    textClass: 'text-slate-700',
    borderClass: 'border-slate-200',
    bgClass: 'bg-slate-50',
  },
}

// ---------- 主组件 ----------

export interface DocumentSourcePanelProps {
  /** 运行 ID */
  runId: number
  /** 文书 ID */
  documentId: string
  /** 文书段落（用于提取证据/法条引用） */
  paragraphs: Paragraph[]
  /** 已加载的导出检查结果（外部传入时跳过内部刷新） */
  exportCheckResult?: ExportCheckResult | null
  /** 是否正在加载 export-check（外部受控时使用） */
  exportCheckLoading?: boolean
  /** 外部受控时调用此方法刷新 export-check */
  onRefreshExportCheck?: () => void
  /** 点击证据编号跳转 EvidenceSourceViewer */
  onJumpToEvidence?: (evidenceCode: string, paragraphId?: string) => void
  /** 点击法条查看原文 */
  onShowLegalReference?: (reference: LegalReference, paragraphId?: string) => void
  /** 点击导出按钮 */
  onExport?: () => void
  /** 是否正在导出 */
  isExporting?: boolean
  /** 紧凑模式（移动端使用） */
  compact?: boolean
}

export function DocumentSourcePanel({
  runId,
  documentId,
  paragraphs,
  exportCheckResult,
  exportCheckLoading,
  onRefreshExportCheck,
  onJumpToEvidence,
  onShowLegalReference,
  onExport,
  isExporting = false,
  compact = false,
}: DocumentSourcePanelProps) {
  const [internalResult, setInternalResult] = useState<ExportCheckResult | null>(null)
  const [internalLoading, setInternalLoading] = useState(false)
  const [internalError, setInternalError] = useState<string | null>(null)

  const isControlled = exportCheckResult !== undefined
  const result = isControlled ? exportCheckResult : internalResult
  const loading = isControlled ? Boolean(exportCheckLoading) : internalLoading

  // 内部加载 export-check
  async function loadExportCheck() {
    if (isControlled) {
      onRefreshExportCheck?.()
      return
    }
    if (internalLoading) return
    setInternalLoading(true)
    setInternalError(null)
    try {
      const data = await documentApi.exportCheck(runId, documentId)
      setInternalResult(data)
    } catch (e) {
      if (e instanceof DocumentApiError) {
        setInternalError(e.message)
      } else {
        setInternalError(e instanceof Error ? e.message : '导出检查失败')
      }
    } finally {
      setInternalLoading(false)
    }
  }

  // 首次挂载时调用 export-check（仅内部模式）
  useEffect(() => {
    if (!isControlled && runId && documentId) {
      loadExportCheck()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, documentId, isControlled])

  // 提取证据引用（按段分组，去重）
  const evidenceByParagraph = useMemo(() => {
    return paragraphs
      .filter((p) => p.evidence_codes && p.evidence_codes.length > 0)
      .map((p) => ({
        paragraph: p,
        codes: Array.from(new Set(p.evidence_codes)),
      }))
  }, [paragraphs])

  // 提取法条引用（按段分组）
  const legalRefsByParagraph = useMemo(() => {
    return paragraphs
      .filter((p) => p.legal_references && p.legal_references.length > 0)
      .map((p) => ({
        paragraph: p,
        references: p.legal_references,
      }))
  }, [paragraphs])

  // 完整性检查
  const sectionCheck = useMemo(() => detectSections(paragraphs), [paragraphs])

  // 风险提示：取 severity=blocking/warning 的项（同时优先 export-check issues）
  const riskIssues = useMemo<ExportCheckIssue[]>(() => {
    if (!result || !result.issues) return []
    return result.issues.filter((i) => i.severity === 'blocking' || i.severity === 'warning')
  }, [result])

  const passed = Boolean(result?.passed)
  const hasBlockingIssues = riskIssues.some((i) => i.severity === 'blocking')
  const missingElements = result?.missing_elements || []

  // 导出按钮 tooltip
  const exportBlockedReason = useMemo(() => {
    if (passed) return null
    const parts: string[] = []
    if (hasBlockingIssues) {
      const blockers = riskIssues.filter((i) => i.severity === 'blocking')
      parts.push(`存在 ${blockers.length} 项阻塞问题`)
    }
    if (missingElements.length > 0) {
      const labels = missingElements.map((k) => REQUIRED_ELEMENTS_LABELS[k] || k)
      parts.push(`缺少：${labels.join('、')}`)
    }
    return parts.length > 0 ? parts.join('；') : '导出检查未通过'
  }, [passed, hasBlockingIssues, riskIssues, missingElements])

  // 折叠状态
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({})
  function toggleSection(key: string) {
    setCollapsedSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const sectionWrap = (key: string, title: string, icon: React.ReactNode, children: React.ReactNode) => {
    const collapsed = collapsedSections[key]
    return (
      <section
        aria-labelledby={`section-${key}-title`}
        className="rounded-lg border border-[#EAEAEA] bg-white"
      >
        <button
          type="button"
          onClick={() => toggleSection(key)}
          aria-expanded={!collapsed}
          aria-controls={`section-${key}-content`}
          className="flex w-full items-center gap-2 px-3 py-2 text-left transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] rounded-t-lg"
        >
          {icon}
          <h3
            id={`section-${key}-title`}
            className="flex-1 text-xs font-semibold text-[#111111]"
          >
            {title}
          </h3>
          {collapsed ? (
            <ChevronRight className="h-3.5 w-3.5 text-[#787774]" aria-hidden="true" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-[#787774]" aria-hidden="true" />
          )}
        </button>
        {!collapsed && (
          <div
            id={`section-${key}-content`}
            className="border-t border-[#EAEAEA] px-3 py-2"
          >
            {children}
          </div>
        )}
      </section>
    )
  }

  return (
    <div className={cn("flex h-full flex-col bg-[#F7F6F3]", compact && "px-2")}>
      {/* 顶部标题 */}
      <header className="flex items-center justify-between border-b border-[#EAEAEA] px-4 py-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-[#3f6b57]" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-[#111111]">依据与质量</h2>
        </div>
        <button
          type="button"
          onClick={loadExportCheck}
          disabled={loading}
          aria-label="刷新导出检查"
          className="inline-flex min-h-[36px] min-w-[36px] items-center justify-center rounded-lg border border-[#EAEAEA] bg-white text-[#565652] transition hover:bg-[#F7F6F3] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} aria-hidden="true" />
        </button>
      </header>

      {/* 滚动内容 */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {/* 完整性检查 */}
        {sectionWrap(
          'integrity',
          '完整性检查',
          <CheckCircle2 className="h-3.5 w-3.5 text-[#3f6b57]" aria-hidden="true" />,
          <div className="space-y-1.5">
            <IntegrityRow label="事实段" ok={sectionCheck.hasFact} />
            <IntegrityRow label="依据段" ok={sectionCheck.hasBasis} />
            <IntegrityRow label="诉求段" ok={sectionCheck.hasClaim} />
            {missingElements.length > 0 && (
              <p className="mt-1 text-[11px] text-red-700">
                缺少必备要素：
                {missingElements.map((k) => REQUIRED_ELEMENTS_LABELS[k] || k).join('、')}
              </p>
            )}
            <p className="mt-1 text-[10px] text-[#787774]">
              实际检查以「导出检查」结果为准，此处为段落类型启发式判断。
            </p>
          </div>,
        )}

        {/* 引用证据 */}
        {sectionWrap(
          'evidence',
          `引用证据 (${evidenceByParagraph.reduce((acc, g) => acc + g.codes.length, 0)})`,
          <ExternalLink className="h-3.5 w-3.5 text-sky-600" aria-hidden="true" />,
          evidenceByParagraph.length === 0 ? (
            <p className="py-2 text-center text-[11px] text-[#787774]">暂无证据引用</p>
          ) : (
            <ul className="space-y-2">
              {evidenceByParagraph.map((group) => (
                <li key={group.paragraph.id}>
                  <p className="text-[10px] text-[#787774]">
                    段落 #{group.paragraph.id}
                    {group.paragraph.type && (
                      <span className="ml-1">
                        （{PARAGRAPH_TYPE_LABELS[group.paragraph.type]}）
                      </span>
                    )}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {group.codes.map((code) => (
                      <button
                        key={code}
                        type="button"
                        onClick={() => onJumpToEvidence?.(code, group.paragraph.id)}
                        className="inline-flex min-h-[28px] items-center gap-1 rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-700 transition hover:bg-sky-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
                        aria-label={`跳转到证据 ${code}`}
                      >
                        <ExternalLink className="h-2.5 w-2.5" aria-hidden="true" />
                        {code}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ),
        )}

        {/* 引用法条 */}
        {sectionWrap(
          'legal',
          `引用法条 (${legalRefsByParagraph.reduce((acc, g) => acc + g.references.length, 0)})`,
          <BookOpen className="h-3.5 w-3.5 text-emerald-700" aria-hidden="true" />,
          legalRefsByParagraph.length === 0 ? (
            <p className="py-2 text-center text-[11px] text-[#787774]">暂无法条引用</p>
          ) : (
            <ul className="space-y-2">
              {legalRefsByParagraph.map((group) => (
                <li key={group.paragraph.id}>
                  <p className="text-[10px] text-[#787774]">段落 #{group.paragraph.id}</p>
                  <ul className="mt-1 space-y-1">
                    {group.references.map((ref, idx) => (
                      <li key={`${group.paragraph.id}-${idx}`}>
                        <button
                          type="button"
                          onClick={() => onShowLegalReference?.(ref, group.paragraph.id)}
                          className="inline-flex min-h-[28px] w-full items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-left text-[11px] text-emerald-800 transition hover:bg-emerald-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
                          aria-label={`查看法条 ${ref.law_name} ${ref.article_number} 原文`}
                        >
                          <BookOpen className="h-2.5 w-2.5 flex-shrink-0" aria-hidden="true" />
                          <span className="flex-1 truncate">
                            <span className="font-medium">{ref.law_name}</span>
                            <span className="ml-1">{ref.article_number}</span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          ),
        )}

        {/* 风险提示 */}
        {sectionWrap(
          'risk',
          `风险提示 (${riskIssues.length})`,
          <AlertTriangle className="h-3.5 w-3.5 text-amber-600" aria-hidden="true" />,
          <>
            {loading && (
              <div className="flex items-center justify-center gap-2 py-3 text-[11px] text-[#787774]">
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                正在检查...
              </div>
            )}
            {!loading && internalError && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded border border-red-200 bg-red-50 px-2 py-1.5 text-[11px] text-red-700"
              >
                <AlertTriangle className="mt-0.5 h-3 w-3 flex-shrink-0" aria-hidden="true" />
                <span className="break-words">{internalError}</span>
              </div>
            )}
            {!loading && !internalError && riskIssues.length === 0 && (
              <p className="py-2 text-center text-[11px] text-emerald-700">
                暂无风险提示，可放心导出
              </p>
            )}
            {!loading && !internalError && riskIssues.length > 0 && (
              <ul className="space-y-1.5">
                {riskIssues.map((issue, idx) => {
                  const cfg = RISK_CONFIG[issue.severity] || RISK_CONFIG.info
                  const RiskIcon = cfg.icon
                  return (
                    <li
                      key={`${issue.code}-${idx}`}
                      className={cn(
                        "flex items-start gap-2 rounded-md border px-2 py-1.5",
                        cfg.borderClass,
                        cfg.bgClass,
                      )}
                    >
                      <RiskIcon
                        className={cn("mt-0.5 h-3 w-3 flex-shrink-0", cfg.iconClass)}
                        aria-hidden="true"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-1">
                          <span className={cn("font-mono text-[10px] uppercase", cfg.textClass)}>
                            {issue.code}
                          </span>
                          <span
                            className={cn(
                              "rounded-full border px-1 py-0 text-[9px] font-medium",
                              cfg.borderClass,
                              cfg.textClass,
                            )}
                          >
                            {cfg.label}
                          </span>
                          {issue.paragraph_id && (
                            <span className="text-[9px] text-[#787774]">
                              @ 段 #{issue.paragraph_id}
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 text-[11px] text-[#111111] break-words">
                          {issue.message}
                        </p>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </>,
        )}
      </div>

      {/* 底部：导出按钮 */}
      <footer className="border-t border-[#EAEAEA] bg-white px-4 py-3">
        {passed ? (
          <button
            type="button"
            onClick={onExport}
            disabled={isExporting}
            className="inline-flex min-h-[44px] w-full items-center justify-center gap-1.5 rounded-lg bg-[#3f6b57] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#2f5947] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isExporting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                正在导出...
              </>
            ) : (
              <>
                <Download className="h-4 w-4" aria-hidden="true" />
                导出文书
              </>
            )}
          </button>
        ) : (
          <div className="group relative">
            <button
              type="button"
              disabled
              aria-label={`导出被阻塞：${exportBlockedReason || ''}`}
              className="inline-flex min-h-[44px] w-full cursor-not-allowed items-center justify-center gap-1.5 rounded-lg border border-[#EAEAEA] bg-[#F7F6F3] px-4 py-2 text-sm font-medium text-[#787774]"
            >
              <ShieldAlert className="h-4 w-4" aria-hidden="true" />
              导出被阻塞
            </button>
            {exportBlockedReason && (
              <div
                role="tooltip"
                className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 rounded-md bg-[#111111] px-2.5 py-1.5 text-[11px] text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
              >
                {exportBlockedReason}
              </div>
            )}
          </div>
        )}
      </footer>
    </div>
  )
}

// ---------- 完整性行 ----------

function IntegrityRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {ok ? (
        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
      ) : (
        <XCircle className="h-3.5 w-3.5 text-red-500" aria-hidden="true" />
      )}
      <span className={ok ? "text-[#111111]" : "text-red-700"}>
        {label}
      </span>
      <span className="ml-auto text-[10px] text-[#787774]">
        {ok ? "已包含" : "未检测到"}
      </span>
    </div>
  )
}

export default DocumentSourcePanel
