// SSE 客户端封装：
// - FetchStreamSSEClient（主）：fetch + ReadableStream + Authorization Header + AbortController + 心跳超时（Task 3.7.2）
// - WorkflowSSEClient（兼容回退）：EventSource + query token + 自动重连（Task 1.11）
// - createSSEClient 工厂：根据运行环境自动选择实现（Task 3.7.3）
// 参考 spec 第 6.3 节 + Requirement: Frontend SSE Client
import type { SSEEvent, EventType } from "@/lib/workflow-events"
// Task 3.5.4：checkSSEEvent 已提取为独立模块 workflow-event-reducer.ts 作为单一来源
import {
  checkSSEEventLegacy,
  type DispatchContext,
  type DispatchResult,
  type DispatchDropReason,
} from "@/lib/workflow-event-reducer"

// 向后兼容重导出：旧代码 `import { checkSSEEvent } from "@/lib/sse-client"` 继续工作
export {
  // 旧 API（ctx: DispatchContext，返回 DispatchResult.processed）
  checkSSEEventLegacy as checkSSEEvent,
  type DispatchContext,
  type DispatchResult,
  type DispatchDropReason,
  // 新 API（state: ReducerState，返回 ReducerResult.apply）
  checkSSEEvent as checkSSEEventReducer,
  type ReducerState,
  type ReducerResult,
  type ReducerAction,
} from "@/lib/workflow-event-reducer"

export interface SSEHandlers {
  /** 收到任意事件时调用 */
  onEvent: (event: SSEEvent) => void
  /** 连接成功时调用 */
  onConnect?: () => void
  /** 开始重连时调用，传入当前重连次数与最大次数 */
  onReconnect?: (attempt: number, max: number) => void
  /** 达到最大重连次数后调用 */
  onFatalError?: (message: string) => void
  /**
   * 获取当前活跃的 run_id（用于事件过滤）。
   * 返回 null 表示尚未设置，跳过 run_id 检查（向后兼容旧版本后端）。
   */
  getActiveRunId?: () => number | null
  /**
   * 获取当前期望的下一个 revision（用于跳跃检测）。
   * 返回 null 表示尚未设置，跳过 revision 检查（向后兼容旧版本后端）。
   */
  getExpectedRevision?: () => number | null
  /**
   * revision 跳跃时调用（事件将被丢弃，调用方应触发 getSnapshot() 重新获取权威快照）。
   * @param event 触发跳跃的事件
   * @param expected 本地期望的 revision
   * @param got 事件中携带的 revision
   */
  onRevisionGap?: (event: SSEEvent, expected: number, got: number) => void | Promise<void>
}

/** 需要监听的 SSE 事件类型列表（EventSource 显式 addEventListener 用） */
const EVENT_TYPES: EventType[] = [
  "workflow.start",
  "workflow.pause_requested",
  "workflow.paused",
  "workflow.resumed",
  "workflow.cancelled",
  "workflow.complete",
  "workflow.error",
  "workflow.waiting_review",
  "node.start",
  "node.progress",
  "node.complete",
  "node.error",
  "complaint.token",
  "complaint.done",
  "review.interrupt",
  "review.resumed",
  "review.skipped",
  // Task 3.5：业务阶段级事件类型（FetchStreamSSEClient 通过 message 统一接收，
  // EventSource 由于不支持 Authorization Header，主要用于旧链路兼容，仅监听旧事件类型）
]

export class WorkflowSSEClient {
  private eventSource: EventSource | null = null
  private lastEventId = 0
  private reconnectAttempts = 0
  private readonly maxReconnect = 5
  private readonly baseDelay = 1000
  private closed = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  constructor(
    private streamUrl: string,
    private handlers: SSEHandlers,
    /** JWT access token，通过 query parameter 传递（浏览器 EventSource 不支持自定义 header） */
    private token?: string,
    initialLastEventId = 0,
  ) {
    this.lastEventId = initialLastEventId
  }

  /** 建立 SSE 连接，注册所有事件类型监听器 */
  connect(): void {
    this.closed = false
    const separator = this.streamUrl.includes("?") ? "&" : "?"
    const params = new URLSearchParams()
    params.set("last_event_id", String(this.lastEventId))
    if (this.token) {
      params.set("token", this.token)
    }
    const url = `${this.streamUrl}${separator}${params.toString()}`
    this.eventSource = new EventSource(url, { withCredentials: true })

    EVENT_TYPES.forEach((type) => {
      this.eventSource?.addEventListener(type, (e) => this.dispatch(e as MessageEvent))
    })

    this.eventSource.onopen = () => {
      this.reconnectAttempts = 0
      this.handlers.onConnect?.()
    }

    this.eventSource.onerror = () => this.handleDisconnect()
  }

  /**
   * 解析事件，执行 run_id / revision 同步规则检查，更新 lastEventId，调用 handlers.onEvent。
   *
   * Task 1.11 升级：
   * - 新增 run_id 检查：与 getActiveRunId() 不符则丢弃
   * - 新增 revision 检查：跳跃触发 onRevisionGap，重复/乱序丢弃
   * - 向后兼容：run_id / revision 不存在时跳过检查
   *
   * @returns 正常处理时返回事件本身，丢弃时返回 null
   */
  dispatch(e: MessageEvent): SSEEvent | null {
    let data: SSEEvent
    try {
      data = JSON.parse(e.data) as SSEEvent
    } catch {
      return null
    }

    // 构造 dispatch 上下文（从 handlers 闭包动态读取，保证最新值）
    const ctx: DispatchContext = {
      activeRunId: this.handlers.getActiveRunId?.() ?? null,
      expectedRevision: this.handlers.getExpectedRevision?.() ?? null,
    }

    // 执行 run_id / revision 检查（委托 workflow-event-reducer 模块）
    const result = checkSSEEventLegacy(data, ctx)
    if (!result.processed) {
      // revision 跳跃时触发 onRevisionGap 回调（由调用方实现 getSnapshot 重新获取）
      if (result.needsRevisionGap) {
        const expected = ctx.expectedRevision ?? 0
        const got = typeof data.revision === "number" ? data.revision : 0
        void this.handlers.onRevisionGap?.(data, expected, got)
      }
      return null
    }

    if (typeof data.event_id === "number") {
      this.lastEventId = Math.max(this.lastEventId, data.event_id)
    }
    this.handlers.onEvent(data)
    if (
      data.event_type === "workflow.complete" ||
      data.event_type === "workflow.error" ||
      data.event_type === "workflow.waiting_review" ||
      data.event_type === "workflow.paused" ||
      data.event_type === "workflow.cancelled"
    ) {
      this.close()
    }
    return data
  }

  /** 指数退避重连，最多 maxReconnect 次 */
  private handleDisconnect(): void {
    this.eventSource?.close()
    this.eventSource = null

    if (this.closed) return

    if (this.reconnectAttempts >= this.maxReconnect) {
      this.handlers.onFatalError?.("SSE 连接中断，已达最大重连次数")
      return
    }

    this.reconnectAttempts += 1
    const attempt = this.reconnectAttempts
    this.handlers.onReconnect?.(attempt, this.maxReconnect)

    const delay = this.baseDelay * Math.pow(2, attempt - 1)
    this.reconnectTimer = setTimeout(() => {
      if (!this.closed) this.connect()
    }, delay)
  }

  /** 主动关闭连接，不再重连 */
  close(): void {
    this.closed = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.eventSource?.close()
    this.eventSource = null
  }
}

/**
 * EventSource 兼容回退实现别名（对齐 spec Task 3.7.3）。
 * 旧浏览器不支持 `fetch` + `ReadableStream` 时使用。
 */
export const EventSourceSSEClient = WorkflowSSEClient

// ============================================================================
// Task 3.7.2: FetchStreamSSEClient（fetch + ReadableStream 实现）
// ============================================================================

export interface FetchStreamOptions {
  /** 完整的 SSE 端点 URL（可含 ticket query 参数） */
  url: string
  /** SSE Ticket（短期鉴权票据，由 createRun / submitIntervention / retryRun 返回） */
  token?: string
  /** JWT access token（备用鉴权；FetchStream 支持时优先使用 Authorization Header） */
  accessToken?: string
  /** 断线续传：上次处理的最后一个 event_id */
  lastEventId?: number
  /** 收到任意事件时调用 */
  onEvent: (event: SSEEvent) => void
  /** 连接成功时调用 */
  onConnect?: () => void
  /** 连接断开时调用，传入原因（stream_end / aborted / heartbeat_timeout / fetch_error） */
  onDisconnect?: (reason: string) => void
  /** 连接错误时调用 */
  onError?: (error: Error) => void
  /** 心跳超时（毫秒），默认 30000；超过此时间无任何事件则主动断开并触发重连 */
  heartbeatTimeoutMs?: number
  /** 获取当前活跃 run_id（用于事件过滤，与 SSEHandlers 同义） */
  getActiveRunId?: () => number | null
  /** 获取当前期望 revision（用于跳跃检测） */
  getExpectedRevision?: () => number | null
  /** revision 跳跃时触发（调用方应触发 getSnapshot() 重新获取权威快照） */
  onRevisionGap?: () => void
}

/**
 * 基于 `fetch` + `ReadableStream` 的 SSE 客户端（Task 3.7.2）。
 *
 * 优势（相对 EventSource）：
 * - 支持 `Authorization` Header（避免 token 暴露在 URL/日志/Referer）
 * - 支持 `Last-Event-ID` Header（断线续传不依赖 query parameter）
 * - 支持 `AbortController`（主动中断，不依赖 EventSource.close 兼容性）
 * - 支持心跳超时检测（无事件超过 N 秒主动断开触发重连）
 *
 * 局限：
 * - 浏览器需支持 `fetch` + `ReadableStream`（IE 不支持，Safari<15 部分支持）
 * - 不内置自动重连（由调用方在 onDisconnect 中决定）
 */
export class FetchStreamSSEClient {
  private controller: AbortController | null = null
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null
  private readonly options: Required<Pick<FetchStreamOptions, "heartbeatTimeoutMs">> &
    Omit<FetchStreamOptions, "heartbeatTimeoutMs">
  private isConnecting = false
  private isClosed = false

  constructor(options: FetchStreamOptions) {
    this.options = {
      heartbeatTimeoutMs: 30000,
      ...options,
    }
  }

  /** 建立 SSE 连接（异步，连接成功后 resolve，错误 reject） */
  async connect(): Promise<void> {
    if (this.isConnecting || this.isClosed) return
    this.isConnecting = true

    this.controller = new AbortController()
    const headers: Record<string, string> = {
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    }
    // 优先使用 accessToken（JWT），其次使用 token（SSE Ticket）
    // spec.md Task 3.7.2 推荐 Authorization Header 模式
    if (this.options.accessToken) {
      headers["Authorization"] = `Bearer ${this.options.accessToken}`
    }
    if (typeof this.options.lastEventId === "number" && this.options.lastEventId > 0) {
      headers["Last-Event-ID"] = String(this.options.lastEventId)
    }

    try {
      const response = await fetch(this.options.url, {
        method: "GET",
        headers,
        signal: this.controller.signal,
        credentials: "same-origin",
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      if (!response.body) {
        throw new Error("Response body is empty (ReadableStream not supported)")
      }

      this.options.onConnect?.()
      this.resetHeartbeat()

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      // 持续读取流，按 \n\n 分割 SSE 事件块
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // 收到任意数据（含服务端 `: heartbeat` 注释、未成块的分片）即视为连接存活，
        // 立即重置心跳超时。否则长耗时节点（OCR / LLM 生成）在 heartbeatTimeoutMs
        // 内不产出「可解析事件」时会误判超时 → 断开重连，导致连接状态反复闪烁。
        this.resetHeartbeat()

        // SSE 事件块以空行（\n\n）分隔
        let separatorIdx: number
        while ((separatorIdx = buffer.indexOf("\n\n")) !== -1) {
          const rawEvent = buffer.slice(0, separatorIdx)
          buffer = buffer.slice(separatorIdx + 2)

          const event = this.parseEvent(rawEvent)
          if (event) {
            this.handleEvent(event)
          }
        }
      }

      this.options.onDisconnect?.("stream_end")
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        this.options.onDisconnect?.("aborted")
      } else if (err instanceof Error) {
        this.options.onError?.(err)
        this.options.onDisconnect?.("fetch_error")
      } else {
        this.options.onError?.(new Error(String(err)))
        this.options.onDisconnect?.("fetch_error")
      }
    } finally {
      this.isConnecting = false
      this.clearHeartbeat()
    }
  }

  /** 主动断开连接 */
  disconnect(): void {
    this.isClosed = true
    if (this.controller) {
      this.controller.abort()
      this.controller = null
    }
    this.clearHeartbeat()
  }

  /** 兼容 WorkflowSSEClient 接口 */
  close(): void {
    this.disconnect()
  }

  /** 解析 SSE 事件块（按 SSE 协议：event: / data: / id: 字段） */
  private parseEvent(raw: string): SSEEvent | null {
    const lines = raw.split("\n")
    let eventType = "message"
    let data = ""
    let eventId = ""

    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim()
      } else if (line.startsWith("data:")) {
        // data: 字段可能多行拼接，每行去掉前缀 "data:" 后 trim
        data += (data ? "\n" : "") + line.slice(5).trimStart()
      } else if (line.startsWith("id:")) {
        eventId = line.slice(3).trim()
      }
      // 忽略注释行（: heartbeat）与其他字段
    }

    if (!data) return null

    try {
      const payload = JSON.parse(data) as Record<string, unknown>
      // 兼容两种格式：
      //   1. 后端按 spec 信封返回 {event_id, event_type, run_id, revision, occurred_at, payload}
      //   2. 旧版后端事件对象本身即为 payload（无嵌套 payload 字段）
      const innerPayload = (payload.payload as Record<string, unknown> | undefined) ?? payload
      const event: SSEEvent = {
        event_id:
          eventId && eventId.length > 0
            ? Number(eventId)
            : typeof payload.event_id === "number"
              ? payload.event_id
              : 0,
        event_type: (eventType !== "message"
          ? eventType
          : (payload.event_type as string | undefined) ?? "message") as SSEEvent["event_type"],
        run_id: typeof payload.run_id === "number" ? payload.run_id : null,
        thread_id: typeof payload.thread_id === "string" ? payload.thread_id : undefined,
        revision: typeof payload.revision === "number" ? payload.revision : null,
        occurred_at: typeof payload.occurred_at === "string" ? payload.occurred_at : undefined,
        timestamp: typeof payload.timestamp === "string" ? payload.timestamp : undefined,
        // 业务字段：优先展开 payload.payload，否则展开整个 payload（旧格式）
        ...(innerPayload as object),
      }
      // 必须有 event_type 才返回（避免空事件）
      if (!event.event_type) return null
      return event
    } catch {
      return null
    }
  }

  /** 处理单个事件：run_id / revision 检查（与 WorkflowSSEClient 一致） */
  private handleEvent(event: SSEEvent): void {
    // run_id 检查：与当前活跃 run_id 不符则丢弃
    if (this.options.getActiveRunId && typeof event.run_id === "number") {
      const activeRunId = this.options.getActiveRunId()
      if (activeRunId != null && event.run_id !== activeRunId) {
        return
      }
    }

    // revision 检查：跳跃触发 onRevisionGap 并丢弃当前事件
    if (
      this.options.getExpectedRevision &&
      typeof event.revision === "number" &&
      this.options.onRevisionGap
    ) {
      const expected = this.options.getExpectedRevision()
      if (expected != null && event.revision > expected + 1) {
        this.options.onRevisionGap()
        return
      }
    }

    this.options.onEvent(event)
  }

  private resetHeartbeat(): void {
    this.clearHeartbeat()
    this.heartbeatTimer = setTimeout(() => {
      this.controller?.abort()
      this.options.onDisconnect?.("heartbeat_timeout")
    }, this.options.heartbeatTimeoutMs)
  }

  private clearHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearTimeout(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }
}

// ============================================================================
// Task 3.7.3: SSEClient 统一接口 + createSSEClient 工厂
// ============================================================================

/** SSE 客户端统一接口（WorkflowSSEClient 与 FetchStreamSSEClient 均实现） */
export interface SSEClient {
  connect(): void | Promise<void>
  disconnect?(): void
  close(): void
}

/** createSSEClient 入参（合并两种实现的配置） */
export interface SSEClientOptions {
  /** 完整 SSE 端点 URL */
  url: string
  /** SSE Ticket（短期票据，由创建运行/介入提交/重试 API 返回） */
  token?: string
  /** JWT access token（FetchStream 优先用 Authorization Header） */
  accessToken?: string
  /** 断线续传 last_event_id */
  lastEventId?: number
  /** 心跳超时（FetchStream 用，默认 30s） */
  heartbeatTimeoutMs?: number
  /** 事件回调 */
  onEvent: (event: SSEEvent) => void
  onConnect?: () => void
  onDisconnect?: (reason: string) => void
  onError?: (error: Error) => void
  /** EventSource 重连回调（FetchStream 不内置重连，调用方自行实现） */
  onReconnect?: (attempt: number, max: number) => void
  onFatalError?: (message: string) => void
  /** SSE 同步规则回调 */
  getActiveRunId?: () => number | null
  getExpectedRevision?: () => number | null
  onRevisionGap?: (event: SSEEvent, expected: number, got: number) => void | Promise<void>
}

/**
 * 创建 SSE 客户端实例（Task 3.7.3 工厂函数）。
 *
 * 选择策略：
 * - 优先 FetchStreamSSEClient（支持 Authorization Header + AbortController + 心跳）
 * - 回退 WorkflowSSEClient（EventSource，旧浏览器或 ReadableStream 不可用时）
 *
 * 注意：FetchStream 不内置自动重连；如需重连，调用方应在 onDisconnect 中
 * 重新调用 createSSEClient 或复用实例的 connect()。
 */
export function createSSEClient(options: SSEClientOptions): SSEClient {
  // 检测 ReadableStream 与 fetch 支持（Node.js 与现代浏览器均满足）
  const supportsFetchStream =
    typeof fetch !== "undefined" &&
    typeof ReadableStream !== "undefined"

  if (supportsFetchStream) {
    return new FetchStreamSSEClient({
      url: options.url,
      token: options.token,
      accessToken: options.accessToken,
      lastEventId: options.lastEventId,
      heartbeatTimeoutMs: options.heartbeatTimeoutMs,
      onEvent: options.onEvent,
      onConnect: options.onConnect,
      onDisconnect: options.onDisconnect,
      onError: options.onError,
      getActiveRunId: options.getActiveRunId,
      getExpectedRevision: options.getExpectedRevision,
      // FetchStream 的 onRevisionGap 是 () => void，需要适配旧签名
      onRevisionGap: options.onRevisionGap
        ? () => {
            // FetchStream 无法直接获取 event/expected/got，调用方在回调中应自行读取
            const expected = options.getExpectedRevision?.() ?? 0
            void options.onRevisionGap?.({} as SSEEvent, expected, 0)
          }
        : undefined,
    })
  }

  // 回退到 EventSource 实现
  return new WorkflowSSEClient(
    options.url,
    {
      onEvent: options.onEvent,
      onConnect: options.onConnect,
      onReconnect: options.onReconnect,
      onFatalError: options.onFatalError,
      getActiveRunId: options.getActiveRunId,
      getExpectedRevision: options.getExpectedRevision,
      onRevisionGap: options.onRevisionGap,
    },
    options.accessToken,
    options.lastEventId ?? 0,
  )
}

export default WorkflowSSEClient
