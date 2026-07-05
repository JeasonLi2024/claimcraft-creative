import { useMemo, useState } from "react"
import { Link } from "react-router"
import { motion, useReducedMotion } from "framer-motion"
import {
  ArrowRight,
  Check,
  ChevronRight,
  FileSearch,
  FileText,
  Fingerprint,
  GitBranch,
  ScanText,
  Sparkles,
} from "lucide-react"

const EASE = [0.16, 1, 0.3, 1] as const

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] focus-visible:ring-offset-2 focus-visible:ring-offset-[#f8f8f5]"

const reveal = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: EASE } },
}

const stagger = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.04,
    },
  },
}

const capabilities = [
  {
    title: "证据识别",
    text: "截图、聊天、订单、物流记录统一进入同一案件视图。",
    icon: ScanText,
  },
  {
    title: "字段抽取",
    text: "金额、订单号、时间、当事人自动结构化，并保留置信度。",
    icon: FileSearch,
  },
  {
    title: "时间线整理",
    text: "按事件发生顺序归并事实，减少人工翻截图的成本。",
    icon: GitBranch,
  },
  {
    title: "投诉成稿",
    text: "基于证据链生成可编辑文稿，导出前仍可逐条核对。",
    icon: FileText,
  },
]

const previewTabs = [
  { id: "evidence", label: "证据", icon: ScanText },
  { id: "fields", label: "字段", icon: Fingerprint },
  { id: "draft", label: "文稿", icon: FileText },
] as const

type PreviewTab = (typeof previewTabs)[number]["id"]

const evidenceItems = [
  {
    type: "订单截图",
    title: "实付金额与订单号",
    meta: "淘宝订单页",
    result: "识别 5 个关键字段",
    confidence: "可信",
  },
  {
    type: "聊天记录",
    title: "商家承诺 48 小时发货",
    meta: "客服对话",
    result: "归类为承诺事件",
    confidence: "需复核",
  },
  {
    type: "退款页面",
    title: "退款申请被拒绝",
    meta: "售后记录",
    result: "进入争议节点",
    confidence: "可信",
  },
]

const fieldRows = [
  { label: "订单号", value: "20240315847291", source: "订单截图" },
  { label: "实付金额", value: "1288.00 元", source: "订单截图" },
  { label: "承诺时间", value: "2024-03-16 09:12", source: "聊天记录" },
  { label: "争议类型", value: "延迟发货与拒绝退款", source: "售后记录" },
]

const timelineRows = [
  { date: "03-15 14:23", event: "用户完成付款" },
  { date: "03-16 09:12", event: "商家承诺 48 小时内发货" },
  { date: "03-18 20:05", event: "退款申请被系统拒绝" },
]

const workflow = [
  { title: "收集证据", text: "上传截图和聊天记录，系统自动建立案件资料夹。" },
  { title: "核对事实", text: "抽取结果和原始证据并排展示，方便人工确认。" },
  { title: "生成材料", text: "形成投诉正文、时间线和附件清单，减少重复整理。" },
]

function BrandMark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[#181b1a] text-sm font-semibold text-[#f8f8f5] ${className}`}
      aria-hidden="true"
    >
      C
    </span>
  )
}

function PrimaryCta({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      to="/register"
      className={`group inline-flex shrink-0 items-center justify-center gap-3 rounded-lg bg-[#181b1a] font-semibold text-[#f8f8f5] transition-[background-color,transform] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#2b302d] active:translate-y-px ${focusRing} ${
        compact ? "px-4 py-2 text-sm" : "px-5 py-3 text-base"
      }`}
    >
      开始整理案件
      <span className="flex h-6 w-6 items-center justify-center rounded-md bg-[#f8f8f5]/12 transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:translate-x-0.5">
        <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.7} aria-hidden="true" />
      </span>
    </Link>
  )
}

function PreviewPanel() {
  const [activeTab, setActiveTab] = useState<PreviewTab>("evidence")
  const reduce = useReducedMotion()
  const ActiveIcon = useMemo(
    () => previewTabs.find((tab) => tab.id === activeTab)?.icon ?? ScanText,
    [activeTab]
  )

  return (
    <motion.div
      id="product-preview"
      initial={reduce ? false : { opacity: 0, y: 22 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.72, delay: 0.12, ease: EASE }}
      className="relative"
      aria-label="ClaimCraft 产品界面预览"
    >
      <div className="absolute -left-5 top-8 hidden h-[78%] w-3 rounded-md bg-[#3f6b57] lg:block" aria-hidden="true" />
      <div className="rounded-2xl border border-[#d9ddd5] bg-[#ebece7] p-2">
        <div className="overflow-hidden rounded-xl border border-[#d9ddd5] bg-[#f8f8f5]">
          <div className="flex flex-col border-b border-[#d9ddd5] bg-[#ffffff] md:flex-row md:items-center md:justify-between">
            <div className="flex min-w-0 items-center gap-3 px-4 py-3">
              <BrandMark className="h-7 w-7" />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-[#181b1a]">延迟发货退款争议</p>
                <p className="truncate text-xs text-[#6c706b]">案件资料已整理 7 条证据</p>
              </div>
            </div>
            <div className="flex border-t border-[#d9ddd5] md:border-l md:border-t-0">
              {previewTabs.map((tab) => {
                const Icon = tab.icon
                const active = activeTab === tab.id
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex flex-1 items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition-colors duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] md:flex-none ${focusRing} ${
                      active
                        ? "bg-[#e7eee9] text-[#2f5947]"
                        : "text-[#6c706b] hover:bg-[#f1f2ee] hover:text-[#181b1a]"
                    }`}
                    aria-pressed={active}
                  >
                    <Icon className="h-4 w-4" strokeWidth={1.6} aria-hidden="true" />
                    {tab.label}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="grid min-h-[480px] grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)]">
            <aside className="border-b border-[#d9ddd5] bg-[#f1f2ee] p-4 lg:border-b-0 lg:border-r">
              <div className="mb-5 flex items-center justify-between">
                <span className="text-xs font-semibold text-[#181b1a]">证据链</span>
                <span className="rounded-md bg-[#dfe7e1] px-2 py-1 text-[11px] font-medium text-[#2f5947]">
                  可提交
                </span>
              </div>
              <div className="space-y-3">
                {timelineRows.map((item) => (
                  <div key={item.date} className="grid grid-cols-[72px_minmax(0,1fr)] gap-3">
                    <span className="font-mono text-[11px] text-[#6c706b]">{item.date}</span>
                    <span className="text-xs leading-5 text-[#303431]">{item.event}</span>
                  </div>
                ))}
              </div>
              <div className="mt-6 rounded-lg border border-[#cfd5cc] bg-[#ffffff] p-3">
                <p className="mb-2 text-xs font-semibold text-[#181b1a]">下一步建议</p>
                <p className="text-xs leading-5 text-[#6c706b]">
                  补充物流停滞截图后，可生成更完整的附件清单。
                </p>
              </div>
            </aside>

            <div className="p-4 sm:p-5">
              <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#e7eee9] text-[#2f5947]">
                    <ActiveIcon className="h-4 w-4" strokeWidth={1.6} aria-hidden="true" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-[#181b1a]">案件整理工作区</p>
                    <p className="text-xs text-[#6c706b]">原始证据、结构化字段和文稿共用同一事实来源</p>
                  </div>
                </div>
                <button
                  type="button"
                  className={`inline-flex items-center justify-center gap-2 rounded-lg border border-[#cfd5cc] bg-[#ffffff] px-3 py-2 text-sm font-medium text-[#303431] transition-colors duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#f1f2ee] active:translate-y-px ${focusRing}`}
                >
                  核对并生成
                  <ChevronRight className="h-4 w-4" strokeWidth={1.7} aria-hidden="true" />
                </button>
              </div>

              <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(260px,0.9fr)]">
                <div className="space-y-3">
                  {activeTab === "evidence" &&
                    evidenceItems.map((item, index) => (
                      <motion.article
                        key={item.title}
                        initial={reduce ? false : { opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.42, delay: index * 0.05, ease: EASE }}
                        className="rounded-xl border border-[#d9ddd5] bg-[#ffffff] p-4"
                      >
                        <div className="mb-3 flex items-start justify-between gap-4">
                          <div>
                            <p className="text-xs font-medium text-[#3f6b57]">{item.type}</p>
                            <h3 className="mt-1 text-base font-semibold text-[#181b1a]">{item.title}</h3>
                          </div>
                          <span className="rounded-md bg-[#f1f2ee] px-2 py-1 text-[11px] text-[#6c706b]">
                            {item.confidence}
                          </span>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          <p className="rounded-lg bg-[#f4f5f1] px-3 py-2 text-xs text-[#6c706b]">{item.meta}</p>
                          <p className="rounded-lg bg-[#e7eee9] px-3 py-2 text-xs font-medium text-[#2f5947]">
                            {item.result}
                          </p>
                        </div>
                      </motion.article>
                    ))}

                  {activeTab === "fields" &&
                    fieldRows.map((row, index) => (
                      <motion.div
                        key={row.label}
                        initial={reduce ? false : { opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.42, delay: index * 0.05, ease: EASE }}
                        className="grid gap-3 rounded-xl border border-[#d9ddd5] bg-[#ffffff] p-4 sm:grid-cols-[120px_minmax(0,1fr)_110px]"
                      >
                        <span className="text-sm font-medium text-[#6c706b]">{row.label}</span>
                        <span className="min-w-0 break-words font-mono text-sm text-[#181b1a]">{row.value}</span>
                        <span className="text-xs text-[#6c706b] sm:text-right">{row.source}</span>
                      </motion.div>
                    ))}

                  {activeTab === "draft" && (
                    <motion.article
                      initial={reduce ? false : { opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.42, ease: EASE }}
                      className="rounded-xl border border-[#d9ddd5] bg-[#ffffff] p-5"
                    >
                      <p className="mb-4 text-xs font-semibold text-[#3f6b57]">投诉材料草稿</p>
                      <h3 className="mb-3 text-lg font-semibold leading-snug text-[#181b1a]">
                        关于订单 20240315847291 延迟发货及退款争议的投诉说明
                      </h3>
                      <p className="text-sm leading-7 text-[#4d524e]">
                        本人于 2024 年 3 月 15 日完成付款。商家于次日承诺 48 小时内发货，
                        但截至 3 月 18 日仍未履行。本人发起退款申请后被拒绝，现提交订单、
                        对话记录和售后页面作为证明材料。
                      </p>
                    </motion.article>
                  )}
                </div>

                <div className="rounded-xl border border-[#d9ddd5] bg-[#f4f5f1] p-4">
                  <div className="mb-4 flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-[#3f6b57]" strokeWidth={1.6} aria-hidden="true" />
                    <p className="text-sm font-semibold text-[#181b1a]">生成前检查</p>
                  </div>
                  <div className="space-y-3">
                    {["订单金额已确认", "时间线存在原始证据", "争议诉求表述清楚", "个人信息可脱敏导出"].map(
                      (item) => (
                        <div key={item} className="flex items-start gap-3 rounded-lg bg-[#ffffff] p-3">
                          <Check className="mt-0.5 h-4 w-4 shrink-0 text-[#3f6b57]" strokeWidth={1.8} aria-hidden="true" />
                          <span className="text-sm leading-5 text-[#303431]">{item}</span>
                        </div>
                      )
                    )}
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

  return (
    <div className="min-h-[100dvh] overflow-x-hidden bg-[#f8f8f5] text-[#181b1a]">
      <a
        href="#main-content"
        className={`sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-40 focus:rounded-lg focus:border focus:border-[#d9ddd5] focus:bg-[#ffffff] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold ${focusRing}`}
      >
        跳到主内容
      </a>

      <header className="sticky top-0 z-30 border-b border-[#d9ddd5]/80 bg-[#f8f8f5]/88 backdrop-blur-md">
        <nav className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to="/home" className={`flex items-center gap-3 rounded-lg ${focusRing}`} aria-label="ClaimCraft 首页">
            <BrandMark />
            <span className="text-base font-semibold tracking-[-0.01em] text-[#181b1a]">ClaimCraft</span>
          </Link>
          <div className="flex items-center gap-2">
            <a
              href="#capabilities"
              className={`hidden rounded-lg px-3 py-2 text-sm font-medium text-[#6c706b] transition-colors hover:text-[#181b1a] sm:inline-flex ${focusRing}`}
            >
              核心能力
            </a>
            <Link
              to="/login"
              className={`rounded-lg px-3 py-2 text-sm font-medium text-[#6c706b] transition-colors hover:text-[#181b1a] ${focusRing}`}
            >
              登录
            </Link>
            <PrimaryCta compact />
          </div>
        </nav>
      </header>

      <main id="main-content">
        <section className="relative border-b border-[#d9ddd5]">
          <div className="mx-auto grid min-h-[calc(100dvh-4rem)] max-w-[1400px] grid-cols-1 items-center gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[minmax(0,0.82fr)_minmax(560px,1.18fr)] lg:gap-12 lg:px-8 lg:py-14">
            <motion.div
              variants={stagger}
              initial="hidden"
              animate="visible"
              className="max-w-[680px] lg:pb-8"
            >
              <motion.p variants={reveal} className="mb-5 text-sm font-semibold text-[#3f6b57]">
                ClaimCraft 维权材料工坊
              </motion.p>
              <motion.h1
                variants={reveal}
                className="max-w-[11ch] text-[clamp(2.45rem,6.2vw,5.7rem)] font-semibold leading-[1.08] tracking-[-0.045em] text-[#181b1a] text-balance sm:leading-[1.02] lg:leading-[0.96] lg:tracking-[-0.055em]"
              >
                将维权证据整理成可提交材料
              </motion.h1>
              <motion.p
                variants={reveal}
                className="mt-6 max-w-[56ch] text-base leading-7 text-[#5f6661] sm:text-lg"
              >
                OCR、字段抽取、时间线和投诉成稿放在一个案件工作区里，减少反复复制和人工核对。
              </motion.p>
              <motion.div variants={reveal} className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
                <PrimaryCta />
                <a
                  href="#product-preview"
                  className={`inline-flex shrink-0 items-center justify-center rounded-lg border border-[#cfd5cc] bg-[#ffffff] px-5 py-3 text-base font-semibold text-[#303431] transition-[background-color,transform] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#f1f2ee] active:translate-y-px ${focusRing}`}
                >
                  查看界面预览
                </a>
              </motion.div>
            </motion.div>

            <motion.div
              initial={reduce ? false : { opacity: 0, x: 18 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.7, delay: 0.08, ease: EASE }}
              className="min-w-0"
            >
              <PreviewPanel />
            </motion.div>
          </div>
        </section>

        <section id="capabilities" className="border-b border-[#d9ddd5] px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
          <div className="mx-auto max-w-[1400px]">
            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.25 }}
              className="max-w-[760px]"
            >
              <motion.h2
                variants={reveal}
                className="text-3xl font-semibold leading-tight tracking-[-0.035em] text-[#181b1a] sm:text-4xl lg:text-5xl text-balance"
              >
                首页展示的是产品能力，不是装饰图
              </motion.h2>
              <motion.p variants={reveal} className="mt-4 max-w-[62ch] text-base leading-7 text-[#5f6661]">
                每个模块都对应实际工作台里的处理环节，适合从订单截图、聊天记录和售后页面整理投诉材料。
              </motion.p>
            </motion.div>

            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.2 }}
              className="mt-10 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-[1.15fr_0.85fr_1fr]"
            >
              {capabilities.map((item, index) => {
                const Icon = item.icon
                return (
                  <motion.article
                    key={item.title}
                    variants={reveal}
                    className={`rounded-xl border border-[#d9ddd5] bg-[#ffffff] p-6 transition-[border-color,transform] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-0.5 hover:border-[#bfc8bd] ${
                      index === 0 ? "lg:row-span-2 lg:p-8" : ""
                    } ${index === 3 ? "lg:col-span-2" : ""}`}
                  >
                    <div className="mb-6 flex h-10 w-10 items-center justify-center rounded-lg bg-[#e7eee9] text-[#2f5947]">
                      <Icon className="h-5 w-5" strokeWidth={1.6} aria-hidden="true" />
                    </div>
                    <h3 className="text-xl font-semibold tracking-[-0.02em] text-[#181b1a]">{item.title}</h3>
                    <p className="mt-3 max-w-[44ch] text-sm leading-6 text-[#5f6661]">{item.text}</p>
                  </motion.article>
                )
              })}
            </motion.div>
          </div>
        </section>

        <section className="border-b border-[#d9ddd5] px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
          <div className="mx-auto grid max-w-[1400px] gap-10 lg:grid-cols-[0.72fr_1.28fr] lg:items-start">
            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.25 }}
              className="max-w-[560px]"
            >
              <motion.h2 variants={reveal} className="text-3xl font-semibold leading-tight tracking-[-0.035em] sm:text-4xl">
                工作流更短，人工判断仍在
              </motion.h2>
              <motion.p variants={reveal} className="mt-4 text-base leading-7 text-[#5f6661]">
                ClaimCraft 不替你编造事实。它把证据、字段和材料组织起来，让确认和修改更快。
              </motion.p>
            </motion.div>

            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.2 }}
              className="grid gap-3 md:grid-cols-3"
            >
              {workflow.map((item) => (
                <motion.article key={item.title} variants={reveal} className="rounded-xl border border-[#d9ddd5] bg-[#ffffff] p-6">
                  <h3 className="text-lg font-semibold tracking-[-0.02em] text-[#181b1a]">{item.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-[#5f6661]">{item.text}</p>
                </motion.article>
              ))}
            </motion.div>
          </div>
        </section>

        <section className="px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.25 }}
            className="mx-auto grid max-w-[1400px] gap-8 rounded-2xl border border-[#d9ddd5] bg-[#ffffff] p-6 sm:p-8 lg:grid-cols-[1fr_auto] lg:items-center lg:p-10"
          >
            <div>
              <motion.h2 variants={reveal} className="max-w-[760px] text-3xl font-semibold leading-tight tracking-[-0.035em] sm:text-4xl">
                从下一份投诉材料开始，先把证据整理清楚
              </motion.h2>
              <motion.p variants={reveal} className="mt-4 max-w-[62ch] text-base leading-7 text-[#5f6661]">
                注册后即可创建案件、上传证据并生成第一版投诉文稿。
              </motion.p>
            </div>
            <motion.div variants={reveal}>
              <PrimaryCta />
            </motion.div>
          </motion.div>
        </section>
      </main>

      <footer className="border-t border-[#d9ddd5] px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-4 text-sm text-[#6c706b] sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <BrandMark className="h-7 w-7" />
            <span className="font-semibold text-[#181b1a]">ClaimCraft</span>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            <Link to="/login" className={`rounded-md transition-colors hover:text-[#181b1a] ${focusRing}`}>
              登录
            </Link>
            <Link to="/register" className={`rounded-md transition-colors hover:text-[#181b1a] ${focusRing}`}>
              注册
            </Link>
            <span>维权材料工坊</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
