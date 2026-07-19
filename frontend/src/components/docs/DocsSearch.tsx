// Docs 搜索框：基于内容索引的客户端子串搜索，命中后切页并滚动到对应标题。
import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router"
import { Search, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { searchDocs, type SearchHit } from "@/docs/markdown"
import { focusRing } from "@/lib/brand"

export function DocsSearch() {
  const navigate = useNavigate()
  const [query, setQuery] = useState("")
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const hits = useMemo<SearchHit[]>(() => searchDocs(query), [query])

  useEffect(() => {
    if (!open) return
    function onPointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onPointerDown)
    return () => document.removeEventListener("mousedown", onPointerDown)
  }, [open])

  function go(hit: SearchHit) {
    setOpen(false)
    setQuery("")
    navigate(hit.headingId ? `/docs/${hit.slug}#${hit.headingId}` : `/docs/${hit.slug}`)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      setOpen(false)
      ;(e.target as HTMLInputElement).blur()
    } else if (e.key === "Enter" && hits.length > 0) {
      e.preventDefault()
      go(hits[0])
    }
  }

  return (
    <div ref={containerRef} className="relative w-full max-w-md">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8b8f89]" aria-hidden="true" />
        <input
          type="search"
          value={query}
          placeholder="搜索文档…"
          role="combobox"
          aria-expanded={open && hits.length > 0}
          aria-controls="docs-search-results"
          aria-label="搜索文档"
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          className={cn(
            "h-10 w-full rounded-xl border border-[#d9ddd5] bg-white pl-9 pr-9 text-sm text-[#181b1a] placeholder:text-[#8b8f89] transition-shadow",
            "focus:border-[#3f6b57] focus:outline-none focus:ring-2 focus:ring-[#3f6b57]/20",
          )}
        />
        {query && (
          <button
            type="button"
            onClick={() => { setQuery(""); setOpen(false) }}
            aria-label="清除搜索"
            className={cn("absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-[#8b8f89] hover:text-[#181b1a]", focusRing)}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>

      {open && query.trim() && (
        <div
          id="docs-search-results"
          role="listbox"
          className="absolute left-0 right-0 top-[calc(100%+8px)] z-40 overflow-hidden rounded-xl border border-[#d9ddd5] bg-white shadow-[0_20px_60px_rgba(24,33,29,.16)]"
        >
          {hits.length === 0 ? (
            <p className="px-4 py-3 text-sm text-[#8b8f89]">未找到相关内容</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto py-1">
              {hits.map((hit) => (
                <li key={`${hit.slug}#${hit.headingId ?? ""}`}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    onClick={() => go(hit)}
                    className="flex w-full flex-col gap-0.5 px-4 py-2.5 text-left transition-colors hover:bg-[#f1f2ee]"
                  >
                    <span className="flex items-center gap-2 text-sm font-medium text-[#181b1a]">
                      <span className="rounded bg-[#e7eee9] px-1.5 py-0.5 text-[11px] font-medium text-[#2f5947]">{hit.pageLabel}</span>
                      {hit.headingText && <span className="truncate">{hit.headingText}</span>}
                    </span>
                    <span className="truncate text-xs text-[#8b8f89]">{hit.snippet}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export default DocsSearch
