// 工作流文书产物工具：从 run 快照的 artifacts 中定位文书产物、推导文书 id。
// 供 WorkflowAnalysisPage（编辑入口存在性判断）与 WorkflowDocumentWorkbench（加载文书）共用。
import type { WorkflowArtifact, WorkflowArtifactKind } from "@/types/workflow"

// 文书产物类型（document_generation 阶段）
export const DOC_ARTIFACT_KINDS: readonly WorkflowArtifactKind[] = [
  "complaint_draft",
  "respond_complaint_draft",
]

// 文书生成阶段名（后端 artifact.stage 可能为中文或英文 key）
const DOC_STAGE_NAMES = new Set(["document_generation", "文书生成"])

function isDocArtifact(a: WorkflowArtifact, kind?: WorkflowArtifactKind): boolean {
  if (kind) return a.kind === kind
  return DOC_ARTIFACT_KINDS.includes(a.kind) || DOC_STAGE_NAMES.has(a.stage)
}

/**
 * 取最近一个文书产物（按 artifacts 顺序从后往前，与后端追加顺序一致）。
 * 传入 kind 时仅匹配该种类（complaint_draft / respond_complaint_draft），
 * 否则匹配任意文书种类或 document_generation 阶段。
 */
export function findDocumentArtifact(
  artifacts: WorkflowArtifact[],
  kind?: WorkflowArtifactKind,
): WorkflowArtifact | null {
  for (let i = artifacts.length - 1; i >= 0; i--) {
    if (isDocArtifact(artifacts[i], kind)) return artifacts[i]
  }
  return null
}

/**
 * 推导传给 documentApi 的文书 id：优先 payload.document_version_id，回退 artifact.id。
 */
export function documentIdForArtifact(artifact: WorkflowArtifact): string {
  const versionId = (artifact.payload as { document_version_id?: number }).document_version_id
  return versionId != null ? String(versionId) : String(artifact.id)
}
