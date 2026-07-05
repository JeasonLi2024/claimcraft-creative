import { motion, useScroll, useTransform } from "framer-motion"
import { Link } from "react-router"
import {
  ScanText,
  FileSearch,
  GitBranch,
  FileText,
  ArrowRight,
  Sparkles,
} from "lucide-react"
import ParticleBackground from "@/components/ParticleBackground"

// 焦点环样式（统一 focus-visible 表现）
const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#d6a84b] focus-visible:ring-offset-2 focus-visible:ring-offset-background"

const fadeInUp = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.7, ease: [0.22, 1, 0.36, 1] as const },
  },
}

const stagger = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.15, delayChildren: 0.1 },
  },
}

const FEATURES = [
  {
    icon: ScanText,
    title: "智能 OCR",
    desc: "多引擎级联 · Tesseract + PaddleOCR + LLM Vision · 后纠错",
    accent: "#d6a84b",
  },
  {
    icon: FileSearch,
    title: "字段抽取",
    desc: "正则兜底 · LLM JSON Mode · 13 类字段 · 置信度评估",
    accent: "#9b965f",
  },
  {
    icon: GitBranch,
    title: "时间线重建",
    desc: "LangGraph 工作流 · LLM 事件分类 · 同类归并",
    accent: "#7a8c5e",
  },
  {
    icon: FileText,
    title: "投诉生成",
    desc: "Jinja2 骨架 · LLM 重写 · 语气可调 · 一键导出",
    accent: "#c45c4a",
  },
]

const WORKFLOW_STEPS = [
  { label: "上传截图", color: "#978365" },
  { label: "OCR 识别", color: "#9b965f" },
  { label: "字段抽取", color: "#d6a84b" },
  { label: "时间线", color: "#7a8c5e" },
  { label: "投诉文本", color: "#c45c4a" },
]

const STATUS_FLOW = [
  { label: "draft", name: "草稿", color: "#978365" },
  { label: "processing", name: "处理中", color: "#9b965f" },
  { label: "submitted", name: "已提交", color: "#d6a84b" },
  { label: "closed", name: "已结案", color: "#7a8c5e" },
  { label: "cancelled", name: "已取消", color: "#c45c4a" },
]

export default function HomePage() {
  const { scrollYProgress } = useScroll()
  const heroY = useTransform(scrollYProgress, [0, 0.3], [0, -80])
  const heroOpacity = useTransform(scrollYProgress, [0, 0.25], [1, 0])

  return (
    <div className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <ParticleBackground />

      {/* Navbar */}
      <motion.nav
        initial={{ y: -40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-background/60 border-b border-border/40"
        style={{ paddingTop: "env(safe-area-inset-top)" }}
      >
        <div className="mx-auto max-w-7xl px-6 lg:px-10 h-16 flex items-center justify-between">
          <Link to="/home" className={`flex items-center gap-2.5 group ${focusRing} rounded-md`}>
            <div className="relative">
              <div className="absolute inset-0 rounded-full bg-[#d6a84b] blur-md opacity-40 group-hover:opacity-70 transition-opacity" />
              <div className="relative w-7 h-7 rounded-full bg-gradient-to-br from-[#d6a84b] to-[#9b965f] flex items-center justify-center">
                <span className="font-[Fraunces] text-parchment text-sm font-bold">
                  C
                </span>
              </div>
            </div>
            <span
              className="font-[Fraunces] text-xl font-semibold tracking-tight"
              style={{ fontVariationSettings: '"opsz" 32' }}
            >
              ClaimCraft
            </span>
          </Link>

          <div className="flex items-center gap-2">
            <Link
              to="/login"
              className={`px-4 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors ${focusRing} rounded-md`}
            >
              登录
            </Link>
            <Link
              to="/register"
              className={`px-4 py-1.5 text-sm font-medium bg-foreground text-background rounded-full hover:bg-foreground/90 transition-[background-color,transform] hover:scale-[1.02] ${focusRing}`}
            >
              免费注册
            </Link>
          </div>
        </div>
      </motion.nav>

      {/* Skip link for keyboard users */}
      <a
        href="#main-content"
        className={`sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:bg-background focus:text-foreground focus:rounded-md focus:border focus:border-border ${focusRing}`}
      >
        跳到主内容
      </a>

      {/* Hero — Full-bleed, brand-first */}
      <motion.section
        style={{ y: heroY, opacity: heroOpacity }}
        className="relative min-h-[calc(100svh-4rem)] flex flex-col justify-center px-6 lg:px-10 pt-16"
        id="main-content"
      >
        <div className="mx-auto max-w-7xl w-full">
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="visible"
            className="max-w-3xl"
          >
            <motion.div
              variants={fadeInUp}
              className="inline-flex items-center gap-2 px-3 py-1 mb-8 rounded-full border border-[#d6a84b]/30 bg-[#d6a84b]/5"
            >
              <Sparkles className="w-3.5 h-3.5 text-[#d6a84b]" aria-hidden="true" />
              <span className="text-xs font-medium tracking-wide text-[#d6a84b]">
                LangGraph 智能体工作流 · 多模型可切换
              </span>
            </motion.div>

            <motion.h1
              variants={fadeInUp}
              className="font-[Fraunces] text-[clamp(2.75rem,7vw,5.5rem)] font-light leading-[1.05] tracking-tight mb-6"
              style={{ fontVariationSettings: '"opsz" 144, "wght" 350' }}
            >
              把截图
              <br />
              <span className="italic font-normal text-[#9b965f]">变成</span>{" "}
              投诉材料
            </motion.h1>

            <motion.p
              variants={fadeInUp}
              className="text-lg lg:text-xl text-muted-foreground max-w-xl leading-relaxed mb-10"
            >
              OCR · 字段抽取 · 时间线重建 · 投诉生成
              <br />
              一站式维权证据工坊，让每一条事实都有据可循
            </motion.p>

            <motion.div
              variants={fadeInUp}
              className="flex flex-wrap items-center gap-4"
            >
              <Link
                to="/register"
                className={`group inline-flex items-center gap-2 px-6 py-3 bg-foreground text-background rounded-full font-medium hover:bg-foreground/90 transition-[background-color,transform] hover:scale-[1.02] ${focusRing}`}
              >
                立即开始
                <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" aria-hidden="true" />
              </Link>
              <Link
                to="/login"
                className={`inline-flex items-center gap-2 px-6 py-3 border border-border rounded-full font-medium hover:border-foreground/40 transition-colors ${focusRing}`}
              >
                已有账号 · 登录
              </Link>
            </motion.div>
          </motion.div>
        </div>

        {/* 滚动指示器 */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2, duration: 0.8 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-muted-foreground/60"
          aria-hidden="true"
        >
          <span className="text-xs tracking-widest uppercase">scroll</span>
          <div className="w-px h-12 bg-gradient-to-b from-[#d6a84b]/60 to-transparent" />
        </motion.div>
      </motion.section>

      {/* Core Features — cardless layout, dividers */}
      <section className="relative px-6 lg:px-10 py-32 border-t border-border/40">
        <div className="mx-auto max-w-7xl">
          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            className="mb-20"
          >
            <motion.div
              variants={fadeInUp}
              className="text-sm tracking-widest uppercase text-[#d6a84b] mb-4"
            >
              核心能力
            </motion.div>
            <motion.h2
              variants={fadeInUp}
              className="font-[Fraunces] text-4xl lg:text-5xl font-light leading-tight max-w-2xl"
              style={{ fontVariationSettings: '"opsz" 96, "wght" 350' }}
            >
              四个环节，一条流水线
            </motion.h2>
          </motion.div>

          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            className="grid grid-cols-1 md:grid-cols-2 gap-px bg-border/40 border border-border/40 rounded-2xl overflow-hidden"
          >
            {FEATURES.map((f) => (
              <motion.div
                key={f.title}
                variants={fadeInUp}
                whileHover={{ y: -4 }}
                transition={{ type: "spring", stiffness: 300, damping: 20 }}
                className="group relative bg-background p-8 lg:p-10 hover:bg-[#d6a84b]/[0.03] transition-colors"
              >
                <div
                  className="w-12 h-12 mb-6 rounded-xl flex items-center justify-center transition-[transform] group-hover:scale-110"
                  style={{
                    backgroundColor: `${f.accent}15`,
                    color: f.accent,
                  }}
                >
                  <f.icon className="w-5 h-5" strokeWidth={1.5} aria-hidden="true" />
                </div>
                <h3
                  className="font-[Fraunces] text-2xl font-medium mb-3"
                  style={{ fontVariationSettings: '"opsz" 48' }}
                >
                  {f.title}
                </h3>
                <p className="text-muted-foreground leading-relaxed">
                  {f.desc}
                </p>
                <div
                  className="absolute bottom-0 left-0 h-px w-0 group-hover:w-full transition-[width] duration-500"
                  style={{ backgroundColor: f.accent }}
                />
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* Workflow Demo — horizontal flow with motion */}
      <section className="relative px-6 lg:px-10 py-32 border-t border-border/40">
        <div className="mx-auto max-w-7xl">
          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            className="mb-20"
          >
            <motion.div
              variants={fadeInUp}
              className="text-sm tracking-widest uppercase text-[#d6a84b] mb-4"
            >
              工作流
            </motion.div>
            <motion.h2
              variants={fadeInUp}
              className="font-[Fraunces] text-4xl lg:text-5xl font-light leading-tight max-w-2xl"
              style={{ fontVariationSettings: '"opsz" 96, "wght" 350' }}
            >
              从一张截图到一份投诉
            </motion.h2>
          </motion.div>

          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            className="flex flex-col lg:flex-row items-stretch lg:items-center gap-4 lg:gap-0"
          >
            {WORKFLOW_STEPS.map((step, i) => (
              <motion.div key={step.label} variants={fadeInUp} className="flex items-center gap-4 lg:gap-0">
                <div className="flex flex-col items-center gap-3 lg:flex-1">
                  <div
                    className={`relative w-16 h-16 rounded-full flex items-center justify-center border-2 transition-[transform] hover:scale-110 ${focusRing}`}
                    style={{ borderColor: step.color, color: step.color }}
                    tabIndex={0}
                  >
                    <span className="font-[Fraunces] text-xl font-medium">
                      {i + 1}
                    </span>
                    <div
                      className="absolute inset-0 rounded-full opacity-0 hover:opacity-30 blur-md transition-opacity"
                      style={{ backgroundColor: step.color }}
                    />
                  </div>
                  <span className="text-sm font-medium tracking-wide">
                    {step.label}
                  </span>
                </div>
                {i < WORKFLOW_STEPS.length - 1 && (
                  <div className="hidden lg:block flex-shrink-0 w-16 h-px relative overflow-hidden">
                    <div
                      className="absolute inset-0"
                      style={{
                        background: `linear-gradient(90deg, ${step.color}, ${WORKFLOW_STEPS[i + 1].color})`,
                      }}
                    />
                    <motion.div
                      initial={{ x: "-100%" }}
                      whileInView={{ x: "100%" }}
                      viewport={{ once: true }}
                      transition={{
                        duration: 1.5,
                        delay: 0.3 + i * 0.2,
                        repeat: Infinity,
                        repeatDelay: 1,
                        ease: "easeInOut",
                      }}
                      className="absolute top-0 left-0 w-1/2 h-full bg-[#d6a84b]/80"
                    />
                  </div>
                )}
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* Status Showcase — 5 状态色阶 */}
      <section className="relative px-6 lg:px-10 py-32 border-t border-border/40">
        <div className="mx-auto max-w-7xl">
          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-100px" }}
            className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center"
          >
            <motion.div variants={fadeInUp} className="lg:col-span-5">
              <div className="text-sm tracking-widest uppercase text-[#d6a84b] mb-4">
                案件状态
              </div>
              <h2
                className="font-[Fraunces] text-4xl lg:text-5xl font-light leading-tight mb-6"
                style={{ fontVariationSettings: '"opsz" 96, "wght" 350' }}
              >
                全流程
                <br />
                状态可追溯
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                从草稿到结案，每个状态都有时间戳和操作日志。
                <br />
                基于 django-fsm 状态机，保证状态转换合法可追溯。
              </p>
            </motion.div>

            <motion.div
              variants={fadeInUp}
              className="lg:col-span-7 flex flex-col gap-2"
            >
              {STATUS_FLOW.map((s, i) => (
                <motion.div
                  key={s.label}
                  initial={{ opacity: 0, x: 20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1, duration: 0.6 }}
                  className="group relative flex items-center gap-6 p-5 rounded-xl border border-border/40 hover:border-border transition-[border-color]"
                >
                  <div
                    className="w-1 h-12 rounded-full transition-[height] group-hover:h-14"
                    style={{ backgroundColor: s.color }}
                  />
                  <div className="flex-1">
                    <div
                      className="font-[Fraunces] text-xl font-medium"
                      style={{ fontVariationSettings: '"opsz" 48' }}
                    >
                      {s.name}
                    </div>
                    <div className="text-xs tracking-wider uppercase text-muted-foreground mt-1">
                      {s.label}
                    </div>
                  </div>
                  <div
                    className="text-xs font-mono px-2 py-1 rounded"
                    style={{
                      backgroundColor: `${s.color}15`,
                      color: s.color,
                    }}
                  >
                    {s.color}
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="relative px-6 lg:px-10 py-32 border-t border-border/40">
        <motion.div
          variants={stagger}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          className="mx-auto max-w-4xl text-center"
        >
          <motion.h2
            variants={fadeInUp}
            className="font-[Fraunces] text-4xl lg:text-6xl font-light leading-tight mb-6"
            style={{ fontVariationSettings: '"opsz" 144, "wght" 350' }}
          >
            让证据
            <span className="italic text-[#9b965f]">说话</span>
          </motion.h2>
          <motion.p
            variants={fadeInUp}
            className="text-lg text-muted-foreground mb-10 max-w-xl mx-auto"
          >
            从今天起，把繁琐的维权材料准备交给 ClaimCraft。
          </motion.p>
          <motion.div
            variants={fadeInUp}
            className="flex flex-wrap items-center justify-center gap-4"
          >
            <Link
              to="/register"
              className={`group inline-flex items-center gap-2 px-8 py-4 bg-foreground text-background rounded-full font-medium hover:bg-foreground/90 transition-[background-color,transform] hover:scale-[1.02] ${focusRing}`}
            >
              免费开始
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" aria-hidden="true" />
            </Link>
          </motion.div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="relative px-6 lg:px-10 py-12 border-t border-border/40">
        <div className="mx-auto max-w-7xl flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-[#d6a84b] to-[#9b965f]" />
            <span
              className="font-[Fraunces] text-lg font-medium"
              style={{ fontVariationSettings: '"opsz" 32' }}
            >
              ClaimCraft
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            Golden Time Design System · 2026
          </p>
        </div>
      </footer>
    </div>
  )
}
