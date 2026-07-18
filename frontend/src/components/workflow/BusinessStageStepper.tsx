// 业务阶段横向轨道：4 阶段聚合展示，替代旧版 NodeTrack
// 参考 spec 第 6.5 节 / Task 1.7
import { useEffect, useRef, useState } from "react"
import {
  CheckCircle,
  ChevronUp,
  Circle,
  AlertCircle,
  Loader2,
  MinusCircle,
  X,
} from "lucide-react"
import type { ReactNode } from "react"
import type { BusinessStageKey, WorkflowStage } from "@/types/workflow"

// ---------- 阶段元数据 ----------

const STAGE_ORDER: BusinessStageKey[] = [
  "material_understanding",
  "fact_checking",
  "case_organization",
  "document_generation",
]

const STAGE_LABELS: Record<BusinessStageKey, string> = {
  material_understanding: "材料理解",
  fact_checking: "事实核对",
  case_organization: "案件组织",
  document_generation: "文书生成",
}

const STAGE_NODES: Record<BusinessStageKey, string[]> = {
  material_understanding: ["preclassify", "ocr", "classify"],
  fact_checking: ["extract", "review"],
  case_organization: ["evidence_chain"],
  document_generation: ["complaint", "respond_complaint"],
}

type StageStatus = WorkflowStage["status"]

interface StatusConfig {
  icon: typeof CheckCircle
  textClass: string
  bgClass: string
  borderClass: string
  barClass: string
  label: string
}

const STATUS_CONFIG: Record<StageStatus, StatusConfig> = {
  pending: {
    icon: Circle,
    textClass: "text-slate-400",
    bgClass: "bg-slate-50",
    borderClass: "border-slate-200",
    barClass: "bg-slate-300",
    label: "未开始",
  },
  running: {
    icon: Loader2,
    textClass: "text-sky-600",
    bgClass: "bg-sky-50",
    borderClass: "border-sky-300",
    barClass: "bg-sky-500",
    label: "进行中",
  },
  completed: {
    icon: CheckCircle,
    textClass: "text-emerald-600",
    bgClass: "bg-emerald-50",
    borderClass: "border-emerald-200",
    barClass: "bg-emerald-500",
    label: "已完成",
  },
  failed: {
    icon: AlertCircle,
    textClass: "text-red-600",
    bgClass: "bg-red-50",
    borderClass: "border-red-200",
    barClass: "bg-red-500",
    label: "失败",
  },
  skipped: {
    icon: MinusCircle,
    textClass: "text-slate-400",
    bgClass: "bg-slate-50",
    borderClass: "border-slate-200",
    barClass: "bg-slate-300",
    label: "已跳过",
  },
}

function formatQuality(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return "--"
  const clamped = Math.max(0, Math.min(1, score))
  return `${Math.round(clamped * 100)}%`
}

function formatProgress(progress: number): number {
  const clamped = Math.max(0, Math.min(1, progress || 0))
  return Math.round(clamped * 100)
}

// ---------- 单阶段卡片 ----------

interface StageCardProps {
  stage: WorkflowStage
  isCurrent: boolean
  onClick?: () => void
}

function StageCard({ stage, isCurrent, onClick }: StageCardProps) {
  const config = STATUS_CONFIG[stage.status]
  const Icon = config.icon
  const isRunning = stage.status === "running"
  const qualityText = formatQuality(stage.quality_score)
  const progressPct = formatProgress(stage.progress)

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={isCurrent ? "step" : undefined}
      aria-label={`${STAGE_LABELS[stage.key]} 阶段，状态：${config.label}，质量分：${qualityText}，问题：${stage.issue_count} 个，进度：${progressPct}%`}
      className={`group flex w-full flex-col rounded-xl border px-3 py-3 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${config.borderClass} ${
        isCurrent ? `${config.bgClass} ring-1 ring-sky-400 shadow-sm` : "bg-white hover:bg-slate-50"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-[#565652]">
          {STAGE_LABELS[stage.key]}
        </span>
        <Icon
          className={`h-4 w-4 ${config.textClass} ${isRunning ? "animate-spin" : ""}`}
          aria-hidden="true"
        />
      </div>
      <div className="mt-2 flex items-baseline justify-between gap-2 text-[11px] text-[#787774]">
        <span>
          质量{" "}
          <span className={`font-medium ${stage.quality_score != null ? "text-[#111111]" : ""}`}>
            {qualityText}
          </span>
        </span>
        <span>
          问题{" "}
          <span
            className={`font-medium ${stage.issue_count > 0 ? "text-amber-700" : "text-[#111111]"}`}
          >
            {stage.issue_count}
          </span>
        </span>
      </div>
      <div
        className="mt-2 h-1 w-full overflow-hidden rounded-full bg-slate-200"
        role="progressbar"
        aria-valuenow={progressPct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${STAGE_LABELS[stage.key]} 进度`}
      >
        <div
          className={`h-full rounded-full transition-all ${config.barClass}`}
          style={{ width: `${progressPct}%` }}
        />
      </div>
      <div className="mt-2 text-[10px] text-[#787774]">
        {config.label} · {progressPct}%
      </div>
    </button>
  )
}

// ---------- 移动端底部抽屉 ----------

interface BottomDrawerProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

function BottomDrawer({ open, onClose, title, children }: BottomDrawerProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeBtnRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener("keydown", onKey)
    // 进入时聚焦关闭按钮，便于键盘关闭
    const timer = window.setTimeout(() => closeBtnRef.current?.focus(), 50)
    return () => {
      document.removeEventListener("keydown", onKey)
      window.clearTimeout(timer)
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label={title}>
      <button
        type="button"
        onClick={onClose}
        aria-label="关闭阶段列表"
        className="absolute inset-0 bg-black/40"
      />
      <div
        ref={dialogRef}
        className="absolute bottom-0 left-0 right-0 max-h-[80vh] overflow-y-auto rounded-t-2xl bg-white p-4 shadow-2xl motion-safe:animate-[drawer-slide-in_0.25s_ease-out]"
      >
        <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-slate-300" aria-hidden="true" />
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[#111111]">{title}</h3>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[#787774] hover:bg-slate-100"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ---------- 主组件 ----------

export interface BusinessStageStepperProps {
  stages: WorkflowStage[]
  currentStage: string
  onStageClick?: (stageKey: BusinessStageKey) => void
}

export function BusinessStageStepper({
  stages,
  currentStage,
  onStageClick,
}: BusinessStageStepperProps) {
  const [drawerOpen, setDrawerOpen] = useState(false)

  // 按固定顺序对齐 stages，缺失则补 pending 占位
  const orderedStages: WorkflowStage[] = STAGE_ORDER.map((key) => {
    const found = stages.find((s) => s.key === key)
    if (found) return found
    return {
      key,
      name: STAGE_LABELS[key],
      status: "pending" as const,
      quality_score: null,
      issue_count: 0,
      progress: 0,
      nodes: STAGE_NODES[key],
    }
  })

  // 当前阶段对象：优先 currentStage，其次 running，最后首段
  const currentStageObj =
    orderedStages.find((s) => s.key === currentStage) ||
    orderedStages.find((s) => s.status === "running") ||
    orderedStages[0]

  function handleStageClick(stage: WorkflowStage) {
    onStageClick?.(stage.key)
  }

  function handleDrawerStageClick(stage: WorkflowStage) {
    onStageClick?.(stage.key)
    setDrawerOpen(false)
  }

  return (
    <>
      {/* 桌面端：横向 4 段轨道 */}
      <div className="hidden md:block">
        <ol className="grid grid-cols-4 gap-3">
          {orderedStages.map((stage) => (
            <li key={stage.key}>
              <StageCard
                stage={stage}
                isCurrent={stage.key === currentStage}
                onClick={() => handleStageClick(stage)}
              />
            </li>
          ))}
        </ol>
      </div>

      {/* 移动端：仅当前阶段卡片 + 查看全部按钮 */}
      <div className="md:hidden">
        <StageCard
          stage={currentStageObj}
          isCurrent
          onClick={() => handleStageClick(currentStageObj)}
        />
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          aria-label="查看全部阶段"
          className="mt-2 inline-flex min-h-[44px] w-full items-center justify-center gap-1.5 rounded-lg border border-[#EAEAEA] bg-white px-3 py-1.5 text-xs font-medium text-[#565652] hover:bg-[#F7F6F3]"
        >
          查看全部阶段（{STAGE_ORDER.length}）
          <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>

      <BottomDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="全部业务阶段"
      >
        <ol className="grid grid-cols-1 gap-3">
          {orderedStages.map((stage) => (
            <li key={stage.key}>
              <StageCard
                stage={stage}
                isCurrent={stage.key === currentStage}
                onClick={() => handleDrawerStageClick(stage)}
              />
            </li>
          ))}
        </ol>
      </BottomDrawer>
    </>
  )
}

export default BusinessStageStepper
