# ClaimCraft 工作流前后端统一优化升级 Spec

> 对应设计文档：`docs/workflow-fullstack-upgrade-design.md`
> 参考技能：`framework-selection` / `langgraph-fundamentals` / `langgraph-human-in-the-loop` / `langgraph-persistence`
> 范围：后端统一领域模型 + 质量门 + 统一 API + SSE 协议升级 + LangGraph 架构对齐；前端业务阶段化 + 统一介入 + Store 拆分 + SSE 同步规则 + 视觉与可访问性升级。
> 分 5 个阶段交付，每阶段独立可验证、不破坏现有 API。

## Why

当前系统已完成 SSE 流式推送、断连续传、HITL 中断恢复、阶段暂停等基础能力，但存在 15 项重大差距导致产品形态停留在「技术节点展示 + SSE 流式」层级：

1. **无统一契约**：节点返回结构各异（dict / Command），无 `NodeResult` 统一信封，缺 `quality / warnings / provenance / metrics` 字段；
2. **无运行实例**：所有工作流状态堆在 `Case` 模型上，无法支持「一案件多运行历史」「局部重跑」「产物过期传播」；
3. **无质量门**：现有 `stage_gate` 是「安全暂停门」，非设计文档定义的「质量门」；
4. **无统一介入**：`ReviewInterruptPanel` 与 `StagePausePanel` 是两套独立面板，用户体验割裂；
5. **API 路径不一致**：全部基于 `/cases/<id>/workflow/*`，无 `/workflow-runs/*` 形式；
6. **SSE 协议不完整**：事件信封缺 `run_id / revision / occurred_at`，无 `stage.* / artifact.* / intervention.* / issue.*` 业务事件类型；
7. **SSE 鉴权不安全**：JWT token 通过 query parameter 传递，违反安全基线；
8. **前端状态管理未拆分**：单一 `useCaseStore` 承载所有状态，无 `workflowRunSlice / interventionSlice`；
9. **前端组件缺失**：5 个核心升级组件（`InterventionPanel / BusinessStageStepper / WorkflowCommandBar / DocumentEditor / QualitySummary`）全部不存在；
10. **前端 SSE 消费规则不完整**：仅基于 `event_id` 单维去重，无 `run_id / revision` 检查，无 revision 跳跃时重新获取 snapshot；
11. **LangGraph HITL 模式不规范**：现有 `review_node` 与 `stage_gate_node` 未严格遵循 `interrupt()` + `Command(resume=...)` 模式，interrupt 前的副作用非幂等；
12. **LangGraph 持久化策略缺失**：未利用 `get_state_history` 实现局部重跑，未明确子图 checkpointer 作用域，未使用 `Overwrite` 处理 reducer 字段替换；
13. **LangGraph 错误处理未分层**：未使用 `RetryPolicy` 处理瞬时错误，未使用 `interrupt()` 处理用户可修复错误；
14. **LangGraph State 版本化缺失**：`state_schema_version` 变更时无迁移策略，旧 checkpoint 不可加载时无降级方案；
15. **LangGraph Store 未利用**：跨运行的用户偏好与案件模板未使用 Store 持久化。

升级目标：将系统从「可运行的 AI 工作流」升级为「可用于真实案件材料整理的专业工作台」，形成完整、可靠、可解释的案件材料闭环，同时所有 LangGraph 工作流设计严格遵循官方最佳实践。

## LangGraph 架构对齐

> 本节明确所有 LangGraph 设计决策与官方 skills 的对齐关系，作为后续实现的强制约束。

### A. State Schema 设计（对齐 `langgraph-fundamentals`）

`CaseWorkflowState` 必须遵循以下 reducer 规则：

| 字段类别 | 字段示例 | Reducer 策略 | 理由 |
|---|---|---|---|
| 累积列表 | `evidence_preclassify_results / evidence_ocr_results / evidence_classify_results / evidence_extract_results / evidence_chain / errors / warnings / provenance / artifacts / interventions / issues / events` | `Annotated[list, operator.add]` | 多节点持续追加，避免被覆盖 |
| 标量覆盖 | `revision / current_stage / current_node / progress / workflow_version / state_schema_version` | 默认覆盖（无 reducer） | 每次更新即最新值 |
| 集合去重 | `stale_artifact_ids` | 自定义去重 reducer 或使用 `Overwrite` 替换 | 避免重复 ID 累积 |
| 用户确认 | `user_confirmed_fields` | 自定义合并 reducer（按字段名 merge） | 局部更新不覆盖其他字段 |

**强制约束**：
- 节点必须返回 **partial update dict**，不能 mutate 并返回整个 state：`return {"evidence_ocr_results": [...], "node_result": {...}}` 而非 `return state`
- `NodeResult` 结构存储在 state 的 `node_result` 键下，不直接展开为 state 顶层字段
- 新增字段必须考虑旧 checkpoint 的兼容性（默认值或迁移函数）

### B. HITL 模式（对齐 `langgraph-human-in-the-loop`）

`review_node` 与 `stage_gate_node` 必须严格遵循 LangGraph HITL 模式：

1. **interrupt 前副作用必须幂等**：
   - `WorkflowIntervention` 记录使用 `update_or_create`（按 `workflow_run + intervention_type + stage` 幂等），不能使用 `create`
   - SSE 事件发布使用 upsert 语义，避免 resume 时重复推送
   - 数据库状态标记使用 `update_fields` 而非全量保存

2. **interrupt 调用位置**：
   - `interrupt()` 必须在节点逻辑的**最后阶段**调用（在所有幂等副作用之后）
   - resume 时节点从头重新执行，所有 interrupt 前的代码会再次运行
   - 因此幂等副作用可安全重放，非幂等副作用必须移到 `interrupt()` 返回之后

3. **resume 必须使用 `Command(resume=...)`**：
   - `WorkflowRunner.resume()` 必须调用 `graph.invoke(Command(resume=resume_value), config)` 而非 `graph.invoke({"resume_data": ...}, config)`
   - 当前 `resumePausedWorkflow` 若传普通 dict 会导致 graph 从头重启（stuck），必须修正

4. **中断 payload 必须可 JSON 序列化**：
   - `interrupt()` 传入的 value 必须可序列化（dict / list / str / number / bool / None）
   - 不可传入 Django Model 实例、datetime（需 ISO 8601 字符串）、自定义类

5. **子图 interrupt 重执行**：
   - 若节点内部调用子图且子图含 `interrupt()`，resume 时父节点和子图节点都会重新执行
   - 文书生成若使用子图，需明确此行为，副作用必须幂等

6. **多中断并行处理**：
   - 若并行处理多证据且各自 `interrupt()`，resume 时需传入 `{interrupt_id: resume_value}` 映射
   - `WorkflowRunner` 需支持多中断同时 resume

### C. Checkpointer 配置（对齐 `langgraph-persistence`）

1. **PostgresSaver 生产配置**：
   - 使用 `PostgresSaver.from_conn_string(DATABASE_URL)`（已部署）
   - `checkpointer.setup()` 仅在首次部署时执行一次，创建所需表
   - 不使用 `InMemorySaver`（仅开发测试可用）

2. **thread_id 命名规则**：
   - 每个 `WorkflowRun` 拥有独立 `thread_id`，格式：`case-{case_id}-run-{run_id}`
   - 不复用旧 `Case.thread_id`，避免多运行历史混淆
   - 旧 `Case.thread_id` 保留作为兼容字段，迁移期间双写

3. **time travel 实现局部重跑**：
   - `RetryService.retry_from_stage()` 使用 `graph.get_state_history(config)` 找到 `from_stage` 对应的历史 checkpoint
   - 使用 `graph.update_state(past.config, new_state)` fork 出新分支
   - 使用 `graph.invoke(None, fork_config)` 从 fork 点恢复执行
   - **重要**：`update_state` 会穿过 reducer，需用 `Overwrite` 替换列表字段而非追加

4. **update_state 与 reducer 交互**：
   - 介入提交时若需替换列表字段（如 `evidence_extract_results`），必须使用 `Overwrite([...])` 而非直接传 list
   - 直接传 list 会被 reducer 追加，导致数据重复

5. **子图 checkpointer 作用域**：
   - 文书生成子图：`checkpointer=None`（默认，需 interrupt 但不需跨调用记忆）
   - RAG 检索子图：`checkpointer=False`（无 interrupt，无记忆，最简）
   - 不使用 `checkpointer=True`（stateful subgraph），避免并行调用 namespace 冲突

6. **Store 跨运行记忆**：
   - 用户偏好（默认模板类型、介入策略偏好）使用 `InMemoryStore` 或 `PostgresStore` 跨运行共享
   - 节点通过 `runtime.store` 访问，不直接引用 store 实例
   - namespace 规则：`("user", user_id, "preferences")` / `("case", case_id, "templates")`

### D. 错误处理 4 层策略（对齐 `langgraph-fundamentals`）

| 错误类型 | 处理者 | LangGraph 策略 | 本项目应用 |
|---|---|---|---|
| 瞬时错误（网络、限流） | 系统 | `RetryPolicy(max_attempts=3, initial_interval=1.0)` on `add_node()` | LLM 调用、OCR API、Embedding API |
| LLM 可恢复错误（工具失败） | LLM | `ToolNode(handle_tool_errors=True)` 返回 ToolMessage | 工具调用节点 |
| 用户可修复错误（缺信息） | 人工 | `interrupt()` 暂停并收集输入 | 低置信度字段、阶段暂停、法律确认 |
| 未预期错误 | 开发者 | `raise` 向上抛出 | 代码 bug、数据不一致 |

**强制约束**：
- 不在节点内部手动实现重试循环，使用 `add_node(name, func, retry_policy=RetryPolicy(...))`
- 用户可修复错误必须使用 `interrupt()` 而非抛异常（异常会终止整个 graph）
- `NodePolicy` 概念映射到 `RetryPolicy`，不再自定义重试类

### E. State 版本化与迁移（对齐 `langgraph-persistence`）

1. **版本字段**：`workflow_version / state_schema_version / policy_version / prompt_bundle_version` 写入 initial state 与 `WorkflowRun`
2. **恢复旧 checkpoint 时**：
   - 检查 `state_schema_version` 兼容性
   - 可迁移：执行 state migration 函数（`migrate_state_v1_to_v2(old_state) -> new_state`）
   - 不可迁移：保留旧 `WorkflowArtifact`，提示用户重新发起运行
3. **历史文书版本**：`DocumentVersion` 记录生成时的 `workflow_version`，满足审计需求

### F. Send API 并行处理（对齐 `langgraph-fundamentals`）

- 多证据并行处理使用 `Send("worker_node", {"evidence_id": eid})` fan-out
- 结果字段必须使用 `Annotated[list, operator.add]` reducer 累积，否则最后写入者覆盖
- 当前项目已是累积式，确认不破坏

## What Changes

### 后端变更

#### 阶段 1：统一契约与体验修复 + LangGraph 架构对齐

- **新增 `NodeResult` 统一输出结构**（TypedDict）：`data / quality / warnings / errors / provenance / metrics` 六字段
- **升级 `CaseWorkflowState`**：新增 `revision / workflow_version / state_schema_version / policy_version / prompt_bundle_version / current_stage / current_node / progress / artifacts / interventions / stale_artifact_ids / node_result / user_confirmed_fields` 字段；`errors` 从 `list[str]` 升级为 `list[dict]`；新增字段使用正确的 reducer（累积列表用 `Annotated[list, operator.add]`，标量用默认覆盖）
- **统一节点输出**：所有 8 个节点返回 partial update dict，包含 `node_result: NodeResult` 键 + 旧字段保留向后兼容
- **升级 SSE 事件信封**：在 `EventDepot` 表和 `sse_event_depot.py` 中新增 `run_id / revision / occurred_at` 字段（保留 `created_at` 兼容），`_format_sse_event` 输出统一信封
- **新增事件类型**：`stage.started / stage.progress / stage.completed / stage.quality_changed / artifact.created / artifact.updated / artifact.stale / intervention.created / intervention.submitted / intervention.cancelled / document.delta / document.completed / issue.created / issue.resolved`，旧事件类型保留兼容映射
- **新增工作流版本字段**：`WorkflowVersion` 常量（`WORKFLOW_VERSION = "v11"`、`STATE_SCHEMA_VERSION = 1`、`PROMPT_BUNDLE_VERSION`、`POLICY_VERSION`），写入 `CaseWorkflowState` 和运行实例
- **引入 SSE Ticket**：`POST /api/cases/{case_id}/workflow-runs/` 创建运行时返回 `stream_ticket`（2-5 分钟有效，仅可读指定 run_id），`CaseWorkflowStreamView` 接受 ticket 鉴权
- **LangGraph RetryPolicy 配置**：所有调用 LLM / OCR / Embedding API 的节点在 `add_node()` 时配置 `retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0, backoff="exponential_jitter")`
- **保留现有 API 兼容**：现有 `/cases/<id>/workflow/*` 端点全部保留，新端点通过 `/workflow-runs/*` 平行提供

#### 阶段 2：统一用户介入与质量门 + LangGraph HITL 规范化

- **新增 `WorkflowIntervention` 模型**：`workflow_run / intervention_type (quality_review/user_pause/legal_confirmation/missing_information) / stage / status (pending/submitted/cancelled) / required / reason / editable_scope / form_schema / initial_values / submitted_values / base_revision / created_at / submitted_at`
- **新增 `InterventionService`**：统一管理介入创建、提交、取消、冲突检测
- **统一 `review.interrupt` 和 `stage_pause`**：
  - `review_node` 和 `stage_gate_node` 改为创建 `WorkflowIntervention` 记录（**使用 `update_or_create` 幂等**，避免 resume 时重复创建）
  - 中断 payload 统一为 `interrupt_type=workflow_intervention + intervention_id + intervention_kind + required + stage + reason + base_revision + form_schema + initial_values + impact.stale_artifacts`
  - **`interrupt()` 调用必须在所有幂等副作用之后**
- **`WorkflowRunner.resume()` 修正**：必须使用 `graph.invoke(Command(resume=resume_value), config)` 而非普通 dict
- **新增质量评分**：在 `NodeResult.quality` 字段中输出 `score / coverage / status (high/review_required/blocked) / blocking_issues`，节点级质量规则按设计文档 5.2 实现
- **新增 `Issue` 概念**：`NodeResult.warnings` + `errors` 统一为 `issues`，含 `code / message / severity (blocking/warning/info) / evidence_id / stage / recoverable`
- **revision 冲突检测**：`POST /api/workflow-runs/{run_id}/interventions/{intervention_id}/submit/` 在 `base_revision != current_revision` 时返回 `409 Conflict` + `REVISION_CONFLICT` code
- **用户确认字段标记**：`ExtractedField` 新增 `user_confirmed: BooleanField(default=False)` + `confirmed_at: DateTimeField(null=True)`，局部重跑时默认保留
- **介入提交使用 `Overwrite`**：提交介入时若需替换 `evidence_extract_results` 等列表字段，使用 `graph.update_state(config, {"evidence_extract_results": Overwrite([...])})` 而非直接传 list

#### 阶段 3：运行实例与局部重跑 + LangGraph Time Travel

- **新增 `WorkflowRun` 模型**：`case / thread_id (unique, 格式 case-{case_id}-run-{run_id}) / workflow_version / state_schema_version / policy_version / prompt_bundle_version / status / current_stage / current_node / progress / revision / selected_evidence_ids / run_options / quality_summary / started_at / finished_at`
- **新增 `WorkflowArtifact` 模型**：`workflow_run / artifact_type / stage / version / revision / status (current/stale/superseded) / content (JSON) / source_refs (JSON) / quality (JSON)`
- **`Case` 模型扩展**：新增 `active_workflow_run_id` 外键（保留旧 `thread_id / workflow_status` 字段双写兼容）
- **新增 `/workflow-runs/*` API 端点**：7 个端点（创建运行、获取快照、暂停、提交介入、局部重跑、取消、历史运行）
- **新增 `SnapshotService`**：聚合 `WorkflowRun + WorkflowArtifact + WorkflowIntervention + issues + actions` 返回权威快照
- **`RetryService` 基于 LangGraph Time Travel**：
  - 使用 `graph.get_state_history(config)` 找到 `from_stage` 对应的历史 checkpoint
  - 使用 `graph.update_state(past.config, fork_state)` fork 新分支（列表字段用 `Overwrite`）
  - 使用 `graph.invoke(None, fork_config)` 从 fork 点恢复执行
  - 创建新 `WorkflowRun` 记录 fork 出的运行
  - 自动标记下游产物为 `stale`
- **产物依赖关系**：`WorkflowArtifact.source_refs` 记录上游产物 ID，上游变更时自动传播 `stale` 状态
- **`actions` 字段返回**：所有 `/workflow-runs/*` 响应含 `can_pause / can_resume / can_cancel / can_retry / can_restart_from_stage`
- **子图 checkpointer 作用域配置**：
  - 文书生成子图：`checkpointer=None`（默认，需 interrupt 但无跨调用记忆）
  - RAG 检索子图：`checkpointer=False`（无 interrupt，最简）
  - 不使用 `checkpointer=True` 避免 namespace 冲突

#### 阶段 4：专业文书工作台

> 阶段 4.1（段落级证据引用 + `DocumentVersion` 模型）已实现并 37 测试通过；阶段 4.2/4.3 在此基础上展开。

- **段落级证据引用（已完成）**：`ComplaintTemplate` / `RespondTemplate` 已新增 `paragraphs: JSONField`，每段含 `content / evidence_codes / legal_references / source_regions`
- **文书版本历史（已完成）**：`DocumentVersion` 模型已建立，记录 `document / version / content / changelog / created_by_type / created_by_id / created_at / workflow_version`
- **局部段落重新生成（已完成）**：`POST /api/workflow-runs/{run_id}/documents/{document_id}/paragraphs/{paragraph_id}/regenerate/`
- **法律引用一致性校验（阶段 4.2 待实现）**：新建 `backend/api/services/document_quality_service.py`，调用 `LawRetriever`（已存在于 `backend/api/services/rag_service.py`）验证 `paragraphs[].legal_references[]` 中的法条是否真实存在于 `law_data` 表
- **导出前质量门（阶段 4.2 待实现）**：`POST /api/workflow-runs/{run_id}/documents/{document_id}/export-check/` 返回 `{passed, issues, missing_elements}`，检查项包含：
  - 法条引用真实性（通过 `LawRetriever.retrieve` 反查或直接查 `law_data` 表）
  - 文书金额与 `ExtractedField` 中的金额字段一致性
  - 主体名称一致性（投诉人/被投诉人 vs `ExtractedField.subject`）
  - 必备要素完整性（事实、依据、诉求三段）
  - 是否引用 `stale` 状态的下游产物
- **`quality_gate_service` 接入（阶段 4.2 待实现）**：现有 `evaluate_document_generation(legal_references_valid=None)` 占位参数需由 `document_quality_service` 计算后传入，将 `None` 替换为 `True/False`
- **DocumentEditor + DocumentSourcePanel（阶段 4.3 待实现）**：前端双栏布局 + 自动保存 + 段落级引用 + 重新生成 + AI/用户内容标记 + 影响确认

#### 阶段 5：LangGraph Store 跨运行记忆 + State 版本化

> **重要前提**：`PostgresStore` 已在 `backend/api/agents/graph.py` 的 `_get_store()` 中初始化并通过 `g.compile(checkpointer=..., store=_get_store())` 传入编译图；Task 5.1 **不需要新增 store 实例**，只需在节点中通过 `runtime.store` 访问。

- **节点签名升级**：将访问 Store 的节点签名从 `def node(state)` / `def node(state, config)` 升级为 `def node(state, runtime: Runtime)`（对齐 `langgraph-persistence` skill 的 `runtime.store` 模式）
- **Store 命名空间规则**（已就绪的 `PostgresStore` 实例支持）：
  - `("user", user_id, "preferences")`：用户默认介入策略偏好、默认模板类型
  - `("case", case_id, "templates")`：案件模板缓存（避免重复 LLM 调用）
  - `("case", case_id, "legal_cache")`：法律检索结果缓存（同案件多运行共享）
- **应用场景实现**：
  - 用户偏好：运行结束时 `runtime.store.put(("user", user_id, "preferences"), "intervention_policy", {"value": "critical_only"})`，下次启动时 `runtime.store.get(...)` 读取
  - 案件模板：`complaint_node` / `respond_complaint_node` 启动时先查 Store，命中则跳过 LLM 调用
  - 法律缓存：`evidence_chain_node` 调用 `LawRetriever` 前，先查 Store 缓存
- **State Schema 版本化**：
  - 在 `backend/api/agents/version.py` 新增 `migrate_state_v1_to_v2(old_state) -> new_state` 迁移函数（预留，当前 `STATE_SCHEMA_VERSION=1`）
  - 在 `WorkflowRunner.resume()` 中检查 `state_schema_version` 兼容性
  - 不可迁移时保留旧 `WorkflowArtifact`，返回提示「此运行基于旧版本，建议重新发起」
  - `DocumentVersion` 已记录 `workflow_version`，满足审计需求（Task 4.1 已完成）

### 前端变更

#### 阶段 1：统一契约与体验修复

- **新增类型定义**：`types/workflow.ts` 含 `WorkflowRun / WorkflowArtifact / WorkflowIntervention / WorkflowStage / WorkflowIssue / WorkflowAllowedActions / WorkflowRunSummary / WorkflowRunState / SnapshotSchema / NodeResult / QualityReport / Provenance / Warning`
- **升级 `SSEEvent` 类型**：新增 `run_id / revision / occurred_at` 字段
- **重构 `NodeTrack` 为 `BusinessStageStepper`**：4 业务阶段横向轨道
- **新增 `WorkflowCommandBar` + `CurrentActivityPanel`**
- **修复 `ProductStream` 自动滚动**：用户主动向上滚动后停止自动跟随
- **新增 ARIA live / alert** + 错误分组展示 + 启动按钮防重复 + 移动端布局修复

#### 阶段 2：统一用户介入与质量门

- **合并 `ReviewInterruptPanel` + `StagePausePanel` 为 `InterventionPanel`**：根据 `form_schema` 动态渲染
- **新增 `InterventionField` / `EvidenceSourceViewer` / `QualitySummary` / `QualityBadge` / `IssueList` / `IssueCard`**
- **草稿持久化**：`sessionStorage` key 包含 `runId + interventionId + revision`

#### 阶段 3：运行实例与局部重跑

- **Zustand store 拆分为三 slice**：`caseSlice / workflowRunSlice / interventionSlice`
- **新增 `workflowEventReducer` 纯函数**：SSE 事件先经过 reducer 处理
- **新增 `RunHistoryDrawer` / `RunConfigurationDrawer` / `ArtifactTimeline` / `ArtifactCard` / `WorkflowRecoveryPanel`**
- **过期产物提示**：`artifact.stale` 事件触发 UI 提示
- **`api.ts` 扩展 + Fetch Stream 升级**

#### 阶段 4：专业文书工作台

- **新增 `DocumentEditor`**：双栏布局 + 自动保存 + 版本历史 + 段落级证据引用
- **新增 `DocumentSourcePanel`**：右侧依据面板

### SSE 鉴权变更

- **阶段 1**：引入 SSE Ticket（短期方案），创建工作流时返回 `stream_ticket`
- **阶段 3**：中期改用 `fetch` + `ReadableStream`（Fetch Stream 方案），通过 Header 传递 `Authorization: Bearer ${accessToken}` + `Last-Event-ID: ${lastEventId}`

### 视觉与可访问性变更

- **保留现有视觉基线**：米白背景 + 深墨绿主色 + 灰绿色辅助色 + 低饱和金色强调
- **新增语义色变量** + 状态不只靠颜色 + SVG 图标规范 + 无障碍验收

## Impact

- **Affected specs**：
  - `workflow-stage-pause-user-participation`：阶段暂停将统一为 `WorkflowIntervention`，旧 `StagePausePanel` 合并为 `InterventionPanel`，`stage_gate_node` 改为 LangGraph HITL 规范
  - `add-t1-product-closure`：产物展示升级为 `WorkflowArtifact` + `ArtifactCard`
  - `add-image-ocr-dynamic-generation`：OCR 节点需升级为 `NodeResult` 输出 + `RetryPolicy`
  - `add-physical-evidence-support`：物证视觉摘要纳入 `EvidenceSourceViewer`
  - `extend-scenario-generalization`：场景扩展依赖 `WorkflowRun` 多运行历史

- **Affected code（后端）**：
  - `backend/api/models.py`：新增 3 个模型 + `Case` 扩展 + `ExtractedField` 扩展 + `ComplaintTemplate` 扩展
  - `backend/api/agents/state.py`：`CaseWorkflowState` 新增 10+ 字段，使用正确 reducer
  - `backend/api/agents/schemas.py`：新增 `NodeResult / QualityReport / Issue / Provenance / SnapshotSchema / WorkflowRunSchema / WorkflowArtifactSchema / WorkflowInterventionSchema / AllowedActionsSchema`
  - `backend/api/agents/nodes/*.py`：8 个节点统一返回 partial update dict 含 `node_result` 键
  - `backend/api/agents/graph.py`：新增版本字段注入 + `RetryPolicy` 配置 + 子图 checkpointer 作用域
  - `backend/api/agents/sse_event_depot.py`：表结构新增 `run_id / revision / occurred_at`
  - `backend/api/agents/sse_event_mapper.py`：新增 `stage.* / artifact.* / intervention.* / issue.*` 事件类型
  - `backend/api/agents/workflow_runner.py`：resume 改用 `Command(resume=...)`，注入 `run_id / revision`
  - `backend/api/services/`：新增 `snapshot_service.py / intervention_service.py / retry_service.py / sse_ticket_service.py / quality_gate_service.py / document_quality_service.py`
  - `backend/api/services/case_lifecycle_service.py`：扩展支持 `WorkflowRun` 状态转换
  - `backend/api/views.py`：新增 `/workflow-runs/*` 端点（7 个）
  - `backend/api/urls.py`：新增路由
  - `backend/api/agents/stage_gate_node.py`：迁移为质量门 + 介入创建（幂等副作用）
  - `backend/api/agents/nodes/review_node.py`：HITL 规范化（`interrupt()` 在幂等副作用后）
  - `backend/api/agents/version.py`：新增 `WorkflowVersion` 常量 + state migration 函数

- **Affected code（前端）**：
  - `frontend/src/types/workflow.ts`：新增 10+ 类型定义
  - `frontend/src/lib/workflow-events.ts`：升级 `SSEEvent` + 新增事件类型枚举
  - `frontend/src/lib/api.ts`：新增 6 个方法
  - `frontend/src/lib/sse-client.ts`：升级为支持 `run_id / revision` 检查 + Fetch Stream
  - `frontend/src/stores/case-store.ts`：拆分为 3 个 store
  - `frontend/src/components/workflow/`：新增 18 个组件
  - `frontend/src/pages/WorkspacePage.tsx`：升级为新布局
  - `frontend/src/index.css`：新增语义色变量

- **数据库迁移**：
  - 新增 3 张表：`workflow_runs / workflow_artifacts / workflow_interventions`
  - `sse_event_depot` 表新增 3 列：`run_id / revision / occurred_at`
  - `case` 表新增 1 列：`active_workflow_run_id`
  - `extracted_fields` 表新增 2 列：`user_confirmed / confirmed_at`
  - `complaint_templates` 表新增 1 列：`paragraphs`
  - 新增 `document_versions` 表

## ADDED Requirements

### Requirement: LangGraph State Schema with Reducers

系统 SHALL 在 `CaseWorkflowState` 中为所有累积列表字段使用 `Annotated[list, operator.add]` reducer，标量字段使用默认覆盖，集合字段使用自定义去重 reducer 或 `Overwrite` 替换，节点返回 partial update dict 而非 mutate 整个 state。

#### Scenario: Node returns partial update with NodeResult

- **WHEN** OCR 节点完成证据识别
- **THEN** 节点返回 `{"evidence_ocr_results": [...], "node_result": {...}, "revision": new_rev}` partial update dict
- **AND** `evidence_ocr_results` 通过 reducer 追加到现有列表，不覆盖
- **AND** `revision` 通过默认覆盖更新为最新值

#### Scenario: List field uses Overwrite on intervention submit

- **WHEN** 用户提交介入修正 `evidence_extract_results` 字段
- **THEN** 系统使用 `graph.update_state(config, {"evidence_extract_results": Overwrite([...])})` 替换整个列表
- **AND** 不使用直接传 list（会被 reducer 追加导致数据重复）

### Requirement: LangGraph HITL Pattern

系统 SHALL 严格遵循 LangGraph HITL 模式：`review_node` 与 `stage_gate_node` 在 `interrupt()` 前的副作用必须幂等（使用 `update_or_create`），`interrupt()` 在所有幂等副作用之后调用，resume 必须使用 `Command(resume=...)` 而非普通 dict。

#### Scenario: Idempotent side effect before interrupt

- **WHEN** `review_node` 检测到低置信度字段准备中断
- **THEN** 节点先使用 `WorkflowIntervention.objects.update_or_create(workflow_run=run, intervention_type="quality_review", stage="fact_review", defaults={...})` 幂等创建介入记录
- **AND** 然后调用 `interrupt(interrupt_payload)` 暂停
- **AND** resume 时节点从头执行，`update_or_create` 不会创建重复记录

#### Scenario: Resume uses Command(resume=...)

- **WHEN** 用户提交介入修正
- **THEN** `WorkflowRunner.resume()` 调用 `graph.invoke(Command(resume=resume_value), config)`
- **AND** 不调用 `graph.invoke({"resume_data": ...}, config)`（会导致 graph 从头重启）

#### Scenario: Interrupt payload JSON serializable

- **WHEN** 节点调用 `interrupt(value)`
- **THEN** value 必须是 JSON 可序列化的 dict / list / str / number / bool / None
- **AND** 不传入 Django Model 实例、datetime（需 ISO 8601 字符串）、自定义类

### Requirement: LangGraph Checkpointer per WorkflowRun

系统 SHALL 为每个 `WorkflowRun` 分配独立的 `thread_id`（格式 `case-{case_id}-run-{run_id}`），使用 `PostgresSaver` 持久化，`checkpointer.setup()` 仅在首次部署时执行一次。

#### Scenario: New run gets new thread_id

- **WHEN** 用户对案件 #42 发起新的工作流运行
- **THEN** 系统创建 `WorkflowRun` 记录，`thread_id = "case-42-run-{run_id}"`
- **AND** `graph.invoke(input, {"configurable": {"thread_id": "case-42-run-106"}})` 使用此 thread_id
- **AND** 旧运行的 thread_id 不被覆盖，保留历史

#### Scenario: PostgresSaver setup runs once

- **WHEN** 系统首次部署
- **THEN** `PostgresSaver.from_conn_string(DATABASE_URL).setup()` 执行一次创建所需表
- **AND** 后续应用启动不重复执行 setup

### Requirement: LangGraph RetryPolicy for Transient Errors

系统 SHALL 使用 LangGraph 原生 `RetryPolicy` 处理瞬时错误（网络超时、限流），不在节点内部手动实现重试循环。

#### Scenario: LLM call fails with rate limit

- **WHEN** LLM 调用返回 429 Rate Limit
- **THEN** LangGraph `RetryPolicy(max_attempts=3, initial_interval=1.0, backoff="exponential_jitter")` 自动重试
- **AND** 节点内部不实现 `for i in range(3): try: ...` 重试循环
- **AND** 重试耗尽后错误向上抛出，由 graph 错误处理逻辑接管

#### Scenario: User-fixable error uses interrupt

- **WHEN** 抽取节点检测到字段置信度不足
- **THEN** 节点调用 `interrupt()` 暂停 graph，不抛异常
- **AND** 抛异常会终止整个 graph，违反 HITL 设计

### Requirement: LangGraph Time Travel for Partial Retry

系统 SHALL 使用 LangGraph `get_state_history` + `update_state` + `Overwrite` 实现 `RetryService` 局部重跑，而非手动重新构建 state。

#### Scenario: Retry from evidence chain stage

- **WHEN** 用户请求 `POST /api/workflow-runs/106/retry/` 含 `{from_stage: "evidence_reasoning", preserve_user_confirmed: true}`
- **THEN** `RetryService` 调用 `graph.get_state_history(config)` 找到 `evidence_chain` 节点完成后的 checkpoint
- **AND** 使用 `graph.update_state(past.config, fork_state)` fork 新分支（列表字段用 `Overwrite`）
- **AND** 创建新 `WorkflowRun` 记录 fork 出的运行
- **AND** 使用 `graph.invoke(None, fork_config)` 从 fork 点恢复执行
- **AND** 下游产物自动标记为 `stale`

### Requirement: LangGraph State Schema Versioning & Migration

系统 SHALL 在 `state_schema_version` 变更时提供迁移策略，旧 checkpoint 不可加载时降级为保留产物 + 提示重新发起。

#### Scenario: State schema v1 to v2 migration

- **WHEN** 系统升级后 `state_schema_version` 从 1 变为 2
- **THEN** 恢复旧 checkpoint 时检测到版本不匹配
- **AND** 若可迁移：执行 `migrate_state_v1_to_v2(old_state) -> new_state` 转换
- **AND** 若不可迁移：保留旧 `WorkflowArtifact`，提示用户「此运行基于旧版本，建议重新发起」

### Requirement: LangGraph Subgraph Checkpointer Scoping

系统 SHALL 为子图明确配置 checkpointer 作用域：文书生成子图 `checkpointer=None`，RAG 检索子图 `checkpointer=False`，不使用 `checkpointer=True` 避免 namespace 冲突。

#### Scenario: Document generation subgraph uses None

- **WHEN** 文书生成节点内部调用子图且子图含 `interrupt()`
- **THEN** 子图编译时 `checkpointer=None`（默认）
- **AND** 子图可 pause/resume 但不跨调用记忆
- **AND** resume 时父节点和子图节点都会重新执行，副作用必须幂等

### Requirement: LangGraph Store for Cross-Run Memory

系统 SHALL 使用 `InMemoryStore` 或 `PostgresStore` 跨运行持久化用户偏好与案件模板，节点通过 `runtime.store` 访问。

#### Scenario: User preference persists across runs

- **WHEN** 用户在运行 #106 中选择「critical_only」介入策略偏好
- **THEN** 节点通过 `runtime.store.put(("user", user_id, "preferences"), "intervention_policy", {"value": "critical_only"})` 存储
- **AND** 运行 #107 启动时通过 `runtime.store.get(("user", user_id, "preferences"), "intervention_policy")` 读取
- **AND** graph 编译时配置 `store=store`：`builder.compile(checkpointer=checkpointer, store=store)`

### Requirement: Unified NodeResult Contract

系统 SHALL 为所有工作流节点提供统一的输出契约 `NodeResult`，含 `data / quality / warnings / errors / provenance / metrics` 六字段，每个节点的返回值必须包含此结构（作为 state 的 `node_result` 键，旧字段保留向后兼容）。

#### Scenario: Node outputs NodeResult with quality metrics

- **WHEN** OCR 节点完成证据识别
- **THEN** 节点返回 partial update dict `{"evidence_ocr_results": [...], "node_result": NodeResult(data=..., quality=..., provenance=..., metrics=...), "revision": new_rev}`
- **AND** 旧字段 `evidence_ocr_results` 同时保留在 state 中供下游节点消费

### Requirement: WorkflowRun Model

系统 SHALL 提供 `WorkflowRun` 模型作为独立的工作流运行实例，支持一个案件保留多次运行历史，每个运行拥有独立的 LangGraph `thread_id`。

#### Scenario: Create new workflow run

- **WHEN** 用户对案件 #42 发起工作流分析
- **THEN** 系统创建 `WorkflowRun` 记录，`thread_id` 唯一（格式 `case-42-run-{id}`），`status=queued`，版本字段记录当前版本
- **AND** `Case.active_workflow_run_id` 指向新创建的运行

#### Scenario: List historical runs

- **WHEN** 用户请求 `GET /api/cases/42/workflow-runs/`
- **THEN** 系统返回案件 #42 的所有历史运行列表，含每次运行的状态、阶段、进度、耗时、质量摘要

### Requirement: Unified Snapshot API

系统 SHALL 提供 `GET /api/workflow-runs/{run_id}/snapshot/` 端点返回权威快照，聚合运行状态 + 阶段 + 产物 + 介入 + 问题 + 允许操作。

#### Scenario: Fetch snapshot during running

- **WHEN** 工作流运行中，前端请求 `GET /api/workflow-runs/106/snapshot/`
- **THEN** 系统返回 `{run, stages, active_intervention, artifacts, issues, actions}`，其中 `actions` 含 `can_pause / can_resume / can_cancel / can_retry / can_restart_from_stage`

### Requirement: SSE Unified Envelope

系统 SHALL 为所有 SSE 事件提供统一信封，含 `event_id / event_type / run_id / thread_id / revision / occurred_at / payload` 字段。

#### Scenario: SSE event with revision

- **WHEN** 工作流节点完成并产生新产物
- **THEN** SSE 事件信封含 `run_id=106 / revision=12 / occurred_at="2026-07-17T10:03:20Z"`，前端可基于 `revision` 检测状态一致性

### Requirement: SSE Ticket Authentication

系统 SHALL 提供短期 SSE Ticket 替代 JWT query parameter 鉴权，Ticket 有效期 2-5 分钟，仅可读指定 `run_id`，连接建立后立即失效。

#### Scenario: Connect SSE with ticket

- **WHEN** 前端创建运行获得 `stream_ticket`
- **THEN** 前端使用 `GET /api/workflow-runs/106/events/?ticket={stream_ticket}` 连接 SSE
- **AND** Ticket 验证通过后立即失效，后续重连需重新获取
- **AND** 服务器日志只记录 Ticket 哈希，不记录明文

### Requirement: Unified Intervention Model

系统 SHALL 将低置信度审核和阶段暂停统一为 `WorkflowIntervention` 模型，使用 LangGraph `interrupt()` + `Command(resume=...)` 模式，前端通过统一 `InterventionPanel` 根据 `form_schema` 渲染。

#### Scenario: Low confidence triggers intervention

- **WHEN** 抽取节点检测到 3 项低置信度字段
- **THEN** 节点先使用 `update_or_create` 幂等创建 `WorkflowIntervention` 记录（`intervention_type=quality_review`）
- **AND** 然后调用 `interrupt(interrupt_payload)` 暂停 graph
- **AND** 工作流进入 `waiting_user` 状态，SSE 推送 `intervention.created` 事件

#### Scenario: Revision conflict on submit

- **WHEN** 用户基于 `base_revision=12` 提交介入，但当前 revision 已变为 13
- **THEN** 系统返回 `409 Conflict` + `{code: "REVISION_CONFLICT", detail: "阶段产物已被更新，请重新加载后再提交", current_revision: 13}`

### Requirement: Partial Retry via LangGraph Time Travel

系统 SHALL 支持从指定阶段局部重跑，使用 LangGraph `get_state_history` + `update_state` + `Overwrite` 实现，自动标记下游产物为 `stale`，默认保留用户已确认字段。

#### Scenario: Retry from evidence chain stage

- **WHEN** 用户请求 `POST /api/workflow-runs/106/retry/` 含 `{from_stage: "evidence_reasoning", preserve_user_confirmed: true}`
- **THEN** `RetryService` 使用 `graph.get_state_history(config)` 找到 `evidence_chain` 阶段的历史 checkpoint
- **AND** 使用 `graph.update_state(past.config, fork_state)` fork 新分支（列表字段用 `Overwrite`）
- **AND** 创建新 `WorkflowRun` 记录 fork 出的运行
- **AND** 下游产物（`document_draft`）自动标记为 `stale`
- **AND** 用户已确认的 `ExtractedField` 默认保留

### Requirement: Quality Gate

系统 SHALL 在每个业务阶段完成后执行质量门检查，输出质量评分和问题列表，质量不达标时使用 `interrupt()` 触发介入或阻塞。

#### Scenario: Quality gate blocks document generation

- **WHEN** 证据链阶段完成，但质量门检测到「无可引用证据」
- **THEN** 质量门返回 `status=blocked`，`blocking_issues=1`
- **AND** 节点调用 `interrupt()` 暂停 graph（不抛异常）
- **AND** 创建 `WorkflowIntervention`（`intervention_type=missing_information`，`reason="证据链为空，无法生成文书"`）

### Requirement: Business Stage Display

前端 SHALL 将 8 个技术节点聚合为 4 个业务阶段展示，普通用户只看到业务阶段，技术节点作为可展开详情。

#### Scenario: User views business stages

- **WHEN** 用户打开案件工作台
- **THEN** 显示 4 个业务阶段（材料理解 / 事实核对 / 案件组织 / 文书生成），每段含阶段名称 + 状态文本 + 质量分 + 问题数量 + 当前运行细进度
- **AND** 点击"查看处理详情"后展开技术节点、节点耗时、OCR 策略、工具调用、降级情况、质量评分、警告和错误

### Requirement: SSE Sync Rules

前端 SHALL 遵循四步 SSE 同步规则：检查 `run_id` → 检查 `event_id` 是否已处理 → 检查 `revision` → 轻量事件直接局部更新 / revision 跳跃或未知事件时重新获取 snapshot。

#### Scenario: Revision jump triggers snapshot refetch

- **WHEN** 前端收到 SSE 事件 `revision=15`，但本地 `snapshotRevision=12`
- **THEN** 前端检测到 revision 跳跃，调用 `GET /api/workflow-runs/106/snapshot/` 重新获取权威快照
- **AND** 本地状态完全替换为 snapshot 返回值

### Requirement: Store Split

前端 SHALL 将 Zustand store 拆分为三个 slice：`caseSlice`（案件信息 / 证据 / 时间线 / 文书）+ `workflowRunSlice`（当前运行快照 / 阶段状态 / 连接状态 / 事件游标 / actions）+ `interventionSlice`（当前介入任务 / 编辑草稿 / validation / revision）。

#### Scenario: Run switch destroys old connection

- **WHEN** 用户切换到另一个运行
- **THEN** 旧 SSE 连接被销毁，旧编辑草稿被清除，新运行的 snapshot 被获取

### Requirement: Legal Reference Authenticity Validation

系统 SHALL 在文书导出前通过 `LawRetriever` 验证所有 `paragraphs[].legal_references[]` 中的法条引用真实存在，未通过验证时阻塞导出并返回结构化问题列表。

#### Scenario: Invalid legal reference blocks export

- **WHEN** 用户请求 `POST /api/workflow-runs/106/documents/8/export-check/`，文书 `paragraphs[2].legal_references` 含 `{"law_name": "消费者权益保护法", "article_number": "第六十五条"}`
- **THEN** `document_quality_service` 查询 `law_data` 表确认 `(law_name="消费者权益保护法", article_number="第六十五条")` 真实存在
- **AND** 若不存在：返回 `{passed: false, issues: [{code: "INVALID_LEGAL_REFERENCE", severity: "blocking", paragraph_id: 2, ...}], missing_elements: [...]}`
- **AND** 前端在 `DocumentSourcePanel` 高亮问题段落并禁用「导出」按钮

#### Scenario: Quality gate integrated with legal validation

- **WHEN** `complaint_node` 完成文书生成
- **THEN** 节点后处理调用 `document_quality_service.validate_legal_references(paragraphs)` 计算结果
- **AND** 将结果（`True/False`）传入 `quality_gate_service.evaluate_document_generation(legal_references_valid=...)`，替换占位 `None`
- **AND** 若 `legal_references_valid=False` 且 `should_block_on_quality(quality)=True`，节点调用 `interrupt()` 暂停并创建 `WorkflowIntervention(intervention_type="legal_confirmation")`

### Requirement: Export Pre-check Quality Gate

系统 SHALL 提供 `POST /api/workflow-runs/{run_id}/documents/{document_id}/export-check/` 端点，返回 `{passed, issues, missing_elements}`，问题列表按 `severity`（blocking/warning/info）分级。

#### Scenario: Export check returns structured issues

- **WHEN** 文书导出前请求 `export-check`
- **THEN** 系统返回：
  ```json
  {
    "passed": false,
    "issues": [
      {
        "code": "AMOUNT_INCONSISTENT",
        "severity": "blocking",
        "message": "文书金额 2980 元与抽取金额 2960 元不一致",
        "paragraph_id": 3,
        "field_name": "amount"
      },
      {
        "code": "INVALID_LEGAL_REFERENCE",
        "severity": "blocking",
        "message": "引用的「合同法第一百五十三条」不存在",
        "paragraph_id": 5,
        "legal_reference": {"law_name": "合同法", "article_number": "第一百五十三条"}
      },
      {
        "code": "STALE_ARTIFACT_REFERENCED",
        "severity": "warning",
        "message": "文书引用了已过期的证据链产物",
        "artifact_id": 82
      }
    ],
    "missing_elements": ["fact_section", "claim_section"]
  }
  ```
- **AND** `passed=true` 当且仅当 `issues` 中无 `severity=blocking` 的项且 `missing_elements` 为空

### Requirement: DocumentEditor Dual-Pane Layout

前端 SHALL 提供 `DocumentEditor.tsx` 双栏布局：左侧文书正文（可编辑）+ 右侧 `DocumentSourcePanel`（引用证据 + 引用法条 + 风险提示 + 完整性检查）。

#### Scenario: User edits paragraph with source tracking

- **WHEN** 用户在左侧文书正文编辑段落 #3
- **THEN** 段落右侧实时展示该段引用的证据编号（`evidence_codes`）和法条（`legal_references`）
- **AND** 点击证据编号跳转到 `EvidenceSourceViewer` 对应证据
- **AND** 点击法条打开法条原文弹窗（通过 `LawRetriever` 反查或 `legal_references[].source_url`）
- **AND** AI 生成的段落使用浅米黄背景，用户修改的段落使用浅绿背景，通过 `DocumentVersion.created_by_type` 区分

#### Scenario: Auto-save with debounce

- **WHEN** 用户编辑文书正文
- **THEN** 1 秒 debounce 后自动调用 `POST /api/workflow-runs/{run_id}/documents/{document_id}/paragraphs/{paragraph_id}/regenerate/` 保存修改
- **AND** 创建新的 `DocumentVersion` 记录（`created_by_type="user"`）
- **AND** 版本历史抽屉显示所有版本，支持对比和回滚

#### Scenario: Confirm impact before full regeneration

- **WHEN** 用户点击「全文重新生成」
- **THEN** 弹出确认对话框，列出受影响的下游产物（`WorkflowArtifact.source_refs` 中依赖此文书的所有产物）
- **AND** 用户确认后调用 `POST /api/workflow-runs/{run_id}/retry/` 含 `from_stage="complaint"` 或 `from_stage="respond_complaint"`
- **AND** RetryService 通过 LangGraph Time Travel 标记下游产物为 `stale`，前端展示 `artifact.stale` 事件提示

### Requirement: LangGraph Store Node Access Pattern

系统 SHALL 通过 `runtime.store` 访问 `PostgresStore`（已编译注入），节点签名升级为 `def node(state, runtime: Runtime)` 模式，不直接引用 store 实例（对齐 `langgraph-persistence` skill）。

#### Scenario: User preference persists across runs

- **WHEN** 用户在运行 #106 中选择「critical_only」介入策略偏好
- **THEN** 运行结束节点通过 `runtime.store.put(("user", user_id, "preferences"), "intervention_policy", {"value": "critical_only"})` 存储
- **AND** 运行 #107 启动时通过 `runtime.store.get(("user", user_id, "preferences"), "intervention_policy")` 读取
- **AND** 节点签名升级为 `async def node(state, runtime: Runtime)`，旧 `def node(state)` / `def node(state, config)` 签名仍兼容（LangGraph 自动注入）

#### Scenario: Case template cache hit

- **WHEN** `complaint_node` 启动时查询 `runtime.store.get(("case", case_id, "templates"), "complaint_skeleton")`
- **THEN** 若命中缓存：跳过 LLM 模板生成步骤，直接使用缓存的 skeleton
- **AND** 若未命中：执行 LLM 调用生成 skeleton，完成后 `runtime.store.put(("case", case_id, "templates"), "complaint_skeleton", skeleton)` 写入缓存
- **AND** 缓存失效策略：案件类型变更或 `WorkflowVersion.PROMPT_BUNDLE_VERSION` 变更时清空对应 namespace

#### Scenario: Legal retrieval cache

- **WHEN** `evidence_chain_node` 调用 `LawRetriever.retrieve(query)` 前
- **THEN** 先查 `runtime.store.get(("case", case_id, "legal_cache"), hash(query))`
- **AND** 命中：直接使用缓存结果，跳过 BM25 + 向量检索 + Rerank
- **AND** 未命中：执行完整 RAG 流程，结果写入 Store（TTL 由 `legal_cache_ttl` 控制，默认 7 天）

### Requirement: State Schema Versioning & Migration

系统 SHALL 在 `state_schema_version` 变更时提供迁移策略，旧 checkpoint 不可加载时降级为保留产物 + 提示重新发起。

#### Scenario: Resume detects version mismatch

- **WHEN** `WorkflowRunner.resume()` 加载旧 checkpoint，发现 `state_schema_version=1` 而当前版本为 2
- **THEN** 尝试调用 `migrate_state_v1_to_v2(old_state) -> new_state` 迁移
- **AND** 若迁移成功：使用新 state 继续 resume
- **AND** 若迁移失败（`MigrationError`）：保留旧 `WorkflowArtifact` 记录为只读，返回提示「此运行基于旧版本，建议重新发起」，不抛异常
- **AND** 前端通过 SSE `issue.created` 事件展示提示

#### Scenario: Document version audit trail

- **WHEN** `DocumentVersion` 创建时记录 `workflow_version` 字段
- **THEN** 用户可在版本历史抽屉中查看每个版本生成时的工作流版本
- **AND** 审计需求满足：可追溯到具体 `workflow_version` + `prompt_bundle_version` + `policy_version`

## MODIFIED Requirements

### Requirement: Case Workflow Status

`Case.workflow_status` 枚举从 `idle / running / pausing / paused / waiting_review / succeeded / failed` 修改为 `idle / queued / running / pausing / waiting_user / succeeded / failed / cancelled`，`paused` 和 `waiting_review` 统一为 `waiting_user` + `intervention.kind`。

旧状态值在新 API 中映射：`paused → waiting_user`，`waiting_review → waiting_user`。旧 API 端点保留旧状态值兼容。

### Requirement: SSE Event Types

SSE 事件类型从技术节点级（`node.start / node.complete / complaint.token`）升级为业务阶段级（`stage.started / stage.completed / artifact.created / document.delta`），旧事件类型保留兼容映射。

### Requirement: Frontend Component Architecture

前端组件架构从单一 `workflow/` 目录升级为 18 个业务化组件，`NodeTrack` 重构为 `BusinessStageStepper`（保留 `NodeTrack` 兼容回退），`ReviewInterruptPanel` + `StagePausePanel` 合并为 `InterventionPanel`。

### Requirement: Frontend SSE Client

前端 SSE 客户端从 `EventSource` + JWT query parameter 升级为：
- 阶段 1：`EventSource` + SSE Ticket
- 阶段 3：`fetch` + `ReadableStream` + `Authorization` Header + `AbortController` + 心跳超时检测

### Requirement: WorkflowRunner Resume

`WorkflowRunner.resume()` 从普通 dict 输入修改为 `Command(resume=resume_value)` 输入，符合 LangGraph HITL 规范。

旧实现 `graph.invoke({"resume_data": ...}, config)` 会导致 graph 从头重启（stuck），新实现 `graph.invoke(Command(resume=...), config)` 正确恢复中断点。

## REMOVED Requirements

### Requirement: JWT Token in SSE URL

**Reason**：JWT token 通过 query parameter 传递存在安全风险（日志、浏览器历史、Referer 头泄露）
**Migration**：阶段 1 引入 SSE Ticket 替代，阶段 3 升级为 Fetch Stream + Header

### Requirement: Auto-scroll to Bottom in ProductStream

**Reason**：`ProductStream` 自动滚动到底部违反"流式内容不得强制抢夺用户滚动位置"原则
**Migration**：改为用户主动向上滚动后停止自动跟随 + 底部"回到最新内容"按钮

### Requirement: Fixed min-h-[600px] in Mobile

**Reason**：固定最小高度导致移动端布局溢出
**Migration**：移除固定高度，改为响应式布局

### Requirement: Manual Retry Loop in Nodes

**Reason**：节点内部手动实现重试循环（`for i in range(3): try: ...`）违反 LangGraph 错误处理规范，应使用 `RetryPolicy` 在 `add_node()` 时配置
**Migration**：移除节点内部重试逻辑，改用 `add_node(name, func, retry_policy=RetryPolicy(max_attempts=3))`
