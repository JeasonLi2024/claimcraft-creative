import { useState } from "react"
import { Link } from "react-router"
import { motion, useReducedMotion } from "framer-motion"
import {
  ArrowRight,
  Archive,
  Check,
  ChevronRight,
  CircleCheck,
  Download,
  Eye,
  FileCheck2,
  FileSearch,
  FileText,
  Fingerprint,
  GitBranch,
  Image,
  LockKeyhole,
  MessageSquareText,
  PackageCheck,
  ScanText,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Store,
  Upload,
} from "lucide-react"
import { useAuthStore } from "@/stores/auth-store"

const EASE = [0.16, 1, 0.3, 1] as const
const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] focus-visible:ring-offset-2 focus-visible:ring-offset-[#f8f8f5]"

const reveal = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.58, ease: EASE } },
}
const stagger = { hidden: {}, visible: { transition: { staggerChildren: 0.07 } } }

const previewTabs = [
  { id: "evidence", label: "证据", icon: ScanText },
  { id: "fields", label: "字段", icon: Fingerprint },
  { id: "draft", label: "文稿", icon: FileText },
] as const

type PreviewTab = (typeof previewTabs)[number]["id"]

const evidenceItems = [
  { code: "E1", type: "订单截图", title: "实付金额与订单号", result: "识别 5 个关键字段", confidence: "可信" },
  { code: "E2", type: "聊天记录", title: "商家承诺 48 小时发货", result: "归类为承诺事件", confidence: "需复核" },
  { code: "E3", type: "退款页面", title: "退款申请被拒绝", result: "进入争议节点", confidence: "可信" },
]

const fieldRows = [
  { label: "订单号", value: "20240315847291", source: "E1 订单截图" },
  { label: "实付金额", value: "1288.00 元", source: "E1 订单截图" },
  { label: "承诺时间", value: "2024-03-16 09:12", source: "E2 聊天记录" },
  { label: "争议类型", value: "延迟发货与拒绝退款", source: "E3 售后记录" },
]

const timelineRows = [
  { date: "03-15", event: "完成付款", code: "E1" },
  { date: "03-16", event: "承诺 48 小时发货", code: "E2" },
  { date: "03-18", event: "退款申请被拒绝", code: "E3" },
]

const outcomes = [
  { title: "原始证据可追溯", icon: Eye },
  { title: "关键字段可校正", icon: FileCheck2 },
  { title: "文稿自动引用证据", icon: MessageSquareText },
  { title: "支持脱敏安全导出", icon: ShieldCheck },
]

const workflow = [
  { index: "01", title: "导入材料", text: "上传订单、聊天、物流、付款凭证和文字说明。", icon: Upload },
  { index: "02", title: "识别并核对事实", text: "抽取时间、金额与承诺内容，低置信度结果交由你确认。", icon: FileSearch },
  { index: "03", title: "生成带依据的材料", text: "重建事实时间线，生成文稿并自动插入证据编号。", icon: GitBranch },
  { index: "04", title: "脱敏并安全导出", text: "遮挡敏感信息，导出 PDF、ZIP 证据包或文本包。", icon: Download },
]

const differences = [
  { title: "事实有来源", text: "关键字段和时间节点都能回到原始截图，不让 AI 擅自补全事实。", icon: FileSearch },
  { title: "文稿有依据", text: "正文自动引用 E1、E2、E3 等证据编号，处理人员可以快速核对。", icon: MessageSquareText },
  { title: "结果可提交", text: "同一案件生成多种模板，并以 PDF、ZIP 证据包或文本包导出。", icon: PackageCheck },
]

const safetyItems = [
  "原始材料始终保留，可随时回看",
  "OCR 与字段抽取结果支持人工校正",
  "需要确认的信息会明确提示复核",
  "文本与图片均支持隐私打码",
]

function BrandMark({ className = "" }: { className?: string }) {
  return <span className={`inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[#181b1a] text-sm font-semibold text-[#f8f8f5] ${className}`} aria-hidden="true">C</span>
}

function PrimaryCta({ compact = false, authenticated = false }: { compact?: boolean; authenticated?: boolean }) {
  return (
    <Link
      to={authenticated ? "/cases" : "/register"}
      className={`group inline-flex shrink-0 items-center justify-center gap-3 rounded-lg bg-[#181b1a] font-semibold text-[#f8f8f5] transition-[background-color,transform] duration-300 hover:bg-[#2b302d] active:translate-y-px ${focusRing} ${compact ? "px-4 py-2 text-sm" : "px-5 py-3 text-base"}`}
    >
      {authenticated ? "进入我的案件" : compact ? "免费开始" : "免费创建第一个案件"}
      <span className="flex h-6 w-6 items-center justify-center rounded-md bg-white/10 transition-transform group-hover:translate-x-0.5">
        <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.7} aria-hidden="true" />
      </span>
    </Link>
  )
}

function SectionHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <motion.div variants={stagger} initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.25 }} className="max-w-[760px]">
      <motion.p variants={reveal} className="mb-3 text-sm font-semibold text-[#3f6b57]">{eyebrow}</motion.p>
      <motion.h2 variants={reveal} className="text-3xl font-semibold leading-tight tracking-[-0.035em] text-[#181b1a] sm:text-4xl lg:text-5xl text-balance">{title}</motion.h2>
      <motion.p variants={reveal} className="mt-4 max-w-[64ch] text-base leading-7 text-[#5f6661]">{description}</motion.p>
    </motion.div>
  )
}

function PreviewPanel() {
  const [activeTab, setActiveTab] = useState<PreviewTab>("evidence")
  const reduce = useReducedMotion()
  const activeMeta = previewTabs.find((tab) => tab.id === activeTab) ?? previewTabs[0]
  const ActiveIcon = activeMeta.icon

  return (
    <motion.div id="product-preview" initial={reduce ? false : { opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.72, delay: 0.12, ease: EASE }} className="relative" aria-label="ClaimCraft 产品界面预览">
      <div className="absolute -left-5 top-8 hidden h-[78%] w-3 rounded-md bg-[#3f6b57] lg:block" aria-hidden="true" />
      <div className="rounded-2xl border border-[#d9ddd5] bg-[#ebece7] p-2 shadow-[0_28px_80px_rgba(31,45,38,.10)]">
        <div className="overflow-hidden rounded-xl border border-[#d9ddd5] bg-[#f8f8f5]">
          <div className="flex flex-col border-b border-[#d9ddd5] bg-white md:flex-row md:items-center md:justify-between">
            <div className="flex min-w-0 items-center gap-3 px-4 py-3">
              <BrandMark className="h-7 w-7" />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">延迟发货退款争议</p>
                <p className="truncate text-xs text-[#6c706b]">示例案件 · 3 条证据已关联</p>
              </div>
            </div>
            <div className="flex border-t border-[#d9ddd5] md:border-l md:border-t-0">
              {previewTabs.map((tab) => {
                const Icon = tab.icon
                const active = activeTab === tab.id
                return (
                  <button key={tab.id} type="button" onClick={() => setActiveTab(tab.id)} className={`flex flex-1 items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition-colors md:flex-none ${focusRing} ${active ? "bg-[#e7eee9] text-[#2f5947]" : "text-[#6c706b] hover:bg-[#f1f2ee] hover:text-[#181b1a]"}`} aria-pressed={active}>
                    <Icon className="h-4 w-4" strokeWidth={1.6} aria-hidden="true" />{tab.label}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="grid min-h-[470px] grid-cols-1 lg:grid-cols-[210px_minmax(0,1fr)]">
            <aside className="border-b border-[#d9ddd5] bg-[#f1f2ee] p-4 lg:border-b-0 lg:border-r">
              <div className="mb-5 flex items-center justify-between">
                <span className="text-xs font-semibold">事实时间线</span>
                <span className="rounded-md bg-[#dfe7e1] px-2 py-1 text-[11px] font-medium text-[#2f5947]">证据已关联</span>
              </div>
              <div className="relative space-y-4 before:absolute before:bottom-2 before:left-[3px] before:top-2 before:w-px before:bg-[#c8cec6]">
                {timelineRows.map((item) => (
                  <div key={item.code} className="relative grid grid-cols-[10px_minmax(0,1fr)] gap-3">
                    <span className="mt-1.5 h-2 w-2 rounded-full bg-[#3f6b57] ring-4 ring-[#e4e9e3]" />
                    <div><p className="font-mono text-[10px] text-[#6c706b]">{item.date} · {item.code}</p><p className="mt-1 text-xs leading-5 text-[#303431]">{item.event}</p></div>
                  </div>
                ))}
              </div>
              <div className="mt-6 rounded-lg border border-[#cfd5cc] bg-white p-3">
                <p className="mb-1 text-xs font-semibold">生成前仍由你确认</p>
                <p className="text-xs leading-5 text-[#6c706b]">系统提示 E2 的承诺时间需要复核。</p>
              </div>
            </aside>

            <div className="p-4 sm:p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#e7eee9] text-[#2f5947]"><ActiveIcon className="h-4 w-4" /></span>
                  <div><p className="text-sm font-semibold">案件整理工作区</p><p className="hidden text-xs text-[#6c706b] sm:block">证据、字段和文稿共用同一事实来源</p></div>
                </div>
                <button type="button" onClick={() => setActiveTab("draft")} className={`inline-flex items-center gap-1 rounded-lg border border-[#cfd5cc] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-[#f1f2ee] ${focusRing}`}>
                  查看生成结果<ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(220px,0.72fr)]">
                <div className="space-y-3">
                  {activeTab === "evidence" && evidenceItems.map((item, index) => (
                    <motion.article key={item.code} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: index * 0.04 }} className="rounded-xl border border-[#d9ddd5] bg-white p-4">
                      <div className="flex items-start gap-3">
                        <span className="rounded-md bg-[#181b1a] px-2 py-1 font-mono text-[11px] font-semibold text-white">{item.code}</span>
                        <div className="min-w-0 flex-1"><p className="text-xs font-medium text-[#3f6b57]">{item.type}</p><h3 className="mt-1 text-sm font-semibold">{item.title}</h3><p className="mt-2 text-xs text-[#6c706b]">{item.result}</p></div>
                        <span className={`rounded-md px-2 py-1 text-[10px] ${item.confidence === "可信" ? "bg-[#e7eee9] text-[#2f5947]" : "bg-[#f5ecda] text-[#8b642b]"}`}>{item.confidence}</span>
                      </div>
                    </motion.article>
                  ))}
                  {activeTab === "fields" && fieldRows.map((row, index) => (
                    <motion.div key={row.label} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: index * 0.04 }} className="grid gap-2 rounded-xl border border-[#d9ddd5] bg-white p-4 sm:grid-cols-[100px_minmax(0,1fr)]">
                      <span className="text-xs font-medium text-[#6c706b]">{row.label}</span><span className="font-mono text-sm">{row.value}</span><span className="text-[11px] text-[#3f6b57] sm:col-start-2">来源：{row.source}</span>
                    </motion.div>
                  ))}
                  {activeTab === "draft" && (
                    <motion.article initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-[#d9ddd5] bg-white p-5">
                      <div className="mb-4 flex flex-wrap gap-2"><span className="rounded-md bg-[#e7eee9] px-2 py-1 text-[11px] font-medium text-[#2f5947]">平台客服版</span><span className="rounded-md bg-[#f1f2ee] px-2 py-1 text-[11px] text-[#6c706b]">可切换 3 类模板</span></div>
                      <h3 className="text-base font-semibold leading-snug">关于订单延迟发货及退款争议的投诉说明</h3>
                      <p className="mt-3 text-sm leading-7 text-[#4d524e]">本人于 3 月 15 日完成付款 <strong className="rounded bg-[#e7eee9] px-1 text-[#2f5947]">E1</strong>。商家次日承诺 48 小时内发货 <strong className="rounded bg-[#e7eee9] px-1 text-[#2f5947]">E2</strong>，但截至 3 月 18 日仍未履行，退款申请随后被拒绝 <strong className="rounded bg-[#e7eee9] px-1 text-[#2f5947]">E3</strong>。</p>
                    </motion.article>
                  )}
                </div>
                <div className="rounded-xl border border-[#d9ddd5] bg-[#f4f5f1] p-4">
                  <div className="mb-4 flex items-center gap-2"><Sparkles className="h-4 w-4 text-[#3f6b57]" /><p className="text-sm font-semibold">最终可获得</p></div>
                  <div className="space-y-2">
                    {[{ icon: FileText, text: "3 类投诉文稿" }, { icon: Archive, text: "ZIP 证据包" }, { icon: Download, text: "正式 PDF 文档" }, { icon: ShieldCheck, text: "脱敏版本" }].map(({ icon: Icon, text }) => (
                      <div key={text} className="flex items-center gap-3 rounded-lg bg-white p-3"><Icon className="h-4 w-4 text-[#3f6b57]" /><span className="text-xs font-medium">{text}</span></div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

export default function HomePage() {
  const reduce = useReducedMotion()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  return (
    <div className="min-h-[100dvh] overflow-x-hidden bg-[#f8f8f5] text-[#181b1a]">
      <a href="#main-content" className={`sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 ${focusRing}`}>跳到主内容</a>
      <header className="sticky top-0 z-30 border-b border-[#d9ddd5]/80 bg-[#f8f8f5]/90 backdrop-blur-md">
        <nav className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to="/home" className={`flex items-center gap-3 rounded-lg ${focusRing}`} aria-label="ClaimCraft 首页"><BrandMark /><span className="font-semibold tracking-[-0.01em]">ClaimCraft</span></Link>
          <div className="flex items-center gap-1 sm:gap-2">
            <a href="#workflow" className={`hidden rounded-lg px-3 py-2 text-sm font-medium text-[#6c706b] hover:text-[#181b1a] md:inline-flex ${focusRing}`}>使用流程</a>
            <a href="#scenarios" className={`hidden rounded-lg px-3 py-2 text-sm font-medium text-[#6c706b] hover:text-[#181b1a] md:inline-flex ${focusRing}`}>适用场景</a>
            {!isAuthenticated && <Link to="/login" className={`rounded-lg px-3 py-2 text-sm font-medium text-[#6c706b] hover:text-[#181b1a] ${focusRing}`}>登录</Link>}
            <PrimaryCta compact authenticated={isAuthenticated} />
          </div>
        </nav>
      </header>

      <main id="main-content">
        <section className="relative border-b border-[#d9ddd5]">
          <div className="mx-auto grid min-h-[calc(100dvh-4rem)] max-w-[1400px] grid-cols-1 items-center gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[minmax(0,0.78fr)_minmax(580px,1.22fr)] lg:gap-12 lg:px-8 lg:py-14">
            <motion.div variants={stagger} initial="hidden" animate="visible" className="max-w-[680px]">
              <motion.div variants={reveal} className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#cfd5cc] bg-white px-3 py-1.5 text-xs font-semibold text-[#3f6b57]"><Sparkles className="h-3.5 w-3.5" />AI 维权材料工作区</motion.div>
              <motion.h1 variants={reveal} className="max-w-[11ch] text-[clamp(2.55rem,6.1vw,5.5rem)] font-semibold leading-[1.04] tracking-[-0.05em] text-balance lg:leading-[0.98]">把零散证据，整理成可提交的维权材料</motion.h1>
              <motion.p variants={reveal} className="mt-6 max-w-[58ch] text-base leading-7 text-[#5f6661] sm:text-lg">上传订单、聊天、物流和付款截图，自动识别关键信息、重建事实时间线并生成带证据引用的投诉材料。导出前，你仍可以逐项核对并完成隐私打码。</motion.p>
              <motion.div variants={reveal} className="mt-8 flex flex-col gap-3 sm:flex-row"><PrimaryCta authenticated={isAuthenticated} /><a href="#workflow" className={`inline-flex items-center justify-center rounded-lg border border-[#cfd5cc] bg-white px-5 py-3 font-semibold transition-colors hover:bg-[#f1f2ee] ${focusRing}`}>查看完整处理流程</a></motion.div>
              <motion.p variants={reveal} className="mt-4 text-xs text-[#7a7f7a]">不替你编造事实 · 生成前始终由你确认</motion.p>
            </motion.div>
            <motion.div initial={reduce ? false : { opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.7, delay: 0.08, ease: EASE }} className="min-w-0"><PreviewPanel /></motion.div>
          </div>
          <div className="mx-auto grid max-w-[1400px] grid-cols-2 border-x border-t border-[#d9ddd5] bg-white sm:grid-cols-4">
            {outcomes.map(({ title, icon: Icon }, index) => <div key={title} className={`flex items-center gap-3 px-4 py-4 sm:px-5 ${index % 2 ? "border-l" : ""} ${index > 1 ? "border-t sm:border-t-0" : ""} sm:border-l sm:first:border-l-0`}><Icon className="h-4 w-4 shrink-0 text-[#3f6b57]" /><span className="text-xs font-medium sm:text-sm">{title}</span></div>)}
          </div>
        </section>

        <section className="border-b border-[#d9ddd5] px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
          <div className="mx-auto max-w-[1400px]">
            <SectionHeading eyebrow="一个案例，完整说明" title="不是只识别截图，而是把材料组织成结果" description="以一笔延迟发货退款争议为例，ClaimCraft 让输入、事实与最终文稿保持可追溯的关联。" />
            <motion.div variants={stagger} initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.15 }} className="mt-10 grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:items-stretch">
              {[
                { label: "输入", title: "零散原始材料", icon: Image, items: ["订单与付款截图", "商家聊天记录", "物流与售后页面"] },
                { label: "整理", title: "可核对的事实", icon: FileSearch, items: ["字段保留证据来源", "自动重建时间线", "低置信度提示复核"] },
                { label: "输出", title: "可提交的材料包", icon: PackageCheck, items: ["带 E1 / E2 引用的文稿", "平台 / 监管 / 仲裁模板", "PDF / ZIP / 文本包"] },
              ].map((item, index) => (
                <div key={item.label} className="contents">
                  <motion.article variants={reveal} className="rounded-2xl border border-[#d9ddd5] bg-white p-6 lg:p-8">
                    <div className="flex items-center justify-between"><span className="font-mono text-xs font-semibold text-[#3f6b57]">{item.label}</span><item.icon className="h-5 w-5 text-[#3f6b57]" /></div>
                    <h3 className="mt-8 text-xl font-semibold">{item.title}</h3><div className="mt-5 space-y-3">{item.items.map((text) => <p key={text} className="flex items-center gap-3 text-sm text-[#5f6661]"><Check className="h-4 w-4 shrink-0 text-[#3f6b57]" />{text}</p>)}</div>
                  </motion.article>
                  {index < 2 && <div className="hidden items-center justify-center lg:flex"><ArrowRight className="h-5 w-5 text-[#9aa19b]" /></div>}
                </div>
              ))}
            </motion.div>
          </div>
        </section>

        <section id="workflow" className="scroll-mt-16 border-b border-[#d9ddd5] bg-[#181b1a] px-4 py-16 text-[#f8f8f5] sm:px-6 lg:px-8 lg:py-24">
          <div className="mx-auto max-w-[1400px]">
            <div className="max-w-[760px]"><p className="mb-3 text-sm font-semibold text-[#9fc0ae]">完整工作流</p><h2 className="text-3xl font-semibold leading-tight tracking-[-0.035em] sm:text-4xl lg:text-5xl text-balance">从第一张截图，到一套安全可提交的材料</h2><p className="mt-4 text-base leading-7 text-[#b8bdb9]">自动化缩短整理过程，关键事实、生成内容和最终导出仍由你决定。</p></div>
            <motion.div variants={stagger} initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.15 }} className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-white/15 bg-white/15 md:grid-cols-2 xl:grid-cols-4">
              {workflow.map(({ index, title, text, icon: Icon }) => <motion.article key={index} variants={reveal} className="bg-[#181b1a] p-6 lg:p-8"><div className="flex items-center justify-between"><span className="font-mono text-xs text-[#9fc0ae]">{index}</span><Icon className="h-5 w-5 text-[#9fc0ae]" /></div><h3 className="mt-12 text-xl font-semibold">{title}</h3><p className="mt-3 text-sm leading-6 text-[#b8bdb9]">{text}</p></motion.article>)}
            </motion.div>
          </div>
        </section>

        <section className="border-b border-[#d9ddd5] px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
          <div className="mx-auto max-w-[1400px]">
            <SectionHeading eyebrow="为什么是 ClaimCraft" title="不只生成文字，更整理事实与依据" description="普通 AI 可以帮你润色一段话；ClaimCraft 关注的是证据从哪里来、事实是否准确，以及最终材料能否提交。" />
            <motion.div variants={stagger} initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.2 }} className="mt-10 grid gap-3 lg:grid-cols-3">
              {differences.map(({ title, text, icon: Icon }) => <motion.article key={title} variants={reveal} className="rounded-2xl border border-[#d9ddd5] bg-white p-6 lg:p-8"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#e7eee9] text-[#2f5947]"><Icon className="h-5 w-5" /></span><h3 className="mt-8 text-xl font-semibold">{title}</h3><p className="mt-3 text-sm leading-6 text-[#5f6661]">{text}</p></motion.article>)}
            </motion.div>
          </div>
        </section>

        <section id="scenarios" className="scroll-mt-16 border-b border-[#d9ddd5] px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
          <div className="mx-auto grid max-w-[1400px] gap-10 lg:grid-cols-[0.72fr_1.28fr] lg:items-start">
            <SectionHeading eyebrow="适用场景" title="既能整理投诉，也能组织反证" description="消费者与小微商家面对的是同一个难题：材料散乱、事实难讲清、证据难以快速定位。" />
            <motion.div variants={stagger} initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.2 }} className="grid gap-3 md:grid-cols-2">
              <motion.article variants={reveal} className="rounded-2xl border border-[#d9ddd5] bg-white p-6 lg:p-8"><ShoppingBag className="h-6 w-6 text-[#3f6b57]" /><p className="mt-8 text-xs font-semibold text-[#3f6b57]">消费者维权</p><h3 className="mt-2 text-2xl font-semibold">把纠纷讲清楚</h3><p className="mt-4 text-sm leading-6 text-[#5f6661]">适用于网购退款、虚假宣传、货不对板、售后拖延和服务违约。</p></motion.article>
              <motion.article variants={reveal} className="rounded-2xl border border-[#d9ddd5] bg-[#e7eee9] p-6 lg:p-8"><Store className="h-6 w-6 text-[#2f5947]" /><p className="mt-8 text-xs font-semibold text-[#3f6b57]">商家反证</p><h3 className="mt-2 text-2xl font-semibold">把履约依据理清楚</h3><p className="mt-4 text-sm leading-6 text-[#4f6258]">适用于恶意投诉、履约记录整理、售后沟通举证与订单物流反证。</p></motion.article>
            </motion.div>
          </div>
        </section>

        <section className="border-b border-[#d9ddd5] px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
          <div className="mx-auto grid max-w-[1400px] overflow-hidden rounded-2xl border border-[#d9ddd5] bg-white lg:grid-cols-2">
            <div className="p-6 sm:p-8 lg:p-12"><div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#181b1a] text-white"><LockKeyhole className="h-5 w-5" /></div><p className="mt-10 text-sm font-semibold text-[#3f6b57]">安全与人工控制</p><h2 className="mt-3 max-w-[13ch] text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">自动整理，但不替你做事实判断</h2><p className="mt-5 max-w-[54ch] text-base leading-7 text-[#5f6661]">ClaimCraft 将原始材料、识别结果和生成文稿并排组织，让每次修改都有依据。</p></div>
            <div className="border-t border-[#d9ddd5] bg-[#f1f2ee] p-6 sm:p-8 lg:border-l lg:border-t-0 lg:p-12"><div className="grid gap-3">{safetyItems.map((item) => <div key={item} className="flex items-start gap-3 rounded-xl border border-[#d9ddd5] bg-white p-4"><CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-[#3f6b57]" /><span className="text-sm leading-6">{item}</span></div>)}</div></div>
          </div>
        </section>

        <section className="px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
          <motion.div variants={stagger} initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.25 }} className="mx-auto grid max-w-[1400px] gap-8 rounded-2xl bg-[#3f6b57] p-6 text-white sm:p-8 lg:grid-cols-[1fr_auto] lg:items-center lg:p-12">
            <div><motion.p variants={reveal} className="text-sm font-semibold text-[#d3e3da]">从第一份材料开始</motion.p><motion.h2 variants={reveal} className="mt-3 max-w-[820px] text-3xl font-semibold leading-tight tracking-[-0.035em] sm:text-4xl">先把事实和证据整理清楚，再开始表达诉求</motion.h2><motion.p variants={reveal} className="mt-4 max-w-[66ch] text-base leading-7 text-[#d3e3da]">创建案件，上传第一份证据。你可以在生成前核对字段、修改时间线，并决定是否脱敏导出。</motion.p></div>
            <motion.div variants={reveal}><Link to={isAuthenticated ? "/cases" : "/register"} className={`group inline-flex items-center justify-center gap-3 rounded-lg bg-white px-5 py-3 font-semibold text-[#181b1a] transition-colors hover:bg-[#f1f2ee] ${focusRing}`}>{isAuthenticated ? "进入我的案件" : "免费创建案件"}<ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" /></Link></motion.div>
          </motion.div>
        </section>
      </main>

      <footer className="border-t border-[#d9ddd5] px-4 py-8 sm:px-6 lg:px-8"><div className="mx-auto flex max-w-[1400px] flex-col gap-4 text-sm text-[#6c706b] sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-3"><BrandMark className="h-7 w-7" /><span className="font-semibold text-[#181b1a]">ClaimCraft</span><span>维权材料工坊</span></div><div className="flex gap-5">{!isAuthenticated && <Link to="/login" className={`hover:text-[#181b1a] ${focusRing}`}>登录</Link>}<a href="#workflow" className={`hover:text-[#181b1a] ${focusRing}`}>使用流程</a><a href="#scenarios" className={`hover:text-[#181b1a] ${focusRing}`}>适用场景</a></div></div></footer>
    </div>
  )
}
