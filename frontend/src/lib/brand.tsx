// 主站品牌视觉共享件：供 HomePage 与 DocsPage 复用，保持顶栏/焦点样式一致。
export const GITHUB_URL = "https://github.com/JeasonLi2024/claimcraft-creative"

// 统一焦点环（米白背景 + 绿色强调）。
export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3f6b57] focus-visible:ring-offset-2 focus-visible:ring-offset-[#f8f8f5]"

export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <img
      src="/logo.webp"
      alt="ClaimCraft logo"
      className={`h-8 w-8 rounded-lg object-cover ${className}`}
    />
  )
}

export function GitHubMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M12 .7a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2.23c-3.22.7-3.9-1.37-3.9-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.04 1.78 2.72 1.27 3.38.97.1-.75.4-1.27.74-1.56-2.57-.29-5.27-1.28-5.27-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.16 1.18A10.96 10.96 0 0 1 12 6.11c.98 0 1.95.13 2.87.39 2.19-1.49 3.16-1.18 3.16-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.42-2.71 5.39-5.29 5.68.42.36.79 1.07.79 2.16v3.25c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z" />
    </svg>
  )
}
