// 工作流事件 reducer 纯函数（对齐 spec.md Requirement: SSE Sync Rules）
// Task 3.5.4：从 sse-client.ts 提取为独立模块作为单一来源
//
// 四步检查：
//   1. run_id 检查（不符则 skip）
//   2. event_id 去重（已处理则 skip）
//   3. revision 检查（跳跃则 refetch_snapshot；重复/乱序则 skip）
//   4. 返回 process
//
// 向后兼容：
//   - run_id 不存在或 activeRunId 为 null → 跳过 run_id 检查
//   - revision 不存在或 expectedRevision 为 null → 跳过 revision 检查
//   - latestEventId 为 null → 跳过 event_id 去重检查

import type { SSEEvent } from "./workflow-events"

// ---------- reducer 状态 ----------

export interface ReducerState {
  /** 当前活跃的 run_id；null 表示未设置，跳过 run_id 检查（向后兼容） */
  runId: number | null
  /** 已处理的最新 event_id；null 表示尚未处理任何事件，跳过去重检查 */
  latestEventId: number | null
  /** 本地最新已处理 revision；null 表示尚未处理任何 revision 事件，跳过 revision 检查 */
  snapshotRevision: number | null
}

// ---------- reducer 结果 ----------

export type ReducerAction = "process" | "skip" | "refetch_snapshot"

export interface ReducerResult {
  /** 处理动作：process=正常处理 / skip=丢弃 / refetch_snapshot=触发重新获取权威快照 */
  apply: ReducerAction
  /** 决策原因（便于调试与日志） */
  reason: string
  /** 处理成功时携带新的 event_id（供调用方更新 latestEventId） */
  newEventId?: number
  /** 处理成功时携带新的 revision（供调用方更新 snapshotRevision） */
  newRevision?: number
}

// ---------- 输入构造函数 ----------

/**
 * 从分散字段构造 reducer 状态（便于旧调用方迁移）。
 */
export function createReducerState(
  runId: number | null = null,
  latestEventId: number | null = null,
  snapshotRevision: number | null = null,
): ReducerState {
  return { runId, latestEventId, snapshotRevision }
}

// ---------- 纯函数：四步检查 ----------

/**
 * SSE 事件同步规则检查（纯函数）。
 *
 * @param event 待检查的 SSE 事件
 * @param state 当前 reducer 状态
 * @returns 处理决策与可选的新游标
 */
export function checkSSEEvent(event: SSEEvent, state: ReducerState): ReducerResult {
  // Step 1: run_id 检查（向后兼容：run_id 不存在或 state.runId 未设置时跳过）
  if (
    typeof event.run_id === "number" &&
    state.runId != null &&
    event.run_id !== state.runId
  ) {
    return { apply: "skip", reason: "run_id_mismatch" }
  }

  // Step 2: event_id 去重（向后兼容：event_id 不存在或 latestEventId 未设置时跳过）
  if (
    typeof event.event_id === "number" &&
    state.latestEventId != null &&
    event.event_id <= state.latestEventId
  ) {
    return { apply: "skip", reason: "duplicate_event_id" }
  }

  // Step 3: revision 检查（向后兼容：revision 不存在或 snapshotRevision 未设置时跳过）
  if (typeof event.revision === "number" && state.snapshotRevision != null) {
    const expected = state.snapshotRevision
    if (event.revision > expected + 1) {
      // revision 跳跃 → 触发 snapshot refetch
      return {
        apply: "refetch_snapshot",
        reason: "revision_jump",
        newRevision: event.revision,
      }
    }
    if (event.revision <= expected) {
      // 重复或乱序事件，丢弃
      return { apply: "skip", reason: "stale_revision" }
    }
    // event.revision === expected + 1，连续，正常处理
  }

  // Step 4: 处理
  return {
    apply: "process",
    reason: "ok",
    newEventId: typeof event.event_id === "number" ? event.event_id : undefined,
    newRevision:
      typeof event.revision === "number" ? event.revision : state.snapshotRevision ?? undefined,
  }
}

// ---------- 向后兼容类型别名（对齐旧 sse-client.ts API） ----------
//
// 以下类型别名与导出便于 sse-client.ts 将 checkSSEEvent 重定向到本模块，
// 不破坏现有导入（DispatchContext / DispatchResult / DispatchDropReason）。

/** 旧版 dispatch 上下文（向后兼容别名） */
export type DispatchContext = {
  activeRunId?: number | null
  expectedRevision?: number | null
  latestEventId?: number | null
}

/** 旧版 dispatch 丢弃原因（向后兼容别名） */
export type DispatchDropReason =
  | "run_id_mismatch"
  | "revision_jump"
  | "revision_duplicate"
  | "revision_out_of_order"
  | "duplicate_event_id"
  | "stale_revision"

/** 旧版 dispatch 结果（向后兼容别名） */
export interface DispatchResult {
  /** 是否正常处理（true=传递给 reducer，false=丢弃） */
  processed: boolean
  /** 丢弃原因（仅在 processed=false 时存在） */
  reason?: DispatchDropReason
  /** 是否需要触发 onRevisionGap 回调（revision 跳跃时为 true） */
  needsRevisionGap?: boolean
  /** 原始事件 */
  event: SSEEvent
}

/**
 * 旧版 dispatch 接口（向后兼容）。
 *
 * 与新版 `checkSSEEvent` 的差异：
 * - 返回 `processed: boolean` 而非 `apply: ReducerAction`
 * - revision 重复区分 `revision_duplicate` / `revision_out_of_order`（新版统一为 `stale_revision`）
 *
 * 新代码应直接使用 `checkSSEEvent`。此函数保留用于 sse-client.ts 内部向后兼容。
 */
export function checkSSEEventLegacy(event: SSEEvent, ctx: DispatchContext): DispatchResult {
  const state: ReducerState = {
    runId: ctx.activeRunId ?? null,
    latestEventId: ctx.latestEventId ?? null,
    snapshotRevision: ctx.expectedRevision ?? null,
  }
  const result = checkSSEEvent(event, state)

  if (result.apply === "process") {
    return { processed: true, event }
  }
  if (result.apply === "refetch_snapshot") {
    return { processed: false, reason: "revision_jump", needsRevisionGap: true, event }
  }
  // skip：映射到旧版原因
  let reason: DispatchDropReason
  switch (result.reason) {
    case "run_id_mismatch":
      reason = "run_id_mismatch"
      break
    case "duplicate_event_id":
      reason = "duplicate_event_id"
      break
    case "stale_revision":
      // 区分重复 vs 乱序（保留旧版语义）
      if (
        typeof event.revision === "number" &&
        ctx.expectedRevision != null &&
        event.revision === ctx.expectedRevision
      ) {
        reason = "revision_duplicate"
      } else {
        reason = "revision_out_of_order"
      }
      break
    default:
      reason = "revision_out_of_order"
  }
  return { processed: false, reason, event }
}
