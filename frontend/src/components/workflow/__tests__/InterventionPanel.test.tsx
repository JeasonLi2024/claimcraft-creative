/**
 * Task 6.2.5: 用户介入草稿恢复 + 409 冲突提示测试
 *
 * 测试 InterventionPanel 组件：
 * 1. 草稿恢复：传入 draftValues（受控模式）时表单字段显示草稿内容
 * 2. 409 冲突：传入 revisionConflict 时显示冲突提示并禁用提交
 * 3. Escape 关闭面板（键盘操作）
 * 4. onDraftChange 在字段值变化时被调用
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, cleanup } from "@testing-library/react"
import { InterventionPanel } from "@/components/workflow/InterventionPanel"
import type { WorkflowIntervention } from "@/types/workflow"

// ---------- 辅助函数 ----------

/** 构造测试用介入记录 */
function makeIntervention(overrides: Partial<WorkflowIntervention> = {}): WorkflowIntervention {
  return {
    id: 1,
    run_id: 100,
    intervention_type: "quality_review",
    stage: "review",
    status: "pending",
    base_revision: 5,
    form_schema: {
      fields: [
        { name: "amount", label: "索赔金额", type: "number", required: true, initial_value: 1000 },
        { name: "note", label: "备注", type: "textarea", required: false },
      ],
    },
    initial_values: { amount: 1000 },
    impact: { rerun_nodes: ["complaint"] },
    created_at: "2026-07-17T10:00:00Z",
    ...overrides,
  }
}

// ---------- 草稿恢复测试 ----------

describe("InterventionPanel 草稿恢复", () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("传入 draftValues 时恢复草稿内容（受控模式）", () => {
    const intervention = makeIntervention()
    render(
      <InterventionPanel
        intervention={intervention}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        draftValues={{ amount: 2500, note: "草稿中的备注内容" }}
      />,
    )

    // 验证金额字段恢复了草稿值
    const amountInput = document.getElementById("intervention-field-amount") as HTMLInputElement
    expect(amountInput).toBeTruthy()
    expect(amountInput.value).toBe("2500")

    // 验证备注字段恢复了草稿值
    const noteInput = document.getElementById("intervention-field-note") as HTMLTextAreaElement
    expect(noteInput).toBeTruthy()
    expect(noteInput.value).toBe("草稿中的备注内容")
  })

  it("未传入 draftValues 时使用 initial_values（非受控模式）", () => {
    const intervention = makeIntervention()
    render(
      <InterventionPanel
        intervention={intervention}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    const amountInput = document.getElementById("intervention-field-amount") as HTMLInputElement
    expect(amountInput.value).toBe("1000")
  })

  it("字段值变化时调用 onDraftChange", () => {
    const onDraftChange = vi.fn()
    const intervention = makeIntervention()
    render(
      <InterventionPanel
        intervention={intervention}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        draftValues={{ amount: 1000, note: "" }}
        onDraftChange={onDraftChange}
      />,
    )

    const amountInput = document.getElementById("intervention-field-amount") as HTMLInputElement
    fireEvent.change(amountInput, { target: { value: "3000" } })

    // InterventionField 的 number 类型会将字符串 "3000" 转换为数字 3000
    expect(onDraftChange).toHaveBeenCalledWith("amount", 3000)
  })
})

// ---------- 409 修订冲突测试 ----------

describe("InterventionPanel 409 修订冲突", () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("revisionConflict 存在时显示冲突提示", () => {
    const intervention = makeIntervention()
    render(
      <InterventionPanel
        intervention={intervention}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        draftValues={{ amount: 1000 }}
        revisionConflict={{ baseRevision: 5, currentRevision: 7 }}
      />,
    )

    // 验证 role="alert" 存在并包含冲突提示文本
    // 注意：base_revision 编号在 header 与 alert 中均会出现，
    // 因此使用 alert 元素的 textContent 整体校验，避免 getByText 多匹配
    const alert = screen.getByRole("alert")
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveTextContent("检测到修订冲突")
    expect(alert).toHaveTextContent("修订 #5")
    expect(alert).toHaveTextContent("修订 #7")
  })

  it("revisionConflict 存在时提交按钮禁用", () => {
    const intervention = makeIntervention()
    render(
      <InterventionPanel
        intervention={intervention}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        draftValues={{ amount: 1000 }}
        revisionConflict={{ baseRevision: 5, currentRevision: 7 }}
      />,
    )

    const submitBtn = screen.getByRole("button", { name: /提交并继续/ })
    expect(submitBtn).toBeDisabled()
  })

  it("无冲突且必填字段已填时提交按钮启用", () => {
    const intervention = makeIntervention()
    render(
      <InterventionPanel
        intervention={intervention}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        draftValues={{ amount: 1000 }}
      />,
    )

    const submitBtn = screen.getByRole("button", { name: /提交并继续/ })
    expect(submitBtn).not.toBeDisabled()
  })
})

// ---------- 键盘操作测试 ----------

describe("InterventionPanel 键盘操作", () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("按 Escape 键调用 onCancel 关闭面板", () => {
    const onCancel = vi.fn()
    render(
      <InterventionPanel
        intervention={makeIntervention()}
        onSubmit={vi.fn()}
        onCancel={onCancel}
        draftValues={{ amount: 1000 }}
      />,
    )

    fireEvent.keyDown(document.body, { key: "Escape" })
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it("intervention 为 null 时不渲染", () => {
    const { container } = render(
      <InterventionPanel
        intervention={null}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(container.firstChild).toBeNull()
  })
})
