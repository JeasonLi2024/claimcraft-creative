// 通用产物区块（可折叠）+ 节点产物详情
// 参考 spec 第 6.8 节
import { useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { NODE_LABELS, summarizeProducts } from "@/lib/workflow-events"
import type { ProductBlock as ProductBlockType } from "@/lib/workflow-events"

// ---------- 节点产物详情：按节点类型渲染不同 UI ----------

interface PreclassifyRow {
  evidence_id: number
  evidence_code: string
  evidence_category: string
  confidence: number
}

interface OcrRow {
  evidence_id: number
  evidence_code: string
  ocr_corrected_text: string
  ocr_strategy_used: string
  ocr_status: string
  evidence_category: string
}

interface ClassifyRow {
  evidence_id: number
  evidence_code: string
  evidence_category: string
  category_label: string
  confidence: number
}

interface ExtractField {
  field_name: string
  field_value: string
  field_category: string
  confidence: number
}

interface ExtractRow {
  evidence_id: number
  fields: ExtractField[]
  needs_human_review: boolean
}

interface ChainNode {
  datetime: string
  event: string
  category: string
  evidence_codes: string[]
  chain_order: number
}

interface ToolCallLog {
  tool_name: string
  args?: Record<string, unknown>
  result_summary?: string
  result?: unknown
}

const FIELD_CATEGORY_ORDER = [
  "订单信息", "支付信息", "物流信息", "发票信息", "联系信息", "时间信息", "其他",
]

function groupExtractFields(rows: ExtractRow[]) {
  const groups: Record<string, { evidence_id: number; field: ExtractField }[]> = {}
  for (const row of rows) {
    for (const field of row.fields || []) {
      const cat = field.field_category || "其他"
      if (!groups[cat]) groups[cat] = []
      groups[cat].push({ evidence_id: row.evidence_id, field })
    }
  }
  return FIELD_CATEGORY_ORDER.filter((c) => groups[c]?.length).map((c) => ({
    category: c,
    items: groups[c],
  }))
}

function NodeProductsDetail({
  node,
  products,
}: {
  node: string
  products: Record<string, unknown>
}) {
  if (node === "preclassify") {
    const rows = (products.evidence_preclassify_results as PreclassifyRow[]) || []
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[#EAEAEA] text-left text-[#787774]">
              <th className="py-1.5 pr-3 font-medium">证据编号</th>
              <th className="py-1.5 pr-3 font-medium">类别</th>
              <th className="py-1.5 font-medium">置信度</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-[#EAEAEA] last:border-0">
                <td className="py-1.5 pr-3 font-mono text-[#111111]">{r.evidence_code}</td>
                <td className="py-1.5 pr-3 text-[#111111]">{r.evidence_category}</td>
                <td className="py-1.5 text-[#787774]">
                  {(r.confidence * 100).toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (node === "ocr") {
    const rows = (products.evidence_ocr_results as OcrRow[]) || []
    return (
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="rounded-md border border-[#EAEAEA] bg-[#F7F6F3] p-2">
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-xs font-medium text-[#111111]">
                {r.evidence_code}
              </span>
              <span className="text-xs text-[#787774]">{r.ocr_strategy_used}</span>
            </div>
            <p className="text-xs text-[#111111] line-clamp-3 whitespace-pre-wrap">
              {r.ocr_corrected_text?.slice(0, 200) || ""}
              {r.ocr_corrected_text?.length > 200 ? "..." : ""}
            </p>
          </div>
        ))}
      </div>
    )
  }

  if (node === "classify") {
    const rows = (products.evidence_classify_results as ClassifyRow[]) || []
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[#EAEAEA] text-left text-[#787774]">
              <th className="py-1.5 pr-3 font-medium">证据编号</th>
              <th className="py-1.5 pr-3 font-medium">分类标签</th>
              <th className="py-1.5 font-medium">置信度</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-[#EAEAEA] last:border-0">
                <td className="py-1.5 pr-3 font-mono text-[#111111]">{r.evidence_code}</td>
                <td className="py-1.5 pr-3 text-[#111111]">{r.category_label}</td>
                <td className="py-1.5 text-[#787774]">
                  {(r.confidence * 100).toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (node === "extract") {
    const rows = (products.evidence_extract_results as ExtractRow[]) || []
    const groups = groupExtractFields(rows)
    return (
      <div className="space-y-2">
        {groups.map((group) => (
          <div
            key={group.category}
            className="rounded-md border border-[#EAEAEA] overflow-hidden"
          >
            <div className="bg-[#F7F6F3] px-2 py-1 text-xs font-semibold text-[#111111]">
              {group.category}{" "}
              <span className="text-[#787774]">({group.items.length})</span>
            </div>
            <div className="p-2 space-y-1">
              {group.items.map((item, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-[#787774] w-16">
                    EV#{item.evidence_id}
                  </span>
                  <span className="text-[#111111] w-28">{item.field.field_name}</span>
                  <span className="text-[#111111] flex-1">{item.field.field_value}</span>
                  <span className="text-[#787774]">
                    {(item.field.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (node === "evidence_chain") {
    const nodes = (products.evidence_chain as ChainNode[]) || []
    const toolCalls = (products.evidence_chain_tool_calls as ToolCallLog[]) || []
    return (
      <div className="space-y-3">
        <div className="relative pl-4">
          <div className="absolute left-1 top-1 bottom-1 w-0.5 bg-[#EAEAEA]" />
          {nodes.map((n, i) => (
            <div key={i} className="relative pb-2 last:pb-0">
              <span className="absolute -left-3 top-1 w-2 h-2 rounded-full bg-[#111111]" />
              <div className="text-xs font-medium text-[#111111]">{n.event}</div>
              <div className="text-xs text-[#787774]">
                {n.datetime} · {(n.evidence_codes || []).join(", ")}
              </div>
            </div>
          ))}
        </div>
        {toolCalls.length > 0 && (
          <div className="rounded-md border border-[#EAEAEA] bg-[#F7F6F3] p-2">
            <div className="text-xs font-semibold text-[#111111] mb-1">
              工具调用记录（{toolCalls.length} 次）
            </div>
            <div className="space-y-1">
              {toolCalls.map((tc, i) => (
                <div key={i} className="text-xs text-[#787774]">
                  <span className="font-mono text-[#111111]">{tc.tool_name}</span>
                  {tc.result_summary && (
                    <span className="ml-2">{tc.result_summary}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  // complaint / respond_complaint 节点：展示投诉书摘要 + 工具调用日志
  if (node === "complaint" || node === "respond_complaint") {
    const draft = products.complaint_draft as
      | { title?: string; content?: string; tone?: string }
      | undefined
    const toolCalls = (products.complaint_tool_calls as ToolCallLog[]) || []
    return (
      <div className="space-y-2">
        {draft && (
          <div className="rounded-md border border-[#EAEAEA] bg-[#F7F6F3] p-2">
            <div className="text-xs font-semibold text-[#111111] mb-1">
              {draft.title || (node === "respond_complaint" ? "反证答辩书" : "投诉书")}
            </div>
            <p className="text-xs text-[#111111] line-clamp-4 whitespace-pre-wrap">
              {draft.content?.slice(0, 300) || ""}
              {draft.content && draft.content.length > 300 ? "..." : ""}
            </p>
            {draft.tone && (
              <span className="inline-block mt-1 text-xs text-[#787774]">
                语气: {draft.tone}
              </span>
            )}
          </div>
        )}
        {toolCalls.length > 0 && (
          <div className="rounded-md border border-[#EAEAEA] p-2">
            <div className="text-xs font-semibold text-[#111111] mb-1">
              工具调用记录（{toolCalls.length} 次）
            </div>
            <div className="space-y-1">
              {toolCalls.map((tc, i) => (
                <div key={i} className="text-xs text-[#787774]">
                  <span className="font-mono text-[#111111]">{tc.tool_name}</span>
                  {tc.result_summary && (
                    <span className="ml-2">{tc.result_summary}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  return null
}

// ---------- 通用产物区块 ----------

export function ProductBlock({ block }: { block: ProductBlockType }) {
  const [collapsed, setCollapsed] = useState(block.collapsed)
  const { node, products, completedAt } = block

  return (
    <div
      className={`border-l-4 rounded-r-md bg-white border border-[#EAEAEA] ${
        collapsed ? "border-l-slate-300" : "border-l-green-500"
      }`}
    >
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-[#F7F6F3] transition-colors rounded-r-md"
      >
        <span className="text-sm font-medium text-[#111111]">
          {NODE_LABELS[node]}完成 · {summarizeProducts(node, products)}
        </span>
        <div className="flex items-center gap-2">
          {completedAt && (
            <span className="text-xs text-[#787774]">
              {new Date(completedAt).toLocaleTimeString()}
            </span>
          )}
          {collapsed ? (
            <ChevronRight className="w-4 h-4 text-[#787774]" />
          ) : (
            <ChevronDown className="w-4 h-4 text-[#787774]" />
          )}
        </div>
      </button>

      {!collapsed && (
        <div className="px-3 pb-3 text-sm border-t border-[#EAEAEA] pt-2">
          <NodeProductsDetail node={node} products={products} />
        </div>
      )}
    </div>
  )
}
