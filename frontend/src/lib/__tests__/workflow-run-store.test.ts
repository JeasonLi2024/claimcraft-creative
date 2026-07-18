/**
 * Task 3.5.1 / Task 6.2.2: workflow-run-store.applySSEEvent 单元测试
 *
 * 覆盖场景（对齐 SubTask 3.5.1 applySSEEvent reducer / 6.2.2 Snapshot 初始化 + SSE 增量更新）：
 * 1. run_id 不符 → applied=false, needsSnapshotRefetch=false
 * 2. event_id 重复 → applied=false, needsSnapshotRefetch=false
 * 3. revision 跳跃 → applied=false, needsSnapshotRefetch=true，并更新 snapshotRevision
 * 4. revision 重复 → applied=false, needsSnapshotRefetch=false
 * 5. stage.* 事件 → applied=true，更新对应 stage
 * 6. artifact.created → applied=true，追加 artifact
 * 7. artifact.updated → applied=true，更新对应 artifact
 * 8. artifact.stale → applied=true，标记 artifact.status='stale'
 * 9. intervention.created → applied=true，设置 activeIntervention
 * 10. intervention.submitted/cancelled → applied=true，清空 activeIntervention
 * 11. issue.created → applied=true，追加 issue
 * 12. issue.resolved → applied=true，移除对应 issue
 * 13. document.delta/completed → applied=true，no-op
 * 14. 未知事件类型 → applied=true, needsSnapshotRefetch=true
 * 15. cursor 更新：latestEventId + snapshotRevision
 * 16. reset() 清空所有状态
 * 17. applySnapshot() 设置所有字段
 */

import { describe, it, expect, beforeEach } from "vitest"
import { useWorkflowRunStore, type SnapshotResponse } from "@/stores/workflow-run-store"
import type { SSEEvent } from "@/lib/workflow-events"
import type {
  WorkflowRun,
  WorkflowStage,
  WorkflowArtifact,
  WorkflowIntervention,
  WorkflowAllowedActions,
  Issue,
} from "@/types/workflow"

// ---------- 辅助函数 ----------

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: 100,
    case_id: 1,
    thread_id: "case-1-run-100",
    status: "running",
    workflow_version: "v11",
    state_schema_version: 1,
    policy_version: "v1",
    prompt_bundle_version: "2026.07",
    revision: 10,
    current_stage: "material_understanding",
    current_node: "ocr",
    progress: 0.3,
    started_at: "2026-07-17T10:00:00Z",
    completed_at: null,
    error_message: null,
    ...overrides,
  }
}

function makeStage(overrides: Partial<WorkflowStage> = {}): WorkflowStage {
  return {
    key: "material_understanding",
    name: "材料理解",
    status: "running",
    quality_score: null,
    issue_count: 0,
    progress: 0.3,
    nodes: ["preclassify", "ocr", "classify"],
    ...overrides,
  }
}

function makeArtifact(overrides: Partial<WorkflowArtifact> = {}): WorkflowArtifact {
  return {
    id: 1,
    run_id: 100,
    kind: "ocr",
    stage: "material_understanding",
    status: "active",
    source_refs: [],
    summary: "OCR 识别结果",
    payload: { content: "示例内容" },
    created_at: "2026-07-17T10:01:00Z",
    updated_at: null,
    ...overrides,
  }
}

function makeIntervention(
  overrides: Partial<WorkflowIntervention> = {},
): WorkflowIntervention {
  return {
    id: 1,
    run_id: 100,
    intervention_type: "quality_review",
    stage: "fact_checking",
    status: "pending",
    base_revision: 10,
    form_schema: { fields: [] },
    initial_values: {},
    impact: {},
    created_at: "2026-07-17T10:02:00Z",
    submitted_at: null,
    ...overrides,
  }
}

function makeIssue(overrides: Partial<Issue> = {}): Issue {
  return {
    code: "LOW_CONFIDENCE",
    message: "字段置信度低于阈值",
    severity: "warning",
    evidence_id: 1,
    stage: "fact_checking",
    recoverable: true,
    ...overrides,
  }
}

function makeActions(overrides: Partial<WorkflowAllowedActions> = {}): WorkflowAllowedActions {
  return {
    can_pause: true,
    can_resume: false,
    can_cancel: true,
    can_retry: false,
    can_restart_from_stage: false,
    ...overrides,
  }
}

function makeSnapshot(overrides: Partial<SnapshotResponse> = {}): SnapshotResponse {
  return {
    run: makeRun(),
    stages: [makeStage()],
    active_intervention: null,
    artifacts: [],
    issues: [],
    actions: makeActions(),
    ...overrides,
  }
}

function makeEvent(overrides: Partial<SSEEvent> = {}): SSEEvent {
  return {
    event_id: 200,
    event_type: "stage.progress",
    run_id: 100,
    revision: 11,
    occurred_at: "2026-07-17T10:01:30Z",
    ts: "2026-07-17T10:01:30Z",
    ...overrides,
  } as SSEEvent
}

function getStore() {
  return useWorkflowRunStore.getState()
}

// ---------- 测试前置：每个用例前重置 store ----------

beforeEach(() => {
  useWorkflowRunStore.getState().reset()
})

// ---------- 1-4: SSE 同步规则检查 ----------

describe("applySSEEvent SSE 同步规则检查", () => {
  it("run_id 不符时返回 applied=false + needsSnapshotRefetch=false", () => {
    getStore().applySnapshot(makeSnapshot())
    const event = makeEvent({ run_id: 999 })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(false)
    expect(result.needsSnapshotRefetch).toBe(false)
    expect(result.reason).toBe("run_id_mismatch")
  })

  it("event_id 重复时返回 applied=false + needsSnapshotRefetch=false", () => {
    getStore().applySnapshot(makeSnapshot())
    // 先消费一个 event_id=200 的事件，让 latestEventId 推进到 200
    const event1 = makeEvent({ event_id: 200, event_type: "document.delta" })
    getStore().applySSEEvent(event1)
    expect(getStore().latestEventId).toBe(200)

    // 再发送 event_id=200 的事件 → 应被去重
    const event2 = makeEvent({ event_id: 200, event_type: "document.delta" })
    const result = getStore().applySSEEvent(event2)
    expect(result.applied).toBe(false)
    expect(result.reason).toBe("duplicate_event_id")
  })

  it("revision 跳跃时返回 applied=false + needsSnapshotRefetch=true + 更新 snapshotRevision", () => {
    getStore().applySnapshot(makeSnapshot()) // snapshotRevision = 10
    const event = makeEvent({ revision: 20 }) // 跳跃 10→20（缺 11-19）
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(false)
    expect(result.needsSnapshotRefetch).toBe(true)
    expect(result.reason).toBe("revision_jump")
    expect(getStore().snapshotRevision).toBe(20)
  })

  it("revision 重复时返回 applied=false + needsSnapshotRefetch=false", () => {
    getStore().applySnapshot(makeSnapshot()) // snapshotRevision = 10
    const event = makeEvent({ revision: 10 })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(false)
    expect(result.needsSnapshotRefetch).toBe(false)
    expect(result.reason).toBe("stale_revision")
  })
})

// ---------- 5: stage.* 事件 ----------

describe("applySSEEvent stage.* 事件", () => {
  it("stage.completed 更新对应 stage 的 status + progress", () => {
    getStore().applySnapshot(makeSnapshot({
      stages: [makeStage({ key: "material_understanding", status: "running", progress: 0.3 })],
    }))
    const event = makeEvent({
      event_type: "stage.completed",
      stage: "material_understanding",
      payload: { stage: "material_understanding", status: "completed", progress: 1.0 },
    })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(result.needsSnapshotRefetch).toBe(false)
    const stage = getStore().stages.find((s) => s.key === "material_understanding")
    expect(stage?.status).toBe("completed")
    expect(stage?.progress).toBe(1.0)
  })

  it("stage.progress 更新 progress 字段", () => {
    getStore().applySnapshot(makeSnapshot({
      stages: [makeStage({ key: "fact_checking", status: "running", progress: 0.2, nodes: ["extract", "review"] })],
    }))
    const event = makeEvent({
      event_type: "stage.progress",
      payload: { stage: "fact_checking", progress: 0.5 },
    })
    getStore().applySSEEvent(event)
    const stage = getStore().stages.find((s) => s.key === "fact_checking")
    expect(stage?.progress).toBe(0.5)
  })

  it("stage.quality_changed 更新 quality_score + issue_count", () => {
    getStore().applySnapshot(makeSnapshot({
      stages: [makeStage({ key: "material_understanding", quality_score: null, issue_count: 0 })],
    }))
    const event = makeEvent({
      event_type: "stage.quality_changed",
      payload: { stage: "material_understanding", quality_score: 0.85, issue_count: 2 },
    })
    getStore().applySSEEvent(event)
    const stage = getStore().stages.find((s) => s.key === "material_understanding")
    expect(stage?.quality_score).toBe(0.85)
    expect(stage?.issue_count).toBe(2)
  })
})

// ---------- 6-8: artifact.* 事件 ----------

describe("applySSEEvent artifact.* 事件", () => {
  it("artifact.created 追加新 artifact", () => {
    getStore().applySnapshot(makeSnapshot({ artifacts: [] }))
    const newArtifact = makeArtifact({ id: 1, kind: "ocr", summary: "OCR 结果" })
    const event = makeEvent({
      event_type: "artifact.created",
      payload: { artifact: newArtifact },
    })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(getStore().artifacts).toHaveLength(1)
    expect(getStore().artifacts[0].id).toBe(1)
    expect(getStore().artifacts[0].summary).toBe("OCR 结果")
  })

  it("artifact.updated 更新已有 artifact", () => {
    const existing = makeArtifact({ id: 1, summary: "旧摘要", status: "active" })
    getStore().applySnapshot(makeSnapshot({ artifacts: [existing] }))
    const updated = makeArtifact({ id: 1, summary: "新摘要" })
    const event = makeEvent({
      event_type: "artifact.updated",
      payload: { artifact: updated },
    })
    getStore().applySSEEvent(event)
    expect(getStore().artifacts).toHaveLength(1)
    expect(getStore().artifacts[0].summary).toBe("新摘要")
  })

  it("artifact.stale 标记对应 artifact 状态为 stale", () => {
    const artifact = makeArtifact({ id: 5, status: "active" })
    getStore().applySnapshot(makeSnapshot({ artifacts: [artifact] }))
    const event = makeEvent({
      event_type: "artifact.stale",
      payload: { artifact_id: 5 },
    })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(getStore().artifacts[0].status).toBe("stale")
  })

  it("artifact.stale 在 artifact_id 不存在时静默忽略", () => {
    getStore().applySnapshot(makeSnapshot({ artifacts: [] }))
    const event = makeEvent({
      event_type: "artifact.stale",
      payload: { artifact_id: 999 },
    })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(getStore().artifacts).toHaveLength(0)
  })
})

// ---------- 9-10: intervention.* 事件 ----------

describe("applySSEEvent intervention.* 事件", () => {
  it("intervention.created 设置 activeIntervention（payload.intervention）", () => {
    getStore().applySnapshot(makeSnapshot({ active_intervention: null }))
    const intervention = makeIntervention({ id: 7, base_revision: 10 })
    const event = makeEvent({
      event_type: "intervention.created",
      payload: { intervention },
    })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(getStore().activeIntervention).not.toBeNull()
    expect(getStore().activeIntervention?.id).toBe(7)
  })

  it("intervention.created 兼容旧格式（payload 直接为 intervention 对象）", () => {
    getStore().applySnapshot(makeSnapshot({ active_intervention: null }))
    const intervention = makeIntervention({ id: 8, base_revision: 10 })
    // 旧格式：payload 直接是 intervention 对象本身
    const event = makeEvent({
      event_type: "intervention.created",
      payload: intervention,
    })
    // mock readPayload 优先读 payload，发现是 intervention 对象
    // 但 reducer 在 payload.id 存在时也会触发回退分支
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(getStore().activeIntervention?.id).toBe(8)
  })

  it("intervention.submitted 清空 activeIntervention", () => {
    const intervention = makeIntervention({ id: 7 })
    getStore().applySnapshot(makeSnapshot({ active_intervention: intervention }))
    expect(getStore().activeIntervention).not.toBeNull()

    const event = makeEvent({ event_type: "intervention.submitted" })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(getStore().activeIntervention).toBeNull()
  })

  it("intervention.cancelled 清空 activeIntervention", () => {
    const intervention = makeIntervention({ id: 7 })
    getStore().applySnapshot(makeSnapshot({ active_intervention: intervention }))
    const event = makeEvent({ event_type: "intervention.cancelled" })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(getStore().activeIntervention).toBeNull()
  })
})

// ---------- 11-12: issue.* 事件 ----------

describe("applySSEEvent issue.* 事件", () => {
  it("issue.created 追加新 issue", () => {
    getStore().applySnapshot(makeSnapshot({ issues: [] }))
    const issue = makeIssue({ code: "LOW_CONFIDENCE" })
    const event = makeEvent({
      event_type: "issue.created",
      payload: { issue },
    })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(getStore().issues).toHaveLength(1)
    expect(getStore().issues[0].code).toBe("LOW_CONFIDENCE")
  })

  it("issue.resolved 按 code 过滤对应 issue", () => {
    const issue1 = makeIssue({ code: "LOW_CONFIDENCE" })
    const issue2 = makeIssue({ code: "MISSING_FIELD" })
    getStore().applySnapshot(makeSnapshot({ issues: [issue1, issue2] }))
    const event = makeEvent({
      event_type: "issue.resolved",
      payload: { code: "LOW_CONFIDENCE" },
    })
    getStore().applySSEEvent(event)
    expect(getStore().issues).toHaveLength(1)
    expect(getStore().issues[0].code).toBe("MISSING_FIELD")
  })
})

// ---------- 13: document.* 事件 ----------

describe("applySSEEvent document.* 事件", () => {
  it("document.delta 返回 applied=true，不修改 store 其他字段", () => {
    getStore().applySnapshot(makeSnapshot())
    const before = { ...getStore() }
    const event = makeEvent({ event_type: "document.delta", delta: "hello" })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(result.needsSnapshotRefetch).toBe(false)
    // 除 latestEventId/snapshotRevision 外不变
    expect(getStore().stages).toEqual(before.stages)
    expect(getStore().artifacts).toEqual(before.artifacts)
    expect(getStore().issues).toEqual(before.issues)
  })

  it("document.completed 返回 applied=true", () => {
    getStore().applySnapshot(makeSnapshot())
    const event = makeEvent({ event_type: "document.completed" })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
  })
})

// ---------- 14: 未知事件类型 ----------

describe("applySSEEvent 未知事件类型", () => {
  it("未知 event_type 返回 applied=true + needsSnapshotRefetch=true", () => {
    getStore().applySnapshot(makeSnapshot())
    // 构造一个未在 switch 中处理的事件类型
    const event = makeEvent({ event_type: "node.complete" })
    const result = getStore().applySSEEvent(event)
    expect(result.applied).toBe(true)
    expect(result.needsSnapshotRefetch).toBe(true)
    expect(result.reason).toBe("unknown_event_type")
  })
})

// ---------- 15: cursor 更新 ----------

describe("applySSEEvent cursor 更新", () => {
  it("正常处理后更新 latestEventId + snapshotRevision", () => {
    getStore().applySnapshot(makeSnapshot({ run: makeRun({ revision: 10 }) }))
    expect(getStore().latestEventId).toBeNull()
    expect(getStore().snapshotRevision).toBe(10)

    const event = makeEvent({ event_id: 200, revision: 11, event_type: "document.delta" })
    getStore().applySSEEvent(event)

    expect(getStore().latestEventId).toBe(200)
    expect(getStore().snapshotRevision).toBe(11)
  })

  it("event_id 缺失时不更新 latestEventId", () => {
    getStore().applySnapshot(makeSnapshot({ run: makeRun({ revision: 10 }) }))
    const event = makeEvent({ event_id: undefined, revision: 11, event_type: "document.delta" })
    delete (event as { event_id?: unknown }).event_id
    getStore().applySSEEvent(event)
    expect(getStore().latestEventId).toBeNull()
    expect(getStore().snapshotRevision).toBe(11)
  })
})

// ---------- 16: reset() ----------

describe("reset() 清空状态", () => {
  it("reset 后所有字段回到初始值", () => {
    getStore().applySnapshot(makeSnapshot({
      run: makeRun({ id: 100, revision: 10 }),
      stages: [makeStage()],
      artifacts: [makeArtifact()],
      issues: [makeIssue()],
      active_intervention: makeIntervention(),
    }))
    getStore().setConnection("connected")
    getStore().setLatestEventId(200)
    getStore().setFatalError("oops")

    getStore().reset()

    const state = getStore()
    expect(state.run).toBeNull()
    expect(state.runId).toBeNull()
    expect(state.stages).toEqual([])
    expect(state.artifacts).toEqual([])
    expect(state.issues).toEqual([])
    expect(state.activeIntervention).toBeNull()
    expect(state.connection).toBe("disconnected")
    expect(state.latestEventId).toBeNull()
    expect(state.snapshotRevision).toBeNull()
    expect(state.fatalError).toBeNull()
    expect(state.actions).toEqual({
      can_pause: false,
      can_resume: false,
      can_cancel: false,
      can_retry: false,
      can_restart_from_stage: false,
    })
  })
})

// ---------- 17: applySnapshot() ----------

describe("applySnapshot() 设置所有字段", () => {
  it("applySnapshot 后所有字段正确设置", () => {
    const snapshot = makeSnapshot({
      run: makeRun({ id: 100, revision: 10 }),
      stages: [makeStage({ key: "material_understanding" })],
      artifacts: [makeArtifact({ id: 1 })],
      issues: [makeIssue({ code: "TEST" })],
      active_intervention: makeIntervention({ id: 5 }),
      actions: makeActions({ can_pause: true, can_retry: true }),
    })

    getStore().applySnapshot(snapshot)

    const state = getStore()
    expect(state.run).toEqual(snapshot.run)
    expect(state.runId).toBe(100)
    expect(state.stages).toEqual(snapshot.stages)
    expect(state.artifacts).toEqual(snapshot.artifacts)
    expect(state.issues).toEqual(snapshot.issues)
    expect(state.activeIntervention).toEqual(snapshot.active_intervention)
    expect(state.actions).toEqual(snapshot.actions)
    expect(state.snapshotRevision).toBe(10)
    expect(state.fatalError).toBeNull()
  })
})

// ---------- 额外：setters 行为验证 ----------

describe("setters 行为验证", () => {
  it("setRun 设置 run", () => {
    getStore().setRun(makeRun({ id: 999 }))
    expect(getStore().run?.id).toBe(999)
  })

  it("setRunId 设置 runId", () => {
    getStore().setRunId(42)
    expect(getStore().runId).toBe(42)
  })

  it("setConnection 设置连接状态", () => {
    getStore().setConnection("connecting")
    expect(getStore().connection).toBe("connecting")
  })

  it("setLatestEventId 设置事件游标", () => {
    getStore().setLatestEventId(500)
    expect(getStore().latestEventId).toBe(500)
  })

  it("setFatalError 设置错误信息", () => {
    getStore().setFatalError("fatal error")
    expect(getStore().fatalError).toBe("fatal error")
  })
})
