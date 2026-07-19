// Docs 左侧导航：参考案件工作区侧栏（图标+文字列表，激活态高亮）。
import { Link } from "react-router"
import { ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { DOC_PAGES } from "@/docs/manifest"

export interface DocsSidebarProps {
  activeSlug: string
}

export function DocsSidebar({ activeSlug }: DocsSidebarProps) {
  return (
    <nav aria-label="文档导航" className="flex flex-col gap-1">
      <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#8b8f89]">文档</p>
      {DOC_PAGES.map((page) => {
        const active = page.slug === activeSlug
        const Icon = page.icon
        return (
          <Link
            key={page.slug}
            to={`/docs/${page.slug}`}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              active
                ? "bg-[#e7eee9] text-[#2f5947]"
                : "text-[#6c706b] hover:bg-[#f1f2ee] hover:text-[#181b1a]",
            )}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="flex-1">{page.label}</span>
            {active && <ChevronRight className="h-4 w-4" aria-hidden="true" />}
          </Link>
        )
      })}
    </nav>
  )
}

export default DocsSidebar
