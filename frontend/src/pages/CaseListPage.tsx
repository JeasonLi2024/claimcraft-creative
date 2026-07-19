import { useState, useEffect, useCallback, useMemo } from "react"
import { useNavigate } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useAuthStore } from "@/stores/auth-store"
import { useDebounce } from "@/composables/useDebounce"
import CaseCard from "@/components/CaseCard"
import { cn } from "@/lib/utils"
import {
  ArrowRight,
  BarChart3,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  FileCheck2,
  FileText,
  Filter,
  Gavel,
  Image,
  ListFilter,
  Loader2,
  PackageCheck,
  Plus,
  Search,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Store,
  X,
} from "lucide-react"

const CASE_TYPE_FILTERS = [
  { value: "", label: "全部类型" },
  { value: "shopping", label: "网购纠纷" },
  { value: "service", label: "服务违约" },
  { value: "secondhand", label: "二手交易" },
  { value: "other", label: "其他" },
]

const CASE_MODES = [
  { value: "complain", label: "维权投诉" },
  { value: "respond", label: "商家反证" },
] as const

const STATUS_FILTERS = [
  { value: "", label: "全部状态" },
  { value: "draft", label: "草稿" },
  { value: "processing", label: "处理中" },
  { value: "submitted", label: "已提交" },
  { value: "closed", label: "已结案" },
  { value: "cancelled", label: "已取消" },
]

const quickStarts = [
  { type: "shopping", mode: "complain" as const, title: "网购退款纠纷", text: "整理订单、聊天、物流与退款记录", icon: ShoppingBag, color: "bg-[#e4eee8] text-[#315a48]" },
  { type: "service", mode: "complain" as const, title: "服务履约争议", text: "梳理合同、付款与履约承诺", icon: FileCheck2, color: "bg-[#eee9dd] text-[#705d39]" },
  { type: "other", mode: "respond" as const, title: "商家反证材料", text: "组织履约记录与沟通依据", icon: Store, color: "bg-[#e6e8ec] text-[#4d5965]" },
]

export default function CaseListPage() {
  const navigate = useNavigate()
  const fetchCases = useCaseStore((s) => s.fetchCases)
  const cases = useCaseStore((s) => s.cases)
  const loading = useCaseStore((s) => s.loading)
  const deleteCase = useCaseStore((s) => s.deleteCase)
  const error = useCaseStore((s) => s.error)
  const user = useAuthStore((s) => s.user)

  const [search, setSearch] = useState("")
  const [caseType, setCaseType] = useState("")
  const [status, setStatus] = useState("")
  const [showCreate, setShowCreate] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null)
  const [newTitle, setNewTitle] = useState("")
  const [newDesc, setNewDesc] = useState("")
  const [newType, setNewType] = useState("shopping")
  const [newMode, setNewMode] = useState<"complain" | "respond">("complain")
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState("")

  const debouncedSearch = useDebounce(search, 300)
  const hasFilters = Boolean(search || caseType || status)

  const loadCases = useCallback(() => {
    const params: Record<string, string> = {}
    if (debouncedSearch) params.search = debouncedSearch
    if (caseType) params.case_type = caseType
    if (status) params.status = status
    fetchCases(params)
  }, [debouncedSearch, caseType, status, fetchCases])

  useEffect(() => { loadCases() }, [loadCases])

  const metrics = useMemo(() => {
    const active = cases.filter((item) => item.status === "processing" || item.status === "draft").length
    const completed = cases.filter((item) => item.status === "submitted" || item.status === "closed").length
    const evidence = cases.reduce((sum, item) => sum + (item.evidence_count || 0), 0)
    const fields = cases.reduce((sum, item) => sum + (item.extracted_field_count || 0), 0)
    return { active, completed, evidence, fields }
  }, [cases])

  const recentCase = useMemo(() => [...cases].sort((a, b) => new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime())[0], [cases])

  function openCreate(type = "shopping", mode: "complain" | "respond" = "complain", title = "") {
    setNewType(type)
    setNewMode(mode)
    setNewTitle(title)
    setCreateError("")
    setShowCreate(true)
  }

  function clearFilters() {
    setSearch("")
    setCaseType("")
    setStatus("")
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreateError("")
    if (!newTitle.trim()) { setCreateError("请输入案件标题"); return }
    setCreating(true)
    try {
      const created = await useCaseStore.getState().createCase({ title: newTitle.trim(), description: newDesc.trim(), case_type: newType, case_mode: newMode })
      setShowCreate(false)
      setNewTitle("")
      setNewDesc("")
      setNewType("shopping")
      setNewMode("complain")
      navigate(`/cases/${created.id}/workspace`, { state: { case_mode: newMode } })
    } catch (err: any) {
      setCreateError(err.response?.data?.detail || err.message || "创建失败")
    } finally { setCreating(false) }
  }

  async function handleDelete(id: number) {
    try { await deleteCase(id); setDeleteTarget(null) } catch {}
  }

  const greeting = user && user.username ? `${user.username}，欢迎回来` : "欢迎回到案件工作区"

  return (
    <div className="space-y-7">
      <section className="relative overflow-hidden rounded-[26px] bg-[#18211d] text-white shadow-[0_24px_70px_rgba(24,33,29,.16)]">
        <div className="pointer-events-none absolute -right-20 -top-32 h-80 w-80 rounded-full bg-[#557461]/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-40 left-[28%] h-72 w-72 rounded-full bg-[#9d8758]/20 blur-3xl" />
        <div className="pointer-events-none absolute inset-0 opacity-[0.13] [background-image:linear-gradient(rgba(255,255,255,.12)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.12)_1px,transparent_1px)] [background-size:48px_48px]" />
        <div className="relative grid gap-8 p-6 sm:p-8 lg:grid-cols-[1fr_360px] lg:p-10">
          <div className="flex flex-col justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1.5 text-xs text-[#c7dbcf] backdrop-blur"><Sparkles className="h-3.5 w-3.5" />案件总览</div>
              <h1 className="mt-5 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">{greeting}</h1>
              <p className="mt-3 max-w-[58ch] text-sm leading-6 text-white/60">把每一份证据、事实节点和文稿集中在同一个工作区，清楚掌握材料整理进度。</p>
            </div>
            <div className="mt-8 flex flex-wrap gap-3">
              <button onClick={() => openCreate()} className="group inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-[#18211d] transition-transform hover:-translate-y-0.5"><Plus className="h-4 w-4" />新建案件</button>
              {recentCase && <button onClick={() => navigate(`/cases/${recentCase.id}/workspace`)} className="inline-flex items-center gap-2 rounded-xl border border-white/20 bg-white/8 px-4 py-2.5 text-sm font-medium text-white backdrop-blur transition-colors hover:bg-white/14">继续最近案件<ArrowRight className="h-4 w-4" /></button>}
            </div>
          </div>

          <div className="rounded-2xl border border-white/15 bg-white/8 p-5 backdrop-blur-md">
            <div className="flex items-center justify-between"><div><p className="text-xs text-white/45">材料工作区</p><p className="mt-1 text-base font-semibold">整体整理概览</p></div><BarChart3 className="h-5 w-5 text-[#a7c5b4]" /></div>
            <div className="mt-5 grid grid-cols-2 gap-2">
              {[{ label: "全部案件", value: cases.length, icon: BriefcaseBusiness }, { label: "处理中", value: metrics.active, icon: CircleDot }, { label: "证据材料", value: metrics.evidence, icon: Image }, { label: "已抽取字段", value: metrics.fields, icon: ShieldCheck }].map(({ label, value, icon: Icon }) => <div key={label} className="rounded-xl border border-white/10 bg-black/10 p-3"><div className="flex items-center justify-between"><span className="text-[10px] text-white/45">{label}</span><Icon className="h-3.5 w-3.5 text-[#9fc0ae]" /></div><p className="mt-2 text-2xl font-semibold">{value}</p></div>)}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "进行中的案件", value: metrics.active, note: "草稿与处理中", icon: CircleDot, color: "bg-[#e7eee9] text-[#2f5947]" },
          { label: "已提交 / 结案", value: metrics.completed, note: "形成可提交成果", icon: CheckCircle2, color: "bg-[#edf0e8] text-[#526447]" },
          { label: "累计证据材料", value: metrics.evidence, note: "图片与文字证据", icon: FileText, color: "bg-[#f2eee5] text-[#765f3e]" },
          { label: "材料完整度", value: cases.length ? `${Math.round((cases.filter((item) => item.evidence_count > 0).length / cases.length) * 100)}%` : "0%", note: "至少包含一份证据", icon: PackageCheck, color: "bg-[#e8e9ed] text-[#505b68]" },
        ].map(({ label, value, note, icon: Icon, color }) => <article key={label} className="rounded-2xl border border-[#d9ddd5] bg-white p-5 shadow-[0_10px_30px_rgba(31,45,38,.035)]"><div className="flex items-start justify-between"><div><p className="text-xs font-medium text-[#737a75]">{label}</p><p className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[#181b1a]">{value}</p></div><span className={`flex h-10 w-10 items-center justify-center rounded-xl ${color}`}><Icon className="h-5 w-5" /></span></div><p className="mt-4 text-[11px] text-[#959a96]">{note}</p></article>)}
      </section>

      <section className="rounded-2xl border border-[#d9ddd5] bg-[#f1f2ee] p-5 sm:p-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-xs font-semibold text-[#3f6b57]">快速开始</p><h2 className="mt-1 text-xl font-semibold tracking-[-0.025em]">从常见场景创建材料工作区</h2></div><p className="text-xs text-[#777e79]">选择场景后仍可修改案件信息</p></div>
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          {quickStarts.map(({ type, mode, title, text, icon: Icon, color }) => <button key={title} onClick={() => openCreate(type, mode, title)} className="group flex items-center gap-4 rounded-xl border border-[#d9ddd5] bg-white p-4 text-left transition-all hover:-translate-y-0.5 hover:border-[#afbbb1] hover:shadow-[0_12px_30px_rgba(31,45,38,.07)]"><span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${color}`}><Icon className="h-5 w-5" /></span><span className="min-w-0 flex-1"><strong className="block text-sm text-[#242925]">{title}</strong><span className="mt-1 block truncate text-xs text-[#7a817c]">{text}</span></span><ArrowRight className="h-4 w-4 text-[#9aa19c] transition-transform group-hover:translate-x-1 group-hover:text-[#3f6b57]" /></button>)}
        </div>
      </section>

      <section>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div><p className="text-xs font-semibold text-[#3f6b57]">案件工作区</p><h2 className="mt-1 text-2xl font-semibold tracking-[-0.03em]">我的案件</h2><p className="mt-1 text-sm text-[#777e79]">{hasFilters ? `找到 ${cases.length} 个符合条件的案件` : `共 ${cases.length} 个案件`}</p></div>
          <button onClick={() => openCreate()} className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#181b1a] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#2b302d]"><Plus className="h-4 w-4" />新建案件</button>
        </div>

        <div className="rounded-2xl border border-[#d9ddd5] bg-white p-3 shadow-[0_8px_25px_rgba(31,45,38,.03)] sm:p-4">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
            <div className="relative min-w-[240px] flex-1"><Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a918c]" /><input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索案件标题或描述" className="w-full rounded-xl border border-[#d9ddd5] bg-[#f8f8f5] py-2.5 pl-10 pr-4 text-sm placeholder:text-[#a0a5a1] focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10" /></div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <label className="relative"><ListFilter className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#818783]" /><select value={caseType} onChange={(e) => setCaseType(e.target.value)} className="w-full appearance-none rounded-xl border border-[#d9ddd5] bg-white py-2.5 pl-9 pr-9 text-sm focus:border-[#3f6b57] focus:outline-none sm:w-auto">{CASE_TYPE_FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#818783]" /></label>
              <label className="relative"><Filter className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#818783]" /><select value={status} onChange={(e) => setStatus(e.target.value)} className="w-full appearance-none rounded-xl border border-[#d9ddd5] bg-white py-2.5 pl-9 pr-9 text-sm focus:border-[#3f6b57] focus:outline-none sm:w-auto">{STATUS_FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#818783]" /></label>
              {hasFilters && <button onClick={clearFilters} className="inline-flex items-center justify-center gap-1.5 rounded-xl px-3 py-2.5 text-sm text-[#747b76] hover:bg-[#f1f2ee] hover:text-[#181b1a]"><X className="h-3.5 w-3.5" />清除</button>}
            </div>
          </div>
        </div>
      </section>

      {error && <div className="rounded-xl border border-[#e9c8c3] bg-[#fff6f4] px-4 py-3 text-sm text-[#ad4438]">{error}</div>}

      {loading && cases.length === 0 && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((item) => <div key={item} className="h-[330px] animate-pulse rounded-2xl border border-[#d9ddd5] bg-white p-6"><div className="h-5 w-24 rounded bg-[#eceeea]" /><div className="mt-6 h-6 w-2/3 rounded bg-[#e4e7e2]" /><div className="mt-3 h-4 w-full rounded bg-[#eff1ed]" /><div className="mt-8 grid grid-cols-3 gap-2">{[0, 1, 2].map((sub) => <div key={sub} className="h-16 rounded-xl bg-[#f1f2ee]" />)}</div><Loader2 className="mx-auto mt-10 h-5 w-5 animate-spin text-[#3f6b57]" /></div>)}</div>}

      {!loading && cases.length === 0 && (
        <div className="relative overflow-hidden rounded-2xl border border-dashed border-[#bdc6be] bg-white px-6 py-14 text-center">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(63,107,87,.08),transparent_55%)]" />
          <img src="/empty-state.webp" alt="" aria-hidden="true" loading="lazy" className="relative mx-auto w-52 max-w-[75%] object-contain" />
          <h3 className="relative mt-5 text-xl font-semibold">{hasFilters ? "没有符合条件的案件" : "创建你的第一个案件工作区"}</h3>
          <p className="relative mx-auto mt-2 max-w-md text-sm leading-6 text-[#777e79]">{hasFilters ? "尝试更换搜索词或清除筛选条件。" : "从上传第一份证据开始，逐步完成事实时间线、投诉文稿和安全导出。"}</p>
          <div className="relative mt-6 flex justify-center gap-3">{hasFilters ? <button onClick={clearFilters} className="rounded-xl border border-[#d9ddd5] bg-white px-4 py-2.5 text-sm font-semibold hover:bg-[#f1f2ee]">清除筛选</button> : <button onClick={() => openCreate()} className="inline-flex items-center gap-2 rounded-xl bg-[#181b1a] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#2b302d]"><Plus className="h-4 w-4" />新建第一个案件</button>}</div>
        </div>
      )}

      {!loading && cases.length > 0 && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{cases.map((item) => <CaseCard key={item.id} caseData={item} onDelete={(id) => setDeleteTarget(id)} />)}</div>}

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#111713]/55 p-4 backdrop-blur-sm" onClick={() => setShowCreate(false)}>
          <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-[24px] border border-white/40 bg-[#f8f8f5] shadow-[0_35px_100px_rgba(15,22,18,.35)]" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between border-b border-[#d9ddd5] p-6"><div><p className="text-xs font-semibold text-[#3f6b57]">新建工作区</p><h2 className="mt-1 text-2xl font-semibold tracking-[-0.03em]">创建案件</h2><p className="mt-2 text-sm text-[#777e79]">先填写基础信息，证据和诉求可稍后补充。</p></div><button onClick={() => setShowCreate(false)} className="rounded-lg p-2 text-[#737a75] hover:bg-[#eceeea]"><X className="h-4 w-4" /></button></div>
            {createError && <div className="mx-6 mt-5 rounded-xl bg-[#fff0ee] px-4 py-3 text-sm text-[#b2483d]">{createError}</div>}
            <form onSubmit={handleCreate} className="space-y-5 p-6">
              <div><label className="mb-2 block text-sm font-semibold">案件标题</label><input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="例如：XX 平台延迟发货退款纠纷" className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10" autoFocus /></div>
              <div><label className="mb-2 block text-sm font-semibold">案件描述</label><textarea value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="简要描述发生了什么、目前有哪些证据和希望解决的问题..." rows={3} className="w-full resize-none rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none focus:ring-3 focus:ring-[#3f6b57]/10" /></div>
              <div className="grid gap-4 sm:grid-cols-2"><div><label className="mb-2 block text-sm font-semibold">纠纷类型</label><select value={newType} onChange={(e) => setNewType(e.target.value)} className="w-full rounded-xl border border-[#d9ddd5] bg-white px-4 py-3 text-sm focus:border-[#3f6b57] focus:outline-none">{CASE_TYPE_FILTERS.filter((item) => item.value).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div><div><label className="mb-2 block text-sm font-semibold">案件模式</label><div className="grid grid-cols-2 gap-2">{CASE_MODES.map((item) => <button key={item.value} type="button" onClick={() => setNewMode(item.value)} className={cn("rounded-xl border px-3 py-3 text-xs font-semibold transition-all", newMode === item.value ? "border-[#3f6b57] bg-[#e7eee9] text-[#2f5947]" : "border-[#d9ddd5] bg-white text-[#777e79] hover:bg-[#f1f2ee]")}>{item.value === "complain" ? <ShoppingBag className="mx-auto mb-1 h-4 w-4" /> : <Gavel className="mx-auto mb-1 h-4 w-4" />}{item.label}</button>)}</div></div></div>
              <div className="rounded-xl bg-[#eef1ec] p-4 text-xs leading-5 text-[#68706a]">{newMode === "complain" ? "将创建消费者维权流程，可生成平台、监管和仲裁准备文稿。" : "将创建商家反证流程，用于组织履约与沟通依据。"}</div>
              <div className="flex justify-end gap-3 pt-2"><button type="button" onClick={() => setShowCreate(false)} className="rounded-xl border border-[#d9ddd5] bg-white px-4 py-2.5 text-sm font-semibold hover:bg-[#f1f2ee]">取消</button><button type="submit" disabled={creating} className="inline-flex min-w-28 items-center justify-center gap-2 rounded-xl bg-[#181b1a] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#2b302d] disabled:opacity-50">{creating ? <><Loader2 className="h-4 w-4 animate-spin" />创建中</> : <>创建案件<ArrowRight className="h-4 w-4" /></>}</button></div>
            </form>
          </div>
        </div>
      )}

      {deleteTarget !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#111713]/55 p-4 backdrop-blur-sm" onClick={() => setDeleteTarget(null)}>
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-[0_30px_80px_rgba(15,22,18,.35)]" onClick={(e) => e.stopPropagation()}><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#fff0ee] text-[#b2483d]"><X className="h-5 w-5" /></span><h2 className="mt-5 text-xl font-semibold">确认删除案件？</h2><p className="mt-2 text-sm leading-6 text-[#777e79]">案件及其关联材料将被删除，此操作不可撤销。</p><div className="mt-6 flex justify-end gap-3"><button onClick={() => setDeleteTarget(null)} className="rounded-xl border border-[#d9ddd5] px-4 py-2.5 text-sm font-semibold hover:bg-[#f1f2ee]">取消</button><button onClick={() => handleDelete(deleteTarget)} className="rounded-xl bg-[#b2483d] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#983b32]">确认删除</button></div></div>
        </div>
      )}
    </div>
  )
}
