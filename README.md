# ClaimCraft 维权材料工坊

> 把"截图 + 聊天记录"一键变成可提交的投诉与证据包。

普通用户遇到网购纠纷、退款扯皮、服务违约时，往往"证据散、时间线乱、不会写投诉材料"。ClaimCraft 通过 OCR + 信息抽取 + 时间线重建 + 模板渲染，把最费时间的整理工作自动化，输出可直接复制粘贴的标准化证据包。

项目已完成 T0（核心链路）→ T1（产品闭环）→ T2（工程化）三阶段迭代，前端基于 **React 19 + TypeScript + Golden Time 设计系统** 全量重写，后端提供 27 条 RESTful API，支持 Docker 一键部署。

---

## 设计说明

### 产品定位

ClaimCraft 是一个"维权材料工坊"：用户只需上传证据截图，系统自动完成 OCR 识别 → 关键信息抽取 → 时间线重建 → 投诉文本生成 → 隐私打码 → 多格式导出的全链路工作，并辅以多案件管理、状态流转、数据仪表盘等工程化能力。

### 视觉设计系统（Golden Time）

前端采用 **Golden Time** 设计系统，定位为"编辑风格的工坊语调"：

- **主色调**：cocoa 棕 `#3b352b`（`--primary`，亦为正文色），传达稳重与权威感
- **背景**：parchment 羊皮纸 `#fbfaf9`（`--background` / `--card` / `--popover` 共用），营造纸质书写的温润感
- **辅色**：`--secondary #9b965f`、`--accent #cbc0aa`、`--muted #eae6db`，构成暖中性色阶
- **字体**：单一衬线字体 **Fraunces**（`ui-serif` 回退），heading 与正文同源，形成"全篇署名感"的编辑器气质
- **圆角**：单一 `--radius: 2rem`（32px），card / button / input 共用同一弧度，强调一致与柔和
- **阴影**：刻意"几乎不可见"（opacity 为 0），层级关系靠 border 与色阶区分，不靠投影戏法
- **状态色阶**：5 色状态体系
  - draft `#978365`（草稿，浅可可）
  - processing `#9b965f`（处理中，暖灰）
  - submitted `#d6a84b`（已提交，金箔）
  - closed `#7a8c5e`（已结案，苔绿）
  - cancelled `#c45c4a`（已取消，赭红）
- **图表色阶**：5 色图表 token（`#d6d5c2` → `#f79b45`），保证可视化对比但不喧宾夺主
- **暗色模式**：`#060201` 背景 + `#e3dfd6` 文字，保留同样的编辑式暖调

### 语调与文案

界面文案遵循 Golden Time 的"editorial briefing"语调：标签 sentence-case、措辞克制、关键操作显式标注、不使用感叹号与营销话术。例如：

- 顶部主操作："发布简报"
- 搜索占位："搜索案件、证据或备注"
- 危险路径：单独标注、不与主操作竞争

---

## 技术栈

### 后端

| 层 | 技术 |
|---|---|
| 框架 | Django 5 + Django REST Framework |
| 数据库 | MySQL 8.0（PyMySQL 驱动） |
| 状态机 | django-fsm（5 条状态转换） |
| 鉴权 | djangorestframework-simplejwt（access 2h / refresh 7d） |
| OCR | Tesseract + pytesseract（chi_sim + eng） |
| 图片处理 | Pillow（缩略图、打码模糊） |
| PDF 生成 | reportlab（字体三级回退 simsun.ttc → STSong-Light → Helvetica） |
| 模板引擎 | Jinja2（投诉文本动态渲染） |
| 部署 | gunicorn + nginx |

### 前端

| 层 | 技术 |
|---|---|
| 框架 | React 19 + TypeScript |
| 构建 | Vite 8 |
| 样式 | Tailwind CSS v4（`@tailwindcss/vite` 插件 + `@theme inline` token 映射） |
| 状态管理 | Zustand 5（auth-store / case-store） |
| 路由 | React Router v7（lazy loading + Suspense + AuthGuard/PublicOnly 守卫） |
| HTTP | Axios（带 baseURL 拦截器 + JWT 自动注入） |
| 可视化 | Recharts 3（数据仪表盘） |
| 图标 | lucide-react |
| 工具库 | date-fns（时间格式化）、clsx + tailwind-merge（className 合并） |

### 部署

| 项 | 技术 |
|---|---|
| 容器化 | Docker（多阶段构建） |
| 编排 | docker-compose（mysql + backend + frontend 三服务） |
| 反代 | nginx（SPA fallback + `/api` + `/media` 反代） |
| 应用服务器 | gunicorn（backend） |

---

## 代码文件树说明

```
claimcraft-creative/
├── backend/                              # Django 后端
│   ├── api/
│   │   ├── models.py                    # 7 个数据模型
│   │   ├── views.py                     # ~20 个视图类（全部按 owner 过滤）
│   │   ├── serializers.py               # DRF 序列化器
│   │   ├── permissions.py               # IsOwner 鉴权
│   │   ├── urls.py                      # 27 条 API 路由
│   │   ├── admin.py                     # Django Admin 注册
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   ├── 0002_evidence_*.py
│   │   │   ├── 0003_case_*.py
│   │   │   ├── 0004_case_owner.py       # T2：用户体系
│   │   │   └── 0005_casetypepreset.py   # T2：案件预设
│   │   └── services/                    # 9 个业务服务
│   │       ├── ocr_service.py           # OCR 识别（Tesseract + Mock 回退）
│   │       ├── extraction_service.py    # 正则信息抽取
│   │       ├── timeline_service.py      # 时间线重建
│   │       ├── complaint_service.py     # Jinja2 投诉文本生成
│   │       ├── evidence_service.py      # 证据管理
│   │       ├── mask_service.py          # 文本打码
│   │       ├── image_mask_service.py    # 图片打码（pytesseract 定位 + 高斯模糊）
│   │       ├── export_service.py        # ZIP 包导出
│   │       └── pdf_service.py           # PDF 生成（字体三级回退）
│   ├── claimcraft/                      # 项目配置
│   │   ├── settings.py                  # JWT + MySQL + 环境变量分层
│   │   ├── urls.py                      # /api/ 路由聚合
│   │   ├── wsgi.py / asgi.py
│   ├── seed_data.json                   # 种子数据（admin 用户 + 案件 + 证据 + 模板 + 预设）
│   ├── requirements.txt
│   └── manage.py
├── frontend/                            # React 19 + TypeScript 前端
│   ├── src/
│   │   ├── App.tsx                      # 路由根（lazy + Suspense + 守卫）
│   │   ├── main.tsx                     # 入口
│   │   ├── index.css                    # Golden Time 设计系统 token
│   │   ├── components/                  # 5 个公共组件
│   │   │   ├── CaseCard.tsx             # 案件卡片
│   │   │   ├── EmptyState.tsx           # 空态
│   │   │   ├── HeroSection.tsx          # Hero 视觉锚点
│   │   │   ├── PillTag.tsx              # 小标签
│   │   │   └── StatusTag.tsx            # 状态标签（5 色）
│   │   ├── composables/                 # 3 个组合函数
│   │   │   ├── useDebounce.ts           # 防抖
│   │   │   ├── useFormat.ts            # 格式化工具
│   │   │   └── useStatus.ts            # 状态映射
│   │   ├── layouts/                     # 2 个布局
│   │   │   ├── AppLayout.tsx            # 应用主布局（侧栏 + 内容区）
│   │   │   └── AuthLayout.tsx           # 鉴权页布局（品牌 + glow）
│   │   ├── lib/                         # 工具与 API
│   │   │   ├── api-client.ts            # Axios 实例 + 拦截器
│   │   │   ├── api.ts                   # API 封装
│   │   │   └── utils.ts                 # cn() className 合并
│   │   ├── pages/                       # 10 个页面
│   │   │   ├── LoginPage.tsx / RegisterPage.tsx   # 鉴权
│   │   │   ├── CaseListPage.tsx                    # 案件列表 + Hero
│   │   │   ├── DashboardPage.tsx                  # 数据仪表盘（Recharts）
│   │   │   ├── WorkspacePage.tsx                  # 案件工作台（子路由壳）
│   │   │   ├── EvidencePage.tsx                   # 证据上传与列表
│   │   │   ├── TimelinePage.tsx                   # 时间线
│   │   │   ├── ComplaintPage.tsx                 # 投诉文本
│   │   │   ├── MaskPage.tsx                       # 隐私打码
│   │   │   └── ExportPage.tsx                     # 多格式导出
│   │   ├── stores/                      # 2 个 Zustand store
│   │   │   ├── auth-store.ts            # 登录态 + token 持久化
│   │   │   └── case-store.ts           # 当前案件缓存
│   │   └── types/                       # 4 个类型定义
│   │       ├── api.ts / auth.ts / case.ts / index.ts
│   ├── public/                         # 静态资源（favicon、icons）
│   ├── index.html
│   ├── vite.config.ts                  # @tailwindcss/vite + react + /api 代理
│   ├── tsconfig.json / tsconfig.app.json
│   └── package.json
├── docs/                               # 文档
│   ├── plan.md                         # 生态完善任务规划
│   ├── T0_spec.md                     # T0 阶段 spec
│   ├── T1_spec.md                     # T1 阶段 spec
│   ├── frontend-display-design.md     # 前端展示效果设计方案草案
│   └── superpowers/specs/
│       └── 2026-07-04-frontend-react-rewrite-design.md   # React 重写规范
├── Dockerfile.backend                  # Python 3.11 + Tesseract + gunicorn
├── Dockerfile.frontend                 # Node 18 build + nginx
├── docker-compose.yml                  # mysql + backend + frontend
├── nginx.conf                          # SPA + /api + /media 反代
├── .env.example                        # DB_PASSWORD + SECRET_KEY
├── .dockerignore / .gitignore
├── claimcraft-creative.html            # 项目展示页
└── README.md
```

---

## 功能设计

### 核心数据模型（7 个）

| 模型 | 说明 |
|---|---|
| `Case` | 案件主表，含 `owner`（FK→User）、`status`（FSMField）、`case_type` |
| `Evidence` | 证据（文本/图片），关联 Case |
| `ExtractedField` | 证据抽取字段（订单号、金额、手机号等），支持人工校正 |
| `TimelineNode` | 时间线节点（自动/手动），含 `source` 字段标识来源 |
| `ComplaintTemplate` / `ComplaintTemplateRule` | 投诉模板（platform / regulatory / arbitration）+ 规则 |
| `CaseStatusLog` | 状态转换日志（审计） |
| `CaseTypePreset` | 4 种纠纷类型预设（购物 / 服务 / 二手 / 其他） |

### 状态机（django-fsm）

5 条状态转换：

```
draft ──start──▶ processing
draft ──cancel──▶ cancelled
processing ──submit──▶ submitted
processing ──cancel──▶ cancelled
submitted ──close──▶ closed
```

> 关键约束：`submitted` 后不可取消（保护已提交材料的稳定性）。

### 业务流水线

```
1. 上传截图 → 2. OCR 识别 → 3. 正则抽取关键字段 → 4. 时间线自动重建
   → 5. Jinja2 渲染投诉文本 → 6. 隐私打码（文本+图片）
   → 7. 多格式导出（文本包 / ZIP / PDF）
```

### 前端页面与路由

| 路由 | 页面 | 守卫 |
|---|---|---|
| `/login` `/register` | LoginPage / RegisterPage | PublicOnly |
| `/` | 重定向 → `/cases` | AuthGuard |
| `/cases` | CaseListPage（含 Hero） | AuthGuard |
| `/dashboard` | DashboardPage（Recharts 可视化） | AuthGuard |
| `/cases/:caseId/workspace` | WorkspacePage（子路由壳） | AuthGuard |
| `/cases/:caseId/evidence` | EvidencePage | AuthGuard |
| `/cases/:caseId/timeline` | TimelinePage | AuthGuard |
| `/cases/:caseId/complaint` | ComplaintPage | AuthGuard |
| `/cases/:caseId/mask` | MaskPage | AuthGuard |
| `/cases/:caseId/export` | ExportPage | AuthGuard |

### API 概览（27 条）

#### 鉴权（5 条）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register/` | 注册 |
| POST | `/api/auth/login/` | 登录（JWT） |
| POST | `/api/auth/refresh/` | 刷新 token |
| POST | `/api/auth/verify/` | 校验 token |
| GET | `/api/auth/me/` | 当前用户 |

#### 案件管理（7 条）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/api/cases/` | 列表 / 新建 |
| GET | `/api/cases/<id>/` | 详情（含统计） |
| PATCH / DELETE | `/api/cases/<id>/manage/` | 更新 / 删除 |
| POST | `/api/cases/<id>/status/transition/` | 状态转换 |
| GET | `/api/cases/<id>/status-logs/` | 状态日志 |
| GET | `/api/cases/<id>/mask-images/` | 案件图片打码 |
| POST | `/api/cases/<id>/apply-preset/` | 应用模板预设 |

#### 证据 / 抽取字段（4 条）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/api/cases/<case_id>/evidences/` | 证据列表 / 新建 |
| POST | `/api/cases/<case_id>/evidences/upload/` | 上传图片（multipart） |
| DELETE | `/api/evidences/<id>/` | 删除证据 |
| GET / PATCH | `/api/evidences/<id>/extracted-fields/` | 抽取字段列表 / 校正 |

#### 时间线（3 条）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/api/cases/<case_id>/timeline/` | 列表 / 新建节点 |
| POST | `/api/cases/<case_id>/timeline/rebuild/` | 重建时间线 |
| PATCH | `/api/timeline-nodes/<id>/` | 更新节点 |

#### 投诉文本（2 条）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/cases/<case_id>/complaints/?template=` | 获取投诉文本 |
| POST | `/api/cases/<case_id>/complaints/regenerate/` | 重新生成 |

#### 打码与导出（4 条）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/cases/<case_id>/mask/` | 文本打码 |
| GET | `/api/cases/<case_id>/export/` | 文本包导出 |
| GET | `/api/cases/<id>/export/package/` | ZIP 包导出 |
| GET | `/api/cases/<id>/export/pdf/` | PDF 导出 |

#### 预设与统计（2 条）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/case-presets/` | 4 种案件类型预设 |
| GET | `/api/stats/` | 7 项仪表盘统计 |

---

## 部署说明

### 方式一：Docker 一键部署（推荐）

#### 前置条件

- 已安装 Docker 与 Docker Compose

#### 步骤

```bash
# 1. 复制环境变量配置
cp .env.example .env
# 按需修改 .env 中的 DB_PASSWORD 与 SECRET_KEY

# 2. 一键启动（MySQL + 后端 + 前端 nginx）
docker-compose up -d --build

# 3. 查看日志
docker-compose logs -f backend

# 4. 停止
docker-compose down
```

启动后访问 `http://localhost` 即可使用。

#### 容器架构

| 服务 | 说明 |
|---|---|
| `mysql` | MySQL 8.0，数据持久化到 `mysql_data` volume |
| `backend` | Django + gunicorn，含 Tesseract OCR（中文+英文），数据持久化到 `media_data` volume |
| `frontend` | nginx 托管 React 构建产物 + `/api` 反代到后端 + `/media` 反代到后端 |

#### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DB_PASSWORD` | claimcraft_dev_2025 | MySQL root 密码 |
| `SECRET_KEY` | claimcraft-prod-secret-change-me | Django 密钥 |
| `DJANGO_DEBUG` | False | 调试模式 |
| `DJANGO_ALLOWED_HOSTS` | * | 允许的主机 |

### 方式二：本地开发启动

详见下一节"本地测试开发启动步骤"。

---

## 本地测试开发启动步骤

### 环境要求

- Python 3.10+
- Node.js 18+
- MySQL 8.0+（已配置，亦可回退 SQLite）
- Tesseract OCR（可选，未安装时自动回退 Mock）

### 1. 后端启动

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置数据库（默认 MySQL，配置见 backend/claimcraft/settings.py）
# 如需创建 MySQL 数据库：
# mysql -u root -p -e "CREATE DATABASE claimcraft DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
# 如需切换 SQLite，注释 settings.py 中 MySQL 块、取消注释 SQLite 块

# 执行迁移
python manage.py migrate

# 导入种子数据（含示例案件、8 条证据、抽取字段、时间线、3 套投诉模板、4 种预设）
python manage.py loaddata seed_data.json

# 启动开发服务器
python manage.py runserver
```

后端运行在 `http://localhost:8000`。

### 2. 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器（Vite，端口 5173）
npm run dev
```

前端运行在 `http://localhost:5173`，`/api` 请求自动代理到 `http://localhost:8000`（见 `vite.config.ts`）。

### 3. Tesseract 安装（可选，用于真实 OCR）

未安装 Tesseract 时，系统自动回退 Mock OCR，识别预置样本文本，不影响流程。

如需真实 OCR 识别：

1. 下载安装 Tesseract：[GitHub Releases](https://github.com/UB-Mannheim/tesseract/wiki)
2. 安装时勾选 Chinese (Simplified) 语言包
3. 确认安装路径为 `D:\tesseract\tesseract.exe`（或修改 `backend/api/services/ocr_service.py` 中的 `TESSERACT_CMD`）

### 4. 默认账号

- 用户名：`admin`
- 密码：`admin123`

### 5. 验证启动

- 访问 `http://localhost:5173` → 跳转到登录页
- 使用默认账号登录 → 跳转到案件列表
- 选择示例案件 → 进入工作台 → 验证 OCR / 时间线 / 投诉文本 / 导出流程

---

## 种子数据

导入 `seed_data.json` 后包含：

- 1 个 admin 用户（`admin` / `admin123`）
- 1 个示例案件（网购退款纠纷）
- 8 条证据（E1-E8，含文本与图片证据）
- 12 条抽取字段（订单号、金额、手机号、地址、时间、承诺话术）
- 6 个时间线节点（手动）
- 3 套投诉模板规则（platform / regulatory / arbitration，Jinja2 源码）
- 4 种案件类型预设（购物 / 服务 / 二手 / 其他）

---

## 开发路线

项目采用分阶段迭代：

- **T0（已完成）**：补全创意核心能力——证据图片上传 + OCR + 信息抽取 + 时间线重建 + 动态投诉生成
- **T1（已完成）**：产品闭环——多案件管理 + 状态流转 + 图片打码 + ZIP/PDF 导出
- **T2（已完成）**：工程化——用户体系（JWT） + 案件模板预设 + 数据仪表盘 + Docker 部署
- **前端重写（已完成）**：Vue 3 → React 19 + TypeScript + Golden Time 设计系统
- **T3（规划中）**：浏览器插件入口 + 更多纠纷类型模板 + 移动端适配

详见 [docs/plan.md](docs/plan.md)、[docs/T0_spec.md](docs/T0_spec.md)、[docs/T1_spec.md](docs/T1_spec.md)、[docs/superpowers/specs/2026-07-04-frontend-react-rewrite-design.md](docs/superpowers/specs/2026-07-04-frontend-react-rewrite-design.md)。

---

## 关键技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 数据库 | MySQL（不使用 SQLite） | 字符编码与类型更适合中文场景，生产可用 |
| 鉴权 | djangorestframework-simplejwt | 标准 JWT 方案，access 2h / refresh 7d |
| User 模型 | Django 内置 User + Case.owner FK | 已有 migration，不重建自定义 User |
| 状态机 | django-fsm | 声明式状态转换，submitted 后不可取消 |
| 前端框架 | React 19 + TypeScript | 类型安全 + 生态丰富 + 性能优秀 |
| 样式方案 | Tailwind CSS v4 + Golden Time token | 设计令牌统一管理，editorial 风格 |
| 状态管理 | Zustand 5 | 轻量、无样板代码、TypeScript 友好 |
| 路由 | React Router v7 + lazy loading | 代码分割，首屏快 |
| PDF 字体 | 三级回退（simsun.ttc → STSong-Light → Helvetica） | 兼容不同环境下的中文字体可用性 |
| OCR 回退 | Tesseract 不可用时 Mock | 保证流程不中断，便于本地开发 |
| 部署 | docker-compose 三服务 | 一键启动，环境隔离 |

---

## 许可证

本项目仅用于学习与演示目的。
