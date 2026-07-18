# 工作流前后端重构 · 验证指导文档

> 目的：指导在服务器环境验证本次「新工作流 UI 接入 + 前后端契约对齐」重构运行正常，且旧路径不受影响。
> 关联：`docs/workflow-fullstack-upgrade-design.md`、`docs/workflow-ui-integration-assessment.md`
> 适用改动：新增 `/cases/:caseId/analysis` 分析页、契约适配层、后端追加式 `stage.*` 事件与 `stream-ticket` 端点、文书工作台接入。

---

## 0. 本次改动速览（验证对象）

后端（追加式，不改旧行为）
- `api/agents/sse_event_mapper.py`：node 生命周期追加发送 `stage.started / stage.progress / stage.completed`。
- `api/views.py` + `api/urls.py`：
  - 新增 `POST /api/workflow-runs/{run_id}/stream-ticket/`（为已存在运行签发一次性 SSE 票据）。
  - 新增 `GET /api/workflow-runs/{run_id}/events/`（票据鉴权 SSE 事件流）。
  - 新增文书端点：`GET .../documents/{document_id}/`、`.../versions/`、`.../versions/{version}/rollback/`。
  - 段落 `regenerate` 响应 `version` 改为数字；段落序列化补 `id`（由 `paragraph_id` 派生）。
- `api/models.py` + 迁移 `0024`：`WorkflowIntervention.intervention_type` 扩展为 4 值。

前端
- 新增 `pages/WorkflowAnalysisPage.tsx` + 路由 `/cases/:caseId/analysis` + 侧栏「工作流分析」。
- 新增 `lib/workflow-adapters.ts`（snapshot 归一化）、`workflowRunApi.streamTicket`。
- 类型对齐：`InterventionType`(4 值)、`WorkflowArtifactKind`(后端真实 artifact_type)。
- 构建改为真正类型检查：`build = tsc -p tsconfig.app.json && vite build`；`vitest.config` 显式 `esbuild.jsx=automatic`。
- 清理：删除破损未用的 `case-store.saveComplaint`。

判定通过的总标准见 [第 7 节](#7-验收标准)。

---

## 1. 环境准备

后端（服务器）
- Python 依赖已安装（`pip install -r backend/requirements.txt`）。
- 数据库可连接；SSE 依赖 **ASGI** 运行（`uvicorn`），不要用 `runserver` 验证流式。
- 一个可登录的测试账号（用于取 JWT）。

前端
- `cd frontend && npm ci`（或已安装 `node_modules`）。

---

## 2. 自动化检查（最快的回归门）

### 2.1 前端类型检查（必须 0 错误）
```bash
cd frontend
npm run typecheck        # = tsc -p tsconfig.app.json
```
预期：无输出、退出码 0。

### 2.2 前端单元测试（必须全绿）
```bash
cd frontend
npm test                 # = vitest run
```
预期：`Test Files 6 passed`，`Tests 97 passed`。
重点用例：`workflow-run-store` / `workflow-event-reducer` / `sse-client` / `InterventionPanel` / `DocumentEditor` / `useScrollFollow`。

### 2.3 前端生产构建（验证 build 链路）
```bash
cd frontend
npm run build            # tsc 类型检查 + vite 打包
```
预期：类型检查通过后正常产出 `dist/`。

### 2.4 后端测试
```bash
cd backend
python manage.py migrate                    # 见第 3 节
python manage.py test api                    # 或 pytest（若已配置）
```
重点测试文件（本次契约相关）：
- `api/tests/test_sse_envelope.py` / `test_sse_envelope_integration.py`
- `api/tests/test_workflow_runs_api.py`
- `api/tests/test_snapshot_service.py`
- `api/tests/test_unified_interruption.py` / `test_revision_conflict.py`
- `api/tests/test_document_version.py` / `test_document_quality_service.py`

> 注意：`test_workflow_runs_api.py` 已更新断言 `stream_url` 含 `/events/`（原 `/stream/`）。若此断言失败，说明跑的是旧代码。

---

## 3. 数据库迁移

```bash
cd backend
python manage.py showmigrations api | tail -20
python manage.py migrate
```
预期：应用到 `0024_alter_workflowintervention_intervention_type`。
验证 4 类介入类型可用：
```bash
python manage.py shell -c "from api.models import WorkflowIntervention as W; print([c[0] for c in W.INTERVENTION_TYPE_CHOICES])"
# 期望：['quality_review', 'user_pause', 'legal_confirmation', 'missing_information']
```

---

## 4. 后端 API 冒烟测试（curl）

先取 JWT（替换账号密码与域名）：
```bash
BASE=http://localhost:8000
TOKEN=$(curl -s $BASE/api/auth/login/ -H 'Content-Type: application/json' \
  -d '{"username":"<user>","password":"<pass>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access"])')
AUTH="Authorization: Bearer $TOKEN"
```

### 4.1 创建运行（返回 run_id + 票据 + `/events/` 流地址）
```bash
curl -s $BASE/api/cases/<CASE_ID>/workflow-runs/ -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"evidence_ids":[<E1>,<E2>]}' | python3 -m json.tool
```
预期字段：`run_id / thread_id / status / stream_ticket / stream_url`，且 `stream_url` 形如 `/api/workflow-runs/<id>/events/?ticket=...`。

### 4.2 权威快照（字段应与前端适配层对齐）
```bash
curl -s $BASE/api/workflow-runs/<RUN_ID>/snapshot/ -H "$AUTH" | python3 -m json.tool
```
检查：`run`（含 `finished_at`）、`stages[]`（`name`=键、`label`=显示名、`quality`）、`artifacts[]`（`workflow_run_id / artifact_type / content`）、`active_intervention`（`workflow_run_id`）、`issues[]`、`actions`。
> 这些后端字段名由前端 `lib/workflow-adapters.ts` 归一化，无需后端改名。

### 4.3 为已存在运行签发票据（新端点）
```bash
curl -s $BASE/api/workflow-runs/<RUN_ID>/stream-ticket/ -X POST -H "$AUTH" | python3 -m json.tool
# 期望：{run_id, stream_ticket, stream_url}
```

### 4.4 SSE 事件流（应含追加式 stage.* 事件）
```bash
TICKET=$(curl -s $BASE/api/workflow-runs/<RUN_ID>/stream-ticket/ -X POST -H "$AUTH" | python3 -c 'import sys,json;print(json.load(sys.stdin)["stream_ticket"])')
curl -N -s "$BASE/api/workflow-runs/<RUN_ID>/events/?ticket=$TICKET" -H "$AUTH"
```
预期：看到 `event: node.start` / `event: node.complete` 等旧事件**以及**新增的 `event: stage.started` / `event: stage.progress` / `event: stage.completed`；`data` JSON 含 `run_id`、`revision`、`payload.stage`。心跳为 `: heartbeat`。
> 票据撤销时机：仅在事件流**正常结束（运行进入终态）**时撤销。运行进行中断开后，可用**同一** `ticket`（携 `Last-Event-ID`）在票据 TTL 内**重连续传**；运行结束后或 TTL 过期后，同一票据将被拒绝。
> 重连断点续传验证：连接后 `Ctrl-C` 断开 → 记下最后 `event_id` → 用**同一** ticket 且 `-H "Last-Event-ID: <id>"` 重新 `curl -N` → 应只补发该 id 之后的事件，不重复历史。

### 4.5 其他动作端点
```bash
curl -s $BASE/api/workflow-runs/<RUN_ID>/pause/  -X POST -H "$AUTH"
curl -s $BASE/api/workflow-runs/<RUN_ID>/cancel/ -X POST -H "$AUTH"
curl -s $BASE/api/cases/<CASE_ID>/workflow-runs/  -H "$AUTH" | python3 -m json.tool   # 历史 + active_run_id
```

### 4.6 文书端点（运行产出文书后）
```bash
# document_id = snapshot.artifacts 中文书产物 content.document_version_id
curl -s $BASE/api/workflow-runs/<RUN_ID>/documents/<DOC_VERSION_ID>/ -H "$AUTH" | python3 -m json.tool
# 校验：paragraphs[].id 存在（由 paragraph_id 派生），template_type、current_version 正确
curl -s $BASE/api/workflow-runs/<RUN_ID>/documents/<DOC_VERSION_ID>/versions/ -H "$AUTH" | python3 -m json.tool
curl -s $BASE/api/workflow-runs/<RUN_ID>/documents/<DOC_VERSION_ID>/export-check/ -X POST -H "$AUTH" | python3 -m json.tool
```

### 4.7 介入提交 + 冲突（409）
```bash
# 正常提交（base_revision 与当前一致）
curl -s $BASE/api/workflow-runs/<RUN_ID>/interventions/<IID>/submit/ -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"submitted_values":{}}' | python3 -m json.tool
# 期望：{intervention, status:"submitted", stream_ticket, stream_url}
```
制造冲突：在两个会话对同一介入并发提交，其一应返回 `409` + `{code:"REVISION_CONFLICT", current_revision}`。

---

## 5. 前端 E2E 手动验证

前置：`npm run dev`（或部署后访问），登录，进入一个已有证据的案件。

### 5.1 新分析页 · 主链路
1. 侧栏点击「工作流分析」→ 进入 `/cases/{id}/analysis`。无运行时显示空状态与「开始分析」。
2. 点击「开始分析」→ 配置抽屉选择证据 → 开始。
3. 观察 **BusinessStageStepper** 四阶段随 `stage.*` 事件实时推进（材料理解→事实核对→案件组织→文书生成）。
4. **WorkflowCommandBar**：运行中显示进度、连接状态；按钮可用性由后端 `actions` 决定（不前端臆测）。
5. **CurrentActivityPanel / ArtifactTimeline**：随节点完成出现产物卡（标签为中文，非英文串）。
6. **QualitySummary / IssueList**：显示质量与问题；点击 issue 的证据链接跳转证据页。

### 5.2 用户介入（低置信度 / 暂停）
1. 触发低置信度审核或质量门时，出现 **InterventionPanel**，焦点移至标题，可 Esc 关闭。
2. 编辑字段 → 刷新页面 → 草稿从 `sessionStorage` 恢复。
3. 提交 → 运行 resume 继续；面板关闭。
4. 并发冲突：另一会话推进 revision 后提交 → 面板提示修订冲突（对应 409）。

### 5.3 暂停 / 取消 / 失败恢复
1. 运行中「暂停」→ 状态转 `waiting_user`/`pausing`；「继续/取消」按钮随 `actions` 变化。
2. 制造失败（如无有效文书）→ 出现 **WorkflowRecoveryPanel** → 「重试」从阶段 fork 新运行并切换。

### 5.4 运行历史 / 刷新恢复
1. 「运行历史」抽屉列出多次运行 + 高亮当前；切换到历史运行加载其快照。
2. 运行中刷新页面 → 通过 `listRuns→snapshot→stream-ticket` 恢复状态与实时连接（断线自动退避重连）。

### 5.5 文书工作台
1. 文书生成后，页面下方出现 **DocumentEditor**（双栏：正文 + 依据/质量）。
2. 段落证据编号 / 法条可点击（跳转证据页 / 打开法条原文）。
3. 修改段落 → 自动保存（顶部「保存中/已保存」）→ 生成新版本。
4. 「版本历史」列出版本（含 workflow_version），可对比 / 回滚。
5. 「重新生成选中段落」→ 段落更新。
6. 「导出前检查」：`passed=true` 启用导出，`false` 展示阻塞原因。
7. 流式生成时正文逐段写入；用户上滚后停止自动跟随，底部出现「回到最新内容」。

---

## 6. 旧路径回归（必须行为不变）

1. `/cases/{id}/evidence` → 旧 **WorkflowStreamPanel** 正常：启动、节点轨道、流式文书、审核/暂停面板。
2. 旧 SSE 端点 `/api/cases/{id}/workflow/stream/` 仍可用；旧 EventSource 客户端**忽略**新增的 `stage.*` 事件（不报错）。
3. 旧投诉/答辩/导出/时间线页功能不变。
4. `case-store` 旧字段仍驱动旧路径（未删除，仅 `@deprecated`）。

---

## 7. 验收标准

- [ ] 前端 `npm run typecheck` 0 错误；`npm test` 97/97 通过；`npm run build` 成功。
- [ ] 后端 `migrate` 到 `0024`；重点测试文件全绿。
- [ ] `POST workflow-runs` 返回 `/events/` 流地址与票据。
- [ ] `snapshot` 字段齐全；前端页面渲染无「字段 undefined」白屏或英文原始枚举串。
- [ ] SSE 流含 `stage.*` 新事件且携 `run_id/revision`；旧事件仍在。
- [ ] 分析页主链路、介入、暂停/取消、失败恢复、运行历史、刷新恢复、文书工作台全部可用。
- [ ] 介入并发提交返回 409 且前端提示冲突。
- [ ] 旧路径 `/evidence` 行为无变化。

---

## 8. 故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| SSE 立即 401 | 票据 TTL 过期、运行已终态被撤销，或缺 JWT | 重新 `stream-ticket/` 取票据；确认 `Authorization` 头 |
| SSE 无数据只有心跳 | 运行已结束或无新事件 | 查 `snapshot.run.status`；已结束运行不建连接 |
| 分析页产物卡显示英文串 | artifact `kind` 未匹配标签表 | 确认后端 `artifact_type` 与 `WorkflowArtifactKind` 一致 |
| 段落重生成 404 | `paragraph_id` 与 URL 不符 | 确认详情端点段落已补 `id`（=paragraph_id） |
| stage 不动但节点在跑 | 前端未收到 `stage.*` | 确认后端 mapper 追加事件已部署；检查 `payload.stage` 是否为业务阶段键 |
| 刷新后连接不恢复 | `stream-ticket` 端点未部署 | 确认 `urls.py` 已注册 `stream-ticket/` |
| 前端 tsc 报 vitest/node 类型错误 | 误用 `tsc`（空检查）或未排除测试 | 用 `npm run typecheck`（`-p tsconfig.app.json`，已排除测试） |
| JSX 测试报 `React is not defined` | vitest 未启用自动 JSX 运行时 | 确认 `vitest.config.ts` 的 `esbuild.jsx='automatic'` |
