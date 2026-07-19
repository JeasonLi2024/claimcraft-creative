/**
 * input-quality-guard Gate 2：InterventionField 的 radio 字段类型测试。
 *
 * 覆盖：
 * 1. radio 选项渲染（label 文案）
 * 2. 选中态反映 value
 * 3. 点击选项触发 onChange(选项值)
 */
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, screen, fireEvent, cleanup } from "@testing-library/react"
import { InterventionField, type FormField } from "@/components/workflow/InterventionField"

afterEach(() => cleanup())

const radioField: FormField = {
  name: "action",
  label: "处理方式",
  type: "radio",
  required: true,
  initial_value: "confirm_continue",
  options: [
    { value: "confirm_continue", label: "我了解风险，继续生成（输出质量可能较低）" },
    { value: "abort", label: "终止本次工作流，我将重新上传证据" },
  ],
}

describe("InterventionField radio", () => {
  it("渲染所有单选项", () => {
    render(<InterventionField field={radioField} value="" onChange={() => {}} />)
    expect(
      screen.getByText("我了解风险，继续生成（输出质量可能较低）"),
    ).toBeInTheDocument()
    expect(
      screen.getByText("终止本次工作流，我将重新上传证据"),
    ).toBeInTheDocument()
    // radiogroup 语义
    expect(screen.getByRole("radiogroup", { name: "处理方式" })).toBeInTheDocument()
  })

  it("选中态反映当前 value", () => {
    render(<InterventionField field={radioField} value="abort" onChange={() => {}} />)
    const radios = screen.getAllByRole("radio") as HTMLInputElement[]
    // 第二个（abort）应被选中
    const abort = radios.find((r) => r.value === "abort")
    const confirm = radios.find((r) => r.value === "confirm_continue")
    expect(abort?.checked).toBe(true)
    expect(confirm?.checked).toBe(false)
  })

  it("点击选项触发 onChange(选项值)", () => {
    const onChange = vi.fn()
    render(<InterventionField field={radioField} value="confirm_continue" onChange={onChange} />)
    fireEvent.click(screen.getByText("终止本次工作流，我将重新上传证据"))
    expect(onChange).toHaveBeenCalledWith("abort")
  })
})
