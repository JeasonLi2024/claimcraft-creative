import { useEffect, useRef, useMemo } from "react"

/**
 * ParticleBackground — Canvas 粒子背景层
 *
 * 设计理念（Golden Time 设计系统）：
 * - 100-150 个金色光斑粒子（#d6a84b），缓速漂浮
 * - 鼠标附近聚集（吸引力 ≤ 80px）
 * - requestAnimationFrame 循环
 * - IntersectionObserver 离屏暂停
 * - prefers-reduced-motion 降级（静止粒子）
 * - 移动端粒子数减半
 *
 * 性能保障：
 * - 仅在可见时渲染
 * - 粒子数量按设备性能分级
 */
interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  opacity: number
}

export default function ParticleBackground({
  particleCount,
}: {
  particleCount?: number
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | null>(null)
  const particlesRef = useRef<Particle[]>([])
  const mouseRef = useRef({ x: -1000, y: -1000 })
  const isVisibleRef = useRef(true)

  // 根据设备性能确定粒子数
  const actualCount = useMemo(() => {
    if (particleCount) return particleCount
    if (typeof window === "undefined") return 100
    const isMobile = window.innerWidth < 768
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    if (reduced) return 30
    return isMobile ? 50 : 150
  }, [particleCount])

  // 是否偏好减少动效（静态渲染）
  const reducedMotion = useMemo(() => {
    if (typeof window === "undefined") return false
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    const resize = () => {
      canvas.width = window.innerWidth * dpr
      canvas.height = window.innerHeight * dpr
      canvas.style.width = `${window.innerWidth}px`
      canvas.style.height = `${window.innerHeight}px`
      ctx.scale(dpr, dpr)
    }

    // debounce resize：避免频繁重建粒子
    let resizeTimer: number | null = null
    const debouncedResize = () => {
      if (resizeTimer) window.clearTimeout(resizeTimer)
      resizeTimer = window.setTimeout(() => {
        resize()
        initParticles()
      }, 150)
    }

    const initParticles = () => {
      const particles: Particle[] = []
      for (let i = 0; i < actualCount; i++) {
        particles.push({
          x: Math.random() * window.innerWidth,
          y: Math.random() * window.innerHeight,
          vx: (Math.random() - 0.5) * 0.4,
          vy: (Math.random() - 0.5) * 0.4,
          radius: Math.random() * 2 + 0.8,
          opacity: Math.random() * 0.5 + 0.2,
        })
      }
      particlesRef.current = particles
    }

    const draw = (animate: boolean) => {
      if (!isVisibleRef.current) {
        if (animate) animationRef.current = requestAnimationFrame(() => draw(true))
        return
      }

      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)

      const particles = particlesRef.current
      const mouse = mouseRef.current

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]

        if (animate) {
          // 漂浮运动
          p.x += p.vx
          p.y += p.vy

          // 边界反弹
          if (p.x < 0 || p.x > window.innerWidth) p.vx *= -1
          if (p.y < 0 || p.y > window.innerHeight) p.vy *= -1

          // 鼠标吸引力（≤ 80px）
          const dx = mouse.x - p.x
          const dy = mouse.y - p.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 80 && dist > 0) {
            const force = (80 - dist) / 80
            p.x += (dx / dist) * force * 0.5
            p.y += (dy / dist) * force * 0.5
          }
        }

        // 绘制光斑（带光晕）
        const gradient = ctx.createRadialGradient(
          p.x,
          p.y,
          0,
          p.x,
          p.y,
          p.radius * 4
        )
        gradient.addColorStop(0, `rgba(214, 168, 75, ${p.opacity})`)
        gradient.addColorStop(0.5, `rgba(214, 168, 75, ${p.opacity * 0.3})`)
        gradient.addColorStop(1, "rgba(214, 168, 75, 0)")

        ctx.fillStyle = gradient
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.radius * 4, 0, Math.PI * 2)
        ctx.fill()

        // 核心亮点
        ctx.fillStyle = `rgba(214, 168, 75, ${p.opacity * 1.5})`
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
        ctx.fill()
      }

      if (animate) {
        animationRef.current = requestAnimationFrame(() => draw(true))
      }
    }

    const handleMouseMove = (e: MouseEvent) => {
      mouseRef.current = { x: e.clientX, y: e.clientY }
    }

    const handleMouseLeave = () => {
      mouseRef.current = { x: -1000, y: -1000 }
    }

    // IntersectionObserver 离屏暂停
    const observer = new IntersectionObserver(
      (entries) => {
        isVisibleRef.current = entries[0]?.isIntersecting ?? true
      },
      { threshold: 0 }
    )
    observer.observe(canvas)

    resize()
    initParticles()
    draw(!reducedMotion)

    window.addEventListener("resize", debouncedResize)
    window.addEventListener("mousemove", handleMouseMove)
    window.addEventListener("mouseleave", handleMouseLeave)

    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current)
      if (resizeTimer) window.clearTimeout(resizeTimer)
      window.removeEventListener("resize", debouncedResize)
      window.removeEventListener("mousemove", handleMouseMove)
      window.removeEventListener("mouseleave", handleMouseLeave)
      observer.disconnect()
    }
  }, [actualCount, reducedMotion])

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0 z-0"
      aria-hidden="true"
    />
  )
}
