// 反证答辩页：加载当前工作流运行的反证答辩书产物并支持编辑（DocumentEditor）。
// 与投诉页复用同一套 WorkflowDocumentWorkbench，仅文书种类与文案不同。
import { useParams } from "react-router"
import { Gavel } from "lucide-react"
import { useCaseStore } from "@/stores/case-store"
import { WorkflowDocumentWorkbench } from "@/components/workflow/WorkflowDocumentWorkbench"

export default function RespondPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const currentCase = useCaseStore((s) => s.currentCase)
  const isRespondMode = currentCase?.case_mode === "respond"

  return (
    <div className="space-y-5">
      {currentCase && !isRespondMode && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          当前案件为维权投诉模式，反证答辩书适用于商家反证模式案件。
        </div>
      )}
      <WorkflowDocumentWorkbench
        caseId={Number(caseId)}
        kind="respond_complaint"
        hero={{
          eyebrow: "商家反证答辩",
          title: "反证答辩书",
          description: "基于证据自动生成商家反证答辩书，可逐段编辑、AI 重写并核对法律依据，完成后前往导出。",
          icon: Gavel,
        }}
      />
    </div>
  )
}
