# Tasks

## 阶段 0：LangGraph 架构对齐基础（1 周，与阶段 1 部分并行）

> 本阶段任务对齐 `langgraph-fundamentals` / `langgraph-human-in-the-loop` / `langgraph-persistence` 三个 skills，作为后续所有阶段的前置约束。

- [x] Task 0.1: State Schema Reducer 规范化（对齐 `langgraph-fundamentals`）
  - [x] SubTask 0.1.1: 审计 `backend/api/agents/state.py` 现有字段，确认累积列表字段使用 `Annotated[list, operator.add]`（`evidence_preclassify_results / evidence_ocr_results / evidence_classify_results / evidence_extract_results / evidence_chain / errors` 已正确）
  - [x] SubTask 0.1.2: 新增累积字段 `warnings / provenance / artifacts / interventions / issues / events` 使用 `Annotated[list, operator.add]` reducer
  - [x] SubTask 0.1.3: 新增标量字段 `revision / current_stage / current_node / progress / workflow_version / state_schema_version / policy_version / prompt_bundle_version` 使用默认覆盖（无 reducer）
  - [x] SubTask 0.1.4: 新增 `stale_artifact_ids` 使用自定义去重 reducer 或后续用 `Overwrite` 替换
  - [x] SubTask 0.1.5: 新增 `user_confirmed_fields` 使用自定义合并 reducer（按字段名 merge，不覆盖其他字段）
  - [x] SubTask 0.1.6: 新增 `node_result` 字段存储当前节点 `NodeResult` 输出（默认覆盖）
  - [x] SubTask 0.1.7: 编写单元测试验证 reducer 行为：列表追加、标量覆盖、`Overwrite` 替换

- [x] Task 0.2: WorkflowRunner Resume 修正（对齐 `langgraph-human-in-the-loop`）
  - [x] SubTask 0.2.1: 审计 `backend/api/agents/workflow_runner.py` 现有 resume 实现，确认是否使用普通 dict（错误模式）
  - [x] SubTask 0.2.2: 修改 `WorkflowRunner.resume()` 为 `graph.invoke(Command(resume=resume_value), config)` 模式
  - [x] SubTask 0.2.3: 修改 `resumePausedWorkflow` 同样使用 `Command(resume=...)`
  - [x] SubTask 0.2.4: 验证 resume 不再导致 graph 从头重启（stuck 问题）
  - [x] SubTask 0.2.5: 编写集成测试：interrupt → resume → 验证节点从中断点恢复而非从头执行

- [x] Task 0.3: HITL 节点副作用幂等化（对齐 `langgraph-human-in-the-loop`）
  - [x] SubTask 0.3.1: 审计 `backend/api/agents/nodes/review_node.py` 与 `stage_gate_node.py` 现有副作用，识别非幂等操作（如 `WorkflowIntervention.objects.create`）
  - [x] SubTask 0.3.2: 将 `create` 改为 `update_or_create`（按 `workflow_run + intervention_type + stage` 幂等）
  - [x] SubTask 0.3.3: 确认 `interrupt()` 调用在所有幂等副作用之后
  - [x] SubTask 0.3.4: 确认中断 payload 仅含 JSON 可序列化值（datetime 转 ISO 8601 字符串）
  - [x] SubTask 0.3.5: 编写测试：resume 时 `update_or_create` 不创建重复记录

- [x] Task 0.4: LangGraph RetryPolicy 配置（对齐 `langgraph-fundamentals`）
  - [x] SubTask 0.4.1: 审计 `backend/api/agents/graph.py` 现有 `add_node` 调用，识别哪些节点调用 LLM / OCR / Embedding API
  - [x] SubTask 0.4.2: 为调用外部 API 的节点在 `add_node()` 时配置 `retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0)`
  - [x] SubTask 0.4.3: 移除节点内部手动重试循环（`for i in range(3): try: ...` 模式）
  - [x] SubTask 0.4.4: 确认瞬时错误（网络、限流）由 RetryPolicy 自动处理，用户可修复错误由 `interrupt()` 处理，未预期错误向上抛出
  - [x] SubTask 0.4.5: 编写测试：模拟 429 限流，验证 RetryPolicy 自动重试 3 次后失败

- [x] Task 0.5: PostgresSaver 配置规范化（对齐 `langgraph-persistence`）
  - [x] SubTask 0.5.1: 确认 `backend/api/agents/graph.py` 使用 `PostgresSaver.from_conn_string(DATABASE_URL)` 而非 `InMemorySaver`
  - [x] SubTask 0.5.2: 确认 `checkpointer.setup()` 在首次部署时执行一次（不每次启动都执行）
  - [x] SubTask 0.5.3: 编写部署文档说明 setup 执行时机
  - [x] SubTask 0.5.4: 确认 `thread_id` 配置在 `{"configurable": {"thread_id": ...}}` 中传递

---

## 阶段 1：统一契约与体验修复（1-2 周）

### 后端任务

- [x] Task 1.1: 定义 `NodeResult` 统一输出结构
  - [x] SubTask 1.1.1: 在 `backend/api/agents/schemas.py` 新增 `NodeResult / QualityReport / Issue / Provenance / Warning / Metrics` Pydantic 模型
  - [x] SubTask 1.1.2: 在 `backend/api/agents/state.py` 扩展 `CaseWorkflowState`，新增 Task 0.1 中规划的版本与运行字段
  - [x] SubTask 1.1.3: 在 `backend/api/agents/version.py` 新增 `WorkflowVersion` 常量（`WORKFLOW_VERSION="v11" / STATE_SCHEMA_VERSION=1 / PROMPT_BUNDLE_VERSION="2026.07" / POLICY_VERSION="v1"`），由 `graph.py` 在 `build_case_workflow` 时注入到 initial state

- [x] Task 1.2: 8 个节点统一返回 `NodeResult` 兼容结构（partial update dict）
  - [x] SubTask 1.2.1: `preclassify_node.py` 返回 `{"evidence_preclassify_results": [...], "node_result": NodeResult(...), "revision": new_rev}`，保留旧字段
  - [x] SubTask 1.2.2: `ocr_node.py` 返回值新增 `quality`（OCR 成功率 + 覆盖率）+ `provenance`（图片区域 + OCR 策略）+ `metrics`（duration_ms + model_calls）
  - [x] SubTask 1.2.3: `classify_node.py` 返回值新增 `quality`（分类置信度分布）+ `provenance`（来源 evidence_id）
  - [x] SubTask 1.2.4: `extract_node.py` 返回值新增 `quality`（字段完整率 + 低置信度数量）+ `provenance`（字段来源 evidence_id + 区域）
  - [x] SubTask 1.2.5: `review_node.py` 返回 Command 时携带 `node_result` 字段（注意：Task 0.3 已修正副作用幂等性）
  - [x] SubTask 1.2.6: `evidence_chain_node.py` 返回值新增 `quality`（引用覆盖率 + 时间断点）+ `provenance`（每个节点的证据来源）
  - [x] SubTask 1.2.7: `complaint_node.py` 返回值新增 `quality`（法条验证 + 金额一致性）+ `provenance`（段落引用证据）
  - [x] SubTask 1.2.8: `respond_complaint_node.py` 同步 SubTask 1.2.7
  - [x] SubTask 1.2.9: 确认所有节点返回 partial update dict，不 mutate 整个 state

- [x] Task 1.3: 升级 SSE 事件信封
  - [x] SubTask 1.3.1: `backend/api/agents/sse_event_depot.py` 表结构新增 `run_id BIGINT NULL / revision INT NULL / occurred_at TIMESTAMPTZ NULL`（保留 `created_at` 兼容），新增迁移 SQL
  - [x] SubTask 1.3.2: `backend/api/agents/sse_event_mapper.py` 在 `SSEEvent` dataclass 新增 `run_id / revision / occurred_at` 字段，`map` 方法注入
  - [x] SubTask 1.3.3: `backend/api/views.py` 的 `_format_sse_event` 输出统一信封 `{event_id, event_type, run_id, thread_id, revision, occurred_at, payload}`
  - [x] SubTask 1.3.4: 新增事件类型枚举 `stage.started / stage.progress / stage.completed / stage.quality_changed / artifact.created / artifact.updated / artifact.stale / intervention.created / intervention.submitted / intervention.cancelled / document.delta / document.completed / issue.created / issue.resolved`，在 `sse_event_mapper.py` 加旧→新事件类型映射函数

- [x] Task 1.4: 引入 SSE Ticket 鉴权
  - [x] SubTask 1.4.1: 新建 `backend/api/services/sse_ticket_service.py`，实现 `issue_ticket(run_id, user_id) -> ticket_str` + `validate_ticket(ticket_str, run_id) -> bool` + `revoke_ticket(ticket_str)`，使用 Redis 或内存 dict（带 TTL 2-5 分钟），日志只记录 hash
  - [x] SubTask 1.4.2: `backend/api/views.py` 的 `CaseWorkflowStreamView` 接受 `?ticket=` 参数，验证通过后立即 revoke
  - [x] SubTask 1.4.3: 启动工作流的视图返回 `stream_ticket` 字段

- [x] Task 1.5: 工作流集成测试
  - [x] SubTask 1.5.1: 新建 `backend/api/tests/test_workflow_integration.py`，覆盖：完整启动 + 完成 + 失败、节点超时 + RetryPolicy 重试 + 降级、checkpoint 恢复、SSE 事件顺序、revision 单调递增
  - [x] SubTask 1.5.2: 新建 `backend/api/tests/test_sse_envelope.py`，验证事件信封含 `run_id / revision / occurred_at`
  - [x] SubTask 1.5.3: 新建 `backend/api/tests/test_hitl_resume.py`，验证 `Command(resume=...)` 正确恢复中断点（对齐 Task 0.2）

### 前端任务（可与后端并行）

- [x] Task 1.6: 新增类型定义
  - [x] SubTask 1.6.1: 新建 `frontend/src/types/workflow.ts`，定义 `WorkflowRun / WorkflowArtifact / WorkflowIntervention / WorkflowStage / WorkflowIssue / WorkflowAllowedActions / WorkflowRunSummary / WorkflowRunState / SnapshotSchema / NodeResult / QualityReport / Provenance / Warning / Issue`
  - [x] SubTask 1.6.2: 升级 `frontend/src/lib/workflow-events.ts` 的 `SSEEvent` 类型，新增 `run_id? / revision? / occurred_at?` 字段
  - [x] SubTask 1.6.3: 扩展 `frontend/src/types/case.ts` 的 `Case` 接口，新增 `active_workflow_run_id?` 字段

- [x] Task 1.7: 重构 `NodeTrack` 为 `BusinessStageStepper`
  - [x] SubTask 1.7.1: 新建 `frontend/src/components/workflow/BusinessStageStepper.tsx`，4 阶段横向轨道（材料理解 = preclassify+ocr+classify；事实核对 = extract+review；案件组织 = evidence_chain；文书生成 = complaint/respond_complaint），每段展示阶段名称 + 状态 + 质量分 + 问题数量 + 进度
  - [x] SubTask 1.7.2: 移动端断点（< 768px）只显示当前阶段，点击打开底部抽屉
  - [x] SubTask 1.7.3: 保留 `NodeTrack.tsx` 作为兼容回退（标记 `@deprecated`）

- [x] Task 1.8: 新增 `WorkflowCommandBar` + `CurrentActivityPanel`
  - [x] SubTask 1.8.1: 新建 `WorkflowCommandBar.tsx`，含运行编号 + 状态 + 总进度 + 当前阶段 + 连接状态 + 暂停/取消按钮 + 更多菜单
  - [x] SubTask 1.8.2: 新建 `CurrentActivityPanel.tsx`，展示当前正在做什么 + 最近完成的产物 + 需要用户注意的内容 + 文书流式生成

- [x] Task 1.9: 修复 `ProductStream` 自动滚动
  - [x] SubTask 1.9.1: `ProductStream.tsx` 移除 `bottomRef.current?.scrollIntoView` 自动滚动
  - [x] SubTask 1.9.2: 新增用户滚动方向检测，向上滚动后停止自动跟随
  - [x] SubTask 1.9.3: 底部新增"回到最新内容"按钮，点击后回到底部并恢复自动跟随

- [x] Task 1.10: 无障碍与移动端修复
  - [x] SubTask 1.10.1: 动态状态区域新增 `aria-live="polite"`，阻塞错误新增 `role="alert"`
  - [x] SubTask 1.10.2: 表单错误新增 `aria-describedby` 关联
  - [x] SubTask 1.10.3: 启动按钮新增 disabled 防重复 + 准备摘要
  - [x] SubTask 1.10.4: 移除 `min-h-[600px]` 固定高度，最小正文 14px，按钮最小高度 44px

- [x] Task 1.11: 升级 SSE 客户端同步规则
  - [x] SubTask 1.11.1: `frontend/src/lib/sse-client.ts` 的 `dispatch` 方法新增 `run_id` 检查（与当前 activeRunId 不符则丢弃）
  - [x] SubTask 1.11.2: 新增 `revision` 检查，revision 跳跃时调用 `getSnapshot()` 重新获取
  - [x] SubTask 1.11.3: `frontend/src/stores/case-store.ts` 的 `applySSEEvent` reducer 升级四步检查

---

## 阶段 2：统一用户介入与质量门（2-3 周）

### 后端任务

- [x] Task 2.1: 新增 `WorkflowIntervention` 模型 + 服务
  - [x] SubTask 2.1.1: `backend/api/models.py` 新增 `WorkflowIntervention` 模型（字段见 spec.md），执行 `makemigrations + migrate`
  - [x] SubTask 2.1.2: `backend/api/agents/schemas.py` 新增 `WorkflowInterventionSchema` Pydantic 序列化模型
  - [x] SubTask 2.1.3: 新建 `backend/api/services/intervention_service.py`，实现 `create_intervention`（使用 `update_or_create` 幂等）/ `submit_intervention` / `cancel_intervention` / `validate_revision_conflict`

- [x] Task 2.2: 统一 `review.interrupt` 和 `stage_pause`（HITL 规范化，依赖 Task 0.3）
  - [x] SubTask 2.2.1: `backend/api/agents/nodes/review_node.py` 改为创建 `WorkflowIntervention`（`intervention_type=quality_review`，使用 `update_or_create` 幂等），中断 payload 统一为 `{interrupt_type, intervention_id, intervention_kind, required, stage, reason, base_revision, form_schema, initial_values, impact}`
  - [x] SubTask 2.2.2: `backend/api/agents/nodes/stage_gate_node.py` 改为创建 `WorkflowIntervention`（`intervention_type=user_pause`），payload 同上
  - [x] SubTask 2.2.3: 确认 `interrupt()` 调用在 `update_or_create` 之后（Task 0.3 已验证幂等性）
  - [x] SubTask 2.2.4: `backend/api/agents/workflow_runner.py` 处理 `interrupt` 事件时路由到 `InterventionService.create_intervention`，resume 使用 `Command(resume=...)`（Task 0.2 已修正）

- [x] Task 2.3: 实现质量评分 + Issue 分级
  - [x] SubTask 2.3.1: 新建 `backend/api/services/quality_gate_service.py`，按设计文档 5.2 实现四阶段质量规则（材料理解 / 事实核对 / 案件组织 / 文书生成），返回 `QualityReport{score, coverage, status, blocking_issues}`
  - [x] SubTask 2.3.2: 节点返回的 `NodeResult.quality` 字段调用 `quality_gate_service` 计算
  - [x] SubTask 2.3.3: 节点返回的 `NodeResult.warnings + errors` 统一为 `issues: list[Issue]`，含 `code / message / severity (blocking/warning/info) / evidence_id / stage / recoverable`
  - [x] SubTask 2.3.4: 质量门阻塞时使用 `interrupt()` 暂停 graph（不抛异常，对齐 Task 0.4 错误处理策略）

- [x] Task 2.4: revision 冲突检测 + 用户确认字段 + `Overwrite` 使用
  - [x] SubTask 2.4.1: `InterventionService.submit_intervention` 校验 `base_revision != workflow_run.revision` 时抛 `RevisionConflictError`（占位：Task 3.1 前用 `Case.workflow_revision` 替代 `workflow_run.revision`）
  - [x] SubTask 2.4.2: `backend/api/views.py` 的介入提交端点捕获 `RevisionConflictError` 返回 `409 Conflict` + `{code: "REVISION_CONFLICT", detail, current_revision}`（占位端点 `POST /api/cases/<id>/interventions/<id>/submit/`，Task 3.2 迁移到 `/workflow-runs/{run_id}/...`）
  - [x] SubTask 2.4.3: `backend/api/models.py` 的 `ExtractedField` 新增 `user_confirmed: BooleanField(default=False) + confirmed_at: DateTimeField(null=True)`，执行 `makemigrations + migrate`
  - [x] SubTask 2.4.4: `extract_node.py` 创建字段时设 `user_confirmed=False`；`review_node.py` resume 时标记用户修正字段为 `user_confirmed=True, confirmed_at=now`，并追加 `user_confirmed_fields` 到 state（merge_dict reducer）
  - [x] SubTask 2.4.5: 在 `intervention_service.py` 顶部 docstring 文档化 `Overwrite` 使用模式（占位：实际 `graph.update_state(config, {"evidence_extract_results": Overwrite([...])})` 调用留待 Task 3.2/3.3 引入 `WorkflowRun` + graph 实例后落地，对齐 `langgraph-persistence` skill，不直接传 list 避免 reducer 追加）

### 前端任务

- [x] Task 2.5: 合并 `ReviewInterruptPanel` + `StagePausePanel` 为 `InterventionPanel`
  - [x] SubTask 2.5.1: 新建 `frontend/src/components/workflow/InterventionPanel.tsx`，根据 `form_schema` 动态渲染表单字段
  - [x] SubTask 2.5.2: 新建 `frontend/src/components/workflow/InterventionField.tsx`，单字段编辑（原值展示 + 修正值输入 + 来源证据跳转 + 错误提示 + 恢复原值）
  - [x] SubTask 2.5.3: 标记 `ReviewInterruptPanel.tsx` + `StagePausePanel.tsx` 为 `@deprecated`，新组件作为默认
  - [x] SubTask 2.5.4: 介入面板出现时焦点移动到面板标题，支持 Escape 关闭 + 焦点锁定

- [x] Task 2.6: 新增 `EvidenceSourceViewer` + 质量组件
  - [x] SubTask 2.6.1: 新建 `EvidenceSourceViewer.tsx`，支持图片证据（原图 + 缩放旋转 + OCR 文本区域框选 + 点击字段跳转来源区域 + 物证视觉摘要）和文本证据（OCR 原文 + 纠错后文本 + 差异对照）
  - [x] SubTask 2.6.2: 新建 `QualitySummary.tsx`，展示完整度 + 可信度 + 风险
  - [x] SubTask 2.6.3: 新建 `QualityBadge.tsx`，三档业务标签（高可信 / 建议核对 / 必须确认）
  - [x] SubTask 2.6.4: 新建 `IssueList.tsx` + `IssueCard.tsx`，按阻塞 / 警告 / 提示分组展示

- [x] Task 2.7: 草稿持久化
  - [x] SubTask 2.7.1: `frontend/src/stores/intervention-store.ts`（新 slice）的编辑草稿使用 `sessionStorage`，key 包含 `runId + interventionId + revision`
  - [x] SubTask 2.7.2: run 切换时销毁旧草稿

---

## 阶段 3：运行实例与局部重跑（3-4 周）

### 后端任务

- [x] Task 3.1: 新增 `WorkflowRun` + `WorkflowArtifact` 模型
  - [x] SubTask 3.1.1: `backend/api/models.py` 新增 `WorkflowRun` 模型（字段见 spec.md），`thread_id` 格式 `case-{case_id}-run-{run_id}`，`makemigrations + migrate`
  - [x] SubTask 3.1.2: `backend/api/models.py` 新增 `WorkflowArtifact` 模型，`makemigrations + migrate`
  - [x] SubTask 3.1.3: `Case` 模型新增 `active_workflow_run_id` 外键（保留旧 `thread_id / workflow_status` 双写兼容）
  - [x] SubTask 3.1.4: 新建 `backend/api/agents/artifact_service.py`，在节点完成后创建 `WorkflowArtifact` 记录，记录 `source_refs` 上游依赖
  - [x] 扩展：重构 `WorkflowIntervention.case` → `workflow_run` FK（Task 2.1/2.4 遗留 TODO，unique_together 迁移 + case 兼容回退 + 索引）
  - [x] 扩展：启用 `WorkflowRun.revision` 冲突检测（`intervention_service.submit_intervention` 优先读取 `workflow_run.revision`，回退 `case.workflow_revision`）

- [x] Task 3.2: 新增 `/workflow-runs/*` API 端点
  - [x] SubTask 3.2.1: `POST /api/cases/{case_id}/workflow-runs/`（创建运行，返回 `run_id / thread_id / status / stream_ticket / stream_url`）
  - [x] SubTask 3.2.2: `GET /api/workflow-runs/{run_id}/snapshot/`（聚合 run + stages + active_intervention + artifacts + issues + actions）
  - [x] SubTask 3.2.3: `POST /api/workflow-runs/{run_id}/pause/`
  - [x] SubTask 3.2.4: `POST /api/workflow-runs/{run_id}/interventions/{intervention_id}/submit/`（含 409 冲突响应）
  - [x] SubTask 3.2.5: `POST /api/workflow-runs/{run_id}/retry/`（局部重跑）
  - [x] SubTask 3.2.6: `POST /api/workflow-runs/{run_id}/cancel/`
  - [x] SubTask 3.2.7: `GET /api/cases/{case_id}/workflow-runs/`（历史运行列表）

- [x] Task 3.3: 新增 `SnapshotService` + `RetryService`（基于 LangGraph Time Travel）
  - [x] SubTask 3.3.1: 新建 `backend/api/services/snapshot_service.py`，聚合 `WorkflowRun + WorkflowArtifact + WorkflowIntervention + issues + actions`，计算 `actions`（`can_pause / can_resume / can_cancel / can_retry / can_restart_from_stage`）
  - [x] SubTask 3.3.2: 新建 `backend/api/services/retry_service.py`，使用 LangGraph Time Travel 实现：
    - 调用 `graph.get_state_history(config)` 找到 `from_stage` 对应的历史 checkpoint
    - 使用 `graph.update_state(past.config, fork_state)` fork 新分支（列表字段用 `Overwrite` 避免 reducer 追加）
    - 创建新 `WorkflowRun` 记录 fork 出的运行
    - 使用 `graph.invoke(None, fork_config)` 从 fork 点恢复执行
    - 自动标记下游产物为 `stale`
  - [x] SubTask 3.3.3: 产物依赖关系：`WorkflowArtifact.source_refs` 上游变更时自动传播 `stale` 状态，SSE 推送 `artifact.stale` 事件
  - [x] SubTask 3.3.4: 编写测试：验证 `get_state_history` 正确找到目标 checkpoint，`update_state` + `Overwrite` 正确 fork，`invoke(None, fork_config)` 正确恢复

- [x] Task 3.4: `case_lifecycle_service` 扩展 + 状态机统一 + 子图 checkpointer 作用域
  - [x] SubTask 3.4.1: `case_lifecycle_service.py` 新增 `WorkflowRun` 状态转换函数：`start_run / pause_run / resume_run / complete_run / fail_run / cancel_run`
  - [x] SubTask 3.4.2: `Case.workflow_status` 枚举统一为 `idle / queued / running / pausing / waiting_user / succeeded / failed / cancelled`，旧值映射函数（`paused → waiting_user`，`waiting_review → waiting_user`），旧 API 保留旧值
  - [x] SubTask 3.4.3: 配置子图 checkpointer 作用域（对齐 `langgraph-persistence`）：
    - 文书生成子图：`checkpointer=None`（默认，需 interrupt 但无跨调用记忆）
    - RAG 检索子图：`checkpointer=False`（无 interrupt，最简）
    - 不使用 `checkpointer=True` 避免 namespace 冲突

### 前端任务

- [x] Task 3.5: Zustand store 拆分为三 slice
  - [x] SubTask 3.5.1: 新建 `frontend/src/stores/workflow-run-store.ts`（`WorkflowRunState`：run / stages / artifacts / activeIntervention / issues / actions / connection / latestEventId / snapshotRevision）
  - [x] SubTask 3.5.2: 新建 `frontend/src/stores/intervention-store.ts`（当前介入 / 编辑草稿 / validation / revision）
  - [x] SubTask 3.5.3: 现有 `case-store.ts` 精简为 `caseSlice`（案件信息 / 证据 / 时间线 / 文书）
  - [x] SubTask 3.5.4: 新建 `frontend/src/lib/workflow-event-reducer.ts` 纯函数，SSE 事件先经过 reducer，revision 不连续时返回 `{needsSnapshotRefetch: true}`

- [x] Task 3.6: 新增运行相关组件
  - [x] SubTask 3.6.1: 新建 `RunHistoryDrawer.tsx`，历史运行列表 + 版本对比
  - [x] SubTask 3.6.2: 新建 `RunConfigurationDrawer.tsx`，启动配置（基础模式 + 高级设置）
  - [x] SubTask 3.6.3: 新建 `ArtifactTimeline.tsx` + `ArtifactCard.tsx`，统一产物卡片（标题 + 状态版本 + 业务摘要 + 关键指标 + 主体内容 + 来源依据 + 操作区）
  - [x] SubTask 3.6.4: 新建 `WorkflowRecoveryPanel.tsx`，错误恢复中心（重试 / 跳过 / 手动补录 / 重新上传 / 查看技术详情）
  - [x] SubTask 3.6.5: 过期产物提示：`artifact.stale` 事件触发 UI 提示

- [x] Task 3.7: `api.ts` 扩展 + Fetch Stream
  - [x] SubTask 3.7.1: `frontend/src/lib/api.ts` 新增 `createRun / getSnapshot / submitIntervention / retry / cancelRun / listRuns` 方法
  - [x] SubTask 3.7.2: 升级 `frontend/src/lib/sse-client.ts` 为 `fetch` + `ReadableStream` + `Authorization` Header + `AbortController` + 心跳超时检测
  - [x] SubTask 3.7.3: 保留 `EventSource` 兼容回退（旧浏览器）

---

## 阶段 4：专业文书工作台（3-5 周）

### 后端任务

- [x] Task 4.1: 段落级证据引用 + 文书版本
  - [x] SubTask 4.1.1: `ComplaintTemplate` 新增 `paragraphs: JSONField`（每段含 `content / evidence_codes / legal_references / source_regions`），`makemigrations + migrate`
  - [x] SubTask 4.1.2: 新增 `DocumentVersion` 模型（`document / version / content / changelog / created_by_type (user/ai) / created_by_id / created_at / workflow_version`），`makemigrations + migrate`
  - [x] SubTask 4.1.3: `complaint_node.py` 升级输出 `paragraphs` 字段，每段含证据引用
  - [x] SubTask 4.1.4: 新建 `POST /api/workflow-runs/{run_id}/documents/{document_id}/paragraphs/{paragraph_id}/regenerate/`（局部段落重新生成）

- [x] Task 4.2: 法律引用一致性校验 + 导出前质量门（对齐设计文档 5.2 + 5.3 + 16）
  - [x] SubTask 4.2.1: 新建 `backend/api/services/document_quality_service.py`，实现 `validate_legal_references(paragraphs) -> ValidationResult`：
    - 通过 `LawRetriever`（已存在于 `rag_service.py`）或直接查询 `law_data` 表验证 `paragraphs[].legal_references[]` 中的 `(law_name, article_number)` 真实存在
    - 返回 `{valid: bool, invalid_refs: [...], by_paragraph: {...}}`
  - [x] SubTask 4.2.2: 实现 `run_export_check(document_id) -> ExportCheckResult`，检查项含：
    - 法条引用真实性（调用 SubTask 4.2.1）
    - 文书金额与 `ExtractedField` 中 `field_name="amount"` 一致性
    - 主体名称一致性（投诉人/被投诉人 vs `ExtractedField.subject`）
    - 必备要素完整性（事实段 / 依据段 / 诉求段识别，使用 `paragraph_splitter`）
    - 是否引用 `stale` 状态的下游产物（查询 `WorkflowArtifact.source_refs`）
    - 返回 `{passed, issues: [{code, severity, message, paragraph_id, ...}], missing_elements: [...]}`
  - [x] SubTask 4.2.3: `complaint_node.py` / `respond_complaint_node.py` 后处理接入：
    - 调用 `validate_legal_references` 计算结果
    - 将 `True/False` 传入 `quality_gate_service.evaluate_document_generation(legal_references_valid=...)`，替换占位 `None`
    - 若 `should_block_on_quality(quality)=True`：节点调用 `interrupt()` 暂停并创建 `WorkflowIntervention(intervention_type="legal_confirmation")`，payload 含 `{invalid_refs, suggested_alternatives}`
  - [x] SubTask 4.2.4: 新建 `POST /api/workflow-runs/{run_id}/documents/{document_id}/export-check/` 端点（在 `views.py` 注册 `DocumentExportCheckView`）：
    - 调用 `document_quality_service.run_export_check(document_id)`
    - 返回 `{passed, issues, missing_elements}`
    - 404 若 `document_id` 不属于 `run_id`
  - [x] SubTask 4.2.5: 编写测试 `backend/api/tests/test_document_quality_service.py`：
    - 法条存在 / 不存在两种场景
    - 金额一致 / 不一致两种场景
    - 主体一致 / 不一致两种场景
    - 必备要素缺失场景
    - 引用 stale 产物场景
    - `should_block_on_quality=True` 时 `interrupt()` 触发测试

### 前端任务

- [x] Task 4.3: `DocumentEditor` + `DocumentSourcePanel`（对齐设计文档 16）
  - [x] SubTask 4.3.1: 新建 `frontend/src/components/workflow/DocumentEditor.tsx`，双栏布局（左文书正文 + 右依据与质量），桌面端 ≥1280px 双栏，平板 768-1279px 右栏可收起，移动端 <768px 上下堆叠
  - [x] SubTask 4.3.2: 实现自动保存（debounce 1s）：
    - 编辑段落时 debounce 1s 后调用 `POST /api/workflow-runs/{run_id}/documents/{document_id}/paragraphs/{paragraph_id}/regenerate/`
    - 创建新 `DocumentVersion`（`created_by_type="user"`）
    - 顶部展示「保存中」/「已保存」状态指示
  - [x] SubTask 4.3.3: 实现版本历史抽屉（`VersionHistoryDrawer.tsx`）：
    - 列出所有 `DocumentVersion`，含 `version / created_by_type / created_at / workflow_version`
    - 支持版本对比（diff 视图）
    - 支持回滚到指定版本（创建新版本，内容为旧版本）
  - [x] SubTask 4.3.4: 实现段落级证据引用展示：
    - 每段右侧浮动显示 `evidence_codes`（点击跳转 `EvidenceSourceViewer`）
    - 每段右侧浮动显示 `legal_references`（点击打开法条原文弹窗，调用 `LawRetriever.retrieve` 或直接访问 `legal_references[].source_url`）
  - [x] SubTask 4.3.5: 实现重新生成选中段落（右键菜单或段落操作按钮）：
    - 调用 regenerate API
    - 流式展示生成中状态
    - 生成完成后创建新 `DocumentVersion`（`created_by_type="ai"`）
  - [x] SubTask 4.3.6: 标记 AI 生成和用户修改内容：
    - AI 生成段落使用浅米黄背景（`bg-amber-50/60`）
    - 用户修改段落使用浅绿背景（`bg-emerald-50/60`）
    - 通过 `DocumentVersion.created_by_type` 区分
    - 段落右上角展示「AI」或「用户」标签
  - [x] SubTask 4.3.7: 全文重新生成前确认影响：
    - 弹出确认对话框，列出受影响下游产物（查询 `WorkflowArtifact.source_refs` 中依赖此文书的产物）
    - 用户确认后调用 `POST /api/workflow-runs/{run_id}/retry/` 含 `{from_stage: "complaint"|"respond_complaint", preserve_user_confirmed: false}`
    - RetryService 通过 LangGraph Time Travel 标记下游产物为 `stale`
    - 前端展示 `artifact.stale` SSE 事件提示
  - [x] SubTask 4.3.8: 新建 `frontend/src/components/workflow/DocumentSourcePanel.tsx`，右侧依据面板：
    - 引用证据列表（按段分组，点击跳转）
    - 引用法条列表（点击查看原文）
    - 风险提示（来自 `quality_gate_service` 的 `issues` 中 `severity=warning/blocking`）
    - 完整性检查（事实 / 依据 / 诉求三段是否齐全，调用 `export-check` API）
    - 导出按钮（`passed=true` 时启用，`passed=false` 时禁用并展示阻塞原因）
  - [x] SubTask 4.3.9: 流式生成行为（对齐设计文档 16.1）：
    - 正文逐段写入（SSE `document.delta` 事件）
    - 用户主动向上滚动后停止自动跟随
    - 底部显示「回到最新内容」按钮
    - 不强制滚动到页面底部
  - [x] SubTask 4.3.10: 新建 `frontend/src/lib/document-api.ts`（或扩展 `api.ts`）：
    - `getDocument(runId, documentId)` / `regenerateParagraph(...)` / `exportCheck(runId, documentId)` / `listDocumentVersions(documentId)` / `rollbackDocumentVersion(...)`

---

## 阶段 5：LangGraph Store 跨运行记忆 + State 版本化（2-3 周）

### 后端任务

- [x] Task 5.1: 引入 LangGraph Store 节点访问（对齐 `langgraph-persistence` skill）
  > **前提**：`PostgresStore` 已在 `backend/api/agents/graph.py` 的 `_get_store()` 初始化并通过 `g.compile(checkpointer=..., store=_get_store())` 传入编译图；本任务**不新增 store 实例**，仅升级节点签名以访问 `runtime.store`。
  - [x] SubTask 5.1.1: 在 `backend/api/agents/graph.py` 模块顶部 import `Runtime`：`from langgraph.runtime import Runtime`
  - [x] SubTask 5.1.2: 升级 `complaint_node.py` / `respond_complaint_node.py` 签名为 `async def node(state, runtime: Runtime)`：
    - 启动时先查 `runtime.store.get(("case", case_id, "templates"), "complaint_skeleton")`
    - 命中：跳过 LLM 模板生成步骤
    - 未命中：执行 LLM 调用，完成后 `runtime.store.put(("case", case_id, "templates"), "complaint_skeleton", skeleton)` 写入缓存
    - 缓存失效：案件类型变更或 `WorkflowVersion.PROMPT_BUNDLE_VERSION` 变更时清空对应 namespace（通过 `runtime.store.delete(...)`）
  - [x] SubTask 5.1.3: 升级 `evidence_chain_node.py` 签名为 `async def node(state, runtime: Runtime)`：
    - 调用 `LawRetriever.retrieve(query)` 前先查 `runtime.store.get(("case", case_id, "legal_cache"), hash(query))`
    - 命中：直接使用缓存结果
    - 未命中：执行完整 RAG 流程，结果写入 Store（namespace key 含查询 hash + case_id，TTL 通过 metadata `expires_at` 控制，默认 7 天）
  - [x] SubTask 5.1.4: 新建 `backend/api/services/user_preference_service.py`：
    - `save_user_preference(user_id, key, value)`：`runtime.store.put(("user", user_id, "preferences"), key, {"value": value})`
    - `get_user_preference(user_id, key)`：`runtime.store.get(("user", user_id, "preferences"), key)`
    - 在 `review_node.py` / `stage_gate_node.py` resume 时记录用户的介入策略选择（如「critical_only」）
    - 在 `WorkflowRunner.run_and_persist` 启动时读取用户偏好注入到 `run_options`
  - [x] SubTask 5.1.5: 编写测试 `backend/api/tests/test_store_cross_run.py`：
    - 运行 #106 写入用户偏好 → 运行 #107 读取
    - 案件模板缓存命中场景（跳过 LLM 调用）
    - 法律检索缓存命中场景（跳过 RAG）
    - 缓存失效场景（`PROMPT_BUNDLE_VERSION` 变更后清空）

- [x] Task 5.2: State Schema 版本化与迁移（对齐 `langgraph-persistence` skill）
  - [x] SubTask 5.2.1: 在 `backend/api/agents/version.py` 新增 `migrate_state_v1_to_v2(old_state: dict) -> dict` 迁移函数（预留，当前 `STATE_SCHEMA_VERSION=1`，函数体返回 `old_state` 不变）
  - [x] SubTask 5.2.2: 在 `backend/api/agents/version.py` 新增 `MIGRATION_REGISTRY: dict[int, Callable]` 注册表 + `migrate_state(old_state, from_version, to_version) -> dict` 入口函数，支持链式迁移（v1→v2→v3...）
  - [x] SubTask 5.2.3: 在 `backend/api/agents/workflow_runner.py` 的 `resume()` 方法中：
    - 加载 checkpoint 后检查 `state["state_schema_version"]` 与当前 `STATE_SCHEMA_VERSION` 是否一致
    - 不一致时调用 `migrate_state(old_state, from_version, to_version)`
    - 迁移成功：使用新 state 继续 resume
    - 迁移失败（`MigrationError`）：保留旧 `WorkflowArtifact` 记录为只读（添加 `WorkflowArtifact.metadata.readonly=True`），返回提示「此运行基于旧版本，建议重新发起」
  - [x] SubTask 5.2.4: 新建 `MigrationError` 异常类（在 `backend/api/agents/version.py`）
  - [x] SubTask 5.2.5: `DocumentVersion` 已记录 `workflow_version` 字段（Task 4.1 完成），前端版本历史抽屉展示（Task 4.3.3 完成）
  - [x] SubTask 5.2.6: 编写测试 `backend/api/tests/test_state_migration.py`：
    - v1→v2 迁移成功场景
    - v1→v3 链式迁移场景（v1→v2→v3）
    - 迁移失败场景（`MigrationError`）：保留旧产物 + 返回提示
    - 不可迁移场景：`state_schema_version > STATE_SCHEMA_VERSION`（来自未来版本）

---

## 阶段 6：测试与可观测性（贯穿所有阶段）

- [x] Task 6.1: 后端集成测试
  - [x] SubTask 6.1.1: 覆盖完整工作流启动 + 完成 + 失败
  - [x] SubTask 6.1.2: 覆盖节点超时 + RetryPolicy 重试 + 降级 + 阻塞
  - [x] SubTask 6.1.3: 覆盖用户暂停 + 低置信度审核 + 统一介入（含 `update_or_create` 幂等验证）
  - [x] SubTask 6.1.4: 覆盖 checkpoint 恢复 + 服务重启后恢复
  - [x] SubTask 6.1.5: 覆盖 `Command(resume=...)` 正确恢复中断点（不从头执行）
  - [x] SubTask 6.1.6: 覆盖 revision 冲突 + 409 响应
  - [x] SubTask 6.1.7: 覆盖 SSE 事件顺序 + 断线续传
  - [x] SubTask 6.1.8: 覆盖局部重跑（LangGraph Time Travel）+ 产物 stale 传播 + `Overwrite` 使用
  - [x] SubTask 6.1.9: 覆盖工作流版本不兼容处理（state schema migration）
  - [x] SubTask 6.1.10: 覆盖 Store 跨运行持久化
  - [x] SubTask 6.1.11: 覆盖法条验证失败时文书质量门阻塞

- [x] Task 6.2: 前端测试
  - [x] SubTask 6.2.1: 覆盖四阶段状态映射
  - [x] SubTask 6.2.2: 覆盖 Snapshot 初始化 + SSE 增量更新
  - [x] SubTask 6.2.3: 覆盖 revision 跳跃后重新获取 Snapshot
  - [x] SubTask 6.2.4: 覆盖重连和 fatal error
  - [x] SubTask 6.2.5: 覆盖用户介入草稿恢复 + 409 冲突提示
  - [x] SubTask 6.2.6: 覆盖流式文书停止自动跟随
  - [x] SubTask 6.2.7: 覆盖移动端布局 + 键盘操作 + ARIA live + reduced motion

- [x] Task 6.3: 端到端测试场景
  - [x] SubTask 6.3.1: 普通投诉完整流程
  - [x] SubTask 6.3.2: 商家反证完整流程
  - [x] SubTask 6.3.3: 含纯物证图片的流程
  - [x] SubTask 6.3.4: 低置信度字段人工修正（验证 resume 不重复创建介入记录）
  - [x] SubTask 6.3.5: 用户主动暂停并编辑
  - [x] SubTask 6.3.6: 暂停后刷新并恢复
  - [x] SubTask 6.3.7: SSE 中断并重连
  - [x] SubTask 6.3.8: OCR 单证据失败后降级（验证 RetryPolicy 触发）
  - [x] SubTask 6.3.9: 文书生成失败后阶段重试（验证 LangGraph Time Travel）
  - [x] SubTask 6.3.10: 修改上游字段后局部重算（验证 `Overwrite` 替换列表字段）
  - [x] SubTask 6.3.11: 移动端完成人工确认
  - [x] SubTask 6.3.12: 并发编辑 revision 冲突

# Task Dependencies

## 阶段 0 是所有后续阶段的前置
- Task 0.1 (State Schema Reducer) 是 Task 1.1 / 1.2 / 2.x / 3.x / 5.2 的前置
- Task 0.2 (WorkflowRunner Resume 修正) 是 Task 1.5.3 / 2.2 / 6.1.5 的前置
- Task 0.3 (HITL 副作用幂等化) 是 Task 2.1 / 2.2 的前置
- Task 0.4 (RetryPolicy 配置) 是 Task 1.5.1 / 6.1.2 / 6.3.8 的前置
- Task 0.5 (PostgresSaver 规范化) 是 Task 3.1 / 3.3 的前置

## 阶段内依赖
- Task 1.2 (节点统一返回 NodeResult) 依赖 Task 1.1 (NodeResult 结构定义) + Task 0.1 (State Reducer)
- Task 1.3 (SSE 信封升级) 依赖 Task 1.1 (state 新增 revision 等字段)
- Task 1.4 (SSE Ticket) 独立可并行
- Task 1.5 (集成测试) 依赖 Task 1.1 + 1.2 + 1.3 + Task 0.2 / 0.4
- 前端 Task 1.6-1.11 可与后端 Task 1.1-1.5 并行
- Task 2.x 依赖 Task 1.x 完成（NodeResult + SSE 信封）+ Task 0.3（HITL 幂等）
- Task 2.4 (revision 冲突) 依赖 Task 2.1 (WorkflowIntervention 模型)
- Task 3.1 (WorkflowRun 模型) 依赖 Task 2.1 (WorkflowIntervention 模型) + Task 0.5 (PostgresSaver)
- Task 3.2 (新 API) 依赖 Task 3.1 + 3.3
- Task 3.3 (SnapshotService + RetryService) 依赖 Task 3.1 + Task 0.5 (PostgresSaver)
- 前端 Task 3.5 (store 拆分) 依赖 Task 3.2 (新 API)
- Task 4.x 依赖 Task 3.x 完成（WorkflowRun + WorkflowArtifact）
- Task 5.x 依赖 Task 3.x 完成（WorkflowRun）
- Task 6.x 贯穿所有阶段，每个阶段完成后补充对应测试
