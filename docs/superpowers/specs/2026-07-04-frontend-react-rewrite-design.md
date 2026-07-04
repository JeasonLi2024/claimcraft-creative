# ClaimCraft 前端全量重写设计规范

> Vue 3 SPA -> React 19 + TypeScript + shadcn/ui + Tailwind CSS v4 + Zustand + React Router v7
>
> 日期: 2026-07-04
>
> 状态: 待审核

---

## 1. 背景与动机

ClaimCraft 维权材料工坊前端当前基于 Vue 3 + Vite + Pinia，包含 10 个视图（Login、Register、CaseList、Workspace、Evidence、Timeline、Complaint、Mask、Export、Dashboard），使用手写 CSS（main.css 约 1600 行）。

核心问题：
- **双重设计系统**：主系统（24px 圆角 + 渐变 + 柔和阴影）与 auth/dashboard 系统（8-16px 圆角 + 扁平）并存，视觉割裂
- **缺少品牌沉浸**：SPA 直接进入功能页，无 Hero 视觉锚点
- **DashboardView 风格割裂**：使用独立 `.dashboard-view` / `.stats-cards` / `.chart-card` 类，未复用主系统
- **路由 Bug**：`/dashboard` 引用未导入的 DashboardView
- **重复代码**：`formatTime`、`statusLabel` 等在 4+ 视图中重复实现
- **无公共组件**：Modal、Lightbox、StatusTag 等高频模式内联在各视图中

决定采用全量重写方案（React + shadcn/ui），原因：
- 框架升级带来组件化能力质的提升
- shadcn/ui 提供成熟的组件体系，避免重复造轮子
- TypeScript 提供类型安全，减少运行时错误
- Tailwind CSS v4 的 CSS 变量系统天然支持品牌主题定制

---

## 2. 技术栈

| 包 | 版本 | 职责 |
|---|---|---|
| `react` / `react-dom` | 19.x | UI 框架 |
| `vite` | 6.x | 构建工具 |
| `@vitejs/plugin-react` | latest | React Vite 插件 |
| `tailwindcss` + `@tailwindcss/vite` | 4.x | 原子化 CSS |
| `shadcn/ui` | latest (new-york) | 组件系统 |
| `zustand` | 5.x | 状态管理（persist + devtools） |
| `react-router` | 7.x | 客户端路由 |
| `axios` | latest | HTTP 客户端 |
| `recharts` | 2.x | 图表（替代 ECharts） |
| `lucide-react` | latest | 图标库 |
| `date-fns` | 4.x | 日期格式化 |
| `clsx` + `tailwind-merge` | latest | className 合并工具 |

无其他外部依赖。所有 UI 组件来自 shadcn/ui（源码级引入）或自定义封装。

---

## 3. 项目结构

```
frontend/
  src/
    components/
      ui/                # shadcn/ui 生成组件
        button.tsx
        card.tsx
        input.tsx
        dialog.tsx
        badge.tsx
        table.tsx
        select.tsx
        textarea.tsx
        tabs.tsx
        dropdown-menu.tsx
        skeleton.tsx
        tooltip.tsx
        separator.tsx
        scroll-area.tsx
      HeroSection.tsx    # 深蓝渐变 Hero 区
      StatusTag.tsx      # 5 色状态标签
      PillTag.tsx        # 通用 pill 标签
      EvidenceCard.tsx   # 证据卡片
      CaseCard.tsx       # 案件卡片
      EmptyState.tsx     # 空/加载/错误状态三件套
      Lightbox.tsx       # 全屏大图预览
      BrandLogo.tsx      # 品牌徽标（蓝绿渐变 C + ClaimCraft）
      UserAvatar.tsx     # 用户头像（首字母圆形）
      Dropzone.tsx       # 拖拽上传区
      OcrSection.tsx     # OCR 可展开区
      FieldTable.tsx     # 抽取字段编辑表
      TimelineTrack.tsx   # 垂直时间线
      StatusTimeline.tsx  # 状态历史时间线
      FormatCard.tsx     # 导出格式卡片
    composables/
      useFormat.ts       # formatTime 等格式化工具
      useStatus.ts       # statusLabel / statusColor 映射
      useLightbox.ts     # Lightbox open/close 逻辑
      useDebounce.ts     # 搜索防抖
    stores/
      auth-store.ts      # 认证状态（Zustand + persist）
      case-store.ts      # 案件/证据/时间线/投诉/打码/导出/统计
    lib/
      api-client.ts      # Axios 实例 + JWT 拦截器
      api.ts             # 类型安全的 API 函数
      utils.ts           # cn() 等 shadcn/ui 工具
    types/
      case.ts            # Case, Evidence, TimelineNode 等接口
      auth.ts            # User, LoginDTO, RegisterDTO
      api.ts             # API 响应类型
    pages/
      LoginPage.tsx
      RegisterPage.tsx
      CaseListPage.tsx
      DashboardPage.tsx
      WorkspacePage.tsx
      EvidencePage.tsx
      TimelinePage.tsx
      ComplaintPage.tsx
      MaskPage.tsx
      ExportPage.tsx
    layouts/
      AuthLayout.tsx     # 居中卡片布局（登录/注册）
      AppLayout.tsx      # Topbar + Sidebar + Main
  index.html
  vite.config.ts
  tsconfig.json
  tsconfig.app.json
  components.json        # shadcn/ui 配置
  package.json
```

---

## 4. 品牌主题系统

### 4.1 CSS 变量映射

现有 ClaimCraft 变量到 shadcn/ui 语义 token 的映射：

```
现有变量              shadcn/ui token         用途
--accent: #2f6bff  -> --primary              主色（按钮、链接、活跃状态）
--accent2: #11b981 -> --accent2 (自定义)      辅助色（渐变终点、成功态）
--bg: #f6f8fc      -> --background           页面背景
--bg2: #ffffff     -> --card                 卡片背景
--ink: #172033     -> --foreground           主文字
--muted: #667085    -> --muted-foreground     辅助文字
--rule: #dfe6f3    -> --border               边框/分割线
```

### 4.2 状态色彩体系

```
草稿 (draft)       -> --status-draft:    #667085 (灰)
处理中 (processing) -> --status-processing: #2f6bff (蓝)
已提交 (submitted)  -> --status-submitted:  #f59e0b (橙)
已结案 (closed)     -> --status-closed:     #11b981 (绿)
已取消 (cancelled)  -> --status-cancelled:  #ef4444 (红)
```

### 4.3 阴影与圆角

```
--shadow-soft:   0 10px 30px rgba(20,35,90,.04)    卡片默认
--shadow-hover:  0 14px 36px rgba(20,35,90,.08)    悬浮态
--shadow-glass:  0 8px 24px rgba(17,36,77,.06)     玻璃拟态
--shadow-modal:  0 30px 80px rgba(15,22,40,.35)    弹窗
--shadow-btn:    0 12px 26px rgba(47,107,255,.22)  主按钮

--radius-lg: 24px   大容器 / Section
--radius-md: 16px   内嵌卡片 / stat-card
--radius-sm: 12px   按钮 / 输入框
```

### 4.4 蓝绿渐变品牌语言

贯穿以下元素：
- BrandLogo 徽标
- 主按钮 (`bg-gradient-to-br from-primary to-accent2`)
- Hero 区背景
- 时间线竖线
- Toggle 开关激活态
- Topbar 底部分割线

---

## 5. 布局系统

### 5.1 AuthLayout

- 全屏居中，多层渐变背景（蓝光晕 + 绿光晕）
- 居中 Card（max-width 400px, 20px 圆角）
- Card 顶部 BrandLogo + "ClaimCraft" 文字
- 底部径向蓝光晕

### 5.2 AppLayout

**Topbar:**
- `sticky top-0 z-20`
- 玻璃拟态：`backdrop-blur-[14px] bg-white/82`
- 左侧 BrandLogo（渐变 C + "ClaimCraft"）
- 右侧：导航链接（"数据仪表盘"、"我的案件"）、UserAvatar（蓝绿渐变圆形 + 首字母）、退出按钮、"返回介绍页"链接
- 底部渐变分割线（2px，蓝到绿渐变）
- 已登录态导航链接增加 active 下划线指示

**Sidebar:**
- `sticky top-[84px]`，220px 宽
- 18px 圆角，淡蓝渐变背景
- nav-item 14px 圆角，active 态蓝底 + 蓝边
- 仅在 caseId 存在时显示案件子导航（6 项）

**响应式断点:**

| 断点 | 布局变化 |
|---|---|
| >=1100px | 3 列案件卡片、2x2 图表、4 列统计 |
| 920-1099px | 2 列案件卡片、sidebar 水平滚动 |
| 720-919px | 1 列案件卡片、sidebar 水平滚动、2 列统计 |
| <=719px | 全部单列、sidebar 折叠为汉堡菜单 |

---

## 6. 页面设计规范

### 6.1 LoginPage / RegisterPage

- AuthLayout 包裹
- Card 内：品牌徽标、h1 标题（1.5rem/800）、form-input（12px 圆角）、主按钮（蓝绿渐变）
- 底部 auth-link："还没有账号？去注册" / "已有账号？去登录"
- 输入框 focus：蓝色边框 + `ring-3` 蓝色光环
- 错误提示：红色背景 pill

### 6.2 CaseListPage

- HeroSection：深蓝渐变（135deg, #0f1f4d -> #17306b -> #1d4378），28px 圆角
  - 左侧：标题"维权材料工坊" + 副标题"把截图变成可提交的投诉包"
  - 右侧：快捷统计（案件数 / 证据数 / 处理中），白色半透明卡片
- 工具栏：shadcn Input（搜索）+ shadcn Select（纠纷类型/状态筛选）+ 主按钮"新建案件"
- 案件网格：3 列 -> 2 列 -> 1 列响应式
- CaseCard：18px 圆角，hover 蓝色边框过渡 + 上浮
  - 标题、PillTag（纠纷类型）、StatusTag（状态）、描述（2 行截断）、meta（证据数 + 时间）
  - 右上角删除按钮
- 新建弹窗：shadcn Dialog，含表单（标题、描述、纠纷类型 Select）+ 预设骨架复选
- 删除确认弹窗：shadcn Dialog
- 空状态：EmptyState + "新建第一个案件"引导按钮

### 6.3 DashboardPage

- HeroSection：同 CaseListPage 风格，标题"数据仪表盘"，副标题"洞察案件分布与处理趋势"
- 统计卡片：4 列，shadcn Card（16px 圆角 + --shadow-soft）
  - 案件总数 / 证据总数 / 抽取字段总数 / 处理中案件数
  - 数值 2rem/700 蓝色，标签 .93rem muted
- 图表网格：2x2，shadcn Card（16px 圆角）
  - 饼图：案件类型分布（Recharts PieChart）
  - 柱状图：案件状态分布（Recharts BarChart，颜色匹配状态色体系）
  - 折线图：30 天趋势（Recharts LineChart，蓝色面积渐变）
  - 柱状图：状态转换统计（Recharts BarChart，绿色）
- 图表高度 280px，响应式 1 列

### 6.4 WorkspacePage

- 状态条：18px 圆角卡片，左侧 StatusTag + "当前状态"，中间进度圆点（done/active/cancelled），右侧"推进状态"按钮
- 案件标题：1.6rem/700
- 描述文字：muted 色
- 6 统计卡片：3 列网格（mini-card 风格，16px 圆角）
  - 证据数量 / 关键节点数 / 投诉版本数 / 处理状态 / 图片证据数 / 抽取字段数
- 状态历史：可折叠，StatusTimeline 组件（渐变竖线 + 圆点节点 + from->to 箭头）
- 推进状态弹窗：shadcn Dialog，当前状态展示 + 目标状态 Select + 备注 Textarea

### 6.5 EvidencePage

- 页面标题 + 副标题说明
- Dropzone 组件：拖拽上传区，dragover 蓝色渐变背景过渡
  - 图标 + "拖拽图片到此处上传" + 支持格式提示
  - 上传中状态："正在上传并识别..."
- "添加示例证据"按钮
- 证据网格：2 列 -> 1 列
- EvidenceCard：
  - 顶部：ev-code（蓝绿渐变徽标背景）+ pill（证据类型）+ OCR 状态标签
  - 图片缩略图（12px 圆角，hover 上浮 + 阴影）
  - 或文本描述
  - 来源时间（mono 字体）
  - OCR 可展开区：箭头 + "OCR 识别结果"，展开后显示 OCR 文本 + FieldTable
  - FieldTable：字段名 / 可编辑值（失焦保存） / 置信度，斑马纹
  - 删除按钮
- Lightbox：全屏暗背景 + 大图（12px 圆角）

### 6.6 TimelinePage

- 页面标题 + 副标题
- "重新生成时间线"主按钮
- TimelineTrack 组件：渐变竖线（蓝->绿）+ 圆点节点
  - 每个节点：日期（mono）+ 可编辑输入框（12px 圆角，失焦自动保存）+ gen-pill（自动/手动）+ 证据 pill
  - 节点圆点 hover：tooltip 显示完整时间

### 6.7 ComplaintPage

- 页面标题 + 副标题
- 模板标签页：shadcn Tabs（平台客服版 / 监管投诉版 / 仲裁准备版）
  - active 态：底部 2px 蓝绿渐变指示条
- 操作栏："复制全文"按钮 + "重新生成"按钮 + 已复制提示
- 投诉标题：1.35rem/800
- 投诉正文：pre-wrap，等宽字体选项（mono toggle）
  - 证据编号（E1/E2）高亮为 evidence-ref span
- 加载态：Skeleton
- 空态：EmptyState

### 6.8 MaskPage

- 页面标题 + 副标题
- 文本打码 ToggleRow：toggle 开关 + "开启后显示打码后内容"
- 文本打码结果表格：shadcn Table
  - 证据编号 / 类型（PillTag） / 打码后或原文
  - 类型检测：手机号(amber) / 身份证号(red) / 地址(green)
- 图片打码区：
  - 标题 + "一键打码所有图片"按钮
  - 图片网格：每个证据含原图 + 打码后图
  - mi-code + pill + mask-status-tag（含 spinner 动画）
  - 对比模式：并排显示，可扩展滑块对比
  - 图片点击打开 Lightbox

### 6.9 ExportPage

- 页面标题 + 副标题
- 格式选择：3 个 FormatCard（文本包 / ZIP / PDF）
  - Lucide 图标（FileText / Archive / FileDown）
  - selected 态：渐变边框
- 文本包选项：模板 Tabs + 打码复选框
- PDF 选项：模板 Select 下拉
- ZIP 说明文本
- "导出"主按钮
- 导出成功：绿色摘要卡片 + 文件信息列表
- 错误态：红色提示

---

## 7. 自定义 Hooks

### 7.1 useFormat

```typescript
export function useFormat() {
  function formatTime(value: string | null | undefined): string
  function formatDate(value: string): string
  function confText(c: number | null): string
}
```

### 7.2 useStatus

```typescript
export function useStatus() {
  const STATUS_LABEL: Record<string, string>
  const STATUS_COLOR: Record<string, string>
  const MAIN_FLOW: string[]
  const TRANSITIONS: Record<string, string[]>
  function statusLabel(s: string): string
  function statusColor(s: string): string
  function disputeLabel(t: string): string
}
```

### 7.3 useLightbox

```typescript
export function useLightbox() {
  const src: Ref<string | null>
  function open(src: string): void
  function close(): void
}
```

### 7.4 useDebounce

```typescript
export function useDebounce<T>(value: T, delay: number): T
```

---

## 8. 状态管理（Zustand）

### 8.1 auth-store

```typescript
interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  setAuth: (user: User, token: string) => void
  clearAuth: () => void
  initialize: () => Promise<void>
}
// persist middleware: token -> localStorage
```

### 8.2 case-store

```typescript
interface CaseState {
  currentCase: Case | null
  cases: Case[]
  evidences: Evidence[]
  timelineNodes: TimelineNode[]
  currentTemplate: string
  complaintData: ComplaintData | null
  maskResults: MaskResult[]
  masked: boolean
  statusLogs: StatusLog[]
  stats: DashboardStats | null
  casePresets: CasePreset[]
  presetLoading: boolean
  extractedFieldsMap: Record<string, ExtractedField[]>
  loading: boolean
  error: string | null
  // 30+ actions: fetchCases, createCase, deleteCase, ...
}
```

---

## 9. API 层

### 9.1 Axios 实例

- `baseURL: /api`（dev 由 Vite proxy 代理到 localhost:8000）
- 请求拦截器：从 `useAuthStore.getState().token` 注入 `Authorization: Bearer`
- 响应拦截器：401 -> `clearAuth()` + 跳转 `/login`

### 9.2 API 函数

类型安全封装，分模块：
- `authApi`：login, register, me
- `casesApi`：list, get, create, update, delete, transitionStatus, fetchStatusLogs
- `evidenceApi`：list, add, delete, upload, getFields, updateField
- `timelineApi`：list, updateNode, rebuild
- `complaintApi`：get, regenerate
- `maskApi`：getResults, maskImages
- `exportApi`：exportText, exportPackage, exportPDF
- `statsApi`：getDashboard
- `presetsApi`：list, apply

---

## 10. 路由配置

```typescript
Routes:
  /login            -> LoginPage     (public)
  /register         -> RegisterPage  (public)
  /                 -> redirect /cases
  /cases            -> CaseListPage  (protected)
  /dashboard        -> DashboardPage (protected)
  /cases/:caseId/workspace  -> WorkspacePage  (protected)
  /cases/:caseId/evidence    -> EvidencePage   (protected)
  /cases/:caseId/timeline    -> TimelinePage   (protected)
  /cases/:caseId/complaint   -> ComplaintPage  (protected)
  /cases/:caseId/mask        -> MaskPage       (protected)
  /cases/:caseId/export      -> ExportPage     (protected)
```

Auth guard：未认证访问受保护路由 -> 跳转 `/login`（携带 `from` 状态用于登录后回跳）

---

## 11. 响应式策略

| 断点 | Topbar | Sidebar | 案件卡片 | 图表 | 统计卡片 | 表格 |
|---|---|---|---|---|---|---|
| >=1100px | 完整 | 220px 竖向 | 3 列 | 2x2 | 4 列 | 完整 |
| 920-1099px | 完整 | 水平滚动 | 2 列 | 2x2 | 4 列 | 横滚 |
| 720-919px | 紧凑 | 水平滚动 | 1 列 | 1 列 | 2 列 | 横滚 |
| <=719px | 仅头像+汉堡 | 汉堡菜单 | 1 列 | 1 列 | 2 列 | 卡片堆叠 |

移动端特殊处理：
- Hero 区统计卡片隐藏（仅保留标题 + 副标题）
- 拖拽上传区隐藏 dragover 提示，仅点击触发
- mask-table / field-table 变为卡片堆叠模式

---

## 12. 暗色模式

通过 shadcn/ui CSS 变量系统实现：
- `.dark` class 切换（挂载在 `<html>` 上）
- 所有 shadcn/ui 组件自动适配
- 自定义组件通过 Tailwind `dark:` 前缀适配
- 品牌渐变在暗色模式下使用更亮的色值
- 暂不在 MVP 中实现，但 CSS 变量体系预留暗色 token

---

## 13. 性能优化

- **代码分割**：每个页面使用 `React.lazy()` + `Suspense`
- **图表按需加载**：Recharts 仅在 DashboardPage 导入
- **图片懒加载**：证据缩略图使用 `loading="lazy"`
- **Zustand 选择性订阅**：组件仅订阅需要的 store slice，避免不必要重渲染
- **API 请求取消**：组件卸载时取消未完成请求

---

## 14. 实施阶段

### Phase 1: 项目脚手架 + 设计令牌
- Init Vite + React 19 + TypeScript
- 配置 Tailwind CSS v4 + shadcn/ui (new-york)
- 品牌主题映射（CSS 变量）
- Zustand stores + Axios 拦截器 + React Router v7
- 项目目录结构
- 基础 shadcn/ui 组件安装
- **验证点**: dev server 运行，auth 流程与后端联通

### Phase 2: 布局系统 + 认证页面
- AuthLayout + AppLayout
- LoginPage + RegisterPage
- Topbar（品牌徽标 + 渐变底边 + 用户头像）
- Sidebar（sticky + active 态 + 响应式）
- **验证点**: 登录/注册完整流程，布局响应式

### Phase 3: 案件列表 + 仪表盘 + Hero 系统
- HeroSection 组件
- CaseListPage（Hero + 工具栏 + 案件网格 + 弹窗）
- DashboardPage（Hero + 统计卡片 + Recharts 图表）
- StatusTag + CaseCard + EmptyState
- **验证点**: 案件 CRUD，仪表盘图表渲染

### Phase 4: 案件工作台 6 视图
- WorkspacePage + EvidencePage + TimelinePage
- ComplaintPage + MaskPage + ExportPage
- 自定义 Hooks（useFormat, useStatus, useLightbox, useDebounce）
- Dropzone + Lightbox + OcrSection + TimelineTrack 等组件
- **验证点**: 所有 6 视图功能与后端 API 联通

### Phase 5: 打磨 + 响应式优化
- 证据编号渐变徽标、模板标签指示条、导出卡片图标
- 空状态插图（Lucide）、骨架屏、错误重试
- 移动端适配（Hero 减半、表格卡片堆叠、上传区点击）
- 暗色模式 CSS 预留
- React.lazy 代码分割
- **验证点**: 所有断点、所有流程、npm run build 无错误

---

## 15. 验收标准

- [ ] React 19 + TypeScript + shadcn/ui 项目脚手架可运行
- [ ] 品牌主题 CSS 变量体系完整（primary/accent2/status-5色/shadow-5级/radius-3级）
- [ ] Login/Register 使用 shadcn Card + Input + Button，含品牌徽标
- [ ] AppLayout（Topbar + Sidebar）响应式正常
- [ ] CaseListPage 含 Hero 区 + 案件网格（3/2/1 列）+ CRUD 弹窗
- [ ] DashboardPage 含 Hero 区 + 4 统计卡片 + 2x2 Recharts 图表
- [ ] 6 个工作台视图（Workspace/Evidence/Timeline/Complaint/Mask/Export）功能完整
- [ ] 自定义 Hooks 替代重复工具函数（useFormat/useStatus/useLightbox）
- [ ] 拖拽上传、OCR 展开、失焦保存、Lightbox 等交互正常
- [ ] 所有 StatusTag / PillTag / Badge 使用 5 色状态体系
- [ ] <=720px 全部单列布局
- [ ] `npm run build` 无 TypeScript 错误
- [ ] 与后端 API 全部联通（认证、案件 CRUD、证据上传、OCR、时间线、投诉、打码、导出、统计）
