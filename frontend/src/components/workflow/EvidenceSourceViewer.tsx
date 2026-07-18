// 证据来源查看器：支持图片证据 + 文本证据
// 对齐 spec 第 6.9 节 / Task 2.6.1
// 图片：原图 + 缩放旋转 + OCR 区域框选 + 点击字段跳转 + 物证视觉摘要
// 文本：OCR 原文 + 纠错后文本 + 差异对照（高亮）
import { useEffect, useMemo, useRef, useState } from "react"
import type { RefObject } from "react"
import {
  X,
  ZoomIn,
  ZoomOut,
  RotateCw,
  RotateCcw,
  ImageOff,
  FileText,
  Crosshair,
} from "lucide-react"

// ---------- 类型 ----------

export interface OcrRegion {
  x: number
  y: number
  width: number
  height: number
  fieldName?: string
  text?: string
}

export interface ExtractedFieldRef {
  field_name: string
  field_value: string
  source_region?: { x: number; y: number; width: number; height: number }
}

export interface EvidenceSourceViewerProps {
  evidenceId: number
  evidenceType: "image" | "text"
  imagePath?: string
  ocrRawText?: string
  ocrCorrectedText?: string
  ocrRegions?: OcrRegion[]
  extractedFields?: ExtractedFieldRef[]
  onClose?: () => void
}

// ---------- 坐标归一化 ----------
// 支持 0-1 归一化坐标 + 0-100 百分比坐标，统一转换为 0-100

function normalizeCoord(value: number): number {
  if (value <= 1) return value * 100
  if (value <= 100) return value
  // > 100 视为像素坐标，无法归一化（缺图片尺寸），退化为 0
  return 0
}

// ---------- 文本差异（LCS 行级 diff） ----------

interface DiffLine {
  type: "common" | "removed" | "added"
  text: string
}

function diffLines(oldText: string, newText: string): DiffLine[] {
  const oldLines = oldText.split("\n")
  const newLines = newText.split("\n")
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
      result.push({ type: "common", text: oldLines[i] })
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      result.push({ type: "removed", text: oldLines[i] })
      i++
    } else {
      result.push({ type: "added", text: newLines[j] })
      j++
    }
  }
  while (i < m) {
    result.push({ type: "removed", text: oldLines[i] })
    i++
  }
  while (j < n) {
    result.push({ type: "added", text: newLines[j] })
    j++
  }
  return result
}

// ---------- 主组件 ----------

export function EvidenceSourceViewer({
  evidenceId,
  evidenceType,
  imagePath,
  ocrRawText = "",
  ocrCorrectedText = "",
  ocrRegions = [],
  extractedFields = [],
  onClose,
}: EvidenceSourceViewerProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const imageContainerRef = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(1)
  const [rotation, setRotation] = useState(0)
  const [highlightedIndex, setHighlightedIndex] = useState<number | null>(null)

  const titleId = "evidence-source-viewer-title"

  // Escape 关闭
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        e.stopPropagation()
        onClose?.()
      }
    }
    document.addEventListener("keydown", handleKeyDown, true)
    return () => document.removeEventListener("keydown", handleKeyDown, true)
  }, [onClose])

  // 点击字段高亮对应区域 + 滚动到该区域
  function handleFieldClick(field: ExtractedFieldRef, index: number) {
    // 在 ocrRegions 中查找匹配的字段
    const regionIdx = ocrRegions.findIndex(
      (r) => r.fieldName === field.field_name || r.text?.includes(field.field_value),
    )
    setHighlightedIndex(regionIdx >= 0 ? regionIdx : index)
    // 滚动到图片容器
    imageContainerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
  }

  function handleZoomIn() {
    setZoom((z) => Math.min(3, z + 0.25))
  }
  function handleZoomOut() {
    setZoom((z) => Math.max(0.5, z - 0.25))
  }
  function handleRotateCW() {
    setRotation((r) => (r + 90) % 360)
  }
  function handleRotateCCW() {
    setRotation((r) => (r - 90 + 360) % 360)
  }

  const diffResult = useMemo(() => {
    if (evidenceType !== "text") return []
    if (!ocrRawText && !ocrCorrectedText) return []
    return diffLines(ocrRawText, ocrCorrectedText)
  }, [evidenceType, ocrRawText, ocrCorrectedText])

  const hasExtractedFields = extractedFields.length > 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 md:items-center md:p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl md:max-w-4xl md:rounded-2xl"
      >
        {/* 顶部标题栏 */}
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-3">
          <div className="flex items-center gap-2 min-w-0">
            {evidenceType === "image" ? (
              <FileText className="h-4 w-4 flex-shrink-0 text-slate-500" aria-hidden="true" />
            ) : (
              <FileText className="h-4 w-4 flex-shrink-0 text-slate-500" aria-hidden="true" />
            )}
            <h2 id={titleId} className="truncate text-sm font-semibold text-slate-900">
              证据 #{evidenceId} 来源查看
              <span className="ml-2 text-[11px] font-normal text-slate-500">
                {evidenceType === "image" ? "图片证据" : "文本证据"}
              </span>
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭证据查看器"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        {/* 主体内容 */}
        <div className="flex-1 overflow-y-auto">
          {evidenceType === "image" ? (
            <ImageEvidenceView
              imagePath={imagePath}
              ocrRegions={ocrRegions}
              highlightedIndex={highlightedIndex}
              zoom={zoom}
              rotation={rotation}
              onZoomIn={handleZoomIn}
              onZoomOut={handleZoomOut}
              onRotateCW={handleRotateCW}
              onRotateCCW={handleRotateCCW}
              imageContainerRef={imageContainerRef}
              onRegionFocus={(idx) => setHighlightedIndex(idx)}
            />
          ) : (
            <TextEvidenceView
              ocrRawText={ocrRawText}
              ocrCorrectedText={ocrCorrectedText}
              diffLines={diffResult}
            />
          )}
        </div>

        {/* 底部：抽取字段列表（点击跳转来源区域） */}
        {hasExtractedFields && (
          <footer className="border-t border-slate-200 bg-slate-50 px-5 py-3">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              抽取字段（点击高亮来源区域）
            </p>
            <div className="flex flex-wrap gap-2">
              {extractedFields.map((field, idx) => (
                <button
                  key={`${field.field_name}-${idx}`}
                  type="button"
                  onClick={() => handleFieldClick(field, idx)}
                  className="inline-flex min-h-[36px] items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs text-slate-700 transition hover:border-sky-300 hover:bg-sky-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300"
                  aria-label={`高亮字段 ${field.field_name} 的来源区域`}
                >
                  <Crosshair className="h-3 w-3 text-sky-600" aria-hidden="true" />
                  <span className="font-medium">{field.field_name}</span>
                  <span className="max-w-[160px] truncate font-mono text-[10px] text-slate-500">
                    {field.field_value}
                  </span>
                </button>
              ))}
            </div>
          </footer>
        )}
      </div>
    </div>
  )
}

// ---------- 图片证据子组件 ----------

interface ImageEvidenceViewProps {
  imagePath?: string
  ocrRegions: OcrRegion[]
  highlightedIndex: number | null
  zoom: number
  rotation: number
  onZoomIn: () => void
  onZoomOut: () => void
  onRotateCW: () => void
  onRotateCCW: () => void
  imageContainerRef: RefObject<HTMLDivElement | null>
  /** 点击 OCR 文本区域时触发，父组件提升 highlightedIndex 状态 */
  onRegionFocus?: (index: number) => void
}

function ImageEvidenceView({
  imagePath,
  ocrRegions,
  highlightedIndex,
  zoom,
  rotation,
  onZoomIn,
  onZoomOut,
  onRotateCW,
  onRotateCCW,
  imageContainerRef,
  onRegionFocus,
}: ImageEvidenceViewProps) {
  const hasOcrRegions = ocrRegions.length > 0

  return (
    <div className="flex flex-col">
      {/* 工具栏 */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2">
        <span className="text-[11px] text-slate-500" aria-live="polite">
          缩放 {Math.round(zoom * 100)}% · 旋转 {rotation}°
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={onZoomOut}
            disabled={zoom <= 0.5}
            aria-label="缩小"
            className="inline-flex min-h-[36px] min-w-[36px] items-center justify-center rounded-md border border-slate-300 bg-white text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ZoomOut className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onZoomIn}
            disabled={zoom >= 3}
            aria-label="放大"
            className="inline-flex min-h-[36px] min-w-[36px] items-center justify-center rounded-md border border-slate-300 bg-white text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ZoomIn className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <div className="mx-1 h-4 w-px bg-slate-200" aria-hidden="true" />
          <button
            type="button"
            onClick={onRotateCCW}
            aria-label="逆时针旋转 90 度"
            className="inline-flex min-h-[36px] min-w-[36px] items-center justify-center rounded-md border border-slate-300 bg-white text-slate-600 transition hover:bg-slate-100"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onRotateCW}
            aria-label="顺时针旋转 90 度"
            className="inline-flex min-h-[36px] min-w-[36px] items-center justify-center rounded-md border border-slate-300 bg-white text-slate-600 transition hover:bg-slate-100"
          >
            <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* 图片 + SVG overlay */}
      <div
        ref={imageContainerRef}
        className="flex items-center justify-center overflow-auto bg-slate-100 p-4"
        style={{ maxHeight: "60vh" }}
      >
        {imagePath ? (
          <div
            className="relative inline-block"
            style={{
              transform: `scale(${zoom}) rotate(${rotation}deg)`,
              transformOrigin: "center center",
              transition: "transform 0.2s ease-out",
            }}
          >
            <img
              src={imagePath}
              alt={`证据图片 ${imagePath}`}
              className="block max-w-full select-none"
              draggable={false}
              style={{ maxHeight: "55vh" }}
            />
            {/* SVG overlay：viewBox 0-100，preserveAspectRatio none 使其跟随图片拉伸 */}
            {hasOcrRegions && (
              <svg
                className="pointer-events-none absolute inset-0 h-full w-full"
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                {ocrRegions.map((region, idx) => {
                  const x = normalizeCoord(region.x)
                  const y = normalizeCoord(region.y)
                  const w = normalizeCoord(region.width)
                  const h = normalizeCoord(region.height)
                  const isHighlighted = highlightedIndex === idx
                  return (
                    <g key={`region-${idx}`}>
                      <rect
                        x={x}
                        y={y}
                        width={w}
                        height={h}
                        fill={isHighlighted ? "rgba(56, 189, 248, 0.25)" : "rgba(245, 158, 11, 0.12)"}
                        stroke={isHighlighted ? "#0284c7" : "#d97706"}
                        strokeWidth={isHighlighted ? 0.8 : 0.4}
                        vectorEffect="non-scaling-stroke"
                      />
                      {region.fieldName && (
                        <text
                          x={x + 0.5}
                          y={y + 2}
                          fill={isHighlighted ? "#0284c7" : "#92400e"}
                          fontSize="1.5"
                          fontWeight="600"
                          fontFamily="monospace"
                        >
                          {region.fieldName}
                        </text>
                      )}
                    </g>
                  )
                })}
              </svg>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-12 text-slate-400">
            <ImageOff className="h-8 w-8" aria-hidden="true" />
            <p className="text-sm">图片不可用</p>
          </div>
        )}
      </div>

      {/* 物证视觉摘要（无 OCR 区域时显示） */}
      {!hasOcrRegions && (
        <div className="border-t border-slate-100 px-4 py-3">
          <p className="text-xs text-slate-600">
            此图片未提供 OCR 文本区域信息。{imagePath ? "可作为物证视觉摘要参考。" : ""}
          </p>
        </div>
      )}

      {/* OCR 区域文本列表 */}
      {hasOcrRegions && (
        <div className="border-t border-slate-100 px-4 py-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            OCR 文本区域
          </p>
          <ul className="space-y-1">
            {ocrRegions.map((region, idx) => (
              <li
                key={`ocr-text-${idx}`}
                className={`flex items-start gap-2 rounded px-2 py-1 text-xs transition ${
                  highlightedIndex === idx ? "bg-sky-50" : ""
                }`}
              >
                <button
                  type="button"
                  onClick={() => onRegionFocus?.(idx)}
                  className="font-mono text-[10px] text-sky-700 hover:underline"
                  aria-label={`高亮区域 ${region.fieldName || idx + 1}`}
                >
                  {region.fieldName || `区域 ${idx + 1}`}
                </button>
                <span className="flex-1 text-slate-700 break-words">
                  {region.text || "（无文本）"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ---------- 文本证据子组件 ----------

interface TextEvidenceViewProps {
  ocrRawText: string
  ocrCorrectedText: string
  diffLines: DiffLine[]
}

function TextEvidenceView({ ocrRawText, ocrCorrectedText, diffLines }: TextEvidenceViewProps) {
  const hasDiff = diffLines.length > 0
  const hasRaw = ocrRawText.trim() !== ""
  const hasCorrected = ocrCorrectedText.trim() !== ""

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* 双栏原文 + 纠错后 */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <section
          aria-labelledby="ocr-raw-title"
          className="rounded-lg border border-slate-200 bg-slate-50"
        >
          <header className="border-b border-slate-200 px-3 py-2">
            <h3 id="ocr-raw-title" className="text-xs font-semibold text-slate-700">
              OCR 原文
            </h3>
          </header>
          <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap px-3 py-2 text-xs text-slate-700">
            {hasRaw ? ocrRawText : "（无原文）"}
          </pre>
        </section>
        <section
          aria-labelledby="ocr-corrected-title"
          className="rounded-lg border border-emerald-200 bg-emerald-50"
        >
          <header className="border-b border-emerald-200 px-3 py-2">
            <h3 id="ocr-corrected-title" className="text-xs font-semibold text-emerald-700">
              纠错后文本
            </h3>
          </header>
          <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap px-3 py-2 text-xs text-slate-800">
            {hasCorrected ? ocrCorrectedText : "（无纠错文本）"}
          </pre>
        </section>
      </div>

      {/* 差异对照 */}
      <section
        aria-labelledby="ocr-diff-title"
        className="rounded-lg border border-slate-200"
      >
        <header className="border-b border-slate-200 px-3 py-2">
          <h3 id="ocr-diff-title" className="text-xs font-semibold text-slate-700">
            差异对照
          </h3>
        </header>
        <div className="max-h-60 overflow-y-auto">
          {!hasDiff ? (
            <p className="px-3 py-4 text-center text-xs text-slate-500">无差异内容</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {diffLines.map((line, idx) => {
                const bgClass =
                  line.type === "removed"
                    ? "bg-red-50"
                    : line.type === "added"
                      ? "bg-emerald-50"
                      : ""
                const textClass =
                  line.type === "removed"
                    ? "text-red-800"
                    : line.type === "added"
                      ? "text-emerald-800"
                      : "text-slate-700"
                const prefix =
                  line.type === "removed" ? "- " : line.type === "added" ? "+ " : "  "
                const prefixClass =
                  line.type === "removed"
                    ? "text-red-500"
                    : line.type === "added"
                      ? "text-emerald-600"
                      : "text-slate-400"
                return (
                  <li
                    key={`diff-${idx}`}
                    className={`flex items-start gap-1 px-3 py-1 text-xs ${bgClass}`}
                  >
                    <span className={`font-mono ${prefixClass}`} aria-hidden="true">
                      {prefix}
                    </span>
                    <span className={`flex-1 whitespace-pre-wrap break-words ${textClass}`}>
                      {line.text || " "}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
        <p className="border-t border-slate-100 px-3 py-1.5 text-[10px] text-slate-500">
          <span className="text-red-600">- </span>仅原文 ／
          <span className="ml-2 text-emerald-600">+ </span>仅纠错后
        </p>
      </section>
    </div>
  )
}

export default EvidenceSourceViewer
