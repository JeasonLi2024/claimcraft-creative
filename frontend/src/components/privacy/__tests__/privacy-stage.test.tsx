/**
 * 隐私阶段派生 + 状态条渲染测试。
 */
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, screen, cleanup, fireEvent } from "@testing-library/react"
import { PrivacyStatusBar } from "@/components/privacy/PrivacyStatusBar"
import { derivePrivacyStage } from "@/types/privacy"

afterEach(() => cleanup())

describe("derivePrivacyStage", () => {
  it("无文本风险且无图片 → empty", () => {
    expect(derivePrivacyStage({ textRiskCount: 0, imageTotal: 0, imageDone: 0, imageFailed: 0 })).toBe("empty")
  })
  it("有失败图片 → partial_failed（优先级最高）", () => {
    expect(derivePrivacyStage({ textRiskCount: 0, imageTotal: 3, imageDone: 2, imageFailed: 1 })).toBe("partial_failed")
  })
  it("图片未全部完成 → review_required", () => {
    expect(derivePrivacyStage({ textRiskCount: 0, imageTotal: 3, imageDone: 1, imageFailed: 0 })).toBe("review_required")
  })
  it("图片全部完成但仍有文本风险 → review_required", () => {
    expect(derivePrivacyStage({ textRiskCount: 2, imageTotal: 2, imageDone: 2, imageFailed: 0 })).toBe("review_required")
  })
  it("图片全部完成且无文本风险 → masked_done", () => {
    expect(derivePrivacyStage({ textRiskCount: 0, imageTotal: 2, imageDone: 2, imageFailed: 0 })).toBe("masked_done")
  })
})

describe("PrivacyStatusBar", () => {
  it("渲染阶段标题、说明与主操作，点击触发回调", () => {
    const onPrimary = vi.fn()
    render(<PrivacyStatusBar stage="partial_failed" onPrimary={onPrimary} />)
    expect(screen.getByText("部分图片处理失败")).toBeInTheDocument()
    const btn = screen.getByRole("button", { name: "重试失败项" })
    fireEvent.click(btn)
    expect(onPrimary).toHaveBeenCalledTimes(1)
  })

  it("附带进度说明文案", () => {
    render(<PrivacyStatusBar stage="masked_done" progressText="已处理 2 / 2 张。" />)
    expect(screen.getByText(/已处理 2 \/ 2 张/)).toBeInTheDocument()
  })
})
