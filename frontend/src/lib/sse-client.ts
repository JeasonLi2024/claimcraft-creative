// SSE 客户端封装：EventSource + 自动重连 + last_event_id 续传
// 参考 spec 第 6.3 节

import type { SSEEvent, EventType } from "@/lib/workflow-events"

export interface SSEHandlers {
  /** 收到任意事件时调用 */
  onEvent: (event: SSEEvent) => void
  /** 连接成功时调用 */
  onConnect?: () => void
  /** 开始重连时调用，传入当前重连次数与最大次数 */
  onReconnect?: (attempt: number, max: number) => void
  /** 达到最大重连次数后调用 */
  onFatalError?: (message: string) => void
}

/** 需要监听的 SSE 事件类型列表 */
const EVENT_TYPES: EventType[] = [
  "workflow.start",
  "workflow.resumed",
  "workflow.complete",
  "workflow.error",
  "node.start",
  "node.progress",
  "node.complete",
  "node.error",
  "complaint.token",
  "complaint.done",
  "review.interrupt",
  "review.resumed",
  "review.skipped",
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
  ) {}

  /** 建立 SSE 连接，注册所有事件类型监听器 */
  connect(): void {
    this.closed = false
    const separator = this.streamUrl.includes("?") ? "&" : "?"
    const url = `${this.streamUrl}${separator}last_event_id=${this.lastEventId}`
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

  /** 解析事件，更新 lastEventId，调用 handlers.onEvent */
  private dispatch(e: MessageEvent): void {
    let data: SSEEvent
    try {
      data = JSON.parse(e.data) as SSEEvent
    } catch {
      return
    }
    if (typeof data.event_id === "number") {
      this.lastEventId = Math.max(this.lastEventId, data.event_id)
    }
    this.handlers.onEvent(data)
    if (
      data.event_type === "workflow.complete" ||
      data.event_type === "workflow.error"
    ) {
      this.close()
    }
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
