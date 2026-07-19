// Docs 纯逻辑：从 markdown 派生右侧 TOC 与搜索索引。
// 不引入 React / react-markdown，便于单测；slug 与 rehype-slug（github-slugger）保持一致。
import GithubSlugger from "github-slugger"
import { allDocSources } from "./manifest"

export interface TocItem {
  id: string
  text: string
  level: 2 | 3
}

/** 去除常见 markdown 内联记号，得到用于展示/建 slug 的纯文本。 */
function stripInline(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/\[(.+?)\]\([^)]*\)/g, "$1")
    .trim()
}

const FENCE = /^\s*```/
const HEADING = /^(#{1,6})\s+(.+?)\s*#*\s*$/

/**
 * 提取 h2/h3 目录。对每个标题（含 h1）都推进 slugger，以与 rehype-slug 的
 * 全文档顺序一致，保证 id 精确匹配（用于锚点跳转与 hash 深链）。跳过代码围栏。
 */
export function tocFromMarkdown(md: string): TocItem[] {
  const slugger = new GithubSlugger()
  const items: TocItem[] = []
  let inFence = false
  for (const line of md.split("\n")) {
    if (FENCE.test(line)) {
      inFence = !inFence
      continue
    }
    if (inFence) continue
    const m = HEADING.exec(line)
    if (!m) continue
    const level = m[1].length
    const text = stripInline(m[2])
    const id = slugger.slug(text)
    if (level === 2 || level === 3) items.push({ id, text, level })
  }
  return items
}

export interface SearchHit {
  slug: string
  pageLabel: string
  headingId?: string
  headingText?: string
  snippet: string
}

interface IndexEntry {
  slug: string
  pageLabel: string
  headingId?: string
  headingText?: string
  text: string
}

function stripBlockPrefix(line: string): string {
  return stripInline(
    line
      .replace(/^\s*[-*]\s+/, "")
      .replace(/^\s*\d+\.\s+/, "")
      .replace(/^\s*>\s?/, "")
      .replace(/^:::.*$/, ""),
  )
}

function buildIndex(): IndexEntry[] {
  const entries: IndexEntry[] = []
  for (const { slug, label, md } of allDocSources()) {
    const slugger = new GithubSlugger()
    let headingId: string | undefined
    let headingText: string | undefined
    let inFence = false
    for (const line of md.split("\n")) {
      if (FENCE.test(line)) {
        inFence = !inFence
        continue
      }
      if (inFence) continue
      const h = HEADING.exec(line)
      if (h) {
        const text = stripInline(h[2])
        const id = slugger.slug(text) // 推进 slugger，保持与 rehype-slug 一致
        if (h[1].length >= 2) {
          headingId = id
          headingText = text
          entries.push({ slug, pageLabel: label, headingId, headingText, text })
        } else {
          // H1 页面标题：可被搜索到，但不作为标题锚点
          entries.push({ slug, pageLabel: label, text })
        }
        continue
      }
      const text = stripBlockPrefix(line)
      if (text) entries.push({ slug, pageLabel: label, headingId, headingText, text })
    }
  }
  return entries
}

const SEARCH_INDEX = buildIndex()

/** 纯函数客户端搜索：子串（不区分大小写）匹配标题与正文，按 页面#标题 去重。 */
export function searchDocs(query: string, limit = 8): SearchHit[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const hits: SearchHit[] = []
  const seen = new Set<string>()
  for (const entry of SEARCH_INDEX) {
    if (!entry.text.toLowerCase().includes(q)) continue
    const key = `${entry.slug}#${entry.headingId ?? ""}`
    if (seen.has(key)) continue
    seen.add(key)
    hits.push({
      slug: entry.slug,
      pageLabel: entry.pageLabel,
      headingId: entry.headingId,
      headingText: entry.headingText,
      snippet: entry.text.slice(0, 90),
    })
    if (hits.length >= limit) break
  }
  return hits
}
