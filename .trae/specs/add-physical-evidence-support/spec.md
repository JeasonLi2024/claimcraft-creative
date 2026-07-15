# 纯物证图片支持优化 — 规格说明

## 背景与目标

当前工作流假设所有图片证据都含可识别文字（OCR 必跑）。对于无文字的物证图片（如商品损坏照片、现场环境照、实物对比照），OCR 会返回空字符串或命中 Mock 兜底文本，浪费调用配额且对证据链无实际贡献。

本次优化引入"纯物证图片"显式标记机制：
- 用户上传时勾选"纯物证图片"并填写简要说明
- 系统跳过 OCR 节点，但 Captioner 仍生成视觉摘要
- 证据链 LLM 明确知晓哪些证据为物证，作为事实佐证使用

## 范围

### In Scope
1. `Evidence` 模型新增 `is_physical_evidence` + `physical_note` 字段
2. `EvidenceSerializer` 暴露新字段；`EvidenceUploadView` / `EvidenceListCreateView` 接收新字段
3. `ocr_node` 跳过 `is_physical_evidence=True` 的证据
4. `preclassify_node` 的 PRECLASSIFY_PROMPT 注入 `physical_note`，引导对无文字图片输出场景描述
5. `evidence_chain_node` 的 EVIDENCE_CHAIN_PROMPT 明确告知 LLM 物证证据的处理方式
6. 前端 `EvidencePage` 上传弹窗支持勾选"纯物证图片"+ 填写说明
7. 前端 `Evidence` 类型 + `evidenceApi.upload` 支持 `isPhysicalEvidence` + `physicalNote`

### Out of Scope
- 物证图片的图像识别（物体检测/分割）— 仅依赖 Captioner 的视觉描述能力
- 工作流节点新增 — 不增加节点，仅在现有节点内部加分支
- 数据迁移 — 新字段 default=False，对存量数据无影响

## 数据模型变更

### Evidence 模型新增字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `is_physical_evidence` | `BooleanField` | `False` | 是否为纯物证图片（无文字内容） |
| `physical_note` | `CharField(max_length=500)` | `''` | 用户提供的物证说明（损坏程度/现场环境/物证特征等） |

**设计决策**：
- `physical_note` 用 CharField(500) 而非 TextField — 简要说明而非长文，500 字足够
- 不新增 `is_ocr_skipped` 字段 — `is_physical_evidence=True` 即隐含跳过 OCR
- 不改动 `ocr_status` 枚举 — 物证图片 `ocr_status` 保持 `pending`（工作流未处理）或显式置为 `done`+空文本（见下方决策）

### `ocr_status` 对物证图片的取值决策

**采用方案 A**：物证图片在 `ocr_node` 中被显式跳过，置 `ocr_status='done'` + `extracted_text=''`，并在 `ocr_results` 中返回 `ocr_strategy_used='skipped_physical'`。

**理由**：
- `done` 状态让前端 UI 显示"已处理"而非"处理中"
- `skipped_physical` 策略名让 LangSmith Trace 和日志能区分跳过原因
- 空字符串 `extracted_text` 表示无文字，evidence_chain 用 `ocr_summary` 兜底（现有逻辑已支持）

## API 契约

### 1. 上传证据图片（增强）
`POST /cases/<id>/evidences/upload/`

**新增可选表单字段**：
- `is_physical_evidence` (string `'true'`/`'false'`，默认 `'false'`) — multipart 表单中所有值均为字符串
- `physical_note` (string，最长 500 字，默认 `''`)

**后端处理逻辑**：
- 若 `is_physical_evidence='true'`：
  - 保存 evidence 时置 `ocr_status='done'`、`extracted_text=''`（跳过同步 OCR）
  - 跳过 `extraction_service.extract_fields`（无文本可抽取）
  - 字段抽取在 `extract_node` 中也会被跳过（通过 state 过滤）
- 若 `is_physical_evidence='false'`：保持现有同步 OCR + 字段抽取流程

### 2. 新增证据（JSON）
`POST /cases/<id>/evidences/`

`EvidenceSerializer` fields 增加 `is_physical_evidence` + `physical_note`，接受 JSON 字段（布尔值和字符串）。

### 3. 更新证据
`PATCH /evidences/<id>/`（现有）

允许更新 `physical_note`，但 `is_physical_evidence` 一旦证据被创建后不可更改（防止状态不一致）— 通过 `read_only_fields` 限制。

## 工作流节点变更

### preclassify_node（视觉预分类）

**Prompt 增强**：在 `PRECLASSIFY_PROMPT` 中注入 `physical_note`（若存在）。

```python
PRECLASSIFY_PROMPT = """请分析这张维权证据图片，输出 JSON：
{...}

{physical_note_section}

仅输出 JSON，不要其他内容。"""
```

**`physical_note_section` 动态拼接**（在节点中构造，非模板常量）：
- `is_physical_evidence=True` 且 `physical_note` 非空：
  ```
  【重要】用户已标注此图片为"纯物证图片"，无文字内容。
  用户提供的说明：{physical_note}
  
  请结合用户说明，重点描述：
  - 物证的外观特征（如损坏程度、磨损位置、变形情况）
  - 现场环境（如拍摄地点、周围环境、光照条件）
  - 物证特征（如品牌标识、型号、颜色、尺寸）
  - 与案件的关联性（如"商品收到时已破损"、"施工现场未按合同执行"）
  
  evidence_category 应选 work_record / other / communication_record 等物证类，不要选需要文字的类别（如 chat_screenshot / product_order）。
  ```
- `is_physical_evidence=False` 或 `physical_note` 为空：`physical_note_section = ""`

**实现位置**：在 `preclassify_node._process_one` 中读取 `evidence.is_physical_evidence` + `evidence.physical_note`，拼接 prompt 后传给 LLM。

### ocr_node（OCR 识别）

**跳过逻辑**：在确定待处理证据列表后、执行 OCR 前，过滤掉 `is_physical_evidence=True` 的证据。

```python
# 过滤纯物证图片（跳过 OCR）
physical_evidences = [e for e in evidences if e.is_physical_evidence]
ocr_evidences = [e for e in evidences if not e.is_physical_evidence]

# 为物证图片构造跳过结果
skip_results = [
    {
        "evidence_id": e.id,
        "evidence_code": e.code,
        "image_path": e.image.path,
        "ocr_raw_text": "",
        "ocr_corrected_text": "",
        "ocr_strategy_used": "skipped_physical",
        "ocr_status": "done",
        "evidence_category": preclassify_map.get(e.id, ""),
        "errors": [],
    }
    for e in physical_evidences
]

# 仅对 ocr_evidences 执行 OCR
results = await asyncio.gather(*[_process_one(e) for e in ocr_evidences])
ocr_results = [r for r in results if isinstance(r, dict)] + skip_results
```

**日志**：`logger.info(f"跳过 {len(physical_evidences)} 条纯物证图片的 OCR")`

**State 传递**：物证图片仍出现在 `evidence_ocr_results` 中（`ocr_corrected_text=''`），确保下游节点能看到这些证据存在。

### extract_node（字段抽取）

**检查现有逻辑**：`extract_node` 是否会自动跳过 `ocr_corrected_text=''` 的证据？

**预期行为**：
- 若 `extract_node` 已有空文本跳过逻辑 — 无需修改
- 若无 — 添加过滤：`if not ocr_result.get("ocr_corrected_text"): continue`

### evidence_chain_node（证据链构造）

**`_build_evidences_json` 增强**：在每条证据的 JSON 中增加 `is_physical_evidence` 标记。

```python
evidences.append({
    "evidence_code": o["evidence_code"],
    "ocr_summary": ocr_summary,
    "category": category_map.get(eid, "other"),
    "fields": fields_map.get(eid, []),
    "is_physical_evidence": physical_map.get(eid, False),  # 新增
})
```

**`physical_map` 构造**（从 ocr_results 或单独查询）：
```python
physical_map = {
    o["evidence_id"]: o.get("is_physical_evidence", False)
    for o in ocr_results
}
```

**EVIDENCE_CHAIN_PROMPT 增强**：在"证据列表"说明后追加物证处理指引。

```
证据列表（含分类和字段）：
{evidences_json}

【物证说明】
标记为 "is_physical_evidence": true 的证据为纯物证图片，仅有视觉描述（ocr_summary）无文字内容（ocr_corrected_text 为空）。
处理规则：
- 将物证图片作为事实佐证使用，不能因无文字而忽略
- 在 summary 中说明该物证证明了什么事实（如"E3 显示商品收到时屏幕已碎裂，证明物流损坏"）
- 物证图片的 evidence_codes 仍需关联到对应事件
```

## 前端变更

### 1. 类型定义（types/case.ts）

```typescript
export interface Evidence {
  // ... 现有字段
  is_physical_evidence: boolean
  physical_note: string
}
```

### 2. API（lib/api.ts）

`evidenceApi.upload` 增加可选参数：

```typescript
upload: (caseId: number, file: File, options?: { 
  isPhysicalEvidence?: boolean
  physicalNote?: string
}) => {
  const formData = new FormData()
  formData.append("image", file)
  if (options?.isPhysicalEvidence) {
    formData.append("is_physical_evidence", "true")
  }
  if (options?.physicalNote) {
    formData.append("physical_note", options.physicalNote)
  }
  return apiClient.post<Evidence>(`/cases/${caseId}/evidences/upload/`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data)
}
```

### 3. Store（stores/case-store.ts）

`uploadEvidence` 签名增强：

```typescript
uploadEvidence: (caseId: number, file: File, options?: {
  isPhysicalEvidence?: boolean
  physicalNote?: string
}) => Promise<Evidence>
```

### 4. EvidencePage.tsx — 上传交互

**新增上传弹窗**（替代当前"拖拽即上传"的单一交互）：

当用户拖拽或选择文件后，弹出 Modal：
- 文件预览（缩略图）
- 勾选框："标记为纯物证图片（无文字内容，跳过 OCR）"
- 勾选后显示文本框："物证说明（建议描述损坏程度、现场环境、物证特征等）"
- 按钮："上传" / "取消"

**多文件场景**：对每个文件单独应用同一配置（简化交互，避免每个文件单独弹窗）。

**物证卡片显示**：在证据卡片上加"物证"标签（橙色），并展示 `physical_note`。

## 迁移

- `makemigrations` 生成 `0017_add_physical_evidence_fields.py`
- `migrate` 执行（新字段有 default，对存量数据无影响）
- 无需数据回填

## 验证清单

### 后端
- [ ] `python manage.py makemigrations api` 生成迁移
- [ ] `python manage.py migrate` 执行成功
- [ ] `python manage.py check` 无错误
- [ ] 单元测试：上传物证图片，`ocr_status='done'`、`extracted_text=''`、`is_physical_evidence=True`
- [ ] 单元测试：工作流跳过物证图片 OCR，`ocr_strategy_used='skipped_physical'`
- [ ] 单元测试：preclassify_node 对物证图片的 prompt 包含 physical_note

### 前端
- [ ] `npx tsc --noEmit` 无错误
- [ ] 上传弹窗显示文件预览 + 物证勾选框 + 说明文本框
- [ ] 物证卡片显示"物证"标签和说明
- [ ] 勾选物证后上传，后端 `is_physical_evidence=True`

### 集成
- [ ] 端到端：上传物证图片 → 运行工作流 → 证据链中包含物证节点
- [ ] LangSmith Trace：物证图片在 ocr_node 显示 skipped_physical，在 preclassify_node 包含 physical_note

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 用户忘记勾选物证，OCR 仍跑空文本 | OCR 返回空文本不影响主流程，evidence_chain 用 ocr_summary 兜底（现有逻辑） |
| physical_note 过长导致 prompt 膨胀 | CharField(500) 限制 + 节点内截断到 300 字 |
| 存量证据无 is_physical_evidence 字段 | default=False，序列化返回 false，前端按普通证据处理 |
| extract_node 未跳过空文本证据 | 需检查并添加过滤逻辑（见工作流变更） |
