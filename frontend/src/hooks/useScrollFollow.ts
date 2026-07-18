import { useCallback, useRef, useState, type RefObject } from "react"

interface UseScrollFollowOptions {
  // 距底部小于该阈值时视为"已到底部"，恢复自动跟随
  threshold?: number
}

interface UseScrollFollowResult {
  /** 容器 ref，需绑定到可滚动容器 */
  containerRef: RefObject<HTMLDivElement | null>
  /** 是否正在自动跟随底部 */
  isFollowing: boolean
  /** 绑定到容器的 onScroll 事件 */
  onScroll: () => void
  /** 平滑滚动到底部并恢复自动跟随 */
  scrollToBottom: () => void
}

/**
 * 流式内容自动滚动跟随 Hook
 * - 默认开启自动跟随
 * - 用户向上滚动离开底部时停止跟随（避免抢夺滚动位置）
 * - 用户回到底部（距底部 < threshold）时恢复跟随
 *
 * 用于 ProductStream 等流式渲染容器，替代原先强制 scrollIntoView 的逻辑。
 */
export function useScrollFollow(options: UseScrollFollowOptions = {}): UseScrollFollowResult {
  const { threshold = 50 } = options
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [isFollowing, setIsFollowing] = useState(true)
  // 上一次 scrollTop，用于判断滚动方向
  const lastScrollTopRef = useRef<number>(0)

  const onScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const { scrollTop, scrollHeight, clientHeight } = el
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight
    const direction = scrollTop - lastScrollTopRef.current
    lastScrollTopRef.current = scrollTop

    // 向上滚动且距离底部超过阈值 → 停止跟随
    if (direction < 0 && distanceFromBottom > threshold) {
      setIsFollowing(false)
    } else if (distanceFromBottom <= threshold) {
      // 回到底部 → 恢复跟随
      setIsFollowing(true)
    }
  }, [threshold])

  const scrollToBottom = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" })
    setIsFollowing(true)
    // 同步 lastScrollTopRef，避免下一次 onScroll 误判方向
    lastScrollTopRef.current = el.scrollTop
  }, [])

  return { containerRef, isFollowing, onScroll, scrollToBottom }
}
