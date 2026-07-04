# ClaimCraft 前端展示效果设计方案（草案 v1）

> 基于 T0-T2 已实现的 10 个视图、main.css 主题体系、展示页视觉风格，提出前端展示效果的统一设计方案。
> 目标：消除双重设计系统割裂、补全视觉锚点、统一交互语言、提升整体品质感。

---

## 一、现状分析

### 1.1 已有优势（保留）

| 优势 | 说明 |
|---|---|
| 主题变量一致 | SPA 与展示页共用同一套 `:root` CSS 变量（bg/ink/muted/rule/accent/accent2） |
| body 渐变背景 | 多层径向渐变（蓝光晕+绿光晕+浅蓝渐变），柔和有层次 |
| 蓝绿渐变品牌语言 | accent→accent2 渐变贯穿徽标、主按钮、时间线竖线、toggle 开关 |
| 状态色彩体系 | 5 色状态（灰/蓝/橙/绿/红）语义清晰 |
| 失焦自动保存 | 时间线/抽取字段编辑体验流畅 |
| 玻璃拟态 topbar | backdrop-filter blur(14px) + 半透明白底 |

### 1.2 核心问题（需修复）

| 问题 | 影响 | 优先级 |
|---|---|---|
| **双重设计系统并存** | 主系统（24px 圆角+渐变+柔和阴影）vs T26 auth/dashboard 系统（8-16px 圆角+扁平），视觉割裂 | P0 |
| **缺少 Hero 视觉锚点** | 展示页有深蓝渐变 Hero 大圆角，SPA 直接进入功能页，缺少品牌沉浸感 | P1 |
| **DashboardView 风格割裂** | 使用独立 `.dashboard-view/.stats-cards/.chart-card` 类，未复用主系统 `.section/.stats/.stat` | P0 |
| **Topbar 圆角差异** | 展示页 topbar 20px 圆角玻璃拟态，SPA topbar 直角通栏 | P1 |
| **路由 Bug** | `/dashboard` 路由引用未导入的 DashboardView 组件，运行时报错 | P0 |
| **无公共组件** | Modal/Section/Lightbox/StatusTag 等高频模式重复内联在视图中 | P2 |
| **重复 JS 逻辑** | formatTime/statusLabel/templates 等 4+ 处重复实现 | P2 |
| **`--max` 变量未定义** | DashboardView 用 `var(--max, 1120px)` 回退，应在 :root 中定义 | P1 |

---

## 二、设计目标与原则

### 2.1 设计目标

1. **统一视觉语言**：消除双重系统，所有视图统一为主系统风格（24px 圆角、柔和阴影、渐变品牌色）
2. **补全品牌沉浸**：在关键入口页（案件列表、仪表盘）新增 Hero 区，与展示页风格呼应
3. **提升信息层次**：通过卡片层次、留白、字号梯度，让信息更易扫读
4. **组件化复用**：抽离高频 UI 模式为公共组件，减少重复代码

### 2.2 设计原则

- **延续而非推翻**：保留现有主题变量与配色，仅统一圆角/阴影/间距等细节
- **功能优先**：展示效果服务于功能使用，不添加纯装饰性动画
- **渐进增强**：先修复 P0 问题，再逐视图打磨 P1/P2
- **响应式优先**：所有布局改动需适配窄屏（≤720px 单列）

---

## 三、视觉系统统一方案

### 3.1 统一圆角语言

| 层级 | 圆角 | 适用场景 |
|---|---|---|
| Hero / 大容器 | 28-32px | 案件列表 Hero、仪表盘 Hero |
| Section 卡片 | 24px | 所有 `.section` 容器 |
| 内嵌卡片 | 16px | mini-card / stat-card / chart-card / format-card |
| 按钮 / 输入框 | 12px | `.btn` / `.form-input` / `.form-select` |
| Pill / 标签 | 999px | `.pill` / `.status-tag` / `.ocr-tag` |
| Modal | 20px | `.modal-box` |

**改动**：将 auth-card（16px）和 dashboard 的 chart-card（12px）统一为 16px，auth-card 阴影改为主系统柔和阴影。

### 3.2 统一阴影语言

| 层级 | 阴影 | 适用场景 |
|---|---|---|
| 容器默认 | `0 10px 30px rgba(20,35,90,.04)` | `.section` / `.case-card` / `.chart-card` |
| 容器悬浮 | `0 14px 36px rgba(20,35,90,.08)` | hover 状态 |
| 玻璃拟态 | `0 8px 24px rgba(17,36,77,.06)` | `.topbar` |
| Modal | `0 30px 80px rgba(15,22,40,.35)` | `.modal-box` |
| 主按钮 | `0 12px 26px rgba(47,107,255,.22)` | `.btn-primary` |

**改动**：auth-card 的 `0 4px 24px rgba(0,0,0,0.08)` 改为容器默认阴影，dashboard stat-card 同步。

### 3.3 补全 :root 变量

```css
:root {
  /* ... 现有变量 ... */
  --max: 1120px;            /* 内容区最大宽度 */
  --radius-lg: 24px;        /* 大容器圆角 */
  --radius-md: 16px;        /* 内嵌卡片圆角 */
  --radius-sm: 12px;        /* 按钮/输入框圆角 */
  --shadow-soft: 0 10px 30px rgba(20,35,90,.04);
  --shadow-hover: 0 14px 36px rgba(20,35,90,.08);
  --shadow-glass: 0 8px 24px rgba(17,36,77,.06);
  --shadow-modal: 0 30px 80px rgba(15,22,40,.35);
  --shadow-btn: 0 12px 26px rgba(47,107,255,.22);
  /* 状态色（标准化） */
  --status-draft: #667085;
  --status-processing: #2f6bff;
  --status-submitted: #f59e0b;
  --status-closed: #11b981;
  --status-cancelled: #ef4444;
}
```

### 3.4 字号梯度

| 层级 | 字号 | 字重 | 用途 |
|---|---|---|---|
| Hero 标题 | 2rem(32px) | 800 | Hero 区主标题 |
| 页面标题 | 1.6rem(25.6px) | 700 | h2 / 工作台案件标题 |
| 卡片标题 | 1.3rem(20.8px) | 700 | `.section h2` |
| 统计数值 | 2rem(32px) | 700 | `.stat .num` / `.stat-value` |
| 正文 | 1rem(16px) | 400 | 默认正文 |
| 辅助文字 | 0.875rem(14px) | 400 | `.section-lead` / meta |
| 标签/提示 | 0.8125rem(13px) | 400 | `.pill` / `.auth-link` |

---

## 四、各视图展示效果设计

### 4.1 LoginView / RegisterView（P0 修复）

**目标**：统一为主系统风格，增加品牌沉浸感。

**改动**：
1. `.auth-card` 圆角从 16px → 20px，阴影改为 `--shadow-soft`
2. `.auth-form input` 圆角从 8px → 12px，focus 阴影改为 `0 0 0 3px rgba(47,107,255,.12)`
3. `.auth-form button` 圆角从 8px → 12px，使用 `.btn-primary` 渐变（蓝绿 135deg）
4. 在 auth-card 顶部增加品牌徽标（蓝绿渐变 C + "ClaimCraft"文字），与 topbar 品牌一致
5. 背景增强：auth-page 底部增加一道径向蓝光晕（`radial-gradient(circle at 50% 80%, rgba(47,107,255,.08), transparent 40%)`）

**视觉效果**：
```
┌─────────────────────────────────┐
│        [C] ClaimCraft            │  ← 品牌徽标
│                                  │
│        登录                       │  ← 24px 标题
│   ┌─────────────────────────┐   │
│   │ 用户名                   │   │  ← 12px 圆角输入框
│   └─────────────────────────┘   │
│   ┌─────────────────────────┐   │
│   │ 密码                     │   │
│   └─────────────────────────┘   │
│   ┌─────────────────────────┐   │
│   │        登录              │   │  ← 蓝绿渐变主按钮
│   └─────────────────────────┘   │
│   还没有账号？去注册              │
└─────────────────────────────────┘
         ↑ 底部蓝光晕
```

### 4.2 CaseListView（P1 增强）

**目标**：新增 Hero 区，提升案件列表的品牌感与信息密度。

**改动**：
1. **新增 Hero 区**（section 上方）：
   - 深蓝渐变背景（`linear-gradient(135deg, #0f1f4d, #17306b, #1d4378)`）
   - 28px 圆角，白色文字
   - 左侧：标题"维权材料工坊" + 副标题"把截图变成可提交的投诉包"
   - 右侧：快速统计（案件数 / 证据数 / 处理中），白色半透明卡片
2. 工具栏样式不变（搜索+筛选+新建）
3. 案件卡片 hover 增加蓝色边框过渡（`border-color: var(--rule) → #c2d8ff`）
4. 空状态优化：`.empty-box` 增加插画图标（emoji 或 SVG）+ "新建第一个案件"引导按钮

**视觉效果**：
```
┌──────────────────────────────────────────────┐
│  维权材料工坊                    案件 3  证据 24 │  ← Hero 深蓝渐变
│  把截图变成可提交的投诉包          处理中 1       │
└──────────────────────────────────────────────┘
┌──────────────────────────────────────────────┐
│ [搜索...]  [类型▾]  [状态▾]        [+ 新建案件] │  ← 工具栏
├──────────┬──────────┬──────────────────────┤
│ 案件卡片1  │ 案件卡片2  │ 案件卡片3              │
│ 标题      │ 标题      │ 标题                  │
│ [类型][状态]│ [类型][状态]│ [类型][状态]            │
│ 描述...    │ 描述...    │ 描述...                │
│ 证据8 6/10 │ 证据5 6/9 │ 证据3 6/8             │
└──────────┴──────────┴──────────────────────┘
```

### 4.3 WorkspaceView（P1 打磨）

**目标**：状态条更直观，统计卡片视觉层次更清晰。

**改动**：
1. 状态条进度圆点增加连接线动画（当前步骤之前的线段渐变填充）
2. 6 卡片统计改用 3 列布局（`.stats.cols-6` 已有），统一卡片样式为 `.mini-card`（16px 圆角）
3. 状态历史时间轴增加 from→to 的箭头动画

**保持不变**：状态色标、推进按钮弹窗、折叠交互。

### 4.4 EvidenceView（P2 打磨）

**目标**：证据卡片信息更紧凑，OCR 展开区更清晰。

**改动**：
1. 证据编号 `.ev-code` 增加蓝绿渐变背景（小圆角徽标，而非纯文字）
2. OCR 展开区的抽取字段表格增加斑马纹（偶数行浅蓝底）
3. 拖拽上传区 dragover 时增加蓝色渐变背景过渡

**保持不变**：拖拽交互、lightbox、失焦保存。

### 4.5 TimelineView（保持现状）

**当前设计已较完善**：蓝绿渐变竖线、可编辑事件输入、自动/手动标签、关联证据 pill。仅微调：
- 节点圆点 hover 增加 tooltip 显示完整时间

### 4.6 ComplaintView（P2 打磨）

**改动**：
1. 模板标签页 active 状态增加底部蓝色指示条（2px 高，渐变色）
2. 证据编号高亮 `.evidence-ref` 增加 hover 效果（加深背景色）
3. 投诉文本区增加等宽字体选项（monospace toggle），方便核对编号

### 4.7 MaskView（P2 打磨）

**改动**：
1. 图片打码前后对比增加"对比模式"切换：并排 / 滑块对比（slider 拖动对比）
2. 打码状态标签 pending 的 spinner 颜色统一为 `--accent`

### 4.8 ExportView（P2 打磨）

**改动**：
1. 导出格式卡片增加图标（📄 文本包 / 📦 ZIP / 📄 PDF），用 SVG 或 emoji
2. selected 状态的边框改为渐变色（`border-image: linear-gradient(135deg, var(--accent), var(--accent2))`）
3. 导出成功结果区增加下载图标动画

### 4.9 DashboardView（P0 修复 + P1 增强）

**目标**：消除风格割裂，统一为主系统风格。

**改动**：
1. **P0 修复路由 Bug**：在 router/index.js 补充 `import DashboardView`
2. `.dashboard-view` 改为复用 `.section` 容器（24px 圆角 + 柔和阴影）
3. `.stats-cards` 改为 `.stats`（4 列），`.stat-card` 改为 `.stat`，统一样式
4. `.chart-card` 圆角从 12px → 16px，阴影改为 `--shadow-soft`
5. `.chart-card h3` 改为 `.section h2` 风格（1.3rem + 底部分割线）
6. **新增 Hero 区**（与 CaseListView 一致的深蓝渐变，显示"数据仪表盘"标题）
7. echarts 配色保持 `['#2f6bff', '#11b981', '#f59e0b', '#ef4444']`（与状态色体系一致）

**视觉效果**：
```
┌──────────────────────────────────────────────┐
│  数据仪表盘                                   │  ← Hero 深蓝渐变
│  洞察案件分布与处理趋势                         │
└──────────────────────────────────────────────┘
┌─────────┬─────────┬─────────┬─────────┐
│ 案件 3   │ 证据 24  │ 字段 18  │ 处理中 1 │  ← 统计卡片（主系统风格）
└─────────┴─────────┴─────────┴─────────┘
┌──────────────┬──────────────┐
│ [饼图]       │ [柱状图]      │  ← 图表卡片（16px 圆角）
│ 案件类型分布  │ 案件状态分布   │
├──────────────┼──────────────┤
│ [折线图]     │ [柱状图]      │
│ 30天趋势     │ 状态转换统计   │
└──────────────┴──────────────┘
```

---

## 五、Topbar 统一方案

### 5.1 圆角玻璃拟态统一

**展示页 topbar**：20px 圆角 + backdrop-filter blur(14px) + 半透明白底
**SPA topbar**：直角通栏 + backdrop-filter blur(14px) + 半透明白底

**改动**：SPA topbar 保持直角通栏（因 SPA 内容区更宽，通栏更协调），但增加底部 1px 渐变分割线（`border-bottom: 1px solid transparent; border-image: linear-gradient(90deg, var(--accent), var(--accent2)) 1`），呼应品牌渐变。

### 5.2 导航项视觉优化

- 已登录态：topbar-actions 的"数据仪表盘"/"我的案件"链接增加 active 下划线指示
- 用户名区域增加头像占位符（蓝绿渐变圆形，显示用户名首字母）

---

## 六、公共组件抽离方案（P2）

### 6.1 建议抽离的组件

| 组件 | 路径 | 复用视图 | 说明 |
|---|---|---|---|
| `SectionCard.vue` | `components/SectionCard.vue` | 7 个视图 | `.section` + h2 + lead 的封装 |
| `AppModal.vue` | `components/AppModal.vue` | CaseList(2) / Workspace(1) | Modal mask + box + head/body/foot |
| `Lightbox.vue` | `components/Lightbox.vue` | Evidence / Mask | 全屏大图预览 |
| `StatusTag.vue` | `components/StatusTag.vue` | CaseList / Workspace / Dashboard | 状态色标标签 |
| `PillTag.vue` | `components/PillTag.vue` | CaseList / Evidence / Timeline / Mask | 通用 pill 标签 |
| `EmptyState.vue` | `components/EmptyState.vue` | 所有视图 | loading/error/empty 三件套 |

### 6.2 建议抽离的 Composables

| Composable | 路径 | 复用视图 | 说明 |
|---|---|---|---|
| `useFormat` | `composables/useFormat.js` | 4+ 视图 | formatTime 统一实现 |
| `useStatus` | `composables/useStatus.js` | 3+ 视图 | statusLabel / statusColor / transitions 映射 |
| `useTemplates` | `composables/useTemplates.js` | Complaint / Export | 3 套模板定义 |
| `useLightbox` | `composables/useLightbox.js` | Evidence / Mask | open/close lightbox 逻辑 |

---

## 七、响应式策略

### 7.1 断点规范

| 断点 | 布局变化 |
|---|---|
| ≥1100px | 案件卡片 3 列、图表 2×2、统计 4 列 |
| 920-1099px | 案件卡片 2 列、sidebar 横滚、统计 4 列 |
| 720-919px | 案件卡片 1 列、sidebar 横滚、统计 2 列、图表 1 列 |
| ≤719px | 全部单列、topbar 紧凑（隐藏用户名只显头像） |

### 7.2 移动端适配优化

- Hero 区在 ≤720px 时高度减半，统计卡片隐藏（仅保留标题+副标题）
- 拖拽上传区在移动端改为点击触发（已支持，但 dragover 提示需隐藏）
- 表格类（mask-table / field-table）改为卡片堆叠模式

---

## 八、实现优先级

### P0（立即修复）

1. 修复 DashboardView 路由 import Bug
2. 补全 `:root` 变量（--max / --radius-* / --shadow-* / --status-*）
3. 统一 auth-card / dashboard 样式为主系统风格（圆角+阴影）
4. DashboardView 改为复用 `.section` / `.stats` 类

### P1（视觉增强）

5. CaseListView 新增 Hero 区
6. DashboardView 新增 Hero 区
7. LoginView/RegisterView 增加品牌徽标 + 背景光晕
8. Topbar 底部渐变分割线 + 用户头像占位符

### P2（组件化 + 打磨）

9. 抽离 SectionCard / AppModal / Lightbox / StatusTag 公共组件
10. 抽离 useFormat / useStatus / useTemplates composables
11. 各视图细节打磨（证据编号徽标、模板标签指示条、导出卡片图标等）
12. 移动端适配优化（Hero 减半、表格卡片堆叠）

---

## 九、验收标准

- [ ] 所有视图圆角/阴影统一为主系统风格（无 8px/12px 扁平卡片）
- [ ] `:root` 含 --max / --radius-* / --shadow-* / --status-* 变量
- [ ] CaseListView 与 DashboardView 含 Hero 区（深蓝渐变 + 28px 圆角）
- [ ] LoginView/RegisterView 含品牌徽标 + 背景光晕
- [ ] DashboardView 复用 `.section` / `.stats` 类，无独立 `.dashboard-view` 类
- [ ] `/dashboard` 路由无运行时错误
- [ ] Topbar 含底部渐变分割线 + 用户头像占位符
- [ ] npm run build 无错误
- [ ] 窄屏（720px）所有视图单列布局正常
