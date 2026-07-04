import { useState, useEffect, useCallback } from "react"
import { useNavigate } from "react-router"
import { useCaseStore } from "@/stores/case-store"
import { useDebounce } from "@/composables/useDebounce"
import HeroSection from "@/components/HeroSection"
import CaseCard from "@/components/CaseCard"
import EmptyState from "@/components/EmptyState"
import StatusTag from "@/components/StatusTag"
import { Plus, Search, FileText, Image, Loader2 } from "lucide-react"

const DISPUTE_FILTERS = [
  { value: "", label: "全部类型" },
  { value: "online_shopping", label: "网购纠纷" },
  { value: "service_breach", label: "服务违约" },
  { value: "second_hand", label: "二手交易" },
  { value: "other", label: "其他" },
]

const STATUS_FILTERS = [
  { value: "", label: "全部状态" },
  { value: "draft", label: "草稿" },
  { value: "processing", label: "处理中" },
  { value: "submitted", label: "已提交" },
  { value: "closed", label: "已结案" },
  { value: "cancelled", label: "已取消" },
]

export default function CaseListPage() {
  const navigate = useNavigate()
  const fetchCases = useCaseStore((s) => s.fetchCases)
  const cases = useCaseStore((s) => s.cases)
  const loading = useCaseStore((s) => s.loading)
  const deleteCase = useCaseStore((s) => s.deleteCase)
  const error = useCaseStore((s) => s.error)

  const [search, setSearch] = useState("")
  const [disputeType, setDisputeType] = useState("")
  const [status, setStatus] = useState("")
  const [showCreate, setShowCreate] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null)

  // Form state
  const [newTitle, setNewTitle] = useState("")
  const [newDesc, setNewDesc] = useState("")
  const [newType, setNewType] = useState("online_shopping")
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState("")

  const debouncedSearch = useDebounce(search, 300)

  const loadCases = useCallback(() => {
    const params: Record<string, string> = {}
    if (debouncedSearch) params.search = debouncedSearch
    if (disputeType) params.dispute_type = disputeType
    if (status) params.status = status
    fetchCases(params)
  }, [debouncedSearch, disputeType, status, fetchCases])

  useEffect(() => {
    loadCases()
  }, [loadCases])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreateError("")
    if (!newTitle.trim()) { setCreateError("请输入案件标题"); return }
    setCreating(true)
    try {
      const created = await useCaseStore.getState().createCase({
        title: newTitle.trim(),
        description: newDesc.trim(),
        dispute_type: newType,
      })
      setShowCreate(false)
      setNewTitle("")
      setNewDesc("")
      setNewType("online_shopping")
      navigate(`/cases/${created.id}/workspace`)
    } catch (err: any) {
      setCreateError(err.response?.data?.detail || err.message || "创建失败")
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteCase(id)
      setDeleteTarget(null)
    } catch {}
  }

  return (
    <div className="space-y-6">
      {/* Hero */}
      <HeroSection
        title="维权材料工坊"
        subtitle="把截图变成可提交的投诉包"
      >
        <div className="flex flex-wrap gap-3">
          <div className="flex items-center gap-2 rounded-xl bg-white/10 px-4 py-2 text-sm backdrop-blur-sm">
            <FileText className="h-4 w-4 text-white/70" />
            <span className="font-semibold">{cases.length}</span>
            <span className="text-white/60">个案件</span>
          </div>
          <div className="hidden items-center gap-2 rounded-xl bg-white/10 px-4 py-2 text-sm backdrop-blur-sm sm:flex">
            <Image className="h-4 w-4 text-white/70" />
            <span className="font-semibold">{cases.reduce((sum, c) => sum + c.evidence_count, 0)}</span>
            <span className="text-white/60">条证据</span>
          </div>
        </div>
      </HeroSection>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索案件..."
            className="w-full rounded-xl border border-input bg-card py-2 pl-9 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
          />
        </div>
        <select
          value={disputeType}
          onChange={(e) => setDisputeType(e.target.value)}
          className="rounded-xl border border-input bg-card px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
        >
          {DISPUTE_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-xl border border-input bg-card px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
        >
          {STATUS_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-all hover:opacity-90"
        >
          <Plus className="h-4 w-4" />
          新建案件
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && cases.length === 0 && (
        <div className="flex h-48 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      )}

      {/* Case Grid */}
      {!loading && cases.length === 0 && (
        <EmptyState
          title="还没有案件"
          description={"点击\u201C新建案件\u201D按钮，开始创建你的第一个维权案件。"}
          action={
            <button
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90"
            >
              <Plus className="h-4 w-4" />
              新建第一个案件
            </button>
          }
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cases.map((c) => (
          <a
            key={c.id}
            href={`/cases/${c.id}/workspace`}
            onClick={(e) => e.currentTarget.tagName === 'A' && undefined}
          >
            <CaseCard caseData={c} onDelete={deleteTarget === c.id ? undefined : (id) => setDeleteTarget(id)} />
          </a>
        ))}
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-md rounded-2xl border border-border/50 bg-white p-6 shadow-[0_30px_80px_rgba(15,22,40,.35)]" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-foreground">新建案件</h2>
            <p className="mt-1 text-sm text-muted-foreground">填写案件基本信息</p>

            {createError && (
              <div className="mt-4 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{createError}</div>
            )}

            <form onSubmit={handleCreate} className="mt-4 space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-foreground">案件标题</label>
                <input
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="例如：XX平台购物纠纷"
                  className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
                  autoFocus
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-foreground">案件描述</label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="简要描述纠纷情况..."
                  rows={3}
                  className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-foreground">纠纷类型</label>
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value)}
                  className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
                >
                  {DISPUTE_FILTERS.filter(f => f.value).map((f) => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </select>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {creating ? "创建中..." : "创建案件"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirm Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setDeleteTarget(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-border/50 bg-white p-6 shadow-[0_30px_80px_rgba(15,22,40,.35)]" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-foreground">确认删除</h2>
            <p className="mt-2 text-sm text-muted-foreground">确定要删除这个案件吗？此操作不可撤销。</p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setDeleteTarget(null)}
                className="rounded-xl border border-input px-4 py-2 text-sm font-medium text-foreground hover:bg-accent"
              >
                取消
              </button>
              <button
                onClick={() => handleDelete(deleteTarget)}
                className="rounded-xl bg-destructive px-4 py-2 text-sm font-semibold text-white hover:brightness-105"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
