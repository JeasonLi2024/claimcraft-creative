# 工作流升级：新旧路径接入评估与分步计划

> 文档状态：评估结论 + 建议计划
> 关联设计：`docs/workflow-fullstack-upgrade-design.md`
> 结论日期：2026-07-18
> 目的：说明"最新代码相对设计文档的真实落地程度"，并给出低风险的接入路线。

---

## 1. 结论概要

`workflow-fullstack-upgrade` 的**后端**领域模型、统一接口、质量门、快照、局部重跑、
文书版本与段落级引用等能力基本齐全，方向与设计一致；本轮未提交改动进一步补齐了
`/events/` SSE 端点、文书详情 / 版本 / 回滚端点、以及"介入提交后 resume 工作流"的真实缺口。

**前端**存在关键落地缺口：整套新工作流 UI 与新状态层**已构建且有单元测试，但没有任何
路由 / 页面挂载它**，处于休眠（dead-code island）状态。应用实际仍运行在旧组件路径上。
`.trae/specs/.../checklist.md` 将条目标记为"全部完成"是**组件 / 单元级**完成，
并非**端到端接入**完成——两者不能等同。

---

## 2. 真实运行路径（mounted）

```
EvidencePage
  └─ WorkflowStreamPanel（旧）
       ├─ NodeTrack（旧，@deprecated）
       └─ ProductStream（旧）
            ├─ ReviewInterruptPanel（旧，@deprecated）
            └─ StagePausePanel（旧，@deprecated）
  状态层：stores/case-store.ts（旧）+ lib/sse-client 的 WorkflowSSEClient
  API：lib/api.ts 的 workflowApi（旧 /cases/<id>/workflow/* 端点）
```

要点：
- `NodeTrack` 里对 `BusinessStageStepper`、旧面板里对 `InterventionPanel` 的引用
  **仅存在于 `@deprecated` 注释**，不是真实渲染。
- 因此 case-store 中大量 `@deprecated` 字段虽指向新 store，但**旧 case-store 仍是唯一被挂载使用的状态层**——不能删除。

## 3. 休眠未接入部分（orphaned）

彼此互相引用、但无页面挂载：

| 分类 | 组件 / 模块 |
|---|---|
| 指挥与阶段 | `WorkflowCommandBar`、`BusinessStageStepper`、`CurrentActivityPanel`、`StageSummaryCard` |
| 产物与质量 | `ArtifactTimeline`、`ArtifactCard`、`QualitySummary`、`QualityBadge`、`IssueList`、`IssueCard` |
| 用户介入 | `InterventionPanel`、`InterventionField`、`EvidenceSourceViewer` |
| 运行管理 | `RunHistoryDrawer`、`RunConfigurationDrawer`、`WorkflowRecoveryPanel` |
| 文书工作台 | `DocumentEditor`、`DocumentSourcePanel`、`VersionHistoryDrawer`、`RegenerateConfirmDialog`、`LegalReferenceModal` |
| 状态层 | `stores/workflow-run-store.ts`、`stores/intervention-store.ts`、`lib/workflow-event-reducer.ts` |
| API 客户端 | `lib/api.ts` 的 `workflowRunApi`、`lib/document-api.ts` 的 `documentApi` |

## 4. 后端就绪度（供接入调用）

- `POST /api/cases/{case_id}/workflow-runs/`、`GET .../snapshot/`、`.../pause/`、
  `.../interventions/{id}/submit/`、`.../retry/`、`.../cancel/`、运行历史列表：均已实现。
- `GET /api/workflow-runs/{run_id}/events/`（票据鉴权 SSE）：本轮补齐。
- 文书：`GET .../documents/{id}/`、`.../versions/`、`.../versions/{v}/rollback/`、
  段落 `regenerate`、`export-check`：均已实现（本轮补齐详情/版本/回滚）。
- 结论：后端接口面基本齐备，前端接入主要是"把休眠 UI 接到这些接口 + 新 store"。

## 5. 接入前需消除的风险

1. **无端到端验证**：新路径从未在真实浏览器 + 真实后端跑通，仅有单测。接入必须配合手动/E2E 验证。
2. **契约细节**：段落 `paragraph_id`↔`id` 已在 API 边界归一化（本轮修复）；仍需在接入时核对
   snapshot、artifact.payload、intervention form_schema 等真实返回结构与前端类型一致。
3. **双状态层并存**：接入期 case-store（旧）与 workflow-run-store（新）会短暂共存，
   需明确"谁是单一真相源"，避免双写与竞态。
4. **SSE 客户端切换**：旧 `WorkflowSSEClient`（EventSource + query token）与新
   `FetchStreamSSEClient`（fetch + Header + ticket）不能同时对同一 run 建两条连接。

## 6. 建议分步接入计划（低风险优先）

每步均可独立交付、独立回滚；旧路径保留为回退，直到新路径验证通过再摘除。

- **A. 只读接入（最低风险）**：在工作台/证据页新增一块"分析任务"只读区，
  用 `workflowRunApi.getSnapshot` + `workflow-run-store.applySnapshot` 驱动
  `BusinessStageStepper` + `QualitySummary` + `IssueList`。不改动现有启动/介入逻辑。
- **B. 实时接入**：接上 `/events/` + `FetchStreamSSEClient` + `workflow-event-reducer`，
  让只读区实时更新；验证 revision 跳跃触发 snapshot 重取。
- **C. 命令与介入接入**：挂载 `WorkflowCommandBar`（暂停/取消/重试）与
  `InterventionPanel`（替换 ProductStream 里的旧 Review/StagePause 面板），走新 submit→resume 链路。
- **D. 运行管理接入**：`RunConfigurationDrawer`（启动配置）+ `RunHistoryDrawer`（历史/对比）+ `WorkflowRecoveryPanel`。
- **E. 文书工作台接入**：以新路由或页签挂载 `DocumentEditor` + `DocumentSourcePanel`，
  接 `documentApi`（详情/段落重生/版本/回滚/导出检查）。
- **F. 收尾清理**：新路径全部验证通过后，移除 `WorkflowStreamPanel`、`NodeTrack`、
  `ReviewInterruptPanel`、`StagePausePanel`、旧 `workflowApi` 与 case-store 中的 `@deprecated` 工作流字段。

> 在到达 F 之前，不建议删除任何旧组件——它们是当前唯一在跑的实现。

## 7. 本轮已完成的修复与清理

- 删除 `case-store.ts` 中破损且未被使用的 `saveComplaint`（调用了不存在的
  `complaintApi.update`，无对应后端端点，无任何调用方；亦是唯一的 TS 类型错误）。
- 在文书接口边界统一段落契约：新增 `_serialize_paragraph`，令
  `WorkflowRunDocumentDetailView` 与段落 `regenerate` 响应输出 `id`（由 `paragraph_id` 派生），
  与前端 `Paragraph` / `DocumentEditor` 一致，消除接入后 `p.id === undefined` 的隐患。
- 更新 `document-api.ts` 过期注释（相关端点已实现，非"后端可能未实现"）。
- 打开真正的生产类型检查：`tsconfig.app.json` 排除测试文件，`build` 改为
  `tsc -p tsconfig.app.json && vite build`（原 `tsc` 因 `files:[]`+references 实为空检查，
  正是上述类型错误得以溜过的原因），并新增 `npm run typecheck`。验证 `src` 全量类型检查通过。

## 8. 接入实现（前后端双向对齐，已落地）

按「前后端双向对齐（含细粒度实时事件）」执行，新增独立路由页，旧路径完全保留。

**前端**
- 类型对齐：`InterventionType` 扩展为 4 值；`WorkflowArtifactKind` 增补 5 个后端产物类型；
  对应两处 `ARTIFACT_KIND_LABELS` 补全（ArtifactCard / CurrentActivityPanel）。
- `lib/workflow-adapters.ts`：`normalizeSnapshot` + 各实体归一化，把后端 snapshot 字段/枚举
  映射为前端形状（`finished_at→completed_at`、stage `name/label→key/name` + `quality.score→quality_score`、
  artifact `workflow_run_id/artifact_type/content→run_id/kind/payload`、status `current/superseded→active/archived`、
  intervention `workflow_run_id→run_id`）。
- `pages/WorkflowAnalysisPage.tsx` + 路由 `/cases/:caseId/analysis` + 侧栏「工作流分析」入口：
  listRuns→active→streamTicket+getSnapshot(归一化)→applySnapshot→SSE；挂载 CommandBar / Stepper /
  CurrentActivityPanel / QualitySummary / IssueList / InterventionPanel / ArtifactTimeline /
  RunConfigurationDrawer / RunHistoryDrawer / WorkflowRecoveryPanel。
- 文书工作台（step E）：从 snapshot 的文书产物（`complaint_draft` / `respond_complaint_draft`，
  content 含 `document_version_id` + `paragraphs`）定位文书，`documentApi.getDocument`（端点缺失时
  回退 artifact 构造）加载后挂载 `DocumentEditor`（含双栏来源面板 / 段落重生 / 版本历史 / 导出检查）。
- `WorkflowArtifactKind` 与两处标签表对齐后端真实 `artifact_type`
  （preclassify_result / ocr_result / classify_result / extract_result / evidence_chain /
  complaint_draft / respond_complaint_draft）；`document-api.artifactToDocument` 归一化段落 `paragraph_id→id`。
- SSE：`createSSEClient`（fetch+Authorization+票据）；`stage.*` 本地即时更新，其余结构性事件与
  revision 跳跃触发去抖 snapshot 重取（权威来源）；断线退避重连（重新签发票据）；
  介入提交 409→revisionConflict。
- `workflowRunApi.streamTicket`（新）。

**后端（追加式，不改旧事件）**
- `sse_event_mapper`：node.start/complete 追加发送 `stage.started/progress/completed`，
  携 stage/status/progress/quality_score/issue_count/revision（旧 EventSource 路径忽略未知类型）。
- 新增 `POST /api/workflow-runs/{run_id}/stream-ticket/` 为已存在运行签发一次性票据。

**验证状态**：前端 `tsc -p tsconfig.app.json` 0 错误、`vitest` 97/97 通过。
后端因本机无 Django 环境未跑，需在服务器执行下述清单。

### 服务器端验证清单
1. `python manage.py migrate`（含 0024 intervention_type）。
2. 后端测试：`pytest`（重点 `test_sse_envelope*` / `test_workflow_runs_api` / `test_snapshot_service`）。
3. E2E：进入 `/cases/{id}/analysis` → 开始分析 → 观察四阶段实时推进、质量/问题、
   低置信度介入面板提交→resume、暂停/取消、失败后恢复重试、运行历史切换、刷新后快照恢复。
4. 文书工作台：运行产出文书后，页面下方出现 DocumentEditor；验证段落来源跳转、
   段落重新生成、自动保存新版本、版本历史/回滚、导出前检查（passed 时启用导出）。
5. 确认旧路径 `/cases/{id}/evidence`（WorkflowStreamPanel）行为不变。
