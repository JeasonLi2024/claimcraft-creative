/**
 * Task 3.5.4 / Task 6.2.2: workflow-event-reducer 纯函数单元测试
 *
 * 覆盖场景（对齐 SubTask 3.5.4 四步 SSE 同步规则 / 6.2.3 revision 跳跃）：
 * 1. run_id 不符 → skip
 * 2. event_id 重复（<= latestEventId） → skip
 * 3. revision 跳跃（> expected+1） → refetch_snapshot
 * 4. revision 重复/乱序（<= expected） → skip
 * 5. revision 连续（= expected+1） → process
 * 6. 向后兼容：run_id / event_id / revision 任一缺失时跳过对应检查
 * 7. checkSSEEventLegacy 适配：返回 processed + needsRevisionGap
 */

import { describe, it, expect } from "vitest"
import {
  checkSSEEvent,
  checkSSEEventLegacy,
  createReducerState,
  type ReducerState,
  type DispatchContext,
} from "@/lib/workflow-event-reducer"
import type { SSEEvent } from "@/lib/workflow-events"

// ---------- 辅助函数 ----------

function makeEvent(overrides: Partial<SSEEvent> = {}): SSEEvent {
  return {
    event_id: 1,
    event_type: "node.start",
    node: "ocr",
    ts: "2026-07-17T10:00:00Z",
    ...overrides,
  } as SSEEvent
}

function makeState(overrides: Partial<ReducerState> = {}): ReducerState {
  return {
    runId: null,
    latestEventId: null,
    snapshotRevision: null,
    ...overrides,
  }
}

// ---------- Step 1: run_id 检查 ----------

describe("checkSSEEvent Step 1: run_id 检查", () => {
  it("run_id 不符时返回 skip + run_id_mismatch", () => {
    const event = makeEvent({ run_id: 200 })
    const state = makeState({ runId: 100 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("skip")
    expect(result.reason).toBe("run_id_mismatch")
  })

  it("run_id 一致时通过（进入下一步检查）", () => {
    const event = makeEvent({ run_id: 100 })
    const state = makeState({ runId: 100 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
    expect(result.reason).toBe("ok")
  })

  it("state.runId 为 null 时跳过 run_id 检查（向后兼容）", () => {
    const event = makeEvent({ run_id: 999 })
    const state = makeState({ runId: null })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
  })

  it("event.run_id 为 undefined 时跳过 run_id 检查（向后兼容）", () => {
    const event = makeEvent({})
    delete (event as Partial<SSEEvent>).run_id
    const state = makeState({ runId: 100 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
  })

  it("event.run_id 为 null 时跳过 run_id 检查（向后兼容）", () => {
    const event = makeEvent({ run_id: null })
    const state = makeState({ runId: 100 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
  })
})

// ---------- Step 2: event_id 去重 ----------

describe("checkSSEEvent Step 2: event_id 去重", () => {
  it("event_id <= latestEventId 时返回 skip + duplicate_event_id", () => {
    const event = makeEvent({ event_id: 5 })
    const state = makeState({ latestEventId: 10 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("skip")
    expect(result.reason).toBe("duplicate_event_id")
  })

  it("event_id === latestEventId 时返回 skip（去重边界）", () => {
    const event = makeEvent({ event_id: 10 })
    const state = makeState({ latestEventId: 10 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("skip")
    expect(result.reason).toBe("duplicate_event_id")
  })

  it("event_id > latestEventId 时通过", () => {
    const event = makeEvent({ event_id: 11 })
    const state = makeState({ latestEventId: 10 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
    expect(result.newEventId).toBe(11)
  })

  it("state.latestEventId 为 null 时跳过去重检查（向后兼容）", () => {
    const event = makeEvent({ event_id: 1 })
    const state = makeState({ latestEventId: null })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
  })
})

// ---------- Step 3: revision 检查 ----------

describe("checkSSEEvent Step 3: revision 检查", () => {
  it("revision 跳跃（> expected+1）时返回 refetch_snapshot + revision_jump", () => {
    const event = makeEvent({ revision: 15 })
    const state = makeState({ snapshotRevision: 10 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("refetch_snapshot")
    expect(result.reason).toBe("revision_jump")
    expect(result.newRevision).toBe(15)
  })

  it("revision 连续（= expected+1）时返回 process", () => {
    const event = makeEvent({ revision: 11 })
    const state = makeState({ snapshotRevision: 10 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
    expect(result.newRevision).toBe(11)
  })

  it("revision === expected 时返回 skip + stale_revision（重复）", () => {
    const event = makeEvent({ revision: 10 })
    const state = makeState({ snapshotRevision: 10 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("skip")
    expect(result.reason).toBe("stale_revision")
  })

  it("revision < expected 时返回 skip + stale_revision（乱序）", () => {
    const event = makeEvent({ revision: 5 })
    const state = makeState({ snapshotRevision: 10 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("skip")
    expect(result.reason).toBe("stale_revision")
  })

  it("state.snapshotRevision 为 null 时跳过 revision 检查（向后兼容）", () => {
    const event = makeEvent({ revision: 999 })
    const state = makeState({ snapshotRevision: null })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
  })

  it("event.revision 为 null 时跳过 revision 检查（向后兼容）", () => {
    const event = makeEvent({ revision: null })
    const state = makeState({ snapshotRevision: 10 })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
  })
})

// ---------- Step 4: 正常处理 ----------

describe("checkSSEEvent Step 4: 正常处理", () => {
  it("所有检查通过时返回 process + ok + newEventId + newRevision", () => {
    const event = makeEvent({ event_id: 100, run_id: 50, revision: 20 })
    const state = makeState({
      runId: 50,
      latestEventId: 99,
      snapshotRevision: 19,
    })
    const result = checkSSEEvent(event, state)
    expect(result.apply).toBe("process")
    expect(result.reason).toBe("ok")
    expect(result.newEventId).toBe(100)
    expect(result.newRevision).toBe(20)
  })

  it("event_id 缺失时不返回 newEventId", () => {
    const event = makeEvent({ revision: 20 })
    const eventNoId = { ...event } as Partial<SSEEvent>
    delete (eventNoId as { event_id?: unknown }).event_id
    const state = makeState({ snapshotRevision: 19 })
    const result = checkSSEEvent(eventNoId as SSEEvent, state)
    expect(result.apply).toBe("process")
    expect(result.newEventId).toBeUndefined()
    expect(result.newRevision).toBe(20)
  })

  it("revision 缺失时 newRevision 回退到 state.snapshotRevision", () => {
    const event = makeEvent({ event_id: 100 })
    const eventNoRev = { ...event } as Partial<SSEEvent>
    delete (eventNoRev as { revision?: unknown }).revision
    const state = makeState({ latestEventId: 99, snapshotRevision: 19 })
    const result = checkSSEEvent(eventNoRev as SSEEvent, state)
    expect(result.apply).toBe("process")
    expect(result.newRevision).toBe(19)
  })

  it("snapshotRevision 也为 null 时 newRevision 为 undefined", () => {
    const event = makeEvent({ event_id: 100 })
    const eventNoRev = { ...event } as Partial<SSEEvent>
    delete (eventNoRev as { revision?: unknown }).revision
    const state = makeState({ latestEventId: 99, snapshotRevision: null })
    const result = checkSSEEvent(eventNoRev as SSEEvent, state)
    expect(result.apply).toBe("process")
    expect(result.newRevision).toBeUndefined()
  })
})

// ---------- createReducerState 辅助函数 ----------

describe("createReducerState 辅助函数", () => {
  it("默认参数全部为 null", () => {
    const state = createReducerState()
    expect(state).toEqual({
      runId: null,
      latestEventId: null,
      snapshotRevision: null,
    })
  })

  it("显式传参时构造对应状态", () => {
    const state = createReducerState(100, 99, 10)
    expect(state).toEqual({
      runId: 100,
      latestEventId: 99,
      snapshotRevision: 10,
    })
  })
})

// ---------- checkSSEEventLegacy 向后兼容适配 ----------

describe("checkSSEEventLegacy 向后兼容适配", () => {
  it("run_id 不符时返回 processed=false + reason=run_id_mismatch", () => {
    const event = makeEvent({ run_id: 200 })
    const ctx: DispatchContext = { activeRunId: 100, expectedRevision: null }
    const result = checkSSEEventLegacy(event, ctx)
    expect(result.processed).toBe(false)
    expect(result.reason).toBe("run_id_mismatch")
    expect(result.needsRevisionGap).toBeFalsy()
    expect(result.event).toBe(event)
  })

  it("revision 跳跃时返回 processed=false + needsRevisionGap=true", () => {
    const event = makeEvent({ revision: 15 })
    const ctx: DispatchContext = { activeRunId: null, expectedRevision: 10 }
    const result = checkSSEEventLegacy(event, ctx)
    expect(result.processed).toBe(false)
    expect(result.reason).toBe("revision_jump")
    expect(result.needsRevisionGap).toBe(true)
  })

  it("revision 重复时返回 reason=revision_duplicate（保留旧版语义）", () => {
    const event = makeEvent({ revision: 10 })
    const ctx: DispatchContext = { expectedRevision: 10 }
    const result = checkSSEEventLegacy(event, ctx)
    expect(result.processed).toBe(false)
    expect(result.reason).toBe("revision_duplicate")
  })

  it("revision 乱序时返回 reason=revision_out_of_order（保留旧版语义）", () => {
    const event = makeEvent({ revision: 5 })
    const ctx: DispatchContext = { expectedRevision: 10 }
    const result = checkSSEEventLegacy(event, ctx)
    expect(result.processed).toBe(false)
    expect(result.reason).toBe("revision_out_of_order")
  })

  it("正常处理时返回 processed=true", () => {
    const event = makeEvent({ run_id: 100, event_id: 5, revision: 11 })
    const ctx: DispatchContext = { activeRunId: 100, expectedRevision: 10, latestEventId: 4 }
    const result = checkSSEEventLegacy(event, ctx)
    expect(result.processed).toBe(true)
    expect(result.event).toBe(event)
  })

  it("ctx.latestEventId 为 null 时跳过去重检查（向后兼容）", () => {
    const event = makeEvent({ event_id: 1 })
    const ctx: DispatchContext = { latestEventId: null }
    const result = checkSSEEventLegacy(event, ctx)
    expect(result.processed).toBe(true)
  })
})
