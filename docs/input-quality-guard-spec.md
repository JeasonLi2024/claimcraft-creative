# 工作流输入质量校验与内容相关性核查 —— 实施规格（SPEC）

> 文档状态：实施规格（对应 [input-quality-guard-design.md](./input-quality-guard-design.md)）
> 目标：在结合真实代码实现的前提下，落地设计文档提出的三道输入质量门，防止 LLM 在无效输入上捏造内容。
> 适用版本：当前 v10/v11 工作流（preclassify → ocr → classify → extract → review? → evidence_chain → complaint / respond_complaint）

---

## 0. 与设计文档的关键适配（务必阅读）

实施时发现设计文档若干处与现有代码/图拓扑不一致，按"合理、正确"原则做如下适配：

1. **Gate 2 abort 的终止机制**
   - 设计原文：extract 返回 `workflow_aborted_by_user=True`，由 `workflow_runner` 检测后 `fail_processing`。
   - 现状问题：图拓扑为 `extract → stage_gate_after_extract → … → complaint → END`。若 extract 正常返回，图会继续执行到 `complaint_node` **生成文书**，`workflow_runner` 只在图结束后检查，无法阻止；且 `extract` 配置了 `error_handler`（Saga 降级），`raise` 会被捕获、图继续，同样无法终止。
   - **实现方案**：abort 分支返回 `Command(update=partial, goto=END)`（沿用 `review_node.py` 的 `Command(update=…, goto=…)` 既有范式），直接路由到 END，跳过 `complaint`。这是 LangGraph 节点级运行时路由，**不新增图节点/边**，符合设计原则#3（不修改图拓扑）。`workflow_runner` 在图结束后读取 `snapshot.values["workflow_aborted_by_user"]`，给出精确失败信息。

2. **interrupt payload 中 reason/diagnostics 的落地**
   - 现状：`WorkflowIntervention` 模型没有 `reason`/`diagnostics` 字段；`snapshot_service._serialize_intervention` 从 `impact` 派生 `reason`；前端介入面板通过 **snapshot**（而非 SSE flat payload）获得介入对象。
   - **实现方案**：把 `reason`/`required`/`diagnostics` 写入 `impact`；`snapshot_service` 额外从 `impact` 派生 `diagnostics`；前端类型 + 归一化 + 面板读取。

3. **Gate 1 / Gate 3 前端呈现的数据通路**
   - 现状：页面 `quality` 对象由 stage 分数合成、`details` 恒为空；`classify`/`extract` 节点不产出 `WorkflowArtifact`（仅 `complaint`/`respond_complaint` 产出），故 stage 的 `quality.details` 不含相关性信息；`DocumentDetail` 无质量字段。
   - **实现方案**：
     - Gate 1：`classify_node` 在触发时追加一条 **warning issue**（code `material.evidence_low_relevance`），经 `state.issues → snapshot.issues → 前端 issues` 通道稳定呈现；`QualitySummary` 增可选 `warnings` prop，由页面从 issues 派生渲染橙色告警。同时相关性数据仍写入 `quality.details` 与 state 字段供审计。
     - Gate 3：`complaint`/`respond_complaint` 把 `data_sufficiency` 写入 `WorkflowArtifact.content`；文书详情端点透出 `data_sufficiency`；`DocumentEditor` 顶部 Banner 渲染。

4. **Gate 3 `critically_sparse` + 未确认 分支**
   - 设计原文：跳过 LLM 重写、返回空内容 → 质量失败。
   - 现状问题：这会**硬失败合法但材料单薄**的案件；且 Gate 2 已拦截最坏情形，此分支设计自称"理论上不应到达"。空内容还会使 `complete_processing` 因 `_has_valid_document` 为假而失败，UX 不佳。
   - **实现方案**：始终以"骨架 + 强约束 `SPARSE_DATA_NOTICE`"生成（骨架只含用户已提供事实、无幻觉），记录 `data_sufficiency_level` 并由前端 Banner 提示，**不硬失败**。既达成防幻觉目标，又不误伤单薄但合法的案件。

---

## 1. 后端实现契约

### 1.1 `state.py`（新增标量字段，默认覆盖无 reducer）
```
low_quality_evidence_acknowledged: bool   # 用户在 Gate 2 确认低质量后继续
workflow_aborted_by_user: bool            # 用户在 Gate 2 选择终止
evidence_relevance_ratio: float           # Gate 1：证据与案件类型相关性比例
evidence_all_other: bool                  # Gate 1：是否全部分类为 other
```

### 1.2 `classify_node.py` — Gate 1
- 常量：`CASE_TYPE_EXPECTED_CATEGORIES: dict[str, set[str]]`（shopping/service/secondhand，`other` 不限制）、`RELEVANCE_WARN_THRESHOLD = 0.3`。
- 纯函数：
  ```
  _compute_evidence_relevance(case_type: str, classify_results: list[dict]) -> dict
    → {relevance_ratio, expected_categories, matched_count, total_count, all_other}
  ```
  规则：无 classify_results → ratio 0.0/all_other True；`case_type` 无预期集合（other/未知）→ ratio 1.0/all_other False；否则 ratio = 命中预期类别数 / 总数。
- 主返回路径：取 `case_type`（`sync_to_async` 从 `Case.objects.filter(pk=case_id).values_list("case_type", flat=True).first()`）；合并 relevance 到 `quality.details`（`evidence_relevance_ratio` / `evidence_all_other` / `evidence_expected_categories` / `evidence_matched_count` / `evidence_total_count`）；`ratio < 阈值` → `quality_status = "warn"`；`legacy_fields` 追加 `evidence_relevance_ratio` / `evidence_all_other`。
- 触发条件（`all_other and ratio < 阈值`）：`build_node_result(warnings=[{code:"material.evidence_low_relevance", message:<中文文案>, severity:"warning", stage:"classify"}])`，由 `make_node_partial_update` 自动并入 `issues`。**不改 blocking_issues、不 interrupt。**

### 1.3 `extract_node.py` — Gate 2（硬拦截门）
- 纯函数：
  ```
  _is_evidence_critically_insufficient(classify_results, preclassify_results, total_fields) -> bool
  ```
  触发 = `classify_results 非空` AND `全部 other` AND `avg(preclassify.confidence) < 0.5` AND `total_fields == 0`（严格 AND）。
- 位置：`node_result` 构造完成后、最终 `return make_node_partial_update(...)` 之前。
- 命中：`create_intervention(intervention_type="missing_information", stage="fact_checking", base_revision, form_schema, initial_values, impact)` → `interrupt(payload)`。
  - `form_schema.fields`：`radio "action"`（选项 `confirm_continue` / `abort`，required）+ `textarea "notes"`（可选）。
  - `initial_values`：`{action:"confirm_continue", evidence_count, avg_confidence, total_fields}`。
  - `impact`：`{downstream_nodes:["evidence_chain","complaint","respond_complaint"], rerun_required:False, required:True, reason:<中文文案>, diagnostics:{evidence_count, avg_preclassify_confidence, total_extracted_fields, all_classified_other}}`。
  - `payload`：统一结构（`interrupt_type/intervention_id/intervention_kind/required/stage/reason/base_revision/form_schema/initial_values/impact/diagnostics`）。
- resume 解析（对齐 `views.py` submit → `Command(resume={interrupt_type, intervention_id, submitted_values})`）：
  ```
  submitted = resume_value.get("submitted_values", {}) if dict else {}
  action = submitted.get("action") or resume_value.get("action") or "confirm_continue"
  ```
  - `abort` → `return Command(update=partial{…, workflow_aborted_by_user:True, errors+=终止说明}, goto=END)`。
  - 否则（`confirm_continue`）→ `return make_node_partial_update(..., legacy_fields={…, low_quality_evidence_acknowledged:True})`。
- import：`from langgraph.types import Command, interrupt`、`from langgraph.graph import END`、`from api.services.intervention_service import create_intervention`；返回注解 `dict[str, Any] | Command`。
- 幂等：`create_intervention` 用 `update_or_create`；resume 时整节点重跑但抽取命中 `_check_extract_cache`（source_hash 未变）跳过 LLM，介入记录不重复。

### 1.4 `workflow_runner.py` — abort 检测
`run_and_persist` 内 `snapshot = await workflow.aget_state(config)` 之后、`stage_pause` 判定之前：
```
final_values = snapshot.values or {}
if final_values.get("workflow_aborted_by_user"):
    fail_processing(case_id, "用户主动终止：证据质量不足，请重新上传证据后再次启动工作流")
    _update_workflow_run(run_id, status='failed', finished_at=now, error_message=...)
    persist "workflow.error"(recoverable=False, message=...) + notify
    return
```

### 1.5 `complaint_node.py` / `respond_complaint_node.py` — Gate 3
- 纯函数（两节点共用逻辑，各自定义或复用）：
  ```
  _assess_data_sufficiency(all_fields, evidence_chain, case_description, acknowledged_low_quality) -> dict
    → {score: float, level: "sufficient"|"sparse"|"critically_sparse", missing_dimensions: list[str]}
  ```
  评分：字段(≥3→0.4, >0→0.2, 0→缺失) + 时间线(≥2→0.3, ==1→0.15, 0→缺失) + 描述(≥50→0.3, ≥20→0.15, <20→缺失)；`score≥0.6 sufficient / ≥0.3 sparse / else critically_sparse`。
- LLM 重写前（`prompt = ....format(...)` 之后、调用 LLM 之前）：
  - `acknowledged = state.get("low_quality_evidence_acknowledged", False)`；
  - `sufficiency = _assess_data_sufficiency(all_fields, state.get("evidence_chain", []), case.description or "", acknowledged)`；
  - `level in ("sparse","critically_sparse")` → `prompt += "\n\n" + SPARSE_DATA_NOTICE.format(fields_count, chain_count, desc_len)`（模块级常量，不改 prompt 模板）。
- `quality.details` 追加 `data_sufficiency_score` / `data_sufficiency_level` / `missing_dimensions`；`WorkflowArtifact.content` 追加 `data_sufficiency`。

### 1.6 `snapshot_service.py`
`_serialize_intervention` 增：`'diagnostics': impact.get('diagnostics', {})`。

### 1.7 `views.py` `WorkflowRunDocumentDetailView.get`
查该 run 最新 `complaint_draft` / `respond_complaint_draft` `WorkflowArtifact`，从 `content.data_sufficiency` 取值加入响应 `'data_sufficiency'`（缺省 None）。不新增 DB 迁移。

---

## 2. 前端实现契约

| 文件 | 变更 |
|---|---|
| `types/workflow.ts` | `WorkflowIntervention` 增可选 `reason?`、`diagnostics?` |
| `lib/workflow-adapters.ts` | `normalizeIntervention` 归一化 `reason`/`diagnostics` |
| `components/workflow/InterventionField.tsx` | `FormFieldType` 增 `"radio"` + radio 组渲染 |
| `components/workflow/InterventionPanel.tsx` | `INTERVENTION_TYPE_CONFIG` 增 `missing_information`/`legal_confirmation`；渲染 `reason` 告警条；`missing_information` 渲染 `diagnostics` 只读区块 |
| `components/workflow/QualitySummary.tsx` | 增可选 `warnings?: {title, detail}[]`，橙色告警条渲染（Gate 1） |
| `pages/WorkflowAnalysisPage.tsx` | 从 `issues`（code `material.evidence_low_relevance`）派生 warnings → QualitySummary；文书 `data_sufficiency` → DocumentEditor |
| `types/document.ts` | `DocumentDetail` 增可选 `data_sufficiency` |
| `components/workflow/DocumentEditor.tsx` | `data_sufficiency.level ∈ {sparse, critically_sparse}` 顶部 Banner |

---

## 3. 测试执行方案（本地无运行环境，仅补充文案）

- **后端** `backend/api/tests/test_input_quality_guard.py`（Django `TestCase`，纯函数单测）：
  - 执行：`cd backend && python manage.py test api.tests.test_input_quality_guard -v 2`
  - 或（若使用 pytest）：`cd backend && pytest api/tests/test_input_quality_guard.py -v`
  - 前置：需可用的 Django settings 与数据库（纯函数测试可用 `SimpleTestCase`，无需 DB）。
- **前端** `frontend/src/components/workflow/__tests__/`：
  - 执行：`cd frontend && npx vitest run`（或 `npm run test`）
  - 覆盖：`InterventionField` radio 渲染/选择/必填；`QualitySummary` warnings 橙条渲染。

---

## 4. 回归验证要点

| 场景 | 预期 |
|---|---|
| 1 张无关图 + 随意描述 | Gate 2 `interrupt(missing_information)`，前端弹面板含诊断 + 单选 |
| Gate 2 选 `abort` | 工作流 `failed`、无投诉文书、提示"用户主动终止…" |
| Gate 2 选 `confirm_continue` | 继续，`complaint` 注入稀疏告知，Banner 提示，文书无捏造 |
| 不匹配类型但可提字段的图 | Gate 2 不触发；classify 发相关性 warning，QualitySummary 橙条 |
| 3 张有效证据 + 合理描述 | 全程无新增中断，与现行为一致 |
| stage_gate 暂停后 resume | Gate 2 仅在 extract 首次执行且条件满足时触发，幂等无重复介入记录 |
