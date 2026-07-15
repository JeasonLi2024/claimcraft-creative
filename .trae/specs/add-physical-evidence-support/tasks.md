# 纯物证图片支持优化 — 任务分解

## 任务依赖

```
A1 (模型字段) → A2 (迁移) → A3 (序列化器+视图)
                           ↓
B1 (preclassify prompt) ─┐
B2 (ocr_node 跳过)      ─┤
B3 (extract_node 检查)  ─┤→ B4 (evidence_chain prompt)
B5 (工作流验证)         ─┘
C1 (类型+API+Store) → C2 (EvidencePage 上传弹窗) → C3 (物证卡片显示) → C4 (前端验证)
```

## A. 后端模型与 API

### A1: Evidence 模型新增字段
**文件**: `backend/api/models.py`

在 `Evidence` 类中 `ocr_summary` 字段后新增：
```python
is_physical_evidence = models.BooleanField(
    '纯物证图片', default=False,
    help_text='标记为纯物证图片（无文字内容），将跳过 OCR 节点'
)
physical_note = models.CharField(
    '物证说明', max_length=500, blank=True, default='',
    help_text='用户提供的物证说明（损坏程度/现场环境/物证特征等）'
)
```

**验证**: `python manage.py check` 无错误

### A2: 生成并执行迁移
**命令**:
```bash
python manage.py makemigrations api --name add_physical_evidence_fields
python manage.py migrate
```

**验证**: 迁移文件 `0017_add_physical_evidence_*.py` 生成，`migrate` 成功

### A3: EvidenceSerializer + 视图增强
**文件**: `backend/api/serializers.py` + `backend/api/views.py`

**serializer.py** `EvidenceSerializer.Meta.fields` 增加 `'is_physical_evidence', 'physical_note'`，`read_only_fields` 增加 `'is_physical_evidence'`（创建后不可改）。

**views.py** `EvidenceUploadView.post`:
- 读取 `is_physical_evidence` / `physical_note` 表单字段
- 物证图片：跳过同步 OCR + 字段抽取，直接置 `ocr_status='done'`、`extracted_text=''`
- 非物证图片：保持现有流程

**验证**: 
- POST 上传物证图片，返回 `is_physical_evidence=true` + `ocr_status='done'` + `extracted_text=''`
- POST 上传普通图片，行为不变

## B. 工作流节点

### B1: preclassify_node prompt 注入 physical_note
**文件**: `backend/api/agents/nodes/preclassify_node.py` + `backend/api/agents/prompts/templates.py`

**templates.py**:
- `PRECLASSIFY_PROMPT` 增加 `{physical_note_section}` 占位符

**preclassify_node.py**:
- 在 `_process_one` 中读取 `evidence.is_physical_evidence` + `evidence.physical_note`
- 构造 `physical_note_section`（物证: 含用户说明 + 描述引导；非物证: 空字符串）
- 注入到 prompt 后传给 LLM

**验证**: LangSmith Trace 中物证图片的 prompt 包含 `【重要】用户已标注此图片为"纯物证图片"`

### B2: ocr_node 跳过物证图片
**文件**: `backend/api/agents/nodes/ocr_node.py`

在 `_process_one` 循环前：
- 过滤 `is_physical_evidence=True` 的证据到 `physical_evidences`
- 为每条物证构造跳过结果（`ocr_strategy_used='skipped_physical'`、`ocr_corrected_text=''`）
- 仅对非物证证据执行 `asyncio.gather` 调用 OCR
- 合并结果到 `ocr_results`

**验证**: 工作流运行后，物证图片的 ocr_result 显示 `skipped_physical`，日志输出跳过数量

### B3: extract_node 跳过空文本证据
**文件**: `backend/api/agents/nodes/extract_node.py`

检查 `extract_node` 是否已自动跳过 `ocr_corrected_text=''` 的证据；若无，添加过滤逻辑。

**验证**: 物证图片不出现在 `evidence_extract_results` 中

### B4: evidence_chain_node prompt 增强
**文件**: `backend/api/agents/nodes/evidence_chain_node.py` + `backend/api/agents/prompts/templates.py`

**evidence_chain_node.py** `_build_evidences_json`:
- 从 ocr_results 或单独查询构造 `physical_map`（evidence_id → is_physical_evidence）
- 每条证据 JSON 增加 `"is_physical_evidence": bool` 字段

**templates.py** `EVIDENCE_CHAIN_PROMPT`:
- 在证据列表说明后追加"【物证说明】"段，明确告知 LLM 物证图片的处理规则

**验证**: 证据链 LLM 输出中包含物证相关节点，summary 提及物证事实

### B5: 工作流端到端验证
- 创建案件 → 上传 1 张物证图片（带说明）+ 1 张普通图片
- 运行工作流
- 检查：preclassify 两张都处理；ocr 仅处理普通图片；evidence_chain 包含两条证据的节点

## C. 前端

### C1: 类型 + API + Store
**文件**: `frontend/src/types/case.ts` + `frontend/src/lib/api.ts` + `frontend/src/stores/case-store.ts`

**case.ts** `Evidence` 接口增加 `is_physical_evidence: boolean` + `physical_note: string`

**api.ts** `evidenceApi.upload` 增加 `options` 参数（见 spec）

**case-store.ts** `uploadEvidence` 签名增强，透传 `options` 到 `api.evidenceApi.upload`

**验证**: `npx tsc --noEmit` 无错误

### C2: EvidencePage 上传弹窗
**文件**: `frontend/src/pages/EvidencePage.tsx`

替换当前"拖拽即上传"逻辑：
- 新增 `UploadDialog` 组件（或 inline Modal）
- 拖拽/选择文件后打开 Modal，显示文件预览
- 勾选框 "标记为纯物证图片（无文字内容，跳过 OCR）"
- 勾选后显示 textarea "物证说明"
- 多文件场景：同一配置应用到所有文件
- 点击"上传"调用 `uploadEvidence(caseId, file, options)`

**验证**: UI 显示弹窗，勾选后显示说明输入框

### C3: 物证卡片显示
**文件**: `frontend/src/pages/EvidencePage.tsx`

证据卡片：
- `is_physical_evidence=true` 时显示橙色"物证"标签
- `physical_note` 非空时在图片下方显示说明文本（小字灰色）
- 替换"OCR 识别结果"展开按钮文案为"图片说明"（物证无 OCR 结果）

**验证**: 物证卡片显示标签和说明

### C4: 前端验证
- `npx tsc --noEmit` 无错误
- 手动测试：上传物证图片 → 卡片显示"物证"标签 + 说明
- 手动测试：上传普通图片 → 行为不变
