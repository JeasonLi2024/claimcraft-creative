// 投诉文本页：加载当前工作流运行的投诉书产物并支持编辑（DocumentEditor）。
// 文书编辑统一收敛到本页；工作流全过程展示在 /analysis。
import { useParams } from "react-router"
import { WandSparkles } from "lucide-react"
import { WorkflowDocumentWorkbench } from "@/components/workflow/WorkflowDocumentWorkbench"

export default function ComplaintPage() {
  const { caseId } = useParams<{ caseId: string }>()

  return (
    <WorkflowDocumentWorkbench
      caseId={Number(caseId)}
      kind="complaint"
      hero={{
        eyebrow: "智能文书生成",
        title: "投诉文案",
        description: "基于案件事实与证据引用生成结构化投诉书，可逐段编辑、AI 重写并核对法律依据，完成后前往导出。",
        icon: WandSparkles,
      }}
    />
  )
}
