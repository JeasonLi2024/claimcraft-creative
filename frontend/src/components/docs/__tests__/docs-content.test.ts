/**
 * Docs 纯逻辑测试：从 markdown 派生 TOC、页面元数据回退、搜索。
 * 仅引纯函数模块（不引 react-markdown），规避 ESM 测试配置。
 */
import { describe, it, expect } from "vitest"
import { searchDocs, tocFromMarkdown } from "@/docs/markdown"
import { DEFAULT_DOC_SLUG, getDocMeta } from "@/docs/manifest"

describe("tocFromMarkdown", () => {
  it("提取 h2/h3，保留顺序与层级并 slug 化标题", () => {
    const md = ["# Title", "intro", "## Getting Started", "text", "### Step One", "## Next Section"].join("\n")
    expect(tocFromMarkdown(md)).toEqual([
      { id: "getting-started", text: "Getting Started", level: 2 },
      { id: "step-one", text: "Step One", level: 3 },
      { id: "next-section", text: "Next Section", level: 2 },
    ])
  })

  it("跳过代码围栏内的 # 行", () => {
    const md = ["## Real", "```", "## Not A Heading", "```", "## Also Real"].join("\n")
    expect(tocFromMarkdown(md).map((t) => t.text)).toEqual(["Real", "Also Real"])
  })

  it("重复标题按 github-slugger 规则加后缀", () => {
    const md = ["## Dup", "## Dup"].join("\n")
    expect(tocFromMarkdown(md).map((t) => t.id)).toEqual(["dup", "dup-1"])
  })

  it("去除标题中的内联记号再 slug", () => {
    const toc = tocFromMarkdown("## Use `code` and **bold**")
    expect(toc[0].text).toBe("Use code and bold")
  })
})

describe("getDocMeta", () => {
  it("未知/空 slug 回退默认页", () => {
    expect(getDocMeta("nope").slug).toBe(DEFAULT_DOC_SLUG)
    expect(getDocMeta(undefined).slug).toBe(DEFAULT_DOC_SLUG)
  })
  it("有效 slug 返回对应页", () => {
    expect(getDocMeta("disclaimer").slug).toBe("disclaimer")
  })
})

describe("searchDocs（对真实 md 内容）", () => {
  it("空查询返回空", () => {
    expect(searchDocs("")).toEqual([])
    expect(searchDocs("   ")).toEqual([])
  })

  it("命中真实内容并带来源页标签", () => {
    const hits = searchDocs("身份证")
    expect(hits.length).toBeGreaterThan(0)
    expect(hits.every((h) => typeof h.pageLabel === "string" && h.pageLabel.length > 0)).toBe(true)
  })

  it("命中标题时返回 headingId 便于跳转", () => {
    const hits = searchDocs("隐私打码")
    expect(hits.some((h) => Boolean(h.headingId))).toBe(true)
  })

  it("片段不含 markdown 记号", () => {
    const hits = searchDocs("辅助工具")
    expect(hits.length).toBeGreaterThan(0)
    for (const h of hits) expect(h.snippet).not.toContain("**")
  })
})
