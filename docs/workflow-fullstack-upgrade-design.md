# ClaimCraft 工作流前后端统一优化升级设计方案

> 文档状态：建议方案  
> 适用范围：ClaimCraft 案件工作台、LangGraph 工作流、证据处理、人工介入、文书生成与前端交互  
> 设计原则：兼容现有实现、分阶段演进、前后端统一、可恢复、可解释、可度量  
> 视觉约束：不使用 Emoji；允许使用 SVG、`lucide-react` 图标及必要的背景图片

---

## 1. 背景与升级目标

当前项目已经具备较完整的 LangGraph 工作流基础，包括：

- 多证据视觉预分类、OCR、分类和字段抽取；
- 低置信度 HITL 人工审核；
- 证据链组织；
- 投诉书和反证答辩书双模式生成；
- Postgres Checkpoint 与状态恢复；
- SSE 事件保留、断线续传与页面回放；
- 业务节点完成后的安全阶段暂停；
- 前端节点轨道、产物流、暂停编辑和流式文书展示。

下一阶段不建议继续简单堆叠工作流节点，而应将当前系统升级为一套：

> 以案件任务为中心、以阶段产物为载体、以质量门为判断依据、允许用户随时理解和介入的法律材料工作台。

本轮升级围绕以下目标展开：

1. 前后端使用同一套工作流领域模型，消除状态、节点和事件定义分散的问题；
2. 从“技术节点展示”升级为“业务阶段展示”，普通用户不需要理解 OCR、RAG 等内部术语；
3. 从“节点是否执行成功”升级为“阶段产物是否达到可用质量”；
4. 统一阶段暂停、低置信度审核和法律风险确认，形成一致的用户介入体验；
5. 保持当前绿色、米白、深墨色的整体视觉风格，强化层级、信息密度和专业感；
6. 支持运行版本、局部重跑、产物失效传播和专业文书编辑；
7. 完善移动端、可访问性、安全性和可观测性。

---

## 2. 总体设计原则

### 2.1 保留现有技术基础

本轮升级不推翻现有 LangGraph、Postgres Checkpointer、EventDepot 和 SSE 能力，而是在其上逐步增加：

- 统一运行实例；
- 统一阶段和产物模型；
- 统一用户介入模型；
- 权威快照；
- 质量门；
- 局部重跑；
- 前端业务化展示。

### 2.2 工作流必须满足四个核心属性

1. **确定性**：节点具有输入输出契约、质量门和失败策略；
2. **可恢复性**：支持版本化 checkpoint、幂等、局部重试和权威快照；
3. **可解释性**：每条结论能追溯到证据、法条和工具调用；
4. **用户控制感**：用户知道系统正在做什么、为什么停、修改会影响什么、失败后如何继续。

### 2.3 前端交互原则

- 面向普通用户展示业务阶段，技术节点作为可展开详情；
- 用户介入必须说明原因、来源和影响；
- 状态不能只通过颜色表达；
- 不使用 Emoji；
- 使用 SVG 或 `lucide-react` 图标；
- 动效只用于状态反馈，不干扰阅读；
- 流式内容不得强制抢夺用户滚动位置；
- SSE 负责增量通知，Snapshot API 负责提供当前真相。

---

## 3. 产品信息架构

### 3.1 双层工作流结构

当前工作流包含以下技术节点：

- `preclassify`
- `ocr`
- `classify`
- `extract`
- `review`
- `evidence_chain`
- `complaint`
- `respond_complaint`

产品层将其聚合成四个业务阶段：

| 业务阶段 | 包含的技术节点 | 面向用户的含义 |
|---|---|---|
| 材料理解 | `preclassify`、`ocr`、`classify` | 识别材料内容并判断证据类型 |
| 事实核对 | `extract`、`review` | 提取主体、金额、时间和争议事实 |
| 案件组织 | `evidence_chain` | 将事实、证据和法律依据组织成链条 |
| 文书生成 | `complaint` / `respond_complaint` | 生成投诉书或反证答辩书 |

### 3.2 两种展示模式

#### 默认业务视图

普通用户只看到四个业务阶段，主要回答三个问题：

- 当前做到哪一步；
- 当前结果是否可信；
- 是否需要用户处理。

#### 展开详情视图

点击“查看处理详情”后展示：

- 技术节点；
- 节点耗时；
- OCR 策略；
- 工具调用；
- 降级情况；
- 质量评分；
- 警告和错误。

---

## 4. 后端统一领域模型

### 4.1 独立工作流运行实例 `WorkflowRun`

当前 `Case` 同时承担案件信息和当前工作流状态。短期保留现有字段以兼容已有逻辑，中期新增独立运行实体：

```python
class WorkflowRun(models.Model):
    STATUS_CHOICES = [
        ("queued", "等待执行"),
        ("running", "执行中"),
        ("pausing", "等待安全暂停"),
        ("waiting_user", "等待用户处理"),
        ("succeeded", "已完成"),
        ("failed", "执行失败"),
        ("cancelled", "已取消"),
    ]

    case = models.ForeignKey(
        Case,
        related_name="workflow_runs",
        on_delete=models.CASCADE,
    )
    thread_id = models.CharField(max_length=100, unique=True)
    workflow_version = models.CharField(max_length=32)
    state_schema_version = models.PositiveIntegerField(default=1)
    policy_version = models.CharField(max_length=32)
    prompt_bundle_version = models.CharField(max_length=32)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    current_stage = models.CharField(max_length=50, blank=True)
    current_node = models.CharField(max_length=50, blank=True)
    progress = models.FloatField(default=0)
    revision = models.PositiveIntegerField(default=1)

    selected_evidence_ids = models.JSONField(default=list)
    run_options = models.JSONField(default=dict)
    quality_summary = models.JSONField(default=dict)

    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

主要收益：

- 一个案件保留多次运行历史；
- 不覆盖旧 `thread_id`；
- 对比不同运行版本；
- 支持局部重跑；
- 统计运行耗时与失败率；
- 明确区分案件状态和 AI 工作流状态。

`Case` 可保留 `active_workflow_run_id`，或通过最新运行查询当前状态。

### 4.2 统一阶段产物 `WorkflowArtifact`

现有产物分布在 `Evidence`、`ExtractedField`、`TimelineNode`、`ComplaintTemplate`、`RespondTemplate`、LangGraph state 和 SSE payload 中。保留现有业务表，并新增统一产物元数据索引：

```python
class WorkflowArtifact(models.Model):
    TYPE_CHOICES = [
        ("evidence_understanding", "材料理解结果"),
        ("extracted_facts", "结构化事实"),
        ("evidence_chain", "证据链"),
        ("legal_references", "法律依据"),
        ("document_draft", "文书草稿"),
        ("quality_report", "质量报告"),
    ]

    workflow_run = models.ForeignKey(
        WorkflowRun,
        related_name="artifacts",
        on_delete=models.CASCADE,
    )
    artifact_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    stage = models.CharField(max_length=50)
    version = models.PositiveIntegerField(default=1)
    revision = models.PositiveIntegerField(default=1)

    status = models.CharField(
        max_length=20,
        choices=[
            ("current", "当前版本"),
            ("stale", "已过期"),
            ("superseded", "已替代"),
        ],
    )

    content = models.JSONField(default=dict)
    source_refs = models.JSONField(default=list)
    quality = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
```

业务表仍是结构化数据的真实来源，`WorkflowArtifact` 用于统一描述：

- 当前阶段产生了什么；
- 产物引用哪些证据；
- 产物质量如何；
- 是否因上游变化而过期；
- 是否需要重新计算。

### 4.3 统一用户介入 `WorkflowIntervention`

当前存在 `review.interrupt` 和 `stage_pause` 两套中断。建议统一为 `WorkflowIntervention`：

```python
class WorkflowIntervention(models.Model):
    TYPE_CHOICES = [
        ("quality_review", "质量审核"),
        ("user_pause", "用户主动暂停"),
        ("legal_confirmation", "法律风险确认"),
        ("missing_information", "缺失信息补充"),
    ]

    workflow_run = models.ForeignKey(
        WorkflowRun,
        related_name="interventions",
        on_delete=models.CASCADE,
    )
    intervention_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    stage = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "待处理"),
            ("submitted", "已提交"),
            ("cancelled", "已取消"),
        ],
    )

    required = models.BooleanField(default=True)
    reason = models.TextField()
    editable_scope = models.JSONField(default=dict)
    form_schema = models.JSONField(default=dict)
    initial_values = models.JSONField(default=dict)
    submitted_values = models.JSONField(default=dict)

    base_revision = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True)
```

统一中断 payload：

```json
{
  "interrupt_type": "workflow_intervention",
  "intervention_id": 38,
  "intervention_kind": "quality_review",
  "required": true,
  "stage": "fact_review",
  "reason": "检测到 3 项关键信息置信度不足",
  "base_revision": 12,
  "form_schema": {
    "sections": []
  },
  "initial_values": {},
  "impact": {
    "stale_artifacts": [
      "evidence_chain",
      "document_draft"
    ]
  }
}
```

前端统一由 `InterventionPanel` 根据 `form_schema` 渲染。

### 4.4 工作流版本字段

工作流初始状态和运行实例必须记录：

```python
workflow_version: str
state_schema_version: int
prompt_bundle_version: str
policy_version: str
```

恢复旧 checkpoint 时：

1. 检查版本兼容性；
2. 可迁移则执行 state migration；
3. 不可迁移则保留旧产物并提示重新发起；
4. 历史文书记录生成时版本，满足审计需求。

---

## 5. 质量门设计

### 5.1 统一节点输出包

每个业务节点输出统一结构：

```python
class NodeResult(TypedDict):
    data: dict
    quality: dict
    warnings: list[dict]
    errors: list[dict]
    provenance: list[dict]
    metrics: dict
```

示例：

```json
{
  "data": {
    "fields": []
  },
  "quality": {
    "score": 0.78,
    "coverage": 0.86,
    "status": "review_required",
    "blocking_issues": 0
  },
  "warnings": [
    {
      "code": "LOW_CONFIDENCE_AMOUNT",
      "message": "付款金额识别结果需要确认",
      "evidence_id": 18
    }
  ],
  "provenance": [
    {
      "claim": "付款金额为 2980 元",
      "evidence_code": "E3",
      "source_region": "page_1:420,235,690,310"
    }
  ],
  "metrics": {
    "duration_ms": 2350,
    "model_calls": 1
  }
}
```

### 5.2 阶段质量规则

#### 材料理解阶段

- 有效证据处理覆盖率；
- OCR 成功率；
- 分类置信度；
- 物证视觉摘要完整度；
- 无法打开的文件数量。

#### 事实核对阶段

- 主体、时间、金额、争议事实完整率；
- 时间是否矛盾；
- 金额是否矛盾；
- 低置信度字段数量；
- 关键字段是否具有证据来源。

#### 案件组织阶段

- 每个关键事实是否引用证据；
- 证据链是否存在时间断点；
- 是否存在只有结论、没有证据的节点；
- 法律检索是否覆盖案件类型。

#### 文书生成阶段

- 法条是否通过真实性验证；
- 文书金额是否与结构化事实一致；
- 主体名称是否一致；
- 是否包含事实、依据、诉求；
- 是否包含无法验证的事实；
- 是否引用过期产物。

### 5.3 错误策略

节点错误分为：

1. 瞬时错误：LLM 限流、网络超时，可重试；
2. 输入错误：图片损坏、无文字，可跳过单条证据或要求补录；
3. 业务阻塞错误：没有有效证据、未生成有效文书，不应继续。

建议节点策略结构：

```python
NodePolicy(
    retryable_errors=(TimeoutError, RateLimitError),
    max_attempts=3,
    backoff="exponential_jitter",
    fallback="structured_output",
    failure_mode="continue_with_warning",
    minimum_output_quality=0.7,
)
```

推荐策略：

| 节点 | 瞬时失败 | 单证据失败 | 整体失败 |
|---|---|---|---|
| 预分类 | 重试后降级 `other` | 允许 | 所有图片失败才阻塞 |
| OCR | 切换 OCR 策略 | 允许 | 全部失败则进入人工补录 |
| 分类 | 使用规则分类 | 允许 | 默认 `other` |
| 抽取 | structured output / 正则降级 | 允许 | 无核心事实则阻塞 |
| 证据链 | 基础时间线降级 | 允许 | 无可引用证据则阻塞 |
| 文书生成 | 重试或模板文书 | 不适用 | 无有效正文必须失败 |

---

## 6. 工作流状态机

统一状态：

```text
idle
  → queued
  → running
  → pausing
  → waiting_user
  → running
  → succeeded

running → failed
running → cancelled
waiting_user → cancelled
failed → queued
```

不再将 `paused` 和 `waiting_review` 作为两个完全独立的顶层状态，而统一为：

```text
status = waiting_user
intervention.kind = user_pause | quality_review | legal_confirmation
```

合法操作由后端返回：

```json
{
  "actions": {
    "can_pause": true,
    "can_resume": false,
    "can_cancel": true,
    "can_retry": false,
    "can_restart_from_stage": false
  }
}
```

前端不自行推断按钮是否显示。

---

## 7. 统一 REST API

### 7.1 创建运行

```http
POST /api/cases/{case_id}/workflow-runs/
```

请求：

```json
{
  "evidence_ids": [12, 15, 18],
  "mode": "standard",
  "intervention_policy": "critical_only",
  "start_from_stage": null,
  "preserve_confirmed_fields": true
}
```

返回：

```json
{
  "run_id": 106,
  "thread_id": "case-42-run-106",
  "status": "queued",
  "stream_ticket": "short-lived-ticket",
  "stream_url": "/api/workflow-runs/106/events/"
}
```

### 7.2 获取权威快照

```http
GET /api/workflow-runs/{run_id}/snapshot/
```

返回：

```json
{
  "run": {
    "id": 106,
    "status": "running",
    "workflow_version": "v11",
    "revision": 12,
    "current_stage": "fact_review",
    "current_node": "extract",
    "progress": 0.46,
    "started_at": "2026-07-17T10:00:00Z"
  },
  "stages": [],
  "active_intervention": null,
  "artifacts": [],
  "issues": [],
  "actions": {
    "can_pause": true,
    "can_resume": false,
    "can_cancel": true,
    "can_retry": false
  }
}
```

### 7.3 请求暂停

```http
POST /api/workflow-runs/{run_id}/pause/
```

### 7.4 提交用户介入

```http
POST /api/workflow-runs/{run_id}/interventions/{intervention_id}/submit/
```

请求：

```json
{
  "base_revision": 12,
  "values": {},
  "action": "continue"
}
```

版本冲突：

```http
409 Conflict
```

```json
{
  "code": "REVISION_CONFLICT",
  "detail": "阶段产物已被更新，请重新加载后再提交",
  "current_revision": 13
}
```

### 7.5 局部重跑

```http
POST /api/workflow-runs/{run_id}/retry/
```

```json
{
  "from_stage": "evidence_reasoning",
  "artifact_ids": [82],
  "preserve_user_confirmed": true
}
```

### 7.6 取消运行

```http
POST /api/workflow-runs/{run_id}/cancel/
```

### 7.7 查询历史运行

```http
GET /api/cases/{case_id}/workflow-runs/
```

---

## 8. SSE 事件协议

### 8.1 职责边界

- SSE：通知增量变化；
- Snapshot API：提供权威当前状态；
- Artifact API：提供完整产物；
- Replay：用于审计、调试和必要的有限回放。

### 8.2 统一事件信封

```json
{
  "event_id": 215,
  "event_type": "stage.updated",
  "run_id": 106,
  "thread_id": "case-42-run-106",
  "revision": 12,
  "occurred_at": "2026-07-17T10:03:20Z",
  "payload": {}
}
```

### 8.3 推荐事件类型

```text
run.started
run.updated
run.completed
run.failed
run.cancelled

stage.started
stage.progress
stage.completed
stage.quality_changed

artifact.created
artifact.updated
artifact.stale

intervention.created
intervention.submitted
intervention.cancelled

document.delta
document.completed

issue.created
issue.resolved
```

### 8.4 前端同步规则

1. 检查 `run_id`；
2. 检查 `event_id` 是否已处理；
3. 检查 `revision`；
4. 轻量事件直接局部更新；
5. revision 跳跃、重连或未知事件时重新获取 snapshot；
6. 文书 Token 流只更新文书内容，不直接改变业务状态。

---

## 9. SSE 鉴权

不再将完整 JWT 放入 query 参数。

### 9.1 短期方案：SSE Ticket

创建工作流时返回短期票据，约束如下：

- 有效期 2～5 分钟；
- 仅可读取指定 `run_id`；
- 不能访问其他 API；
- 可在连接建立后立即失效；
- 日志中只记录票据哈希。

### 9.2 中期方案：Fetch Stream

使用 `fetch` + `ReadableStream`，通过 Header 传递认证：

```typescript
fetch(streamUrl, {
  headers: {
    Authorization: `Bearer ${accessToken}`,
    "Last-Event-ID": String(lastEventId),
  },
})
```

收益：

- 避免 Token 泄露到 URL；
- 支持 `AbortController`；
- 支持心跳超时检测；
- 能区分 HTTP 错误和网络错误。

---

## 10. 前端整体视觉设计

### 10.1 视觉基线

保留当前设计系统：

- 米白背景；
- 深墨绿主色；
- 灰绿色辅助色；
- 克制的低饱和金色强调；
- 大圆角白色卡片；
- 低饱和度阴影；
- 适合长时间阅读的低刺激界面。

不切换回高饱和蓝色科技风。法律材料产品应保持可信、安静、清晰和专业。

### 10.2 建议语义色

```css
:root {
  --status-running: #3f6b57;
  --status-waiting: #9a7428;
  --status-success: #47755e;
  --status-warning: #a86f22;
  --status-error: #b84c42;
  --status-info: #526b78;

  --quality-high: #47755e;
  --quality-medium: #9a7428;
  --quality-low: #b84c42;

  --surface-raised: #ffffff;
  --surface-soft: #f2f4ef;
  --surface-dark: #17231d;
}
```

状态同时使用：

- SVG 图标；
- 文本标签；
- 边框样式；
- 必要时使用不同线型。

---

## 11. 案件工作台升级

### 11.1 桌面端布局

```text
┌────────────────────────────────────────────────────────────┐
│ 案件标题、案件类型、模式、证据数量、更新时间、总体质量      │
│ 当前建议操作                                      主按钮    │
└────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────┬─────────────────────┐
│ 四阶段案件进度                       │ 当前工作流状态       │
│ 1 材料理解                           │ 运行状态             │
│ 2 事实核对                           │ 当前阶段             │
│ 3 案件组织                           │ 预计剩余时间         │
│ 4 文书生成                           │ 连接状态             │
│                                      │ 暂停/继续/取消       │
├──────────────────────────────────────┼─────────────────────┤
│ 当前待处理事项                       │ 质量概览             │
│ 低置信度字段、缺失材料、法律警告     │ 完整度、可信度、风险 │
├──────────────────────────────────────┴─────────────────────┤
│ 最近产物与运行历史                                         │
└────────────────────────────────────────────────────────────┘
```

### 11.2 顶部 Hero

保留现有深墨绿色 Hero，增加：

- 当前运行状态；
- 总体质量评分；
- “继续处理”主按钮；
- 正在运行时显示当前阶段与进度；
- 等待用户时主按钮改为“处理待确认事项”。

### 11.3 推荐流程

不再仅根据业务表数量推断完成情况，改为使用后端阶段状态：

```json
{
  "stage": "fact_review",
  "status": "waiting_user",
  "quality": 0.72,
  "issues_count": 3,
  "artifact_revision": 4
}
```

### 11.4 区分两类状态

- 案件状态：材料准备、处理中、文稿已生成、已归档；
- 分析任务状态：未启动、处理中、等待确认、已完成、失败。

---

## 12. 证据页三栏工作区

桌面端建议布局：

```text
┌──────────────┬───────────────────────────┬────────────────────┐
│ 证据列表     │ 当前证据详情              │ 分析与问题         │
│ E1 订单      │ 原图 / OCR 对照           │ 证据类型           │
│ E2 支付记录  │ 字段来源高亮              │ 识别摘要           │
│ E3 物证      │ 缩放、旋转、区域定位      │ 抽取字段           │
│              │                           │ 可信度与警告       │
└──────────────┴───────────────────────────┴────────────────────┘
```

### 12.1 左栏：证据导航

每条证据显示：

- 缩略图；
- 证据编号；
- 分类；
- 处理状态；
- 问题状态；
- 是否已人工确认；
- 是否需要重算。

支持：

- 多选；
- 批量参与分析；
- 按状态过滤；
- 按类别过滤；
- 仅看待确认项。

### 12.2 中栏：来源阅读器

图片证据：

- 原图；
- 缩放与旋转；
- OCR 文本区域框选；
- 点击字段跳转来源区域；
- 物证视觉摘要。

文本证据：

- OCR 原文；
- 纠错后文本；
- 差异对照。

### 12.3 右栏：结构化分析

标签页：

- 摘要；
- 字段；
- 问题；
- 处理历史。

低置信度字段使用 SVG 线性提示图标，不使用 Emoji。

---

## 13. 工作流运行面板

### 13.1 推荐布局

```text
┌────────────────────────────────────────────────────────────┐
│ 分析任务 #106     执行中      46%         暂停  更多操作    │
│ 材料理解 ━━━━━ 事实核对 ━━━ 案件组织 ━━━ 文书生成          │
└────────────────────────────────────────────────────────────┘

┌──────────────────────────────────┬─────────────────────────┐
│ 当前阶段                         │ 阶段概览                │
│ 正在提取案件关键信息             │ 已处理证据 7/8          │
│ 当前产物、过程说明、流式文书     │ 发现问题 3              │
│                                  │ 质量评分 78             │
└──────────────────────────────────┴─────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 处理记录，可按阶段展开                                     │
└────────────────────────────────────────────────────────────┘
```

### 13.2 `WorkflowCommandBar`

包含：

- 运行编号；
- 状态；
- 总进度；
- 当前阶段；
- 连接状态；
- 暂停；
- 取消；
- 更多菜单：查看运行详情、查看技术节点、查看历史运行、从当前阶段重试。

### 13.3 `BusinessStageStepper`

桌面端使用四段横向轨道，每段展示：

- 阶段名称；
- 状态文本；
- 质量分；
- 问题数量；
- 当前运行细进度。

移动端默认只显示当前阶段，点击后打开底部抽屉查看完整进度。

### 13.4 `CurrentActivityPanel`

默认只展示：

- 当前正在做什么；
- 最近完成的产物；
- 当前需要用户注意的内容；
- 当前文书流式生成。

完整历史放入独立“处理记录”区域，避免页面持续跳动。

---

## 14. 产物展示组件

将技术节点表格逐步升级为业务产物组件：

| 产物 | 组件 |
|---|---|
| 图片理解 | `EvidenceUnderstandingCard` |
| OCR 结果 | `SourceTextCard` |
| 结构化字段 | `FactGrid` |
| 时间线 | `EvidenceTimeline` |
| 法律依据 | `LegalBasisList` |
| 文书 | `DocumentEditor` |
| 质量报告 | `QualitySummary` |

统一产物卡片结构：

1. 标题、状态和版本；
2. 一句业务摘要；
3. 关键指标；
4. 主体内容；
5. 来源与依据；
6. 操作区。

置信度同时提供业务标签：

- 高可信；
- 建议核对；
- 必须确认。

专业用户展开后查看具体百分比。

---

## 15. 统一人工介入界面

将 `ReviewInterruptPanel` 和 `StagePausePanel` 合并为 `InterventionPanel`。

### 15.1 推荐布局

```text
┌────────────────────────────────────────────────────────────┐
│ 需要确认 3 项信息                              必须完成     │
│ 系统无法可靠判断下列信息，请结合原始证据核对。              │
├────────────────────────────────────────────────────────────┤
│ 左：字段编辑                           右：原始证据预览     │
│ 付款金额                                                   │
│ 模型结果：2980 元                                          │
│ 修正值：[              ]                                   │
│ 来源：E3 支付凭证                                          │
│ 修改影响：证据链和文书将被重新计算                         │
├────────────────────────────────────────────────────────────┤
│ 已修改 1/3 项       保存草稿       取消任务    确认并继续  │
└────────────────────────────────────────────────────────────┘
```

### 15.2 必须支持

- 原值和新值；
- 来源证据预览；
- 字段级错误；
- 恢复原值；
- 修改数量；
- 修改影响范围；
- 草稿持久化；
- `base_revision` 冲突检查；
- 提交成功后焦点回到工作流状态区；
- 键盘操作；
- 语义化 dialog 或 section；
- `aria-describedby` 绑定错误文本。

---

## 16. 文书编辑器

生成后的文书升级为双栏专业编辑器：

```text
┌──────────────────────────────────┬─────────────────────────┐
│ 文书正文                         │ 依据与质量              │
│ 可编辑正文                       │ 引用证据                │
│ 段落级来源标记                   │ 引用法条                │
│ 修改痕迹                         │ 风险提示                │
│                                  │ 完整性检查              │
└──────────────────────────────────┴─────────────────────────┘
```

主要能力：

- 自动保存；
- 版本历史；
- 段落级证据引用；
- 点击引用跳转证据；
- 点击法条查看原文；
- 文书质量检查；
- 重新生成选中段落；
- 保留用户修改；
- 全文重新生成前确认影响；
- 标记 AI 生成和用户修改内容。

### 16.1 流式生成行为

- 正文逐段写入；
- 用户主动向上滚动后停止自动跟随；
- 底部显示“回到最新内容”按钮；
- 不抢夺滚动位置；
- 不强制滚动到页面底部。

---

## 17. 错误与恢复中心

错误分级：

| 等级 | 展示 | 示例 |
|---|---|---|
| 阻塞错误 | 红色任务卡，提供恢复动作 | 未生成有效文书 |
| 可恢复问题 | 琥珀色问题卡 | 单张图片 OCR 超时 |
| 提示 | 灰绿色信息条 | 已使用备用抽取策略 |

错误卡内容：

- 发生阶段；
- 对结果的影响；
- 是否已经降级；
- 用户可执行的操作；
- 重试当前阶段；
- 跳过该证据；
- 手动补录；
- 重新上传；
- 查看技术详情。

---

## 18. 启动流程

点击“开始工作流分析”后打开轻量配置抽屉。

### 18.1 基础模式

```text
准备分析 8 份材料

案件类型：服务违约
生成目标：投诉文书
处理模式：标准分析

系统会：
1. 理解材料
2. 提取关键信息
3. 组织事实与依据
4. 生成文书

预计耗时：约 3～6 分钟
执行过程中可以在阶段结束后暂停。

取消       开始分析
```

### 18.2 高级设置

- 选择参与证据；
- 标准、快速、严谨模式；
- 人工介入策略；
- 是否保留已确认字段；
- 从哪个阶段开始；
- 是否重新生成已有文书。

高级设置默认折叠。

---

## 19. 前端状态管理

建议将现有 Zustand store 拆为三个 slice：

```text
caseSlice
  - 案件信息
  - 证据
  - 时间线
  - 文书

workflowRunSlice
  - 当前运行快照
  - 阶段状态
  - 连接状态
  - 事件游标
  - actions

interventionSlice
  - 当前介入任务
  - 编辑草稿
  - validation
  - revision
```

统一状态：

```typescript
interface WorkflowRunState {
  run: WorkflowRunSummary | null
  stages: WorkflowStage[]
  artifacts: WorkflowArtifactSummary[]
  activeIntervention: WorkflowIntervention | null
  issues: WorkflowIssue[]
  actions: WorkflowAllowedActions
  connection: WorkflowConnectionState
  latestEventId: number
  snapshotRevision: number
}
```

更新策略：

- SSE 事件先经过 `workflowEventReducer`；
- revision 不连续时重新获取 snapshot；
- 编辑草稿使用 `sessionStorage`；
- 草稿 key 包含 `runId + interventionId + revision`；
- run 切换时销毁旧连接和旧草稿；
- 暂不强制引入 XState，先将状态转移抽成纯 reducer 并补测试。

---

## 20. 前端组件规划

```text
components/workflow/
  WorkflowCommandBar
  BusinessStageStepper
  CurrentActivityPanel
  StageSummaryCard
  StageDetailDrawer
  ArtifactTimeline
  ArtifactCard
  QualityBadge
  QualitySummary
  IssueList
  IssueCard
  InterventionPanel
  InterventionField
  EvidenceSourceViewer
  RunHistoryDrawer
  RunConfigurationDrawer
  WorkflowRecoveryPanel
  DocumentEditor
  DocumentSourcePanel
```

### 20.1 SVG 图标规范

继续使用 `lucide-react`，必要时补充自定义 SVG。

| 语义 | 图标 |
|---|---|
| 材料理解 | `ScanSearch` |
| 事实核对 | `ListChecks` |
| 案件组织 | `GitBranch` 或 `Network` |
| 文书生成 | `FilePenLine` |
| 等待确认 | `CircleAlert` |
| 已确认 | `BadgeCheck` |
| 证据来源 | `Link2` |
| 法律依据 | `Scale` |
| 暂停 | `PauseCircle` |
| 重试 | `RotateCcw` |
| 版本历史 | `History` |
| 质量检查 | `ShieldCheck` |

自定义 SVG 规范：

- `fill="none"`；
- `stroke="currentColor"`；
- `strokeWidth="1.75"`；
- `strokeLinecap="round"`；
- `strokeLinejoin="round"`；
- 装饰图标提供 `aria-hidden="true"`；
- 独立图标按钮提供 `aria-label`。

---

## 21. 响应式设计

### 21.1 桌面端，宽度 ≥ 1280px

- 三栏证据工作区；
- 双栏工作流当前活动区；
- 文书正文与依据双栏；
- 四阶段横向步骤条；
- 保留案件侧边导航。

### 21.2 平板，768～1279px

- 证据列表和详情双栏；
- 分析面板改为右侧抽屉；
- 工作流阶段保持横向；
- 文书依据改为可收起侧栏。

### 21.3 手机，< 768px

- 单栏页面；
- 当前阶段卡靠前展示；
- 完整步骤放底部抽屉；
- 主操作栏固定在底部安全区；
- 证据预览全屏；
- 人工介入逐字段处理；
- 不使用两列超小卡片；
- 最小正文 14px；
- 主要按钮最小高度 44px；
- 输入区域适配虚拟键盘；
- 不使用固定 `min-h-[600px]`。

---

## 22. 动效规范

- 阶段进度：200～300ms；
- 卡片展开：180ms；
- 抽屉：220ms；
- 新产物出现：轻微淡入和 4px 上移；
- 正在运行：SVG 环形进度或低频明暗变化；
- 不使用大范围粒子作为工作台背景；
- 不使用持续闪烁；
- 不让流式内容强制抢夺滚动位置；
- 继续遵循 `prefers-reduced-motion`。

`ParticleBackground` 可保留在首页或登录页，不建议用于证据页、工作流页和文书编辑页。

---

## 23. 背景图片与生图 Prompt

工作台和工作流页面本身不建议使用写实背景图，原因包括：

- 页面信息密度高；
- 背景图降低文字对比度；
- 法律材料产品需要克制和可信；
- 图片增加加载成本；
- 现有渐变和 SVG 装饰已足够。

建议只在首页 Hero、登录注册页、空状态和首次工作流引导页考虑图片。

### 23.1 首页 Hero 背景

图片描述：

> 一张克制、现代、可信赖的法律科技主题概念插画。画面主体为一张半透明的案件材料工作台，包含叠放的文件、证据照片轮廓、时间线节点、相互连接的证据关系线，以及一份正在生成的正式文书。整体采用深墨绿色、灰绿色、暖米白和少量低饱和金色，不出现人物脸部，不出现真实公司名称，不出现可辨识文字，不出现法槌等过度传统的法律符号。使用精细的三维纸张层次与轻微玻璃质感，光线柔和，背景干净，有足够留白用于叠加标题，专业、安静、可信，16:9 横版。

生图 Prompt：

```text
为法律科技产品 ClaimCraft 生成一张 16:9 横版网页 Hero 背景图。画面表现一个现代化的案件材料工作台：半透明分层文件、证据照片轮廓、结构化事实卡片、时间线节点、细线连接形成的证据链，以及一份正在生成的正式法律文书。视觉风格克制、专业、可信赖，采用深墨绿色、灰绿色、暖米白和少量低饱和金色，柔和侧光，细腻纸张质感与轻微玻璃质感结合，背景简洁，右侧主体清晰，左侧保留大面积低对比留白用于网页标题。不要人物，不要人脸，不要真实文字，不要 logo，不要水印，不要 emoji，不要夸张法槌或法庭元素，高级产品视觉，4K。
```

### 23.2 登录页视觉图

图片描述：

> 抽象的证据组织过程：散落的材料卡片沿着柔和曲线逐步汇聚为清晰时间线和完整文书，表现“从碎片到有序”的过程。

生图 Prompt：

```text
生成一张用于法律材料整理产品登录页右侧的竖版概念插画，比例 4:5。表现散落的证据材料卡片、照片轮廓、付款记录和对话框轮廓，沿着清晰但柔和的连线逐步汇聚为结构化时间线，最终形成一份完整正式文书。整体抽象而不失可理解性，现代编辑风格与轻微三维纸张质感，深墨绿色、灰绿色、米白、少量低饱和金色，柔和光线，安静、可靠、有秩序。不要人物，不要真实文字，不要 logo，不要水印，不要 emoji，不要法槌。
```

### 23.3 空状态插画

优先使用 SVG。SVG 构图：

- 中心为两张略微错位的文件；
- 左侧一张证据图片轮廓；
- 右侧三个时间线圆点；
- 中间以细线连接；
- 底部一个带加号的上传托盘；
- 使用 `currentColor` 和两级透明度；
- 不使用复杂渐变；
- 宽高比 4:3；
- 适合 160～240px 展示。

位图 Prompt：

```text
生成一张极简法律材料工作台空状态插画，4:3 比例，白色和暖米白背景。画面中心是两张轻微错位的文件纸张，旁边有一张证据图片卡片轮廓和三个由细线连接的时间线节点，底部有简洁的上传托盘。深墨绿色和灰绿色线条，少量低饱和金色点缀，大面积留白，扁平矢量风格，边缘清晰。不要文字，不要人物，不要 logo，不要水印，不要 emoji。
```

---

## 24. 无障碍验收要求

1. 动态状态区域具备 `aria-live="polite"`；
2. 阻塞错误具备 `role="alert"`；
3. 人工介入出现后，将焦点移动到面板标题；
4. 弹窗和抽屉支持 `Escape` 关闭与焦点锁定；
5. 所有图标按钮具有 `aria-label`；
6. 状态不能只靠颜色表达；
7. 表单错误通过 `aria-describedby` 关联；
8. 主要操作可通过键盘完成；
9. 触控目标不小于 44 × 44px；
10. 对比度满足 WCAG AA；
11. 动画遵循 `prefers-reduced-motion`；
12. 流式内容不自动抢夺屏幕阅读器焦点。

---

## 25. 分阶段实施计划

### 25.1 第一阶段：统一契约与体验修复，1～2 周

后端：

- 定义统一 Snapshot Schema；
- 统一 SSE event envelope；
- 增加 workflow/state schema version；
- 增加节点错误分类；
- 增加工作流集成测试；
- 引入短期 SSE ticket；
- 保持现有 API 兼容。

前端：

- 增加四业务阶段映射；
- 重构 `NodeTrack` 为 `BusinessStageStepper`；
- 修复移动端固定高度；
- 调整自动滚动逻辑；
- 增加 ARIA live、alert 和表单错误关联；
- 错误按阻塞、警告、提示分组；
- 启动按钮增加防重复与准备摘要。

验收：

- 刷新后状态准确恢复；
- SSE 重连后 snapshot 与 UI 一致；
- 移动端无横向溢出；
- 键盘可完成工作流主要操作；
- access token 不再出现在 SSE URL。

### 25.2 第二阶段：统一用户介入与质量门，2～3 周

后端：

- 增加 `WorkflowIntervention`；
- 统一阶段暂停与低置信度审核；
- 增加质量评分和阶段问题；
- 增加 revision 冲突控制；
- 增加用户确认字段标记。

前端：

- 实现统一 `InterventionPanel`；
- 增加原始证据预览；
- 增加字段 Diff；
- 增加草稿保存；
- 增加修改影响提示；
- 增加 `QualitySummary` 与 `IssueList`。

验收：

- 用户不会连续遇到两套人工编辑面板；
- 刷新后编辑草稿可恢复；
- 两端并发修改返回 409；
- 每个低置信度字段可追溯到证据来源。

### 25.3 第三阶段：运行实例与局部重跑，3～4 周

后端：

- 增加 `WorkflowRun`；
- 增加 `WorkflowArtifact`；
- 支持多运行历史；
- 支持从指定阶段重跑；
- 支持产物 stale 状态；
- 建立产物依赖关系。

前端：

- 运行历史抽屉；
- 启动配置抽屉；
- 证据选择；
- 从阶段重试；
- 过期产物提示；
- 运行版本对比。

验收：

- 一个案件可保留多次运行；
- 修改 OCR 后只失效相关下游产物；
- 可从证据链或文书阶段重跑；
- 用户人工确认字段默认不会被覆盖。

### 25.4 第四阶段：专业文书工作台，3～5 周

后端：

- 段落级证据与法条引用；
- 文书版本历史；
- 局部段落重新生成；
- 法律引用一致性校验；
- 导出前质量门。

前端：

- 双栏文书编辑器；
- 证据和法条侧栏；
- 段落来源；
- 修改历史；
- 风险提示；
- 导出前检查清单。

---

## 26. 测试方案

### 26.1 后端测试

必须覆盖：

- 完整工作流启动、完成和失败；
- 节点超时、重试、降级与阻塞；
- 用户暂停、低置信度审核和统一介入；
- checkpoint 恢复；
- 服务重启后恢复；
- 同一运行重复启动或重复恢复；
- revision 冲突；
- SSE 事件顺序和断线续传；
- Snapshot 与事件最终一致；
- 局部重跑；
- 产物 stale 传播；
- 工作流版本不兼容处理；
- 工具调用轮次和总调用次数限制；
- 法条验证失败时文书质量门阻塞。

### 26.2 前端测试

必须覆盖：

- 四阶段状态映射；
- Snapshot 初始化；
- SSE 增量更新；
- revision 跳跃后重新获取 Snapshot；
- 重连和 fatal error；
- 用户介入草稿恢复；
- 409 冲突提示；
- 流式文书停止自动跟随；
- 移动端布局；
- 键盘操作；
- ARIA live 与 alert；
- reduced motion。

### 26.3 端到端场景

至少覆盖：

1. 普通投诉完整流程；
2. 商家反证完整流程；
3. 含纯物证图片的流程；
4. 低置信度字段人工修正；
5. 用户主动暂停并编辑；
6. 暂停后刷新并恢复；
7. SSE 中断并重连；
8. OCR 单证据失败后降级；
9. 文书生成失败后阶段重试；
10. 修改上游字段后局部重算；
11. 移动端完成人工确认；
12. 并发编辑 revision 冲突。

---

## 27. 核心量化指标

### 27.1 工作流指标

- 总成功率；
- 节点首次成功率；
- 节点降级率；
- 节点重试成功率；
- P50/P95 总耗时；
- Checkpoint 恢复成功率；
- SSE 重连成功率；
- Snapshot revision 冲突率。

### 27.2 质量指标

- OCR 有效覆盖率；
- 字段人工校正率；
- 证据链引用覆盖率；
- 法条校验通过率；
- 文书一次通过率；
- 文书生成后用户修改比例；
- 过期产物误用率。

### 27.3 用户体验指标

- 启动后中途放弃率；
- 暂停后恢复率；
- 人工审核完成时间；
- 错误后恢复成功率；
- 移动端任务完成率；
- 导出前返回修改比例。

---

## 28. 风险与兼容策略

### 28.1 数据迁移风险

- 第一阶段不立即移除 `Case` 上现有工作流字段；
- `WorkflowRun` 引入后进行双写；
- 稳定后再将读取切换到新实体；
- 旧运行转换成只读历史记录。

### 28.2 API 兼容风险

- 保留现有 `/workflow/start/`、`/stream/`、`/resume/` 等端点；
- 新 API 通过 `/workflow-runs/` 提供；
- 前端逐模块迁移；
- 旧端点在新接口稳定后标记弃用。

### 28.3 Checkpoint 兼容风险

- 所有运行记录版本字段；
- 恢复前进行版本检查；
- 提供状态迁移函数；
- 无法迁移时不强制恢复，保留产物并提示重新运行。

### 28.4 前端复杂度风险

- 暂不立即引入新的大型状态机依赖；
- 先拆 Zustand slice；
- 事件处理抽成纯 reducer；
- 组件按业务阶段渐进替换；
- 保持现有组件作为兼容回退。

---

## 29. 推荐落地顺序

1. 统一 Snapshot、SSE 信封和版本字段；
2. 将前端八个技术节点压缩为四个业务阶段；
3. 统一低置信度审核与阶段暂停；
4. 引入质量门和问题分级；
5. 修复 SSE 鉴权和自动滚动；
6. 增加工作流集成测试；
7. 引入 `WorkflowRun` 和多次运行历史；
8. 实现局部重跑和产物过期传播；
9. 升级为段落级证据引用的专业文书编辑器。

该顺序保证每一步均可独立交付，不会一次性重构掉当前已经稳定运行的 LangGraph、SSE 和阶段暂停能力。

---

## 30. 最终目标

完成升级后，ClaimCraft 的核心能力不只是“生成一份投诉书”，而是形成完整、可靠、可解释的案件材料闭环：

```text
证据输入
  → 材料理解
  → 结构化事实
  → 用户确认
  → 证据与法律推理
  → 可追溯文书
  → 安全检查与导出
```

最终产品应让用户清楚知道：

- 系统正在处理什么；
- 当前结果为什么可信；
- 哪些信息需要确认；
- 每个结论来自哪份证据；
- 每条法律依据是否经过验证；
- 用户修改会影响哪些后续产物；
- 发生失败时可以从哪里继续。

这将使现有系统从“可运行的 AI 工作流”升级为“可用于真实案件材料整理的专业工作台”。
