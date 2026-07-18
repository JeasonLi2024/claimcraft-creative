// 工作流运行实例 store（Zustand slice）
// 对齐 spec.md Requirement: Store Split / Task 3.5.1
//
// 职责：
//   - 当前 WorkflowRun 基础信息 + snapshot 数据（stages / artifacts / activeIntervention / issues / actions）
//   - SSE 连接状态 + 事件游标（latestEventId / snapshotRevision）
//   - 错误状态（fatalError）
//   - applySnapshot / applySSEEvent（事件局部更新）/ reset
//
// 与 case-store.ts 的关系：
//   - case-store.ts 仍保留旧 Workflow Slice 字段（已标注 @deprecated），仅向后兼容
//   - 新组件应使用 workflow-run-store 作为权威来源
//   - intervention-store.ts 用于编辑草稿持久化，通过 setIntervention 同步 activeIntervention

import { create } from "zustand"
import type {
  WorkflowRun,
  WorkflowStage,
  WorkflowArtifact,
  WorkflowIntervention,
  WorkflowAllowedActions,
} from "@/types/workflow"
import type { Issue } from "@/types/workflow"
import type { SSEEvent } from "@/lib/workflow-events"
import { checkSSEEvent, type ReducerState } from "@/lib/workflow-event-reducer"

// ---------- Snapshot 响应类型 ----------

export interface SnapshotResponse {
  run: WorkflowRun
  stages: WorkflowStage[]
  active_intervention: WorkflowIntervention | null
  artifacts: WorkflowArtifact[]
  issues: Issue[]
  actions: WorkflowAllowedActions
}

// ---------- applySSEEvent 返回结果 ----------

export interface ApplySSEEventResult {
  /** 是否已应用事件到本地状态 */
  applied: boolean
  /** 是否需要触发 snapshot 重新获取（revision 跳跃或未知事件类型时为 true） */
  needsSnapshotRefetch: boolean
  /** 决策原因（便于调试） */
  reason?: string
}

// ---------- Store 类型 ----------

export type WorkflowRunConnection =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error"

export interface WorkflowRunState {
  // 运行基础信息
  run: WorkflowRun | null
  runId: number | null

  // 快照数据
  stages: WorkflowStage[]
  activeIntervention: WorkflowIntervention | null
  artifacts: WorkflowArtifact[]
  issues: Issue[]
  actions: WorkflowAllowedActions

  // 连接状态
  connection: WorkflowRunConnection

  // 事件游标
  latestEventId: number | null
  snapshotRevision: number | null

  // 错误状态
  fatalError: string | null

  // Actions
  setRun: (run: WorkflowRun | null) => void
  setRunId: (runId: number | null) => void
  applySnapshot: (snapshot: SnapshotResponse) => void
  applySSEEvent: (event: SSEEvent) => ApplySSEEventResult
  setConnection: (status: WorkflowRunState["connection"]) => void
  setLatestEventId: (eventId: number | null) => void
  setFatalError: (error: string | null) => void
  /** 切换 run 时清空状态（对齐 spec Run switch destroys old connection） */
  reset: () => void
}

// ---------- 默认 actions ----------

const DEFAULT_ACTIONS: WorkflowAllowedActions = {
  can_pause: false,
  can_resume: false,
  can_cancel: false,
  can_retry: false,
  can_restart_from_stage: false,
}

// ---------- payload 类型守卫 ----------
//
// SSEEvent 的 index signature 是 `[key: string]: unknown`，
// event.payload 也是 unknown。以下守卫将常见 payload 形状提取为可用类型。

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function readPayload(event: SSEEvent): Record<string, unknown> | null {
  // 优先使用 payload 字段（新信封），否则回退到事件根（旧事件类型）
  const direct = (event as { payload?: unknown }).payload
  if (isObject(direct)) return direct
  // 旧事件：所有字段都在事件根上（event.node / event.ts / event.delta 等）
  // 提取为副本以便按 key 查找
  const flat: Record<string, unknown> = {}
  for (const key of Object.keys(event)) {
    if (key === "event_id" || key === "event_type" || key === "run_id" ||
        key === "thread_id" || key === "revision" || key === "occurred_at" ||
        key === "timestamp" || key === "payload") {
      continue
    }
    flat[key] = (event as Record<string, unknown>)[key]
  }
  return flat
}

function readStringField(payload: Record<string, unknown>, key: string): string | null {
  const v = payload[key]
  return typeof v === "string" && v.length > 0 ? v : null
}

function readNumberField(payload: Record<string, unknown>, key: string): number | null {
  const v = payload[key]
  return typeof v === "number" && !Number.isNaN(v) ? v : null
}

function readObjectField<T = Record<string, unknown>>(
  payload: Record<string, unknown>,
  key: string,
): T | null {
  const v = payload[key]
  return isObject(v) ? (v as T) : null
}

// ---------- Store 实现 ----------

export const useWorkflowRunStore = create<WorkflowRunState>((set, get) => ({
  run: null,
  runId: null,
  stages: [],
  activeIntervention: null,
  artifacts: [],
  issues: [],
  actions: { ...DEFAULT_ACTIONS },
  connection: "disconnected",
  latestEventId: null,
  snapshotRevision: null,
  fatalError: null,

  setRun: (run) => set({ run }),
  setRunId: (runId) => set({ runId }),

  applySnapshot: (snapshot) =>
    set({
      run: snapshot.run,
      runId: snapshot.run.id,
      stages: snapshot.stages,
      activeIntervention: snapshot.active_intervention,
      artifacts: snapshot.artifacts,
      issues: snapshot.issues,
      actions: snapshot.actions,
      snapshotRevision: snapshot.run.revision,
      fatalError: null,
    }),

  applySSEEvent: (event) => {
    const state = get()

    // ===== 四步 SSE 同步规则检查（委托 workflow-event-reducer） =====
    const reducerState: ReducerState = {
      runId: state.runId,
      latestEventId: state.latestEventId,
      snapshotRevision: state.snapshotRevision,
    }
    const check = checkSSEEvent(event, reducerState)

    if (check.apply === "skip") {
      return { applied: false, needsSnapshotRefetch: false, reason: check.reason }
    }
    if (check.apply === "refetch_snapshot") {
      // revision 跳跃：仅更新 revision 游标（若提供），由调用方触发 snapshot 重新获取
      if (typeof check.newRevision === "number") {
        set({ snapshotRevision: check.newRevision })
      }
      return { applied: false, needsSnapshotRefetch: true, reason: check.reason }
    }

    // ===== Step 4: 应用事件到本地状态 =====
    // 更新游标
    const cursorUpdate: Partial<WorkflowRunState> = {}
    if (typeof check.newEventId === "number") {
      cursorUpdate.latestEventId = check.newEventId
    }
    if (typeof check.newRevision === "number") {
      cursorUpdate.snapshotRevision = check.newRevision
    }
    if (Object.keys(cursorUpdate).length > 0) {
      set(cursorUpdate)
    }

    const payload = readPayload(event) ?? {}

    // 根据 event_type 局部更新
    switch (event.event_type) {
      case "stage.started":
      case "stage.progress":
      case "stage.completed":
      case "stage.quality_changed": {
        // 局部更新 stages：通过 stage key 或 name 匹配
        const stageKey = readStringField(payload, "stage") ?? readStringField(payload, "key")
        if (!stageKey) break
        set((s) => ({
          stages: s.stages.map((st) => {
            if (st.key !== stageKey && st.name !== stageKey) return st
            // 合并 payload 中可识别的字段
            const merged: WorkflowStage = { ...st }
            const status = readStringField(payload, "status") as WorkflowStage["status"] | null
            if (status) merged.status = status
            const progress = readNumberField(payload, "progress")
            if (progress != null) merged.progress = progress
            const qualityScore = readNumberField(payload, "quality_score")
            if (qualityScore != null) merged.quality_score = qualityScore
            const issueCount = readNumberField(payload, "issue_count")
            if (issueCount != null) merged.issue_count = issueCount
            return merged
          }),
        }))
        break
      }
      case "artifact.created":
      case "artifact.updated": {
        // 局部更新或追加 artifacts
        const artifact = readObjectField<WorkflowArtifact>(payload, "artifact")
        if (!artifact || typeof artifact.id !== "number") break
        set((s) => {
          const idx = s.artifacts.findIndex((a) => a.id === artifact.id)
          if (idx >= 0) {
            const newArtifacts = s.artifacts.slice()
            newArtifacts[idx] = { ...newArtifacts[idx], ...artifact }
            return { artifacts: newArtifacts }
          }
          return { artifacts: [...s.artifacts, artifact] }
        })
        break
      }
      case "artifact.stale": {
        // 标记单个 artifact 为 stale
        const artifactId = readNumberField(payload, "artifact_id")
        if (artifactId == null) break
        set((s) => ({
          artifacts: s.artifacts.map((a) =>
            a.id === artifactId ? { ...a, status: "stale" } : a,
          ),
        }))
        break
      }
      case "intervention.created": {
        // 直接从 payload 读取完整 intervention 对象
        const intervention = readObjectField<WorkflowIntervention>(payload, "intervention")
        if (intervention && typeof intervention.id === "number") {
          set({ activeIntervention: intervention })
        } else if (payload && typeof payload.id === "number") {
          // 兼容：payload 直接是 intervention 对象
          set({ activeIntervention: payload as unknown as WorkflowIntervention })
        }
        break
      }
      case "intervention.submitted":
      case "intervention.cancelled": {
        set({ activeIntervention: null })
        break
      }
      case "issue.created": {
        const issue = readObjectField<Issue>(payload, "issue")
        if (issue && typeof issue.code === "string") {
          set((s) => ({ issues: [...s.issues, issue] }))
        }
        break
      }
      case "issue.resolved": {
        const issueId = readNumberField(payload, "issue_id")
        const issueCode = readStringField(payload, "code")
        set((s) => ({
          issues: s.issues.filter((i) => {
            if (issueId != null && typeof (i as unknown as { id?: number }).id === "number") {
              return (i as unknown as { id: number }).id !== issueId
            }
            if (issueCode != null) {
              return i.code !== issueCode
            }
            return true
          }),
        }))
        break
      }
      case "document.delta":
      case "document.completed":
        // 文书流式生成事件，由专门的 ProductStream 组件消费
        // 此处仅更新游标（已在上方完成），不修改 store 其他字段
        break
      default:
        // 未知事件类型 → 触发 snapshot refetch（保守策略，确保状态最终一致）
        return { applied: true, needsSnapshotRefetch: true, reason: "unknown_event_type" }
    }

    return { applied: true, needsSnapshotRefetch: false }
  },

  setConnection: (connection) => set({ connection }),
  setLatestEventId: (eventId) => set({ latestEventId: eventId }),
  setFatalError: (error) => set({ fatalError: error }),

  reset: () =>
    set({
      run: null,
      runId: null,
      stages: [],
      activeIntervention: null,
      artifacts: [],
      issues: [],
      actions: { ...DEFAULT_ACTIONS },
      connection: "disconnected",
      latestEventId: null,
      snapshotRevision: null,
      fatalError: null,
    }),
}))

export default useWorkflowRunStore
