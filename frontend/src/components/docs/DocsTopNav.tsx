// Docs 顶栏：品牌(ClaimCraftDocs) + 返回首页 + 搜索 + GitHub + 「体验 ClaimCraft」。
// 与主站顶栏同款（sticky + 毛玻璃 + 米白墨色调色板）。
import { Link } from "react-router"
import { Home } from "lucide-react"
import { useAuthStore } from "@/stores/auth-store"
import { BrandMark, GitHubMark, GITHUB_URL, focusRing } from "@/lib/brand"
import { DocsSearch } from "./DocsSearch"

export function DocsTopNav() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  return (
    <header className="sticky top-0 z-30 border-b border-[#d9ddd5]/80 bg-[#f8f8f5]/90 backdrop-blur-md">
      <nav className="mx-auto flex h-16 max-w-[1400px] items-center gap-3 px-4 sm:px-6 lg:px-8">
        {/* 左：品牌 + 返回首页 */}
        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <Link to="/docs" className={`flex items-center gap-2.5 rounded-lg ${focusRing}`} aria-label="ClaimCraft Docs 首页">
            <BrandMark />
            <span className="font-semibold tracking-[-0.01em]">
              ClaimCraft<span className="text-[#3f6b57]">Docs</span>
            </span>
          </Link>
          <span className="hidden h-5 w-px bg-[#d9ddd5] sm:block" aria-hidden="true" />
          <Link
            to="/home"
            className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-medium text-[#6c706b] transition-colors hover:bg-[#f1f2ee] hover:text-[#181b1a] ${focusRing}`}
          >
            <Home className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">首页</span>
          </Link>
        </div>

        {/* 中：搜索 */}
        <div className="flex min-w-0 flex-1 justify-center">
          <DocsSearch />
        </div>

        {/* 右：GitHub + 体验 */}
        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="在 GitHub 打开 ClaimCraft 项目仓库"
            className={`inline-flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium text-[#6c706b] transition-colors hover:bg-[#f1f2ee] hover:text-[#181b1a] ${focusRing}`}
          >
            <GitHubMark className="h-4 w-4" />
            <span className="hidden md:inline">GitHub</span>
          </a>
          <Link
            to={isAuthenticated ? "/cases" : "/login"}
            className={`inline-flex shrink-0 items-center justify-center rounded-lg bg-[#181b1a] px-3.5 py-2 text-sm font-semibold text-[#f8f8f5] transition-colors hover:bg-[#2b302d] ${focusRing}`}
          >
            体验 ClaimCraft
          </Link>
        </div>
      </nav>
    </header>
  )
}

export default DocsTopNav
