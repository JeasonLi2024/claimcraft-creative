/**
 * input-quality-guard Gate 1：QualitySummary 的 warnings 橙色告警测试。
 *
 * 覆盖：
 * 1. 传入 warnings 时渲染告警条（title + detail）
 * 2. quality 为 null 但有 warnings 时仍渲染（不显示"暂无质量报告"）
 * 3. 无 quality 且无 warnings 时显示占位
 */
import { describe, it, expect, afterEach } from "vitest"
import { render, screen, cleanup } from "@testing-library/react"
import { QualitySummary } from "@/components/workflow/QualitySummary"
import type { QualityReport } from "@/types/workflow"

afterEach(() => cleanup())

const passQuality: QualityReport = {
  score: 0.9,
  coverage: 0.95,
  status: "pass",
  blocking_issues: [],
  details: {},
}

describe("QualitySummary warnings", () => {
  it("渲染 Gate 1 橙色告警（title + detail）", () => {
    render(
      <QualitySummary
        quality={passQuality}
        warnings={[
          {
            title: "证据类型匹配度偏低",
            detail: "上传的证据类型与所选案件类型（网购纠纷）匹配度较低（0%）。",
          },
        ]}
      />,
    )
    expect(screen.getByText("证据类型匹配度偏低")).toBeInTheDocument()
    expect(
      screen.getByText(/上传的证据类型与所选案件类型（网购纠纷）匹配度较低/),
    ).toBeInTheDocument()
  })

  it("quality 为 null 但有 warnings 时仍渲染告警", () => {
    render(
      <QualitySummary
        quality={null}
        warnings={[{ title: "证据类型匹配度偏低", detail: "..." }]}
      />,
    )
    expect(screen.getByText("证据类型匹配度偏低")).toBeInTheDocument()
    expect(screen.queryByText("暂无质量报告")).not.toBeInTheDocument()
  })

  it("无 quality 且无 warnings 时显示占位", () => {
    render(<QualitySummary quality={null} />)
    expect(screen.getByText("暂无质量报告")).toBeInTheDocument()
  })
})
