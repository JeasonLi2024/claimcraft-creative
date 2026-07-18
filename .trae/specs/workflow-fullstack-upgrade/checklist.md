# Checklist

## 阶段 0：LangGraph 架构对齐基础

### State Schema Reducer 规范化（对齐 `langgraph-fundamentals`）
- [x] 现有累积列表字段（`evidence_preclassify_results / evidence_ocr_results / evidence_classify_results / evidence_extract_results / evidence_chain / errors`）使用 `Annotated[list, operator.add]` reducer
- [x] 新增累积字段（`warnings / provenance / artifacts / interventions / issues / events`）使用 `Annotated[list, operator.add]` reducer
- [x] 新增标量字段（`revision / current_stage / current_node / progress / workflow_version / state_schema_version / policy_version / prompt_bundle_version`）使用默认覆盖（无 reducer）
- [x] `stale_artifact_ids` 使用自定义去重 reducer 或后续用 `Overwrite` 替换
- [x] `user_confirmed_fields` 使用自定义合并 reducer（按字段名 merge，不覆盖其他字段）
- [x] `node_result` 字段存储当前节点 `NodeResult` 输出（默认覆盖）
- [x] 单元测试验证 reducer 行为：列表追加、标量覆盖、`Overwrite` 替换
- [x] 节点返回 partial update dict，不 mutate 整个 state

### WorkflowRunner Resume 修正（对齐 `langgraph-human-in-the-loop`）
- [x] `WorkflowRunner.resume()` 使用 `graph.invoke(Command(resume=resume_value), config)` 而非普通 dict
- [x] `resumePausedWorkflow` 同样使用 `Command(resume=...)`
- [x] resume 不再导致 graph 从头重启（stuck 问题修复）
- [x] 集成测试：interrupt → resume → 验证节点从中断点恢复而非从头执行

### HITL 节点副作用幂等化（对齐 `langgraph-human-in-the-loop`）
- [x] `review_node.py` 与 `stage_gate_node.py` 识别非幂等操作（如 `WorkflowIntervention.objects.create`）
- [x] `create` 改为 `update_or_create`（按 `workflow_run + intervention_type + stage` 幂等）
- [x] `interrupt()` 调用在所有幂等副作用之后
- [x] 中断 payload 仅含 JSON 可序列化值（datetime 转 ISO 8601 字符串）
- [x] 测试：resume 时 `update_or_create` 不创建重复记录

### LangGraph RetryPolicy 配置（对齐 `langgraph-fundamentals`）
- [x] 调用 LLM / OCR / Embedding API 的节点在 `add_node()` 时配置 `retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0)`
- [x] 节点内部手动重试循环（`for i in range(3): try: ...`）已移除
- [x] 瞬时错误（网络、限流）由 RetryPolicy 自动处理
- [x] 用户可修复错误由 `interrupt()` 处理（不抛异常）
- [x] 未预期错误向上抛出
- [x] 测试：模拟 429 限流，验证 RetryPolicy 自动重试 3 次后失败

### PostgresSaver 配置规范化（对齐 `langgraph-persistence`）
- [x] `graph.py` 使用 `PostgresSaver.from_conn_string(DATABASE_URL)` 而非 `InMemorySaver`
- [x] `checkpointer.setup()` 在首次部署时执行一次（不每次启动都执行）
- [x] 部署文档说明 setup 执行时机
- [x] `thread_id` 配置在 `{"configurable": {"thread_id": ...}}` 中传递

---

## 阶段 1：统一契约与体验修复

### 后端 - NodeResult 统一契约
- [x] `NodeResult / QualityReport / Issue / Provenance / Warning / Metrics` Pydantic 模型已在 `backend/api/agents/schemas.py` 定义
- [x] `CaseWorkflowState` 已新增 `revision / workflow_version / state_schema_version / policy_version / prompt_bundle_version / current_stage / current_node / progress / artifacts / interventions / stale_artifact_ids / node_result / user_confirmed_fields` 字段（对齐 Task 0.1 reducer 规则）
- [x] `errors` 字段已从 `list[str]` 升级为 `list[dict]`（含 code / message / severity / evidence_id），旧消费方兼容
- [x] `WorkflowVersion` 常量已在 `backend/api/agents/version.py` 定义，`graph.py` 在 `build_case_workflow` 时注入到 initial state
- [x] 8 个节点返回 partial update dict 含 `node_result: NodeResult` 键 + 旧字段保留
- [x] 旧字段（如 `evidence_ocr_results`）保留在 state 中供下游节点消费，未删除
- [x] 节点不 mutate 整个 state，仅返回 partial update dict

### 后端 - SSE 事件信封
- [x] `sse_event_depot` 表已新增 `run_id / revision / occurred_at` 列，迁移 SQL 已生成并执行
- [x] `SSEEvent` dataclass 已新增 `run_id / revision / occurred_at` 字段
- [x] `_format_sse_event` 输出统一信封 `{event_id, event_type, run_id, thread_id, revision, occurred_at, payload}`
- [x] 新增事件类型枚举 `stage.* / artifact.* / intervention.* / issue.*` 已在 `sse_event_mapper.py` 定义
- [x] 旧事件类型（`node.start / node.complete / complaint.token` 等）保留兼容映射函数

### 后端 - SSE Ticket
- [x] `sse_ticket_service.py` 已实现 `issue_ticket / validate_ticket / revoke_ticket`，TTL 2-5 分钟
- [x] `CaseWorkflowStreamView` 接受 `?ticket=` 参数，验证通过后立即 revoke
- [x] 启动工作流的视图返回 `stream_ticket` 字段
- [x] 日志只记录 Ticket 哈希，不记录明文
- [x] 现有 `/cases/<id>/workflow/*` 端点全部保留可访问

### 后端 - 集成测试
- [x] 完整工作流启动 + 完成 + 失败测试通过
- [x] 节点超时 + RetryPolicy 重试 + 降级测试通过（对齐 Task 0.4）
- [x] checkpoint 恢复测试通过
- [x] SSE 事件顺序测试通过
- [x] revision 单调递增测试通过
- [x] SSE 事件信封含 `run_id / revision / occurred_at` 测试通过
- [x] `Command(resume=...)` 正确恢复中断点测试通过（对齐 Task 0.2，新增）

### 前端 - 类型定义
- [x] `frontend/src/types/workflow.ts` 已定义 10+ 类型
- [x] `SSEEvent` 类型已新增 `run_id? / revision? / occurred_at?` 字段
- [x] `Case` 接口已新增 `active_workflow_run_id?` 字段

### 前端 - 业务阶段展示
- [x] `BusinessStageStepper.tsx` 已实现 4 阶段横向轨道
- [x] 移动端断点（< 768px）只显示当前阶段 + 底部抽屉
- [x] `NodeTrack.tsx` 保留为 `@deprecated` 兼容回退
- [ ] 点击"查看处理详情"可展开技术节点（Task 1.7.1 可选扩展，未实现）

### 前端 - 命令栏 + 活动面板
- [x] `WorkflowCommandBar.tsx` 含运行编号 + 状态 + 总进度 + 当前阶段 + 连接状态 + 暂停/取消 + 更多菜单
- [x] `CurrentActivityPanel.tsx` 展示当前正在做什么 + 最近产物 + 需要注意的内容 + 文书流式生成

### 前端 - 自动滚动修复
- [x] `ProductStream.tsx` 已移除自动 `scrollIntoView`
- [x] 用户向上滚动后停止自动跟随
- [x] 底部"回到最新内容"按钮已实现
- [x] 点击按钮回到底部并恢复自动跟随

### 前端 - 无障碍与移动端
- [x] 动态状态区域 `aria-live="polite"` 已添加
- [x] 阻塞错误 `role="alert"` 已添加
- [x] 表单错误 `aria-describedby` 关联已添加
- [x] 启动按钮 disabled 防重复 + 准备摘要已实现
- [x] `min-h-[600px]` 已移除
- [x] 最小正文 14px，按钮最小高度 44px

### 前端 - SSE 同步规则
- [x] `dispatch` 方法新增 `run_id` 检查（与 activeRunId 不符则丢弃）
- [x] 新增 `revision` 检查，revision 跳跃时调用 `getSnapshot()` 重新获取
- [x] `applySSEEvent` reducer 升级四步检查（run_id → event_id → revision → 局部更新 / 重新获取）

---

## 阶段 2：统一用户介入与质量门

### 后端 - WorkflowIntervention
- [x] `WorkflowIntervention` 模型已在 `models.py` 定义，`makemigrations + migrate` 成功
- [x] `WorkflowInterventionSchema` Pydantic 序列化模型已定义
- [x] `intervention_service.py` 已实现 `create_intervention`（使用 `update_or_create` 幂等，对齐 Task 0.3）/ `submit_intervention` / `cancel_intervention` / `validate_revision_conflict`

### 后端 - 统一中断（HITL 规范化）
- [x] `review_node.py` 改为创建 `WorkflowIntervention`（`intervention_type=quality_review`，使用 `update_or_create` 幂等），payload 统一
- [x] `stage_gate_node.py` 改为创建 `WorkflowIntervention`（`intervention_type=user_pause`），payload 统一
- [x] `interrupt()` 调用在 `update_or_create` 之后（对齐 Task 0.3 幂等性验证）
- [x] `workflow_runner.py` 处理 `interrupt` 事件时路由到 `InterventionService.create_intervention`
- [x] resume 使用 `Command(resume=...)`（对齐 Task 0.2）
- [x] 中断 payload 含 `interrupt_type / intervention_id / intervention_kind / required / stage / reason / base_revision / form_schema / initial_values / impact.stale_artifacts`
- [x] 中断 payload 仅含 JSON 可序列化值（datetime 转 ISO 8601 字符串，对齐 Task 0.3.4）

### 后端 - 质量评分 + Issue 分级
- [x] `quality_gate_service.py` 已实现四阶段质量规则（材料理解 / 事实核对 / 案件组织 / 文书生成）
- [x] 节点返回的 `NodeResult.quality` 字段调用 `quality_gate_service` 计算（服务已就绪，节点接入在 Task 2.2 完成）
- [x] `NodeResult.warnings + errors` 统一为 `issues: list[Issue]`，含 `code / message / severity / evidence_id / stage / recoverable`（已在 Task 1.2 完成节点侧）
- [x] 质量门阻塞时使用 `interrupt()` 暂停 graph（不抛异常，对齐 Task 0.4 错误处理策略）—— `should_block_on_quality` 返回 True 时由调用方节点 interrupt

### 后端 - revision 冲突 + 用户确认 + Overwrite 使用
- [x] `InterventionService.submit_intervention` 校验 `base_revision != workflow_run.revision` 时抛 `RevisionConflictError`（占位：Task 3.1 前用 `Case.workflow_revision` 替代）
- [x] 介入提交端点捕获 `RevisionConflictError` 返回 `409 Conflict` + `{code: "REVISION_CONFLICT", detail, current_revision}`（占位端点 `POST /api/cases/<id>/interventions/<id>/submit/`）
- [x] `ExtractedField` 新增 `user_confirmed / confirmed_at` 字段，`makemigrations + migrate` 成功（迁移 `0020_extractedfield_user_confirmed`）
- [x] `extract_node.py` 创建字段时设 `user_confirmed=False`；`review_node.py` resume 时标记用户修正字段为 `user_confirmed=True, confirmed_at=now`，并追加 `user_confirmed_fields` 到 state（merge_dict reducer 合并）
- [x] `intervention_service.py` 顶部 docstring 文档化 `Overwrite` 使用模式（占位：实际 `graph.update_state(config, {"evidence_extract_results": Overwrite([...])})` 调用留待 Task 3.2/3.3 引入 `WorkflowRun` + graph 实例后落地，对齐 `langgraph-persistence` skill）
- [x] 不直接传 list（会被 reducer 追加导致数据重复）—— 已在 docstring + `merge_dict` reducer 测试（测试 5b）中验证

### 前端 - InterventionPanel
- [x] `InterventionPanel.tsx` 已实现，根据 `form_schema` 动态渲染
- [x] `InterventionField.tsx` 含原值展示 + 修正值输入 + 来源证据跳转 + 错误提示 + 恢复原值
- [x] `ReviewInterruptPanel.tsx` + `StagePausePanel.tsx` 标记为 `@deprecated`
- [x] 介入面板出现时焦点移动到面板标题
- [x] 支持 Escape 关闭 + 焦点锁定

### 前端 - 来源阅读器 + 质量组件
- [x] `EvidenceSourceViewer.tsx` 支持图片证据（原图 + 缩放旋转 + OCR 区域框选 + 字段跳转 + 物证摘要）和文本证据（OCR 原文 + 纠错后 + 差异对照）
- [x] `QualitySummary.tsx` 展示完整度 + 可信度 + 风险
- [x] `QualityBadge.tsx` 三档业务标签（高可信 / 建议核对 / 必须确认）
- [x] `IssueList.tsx` + `IssueCard.tsx` 按阻塞 / 警告 / 提示分组

### 前端 - 草稿持久化
- [x] 编辑草稿使用 `sessionStorage`，key 含 `runId + interventionId + revision`
- [x] run 切换时销毁旧草稿

---

## 阶段 3：运行实例与局部重跑

### 后端 - WorkflowRun + WorkflowArtifact
- [x] `WorkflowRun` 模型已定义，`thread_id` 格式 `case-{case_id}-run-{run_id}`，`makemigrations + migrate` 成功
- [x] `WorkflowArtifact` 模型已定义，`makemigrations + migrate` 成功
- [x] `Case` 模型新增 `active_workflow_run_id` 外键，旧 `thread_id / workflow_status` 双写兼容
- [x] `artifact_service.py` 在节点完成后创建 `WorkflowArtifact` 记录，记录 `source_refs` 上游依赖
- [x] `WorkflowIntervention` 重构为 `workflow_run` FK（nullable）+ `case` FK nullable + `unique_together` 改为 `(workflow_run, type, stage, base_revision)`

### 后端 - /workflow-runs/* API
- [x] `POST /api/cases/{case_id}/workflow-runs/` 端点已实现，返回 `run_id / thread_id / status / stream_ticket / stream_url`
- [x] `GET /api/workflow-runs/{run_id}/snapshot/` 端点已实现，返回 `{run, stages, active_intervention, artifacts, issues, actions}`
- [x] `POST /api/workflow-runs/{run_id}/pause/` 端点已实现
- [x] `POST /api/workflow-runs/{run_id}/interventions/{intervention_id}/submit/` 端点已实现，含 409 冲突响应
- [x] `POST /api/workflow-runs/{run_id}/retry/` 端点已实现，支持 `from_stage + artifact_ids + preserve_user_confirmed`
- [x] `POST /api/workflow-runs/{run_id}/cancel/` 端点已实现
- [x] `GET /api/cases/{case_id}/workflow-runs/` 端点已实现，返回历史运行列表

### 后端 - SnapshotService + RetryService（基于 LangGraph Time Travel）
- [x] `snapshot_service.py` 已实现，聚合 `WorkflowRun + WorkflowArtifact + WorkflowIntervention + issues + actions`
- [x] `actions` 字段含 `can_pause / can_resume / can_cancel / can_retry / can_restart_from_stage`
- [x] `retry_service.py` 使用 LangGraph Time Travel 实现（对齐 `langgraph-persistence`）：
  - [x] 使用 `graph.get_state_history(config)` 找到 `from_stage` 对应的历史 checkpoint
  - [x] 使用 `graph.update_state(past.config, fork_state)` fork 新分支
  - [x] 列表字段使用 `Overwrite` 避免 reducer 追加（对齐 `langgraph-persistence` skill）
  - [x] 创建新 `WorkflowRun` 记录 fork 出的运行
  - [x] 使用 `graph.invoke(None, fork_config)` 从 fork 点恢复执行
  - [x] 自动标记下游产物为 `stale`
- [x] 产物依赖关系：`source_refs` 上游变更时自动传播 `stale` 状态（Python 层级依赖检查，SQLite 兼容）
- [x] SSE 推送 `artifact.stale` 事件
- [x] 测试：验证 `get_state_history` 正确找到目标 checkpoint，`update_state` + `Overwrite` 正确 fork，`invoke(None, fork_config)` 正确恢复（25 测试通过）

### 后端 - 状态机统一 + 子图 checkpointer 作用域
- [x] `case_lifecycle_service.py` 新增 7 个 `WorkflowRun` 状态转换函数
- [x] `Case.workflow_status` 旧值映射函数已实现（`map_workflow_status_to_legacy` / `map_legacy_status_to_new`），不修改字段 choices（避免迁移）
- [x] 旧 API 保留旧状态值兼容
- [x] 子图 checkpointer 作用域已在 `graph.py` 模块 docstring 文档化（对齐 `langgraph-persistence`）：
  - [x] 文书生成子图：`checkpointer=None`（默认，需 interrupt 但无跨调用记忆）
  - [x] RAG 检索子图：`checkpointer=False`（无 interrupt，最简）
  - [x] 不使用 `checkpointer=True` 避免 namespace 冲突
  - [x] 当前项目无子图，仅文档化策略，不引入未使用代码

### 前端 - Store 拆分
- [x] `workflow-run-store.ts` 已创建，含 `WorkflowRunState` 完整字段（含 `applySnapshot` / `applySSEEvent` / `reset` actions）
- [x] `intervention-store.ts` 已创建，含编辑草稿 / validation / revision
- [x] `case-store.ts` 精简为 `caseSlice`（案件信息 / 证据 / 时间线 / 文书）
- [x] `workflow-event-reducer.ts` 纯函数已创建，`checkSSEEvent` 返回 `{apply: 'process'|'skip'|'refetch_snapshot', reason}`

### 前端 - 运行相关组件
- [x] `RunHistoryDrawer.tsx` 已实现，含历史运行列表 + 版本对比
- [x] `RunConfigurationDrawer.tsx` 已实现，含基础模式 + 高级设置
- [x] `ArtifactTimeline.tsx` + `ArtifactCard.tsx` 已实现，统一产物卡片结构 + stale 全局警告条
- [x] `WorkflowRecoveryPanel.tsx` 已实现，含重试 / 跳过 / 手动补录 / 重新上传 / 查看技术详情
- [x] `artifact.stale` 事件触发 UI 提示已实现

### 前端 - api.ts + Fetch Stream
- [x] `api.ts` 新增 `workflowRunApi` 对象含 7 个方法（createRun / getSnapshot / pauseRun / submitIntervention / retryRun / cancelRun / listRuns）
- [x] `sse-client.ts` 升级为 `FetchStreamSSEClient`（fetch + ReadableStream + Authorization Header + AbortController + 心跳超时检测）
- [x] 保留 `EventSource` 兼容回退（`createSSEClient` 工厂函数）

---

## 阶段 4：专业文书工作台

### 后端 - 段落级引用 + 文书版本（Task 4.1 已完成，37 测试通过）
- [x] `ComplaintTemplate` / `RespondTemplate` 新增 `paragraphs: JSONField`，`makemigrations + migrate` 成功（迁移 0022）
- [x] `DocumentVersion` 模型已定义，含 `workflow_version` 字段，`makemigrations + migrate` 成功（迁移 0022）
- [x] `complaint_node.py` / `respond_complaint_node.py` 输出 `paragraphs` 字段，每段含 `evidence_codes / legal_references / source_regions`
- [x] `paragraph_splitter.py` 已实现（Markdown / 中文序号 / 阿拉伯数字 / 「第X条」标题识别）
- [x] `document_version_service.py` 已实现（`get_next_version` / `create_document_version` / `regenerate_paragraph`）
- [x] `POST /api/workflow-runs/{run_id}/documents/{document_id}/paragraphs/{paragraph_id}/regenerate/` 端点已实现（`DocumentParagraphRegenerateView`）
- [x] 测试 `test_document_version.py` 37 用例通过（7 个测试类）

### 后端 - 法律引用校验 + 导出前质量门（Task 4.2 已完成，18 测试通过）
- [x] `document_quality_service.py` 已实现 `validate_legal_references(paragraphs) -> ValidationResult`，调用 `LawRetriever` 或查询 `law_data` 表
- [x] `document_quality_service.py` 已实现 `run_export_check(document_id) -> ExportCheckResult`，含 5 项检查（法条真实性 / 金额一致性 / 主体一致性 / 必备要素完整性 / stale 产物引用）
- [x] `complaint_node.py` / `respond_complaint_node.py` 后处理调用 `validate_legal_references`，结果传入 `quality_gate_service.evaluate_document_generation(legal_references_valid=...)`，替换占位 `None`
- [x] `should_block_on_quality(quality)=True` 时节点调用 `interrupt()` 暂停并创建 `WorkflowIntervention(intervention_type="legal_confirmation")`
- [x] `POST /api/workflow-runs/{run_id}/documents/{document_id}/export-check/` 端点已实现（`DocumentExportCheckView`）
- [x] 端点返回 `{passed, issues, missing_elements}`，问题按 `severity`（blocking/warning/info）分级
- [x] 404 响应当 `document_id` 不属于 `run_id`
- [x] 测试 `test_document_quality_service.py` 覆盖 6 种场景（法条存在/不存在 / 金额一致/不一致 / 主体一致/不一致 / 必备要素缺失 / stale 产物 / `interrupt()` 触发）

### 前端 - DocumentEditor + DocumentSourcePanel（Task 4.3 已完成）
- [x] `DocumentEditor.tsx` 双栏布局已实现（桌面端 ≥1280px 双栏 / 平板 768-1279px 右栏可收起 / 移动端 <768px 上下堆叠）
- [x] 自动保存（debounce 1s）已实现，调用 regenerate API 创建新 `DocumentVersion`（`created_by_type="user"`）
- [x] 顶部「保存中」/「已保存」状态指示已实现
- [x] `VersionHistoryDrawer.tsx` 已实现，列出所有版本（含 `workflow_version`）+ 版本对比（diff 视图）+ 回滚
- [x] 段落级证据引用展示已实现（点击 `evidence_codes` 跳转 `EvidenceSourceViewer`，点击 `legal_references` 打开法条原文弹窗）
- [x] 重新生成选中段落已实现（右键菜单或段落操作按钮，调用 regenerate API）
- [x] 标记 AI 生成（浅米黄 `bg-amber-50/60`）和用户修改（浅绿 `bg-emerald-50/60`）内容已实现，段落右上角展示「AI」/「用户」标签
- [x] 全文重新生成前确认影响弹窗已实现（列出 `WorkflowArtifact.source_refs` 依赖此文书的所有产物）
- [x] 用户确认后调用 `POST /api/workflow-runs/{run_id}/retry/` 含 `{from_stage: "complaint"|"respond_complaint", preserve_user_confirmed: false}`
- [x] RetryService 通过 LangGraph Time Travel 标记下游产物为 `stale`，前端展示 `artifact.stale` SSE 事件提示
- [x] `DocumentSourcePanel.tsx` 已实现，含引用证据列表 + 引用法条列表 + 风险提示 + 完整性检查 + 导出按钮
- [x] 导出按钮 `passed=true` 启用 / `passed=false` 禁用并展示阻塞原因
- [x] 流式生成行为：正文逐段写入（SSE `document.delta`）+ 用户向上滚动后停止自动跟随 + 底部「回到最新内容」按钮
- [x] `document-api.ts`（或 `api.ts` 扩展）已实现：`getDocument / regenerateParagraph / exportCheck / listDocumentVersions / rollbackDocumentVersion`

---

## 阶段 5：LangGraph Store 跨运行记忆 + State 版本化

### 后端 - LangGraph Store 节点访问（Task 5.1 已完成，对齐 `langgraph-persistence` skill）
> **前提**：`PostgresStore` 已在 `graph.py` 的 `_get_store()` 初始化并通过 `g.compile(checkpointer=..., store=_get_store())` 传入编译图；本任务不新增 store 实例。

- [x] `graph.py` 顶部 import `Runtime`：`from langgraph.runtime import Runtime`
- [x] `complaint_node.py` / `respond_complaint_node.py` 签名升级为 `async def node(state, runtime: Runtime)`：
  - [x] 启动时查 `runtime.store.get(("case", case_id, "templates"), "complaint_skeleton")`
  - [x] 命中：跳过 LLM 模板生成
  - [x] 未命中：执行 LLM 调用，完成后 `runtime.store.put(...)` 写入缓存
  - [x] 缓存失效：案件类型变更或 `PROMPT_BUNDLE_VERSION` 变更时 `runtime.store.delete(...)` 清空 namespace
- [x] `evidence_chain_node.py` 签名升级为 `async def node(state, runtime: Runtime)`：
  - [x] `LawRetriever.retrieve(query)` 前查 `runtime.store.get(("case", case_id, "legal_cache"), hash(query))`
  - [x] 命中：跳过 BM25 + 向量检索 + Rerank
  - [x] 未命中：执行完整 RAG 流程，结果写入 Store（TTL 通过 metadata `expires_at` 控制，默认 7 天）
- [x] `user_preference_service.py` 已创建（`save_user_preference` / `get_user_preference`）
- [x] `review_node.py` / `stage_gate_node.py` resume 时记录用户介入策略选择到 Store
- [x] `WorkflowRunner.run_and_persist` 启动时读取用户偏好注入 `run_options`
- [x] 测试 `test_store_cross_run.py` 覆盖：跨运行偏好持久化 / 模板缓存命中 / 法律缓存命中 / 缓存失效

### 后端 - State Schema 版本化与迁移（Task 5.2 已完成，对齐 `langgraph-persistence` skill）
- [x] `migrate_state_v1_to_v2(old_state) -> new_state` 迁移函数已预留（在 `version.py`，当前 `STATE_SCHEMA_VERSION=1`，函数体返回 `old_state` 不变）
- [x] `MIGRATION_REGISTRY: dict[int, Callable]` 注册表 + `migrate_state(old_state, from_version, to_version)` 入口函数已实现，支持链式迁移
- [x] `MigrationError` 异常类已定义（在 `version.py`）
- [x] `WorkflowRunner.resume()` 检查 `state["state_schema_version"]` 兼容性：
  - [x] 不一致时调用 `migrate_state(old_state, from_version, to_version)`
  - [x] 迁移成功：使用新 state 继续 resume
  - [x] 迁移失败：保留旧 `WorkflowArtifact` 为只读（`metadata.readonly=True`），返回提示「此运行基于旧版本，建议重新发起」
- [x] `DocumentVersion` 已记录 `workflow_version` 字段（Task 4.1 完成）
- [x] 前端版本历史抽屉展示 `workflow_version`（Task 4.3.3 完成）
- [x] 测试 `test_state_migration.py` 覆盖：v1→v2 迁移成功 / v1→v3 链式迁移 / 迁移失败保留产物 / 未来版本不可迁移

---

## 阶段 6：测试与可观测性

### 后端集成测试
- [x] 完整工作流启动 + 完成 + 失败测试通过
- [x] 节点超时 + RetryPolicy 重试 + 降级 + 阻塞测试通过
- [x] 用户暂停 + 低置信度审核 + 统一介入测试通过
- [x] `update_or_create` 幂等验证测试通过（resume 不创建重复介入记录）
- [x] checkpoint 恢复 + 服务重启后恢复测试通过
- [x] `Command(resume=...)` 正确恢复中断点测试通过（不从头执行）
- [x] revision 冲突 + 409 响应测试通过
- [x] SSE 事件顺序 + 断线续传测试通过
- [x] 局部重跑（LangGraph Time Travel）+ 产物 stale 传播测试通过
- [x] `Overwrite` 替换列表字段测试通过（不追加）
- [x] 工作流版本不兼容处理（state schema migration）测试通过
- [x] Store 跨运行持久化测试通过
- [x] 法条验证失败时文书质量门阻塞测试通过

### 前端测试
- [x] 四阶段状态映射测试通过
- [x] Snapshot 初始化测试通过
- [x] SSE 增量更新测试通过
- [x] revision 跳跃后重新获取 Snapshot 测试通过
- [x] 重连和 fatal error 测试通过
- [x] 用户介入草稿恢复 + 409 冲突提示测试通过
- [x] 流式文书停止自动跟随测试通过
- [x] 移动端布局测试通过
- [x] 键盘操作测试通过
- [x] ARIA live 与 alert 测试通过
- [x] reduced motion 适配测试通过

### 端到端测试场景
- [x] 普通投诉完整流程通过
- [x] 商家反证完整流程通过
- [x] 含纯物证图片的流程通过
- [x] 低置信度字段人工修正通过（验证 resume 不重复创建介入记录）
- [x] 用户主动暂停并编辑通过
- [x] 暂停后刷新并恢复通过
- [x] SSE 中断并重连通过
- [x] OCR 单证据失败后降级通过（验证 RetryPolicy 触发）
- [x] 文书生成失败后阶段重试通过（验证 LangGraph Time Travel）
- [x] 修改上游字段后局部重算通过（验证 `Overwrite` 替换列表字段）
- [x] 移动端完成人工确认通过
- [x] 并发编辑 revision 冲突通过

---

## 跨阶段验收

### LangGraph 最佳实践验收（对齐三个 skills）
- [x] State Schema 使用正确 reducer（累积列表 `Annotated[list, operator.add]`，标量默认覆盖）
- [x] 节点返回 partial update dict，不 mutate 整个 state
- [x] HITL 节点 `interrupt()` 前副作用幂等（`update_or_create`）
- [x] resume 使用 `Command(resume=...)` 而非普通 dict
- [x] 中断 payload JSON 可序列化
- [x] PostgresSaver 用于生产（不使用 InMemorySaver）
- [x] `checkpointer.setup()` 仅首次部署执行一次
- [x] 每个 `WorkflowRun` 拥有独立 `thread_id`（格式 `case-{case_id}-run-{run_id}`）
- [x] 局部重跑使用 `get_state_history` + `update_state` + `Overwrite`（Time Travel）
- [x] 列表字段替换使用 `Overwrite` 而非直接传 list
- [x] 瞬时错误使用 `RetryPolicy`（不在节点内部手动重试）
- [x] 用户可修复错误使用 `interrupt()`（不抛异常）
- [x] 未预期错误向上抛出
- [x] 子图 checkpointer 作用域明确（文书生成 None / RAG False / 不用 True）
- [x] Store 通过 `runtime.store` 访问（不直接引用）
- [x] Store 跨运行持久化（用户偏好、案件模板）
- [x] State schema 版本化与迁移策略已实现

### 安全验收
- [x] access token 不再出现在 SSE URL
- [x] SSE Ticket 有效期 2-5 分钟
- [x] SSE Ticket 仅可读指定 run_id
- [x] SSE Ticket 连接建立后立即失效
- [x] 日志只记录 Ticket 哈希

### 可访问性验收
- [x] 动态状态区域 `aria-live="polite"`
- [x] 阻塞错误 `role="alert"`
- [x] 人工介入出现后焦点移动到面板标题
- [x] 弹窗和抽屉支持 `Escape` 关闭与焦点锁定
- [x] 所有图标按钮具有 `aria-label`
- [x] 状态不能只靠颜色表达
- [x] 表单错误通过 `aria-describedby` 关联
- [x] 主要操作可通过键盘完成
- [x] 触控目标不小于 44 × 44px
- [x] 对比度满足 WCAG AA
- [x] 动画遵循 `prefers-reduced-motion`
- [x] 流式内容不自动抢夺屏幕阅读器焦点

### 兼容性验收
- [x] 现有 `/cases/<id>/workflow/*` 端点全部保留可访问
- [x] 旧 SSE 事件类型保留兼容映射
- [x] `Case` 旧字段（`thread_id / workflow_status`）双写兼容
- [x] 旧 `NodeTrack` 组件保留 `@deprecated` 回退
- [x] 旧 `ReviewInterruptPanel` + `StagePausePanel` 保留 `@deprecated` 回退
- [x] 旧 `EventSource` 客户端保留兼容回退

### 视觉验收
- [x] 保留米白背景 + 深墨绿主色 + 灰绿色辅助色 + 低饱和金色强调
- [x] 新增语义色变量已定义
- [x] 状态同时使用 SVG 图标 + 文本标签 + 边框样式
- [x] SVG 图标遵循 `fill="none" / stroke="currentColor" / strokeWidth="1.75"` 规范
- [x] 装饰图标 `aria-hidden="true"`
- [x] 独立图标按钮 `aria-label`
