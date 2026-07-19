// 文本风险清单（设计文档 §13.6）：按来源分组，仅展示脱敏预览，不下发原文。
// 每项：类型 + 风险等级 + 脱敏预览 + 来源标签。
import { useMemo } from "react"
import { ScanFace } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  RISK_META,
  SOURCE_META,
  TYPE_META,
  type PrivacySourceType,
  type TextRisk,
} from "@/types/privacy"

export interface TextRiskListProps {
  risks: TextRisk[]
}

function TextRiskItem({ risk }: { risk: TextRisk }) {
  const typeMeta = TYPE_META[risk.type] ?? TYPE_META.unknown
  const riskMeta = RISK_META[risk.risk_level] ?? RISK_META.low
  const TypeIcon = typeMeta.icon
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-border bg-white px-3.5 py-3">
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-foreground">
        <TypeIcon className="h-4 w-4 text-secondary" aria-hidden="true" />
        {typeMeta.label}
      </span>
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
          riskMeta.badgeClass,
        )}
      >
        <span className={cn("inline-block h-1.5 w-1.5 rounded-full", riskMeta.dotClass)} aria-hidden="true" />
        {riskMeta.label}
      </span>
      <code className="min-w-0 flex-1 truncate rounded-md bg-muted px-2 py-1 font-mono text-xs text-muted-foreground">
        {risk.masked}
      </code>
      <span className="text-xs text-muted-foreground">{risk.source_label}</span>
    </li>
  )
}

export function TextRiskList({ risks }: TextRiskListProps) {
  const groups = useMemo(() => {
    const map = new Map<PrivacySourceType, TextRisk[]>()
    for (const risk of risks) {
      const list = map.get(risk.source_type) ?? []
      list.push(risk)
      map.set(risk.source_type, list)
    }
    return Array.from(map.entries()).sort(
      (a, b) => (SOURCE_META[a[0]]?.order ?? 99) - (SOURCE_META[b[0]]?.order ?? 99),
    )
  }, [risks])

  if (risks.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border bg-white px-6 py-10 text-center" role="status">
        <ScanFace className="mx-auto h-7 w-7 text-muted-foreground" aria-hidden="true" />
        <p className="mt-3 text-sm font-medium text-foreground">本轮自动扫描未发现匹配项</p>
        <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-muted-foreground">
          自动识别可能存在遗漏，请在对外分享前检查图片和最终文书。
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-5" role="region" aria-label={`文本风险清单，共 ${risks.length} 项`}>
      {groups.map(([source, items]) => {
        const meta = SOURCE_META[source]
        const SourceIcon = meta.icon
        return (
          <section key={source} aria-label={meta.label}>
            <div className="mb-2 flex items-center gap-2">
              <SourceIcon className="h-4 w-4 text-secondary" aria-hidden="true" />
              <h4 className="text-xs font-semibold uppercase tracking-wide text-secondary">{meta.label}</h4>
              <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full border border-border px-1.5 text-[10px] font-medium text-muted-foreground">
                {items.length}
              </span>
            </div>
            <ul className="space-y-2">
              {items.map((risk, idx) => (
                <TextRiskItem key={`${risk.source_type}-${risk.source_id}-${idx}`} risk={risk} />
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

export default TextRiskList
