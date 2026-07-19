// Docs 文档站编排器：顶栏 + 左导航 + 正文 + 右侧 TOC。
// 公开页（不套 AppLayout），整页 window 滚动，左右栏 sticky；按 :section 切换（可深链/前进后退）。
// 内容来自 src/docs/content/*.md；正文渲染组件懒加载，markdown 库不进主包、Docs 外壳先绘制。
import { Suspense, lazy, useEffect, useMemo } from "react"
import { Link, useLocation, useParams } from "react-router"
import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { DocsTopNav } from "@/components/docs/DocsTopNav"
import { DocsSidebar } from "@/components/docs/DocsSidebar"
import { DocsToc } from "@/components/docs/DocsToc"
import { DOC_PAGES, getDocMarkdown, getDocMeta } from "@/docs/manifest"
import { tocFromMarkdown } from "@/docs/markdown"

const DocsContent = lazy(() => import("@/components/docs/DocsContent"))

function safeDecode(hash: string): string {
  try {
    return decodeURIComponent(hash)
  } catch {
    return hash
  }
}

export default function DocsPage() {
  const { section } = useParams<{ section: string }>()
  const location = useLocation()
  const meta = getDocMeta(section)
  const markdown = getDocMarkdown(section)
  const toc = useMemo(() => tocFromMarkdown(markdown), [markdown])

  // 进入/切页：有 hash 滚到对应标题（CJK 锚点需解码），否则回到顶部。
  useEffect(() => {
    const hash = location.hash ? safeDecode(location.hash.slice(1)) : ""
    if (hash) {
      // 正文异步渲染，稍等 DOM 就绪后再滚动。
      const timer = window.setTimeout(() => {
        const el = document.getElementById(hash)
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" })
      }, 60)
      return () => window.clearTimeout(timer)
    }
    window.scrollTo({ top: 0 })
  }, [meta.slug, location.hash])

  return (
    <div className="min-h-[100dvh] bg-[#f8f8f5] text-[#181b1a]">
      <DocsTopNav />

      <div className="mx-auto max-w-[1400px] px-4 sm:px-6 lg:px-8">
        {/* 移动端：横向页面切换 */}
        <div className="-mx-4 overflow-x-auto px-4 pt-6 sm:-mx-6 sm:px-6 lg:hidden">
          <div className="flex gap-2">
            {DOC_PAGES.map((p) => {
              const active = p.slug === meta.slug
              const Icon = p.icon
              return (
                <Link
                  key={p.slug}
                  to={`/docs/${p.slug}`}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-2 text-sm font-medium transition-colors",
                    active
                      ? "border-transparent bg-[#e7eee9] text-[#2f5947]"
                      : "border-[#d9ddd5] bg-white text-[#6c706b] hover:text-[#181b1a]",
                  )}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {p.label}
                </Link>
              )
            })}
          </div>
        </div>

        <div className="grid gap-8 py-8 lg:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[240px_minmax(0,1fr)_232px] xl:gap-10">
          <aside className="hidden lg:block">
            <div className="sticky top-24">
              <DocsSidebar activeSlug={meta.slug} />
            </div>
          </aside>

          <main id="doc-main" className="min-w-0 pb-16">
            <Suspense
              fallback={
                <div className="flex h-64 items-center justify-center text-[#8b8f89]">
                  <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
                </div>
              }
            >
              <DocsContent markdown={markdown} />
            </Suspense>
          </main>

          <aside className="hidden xl:block">
            <div className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto pr-1">
              <DocsToc key={meta.slug} items={toc} />
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
