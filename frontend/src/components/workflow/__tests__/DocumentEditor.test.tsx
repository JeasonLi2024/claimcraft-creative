/**
 * Task 6.2.7: 移动端布局 + 键盘操作 + ARIA live + reduced motion 测试
 *
 * 测试 DocumentEditor 组件：
 * 1. 移动端 tab 切换（role="tablist" + aria-selected）
 * 2. aria-live="polite" 保存状态指示
 * 3. Escape 关闭版本历史抽屉
 * 4. prefers-reduced-motion 适配（motion-safe 类存在）
 * 5. 双栏 tabpanel 结构
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest"
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react"
import type { DocumentDetail } from "@/types/document"

// ---------- 模块 Mock ----------

// Mock DocumentSourcePanel（避免其 API 调用干扰）
vi.mock("@/components/workflow/DocumentSourcePanel", () => ({
  DocumentSourcePanel: () => <div data-testid="mock-source-panel">依据面板</div>,
}))

// Mock RegenerateConfirmDialog / LegalReferenceModal（条件渲染，默认不出现）
vi.mock("@/components/workflow/RegenerateConfirmDialog", () => ({
  RegenerateConfirmDialog: () => null,
}))
vi.mock("@/components/workflow/LegalReferenceModal", () => ({
  LegalReferenceModal: () => null,
}))

// Mock document-api（VersionHistoryDrawer 和 DocumentEditor 都依赖）
vi.mock("@/lib/document-api", () => ({
  documentApi: {
    regenerateParagraph: vi.fn().mockResolvedValue({
      paragraph: { id: "p1", content: "保存的内容", evidence_codes: [], legal_references: [], created_by_type: "user" },
      version: { id: "v2", document_id: "doc-1", version: 2, content: "保存的内容", created_by_type: "user", created_at: "2026-07-17T12:00:00Z" },
    }),
    exportCheck: vi.fn().mockResolvedValue({ passed: true, issues: [], missing_elements: [], checks_run: [] }),
    listDocumentVersions: vi.fn().mockResolvedValue([
      { id: "v1", document_id: "doc-1", version: 1, content: "版本1内容", created_by_type: "ai", created_at: "2026-07-17T10:00:00Z" },
    ]),
    rollbackDocumentVersion: vi.fn(),
    getDocument: vi.fn(),
  },
  DocumentApiError: class extends Error {
    code = ""
    notImplemented = false
  },
}))

// Mock workflowRunApi
vi.mock("@/lib/api", () => ({
  workflowRunApi: { retryRun: vi.fn() },
}))

// ---------- 导入被测组件（在 mock 之后）----------
import { DocumentEditor } from "@/components/workflow/DocumentEditor"

// ---------- 测试数据 ----------

const mockDocument: DocumentDetail = {
  id: "doc-1",
  run_id: 100,
  title: "测试投诉书",
  template_type: "complaint",
  current_version: 1,
  paragraphs: [
    {
      id: "p1",
      content: "这是第一段内容。",
      evidence_codes: ["EV-001"],
      legal_references: [{ law_name: "消费者权益保护法", article_number: "第二十四条" }],
      created_by_type: "ai",
    },
    {
      id: "p2",
      content: "这是第二段内容。",
      evidence_codes: [],
      legal_references: [],
      created_by_type: "ai",
    },
  ],
}

// ---------- 全局设置 ----------

beforeAll(() => {
  // jsdom 可能不实现 Element.scrollTo，添加空实现避免报错
  if (!Element.prototype.scrollTo) {
    Element.prototype.scrollTo = vi.fn() as unknown as typeof Element.prototype.scrollTo
  }
})

// ---------- 移动端布局测试 ----------

describe("DocumentEditor 移动端布局", () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("渲染移动端 tab 切换栏（role=tablist）", () => {
    render(<DocumentEditor document={mockDocument} />)

    const tablist = screen.getByRole("tablist", { name: "文书编辑器视图切换" })
    expect(tablist).toBeInTheDocument()

    const tabs = screen.getAllByRole("tab")
    expect(tabs).toHaveLength(2)
    expect(tabs[0]).toHaveTextContent("文书正文")
    expect(tabs[1]).toHaveTextContent("依据与质量")
  })

  it("默认选中「文书正文」tab", () => {
    render(<DocumentEditor document={mockDocument} />)

    const tabs = screen.getAllByRole("tab")
    expect(tabs[0]).toHaveAttribute("aria-selected", "true")
    expect(tabs[1]).toHaveAttribute("aria-selected", "false")
  })

  it("点击「依据与质量」tab 切换选中状态", () => {
    render(<DocumentEditor document={mockDocument} />)

    const tabs = screen.getAllByRole("tab")
    fireEvent.click(tabs[1])

    expect(tabs[1]).toHaveAttribute("aria-selected", "true")
    expect(tabs[0]).toHaveAttribute("aria-selected", "false")
  })

  it("双栏 tabpanel 结构存在", () => {
    render(<DocumentEditor document={mockDocument} />)

    const editorPane = screen.getByRole("tabpanel", { name: "文书正文" })
    expect(editorPane).toBeInTheDocument()

    const sourcePane = screen.getByRole("tabpanel", { name: "依据与质量" })
    expect(sourcePane).toBeInTheDocument()
  })
})

// ---------- ARIA live 测试 ----------

describe("DocumentEditor ARIA live", () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("编辑段落后保存状态包含 aria-live=polite", async () => {
    render(<DocumentEditor document={mockDocument} />)

    // 找到第一段的 textarea 并编辑
    const textarea = screen.getByRole("textbox", { name: "段落 1 内容" })
    fireEvent.change(textarea, { target: { value: "修改后的内容" } })

    // 等待保存状态出现
    await waitFor(() => {
      const statusEl = screen.getByText(/保存中/)
      expect(statusEl).toBeInTheDocument()
      expect(statusEl.getAttribute("aria-live")).toBe("polite")
    })
  })
})

// ---------- 键盘操作测试 ----------

describe("DocumentEditor 键盘操作", () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("Escape 关闭版本历史抽屉", async () => {
    render(<DocumentEditor document={mockDocument} />)

    // 打开版本历史抽屉
    const historyBtn = screen.getByRole("button", { name: "查看版本历史" })
    fireEvent.click(historyBtn)

    // 验证抽屉已打开
    const drawer = await screen.findByRole("dialog", { name: "版本历史" })
    expect(drawer).toBeInTheDocument()

    // 按 Escape 关闭
    fireEvent.keyDown(document.body, { key: "Escape" })

    // 验证抽屉已关闭
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "版本历史" })).toBeNull()
    })
  })
})

// ---------- reduced motion 适配测试 ----------

describe("DocumentEditor reduced motion 适配", () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("prefers-reduced-motion 下抽屉包含 motion-safe 类（Tailwind reduced-motion 适配）", async () => {
    // 模拟用户启用了减少动画偏好
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    render(<DocumentEditor document={mockDocument} />)

    // 打开版本历史抽屉
    const historyBtn = screen.getByRole("button", { name: "查看版本历史" })
    fireEvent.click(historyBtn)

    // 抽屉应正常渲染
    const drawer = await screen.findByRole("dialog", { name: "版本历史" })
    expect(drawer).toBeInTheDocument()

    // 验证 aside 元素包含 motion-safe 类（项目通过 Tailwind motion-safe 变体适配 reduced motion）
    const aside = drawer.querySelector("aside")
    expect(aside).toBeTruthy()
    expect(aside?.className).toContain("motion-safe:animate")
  })
})