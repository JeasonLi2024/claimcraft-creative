// Docs 正文渲染：react-markdown + 自定义组件，套用主站米白墨绿调色板与 langchain 式排版。
// remark-gfm（表格等）+ remark-directive + calloutDirective（三态 callout）+ rehype-slug（标题 id）。
import type { ComponentPropsWithoutRef, ReactNode } from "react"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkDirective from "remark-directive"
import rehypeSlug from "rehype-slug"
import { CheckCircle2, Info, TriangleAlert } from "lucide-react"
import { cn } from "@/lib/utils"
import { calloutDirective } from "@/docs/calloutDirective"

const CALLOUT_META = {
  info: { icon: Info, wrap: "border-[#cfe0d6] bg-[#eef4f0]", iconClass: "text-[#2f5947]", titleClass: "text-[#254a3a]" },
  warn: { icon: TriangleAlert, wrap: "border-[#e5d9b5] bg-[#fef9ec]", iconClass: "text-[#8a702d]", titleClass: "text-[#6f5a25]" },
  success: { icon: CheckCircle2, wrap: "border-emerald-200 bg-emerald-50", iconClass: "text-emerald-600", titleClass: "text-emerald-800" },
} as const

function Callout({ tone, title, children }: { tone: keyof typeof CALLOUT_META; title?: string; children: ReactNode }) {
  const meta = CALLOUT_META[tone]
  const Icon = meta.icon
  return (
    <div className={cn("mt-5 flex items-start gap-3 rounded-xl border px-4 py-3.5", meta.wrap)}>
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", meta.iconClass)} aria-hidden="true" />
      <div className="min-w-0 [&>p]:m-0 [&>p]:text-sm [&>p]:leading-6 [&>p]:text-[#4d524e] [&>p+p]:mt-2">
        {title && <p className={cn("!mb-1 text-sm font-semibold", meta.titleClass)}>{title}</p>}
        {children}
      </div>
    </div>
  )
}

const MARKDOWN_COMPONENTS = {
  h1: (props: ComponentPropsWithoutRef<"h1">) => (
    <h1 {...props} className="mt-0 text-3xl font-semibold tracking-[-0.03em] text-[#181b1a] sm:text-4xl" />
  ),
  h2: (props: ComponentPropsWithoutRef<"h2">) => (
    <h2 {...props} className="mt-12 scroll-mt-24 border-b border-[#e4e6e0] pb-2 text-2xl font-semibold tracking-[-0.02em] text-[#181b1a]" />
  ),
  h3: (props: ComponentPropsWithoutRef<"h3">) => (
    <h3 {...props} className="mt-8 scroll-mt-24 text-lg font-semibold text-[#181b1a]" />
  ),
  p: (props: ComponentPropsWithoutRef<"p">) => <p {...props} className="mt-4 leading-7 text-[#4d524e]" />,
  ul: (props: ComponentPropsWithoutRef<"ul">) => (
    <ul {...props} className="mt-4 list-disc space-y-2 pl-5 leading-7 text-[#4d524e] marker:text-[#3f6b57]" />
  ),
  ol: (props: ComponentPropsWithoutRef<"ol">) => (
    <ol {...props} className="mt-4 list-decimal space-y-2 pl-5 leading-7 text-[#4d524e] marker:text-[#8b8f89]" />
  ),
  li: (props: ComponentPropsWithoutRef<"li">) => <li {...props} className="pl-1" />,
  strong: (props: ComponentPropsWithoutRef<"strong">) => <strong {...props} className="font-semibold text-[#181b1a]" />,
  a: ({ href, ...props }: ComponentPropsWithoutRef<"a">) => {
    const external = !!href && /^https?:\/\//.test(href)
    return (
      <a
        href={href}
        {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
        {...props}
        className="font-medium text-[#2f5947] underline decoration-[#9db8ab] underline-offset-2 hover:decoration-[#2f5947]"
      />
    )
  },
  code: ({ className, ...props }: ComponentPropsWithoutRef<"code">) => {
    const isBlock = typeof className === "string" && /language-/.test(className)
    if (isBlock) return <code className={className} {...props} />
    return <code {...props} className="rounded-md bg-[#eceee9] px-1.5 py-0.5 font-mono text-[0.85em] text-[#2f5947]" />
  },
  pre: (props: ComponentPropsWithoutRef<"pre">) => (
    <pre {...props} className="mt-4 overflow-x-auto rounded-xl bg-[#181b1a] p-4 text-sm leading-6 text-[#e7eae6]" />
  ),
  blockquote: (props: ComponentPropsWithoutRef<"blockquote">) => (
    <blockquote {...props} className="mt-5 border-l-2 border-[#cfd5cc] pl-4 italic text-[#5f6661]" />
  ),
  table: (props: ComponentPropsWithoutRef<"table">) => (
    <div className="mt-5 overflow-x-auto rounded-xl border border-[#e4e6e0]">
      <table {...props} className="w-full text-left text-sm" />
    </div>
  ),
  thead: (props: ComponentPropsWithoutRef<"thead">) => <thead {...props} className="bg-[#f1f2ee] text-[#4d524e]" />,
  th: (props: ComponentPropsWithoutRef<"th">) => <th {...props} className="px-4 py-2.5 font-semibold" />,
  td: (props: ComponentPropsWithoutRef<"td">) => <td {...props} className="border-t border-[#e4e6e0] px-4 py-2.5 text-[#4d524e]" />,
  // 由 calloutDirective 生成的 <div class="callout callout-<tone>" data-title>：渲染为三态提示框。
  div: ({ className, children, ...props }: ComponentPropsWithoutRef<"div">) => {
    const cls = typeof className === "string" ? className : ""
    if (cls.includes("callout")) {
      const tone: keyof typeof CALLOUT_META = cls.includes("callout-warn")
        ? "warn"
        : cls.includes("callout-success")
          ? "success"
          : "info"
      const title = (props as Record<string, unknown>)["data-title"] as string | undefined
      return <Callout tone={tone} title={title || undefined}>{children}</Callout>
    }
    return <div className={className} {...props}>{children}</div>
  },
}

export function DocsContent({ markdown }: { markdown: string }) {
  return (
    <div className="mx-auto max-w-[760px] pb-4">
      <Markdown
        remarkPlugins={[remarkGfm, remarkDirective, calloutDirective]}
        rehypePlugins={[rehypeSlug]}
        components={MARKDOWN_COMPONENTS}
      >
        {markdown}
      </Markdown>
    </div>
  )
}

export default DocsContent
