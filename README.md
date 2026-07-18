# ClaimCraft 维权材料工坊

ClaimCraft 是一个面向消费维权与商家反证场景的案件材料整理应用。用户可以创建案件、上传证据图片，系统通过视觉理解、OCR、结构化抽取、人工校正、证据链构建和法律检索生成投诉书或反证答辩书，并提供时间线、隐私打码和多格式导出能力。

本文档严格描述当前仓库中的实际实现。规划中的统一运行模型、质量门等后续设计见 [`docs/workflow-fullstack-upgrade-design.md`](docs/workflow-fullstack-upgrade-design.md)，不作为已实现功能说明。

---

## 1. 已实现功能

### 账户与案件

- 用户名密码登录、邮箱验证码登录和注册、密码重置与修改；
- JWT access/refresh token，refresh 轮换、黑名单和多设备会话撤销；
- 用户资料、头像、邮箱验证、偏好和账户审计；
- 案件创建、查看、更新、删除、归档、取消和状态流转；
- 四类案件：网购纠纷、服务违约、二手交易、其他；
- 两种案件模式：`complain` 维权投诉、`respond` 商家反证；
- 案件预设、状态日志和统计仪表盘。

### 证据与产物

- 图片拖拽、选择、批量上传和 Lightbox 预览；
- 每张图片可独立标记为纯物证并填写物证说明；
- 视觉预分类、摘要、多策略 OCR、证据分类和字段抽取；
- 低置信度字段人工校正，字段分类展示与行内编辑；
- 自动重建和人工编辑事实时间线；
- 法条检索、证据链构建、投诉书和商家反证答辩书；
- 文本脱敏、图片模糊打码、文本包/ZIP/PDF 导出。

### 实时工作流

- LangGraph 异步状态图与 PostgreSQL Checkpointer；
- 低置信度 HITL `interrupt` / `Command(resume=...)`；
- 每个业务节点完成后的安全暂停、编辑和恢复；
- EventDepot 持久化事件与 PostgreSQL `LISTEN/NOTIFY`；
- SSE 断线续传、页面刷新回放、文书增量输出；
- 节点级超时、错误累积与分层降级。

---

## 2. 技术栈

### 后端

| 模块 | 当前实现 |
|---|---|
| Web/API | Django 4.2+、Django REST Framework、Uvicorn ASGI |
| 业务数据库 | MySQL，PyMySQL 驱动；执行测试时默认切换 SQLite |
| 工作流 | LangChain 1.x、LangGraph 1.2.x |
| 工作流存储 | PostgreSQL、PostgresSaver、PostgresStore、psycopg3 pool |
| 实时推送 | SSE、EventDepot、PostgreSQL LISTEN/NOTIFY |
| 鉴权 | DRF SimpleJWT；access 2 小时、refresh 7 天 |
| 状态机 | django-fsm |
| LLM | langchain-openai，OpenAI 兼容协议 |
| 字段抽取 | LangExtract、structured output、正则兜底 |
| OCR | PaddleOCR-VL、视觉 LLM、本地 PaddleOCR、Mock；传统服务支持 Tesseract |
| RAG | MySQL 法条、PostgreSQL pgvector、BM25、RRF、可选 Rerank |
| 文件处理 | Pillow、pytesseract、ReportLab、Jinja2 |
| 可观测性 | 可选 LangSmith tracing |
| 邮件 | Agent Mail CLI 优先、SMTP 兜底 |

### 前端

| 模块 | 当前实现 |
|---|---|
| 框架 | React 19、TypeScript 6、Vite 8 |
| 样式 | Tailwind CSS 4、CSS 变量设计令牌 |
| 状态 | Zustand 5：`auth-store`、`case-store` |
| 路由 | React Router 7、懒加载、AuthGuard/PublicOnly |
| HTTP | Axios、JWT 注入、refresh 防并发、401 自动重试 |
| 实时 | 原生 EventSource 封装 |
| UI | Recharts 3、Framer Motion 11、Lucide React |
| 工具 | date-fns、clsx、tailwind-merge |

### 部署

- 后端镜像：Python 3.11，并注入 Node.js 22 运行 Agent Mail CLI；
- 前端：Node.js 22 构建，Nginx Alpine 运行；
- Compose：MySQL、PostgreSQL/pgvector、后端、前端四个服务；
- Nginx：SPA fallback，并反代 `/api/`、`/media/`、`/static/`；
- SSE 路径关闭缓冲与 gzip，读写超时为 600 秒。

---

## 3. 系统架构

```text
React SPA
  ├─ Axios REST API
  └─ EventSource SSE
          │
          ▼
Django REST Framework / ASGI
  ├─ 账户、案件、证据、时间线、文书、打码、导出
  ├─ WorkflowRunner：后台执行 LangGraph
  └─ CaseWorkflowStreamView：SSE 消费者
          │
          ├───────────────┐
          ▼               ▼
       MySQL          PostgreSQL + pgvector
  业务模型与产物       Checkpoint / Store
                      SSE EventDepot
                      LISTEN/NOTIFY
                      法条向量
```

### 双数据库职责

**MySQL** 保存业务事实和最终产物：用户资料、偏好、会话、案件、证据、抽取字段、时间线、文书、法条、平台规则和状态日志。

**PostgreSQL** 保存 LangGraph checkpoint、LangGraph Store、`sse_event_depot` 和 `law_article_vectors`。这些表不由 Django migration 管理，`graph.py` 和相关服务按需初始化；初始化使用 advisory lock 防止多 worker 并发 setup。

---

## 4. 核心数据模型

`backend/api/models.py` 当前定义 16 个 Django 模型：

| 模型 | 用途 |
|---|---|
| `Case` | 案件、模式、FSM 状态和工作流状态 |
| `UserProfile` | 展示名、头像、地区、时区、邮箱验证 |
| `EmailVerificationChallenge` | 注册、登录、改密、换邮箱验证码 |
| `UserPreference` | 通知、卡片和默认模板偏好 |
| `UserSession` | 多设备 refresh token 会话 |
| `AccountAuditLog` | 账户操作审计 |
| `Evidence` | 图片/文本、OCR、分类、摘要、物证标记 |
| `ExtractedField` | 字段、置信度、分类和源文本哈希 |
| `TimelineNode` | 事实时间线及关联证据 |
| `ComplaintTemplate` | 案件投诉文书 |
| `ComplaintTemplateRule` | Jinja2 投诉规则 |
| `RespondTemplate` | 商家反证答辩书 |
| `CaseStatusLog` | 案件状态转换记录 |
| `CaseTypePreset` | 案件预设 |
| `LawArticle` | 法条、摘要、关键词、适用场景 |
| `PlatformRule` | 平台、监管和行业规则 |

### 两类状态

案件业务状态由 `django-fsm` 约束：

```text
draft ──→ processing ──→ submitted ──→ closed
  └─────→ cancelled
processing ─────────────→ cancelled
```

工作流状态单独记录：

```text
idle | running | pausing | paused | waiting_review | succeeded | failed
```

业务状态表示案件生命周期，工作流状态表示当前 AI 任务状态，两者不可混用。

---

## 5. LangGraph 工作流

### 5.1 图拓扑

当前图包含 8 个业务节点，每个业务节点后均有独立命名的安全阶段门：

```text
START
  → preclassify → gate
  → ocr → gate
  → classify → gate
  → extract → gate
      ├─ 低置信度 → review → gate ─┐
      └─ 无需审核 ─────────────────┤
                                   ▼
                           evidence_chain → gate
                              ├─ complain → complaint → gate → END
                              └─ respond  → respond_complaint → gate → END
```

节点超时：预分类 60 秒、OCR 180 秒、分类 60 秒、抽取 300 秒、审核 30 秒、证据链/投诉/答辩各 120 秒。

节点错误由统一包装器写入 `state.errors`。该机制是节点级继续执行和降级，不是分布式事务补偿回滚。

### 5.2 状态聚合

`CaseWorkflowState` 使用 `TypedDict`。预分类、OCR、分类、抽取和错误列表通过 `Annotated[list, operator.add]` 聚合；证据链、工具日志和文书整体更新。人工审核完成后使用 LangGraph `Overwrite` 替换抽取结果，避免 `add` reducer 重复追加。

### 5.3 视觉预分类

`preclassify_node`：

1. `evidence_ids` 非空时处理指定证据，空列表处理案件内全部图片证据；
2. 安全读取和压缩图片，限制 Pillow 解压炸弹风险；
3. 通过 `asyncio.gather` 并发调用 Captioner；
4. 一次返回类别、视觉摘要和置信度；
5. 类别必须位于白名单，越界值回退 `other`；
6. 置信度裁剪到 `[0, 1]`；
7. 结果写入 `Evidence.evidence_category` 和 `ocr_summary`；
8. Captioner 不可用或单图失败时回退为 `other`、空摘要、`0.0`。

类别白名单：

```text
chat_screenshot, product_order, logistics_tracking, payment_record,
invoice, service_contract, work_record, communication_record,
contract_document, medical_record, other
```

物证图片会把用户填写的 `physical_note` 注入视觉提示词，仍保留视觉摘要能力。

### 5.4 多策略 OCR

`ocr_node` 对非物证图片并发执行 OCR。示例默认顺序由 `OCR_STRATEGIES` 指定：

```text
paddleocr_vl → llm_vision → paddleocr → mock
```

- PaddleOCR-VL：云端高精度文档识别；
- LLM Vision：按预分类类别选择 prompt，并由同一模型纠错；
- 本地 PaddleOCR：本地识别；
- Mock：开发和全策略失败时兜底；
- 每条证据独立记录实际策略；
- 文本写入 `Evidence.extracted_text`；单条失败不阻断其他证据。

纯物证不执行 OCR，返回 `ocr_strategy_used = "skipped_physical"` 和空文本，但继续进入下游，使视觉摘要可用于证据链。

Docker 后端也安装了 Tesseract 中文语言包，传统同步服务支持 Tesseract；LangGraph 默认 OCR 策略链不包含它。

### 5.5 两阶段证据分类

`classify_node`：

1. 预分类置信度 `>= 0.8` 时直接采纳；
2. `< 0.8` 时使用摘要或截断 OCR 文本，通过 structured output 并发细化；
3. 文本 LLM 不可用或单条调用失败时保留预分类结果；
4. 最终按 OCR 输入顺序排序。

高置信度直通避免了重复模型请求。

### 5.6 三级字段抽取

```text
LangExtract
  ↓ 不可用
LangChain structured output + Pydantic
  ↓ LLM 不可用或失败
正则抽取
```

实际算法：

1. 纯物证跳过文本字段抽取；
2. 按证据分类选择上下文和少样本；
3. 始终执行正则作为可合并兜底；
4. 合并正则和 LLM 字段并去重；
5. 映射为订单、支付、物流、发票、联系、时间和其他分类；
6. 使用 OCR 文本 MD5 作为 `source_hash`；
7. 已存在不少于 3 个高置信度字段且哈希未变时复用缓存；
8. 写入时先删除该证据旧字段再创建，保证结果幂等；
9. 任一字段置信度低于 `0.7` 时触发人工审核。

### 5.7 HITL 人工审核

`review_node` 汇总置信度低于 `0.7` 的字段并调用 `interrupt()`。前端提交校正后，后端使用 `Command(resume=...)` 恢复：

- 按 `evidence_id + field_name` 更新字段；
- 人工校正字段置信度设为 `1.0`；
- 从数据库重建抽取结果；
- 使用 `Overwrite` 替换状态结果；
- 转入证据链节点。

`interrupt()` 前不执行数据库写入，以满足恢复时节点重放的幂等要求。

### 5.8 安全阶段暂停

每个业务节点完成后进入 stage gate：

1. 查询 `Case.workflow_pause_requested`；
2. 未请求则继续；
3. 已请求则通过 `interrupt()` 保存 checkpoint；
4. WorkflowRunner 将状态改为 `paused`；
5. 前端加载当前阶段的编辑范围和产物；
6. 后端仅接受白名单字段，使用事务和行锁更新 MySQL；
7. resume payload 同步更新 LangGraph state，保证 checkpoint 与业务库一致。

| 暂停阶段 | 可编辑内容 |
|---|---|
| `preclassify` | 证据分类、视觉/OCR 摘要 |
| `ocr` | OCR 文本 |
| `classify` | 证据分类 |
| `extract` / `review` | 字段名和值 |
| `evidence_chain` | 时间线事件 |
| `complaint` / `respond_complaint` | 文书标题、正文、语气 |

暂停态可以取消本次工作流，已完成业务产物保留。

### 5.9 证据链与法律工具

`evidence_chain_node`：

1. 用规则服务重建基础时间线；
2. 从案件描述和字段生成检索词；
3. 主动预检索法条；
4. 将分类、字段、摘要和物证信息组织为 LLM 输入；
5. 可选绑定 7 个 LangChain 工具；
6. 最多执行 `TOOLS_MAX_ITERATIONS` 轮，同轮工具并发调用；
7. 解析 JSON 证据链并写回 `TimelineNode`；
8. LLM 不可用或解析失败时回退基础时间线。

| 工具 | 作用 |
|---|---|
| `lookup_law` | RAG 法条检索 |
| `lookup_precedent` | 类似判例查询 |
| `lookup_platform_rule` | 平台规则查询 |
| `calculate_compensation` | 赔偿建议计算 |
| `validate_legal_citation` | 校验法条，降低引用幻觉 |
| `jurisdiction_determine` | 推荐法院或受理渠道 |
| `case_similarity` | 检索相似历史案件 |

工具失败会被记录并作为工具结果返回给 LLM，不直接终止工作流。

### 5.10 投诉与答辩生成

`complaint_node` 与 `respond_complaint_node`：

1. 根据案件、字段和证据链构建 Jinja2 骨架；
2. 注入预检索法条；
3. 可选执行多轮法律工具；
4. 使用 LLM 重写；LLM 不可用时保留模板骨架；
5. upsert 到 `ComplaintTemplate` 或 `RespondTemplate`；
6. 保存标题、正文、模板类型、语气和工具日志；
7. LangGraph token 事件映射为 SSE 增量输出。

`case_mode` 决定最终分支：`complain` 生成投诉书，`respond` 生成反证答辩书。

---

## 6. 法律 RAG

### 数据分层

- MySQL `LawArticle`：正文、摘要、关键词、类别、适用场景和来源；
- PostgreSQL `law_article_vectors`：法条键、类别和 pgvector embedding；
- 默认 embedding：`BAAI/bge-large-zh-v1.5`，1024 维；
- 维度不超过 2000 时创建 HNSW cosine 索引，否则顺序扫描。

### 三阶段检索

```text
查询
  ├─ BM25：jieba 分词，法律术语精确召回
  └─ pgvector：embedding 余弦语义召回
          │
          ▼
RRF：score = Σ 1 / (60 + rank)
          │
          ▼
可选 Cross-Encoder Rerank
          │
          ▼
MySQL 回填完整法条 → Top-K
```

- RRF 只使用排名，不要求两种分数量纲一致；
- 配置 `RERANK_API_KEY` 后使用 `BAAI/bge-reranker-v2-m3`；
- 未配置 Rerank 时按 RRF 顺序截断；
- 支持法律类别预过滤；
- Embedding、向量库或检索失败时返回空列表，不阻断主流程。

### 导入命令

```bash
# 内置少量真实法条；配置可用时生成 embedding
python manage.py import_law_articles

# 自定义 JSON，仅写 MySQL
python manage.py import_law_articles --file=/path/law_articles.json --no-embed

# 平台规则
python manage.py import_law_articles --platform-file=/path/platform_rules.json

# 仅重建向量，不覆盖 MySQL 内容/关键词
python manage.py import_law_articles --embed-only

# 强制重建向量
python manage.py import_law_articles --force-embed
```

完整法条数量取决于实际导入文件，代码不保证部署环境固定包含某个条数。

---

## 7. SSE 实时架构

```text
LangGraph astream_events(v2)
  → SSEEventMapper
  → WorkflowRunner
      ├─ EventDepot.persist(thread_id, event)
      └─ NotifyEmitter.notify(thread_id, event_id)
  → PostgreSQL
      ├─ sse_event_depot：可靠存储
      └─ LISTEN/NOTIFY：低延迟唤醒
  → CaseWorkflowStreamView
      ├─ 回放 event_id > last_event_id
      ├─ 等待通知
      ├─ 拉取新增事件
      └─ 超时发送 heartbeat
```

EventDepot 负责可靠回放，`LISTEN/NOTIFY` 只负责通知，两者共同构成推拉结合架构。

前端监听：

```text
workflow.start, workflow.pause_requested, workflow.paused,
workflow.resumed, workflow.cancelled, workflow.complete,
workflow.error, workflow.waiting_review,
node.start, node.progress, node.complete, node.error,
complaint.token, complaint.done,
review.interrupt, review.resumed, review.skipped
```

### Token 批处理

WorkflowRunner 不逐 token 写库，而在以下任一条件满足时 flush：

- 片段数量达到 `SSE_TOKEN_BATCH_SIZE`，默认 50；
- 本批持续达到 `SSE_TOKEN_BATCH_INTERVAL`，默认 0.5 秒。

### 断线续传

服务端优先读取 `Last-Event-ID` 请求头，其次读取 `last_event_id` query 参数。前端记录最大 `event_id`；重连时服务端先回放遗漏事件，再进入实时订阅。

### 清理命令

```bash
python manage.py cleanup_sse_events
python manage.py cleanup_sse_events --hours=48 --dry-run

# 清理旧 checkpoint，同时保留每个 thread 最新记录
python manage.py cleanup_checkpoints --days=30
python manage.py cleanup_checkpoints --days=30 --dry-run
```

建议通过 cron 定时执行。项目当前未引入 Celery。

---

## 8. 前端路由

所有页面使用 `React.lazy` 和 `Suspense`。

| 路由 | 页面 | 权限 |
|---|---|---|
| `/home` | 公开首页 | 公开 |
| `/login` | 登录 | 仅未登录 |
| `/register` | 注册 | 仅未登录 |
| `/cases` | 案件列表和创建 | 登录 |
| `/dashboard` | 仪表盘 | 登录 |
| `/profile` | 资料、偏好、邮箱和会话 | 登录 |
| `/cases/:caseId/workspace` | 案件工作台 | 登录 |
| `/cases/:caseId/evidence` | 证据与实时工作流 | 登录 |
| `/cases/:caseId/timeline` | 时间线 | 登录 |
| `/cases/:caseId/complaint` | 投诉书 | 登录 |
| `/cases/:caseId/respond` | 反证答辩书 | 登录 |
| `/cases/:caseId/mask` | 隐私打码 | 登录 |
| `/cases/:caseId/export` | 导出 | 登录 |

根路径和未知路径当前重定向到 `/home`。

---

## 9. 前端交互实现

### 布局与设计系统

`AppLayout` 提供 sticky 顶栏、桌面全局导航、用户菜单、案件侧栏、移动端汉堡菜单与右侧抽屉。案件模式决定显示“投诉文本”还是“反证答辩”。账户菜单具有 ARIA menu 语义，支持点击外部和 Escape 关闭。

当前 CSS 设计令牌：

- 背景 `#f8f8f5`；正文 `#181b1a`；
- 主辅助绿 `#3f6b57`；柔和强调 `#e7eee9`；
- 边框 `#d9ddd5`；默认圆角 `0.75rem`；
- 字体为 Geist Sans、SF Pro Display、Segoe UI、苹方等系统字体；
- 支持 `prefers-reduced-motion`；
- 已定义暗色变量，但没有可见的主题切换入口。

### 认证状态

`api-client.ts`：

- access、refresh 和 session ID 保存到 `localStorage`；
- 自动注入 Bearer token 与 `X-Session-ID`；
- access 过期后只发起一个 refresh 请求，其他请求共享同一 Promise；
- refresh 成功后重放原请求，失败则清除认证状态。

`auth-store.ts` 在应用启动时恢复 token 并调用 `/auth/me/` 校验用户。

### 证据上传

1. 拖拽或文件选择；
2. 为本地图片创建预览 URL；
3. 在批量弹窗逐张设置普通证据或纯物证；
4. 纯物证说明必填，最多 500 字；
5. 多图通过 `Promise.all` 并行上传，每图一个请求；
6. 完成后释放 `ObjectURL`；
7. 证据卡展示分类、OCR、摘要、文本和字段；
8. 字段在 blur 时提交 PATCH；
9. 图片支持 Lightbox。

### 工作流面板

`WorkflowStreamPanel`：

- 未启动时显示开始按钮；
- 当前启动传空 `evidence_ids`，后端处理案件全部图片证据；
- 运行中显示节点轨道、连接状态和安全暂停按钮；
- `pausing` 表示请求已提交，当前节点完成后才暂停；
- `paused`/`waiting_review` 不允许直接重新启动；
- 成功或失败后可重新分析；
- 页面加载时根据案件 `thread_id` 恢复 UI。

`NodeTrack` 展示 8 个技术节点：手机 2 列、中屏 4 列、超宽屏 8 列。节点显示业务分组、状态、细分进度、当前暂停点和 SSE 状态。

### 产物流

`ProductStream` 按完成顺序展示：预分类、OCR、分类、抽取字段、证据链、工具日志、文书、错误、人工审核和暂停编辑面板。新增产物时折叠前一个区块并展开最新区块，内容变化时滚动到底部。

### 长文书增量渲染

`ComplaintStreamBlock` 使用 `renderedLengthRef` 跟踪已渲染长度：

- token 到来时只追加新的 DOM Text Node；
- 避免 React 每次 diff 整篇长文；
- `complaint.done` 到达后用最终正文替换增量结果；
- 实时显示字数和生成状态。

### SSE 客户端

`WorkflowSSEClient`：

- 使用原生 `EventSource`；
- 通过 `last_event_id` query 参数续传；
- access token 通过 query 参数传递，因为原生 EventSource 不能设置 Authorization Header；
- 1、2、4、8、16 秒指数退避，最多重连 5 次；
- 收到完成、失败、审核、暂停或取消终态后关闭连接。

query token 是当前代码的实际实现，生产部署应避免访问日志记录完整 query string。

### 页面刷新恢复

`restoreWorkflow`：

1. 从案件 `thread_id` 初始化运行；
2. 请求 `/workflow/replay/`；
3. 校验 thread ID，丢弃路由切换后的迟到响应；
4. 每 40 条事件一批复用 SSE reducer；
5. 批次间 `setTimeout(0)` 让出主线程；
6. reducer 按 `event_id` 去重；
7. 暂停态再请求 `/workflow/state/` 获取编辑范围和数据库快照；
8. 运行中或等待安全暂停时，从最后事件 ID 重连。

### 暂停与审核

`StagePausePanel` 根据后端 `editable_scope` 渲染证据分类/摘要/OCR、抽取字段、时间线或文书编辑器。前端执行必填与长度校验；后端再次验证字段白名单、归属和暂停阶段。用户可保存继续或取消。

`ReviewInterruptPanel` 展示低置信度字段、证据 ID 和置信度，提交校正后调用 resume API 并重连 SSE。

### 脱敏与导出

脱敏页支持文本原值/掩码切换、敏感类型标签、批量图片打码、原图/打码图对比。导出页支持文本包预览、ZIP、PDF、模板选择和文本打码开关。

---

## 10. 主要 API

完整定义以 `backend/api/urls.py` 为准。

### 工作流

```text
POST /api/cases/{id}/run-workflow/        # 旧同步入口，保留兼容
GET  /api/cases/{id}/workflow/history/   # checkpoint 历史
GET  /api/cases/{id}/workflow/replay/    # EventDepot 回放
POST /api/cases/{id}/workflow/pause/     # 请求安全暂停
POST /api/cases/{id}/workflow/cancel/    # 暂停态取消
GET  /api/cases/{id}/workflow/state/     # 暂停产物与编辑范围
POST /api/cases/{id}/workflow/start/     # 启动后台任务
GET  /api/cases/{id}/workflow/stream/    # SSE
POST /api/cases/{id}/workflow/resume/    # 审核或暂停恢复
```

### 案件与产物

```text
GET/POST     /api/cases/
GET          /api/cases/{id}/
PATCH/DELETE /api/cases/{id}/manage/
POST         /api/cases/{id}/status/transition/

GET/POST     /api/cases/{id}/evidences/
POST         /api/cases/{id}/evidences/upload/
DELETE       /api/evidences/{id}/
GET          /api/evidences/{id}/extracted-fields/
PATCH        /api/extracted-fields/{id}/

GET/POST     /api/cases/{id}/timeline/
POST         /api/cases/{id}/timeline/rebuild/
PATCH        /api/timeline-nodes/{id}/

GET          /api/cases/{id}/complaints/
POST         /api/cases/{id}/complaints/regenerate/
GET          /api/cases/{id}/respond-templates/
POST         /api/cases/{id}/respond-templates/regenerate/

GET          /api/cases/{id}/mask/
POST         /api/cases/{id}/mask-images/
POST         /api/cases/{id}/export/
GET          /api/cases/{id}/export/package/
GET          /api/cases/{id}/export/pdf/
```

账户接口覆盖注册、邮箱验证码登录、密码重置、token 刷新、资料、头像、偏好、邮箱变更、登出和会话撤销，详见路由文件。

---

## 11. 目录结构

```text
claimcraft-creative/
├── backend/
│   ├── api/
│   │   ├── agents/
│   │   │   ├── graph.py                  # 图、PG pool、Saver、Store
│   │   │   ├── state.py                  # 工作流状态
│   │   │   ├── workflow_runner.py        # 后台执行和事件生产
│   │   │   ├── sse_event_depot.py        # 事件保留站
│   │   │   ├── notify_emitter.py         # LISTEN/NOTIFY
│   │   │   ├── sse_event_mapper.py       # LangGraph → SSE
│   │   │   ├── nodes/                    # 8 节点 + stage gate
│   │   │   ├── prompts/                  # 提示词
│   │   │   ├── tools/                    # 正则和法律工具
│   │   │   └── utils/
│   │   ├── services/                     # OCR、RAG、文书、打码、导出等
│   │   ├── management/commands/
│   │   ├── migrations/
│   │   ├── tests/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── claimcraft/                       # settings、urls、ASGI、WSGI
│   ├── requirements.txt
│   ├── seed_data.json
│   └── manage.py
├── frontend/
│   ├── src/
│   │   ├── components/auth/
│   │   ├── components/workflow/
│   │   ├── composables/
│   │   ├── layouts/AppLayout.tsx
│   │   ├── lib/                          # Axios、API、SSE、事件
│   │   ├── pages/
│   │   ├── stores/
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.ts
├── docs/
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── nginx.conf
├── .env.example
└── README.md
```

---

## 12. 本地开发

### 环境要求

- Python 3.11 推荐；
- Node.js 22 推荐，与 Docker 构建环境一致；
- MySQL 8；
- PostgreSQL 16 + pgvector 推荐；
- Tesseract 可选；
- 至少一个文本 LLM，才能获得完整证据链与文书重写。

### 环境变量

```bash
cp .env.example .env
```

本地 Django 会读取仓库根目录 `.env`。至少检查：

```dotenv
DB_NAME=claimcraft
DB_USER=root
DB_PASSWORD=replace-me
DB_HOST=127.0.0.1
DB_PORT=3306

CHECKPOINTER_DB_URL=postgresql://claimcraft:replace-me@127.0.0.1:5432/claimcraft_checkpoints
LAW_VECTOR_DB_URL=postgresql://claimcraft:replace-me@127.0.0.1:5432/claimcraft_checkpoints

LLM_PROVIDER=siliconflow
LLM_API_KEY=

DJANGO_SECRET_KEY=replace-with-random-secret
DJANGO_DEBUG=True
```

Compose 读取根变量 `SECRET_KEY` 并注入容器内 `DJANGO_SECRET_KEY`；本地直接运行 Django 时应配置 `DJANGO_SECRET_KEY`。生产环境必须使用随机密钥。

### 数据库

MySQL：

```sql
CREATE DATABASE claimcraft
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

PostgreSQL：

```sql
CREATE USER claimcraft WITH PASSWORD 'replace-me';
CREATE DATABASE claimcraft_checkpoints OWNER claimcraft;
\c claimcraft_checkpoints
CREATE EXTENSION IF NOT EXISTS vector;
```

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate

# 可选演示数据
python manage.py loaddata seed_data.json

# 推荐 ASGI；当前 SSE 视图为异步实现
uvicorn claimcraft.asgi:application --host 0.0.0.0 --port 8000 --reload
```

Windows 激活：

```powershell
.venv\Scripts\Activate.ps1
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`。Vite 将 `/api` 和 `/media` 代理到 `http://localhost:8000`。

```bash
npm run build     # tsc + vite build
npm run preview
```

---

## 13. Docker Compose

```bash
cp .env.example .env
# 修改数据库密码、SECRET_KEY 和模型凭据
docker compose up -d --build

docker compose logs -f backend
docker compose down
```

访问 `http://localhost`。

| 服务 | 作用 |
|---|---|
| `mysql` | MySQL 业务数据库 |
| `postgres-checkpointer` | checkpoint、Store、SSE 和法条向量 |
| `backend` | Django + Uvicorn，启动时迁移、创建演示管理员并尝试加载种子数据 |
| `frontend` | Nginx 托管 React 和反代 API/SSE/media/static |

默认容器启动会准备演示账号 `admin / admin123`。该账号仅适合本地或演示，生产部署必须修改启动逻辑和密码。

当前 Compose 含服务器特定 bind mount：

```text
/srv/claimcraft/.agently-home
/home/ubuntu/claimcraft-creative/logs/backend
/home/ubuntu/claimcraft-creative/logs/frontend
```

在 macOS、Windows 或其他 Linux 环境应改为本机路径或命名 volume。

---

## 14. 环境变量分组

完整定义见 `.env.example` 和 `docker-compose.yml`。

| 分组 | 前缀 | 作用 |
|---|---|---|
| Django/MySQL | `DJANGO_*`、`DB_*` | 应用与业务库 |
| Checkpoint | `CHECKPOINTER_*` | PostgreSQL 连接池 |
| 文本 LLM | `LLM_*` | 分类、证据链、文书 |
| 视觉 OCR | `LLM_OCR_*` | 视觉模型 OCR |
| Captioner | `LLM_CAPTIONER_*` | 视觉预分类与摘要 |
| PaddleOCR-VL | `PADDLEOCR_VL_*` | 云端文档 OCR |
| LangExtract | `LANGEXTRACT_*` | 字段抽取 |
| OCR 策略 | `OCR_*`、`TESSERACT_CMD` | 顺序和重试 |
| Embedding | `EMBEDDING_*` | 法条向量 |
| RAG/Rerank | `RAG_*`、`RERANK_*`、`LAW_VECTOR_DB_URL` | 检索与精排 |
| Tools | `TOOLS_*` | 法律工具开关与轮次 |
| SSE | `SSE_TOKEN_*`、`SSE_EVENT_DEPOT_TTL_HOURS` | token 批处理和保留期 |
| LangSmith | `LANGSMITH_*` | 可选 tracing |
| 邮件 | `CLAIMCRAFT_AGENT_MAIL_*`、`CLAIMCRAFT_SMTP_*` | 验证邮件 |
| 头像 | `CLAIMCRAFT_AVATAR_*` | 上传和展示图 |

`.env.example` 与 Compose 的部分默认值目前不同，例如 `RAG_TOP_K`、PaddleOCR-VL 轮询超时和 SMTP 模式。实际值以进程收到的环境变量为准；Compose 部署可运行：

```bash
docker compose config
```

---

## 15. 测试与检查

### 后端

当前测试覆盖账户、头像/邮件、案件生命周期和投诉服务；尚无完整 LangGraph、SSE 与阶段暂停端到端测试。

```bash
cd backend

# manage.py test 默认自动使用 SQLite
python manage.py test
python manage.py check

python manage.py test api.tests.test_case_lifecycle
python manage.py test api.tests.test_complaint_service
```

### 前端

当前未配置单元测试框架。生产构建会执行 TypeScript 检查：

```bash
cd frontend
npm run build
```

---

## 16. 当前实现边界

- 尚无独立 `WorkflowRun`、`WorkflowArtifact`、`WorkflowIntervention` 模型；运行状态保存在 `Case` 和 checkpoint；
- 阶段暂停与低置信度审核仍为两套前端面板；
- 启动 UI 不支持选择部分证据，当前默认分析全部图片证据；
- 前端没有全局 live region、skip-to-content 或完整焦点管理；
- 前端没有单元测试配置；
- 未引入 Celery，后台任务使用进程内事件循环/线程和 Future 注册表；
- 法条数量取决于部署导入数据，不保证固定数量；
- EventSource 通过 query 参数携带 access token，需注意代理日志安全；
- `Case.case_type` 当前只有四类，虽然法律工具覆盖更多领域；
- 暗色 CSS 变量已定义，但没有主题切换 UI；
- Docker Compose 当前含服务器特定挂载路径；
- 根目录早期 spec 可能与现状不同，应以当前代码和本文为准。

---

## 17. 关键设计决策

| 决策 | 当前选择 | 原因 |
|---|---|---|
| 存储 | MySQL + PostgreSQL | 业务 CRUD 与 LangGraph/pgvector/通知分工 |
| 工作流 | LangGraph StateGraph | checkpoint、条件路由、HITL |
| 暂停 | 节点完成后的 stage gate | 避免中途暂停产生半成品 |
| 多证据 | 节点内 `asyncio.gather` | 提高吞吐并隔离单条失败 |
| 分类 | 高置信度直通、低置信度细化 | 降低重复模型调用 |
| 抽取 | LangExtract → structured output → 正则 | 精度与可用性分层降级 |
| 缓存 | OCR MD5 + 高置信度字段 | 源文本未变时避免重复抽取 |
| RAG | BM25 + 向量 + RRF + 可选 Rerank | 兼顾术语与语义匹配 |
| 防幻觉 | 法条引用校验工具 | 验证法律名称与条款编号 |
| SSE | EventDepot + LISTEN/NOTIFY | 可靠回放与实时通知结合 |
| Token 流 | 批量落库 | 平衡实时性和写入/渲染成本 |
| 页面恢复 | replay + 同一 reducer | 刷新后重建实时 UI |
| 长文本 | 增量 DOM append | 避免每 token 整篇 React diff |

---

## 18. 相关文档

- [`docs/workflow-fullstack-upgrade-design.md`](docs/workflow-fullstack-upgrade-design.md)：后续前后端统一升级设计；
- [`docs/superpowers/specs/2026-07-07-sse-workflow-design.md`](docs/superpowers/specs/2026-07-07-sse-workflow-design.md)：SSE 设计背景；
- [`docs/backend-user-auth-optimization-design.md`](docs/backend-user-auth-optimization-design.md)：账户体系设计；
- [`docs/server-mail-service-deployment-guide.md`](docs/server-mail-service-deployment-guide.md)：邮件部署；
- [`docs/linux-kb-build-guide.md`](docs/linux-kb-build-guide.md)：Linux 知识库构建；
- [`.env.example`](.env.example)：完整运行参数。

---

## 19. 许可证

本项目仅用于学习与演示目的。
