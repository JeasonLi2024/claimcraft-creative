// 极简 remark 插件：把 `:::info/:::warn/:::success{title="…"}` 容器指令转成
// <div class="callout callout-<tone>" data-title="…">，由 DocsContent 的 div 组件渲染为三态提示框。
// 不依赖 unist-util-visit，手写递归即可。
interface DirNode {
  type: string
  name?: string
  attributes?: Record<string, string | null | undefined> | null
  children?: DirNode[]
  data?: { hName?: string; hProperties?: Record<string, unknown> }
}

const TONES = new Set(["info", "warn", "success"])

function walk(node: DirNode): void {
  if (!node.children) return
  for (const child of node.children) {
    if (child.type === "containerDirective" && child.name && TONES.has(child.name)) {
      const title = child.attributes?.title ?? ""
      child.data = child.data ?? {}
      child.data.hName = "div"
      child.data.hProperties = {
        className: ["callout", `callout-${child.name}`],
        "data-title": title,
      }
    }
    walk(child)
  }
}

export function calloutDirective() {
  return (tree: unknown): void => walk(tree as DirNode)
}
