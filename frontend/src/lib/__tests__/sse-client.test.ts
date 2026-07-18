/**
 * Task 1.11 / Task 6.2.1: SSE 客户端同步规则测试
 *
 * 覆盖场景（对齐 SubTask 1.11.1 / 1.11.2 / 6.2.4）：
 * 1. dispatch 对 run_id 不符的事件返回 null（丢弃）
 * 2. dispatch 对 run_id 一致的事件正常处理
 * 3. dispatch 对 revision 跳跃的事件触发 onRevisionGap 回调
 * 4. dispatch 对 revision 连续的事件正常处理（reducer 侧更新 expectedRevision）
 * 5. dispatch 对无 run_id / revision 的事件（旧版本兼容）正常处理
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  WorkflowSSEClient,
  checkSSEEvent,
  type DispatchContext,
  type SSEHandlers,
} from '@/lib/sse-client'
import type { SSEEvent } from '@/lib/workflow-events'

// ---------- 辅助函数 ----------

function makeEvent(overrides: Partial<SSEEvent> = {}): SSEEvent {
  return {
    event_id: 1,
    event_type: 'node.start',
    node: 'ocr',
    ts: '2026-07-17T10:00:00Z',
    ...overrides,
  }
}

function makeMessageEvent(data: SSEEvent): MessageEvent {
  return new MessageEvent('message', { data: JSON.stringify(data) })
}

function makeHandlers(overrides: Partial<SSEHandlers> = {}): SSEHandlers {
  return {
    onEvent: vi.fn(),
    onConnect: vi.fn(),
    onReconnect: vi.fn(),
    onFatalError: vi.fn(),
    getActiveRunId: vi.fn(() => null),
    getExpectedRevision: vi.fn(() => null),
    onRevisionGap: vi.fn(),
    ...overrides,
  }
}

// ---------- 纯函数 checkSSEEvent 测试 ----------

describe('checkSSEEvent (纯函数)', () => {
  it('run_id 不符时返回 processed=false + run_id_mismatch', () => {
    const event = makeEvent({ run_id: 200 })
    const ctx: DispatchContext = { activeRunId: 100, expectedRevision: null }
    const result = checkSSEEvent(event, ctx)
    expect(result.processed).toBe(false)
    expect(result.reason).toBe('run_id_mismatch')
    expect(result.needsRevisionGap).toBeFalsy()
  })

  it('run_id 一致时返回 processed=true', () => {
    const event = makeEvent({ run_id: 100 })
    const ctx: DispatchContext = { activeRunId: 100, expectedRevision: null }
    const result = checkSSEEvent(event, ctx)
    expect(result.processed).toBe(true)
    expect(result.reason).toBeUndefined()
  })

  it('revision 跳跃时返回 processed=false + revision_jump + needsRevisionGap', () => {
    const event = makeEvent({ revision: 15 })
    const ctx: DispatchContext = { activeRunId: null, expectedRevision: 10 }
    const result = checkSSEEvent(event, ctx)
    expect(result.processed).toBe(false)
    expect(result.reason).toBe('revision_jump')
    expect(result.needsRevisionGap).toBe(true)
  })

  it('revision 连续（expected+1）时返回 processed=true', () => {
    const event = makeEvent({ revision: 11 })
    const ctx: DispatchContext = { activeRunId: null, expectedRevision: 10 }
    const result = checkSSEEvent(event, ctx)
    expect(result.processed).toBe(true)
  })

  it('revision 重复（=== expected）时返回 revision_duplicate', () => {
    const event = makeEvent({ revision: 10 })
    const ctx: DispatchContext = { activeRunId: null, expectedRevision: 10 }
    const result = checkSSEEvent(event, ctx)
    expect(result.processed).toBe(false)
    expect(result.reason).toBe('revision_duplicate')
  })

  it('revision 乱序（< expected）时返回 revision_out_of_order', () => {
    const event = makeEvent({ revision: 5 })
    const ctx: DispatchContext = { activeRunId: null, expectedRevision: 10 }
    const result = checkSSEEvent(event, ctx)
    expect(result.processed).toBe(false)
    expect(result.reason).toBe('revision_out_of_order')
  })

  it('无 run_id / revision（旧版本后端）时返回 processed=true（向后兼容）', () => {
    const event = makeEvent()
    const ctx: DispatchContext = { activeRunId: 100, expectedRevision: 10 }
    const result = checkSSEEvent(event, ctx)
    expect(result.processed).toBe(true)
  })

  it('activeRunId 为 null 时跳过 run_id 检查（向后兼容）', () => {
    const event = makeEvent({ run_id: 999 })
    const ctx: DispatchContext = { activeRunId: null, expectedRevision: null }
    const result = checkSSEEvent(event, ctx)
    expect(result.processed).toBe(true)
  })

  it('expectedRevision 为 null 时跳过 revision 检查（向后兼容）', () => {
    const event = makeEvent({ revision: 999 })
    const ctx: DispatchContext = { activeRunId: null, expectedRevision: null }
    const result = checkSSEEvent(event, ctx)
    expect(result.processed).toBe(true)
  })
})

// ---------- WorkflowSSEClient.dispatch 集成测试 ----------

describe('WorkflowSSEClient.dispatch (集成)', () => {
  it('测试 1: dispatch 对 run_id 不符的事件返回 null（丢弃）', () => {
    const handlers = makeHandlers({ getActiveRunId: () => 100 })
    const client = new WorkflowSSEClient('about:blank', handlers, undefined, 0)
    const event = makeEvent({ event_id: 5, run_id: 200 })
    const result = client.dispatch(makeMessageEvent(event))
    expect(result).toBeNull()
    expect(handlers.onEvent).not.toHaveBeenCalled()
  })

  it('测试 2: dispatch 对 run_id 一致的事件正常处理', () => {
    const handlers = makeHandlers({ getActiveRunId: () => 100 })
    const client = new WorkflowSSEClient('about:blank', handlers, undefined, 0)
    const event = makeEvent({ event_id: 5, run_id: 100 })
    const result = client.dispatch(makeMessageEvent(event))
    expect(result).not.toBeNull()
    expect(result?.event_id).toBe(5)
    expect(handlers.onEvent).toHaveBeenCalledWith(event)
  })

  it('测试 3: dispatch 对 revision 跳跃的事件触发 onRevisionGap 回调', () => {
    const handlers = makeHandlers({
      getExpectedRevision: () => 10,
      onRevisionGap: vi.fn(),
    })
    const client = new WorkflowSSEClient('about:blank', handlers, undefined, 0)
    const event = makeEvent({ event_id: 5, revision: 15 })
    const result = client.dispatch(makeMessageEvent(event))
    expect(result).toBeNull()
    expect(handlers.onEvent).not.toHaveBeenCalled()
    expect(handlers.onRevisionGap).toHaveBeenCalledWith(event, 10, 15)
  })

  it('测试 4: dispatch 对 revision 连续的事件正常处理（reducer 侧更新 expectedRevision）', () => {
    const handlers = makeHandlers({ getExpectedRevision: () => 10 })
    const client = new WorkflowSSEClient('about:blank', handlers, undefined, 0)
    const event = makeEvent({ event_id: 5, revision: 11 })
    const result = client.dispatch(makeMessageEvent(event))
    expect(result).not.toBeNull()
    expect(result?.event_id).toBe(5)
    expect(handlers.onEvent).toHaveBeenCalledWith(event)
    // 注：expectedRevision 的实际更新由 case-store.ts 的 applySSEEvent reducer 负责
    // （set { snapshotRevision: event.revision }），此处仅验证 dispatch 正常返回事件
  })

  it('测试 5: dispatch 对无 run_id / revision 的事件（旧版本兼容）正常处理', () => {
    const handlers = makeHandlers({
      getActiveRunId: () => 100,
      getExpectedRevision: () => 10,
    })
    const client = new WorkflowSSEClient('about:blank', handlers, undefined, 0)
    const event = makeEvent({ event_id: 5 }) // 无 run_id / revision
    const result = client.dispatch(makeMessageEvent(event))
    expect(result).not.toBeNull()
    expect(result?.event_id).toBe(5)
    expect(handlers.onEvent).toHaveBeenCalledWith(event)
  })

  it('dispatch 对 revision 重复的事件丢弃且不触发 onRevisionGap', () => {
    const handlers = makeHandlers({
      getExpectedRevision: () => 10,
      onRevisionGap: vi.fn(),
    })
    const client = new WorkflowSSEClient('about:blank', handlers, undefined, 0)
    const event = makeEvent({ event_id: 5, revision: 10 })
    const result = client.dispatch(makeMessageEvent(event))
    expect(result).toBeNull()
    expect(handlers.onEvent).not.toHaveBeenCalled()
    expect(handlers.onRevisionGap).not.toHaveBeenCalled()
  })

  it('dispatch 对 JSON 解析失败的事件返回 null', () => {
    const handlers = makeHandlers()
    const client = new WorkflowSSEClient('about:blank', handlers, undefined, 0)
    const result = client.dispatch(new MessageEvent('message', { data: 'not-json' }))
    expect(result).toBeNull()
    expect(handlers.onEvent).not.toHaveBeenCalled()
  })
})

// ---------- 重连和 fatal error 测试（SubTask 6.2.4）----------

/**
 * Mock EventSource：模拟 SSE 连接生命周期
 * jsdom 不内置 EventSource，需手动 stub
 */
class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onopen: ((ev: Event) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  private listeners: Map<string, Array<(ev: MessageEvent) => void>> = new Map()
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  addEventListener(type: string, handler: (ev: MessageEvent) => void): void {
    if (!this.listeners.has(type)) this.listeners.set(type, [])
    this.listeners.get(type)!.push(handler)
  }
  close(): void {
    this.closed = true
  }
  /** 模拟连接错误，触发 onerror 回调 */
  simulateError(): void {
    this.onerror?.(new Event('error'))
  }
  /** 模拟连接成功，触发 onopen 回调 */
  simulateOpen(): void {
    this.onopen?.(new Event('open'))
  }
}

describe('WorkflowSSEClient 重连和 fatal error（SubTask 6.2.4）', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('连接错误后触发 onReconnect 回调（第 1 次重连）', () => {
    vi.useFakeTimers()
    const onReconnect = vi.fn()
    const onFatalError = vi.fn()
    const handlers = makeHandlers({ onReconnect, onFatalError })
    const client = new WorkflowSSEClient('http://test/sse', handlers, undefined, 0)
    client.connect()

    // 模拟连接错误
    MockEventSource.instances[0].simulateError()

    expect(onReconnect).toHaveBeenCalledTimes(1)
    expect(onReconnect).toHaveBeenCalledWith(1, 5)
    expect(onFatalError).not.toHaveBeenCalled()

    client.close()
  })

  it('达到最大重连次数后触发 onFatalError', () => {
    vi.useFakeTimers()
    const onReconnect = vi.fn()
    const onFatalError = vi.fn()
    const handlers = makeHandlers({ onReconnect, onFatalError })
    const client = new WorkflowSSEClient('http://test/sse', handlers, undefined, 0)
    client.connect()

    // 模拟 5 次连接错误 + 重连定时器推进（maxReconnect=5）
    for (let i = 0; i < 5; i++) {
      const es = MockEventSource.instances[MockEventSource.instances.length - 1]
      es.simulateError()
      // 推进重连定时器（指数退避：1s, 2s, 4s, 8s, 16s）
      vi.advanceTimersByTime(20000)
    }

    // 第 6 次错误触发 onFatalError（reconnectAttempts 已达 maxReconnect）
    const lastEs = MockEventSource.instances[MockEventSource.instances.length - 1]
    lastEs.simulateError()

    expect(onReconnect).toHaveBeenCalledTimes(5)
    expect(onFatalError).toHaveBeenCalledTimes(1)
    expect(onFatalError).toHaveBeenCalledWith('SSE 连接中断，已达最大重连次数')

    client.close()
  })

  it('close() 后不再重连', () => {
    vi.useFakeTimers()
    const onReconnect = vi.fn()
    const handlers = makeHandlers({ onReconnect })
    const client = new WorkflowSSEClient('http://test/sse', handlers, undefined, 0)
    client.connect()

    // 主动关闭
    client.close()

    // 模拟错误
    MockEventSource.instances[0].simulateError()

    expect(onReconnect).not.toHaveBeenCalled()
  })

  it('重连成功后重置 reconnectAttempts', () => {
    vi.useFakeTimers()
    const onConnect = vi.fn()
    const onReconnect = vi.fn()
    const handlers = makeHandlers({ onConnect, onReconnect })
    const client = new WorkflowSSEClient('http://test/sse', handlers, undefined, 0)
    client.connect()

    // 第 1 次错误 → 重连
    MockEventSource.instances[0].simulateError()
    expect(onReconnect).toHaveBeenCalledWith(1, 5)
    vi.advanceTimersByTime(2000) // 推进重连定时器 → connect()

    // 第 2 个 EventSource 连接成功 → 重置 reconnectAttempts
    MockEventSource.instances[1].simulateOpen()
    expect(onConnect).toHaveBeenCalled()

    // 再次错误应从 attempt=1 重新开始（证明已重置）
    MockEventSource.instances[1].simulateError()
    expect(onReconnect).toHaveBeenLastCalledWith(1, 5)

    client.close()
  })
})
