// Docs 元数据 + md 原文读取。
// 内容住在 content/*.md；本文件只保留无法进 md 的元数据（图标/顺序/标签）与取原文的入口。
// 改内容只需编辑对应 .md 并重新构建，不必改代码。
import type { LucideIcon } from "lucide-react"
import { BookOpen, FileText, History, ShieldAlert } from "lucide-react"

export interface DocMeta {
  slug: string
  label: string
  icon: LucideIcon
}

// 顺序即侧栏顺序
export const DOC_PAGES: DocMeta[] = [
  { slug: "intro", label: "项目简介", icon: FileText },
  { slug: "guide", label: "使用说明", icon: BookOpen },
  { slug: "changelog", label: "版本更新", icon: History },
  { slug: "disclaimer", label: "免责声明", icon: ShieldAlert },
]

export const DEFAULT_DOC_SLUG = DOC_PAGES[0].slug

// 构建期把各 md 原文打包为字符串（随 /docs 分包，不进主包）。
const SOURCES = import.meta.glob("./content/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

// './content/intro.md' → 'intro'
const BY_SLUG: Record<string, string> = {}
for (const [path, raw] of Object.entries(SOURCES)) {
  const match = /\/([^/]+)\.md$/.exec(path)
  if (match) BY_SLUG[match[1]] = raw
}

export function getDocMeta(slug: string | undefined): DocMeta {
  return DOC_PAGES.find((p) => p.slug === slug) ?? DOC_PAGES[0]
}

export function getDocMarkdown(slug: string | undefined): string {
  return BY_SLUG[getDocMeta(slug).slug] ?? ""
}

/** 供搜索索引构建：返回各文档的 slug/label/原文。 */
export function allDocSources(): { slug: string; label: string; md: string }[] {
  return DOC_PAGES.map((p) => ({ slug: p.slug, label: p.label, md: BY_SLUG[p.slug] ?? "" }))
}
