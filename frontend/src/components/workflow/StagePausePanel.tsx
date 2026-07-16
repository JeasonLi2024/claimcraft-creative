import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, Loader2, Play, Square } from "lucide-react"
import { NODE_LABELS, type StageEdits, type StageProducts } from "@/lib/workflow-events"
import { useCaseStore } from "@/stores/case-store"

const LIMITS: Record<string, number> = {
  evidence_category: 50,
  ocr_summary: 2000,
  extracted_text: 20000,
  field_name: 50,
  field_value: 500,
  event: 4000,
  title: 200,
  content: 20000,
  tone: 20,
}

const FIELD_LABELS: Record<string, string> = {
  evidence_category: "证据分类",
  ocr_summary: "OCR 摘要",
  extracted_text: "识别文本",
  field_name: "字段名",
  field_value: "字段值",
  event: "事件描述",
  title: "文书标题",
  content: "文书正文",
  tone: "文书语气",
}

function textInputClass(multiline = false) {
  return `w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-amber-400 focus:ring-2 focus:ring-amber-100 ${multiline ? "min-h-28 resize-y leading-6" : ""}`
}

export function StagePausePanel({ caseId }: { caseId: number }) {
  const pauseData = useCaseStore((s) => s.pauseData)
  const fetchWorkflowState = useCaseStore((s) => s.fetchWorkflowState)
  const resumePausedWorkflow = useCaseStore((s) => s.resumePausedWorkflow)
  const cancelWorkflow = useCaseStore((s) => s.cancelWorkflow)
  const storeError = useCaseStore((s) => s.error)
  const [products, setProducts] = useState<StageProducts>(pauseData?.stage_products || {})
  const [loading, setLoading] = useState(!pauseData?.stage_products)
  const [submitting, setSubmitting] = useState<"resume" | "cancel" | null>(null)
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    if (!pauseData) return
    if (pauseData.stage_products) {
      setProducts(pauseData.stage_products)
      setLoading(false)
      return
    }
    let active = true
    setLoading(true)
    void fetchWorkflowState(caseId)
      .then((data) => {
        if (active) setProducts(data.stage_products)
      })
      .catch((error) => {
        if (active) setLocalError(error.response?.data?.detail || error.message || "加载阶段产物失败")
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [caseId, fetchWorkflowState, pauseData])

  const scope = pauseData?.editable_scope || {}
  const hasEditableFields = useMemo(() => Object.values(scope).some((fields) => fields && fields.length > 0), [scope])

  if (!pauseData) return null

  function updateList(section: keyof StageProducts, index: number, field: string, value: string) {
    setProducts((current) => {
      const rows = [...((current[section] as Array<Record<string, unknown>> | undefined) || [])]
      rows[index] = { ...rows[index], [field]: value }
      return { ...current, [section]: rows }
    })
  }

  function updateDocument(field: string, value: string) {
    setProducts((current) => ({ ...current, document: { ...(current.document || {}), [field]: value } }))
  }

  function validate(): string | null {
    for (const [section, fields] of Object.entries(scope)) {
      const rows = section === "document" ? [products.document || {}] : ((products[section as keyof StageProducts] as Array<Record<string, unknown>> | undefined) || [])
      for (const row of rows) {
        for (const field of fields || []) {
          const value = String(row?.[field] ?? "").trim()
          if (["field_name", "event", "title", "content"].includes(field) && !value) return `${FIELD_LABELS[field]}不能为空`
          if (LIMITS[field] && value.length > LIMITS[field]) return `${FIELD_LABELS[field]}不能超过 ${LIMITS[field]} 个字符`
        }
      }
    }
    return null
  }

  function buildEdits(): StageEdits {
    const edits: StageEdits = {}
    if (scope.evidences) {
      edits.evidences = (products.evidences || []).map((row) => ({
        id: row.id,
        ...Object.fromEntries(scope.evidences!.map((field) => [field, String(row[field as keyof typeof row] ?? "")])),
      })) as StageEdits["evidences"]
    }
    if (scope.extracted_fields) {
      edits.extracted_fields = (products.extracted_fields || []).map((row) => ({
        id: row.id,
        field_name: row.field_name,
        field_value: row.field_value,
      }))
    }
    if (scope.timeline_nodes) {
      edits.timeline_nodes = (products.timeline_nodes || []).map((row) => ({ id: row.id, event: row.event }))
    }
    if (scope.document && products.document) {
      edits.document = Object.fromEntries(scope.document.map((field) => [field, String(products.document?.[field as keyof typeof products.document] ?? "")]))
    }
    return edits
  }

  async function handleResume() {
    const validationError = validate()
    if (validationError) {
      setLocalError(validationError)
      return
    }
    setLocalError(null)
    setSubmitting("resume")
    try {
      await resumePausedWorkflow(caseId, buildEdits())
    } catch {
      // store 已记录错误
    } finally {
      setSubmitting(null)
    }
  }

  async function handleCancel() {
    if (!window.confirm("确定取消本次工作流吗？已完成的阶段产物会保留。")) return
    setLocalError(null)
    setSubmitting("cancel")
    try {
      await cancelWorkflow(caseId)
    } catch {
      // store 已记录错误
    } finally {
      setSubmitting(null)
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 to-white shadow-sm">
      <header className="border-b border-amber-200 px-5 py-4">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-amber-100 p-2 text-amber-700"><AlertTriangle className="h-5 w-5" /></div>
          <div>
            <h3 className="font-semibold text-slate-900">已暂停于「{NODE_LABELS[pauseData.paused_after]}」阶段</h3>
            <p className="mt-1 text-sm leading-6 text-slate-600">{pauseData.message || "请检查并修改本阶段产物。保存后，工作流会从下一安全步骤继续执行。"}</p>
          </div>
        </div>
      </header>

      <div className="space-y-4 p-5">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />正在加载可编辑产物...</div>
        ) : !hasEditableFields ? (
          <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50/60 px-4 py-6 text-sm text-slate-600">此阶段没有可编辑字段，你可以直接继续工作流。</div>
        ) : (
          <>
            {scope.evidences && (products.evidences || []).map((row, index) => (
              <div key={row.id} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">{row.code || `证据 ${index + 1}`} {row.description ? `· ${row.description}` : ""}</div>
                <div className="space-y-3">{scope.evidences!.map((field) => (
                  <label key={field} className="block text-sm font-medium text-slate-700">{FIELD_LABELS[field] || field}
                    {field === "extracted_text" || field === "ocr_summary" ? <textarea maxLength={LIMITS[field]} value={String(row[field as keyof typeof row] ?? "")} onChange={(e) => updateList("evidences", index, field, e.target.value)} className={`${textInputClass(true)} mt-1.5`} /> : <input maxLength={LIMITS[field]} value={String(row[field as keyof typeof row] ?? "")} onChange={(e) => updateList("evidences", index, field, e.target.value)} className={`${textInputClass()} mt-1.5`} />}
                  </label>
                ))}</div>
              </div>
            ))}

            {scope.extracted_fields && (products.extracted_fields || []).map((row, index) => (
              <div key={row.id} className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 md:grid-cols-2">
                <div className="md:col-span-2 text-xs font-semibold text-slate-500">{row.evidence_code || `抽取字段 ${index + 1}`}</div>
                {scope.extracted_fields!.map((field) => <label key={field} className="text-sm font-medium text-slate-700">{FIELD_LABELS[field] || field}<input maxLength={LIMITS[field]} value={String(row[field as keyof typeof row] ?? "")} onChange={(e) => updateList("extracted_fields", index, field, e.target.value)} className={`${textInputClass()} mt-1.5`} /></label>)}
              </div>
            ))}

            {scope.timeline_nodes && (products.timeline_nodes || []).map((row, index) => (
              <div key={row.id} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="mb-2 text-xs font-semibold text-slate-500">时间线节点 {index + 1}{row.datetime ? ` · ${new Date(row.datetime).toLocaleString()}` : ""}</div>
                {scope.timeline_nodes!.map((field) => <label key={field} className="text-sm font-medium text-slate-700">{FIELD_LABELS[field] || field}<textarea maxLength={LIMITS[field]} value={String(row[field as keyof typeof row] ?? "")} onChange={(e) => updateList("timeline_nodes", index, field, e.target.value)} className={`${textInputClass(true)} mt-1.5`} /></label>)}
              </div>
            ))}

            {scope.document && products.document && <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">{scope.document.map((field) => <label key={field} className="block text-sm font-medium text-slate-700">{FIELD_LABELS[field] || field}{field === "content" ? <textarea maxLength={LIMITS[field]} value={String(products.document?.[field as keyof typeof products.document] ?? "")} onChange={(e) => updateDocument(field, e.target.value)} className={`${textInputClass(true)} mt-1.5 min-h-64`} /> : <input maxLength={LIMITS[field]} value={String(products.document?.[field as keyof typeof products.document] ?? "")} onChange={(e) => updateDocument(field, e.target.value)} className={`${textInputClass()} mt-1.5`} />}</label>)}</div>}
          </>
        )}

        {(localError || storeError) && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{localError || storeError}</div>}

        <div className="flex flex-wrap justify-end gap-3 border-t border-amber-100 pt-4">
          <button type="button" onClick={handleCancel} disabled={loading || submitting !== null} className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50">{submitting === "cancel" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}取消工作流</button>
          <button type="button" onClick={handleResume} disabled={loading || submitting !== null} className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50">{submitting === "resume" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}保存并继续</button>
        </div>
      </div>
    </section>
  )
}

export default StagePausePanel
