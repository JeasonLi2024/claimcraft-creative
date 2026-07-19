// 右侧「本页目录」：由当前页标题派生，随页面滚动高亮当前标题。
import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import type { TocItem } from "@/docs/markdown"

export interface DocsTocProps {
  items: TocItem[]
}

export function DocsToc({ items }: DocsTocProps) {
  const [activeId, setActiveId] = useState<string | null>(items[0]?.id ?? null)

  // 滚动高亮：观察各标题进入视口，取当前最靠上的可见标题为激活项。
  useEffect(() => {
    if (items.length === 0) return
    setActiveId(items[0].id)
    const visible = new Set<string>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.id
          if (entry.isIntersecting) visible.add(id)
          else visible.delete(id)
        }
        // 取文档顺序中第一个可见标题；无可见时保持不变。
        const firstVisible = items.find((it) => visible.has(it.id))
        if (firstVisible) setActiveId(firstVisible.id)
      },
      // 顶栏约 64px；上边界下移让标题“到达顶部区”即激活。
      { rootMargin: "-72px 0px -70% 0px", threshold: [0, 1] },
    )
    for (const it of items) {
      const el = document.getElementById(it.id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [items])

  function handleClick(e: React.MouseEvent, id: string) {
    e.preventDefault()
    const el = document.getElementById(id)
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" })
      setActiveId(id)
      history.replaceState(null, "", `#${id}`)
    }
  }

  if (items.length === 0) return null

  return (
    <nav aria-label="本页目录" className="text-sm">
      <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#8b8f89]">本页目录</p>
      <ul className="space-y-1.5 border-l border-[#e4e6e0]">
        {items.map((item) => {
          const active = item.id === activeId
          return (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                onClick={(e) => handleClick(e, item.id)}
                aria-current={active ? "location" : undefined}
                className={cn(
                  "-ml-px block border-l-2 py-1 leading-5 transition-colors",
                  item.level === 3 ? "pl-6" : "pl-3",
                  active
                    ? "border-[#3f6b57] font-medium text-[#2f5947]"
                    : "border-transparent text-[#6c706b] hover:text-[#181b1a]",
                )}
              >
                {item.text}
              </a>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

export default DocsToc
