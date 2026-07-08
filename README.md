# ClaimCraft 维权材料工坊

> 把"截图 + 聊天记录"一键变成可提交的投诉与证据包。

普通用户遇到网购纠纷、退款扯皮、服务违约时，往往"证据散、时间线乱、不会写投诉材料"。ClaimCraft 通过 OCR + 信息抽取 + 时间线重建 + 模板渲染，把最费时间的整理工作自动化，输出可直接复制粘贴的标准化证据包。

项目已完成 T0（核心链路）→ T1（产品闭环）→ T2（工程化）→ T3（LLM 工作流 + RAG + SSE 流式）→ v10（场景泛化 + 三阶段标准 RAG）五阶段迭代，后端基于 **LangGraph 7 节点工作流 + EventDepot 事件保留站** 实现 SSE 流式推送，前端基于 **React 19 + TypeScript + Golden Time 设计系统** 实时展示工作流中间产物与 complaint token 逐字流，提供 30 条 RESTful + SSE API，支持 Docker 一键部署。

v10 场景泛化扩展已完成：从电商单一场景泛化到 **10 类纠纷领域**（消保/电商/合同/质量/安全/隐私/服务/医疗/劳动/平台规则），法律知识库导入 **2260 条法条**（10 部法律），RAG 检索升级为 **三阶段标准流程**（BM25 粗排 + RRF 融合 + bge-reranker-v2-m3 精排），新增商家反证维权流程（case_mode=respond）。

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
| 框架 | Django 5 + Django REST Framework（ASGI 部署） |
| 应用服务器 | uvicorn（ASGI，支持 SSE 流式响应） |
| 业务数据库 | MySQL 8.0（PyMySQL 驱动，业务数据） |
| Checkpointer | PostgreSQL（psycopg3 + ConnectionPool，工作流状态 + SSE 事件保留站） |
| LLM 工作流 | LangChain 1.0 + LangGraph 1.2（7 节点 StateGraph + PostgresSaver checkpointer + PostgresStore 长期记忆） |
| SSE 流式 | EventDepot（事件保留站）+ Postgres LISTEN/NOTIFY（实时通知） |
| 状态机 | django-fsm（5 条状态转换） |
| 鉴权 | djangorestframework-simplejwt（access 2h / refresh 7d） |
| OCR | Tesseract + pytesseract（chi_sim + eng）+ PaddleOCR-VL 云端 + LLM 视觉多策略回退 |
| RAG 知识库 | pgvector + BAAI/bge-large-zh-v1.5（1024维）+ BM25 + RRF 融合 + bge-reranker-v2-m3 精排（三阶段标准 RAG） |
| 图片处理 | Pillow（缩略图、打码模糊、压缩防爆弹） |
| PDF 生成 | reportlab（字体三级回退 simsun.ttc → STSong-Light → Helvetica） |
| 模板引擎 | Jinja2（投诉文本动态渲染） |
| 部署 | uvicorn + nginx |

### 前端

| 层 | 技术 |
|---|---|
| 框架 | React 19 + TypeScript |
| 构建 | Vite 8 |
| 样式 | Tailwind CSS v4（`@tailwindcss/vite` 插件 + `@theme inline` token 映射） |
| 状态管理 | Zustand 5（auth-store / case-store，含 workflow SSE slice） |
| 路由 | React Router v7（lazy loading + Suspense + AuthGuard/PublicOnly 守卫） |
| HTTP | Axios（带 baseURL 拦截器 + JWT 自动注入） |
| SSE | 原生 EventSource 封装（指数退避重连 + last_event_id 续传） |
| 可视化 | Recharts 3（数据仪表盘） |
| 图标 | lucide-react |
| 工具库 | date-fns（时间格式化）、clsx + tailwind-merge（className 合并） |

### 部署

| 项 | 技术 |
|---|---|
| 容器化 | Docker（多阶段构建） |
| 编排 | docker-compose（mysql + postgres + backend + frontend 四服务） |
| 反代 | nginx（SPA fallback + `/api` + `/media` + SSE 长连接反代） |
| 应用服务器 | uvicorn（backend，ASGI 模式，支持 SSE 流式） |
| 定时任务 | cron（清理 SSE 事件保留站，可选升级 Celery Beat） |

---

## 代码文件树说明

```
claimcraft-creative/
├── backend/                              # Django 后端
│   ├── api/
│   │   ├── models.py                    # 7 个数据模型
│   │   ├── views.py                     # 视图类（含 SSE 工作流 3 端点，全部按 owner 过滤）
│   │   ├── serializers.py               # DRF 序列化器
│   │   ├── permissions.py               # IsOwner 鉴权
│   │   ├── urls.py                      # 30 条 API 路由（含 SSE 3 条）
│   │   ├── admin.py                     # Django Admin 注册
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   ├── 0002_evidence_*.py
│   │   │   ├── 0003_case_*.py
│   │   │   ├── 0004_case_owner.py       # T2：用户体系
│   │   │   └── 0005_casetypepreset.py   # T2：案件预设
│   │   ├── agents/                      # LangGraph 工作流 + SSE 基础设施
│   │   │   ├── graph.py                 # 7 节点 StateGraph + PostgresSaver checkpointer
│   │   │   ├── state.py                 # CaseWorkflowState TypedDict
│   │   │   ├── nodes/                   # 7 个工作流节点
│   │   │   │   ├── preclassify_node.py  # Qwen3-Omni 视觉预分类
│   │   │   │   ├── ocr_node.py          # OCR 多策略回退
│   │   │   │   ├── classify_node.py     # 证据分类
│   │   │   │   ├── extract_node.py      # LangExtract 字段抽取
│   │   │   │   ├── review_node.py       # HITL 人工校正（interrupt）
│   │   │   │   ├── evidence_chain_node.py # 证据链构造
│   │   │   │   └── complaint_node.py    # 投诉书生成（token 流式）
│   │   │   ├── sse_event_depot.py       # SSE 事件保留站（Postgres 表）
│   │   │   ├── notify_emitter.py        # Postgres LISTEN/NOTIFY 封装
│   │   │   ├── sse_event_mapper.py      # astream_events → SSE 事件过滤映射
│   │   │   └── workflow_runner.py       # 后台任务（消费 astream_events 写入 EventDepot）
│   │   ├── services/                    # 业务服务（OCR + 抽取 + 时间线 + 投诉 + RAG + 法律工具）
│   │   │   ├── ocr_service.py           # OCR 识别（Tesseract + Mock 回退）
│   │   │   ├── extraction_service.py    # 正则信息抽取
│   │   │   ├── timeline_service.py      # 时间线重建
│   │   │   ├── complaint_service.py     # Jinja2 投诉文本生成
│   │   │   ├── evidence_service.py      # 证据管理
│   │   │   ├── mask_service.py          # 文本打码
│   │   │   ├── image_mask_service.py    # 图片打码（pytesseract 定位 + 高斯模糊）
│   │   │   ├── export_service.py        # ZIP 包导出
│   │   │   ├── pdf_service.py           # PDF 生成（字体三级回退）
│   │   │   ├── rag_service.py          # v10 三阶段 RAG 检索（BM25+RRF+Rerank）
│   │   │   ├── bm25_service.py         # v10 BM25 索引（rank_bm25 + jieba，按 category 独立）
│   │   │   ├── embedding_service.py     # v10 Embedding 服务（bge-large-zh-v1.5，1024 维）
│   │   │   ├── rerank_service.py        # v10 Rerank 精排（bge-reranker-v2-m3 Cross-encoder）
│   │   │   ├── keyword_extraction_service.py  # v10 LLM 关键词提取（Qwen3-8B）
│   │   │   └── law_tools.py             # v10 7 个法律工具（lookup_law/calculate_compensation 等）
│   │   └── management/commands/
│   │       ├── cleanup_sse_events.py    # SSE 事件保留站定时清理
│   │       ├── import_law_articles.py  # v10 法律条文导入 + embedding 生成
│   │       └── regenerate_keywords.py  # v10 LLM 并发提取法条 keywords
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
│   │   ├── components/                  # 公共组件 + workflow 工作流面板
│   │   │   ├── CaseCard.tsx             # 案件卡片
│   │   │   ├── EmptyState.tsx           # 空态
│   │   │   ├── HeroSection.tsx          # Hero 视觉锚点
│   │   │   ├── PillTag.tsx              # 小标签
│   │   │   ├── StatusTag.tsx            # 状态标签（5 色）
│   │   │   └── workflow/                # SSE 工作流实时面板（9 个组件）
│   │   │       ├── WorkflowStreamPanel.tsx  # 顶层容器
│   │   │       ├── NodeTrack.tsx        # 左侧步进轨道（7 节点）
│   │   │       ├── ProductStream.tsx    # 主区产物流
│   │   │       ├── ProductBlock.tsx     # 通用产物区块（可折叠）
│   │   │       ├── ComplaintStreamBlock.tsx # 投诉书 token 流式
│   │   │       ├── ReviewInterruptPanel.tsx # HITL 校正 UI
│   │   │       └── NodeStatusIcon.tsx   # 节点状态图标
│   │   ├── composables/                 # 3 个组合函数
│   │   │   ├── useDebounce.ts           # 防抖
│   │   │   ├── useFormat.ts            # 格式化工具
│   │   │   └── useStatus.ts            # 状态映射
│   │   ├── layouts/                     # 2 个布局
│   │   │   ├── AppLayout.tsx            # 应用主布局（侧栏 + 内容区）
│   │   │   └── AuthLayout.tsx           # 鉴权页布局（品牌 + glow）
│   │   ├── lib/                         # 工具与 API
│   │   │   ├── api-client.ts            # Axios 实例 + 拦截器
│   │   │   ├── api.ts                   # API 封装（含 workflowApi SSE 模块）
│   │   │   ├── sse-client.ts            # EventSource 封装（重连 + 续传）
│   │   │   ├── workflow-events.ts       # SSE 事件类型定义 + 辅助函数
│   │   │   └── utils.ts                 # cn() className 合并
│   │   ├── pages/                       # 10 个页面
│   │   │   ├── LoginPage.tsx / RegisterPage.tsx   # 鉴权
│   │   │   ├── CaseListPage.tsx                    # 案件列表 + Hero
│   │   │   ├── DashboardPage.tsx                  # 数据仪表盘（Recharts）
│   │   │   ├── WorkspacePage.tsx                  # 案件工作台（子路由壳）
│   │   │   ├── EvidencePage.tsx                   # 证据上传与列表（集成 SSE 工作流面板）
│   │   │   ├── TimelinePage.tsx                   # 时间线
│   │   │   ├── ComplaintPage.tsx                 # 投诉文本
│   │   │   ├── MaskPage.tsx                       # 隐私打码
│   │   │   └── ExportPage.tsx                     # 多格式导出
│   │   ├── stores/                      # 2 个 Zustand store
│   │   │   ├── auth-store.ts            # 登录态 + token 持久化
│   │   │   └── case-store.ts           # 当前案件缓存 + workflow SSE slice
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
│       ├── 2026-07-04-frontend-react-rewrite-design.md   # React 重写规范
│       └── 2026-07-07-sse-workflow-design.md             # SSE 工作流流式改造规范
├── Dockerfile.backend                  # Python 3.11 + Tesseract + uvicorn
├── Dockerfile.frontend                 # Node 18 build + nginx
├── docker-compose.yml                  # mysql + postgres + backend + frontend
├── nginx.conf                          # SPA + /api + /media + SSE 反代
├── .env.example                        # DB_PASSWORD + SECRET_KEY + LLM 配置
├── .dockerignore / .gitignore
├── langgraph.json                      # LangGraph dev 配置（graphs + dependencies + env）
├── pyproject.toml                      # langgraph dev 依赖声明（轻量，不含 Django）
├── dev_graph.py                        # langgraph dev 入口（mock 节点，复刻工作流拓扑）
├── claimcraft-creative.html            # 项目展示页
└── README.md
```

---

## 功能设计

### 核心数据模型（9 个）

| 模型 | 说明 |
|---|---|
| `Case` | 案件主表，含 `owner`（FK→User）、`status`（FSMField）、`case_type`、`case_mode`（complain/respond，v10 新增） |
| `Evidence` | 证据（文本/图片），关联 Case |
| `ExtractedField` | 证据抽取字段（订单号、金额、手机号等），支持人工校正 |
| `TimelineNode` | 时间线节点（自动/手动），含 `source` 字段标识来源 |
| `ComplaintTemplate` / `ComplaintTemplateRule` | 投诉模板（platform / regulatory / arbitration）+ 规则 |
| `CaseStatusLog` | 状态转换日志（审计） |
| `CaseTypePreset` | 4 种纠纷类型预设（购物 / 服务 / 二手 / 其他） |
| `LawArticle` | 法律条文（v10 新增，2260 条，10 部法律，含 keywords/applicable_scenarios，支持 9 类分类） |
| `PlatformRule` | 平台规则（v10 新增，6 个电商平台规则，含 rule_type=platform/regulatory/industry） |
| `RespondTemplate` | 商家反证模板（v10 新增，配合 case_mode=respond 流程） |

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
| `/cases/:caseId/respond` | RespondPage（v10 商家反证） | AuthGuard |
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

#### 工作流（5 条，含 SSE 3 条）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/cases/<id>/run-workflow/` | 同步运行工作流（已废弃，保留兼容） |
| GET | `/api/cases/<id>/workflow/history/` | 工作流状态历史（调试审计） |
| POST | `/api/cases/<id>/workflow/start/` | **SSE** 启动工作流后台任务，返回 thread_id + stream_url |
| GET | `/api/cases/<id>/workflow/stream/?thread_id=X&last_event_id=N` | **SSE** 流式端点，推送节点事件 + token 流 |
| POST | `/api/cases/<id>/workflow/resume/` | **SSE** HITL 校正提交，恢复工作流 |

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
- MySQL 8.0+（业务数据库）
- PostgreSQL 14+（工作流 checkpointer + SSE 事件保留站，需启用 pgvector 扩展用于 RAG）
- Tesseract OCR（可选，未安装时自动回退 Mock）

### 1. 后端启动

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置数据库（默认 MySQL，配置见 backend/claimcraft/settings.py）
# 如需创建 MySQL 数据库：
# mysql -u root -p -e "CREATE DATABASE claimcraft DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 创建 PostgreSQL 数据库（工作流 checkpointer + SSE 事件保留站）
# psql -U postgres -c "CREATE DATABASE claimcraft_checkpoints;"
# psql -U postgres -d claimcraft_checkpoints -c "CREATE EXTENSION IF NOT EXISTS vector;"  # RAG 向量检索

# 配置环境变量（复制 .env.example 为 .env，按需修改）
# 关键变量：
#   DB_PASSWORD=...                     # MySQL 密码
#   CHECKPOINTER_DB_URL=postgresql://... # PostgreSQL 连接串
#   LLM_API_KEY=...                     # 文本 LLM (Qwen) API Key
#   LLM_OCR_API_KEY=...                 # OCR 视觉 LLM API Key
#   EMBEDDING_API_KEY=...               # RAG 向量嵌入 API Key

# 执行迁移
python manage.py migrate

# 导入种子数据（含示例案件、8 条证据、抽取字段、时间线、3 套投诉模板、4 种预设）
python manage.py loaddata seed_data.json

# （可选）导入法律条文 RAG 知识库（2260 条法条，10 部法律，含 embedding 向量生成）
# 首次导入：python manage.py import_law_articles --file=<JSON路径> --no-embed
# 仅重新生成 embedding（保护 LLM keywords）：python manage.py import_law_articles --embed-only
python manage.py import_law_articles

# 启动开发服务器（二选一）

# 方式 A：Django runserver（仅非 SSE 场景，WSGI 模式）
python manage.py runserver

# 方式 B：uvicorn ASGI（推荐，支持 SSE 流式响应）
uvicorn claimcraft.asgi:application --host 0.0.0.0 --port 8000 --reload
```

后端运行在 `http://localhost:8000`。

> **重要**：SSE 工作流端点（`/api/cases/<id>/workflow/stream/`）必须使用 ASGI 模式（方式 B）才能正常推送流式响应。`runserver`（方式 A）不支持长连接流式推送。

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

### 6. LangGraph Dev 开发测试（可选）

用于本地快速调试 LangGraph 工作流拓扑，无需 Docker / Django / MySQL / PostgreSQL 环境，参考 [LangSmith Local Dev Testing](https://docs.langchain.com/langsmith/local-dev-testing)。

```bash
# 前置：已安装 langgraph-cli[inmem]
pip install 'langgraph-cli[inmem]'

# 启动 dev server（in-memory checkpointer，热重载）
langgraph dev --port 2024 --no-browser
```

启动后访问：

- **API**：`http://127.0.0.1:2024`
- **Swagger 文档**：`http://127.0.0.1:2024/docs`
- **Studio UI**：`https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`

设计说明：

- 入口文件 [dev_graph.py](dev_graph.py) 复刻真实业务工作流拓扑 `START → ocr → classify → extract → [review?] → evidence_chain → complaint → END`，节点用 mock 实现，独立于 [backend/api/agents/graph.py](backend/api/agents/graph.py)（后者受 Django 环境托管，依赖 Case/Evidence ORM）。
- 配置文件 [langgraph.json](langgraph.json) 声明 `graphs.claimcraft_dev = "./dev_graph.py:graph"`，依赖 [pyproject.toml](pyproject.toml)（仅含 langgraph 核心，不含 Django）。
- 启动验证：threadless run 跑通 6 节点（ocr → classify → extract → evidence_chain → complaint），`errors` 为空。

---

## SSE 工作流流式推送

本项目核心算法基于 LangGraph 7 节点工作流（`preclassify → ocr → classify → extract → [review?] → evidence_chain → complaint`），采用 **EventDepot 事件保留站模式** 实现 SSE 流式推送，让前端实时看到每个节点的中间产物与 complaint 节点的 token 逐字流。

### 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│  生产者（后台任务 WorkflowRunner）                                │
│  workflow.astream_events(v2) → SSEEventMapper 过滤映射           │
│    → EventDepot.persist(thread_id, event)  ← 每次输出立即写入    │
│    → NotifyEmitter.notify(thread_id)       ← Postgres NOTIFY     │
└──────────────────────────────────────────────────────────────────┘
                              │ 持久化
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  EventDepot（Postgres 表 sse_event_depot）                       │
│  thread_id | event_id | event_type | payload | created_at        │
│  保留期 24h，支持断连续传 + 多客户端订阅                          │
└──────────────────────────────────────────────────────────────────┘
                              ▲ 读取
                              │
┌──────────────────────────────────────────────────────────────────┐
│  消费者（CaseWorkflowStreamView，SSE 端点）                       │
│  1. 回放 last_event_id 之后的事件（断连续传）                     │
│  2. LISTEN 订阅新事件通知                                         │
│  3. 收到 NOTIFY → 拉取新事件 → SSE 推送                           │
│  4. 每 15s 心跳保活                                               │
└──────────────────────────────────────────────────────────────────┘
```

### 事件类型

| 类别 | 事件类型 | 说明 |
|---|---|---|
| 生命周期 | `workflow.start` / `workflow.complete` / `workflow.error` / `workflow.resumed` | 工作流级 |
| 节点级 | `node.start` / `node.progress` / `node.complete` / `node.error` | 7 节点通用，含产物 |
| Token 流 | `complaint.token` / `complaint.done` | 仅 complaint 节点，逐字推送 |
| HITL | `review.interrupt` / `review.resumed` / `review.skipped` | 人工校正协调 |

### 前端展示

EvidencePage 集成 `WorkflowStreamPanel`，采用方案 C 布局：
- **左侧 NodeTrack**（120px 暗色步进轨道）：7 节点垂直列表，状态点（绿/蓝脉动/红/灰）
- **主区 ProductStream**：按完成顺序插入产物区块，自动折叠历史，complaint 区块内联 token 流式 + 光标闪烁
- **HITL 校正面板**：低置信度字段触发琥珀色校正面板，提交后继续推送后续节点

### 设计文档

详见 [docs/superpowers/specs/2026-07-07-sse-workflow-design.md](docs/superpowers/specs/2026-07-07-sse-workflow-design.md)。

---

## Nginx SSE 反代配置

SSE 长连接需要特殊 Nginx 配置，禁用缓冲、延长超时、启用 HTTP/1.1。在 `nginx.conf` 的 `server` 块中添加：

```nginx
server {
    listen 80;
    server_name localhost;
    client_max_body_size 50M;

    # 前端 SPA
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # API 反代（普通 REST 请求）
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 媒体文件
    location /media/ {
        proxy_pass http://backend:8000;
    }

    # ===== SSE 工作流流式端点（关键配置） =====
    location ~ ^/api/cases/[0-9]+/workflow/stream/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 关键：禁用所有缓冲
        proxy_buffering off;
        proxy_cache off;
        proxy_request_buffering off;

        # 启用 HTTP/1.1（默认 HTTP/1.0 不支持长连接）
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # 延长超时（HITL 可能暂停数分钟，complaint 生成可能 60s+）
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;

        # 禁用 gzip（SSE 流式不能压缩，会导致事件边界丢失）
        gzip off;
    }
}
```

### 关键配置说明

| 指令 | 值 | 原因 |
|---|---|---|
| `proxy_buffering` | off | Nginx 默认缓冲响应再批量发送，会破坏 SSE 实时性 |
| `proxy_http_version` | 1.1 | HTTP/1.0 不支持长连接，SSE 需要持久连接 |
| `Connection` | "" | 清除 hop-by-hop header，避免连接被提前关闭 |
| `proxy_read_timeout` | 600s | HITL 校正可能暂停数分钟，complaint 生成需 60s+ |
| `gzip` | off | 压缩会破坏 SSE 事件边界（`\n\n` 分隔符） |

### 启动与验证

```bash
# 1. 启动后端（ASGI 模式，必须）
cd backend
uvicorn claimcraft.asgi:application --host 0.0.0.0 --port 8000

# 2. 启动 Nginx（使用上述配置）
nginx -c /path/to/nginx.conf

# 3. 验证 SSE 端点（curl 手动测试）
# 启动一个工作流
curl -X POST http://localhost/api/cases/1/workflow/start/ \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"evidence_ids": []}'
# 返回 {"thread_id": "case-1-...", "stream_url": "/api/cases/1/workflow/?thread_id=..."}

# 订阅 SSE 流
curl -N -H "Authorization: Bearer <JWT>" \
  "http://localhost/api/cases/1/workflow/stream/?thread_id=case-1-...&last_event_id=0"
# 应看到 event: workflow.start / node.start / node.complete 等事件逐条推送
```

### Docker 部署的 Nginx 配置

Docker 部署时 Nginx 配置已内置在 `Dockerfile.frontend` 中，`docker-compose.yml` 启动时会自动加载 `nginx.conf`。SSE 路径匹配规则已包含在内，无需额外操作。

---

## 定时任务：SSE 事件保留站清理

SSE 事件保留站（`sse_event_depot` 表）会持续累积事件，需定时清理 24h 前的历史数据。提供两种方案：

### 方案一：cron 定时任务（默认，轻量）

**适用场景**：单机部署、无额外依赖、清理任务简单。

```bash
# 编辑 crontab
crontab -e

# 添加每小时清理一次（保留 24h）
0 * * * * cd /app/backend && python manage.py cleanup_sse_events --hours=24 >> /var/log/cleanup_sse.log 2>&1
```

Docker 部署可在 `docker-compose.yml` 的 backend 服务中添加：

```yaml
services:
  backend:
    # ... 其他配置
    environment:
      - SSE_EVENT_DEPOT_TTL_HOURS=24
```

并通过宿主机 cron 或 Docker 的 `ofelia` 等定时任务工具触发。

### 方案二：Celery Beat（可选，重型）

**适用场景**：多机部署、需要分布式任务队列、已有 Celery 基础设施。

本项目当前**不引入 Celery 依赖**（保留升级路径），但提供迁移方案：

#### 1. 添加依赖

```bash
# requirements.txt 添加
celery>=5.3
django-celery-beat>=2.5
redis>=5.0  # 作为 broker
```

#### 2. 配置 Celery

```python
# backend/claimcraft/celery.py（新增）
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')
app = Celery('claimcraft')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

```python
# backend/claimcraft/settings.py 添加
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
```

#### 3. 定义任务

```python
# backend/api/tasks.py（新增）
from celery import shared_task
from api.agents.sse_event_depot import EventDepot

@shared_task
def cleanup_sse_events_task(hours: int = 24):
    """清理 SSE 事件保留站过期数据"""
    depot = EventDepot()
    deleted = depot.cleanup_old_events(hours)
    return f"Cleaned up {deleted} SSE events older than {hours}h"
```

#### 4. 注册定时任务

```python
# backend/api/apps.py
from django.apps import AppConfig

class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        from django_celery_beat.models import PeriodicTask, IntervalSchedule
        import json
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=1, period=IntervalSchedule.HOURS,
        )
        PeriodicTask.objects.get_or_create(
            interval=schedule,
            name='cleanup-sse-events',
            task='api.tasks.cleanup_sse_events_task',
            kwargs=json.dumps({'hours': 24}),
        )
```

#### 5. 启动 Celery worker + beat

```bash
# 启动 worker
celery -A claimcraft worker --loglevel=info

# 启动 beat 调度器
celery -A claimcraft beat --loglevel=info
```

### 方案对比

| 维度 | cron | Celery Beat |
|---|---|---|
| 依赖 | 无 | Redis/RabbitMQ + celery + django-celery-beat |
| 部署复杂度 | 低（crontab 一行） | 中（需启动 worker + beat 两个进程） |
| 多机部署 | 不支持（每台机器独立 cron） | 支持（集中调度） |
| 任务监控 | 日志文件 | Flower 监控面板 |
| 失败重试 | 无 | 自动重试 |
| 适用规模 | 单机、中小流量 | 多机、高可用 |

**建议**：当前项目采用 cron 方案即可。若未来扩展到多机部署或需要更复杂的定时任务（如定期生成报告、数据归档），再升级到 Celery Beat。

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

## v10 场景泛化与三阶段标准 RAG

### 场景泛化扩展

v10 将项目从电商单一场景泛化到 **10 类纠纷领域**：

| 分类 | 法律 | 场景示例 |
|------|------|---------|
| consumer_protection | 消费者权益保护法 | 欺诈退一赔三、知情权 |
| e-commerce | 电子商务法、网络交易监督管理办法 | 延迟发货、平台责任 |
| contract | 民法典（合同编） | 家装违约、服务合同 |
| quality | 产品质量法 | 商品质量缺陷 |
| safety | 食品安全法、药品管理法 | 食安十倍赔偿、假药 |
| service | 家政服务管理办法 | 家政违约、服务纠纷 |
| medical | 医疗事故处理条例、医疗纠纷预防和处理条例 | 医疗事故赔偿 |
| labor | 劳动法、劳动合同法、劳动争议调解仲裁法 | 拖欠工资、违法解除 |
| platform_rule | 各电商平台规则 | 平台规则查询 |
| privacy | 个人信息保护法 | 隐私泄露 |

同时新增 **商家反证维权流程**（`case_mode=respond`），支持商家对投诉进行反驳举证。

### 三阶段标准 RAG 流程

法律/医疗等高严谨领域采用**三阶段标准 RAG** 最佳实践：

```
用户查询 Query
       │
       ├──────────────┐
       ↓              ↓
  [Embedding]    [BM25 检索]
  bge-large-zh  jieba 分词
  生成 query 向量 精确匹配法律术语
       │              │
       ↓              ↓
  [向量检索]      top 50（粗排候选）
  PG pgvector
  余弦相似度
       │              │
       └──────┬───────┘
              ↓
       [RRF 融合]
       score = Σ 1/(60+rank)
       去重合并 50 条
              │
              ↓
    ════════════════════
    ║  [Rerank 精排]   ║
    ║  bge-reranker    ║
    ║  -v2-m3          ║
    ║  Cross-encoder   ║
    ════════════════════
              │
              ↓
       精排 top 10
              │
              ↓
      [LLM 生成]
      Prompt + Context
      → 答案 + 引用
```

| 阶段 | 算法/模型 | 作用 |
|------|---------|------|
| 粗排 | BM25（jieba + rank_bm25）+ bge-large-zh-v1.5 向量检索 | 双路召回 50 条候选 |
| 融合 | RRF（Reciprocal Rank Fusion, k=60） | 不依赖 score 量纲，仅用 rank 位置融合 |
| 精排 | bge-reranker-v2-m3（Cross-encoder） | 对每个 (query, doc) 对计算相关性，精度比 bi-encoder 高 10-20% |
| 生成 | Qwen LLM | top-10 法条作为 context 生成投诉/证据链 |

**关键设计**：
- BM25 按 category 维护独立索引（避免跨 category 污染）
- Rerank 失败时优雅降级为 RRF 顺序截断（不影响检索功能）
- 法条 keywords 由 LLM（Qwen3-8B）基于 content 独立提取（99.7% 独立化）
- 向量索引仅用 content，law_name/article_number 等作为元数据存 MySQL

**验证结果**：8/8 场景全部通过（消保法55条/食安法148条/电商法49条/民法典577条/家政办法35条/医疗事故条例49条/劳动合同法30条/48条），平均 1.87s/场景。

---

## 开发路线

项目采用分阶段迭代：

- **T0（已完成）**：补全创意核心能力——证据图片上传 + OCR + 信息抽取 + 时间线重建 + 动态投诉生成
- **T1（已完成）**：产品闭环——多案件管理 + 状态流转 + 图片打码 + ZIP/PDF 导出
- **T2（已完成）**：工程化——用户体系（JWT） + 案件模板预设 + 数据仪表盘 + Docker 部署
- **前端重写（已完成）**：Vue 3 → React 19 + TypeScript + Golden Time 设计系统
- **T3（已完成）**：LLM 工作流 + RAG 知识库 + SSE 流式推送
- **v10（已完成）**：场景泛化（10 类纠纷领域）+ 三阶段标准 RAG（BM25+RRF+Rerank）+ 商家反证流程 + 2260 条法条知识库
- **后续规划**：浏览器插件入口 + 移动端适配 + 更多纠纷类型模板

详见 [docs/plan.md](docs/plan.md)、[docs/T0_spec.md](docs/T0_spec.md)、[docs/T1_spec.md](docs/T1_spec.md)、[docs/superpowers/specs/2026-07-04-frontend-react-rewrite-design.md](docs/superpowers/specs/2026-07-04-frontend-react-rewrite-design.md)。

---

## 关键技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 数据库 | MySQL（业务数据）+ PostgreSQL（工作流状态 + SSE 事件） | MySQL 适合业务 CRUD；PostgreSQL 适合 LangGraph checkpointer + pgvector RAG + LISTEN/NOTIFY |
| 鉴权 | djangorestframework-simplejwt | 标准 JWT 方案，access 2h / refresh 7d |
| User 模型 | Django 内置 User + Case.owner FK | 已有 migration，不重建自定义 User |
| 状态机 | django-fsm | 声明式状态转换，submitted 后不可取消 |
| 前端框架 | React 19 + TypeScript | 类型安全 + 生态丰富 + 性能优秀 |
| 样式方案 | Tailwind CSS v4 + Golden Time token | 设计令牌统一管理，editorial 风格 |
| 状态管理 | Zustand 5 | 轻量、无样板代码、TypeScript 友好 |
| 路由 | React Router v7 + lazy loading | 代码分割，首屏快 |
| PDF 字体 | 三级回退（simsun.ttc → STSong-Light → Helvetica） | 兼容不同环境下的中文字体可用性 |
| OCR 回退 | Tesseract 不可用时 Mock | 保证流程不中断，便于本地开发 |
| 工作流引擎 | LangGraph 1.2 StateGraph | 节点级 timeout + Saga 降级 + HITL interrupt |
| SSE 架构 | EventDepot 事件保留站 + LISTEN/NOTIFY | 解耦生产者消费者，支持断连续传 + 多客户端订阅 |
| SSE 通知机制 | Postgres LISTEN/NOTIFY | 复用现有 Postgres，无需引入 Redis Pub/Sub |
| 后台任务 | asyncio.create_task + 全局注册表 | 轻量，单进程 ASGI 部署足够；保留 Celery 升级路径 |
| 定时清理 | cron（保留 Celery Beat 升级路径） | 无额外依赖，单机部署足够 |
| 部署 | docker-compose 四服务 | 一键启动，环境隔离 |
| 应用服务器 | uvicorn（ASGI） | 支持 SSE 流式响应长连接，替代 gunicorn WSGI |
| LangGraph 开发测试 | 轻量级独立 graph 入口（`dev_graph.py`） | 隔离 Django/MySQL/PG 环境，最快验证 langgraph dev 工作流；真实业务 graph 仍在 `backend/api/agents/graph.py` 受 Django 托管 |
| RAG 检索（v10） | 三阶段标准 RAG：BM25 + RRF + Rerank | 法律/医疗高严谨领域最佳实践，检索准确率 0% → 100% |
| Embedding 模型（v10） | BAAI/bge-large-zh-v1.5（1024维） | 专为中文优化，比 bge-m3 在法律术语跨域匹配上更优 |
| Rerank 模型（v10） | BAAI/bge-reranker-v2-m3（Cross-encoder） | 精度比 bi-encoder 高 10-20%，适合法律/医疗高严谨领域 |
| BM25 索引设计（v10） | 按 category 维护独立索引 | 避免跨 category 污染，category 内归一化 score |
| 法条 keywords（v10） | LLM（Qwen3-8B）独立提取 | 替代整部法律共用 keywords，99.7% 独立化 |

---

## 许可证

本项目仅用于学习与演示目的。
