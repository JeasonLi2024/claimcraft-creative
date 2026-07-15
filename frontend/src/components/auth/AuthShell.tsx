import { type PointerEvent, type ReactNode, useState } from "react"
import { Link } from "react-router"
import { motion, useReducedMotion } from "framer-motion"
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileCheck2,
  FileSearch,
  FileText,
  GitBranch,
  ScanText,
  ShieldCheck,
  Sparkles,
} from "lucide-react"

const EASE = [0.16, 1, 0.3, 1] as const

export const authFocusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] focus-visible:ring-offset-2"

const evidenceCards = [
  { code: "E1", label: "订单截图", icon: ScanText, color: "bg-[#e7eee9] text-[#2f5947]" },
  { code: "E2", label: "聊天承诺", icon: FileSearch, color: "bg-[#edf0e8] text-[#526447]" },
  { code: "E3", label: "退款记录", icon: FileCheck2, color: "bg-[#f3eee5] text-[#765f3e]" },
]

function BrandMark({ inverse = false }: { inverse?: boolean }) {
  return (
    <img
      src="/media/logo/logo.jpg"
      alt="ClaimCraft logo"
      className={`h-9 w-9 rounded-xl object-cover ${inverse ? "ring-1 ring-white/30" : ""}`}
    />
  )
}

function FlowingBackground({ reduce }: { reduce: boolean | null }) {
  const blobs = [
    { className: "-left-[12%] -top-[18%] h-[58%] w-[64%] bg-[#658b77]/55", x: [0, 58, 12, 0], y: [0, 24, 70, 0], scale: [1, 1.12, 0.96, 1], duration: 17 },
    { className: "-bottom-[22%] -right-[12%] h-[62%] w-[66%] bg-[#7a8564]/45", x: [0, -55, -18, 0], y: [0, -40, -80, 0], scale: [1, 0.94, 1.12, 1], duration: 21 },
    { className: "left-[32%] top-[28%] h-[42%] w-[48%] bg-[#c1a96f]/24", x: [0, 42, -38, 0], y: [0, -58, 28, 0], scale: [1, 1.18, 0.9, 1], duration: 19 },
  ]

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden bg-[#18211d]">
      {blobs.map((blob, index) => (
        <motion.div
          key={index}
          className={`absolute rounded-full blur-[90px] ${blob.className}`}
          animate={reduce ? undefined : { x: blob.x, y: blob.y, scale: blob.scale }}
          transition={{ duration: blob.duration, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
      <div className="absolute inset-0 opacity-[0.16] [background-image:linear-gradient(rgba(255,255,255,.13)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.13)_1px,transparent_1px)] [background-size:56px_56px] [mask-image:linear-gradient(to_bottom,black,transparent_90%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_48%_40%,transparent_0%,rgba(15,22,18,.18)_45%,rgba(10,15,12,.62)_100%)]" />
    </div>
  )
}

function GuideCharacter({ reduce }: { reduce: boolean | null }) {
  return (
    <motion.div
      className="absolute -right-4 bottom-5 z-20 hidden h-44 w-32 xl:block"
      animate={reduce ? undefined : { y: [0, -8, 0], rotate: [0, 1.2, 0] }}
      transition={{ duration: 4.8, repeat: Infinity, ease: "easeInOut" }}
      aria-hidden="true"
    >
      <div className="absolute left-1/2 top-0 h-14 w-14 -translate-x-1/2 rounded-[48%_52%_45%_55%] border border-white/40 bg-[#e9dbc3] shadow-[inset_-8px_-8px_15px_rgba(83,64,44,.16),0_14px_30px_rgba(0,0,0,.18)]">
        <div className="absolute left-3 top-6 h-1.5 w-1.5 rounded-full bg-[#26312b]" />
        <div className="absolute right-3 top-6 h-1.5 w-1.5 rounded-full bg-[#26312b]" />
        <div className="absolute left-1/2 top-9 h-1 w-4 -translate-x-1/2 rounded-full bg-[#b78f72]" />
        <div className="absolute -left-1 -top-1 h-7 w-14 -rotate-6 rounded-[60%_45%_40%_35%] bg-[#27342e]" />
      </div>
      <div className="absolute left-1/2 top-12 h-24 w-20 -translate-x-1/2 rounded-[38%_38%_24%_24%] border border-white/25 bg-[#e8eee9] shadow-[inset_-12px_-12px_20px_rgba(51,74,61,.15),0_18px_35px_rgba(0,0,0,.16)]">
        <div className="absolute left-1/2 top-4 -translate-x-1/2 rounded-md bg-[#3f6b57] px-2 py-1 font-mono text-[8px] font-bold text-white">
          CC
        </div>
        <div className="absolute -left-7 top-3 h-14 w-6 rotate-[24deg] rounded-full border border-white/30 bg-[#e8eee9]" />
        <div className="absolute -right-7 top-3 h-14 w-6 -rotate-[24deg] rounded-full border border-white/30 bg-[#e8eee9]" />
      </div>
      <div className="absolute bottom-0 left-7 h-9 w-6 rounded-b-full bg-[#25332c]" />
      <div className="absolute bottom-0 right-7 h-9 w-6 rounded-b-full bg-[#25332c]" />
      <motion.div
        className="absolute -right-2 top-4 rounded-xl border border-white/30 bg-white/85 px-3 py-2 text-[10px] font-semibold text-[#26312b] shadow-xl backdrop-blur"
        animate={reduce ? undefined : { opacity: [0.78, 1, 0.78], y: [0, -3, 0] }}
        transition={{ duration: 2.8, repeat: Infinity }}
      >
        材料已整理好
      </motion.div>
    </motion.div>
  )
}

function ProductScene({ reduce }: { reduce: boolean | null }) {
  const [tilt, setTilt] = useState({ x: 0, y: 0 })

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (reduce) return
    const rect = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - rect.left) / rect.width - 0.5
    const y = (event.clientY - rect.top) / rect.height - 0.5
    setTilt({ x: y * -7, y: x * 9 })
  }

  return (
    <div
      className="relative mx-auto mt-10 h-[360px] w-full max-w-[650px] [perspective:1200px]"
      onPointerMove={handlePointerMove}
      onPointerLeave={() => setTilt({ x: 0, y: 0 })}
    >
      <motion.div
        className="absolute inset-x-[7%] top-4 h-[302px] rounded-[24px] border border-white/25 bg-[#f8f8f5]/95 p-3 shadow-[0_45px_100px_rgba(0,0,0,.35)] backdrop-blur-xl [transform-style:preserve-3d]"
        animate={{ rotateX: tilt.x, rotateY: tilt.y }}
        transition={{ type: "spring", stiffness: 120, damping: 18 }}
      >
        <div className="flex h-full overflow-hidden rounded-2xl border border-[#d9ddd5] bg-[#f8f8f5]">
          <div className="hidden w-28 shrink-0 border-r border-[#d9ddd5] bg-[#eef0eb] p-3 sm:block">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-[#181b1a] text-[9px] font-bold text-white">
                C
              </span>
              <span className="text-[9px] font-bold">案件工作区</span>
            </div>
            <div className="mt-6 space-y-2">
              {["证据管理", "事实时间线", "投诉文本", "脱敏导出"].map((item, index) => (
                <div
                  key={item}
                  className={`rounded-md px-2 py-2 text-[8px] ${index === 0 ? "bg-[#dfe8e1] font-semibold text-[#2f5947]" : "text-[#737a75]"}`}
                >
                  {item}
                </div>
              ))}
            </div>
          </div>
          <div className="min-w-0 flex-1 p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[9px] text-[#69716c]">延迟发货退款争议</p>
                <p className="mt-1 text-xs font-bold text-[#181b1a]">证据正在成为事实链</p>
              </div>
              <span className="rounded-md bg-[#e7eee9] px-2 py-1 text-[8px] font-semibold text-[#2f5947]">
                3 / 3 已识别
              </span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              {evidenceCards.map(({ code, label, icon: Icon, color }, index) => (
                <motion.div
                  key={code}
                  className="rounded-xl border border-[#d9ddd5] bg-white p-3 shadow-sm [transform:translateZ(28px)]"
                  animate={reduce ? undefined : { y: [0, index % 2 ? 4 : -4, 0] }}
                  transition={{ duration: 3.4 + index * 0.45, repeat: Infinity, ease: "easeInOut" }}
                >
                  <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${color}`}>
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                  <p className="mt-4 font-mono text-[8px] font-bold text-[#3f6b57]">{code}</p>
                  <p className="mt-1 truncate text-[9px] font-semibold text-[#303531]">{label}</p>
                </motion.div>
              ))}
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_0.75fr]">
              <div className="rounded-xl border border-[#d9ddd5] bg-white p-3">
                <div className="flex items-center gap-2">
                  <GitBranch className="h-3 w-3 text-[#3f6b57]" />
                  <span className="text-[8px] font-bold">事实时间线</span>
                </div>
                <div className="mt-3 flex items-center gap-1">
                  {["付款", "承诺发货", "拒绝退款"].map((text, index) => (
                    <div key={text} className="contents">
                      <span className="rounded bg-[#f0f2ed] px-1.5 py-1 text-[7px] text-[#555d58]">
                        {text}
                      </span>
                      {index < 2 && <ArrowRight className="h-2.5 w-2.5 text-[#9ca39e]" />}
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-xl bg-[#1d2822] p-3 text-white">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-3 w-3 text-[#a9c9b7]" />
                  <span className="text-[8px] font-bold">生成结果</span>
                </div>
                <p className="mt-3 text-[8px] leading-4 text-white/65">
                  投诉文稿已引用 <strong className="text-[#b9d6c6]">E1 / E2 / E3</strong>
                </p>
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      <motion.div
        className="absolute -left-1 top-24 z-20 rounded-2xl border border-white/35 bg-white/88 p-3 shadow-[0_20px_45px_rgba(0,0,0,.22)] backdrop-blur-xl [transform:translateZ(70px)]"
        animate={reduce ? undefined : { y: [0, -9, 0], rotate: [-2, 1, -2] }}
        transition={{ duration: 5.2, repeat: Infinity, ease: "easeInOut" }}
      >
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-[#3f6b57]" />
          <div>
            <p className="text-[9px] font-bold text-[#26312b]">隐私检查完成</p>
            <p className="text-[8px] text-[#69716c]">敏感信息可一键打码</p>
          </div>
        </div>
      </motion.div>

      <motion.div
        className="absolute bottom-4 left-[24%] z-20 rounded-2xl border border-white/25 bg-[#26342d]/92 px-4 py-3 text-white shadow-[0_20px_45px_rgba(0,0,0,.28)] backdrop-blur-xl"
        animate={reduce ? undefined : { x: [0, 8, 0], y: [0, 5, 0] }}
        transition={{ duration: 4.4, repeat: Infinity, ease: "easeInOut" }}
      >
        <div className="flex items-center gap-3">
          <FileText className="h-4 w-4 text-[#b7d1c2]" />
          <div>
            <p className="text-[9px] font-bold">材料包可提交</p>
            <p className="mt-0.5 text-[8px] text-white/55">PDF · ZIP · 文本包</p>
          </div>
        </div>
      </motion.div>
      <GuideCharacter reduce={reduce} />
    </div>
  )
}

interface AuthShellProps {
  eyebrow: string
  title: string
  description: string
  children: ReactNode
}

export default function AuthShell({ eyebrow, title, description, children }: AuthShellProps) {
  const reduce = useReducedMotion()

  return (
    <main className="grid min-h-[100dvh] overflow-hidden bg-[#f8f8f5] lg:grid-cols-[minmax(0,1.12fr)_minmax(440px,0.88fr)]">
      <section
        className="relative hidden min-h-[100dvh] overflow-hidden p-8 text-white lg:flex lg:flex-col xl:p-12"
        aria-label="ClaimCraft 产品能力展示"
      >
        <FlowingBackground reduce={reduce} />
        <div className="relative z-10 flex items-center justify-between">
          <Link to="/home" className={`flex items-center gap-3 rounded-xl ${authFocusRing}`}>
            <BrandMark inverse />
            <span className="text-base font-semibold tracking-[-0.01em]">ClaimCraft</span>
          </Link>
          <span className="rounded-full border border-white/20 bg-white/8 px-3 py-1.5 text-[11px] font-medium text-white/70 backdrop-blur">
            维权材料工坊
          </span>
        </div>

        <div className="relative z-10 mt-auto max-w-[680px] pt-12">
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: EASE }}
            className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/8 px-3 py-1.5 text-xs font-medium text-[#cce0d4] backdrop-blur"
          >
            <Sparkles className="h-3.5 w-3.5" />
            让证据自己讲清事实
          </motion.div>
          <motion.h1
            initial={reduce ? false : { opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, delay: 0.08, ease: EASE }}
            className="mt-5 max-w-[12ch] text-[clamp(2.65rem,4.5vw,5.3rem)] font-semibold leading-[0.98] tracking-[-0.055em] text-balance"
          >
            回到你的案件工作区
          </motion.h1>
          <motion.p
            initial={reduce ? false : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, delay: 0.16, ease: EASE }}
            className="mt-5 max-w-[56ch] text-sm leading-7 text-white/62 xl:text-base"
          >
            继续核对证据、校正事实时间线，把零散材料整理成有依据、可脱敏、可提交的投诉包。
          </motion.p>
        </div>

        <div className="relative z-10">
          <ProductScene reduce={reduce} />
        </div>
        <div className="relative z-10 mt-auto flex items-center gap-5 pt-8 text-[11px] text-white/48">
          <span className="flex items-center gap-2">
            <Check className="h-3.5 w-3.5 text-[#a9c9b7]" />
            事实可追溯
          </span>
          <span className="flex items-center gap-2">
            <Check className="h-3.5 w-3.5 text-[#a9c9b7]" />
            人工可复核
          </span>
          <span className="flex items-center gap-2">
            <Check className="h-3.5 w-3.5 text-[#a9c9b7]" />
            隐私可保护
          </span>
        </div>
      </section>

      <section className="relative flex min-h-[100dvh] items-center justify-center overflow-hidden px-4 py-8 sm:px-8 lg:px-10 xl:px-16">
        <div className="pointer-events-none absolute inset-0 lg:hidden">
          <FlowingBackground reduce={reduce} />
          <div className="absolute inset-0 bg-[#f8f8f5]/92 backdrop-blur-3xl" />
        </div>
        <motion.div
          initial={reduce ? false : { opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.65, ease: EASE }}
          className="relative z-10 w-full max-w-[470px]"
        >
          <div className="mb-10 flex items-center justify-between lg:hidden">
            <Link to="/home" className={`flex items-center gap-3 rounded-xl ${authFocusRing}`}>
              <BrandMark />
              <span className="font-semibold">ClaimCraft</span>
            </Link>
            <Link
              to="/home"
              className={`rounded-lg p-2 text-[#6c706b] hover:bg-white ${authFocusRing}`}
              aria-label="返回首页"
            >
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </div>

          <div className="mb-8">
            <p className="text-sm font-semibold text-[#3f6b57]">{eyebrow}</p>
            <h2 className="mt-3 text-4xl font-semibold tracking-[-0.045em] text-[#181b1a] sm:text-5xl">
              {title}
            </h2>
            <p className="mt-4 text-sm leading-6 text-[#6c706b]">{description}</p>
          </div>

          {children}
        </motion.div>
      </section>
    </main>
  )
}
