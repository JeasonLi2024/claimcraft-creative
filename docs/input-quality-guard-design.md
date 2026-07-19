# 工作流输入质量校验与内容相关性核查设计方案

> 文档状态：设计方案（待实施）
> 问题来源：代码审查发现——随意填写案件表单 + 上传无关图片时，LLM 会凭当前输入自行捏造内容，全流程缺乏输入质量拦截门
> 适用版本：当前 v10 工作流（preclassify → ocr → classify → extract → review? → evidence_chain → complaint / respond_complaint）

---

## 1. 问题背景

### 1.1 问题一：证据质量无硬性拦截门

当用户上传与案件无关的图片（如随意截图、非证据照片）时：

- `preclassify_node`：低置信度 → `quality_status = "warn"`，`blocking_issues = []`，**流程继续**
- `classify_node`：全部归类为 `other` → `quality_status = "warn"`，**流程继续**
- `extract_node`：无法从无关图片提取有效字段 → `total_fields = 0` → `quality_status = "warn"`（因 `any_needs_review = False`），**流程继续**
- `complaint_node`：拿到空 `all_fields` + 案件描述骨架后，LLM 会凭 `scenario_description` 和 Jinja2 骨架中的案件类型捏造典型情节

当前唯一硬性拦截点（[quality_gate_service.py:352](../backend/api/services/quality_gate_service.py)）是：

```python
def should_block_on_quality(quality: QualityReport) -> bool:
    return quality.status == "fail"  # 只要 LLM 输出了文字，status 就是 pass
```

只要 LLM 产出任何文字，质量状态就是 `pass`，不会触发阻塞。

### 1.2 问题二：案件表单与证据内容无交叉核查

案件表单字段（`description`、`case_type`）与证据图片分析结果在工作流各节点中的流转方式：

| 节点 | 表单数据用途 | 是否核查一致性 |
|---|---|---|
| `preclassify_node` | 加载 `case_description`，但未注入 `PRECLASSIFY_PROMPT` | ✗ |
| `ocr_node` | `case_description` 注入 OCR 纠错 prompt，辅助识别 | ✗（仅辅助，不验证） |
| `classify_node` | 不使用表单数据 | ✗ |
| `extract_node` | 不使用表单数据 | ✗ |
| `evidence_chain_node` | `case_description` + `evidences_json` 同时注入 LLM，但 prompt 要求"构造时间链"，不要求判断一致性 | ✗（LLM 倾向调和矛盾而非报告） |
| `complaint_node` | `case_description` 渲染 Jinja2 骨架；骨架 + 空字段 → LLM 重写 | ✗ |

结论：两类数据各自独立流入 LLM，**不存在任何程序层面的交叉核查逻辑**。

---

## 2. 设计原则

1. **遵循现有 interrupt 模式**：所有拦截点沿用 `create_intervention()` → `interrupt()` 范式，保持与 `review_node`、`stage_gate_node`、`complaint_node` 中质量门的一致性。
2. **分层响应，不过度拦截**：轻微异常给警告 + 提示（可继续），严重异常才硬性阻断（需用户确认或纠正）。LLM 的不确定性不能完全转移为对用户的障碍。
3. **不修改图拓扑**：所有新增逻辑内嵌至已有节点，不在 `graph.py` 中增加新节点或改变边关系，降低回归风险。
4. **幂等性**：所有新增 `interrupt()` 调用之前先调用 `create_intervention()`（使用 `update_or_create` 保证幂等），resume 时节点从头重新执行不创建重复记录。
5. **渐进降级**：能通过 prompt 工程约束 LLM 行为的地方，以 prompt 约束为辅助手段；不能依赖 prompt 完全防止幻觉，必须有程序层面硬性条件。

---

## 3. 整体方案架构

```
START → preclassify → stage_gate → ocr → stage_gate → classify
           │                                               │
           │                                         【Gate 1】证据-案件类型
           │                                         相关性评分（仅警告）
           │                                               │
           ↓                                         stage_gate → extract
                                                           │
                                                     【Gate 2】证据质量硬拦截
                                                     （条件：全 other + 零字段）
                                                           │
                                             interrupt(missing_information)
                                             ← 用户：重传证据 或 确认继续
                                                           │
                                            stage_gate → evidence_chain
                                                           │
                                                     stage_gate → complaint
                                                           │
                                                     【Gate 3】投诉节点
                                                     入口数据充分性校验
                                                     （数据极度稀疏时）
                                                           │
                                          prompt 注入稀疏数据告知段落
                                          + quality 报告注明数据局限
```

---

## 4. Gate 1：证据-案件类型相关性评分（`classify_node` 内）

### 4.1 目的

在分类完成后，评估证据内容与用户填报的 `case_type` 是否吻合，结果写入质量详情，供 UI 在「材料理解」阶段的质量面板中展示橙色警告。**不硬性阻塞流程。**

### 4.2 案件类型与预期证据类别的映射关系

```python
# 新增常量（classify_node.py 顶部）
CASE_TYPE_EXPECTED_CATEGORIES: dict[str, set[str]] = {
    "shopping": {
        "chat_screenshot", "product_order", "logistics_tracking",
        "payment_record", "invoice",
    },
    "service": {
        "service_contract", "communication_record", "work_record",
        "chat_screenshot",
    },
    "secondhand": {
        "chat_screenshot", "product_order", "payment_record",
        "communication_record",
    },
    # "other" 不做限制，任何类别均视为相关
}

# 相关性评分的最低阈值（低于此值时写入警告）
RELEVANCE_WARN_THRESHOLD = 0.3
```

### 4.3 实现逻辑

在 `classify_node` 计算完 `classify_results` 后（当前代码第 177 行之后），追加：

```python
def _compute_evidence_relevance(
    case_type: str,
    classify_results: list[dict],
) -> dict:
    """计算证据与案件类型的相关性。

    Returns:
        {
          "relevance_ratio": float,      # 相关证据占比 0.0-1.0
          "expected_categories": list,   # 该案件类型的预期证据类别
          "matched_count": int,          # 命中预期类别的证据数
          "total_count": int,
          "all_other": bool,             # 是否全部归类为 other
        }
    """
    if not classify_results:
        return {"relevance_ratio": 0.0, "all_other": True,
                "matched_count": 0, "total_count": 0, "expected_categories": []}

    expected = CASE_TYPE_EXPECTED_CATEGORIES.get(case_type, set())
    if not expected:
        # "other" 案件类型不做限制，全部视为相关
        return {"relevance_ratio": 1.0, "all_other": False,
                "matched_count": len(classify_results),
                "total_count": len(classify_results),
                "expected_categories": []}

    matched = sum(
        1 for r in classify_results
        if r.get("evidence_category") in expected
    )
    all_other = all(
        r.get("evidence_category") == "other" for r in classify_results
    )
    ratio = matched / len(classify_results)
    return {
        "relevance_ratio": round(ratio, 3),
        "expected_categories": sorted(expected),
        "matched_count": matched,
        "total_count": len(classify_results),
        "all_other": all_other,
    }
```

将返回值合并到 `node_result` 的 `quality.details` 中：

```python
relevance_info = _compute_evidence_relevance(case_type, classify_results)

# 在 build_node_result 的 details 中追加
details = {
    "avg_confidence": avg_confidence,
    "category_distribution": category_distribution,
    # Gate 1 新增
    "evidence_relevance_ratio": relevance_info["relevance_ratio"],
    "evidence_all_other": relevance_info["all_other"],
    "evidence_expected_categories": relevance_info["expected_categories"],
    "evidence_matched_count": relevance_info["matched_count"],
    "evidence_total_count": relevance_info["total_count"],
}

# quality_status 在相关性极低时降为 warn（已经是 warn 则不变）
if relevance_info["relevance_ratio"] < RELEVANCE_WARN_THRESHOLD:
    quality_status = "warn"
```

> **注意**：Gate 1 只写入 `details`，不修改 `blocking_issues`，不调用 `interrupt()`。前端 `QualitySummary` 组件读取 `details.evidence_relevance_ratio` 字段，在 < 0.3 时展示橙色提示："上传的证据类型与选择的案件类型（XX 纠纷）匹配度较低，建议确认证据是否正确"。

#### 4.4 需要修改的文件

- `backend/api/agents/nodes/classify_node.py`：新增常量 + `_compute_evidence_relevance` 函数 + 在节点末尾追加到 details

---

## 5. Gate 2：证据质量硬性拦截门（`extract_node` 末尾）

### 5.1 触发条件（AND 关系，同时满足才触发）

| 条件 | 含义 | 实现来源 |
|---|---|---|
| `all_other = True` | 所有证据均被分类为 `other` | `classify_results` 中 `evidence_category` 全为 `other` |
| `avg_preclassify_confidence < 0.5` | 预分类平均置信度极低（LLM 本身也没把握） | `preclassify_results` 中 `confidence` 的均值 |
| `total_fields == 0` | 全流程未提取到任何有效字段 | `extract_results` 中所有 `fields` 合计数量 |

**三条件均满足 = 流程没有获得任何有价值的输入信息，继续生成文书必然导致 LLM 捏造内容。**

单独一条件不触发，例如：
- 证据是物证图片（全 `other`，低置信度）但描述充分（fields > 0）→ 不触发
- 有部分 `other` 但有一张聊天记录（fields > 0）→ 不触发

### 5.2 实现逻辑

在 `extract_node` 的 `make_node_partial_update` 调用之前插入：

```python
def _is_evidence_critically_insufficient(
    classify_results: list[dict],
    preclassify_results: list[dict],
    total_fields: int,
) -> bool:
    """判断证据质量是否低到必须阻断流程的程度。"""
    if not classify_results:
        return False  # 无证据是另一个问题（preclassify_node 已处理）

    all_other = all(
        r.get("evidence_category") == "other" for r in classify_results
    )
    if not all_other:
        return False

    if preclassify_results:
        avg_confidence = sum(
            r.get("confidence", 0.0) for r in preclassify_results
        ) / len(preclassify_results)
    else:
        avg_confidence = 0.0

    return avg_confidence < 0.5 and total_fields == 0


# 在 extract_node 末尾、return make_node_partial_update(...) 之前
if _is_evidence_critically_insufficient(
    classify_results, preclassify_results, total_fields
):
    from langgraph.types import interrupt
    from api.services.intervention_service import create_intervention

    base_revision = state.get("revision", 0)
    workflow_run_id = state.get("workflow_run_id")

    intervention = await sync_to_async(create_intervention)(
        workflow_run_id=workflow_run_id,
        case_id=case_id,
        intervention_type="missing_information",
        stage="fact_checking",
        base_revision=base_revision,
        form_schema={
            "fields": [
                {
                    "name": "action",
                    "label": "处理方式",
                    "type": "radio",
                    "required": True,
                    "options": [
                        {
                            "value": "confirm_continue",
                            "label": "我了解风险，继续生成（输出质量可能较低）",
                        },
                        {
                            "value": "abort",
                            "label": "终止本次工作流，我将重新上传证据",
                        },
                    ],
                },
                {
                    "name": "notes",
                    "label": "补充说明（可选）",
                    "type": "textarea",
                    "required": False,
                },
            ]
        },
        initial_values={
            "evidence_count": len(classify_results),
            "avg_confidence": round(avg_confidence, 3),
            "total_fields": total_fields,
        },
        impact={
            "downstream_nodes": ["evidence_chain", "complaint", "respond_complaint"],
            "rerun_required": False,
        },
    )

    payload = {
        "interrupt_type": "missing_information",
        "intervention_id": intervention.id,
        "intervention_kind": "missing_information",
        "required": True,
        "stage": "fact_checking",
        "reason": (
            f"上传的 {len(classify_results)} 张图片均无法识别为有效证据材料"
            f"（平均置信度 {avg_confidence:.0%}），且未能提取任何结构化字段。"
            "如继续生成，文书内容将主要基于案件描述而非实际证据。"
        ),
        "base_revision": base_revision,
        "form_schema": intervention.form_schema,
        "initial_values": intervention.initial_values,
        "impact": intervention.impact,
        # 诊断数据（前端可展示辅助信息）
        "diagnostics": {
            "evidence_count": len(classify_results),
            "avg_preclassify_confidence": round(avg_confidence, 3),
            "total_extracted_fields": total_fields,
            "all_classified_other": True,
        },
    }

    resume_value = interrupt(payload)

    # resume 后处理：读取用户选择
    if isinstance(resume_value, dict):
        action = resume_value.get("action", "confirm_continue")
        if action == "abort":
            # 用户选择终止：写入 state 标记，让 workflow_runner 识别后 fail_processing
            return make_node_partial_update(
                node_name="extract",
                stage="fact_checking",
                progress=0.45,
                state=state,
                node_result=node_result,
                legacy_fields={
                    "evidence_extract_results": extract_results,
                    "needs_human_review": False,
                    "errors": error_dicts + [{"stage": "extract", "msg": "用户终止：证据质量不足"}],
                    "workflow_aborted_by_user": True,  # 新增 state 字段，runner 检测到后 fail
                },
            )
        # action == "confirm_continue"：记录用户已知晓，继续流程
        logger.info("[extract] 用户确认在低质量证据下继续工作流")
        state["low_quality_evidence_acknowledged"] = True
```

### 5.3 Resume 后的工作流行为

| 用户选择 | 工作流行为 |
|---|---|
| `confirm_continue` | 设置 `state["low_quality_evidence_acknowledged"] = True`，继续流程；`complaint_node` 读取该标记后在生成时附加数据质量免责提示 |
| `abort` | 设置 `legacy_fields["workflow_aborted_by_user"] = True`；`workflow_runner.py` 检测到该字段后调用 `fail_processing`，提示"用户主动终止，请重新上传证据后再次启动工作流" |

> `low_quality_evidence_acknowledged` 和 `workflow_aborted_by_user` 为新增 state 字段，需在 `backend/api/agents/state.py` 中增加声明。

### 5.4 需要修改的文件

- `backend/api/agents/nodes/extract_node.py`：新增 `_is_evidence_critically_insufficient` 函数 + 末尾插入拦截逻辑
- `backend/api/agents/state.py`：新增 `low_quality_evidence_acknowledged: bool`、`workflow_aborted_by_user: bool` 字段
- `backend/api/agents/workflow_runner.py`：在结果处理阶段检测 `workflow_aborted_by_user` 标记，调用 `fail_processing`

---

## 6. Gate 3：`complaint_node` 入口数据充分性校验

### 6.1 目的

Gate 2 覆盖"全 other + 零字段"的最严重情形。Gate 3 作为纵深防御，处理两种补充场景：

1. 用户在 Gate 2 选择了 `confirm_continue`（明确知晓风险但仍继续）
2. 证据通过了 Gate 2 筛选但实际数据仍极度稀疏（如只有 1 个低置信度字段）

Gate 3 不再触发 `interrupt()`（用户已有机会在 Gate 2 决策），而是：

- 在 LLM 重写 prompt 中注入"稀疏数据告知段落"，明确要求 LLM 如实声明数据局限而非捏造
- 在 `quality` 报告中记录数据充分性得分，前端显示相应警告

### 6.2 数据充分性评分

```python
def _assess_data_sufficiency(
    all_fields: list[dict],
    evidence_chain: list[dict],
    case_description: str,
    acknowledged_low_quality: bool,
) -> dict:
    """评估投诉文书生成前的输入数据充分性。

    Returns:
        {
          "score": float,           # 0.0-1.0
          "level": str,             # "sufficient" / "sparse" / "critically_sparse"
          "missing_dimensions": list[str],  # 缺失维度的描述
        }
    """
    score = 0.0
    missing = []

    # 字段维度：有效字段 ≥3 得 0.4 分，0 字段得 0
    if len(all_fields) >= 3:
        score += 0.4
    elif len(all_fields) > 0:
        score += 0.2
    else:
        missing.append("证据字段（订单号/金额/时间等）")

    # 时间线维度：有证据链节点 ≥2 得 0.3 分
    if len(evidence_chain) >= 2:
        score += 0.3
    elif len(evidence_chain) == 1:
        score += 0.15
    else:
        missing.append("事件时间线")

    # 案件描述维度：描述 ≥50 字得 0.3 分
    desc_len = len(case_description.strip())
    if desc_len >= 50:
        score += 0.3
    elif desc_len >= 20:
        score += 0.15
    else:
        missing.append("案件描述（过于简短）")

    if score >= 0.6:
        level = "sufficient"
    elif score >= 0.3:
        level = "sparse"
    else:
        level = "critically_sparse"

    return {"score": round(score, 2), "level": level, "missing_dimensions": missing}
```

### 6.3 基于充分性等级的行为差异

```python
# complaint_node 中，在 LLM 重写之前
acknowledged = state.get("low_quality_evidence_acknowledged", False)
sufficiency = _assess_data_sufficiency(
    all_fields=all_fields,
    evidence_chain=state.get("evidence_chain", []),
    case_description=case.description or "",
    acknowledged_low_quality=acknowledged,
)

if sufficiency["level"] == "critically_sparse" and not acknowledged:
    # 极度稀疏且用户未经 Gate 2 确认（理论上不应到达此处，作为最后防线）
    # 跳过 LLM 重写，直接返回质量失败
    errors.append(f"输入数据不足以生成有效文书：缺失 {sufficiency['missing_dimensions']}")
    has_content = False
    final_content = ""
    # 后续正常走 quality 评估并在报告中标注原因

elif sufficiency["level"] in ("sparse", "critically_sparse"):
    # 数据稀疏（用户已确认继续）：注入稀疏数据告知段落到 prompt
    SPARSE_DATA_NOTICE = """
【重要提示 - 输入数据说明】
当前可用的证据字段有限（{fields_count} 个），事件时间线节点数 {chain_count} 个，
案件描述长度 {desc_len} 字。

在此情况下，你的写作要求：
1. 仅使用上述已提供的信息，不得根据案件类型或常见场景推测、补充或编造任何事实
2. 对于无法从现有信息中确认的内容，使用"据当事人陈述"或"根据现有资料"等限定语
3. 如果某项诉求缺乏证据支撑，明确在文书中注明"尚待补充证据"而非凭空生成
4. 文书长度应与实际信息量相符，不要为了格式完整而填充虚假内容
""".format(
        fields_count=len(all_fields),
        chain_count=len(state.get("evidence_chain", [])),
        desc_len=len(case.description.strip()),
    )
    # 将告知段落注入 prompt（追加在 facts_json 之后）
    # 通过修改 prompt 构造逻辑实现

# 在 quality 报告中记录数据充分性
# 追加到 evaluate_document_generation 的 details 参数
```

### 6.4 需要修改的文件

- `backend/api/agents/nodes/complaint_node.py`：
  - 新增 `_assess_data_sufficiency` 函数
  - 在 LLM 重写分支前插入充分性评估
  - 按等级选择注入 prompt 片段或跳过 LLM 重写
  - 在 quality details 中追加 `data_sufficiency_score`、`data_sufficiency_level`、`missing_dimensions`
- `backend/api/agents/nodes/respond_complaint_node.py`：对称地实施相同的 Gate 3 逻辑

---

## 7. State 新增字段说明

在 `backend/api/agents/state.py` 的 `CaseWorkflowState` 中追加：

```python
# Gate 2 新增
low_quality_evidence_acknowledged: bool  # 用户在 Gate 2 确认低质量后继续
workflow_aborted_by_user: bool           # 用户在 Gate 2 选择终止

# Gate 1 新增（供下游节点读取分类质量概览）
evidence_relevance_ratio: float          # 证据与案件类型的相关性比例
evidence_all_other: bool                 # 是否全部分类为 other
```

---

## 8. 前端适配说明

### 8.1 Gate 2 中断（`missing_information` 类型）

`InterventionPanel` 已支持 `missing_information` 类型（[types/workflow.ts](../frontend/src/types/workflow.ts) 中已声明）。

需要为该类型渲染带单选项的表单，核心字段：

```
radio "action":
  ○ confirm_continue  — 我了解风险，继续生成（输出质量可能较低）
  ● abort             — 终止本次工作流，我将重新上传证据

textarea "notes":  补充说明（可选）
```

在面板上方展示 `payload.diagnostics`：

```
⚠ 证据分析结果
  上传图片：N 张
  可识别为有效证据：0 张（全部归类为"其他"）
  平均识别置信度：XX%
  提取的结构化字段：0 个

  继续生成的文书将主要基于您填写的案件描述，而非实际证据内容，
  输出质量可能显著偏低。
```

### 8.2 Gate 1 警告展示（`QualitySummary` 组件）

在「材料理解」阶段的质量摘要中，当 `details.evidence_all_other == true` 且 `details.evidence_relevance_ratio < 0.3` 时，展示一条橙色警告项：

```
⚠ 证据类型匹配度偏低
  当前案件类型：XX 纠纷
  预期证据类型：XX、XX、XX
  上传证据识别结果：全部为"其他"类型（匹配度 N%）
  建议检查上传的图片是否为相关证据材料
```

### 8.3 Gate 3 文书质量说明（`DocumentEditor` 侧边栏或导出前提示）

当 `artifact.content.quality_details.data_sufficiency_level` 为 `sparse` 或 `critically_sparse` 时，在文书编辑器顶部或导出按钮旁展示：

```
⚠ 提示：本文书基于有限证据生成，建议审核后补充证据并重新生成，或手动编辑完善。
```

---

## 9. 与现有中断机制的兼容性

| 现有中断点 | 类型 | 本方案影响 |
|---|---|---|
| `review_node` | `quality_review` | 无影响 |
| `stage_gate_after_*` | `user_pause` | 无影响 |
| `complaint_node` 法条校验 | `legal_confirmation` | 无影响 |
| **新增** `extract_node` Gate 2 | `missing_information` | 新增，已有模型字段支持 |

Gate 2 使用 `WorkflowIntervention.INTERVENTION_TYPES` 中已存在的 `missing_information` 类型（[models.py:1157](../backend/api/models.py#L1157)），无需修改模型和迁移。

---

## 10. 实施检查清单

### 后端

- [ ] `classify_node.py`
  - [ ] 新增 `CASE_TYPE_EXPECTED_CATEGORIES` 常量
  - [ ] 新增 `_compute_evidence_relevance()` 函数
  - [ ] 在节点末尾追加相关性信息到 `details`
  - [ ] 低相关性时 `quality_status` 降为 `"warn"`

- [ ] `extract_node.py`
  - [ ] 新增 `_is_evidence_critically_insufficient()` 函数
  - [ ] 在 `return make_node_partial_update()` 之前插入 Gate 2 判断
  - [ ] 实现 `interrupt()` 调用及 resume 处理（`confirm_continue` / `abort` 分支）

- [ ] `state.py`
  - [ ] 新增 `low_quality_evidence_acknowledged: bool`
  - [ ] 新增 `workflow_aborted_by_user: bool`
  - [ ] 新增 `evidence_relevance_ratio: float`
  - [ ] 新增 `evidence_all_other: bool`

- [ ] `workflow_runner.py`
  - [ ] 检测 `state.get("workflow_aborted_by_user")` 并调用 `fail_processing`

- [ ] `complaint_node.py`
  - [ ] 新增 `_assess_data_sufficiency()` 函数
  - [ ] LLM 重写前评估充分性
  - [ ] `critically_sparse + 未确认` → 跳过 LLM 重写，返回空内容
  - [ ] `sparse（已确认）` → 注入 `SPARSE_DATA_NOTICE` 到 prompt
  - [ ] quality details 追加充分性字段

- [ ] `respond_complaint_node.py`
  - [ ] 对称实施 Gate 3 逻辑

### 前端

- [ ] `InterventionPanel`（或新建专用面板）
  - [ ] 支持 `missing_information` 类型的单选表单渲染
  - [ ] 展示 `payload.diagnostics` 诊断数据区块

- [ ] `QualitySummary`
  - [ ] 读取 `details.evidence_all_other` 和 `details.evidence_relevance_ratio`
  - [ ] 低于阈值时展示橙色证据匹配度警告

- [ ] `DocumentEditor`（或导出逻辑）
  - [ ] 读取 `content.quality_details.data_sufficiency_level`
  - [ ] `sparse` / `critically_sparse` 时展示顶部提示 Banner

---

## 11. 回归验证要点

实施完成后，需验证以下场景：

| 场景 | 预期行为 |
|---|---|
| 上传 1 张无关图片 + 随意填写案件描述 | Gate 2 触发 `interrupt(missing_information)`，用户看到诊断数据和选项 |
| 用户在 Gate 2 选择 `abort` | 工作流标记为 `failed`，提示"用户终止，请重新上传证据" |
| 用户在 Gate 2 选择 `confirm_continue` | 流程继续，`complaint_node` 注入稀疏数据告知，文书中无捏造事实 |
| 上传 1 张不匹配案件类型的图片（但内容有效，能提取字段） | Gate 2 不触发；`classify_node` 写入低相关性警告；流程正常 |
| 上传 3 张有效证据 + 合理案件描述 | 全程无额外中断，与当前行为完全一致 |
| 用户在 stage_gate 手动暂停后 resume | `interrupt` 行为不受影响，Gate 2 仅在 extract_node 首次执行且条件满足时触发 |

---

## 12. 不在本方案范围内的问题

- **案件描述文本本身的语义合法性校验**（如检测描述是否包含无意义随机字符）：语义检测误判风险高，暂不引入
- **用户身份/权限层面的防滥用**：属于 API 层限流范畴，不在工作流层处理
- **respond_complaint 工作流的 Gate 1/2**：逻辑对称，同步实施即可，设计与上述相同
