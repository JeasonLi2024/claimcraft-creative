/**
 * @deprecated 使用 InterventionPanel 代替。本组件保留用于渐进迁移。
 *
 * HITL 校正 UI：人工审核中断时展示可编辑字段列表
 * 参考 spec 第 6.10 节
 */
import { useState } from "react"
import { AlertTriangle } from "lucide-react"
import { useCaseStore } from "@/stores/case-store"
import type { ReviewInterruptData, Correction } from "@/lib/workflow-events"

export function ReviewInterruptPanel({
  data,
  caseId,
}: {
  data: ReviewInterruptData
  caseId: number
}) {
  const submitReviewCorrections = useCaseStore((s) => s.submitReviewCorrections)
  const error = useCaseStore((s) => s.error)
  const [corrections, setCorrections] = useState<Correction[]>(
    (data.fields_to_review || []).map((f) => ({
      evidence_id: f.evidence_id,
      field_name: f.field_name,
      corrected_value: f.current_value,
    })),
  )
  const [submitting, setSubmitting] = useState(false)

  function updateCorrection(index: number, value: string) {
    setCorrections((prev) =>
      prev.map((c, i) => (i === index ? { ...c, corrected_value: value } : c)),
    )
  }

  async function handleSubmit() {
    setSubmitting(true)
    try {
      await submitReviewCorrections(caseId, corrections)
    } catch {
      // 错误已写入 store.error
    } finally {
      setSubmitting(false)
    }
  }

  // 表单错误关联：错误提示元素 id + 输入框 aria-describedby
  const errorId = "review-interrupt-error"
  const hasError = Boolean(error)

  return (
    <div className="border-2 border-amber-400 bg-[#FBF3DB] rounded-md p-4">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-5 h-5 text-amber-600" aria-hidden="true" />
        <h3 className="font-semibold text-amber-900">需要人工校正</h3>
      </div>
      {data.message && (
        <p className="text-sm text-amber-800 mb-3">{data.message}</p>
      )}

      <div className="space-y-2">
        {(data.fields_to_review || []).map((field, i) => (
          <div
            key={i}
            className="flex items-center gap-2 bg-white border border-[#EAEAEA] px-2 py-1.5 rounded"
          >
            <span className="text-xs text-[#787774] w-20 font-mono">
              EV#{field.evidence_id}
            </span>
            <span className="text-xs text-[#111111] w-32">{field.field_name}</span>
            <span className="text-xs text-red-500 w-20">
              置信度 {(field.confidence * 100).toFixed(0)}%
            </span>
            <input
              value={corrections[i]?.corrected_value ?? ""}
              onChange={(e) => updateCorrection(i, e.target.value)}
              aria-invalid={hasError}
              aria-describedby={hasError ? errorId : undefined}
              className="flex-1 text-sm border border-[#EAEAEA] rounded px-2 py-1 focus:outline-none focus:border-amber-400"
            />
          </div>
        ))}
      </div>

      {error && (
        <p id={errorId} role="alert" className="mt-2 text-sm text-red-600">{error}</p>
      )}

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="mt-3 inline-flex min-h-[44px] items-center justify-center rounded bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? "提交中..." : "提交校正并继续"}
      </button>
    </div>
  )
}
