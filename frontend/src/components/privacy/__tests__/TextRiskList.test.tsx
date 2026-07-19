/**
 * 文本风险清单：按来源分组、显示脱敏预览与风险等级、不泄露原文、空状态。
 */
import { describe, it, expect, afterEach } from "vitest"
import { render, screen, cleanup } from "@testing-library/react"
import { TextRiskList } from "@/components/privacy/TextRiskList"
import type { TextRisk } from "@/types/privacy"

afterEach(() => cleanup())

const risks: TextRisk[] = [
  {
    evidence_code: "E1",
    source_type: "ocr",
    source_label: "E1 · OCR 文本",
    source_id: 1,
    type: "phone",
    risk_level: "medium",
    masked: "138****8000",
  },
  {
    evidence_code: null,
    source_type: "document",
    source_label: "最新投诉书",
    source_id: 9,
    type: "id_card",
    risk_level: "high",
    masked: "130***********8888",
  },
]

describe("TextRiskList", () => {
  it("按来源分组并渲染类型/风险/脱敏预览", () => {
    render(<TextRiskList risks={risks} />)
    // 分组标题
    expect(screen.getByText("最新文书")).toBeInTheDocument()
    expect(screen.getByText("OCR 文本")).toBeInTheDocument()
    // 类型 + 风险等级
    expect(screen.getByText("手机号")).toBeInTheDocument()
    expect(screen.getByText("身份证号")).toBeInTheDocument()
    expect(screen.getByText("高风险")).toBeInTheDocument()
    expect(screen.getByText("中风险")).toBeInTheDocument()
    // 脱敏预览可见
    expect(screen.getByText("138****8000")).toBeInTheDocument()
    // 不泄露原文
    expect(screen.queryByText("13800138000")).not.toBeInTheDocument()
  })

  it("空清单显示未发现文案（含遗漏提示）", () => {
    render(<TextRiskList risks={[]} />)
    expect(screen.getByText("本轮自动扫描未发现匹配项")).toBeInTheDocument()
    expect(screen.getByText(/自动识别可能存在遗漏/)).toBeInTheDocument()
  })
})
