/**
 * Task 6.2.6: 流式文书停止自动跟随测试
 *
 * 测试 useScrollFollow Hook 的行为：
 * 1. 初始状态 isFollowing=true
 * 2. 用户向上滚动后 isFollowing 变为 false
 * 3. 点击「回到最新内容」后 isFollowing 变为 true 并滚动到底部
 * 4. 用户回到底部时自动恢复 isFollowing
 */
import { describe, it, expect, vi } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { useScrollFollow } from "@/hooks/useScrollFollow"

/** 构造模拟 DOM 元素（jsdom 不支持真实滚动，需手动设置 scroll 属性） */
function createMockElement(overrides: Partial<HTMLDivElement> = {}): HTMLDivElement {
  return {
    scrollTop: 0,
    scrollHeight: 500,
    clientHeight: 200,
    scrollTo: vi.fn(),
    ...overrides,
  } as unknown as HTMLDivElement
}

describe("useScrollFollow 初始状态", () => {
  it("默认 isFollowing=true", () => {
    const { result } = renderHook(() => useScrollFollow())
    expect(result.current.isFollowing).toBe(true)
  })

  it("containerRef 初始为 null", () => {
    const { result } = renderHook(() => useScrollFollow())
    expect(result.current.containerRef.current).toBeNull()
  })
})

describe("useScrollFollow 向上滚动停止跟随", () => {
  it("用户向上滚动后 isFollowing 变为 false", () => {
    const { result } = renderHook(() => useScrollFollow({ threshold: 50 }))

    const el = createMockElement({ scrollTop: 200 })
    act(() => {
      result.current.containerRef.current = el
      // 第一次 onScroll：设置 lastScrollTopRef = 200
      result.current.onScroll()
    })
    expect(result.current.isFollowing).toBe(true)

    // 向上滚动：scrollTop 从 200 减到 100
    act(() => {
      el.scrollTop = 100
      result.current.onScroll()
    })
    expect(result.current.isFollowing).toBe(false)
  })

  it("向下滚动不停止跟随", () => {
    const { result } = renderHook(() => useScrollFollow({ threshold: 50 }))

    const el = createMockElement({ scrollTop: 100 })
    act(() => {
      result.current.containerRef.current = el
      result.current.onScroll()
    })

    // 向下滚动：scrollTop 从 100 增到 200
    act(() => {
      el.scrollTop = 200
      result.current.onScroll()
    })
    expect(result.current.isFollowing).toBe(true)
  })
})

describe("useScrollFollow 回到最新内容", () => {
  it("scrollToBottom 后 isFollowing 变为 true 并滚动到底部", () => {
    const { result } = renderHook(() => useScrollFollow({ threshold: 50 }))

    const scrollToMock = vi.fn()
    const el = createMockElement({ scrollTop: 200, scrollTo: scrollToMock })
    act(() => {
      result.current.containerRef.current = el
      result.current.onScroll()
    })

    // 先向上滚动停止跟随
    act(() => {
      el.scrollTop = 100
      result.current.onScroll()
    })
    expect(result.current.isFollowing).toBe(false)

    // 调用 scrollToBottom（模拟点击「回到最新内容」按钮）
    act(() => {
      result.current.scrollToBottom()
    })
    expect(result.current.isFollowing).toBe(true)
    expect(scrollToMock).toHaveBeenCalledWith({ top: 500, behavior: "smooth" })
  })
})

describe("useScrollFollow 自动恢复跟随", () => {
  it("用户回到底部时自动恢复 isFollowing=true", () => {
    const { result } = renderHook(() => useScrollFollow({ threshold: 50 }))

    const el = createMockElement({ scrollTop: 200 })
    act(() => {
      result.current.containerRef.current = el
      result.current.onScroll()
    })

    // 向上滚动停止跟随
    act(() => {
      el.scrollTop = 100
      result.current.onScroll()
    })
    expect(result.current.isFollowing).toBe(false)

    // 滚回底部：scrollTop = 300，distanceFromBottom = 500-300-200 = 0 <= 50
    act(() => {
      el.scrollTop = 300
      result.current.onScroll()
    })
    expect(result.current.isFollowing).toBe(true)
  })
})
