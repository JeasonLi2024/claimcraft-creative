# 纯物证图片支持优化 — 验证清单

## 后端

### 模型与迁移
- [ ] `Evidence` 模型新增 `is_physical_evidence` (BooleanField, default=False)
- [ ] `Evidence` 模型新增 `physical_note` (CharField(500), blank=True, default='')
- [ ] `makemigrations` 生成迁移文件 `0017_add_physical_evidence_*.py`
- [ ] `migrate` 执行成功
- [ ] `python manage.py check` 无错误

### 序列化器与视图
- [ ] `EvidenceSerializer.Meta.fields` 包含 `is_physical_evidence` + `physical_note`
- [ ] `EvidenceSerializer.Meta.read_only_fields` 包含 `is_physical_evidence`（创建后不可改）
- [ ] `EvidenceUploadView.post` 读取 `is_physical_evidence` / `physical_note` 表单字段
- [ ] 物证图片上传后 `ocr_status='done'` + `extracted_text=''`
- [ ] 物证图片上传后跳过 `extraction_service.extract_fields`
- [ ] 非物证图片上传行为不变

### 工作流节点
- [ ] **preclassify_node**: prompt 包含 `{physical_note_section}` 占位符
- [ ] **preclassify_node**: 物证图片的 prompt 包含 `【重要】用户已标注此图片为"纯物证图片"`
- [ ] **preclassify_node**: 物证图片的 prompt 包含用户提供的 `physical_note`
- [ ] **preclassify_node**: 非物证图片的 `physical_note_section` 为空字符串
- [ ] **ocr_node**: 过滤 `is_physical_evidence=True` 的证据到 `physical_evidences`
- [ ] **ocr_node**: 为物证构造跳过结果 `ocr_strategy_used='skipped_physical'`
- [ ] **ocr_node**: 仅对非物证证据执行 `asyncio.gather` 调用 OCR
- [ ] **ocr_node**: 日志输出跳过数量
- [ ] **ocr_node**: 物证仍出现在 `evidence_ocr_results` 中（`ocr_corrected_text=''`）
- [ ] **extract_node**: 检查并跳过 `ocr_corrected_text=''` 的证据
- [ ] **evidence_chain_node**: `_build_evidences_json` 增加 `is_physical_evidence` 字段
- [ ] **evidence_chain_node**: `EVIDENCE_CHAIN_PROMPT` 包含"【物证说明】"段
- [ ] **evidence_chain_node**: LLM 输出中物证节点 summary 说明物证事实

## 前端

### 类型与 API
- [ ] `Evidence` 接口增加 `is_physical_evidence: boolean`
- [ ] `Evidence` 接口增加 `physical_note: string`
- [ ] `evidenceApi.upload` 支持 `options` 参数（`isPhysicalEvidence` + `physicalNote`）
- [ ] `uploadEvidence` store 方法透传 `options`
- [ ] `npx tsc --noEmit` 无错误

### UI
- [ ] 拖拽/选择文件后弹出 Modal（替代直接上传）
- [ ] Modal 显示文件预览（缩略图）
- [ ] Modal 包含"标记为纯物证图片"勾选框
- [ ] 勾选后显示"物证说明"textarea
- [ ] 点击"上传"调用 `uploadEvidence(caseId, file, options)`
- [ ] 多文件场景应用同一配置
- [ ] 物证卡片显示橙色"物证"标签
- [ ] 物证卡片显示 `physical_note` 说明文本
- [ ] 物证卡片的展开按钮文案为"图片说明"（非"OCR 识别结果"）
- [ ] 普通图片卡片显示不变

## 集成验证

- [ ] 端到端：上传 1 张物证图片（带说明）+ 1 张普通图片
- [ ] 工作流运行：preclassify 处理两张
- [ ] 工作流运行：ocr 仅处理普通图片，物证显示 skipped_physical
- [ ] 工作流运行：extract 仅处理普通图片
- [ ] 工作流运行：evidence_chain 包含两条证据的节点
- [ ] 证据链 LLM 输出中物证节点 summary 提及物证事实
- [ ] LangSmith Trace：物证图片在 ocr_node 显示 skipped_physical
- [ ] LangSmith Trace：物证图片在 preclassify_node 的 prompt 包含 physical_note

## 边界情况

- [ ] 存量证据 `is_physical_evidence=false`，序列化返回 false，前端按普通证据处理
- [ ] 用户未勾选物证但上传无文字图片：OCR 返回空文本，evidence_chain 用 ocr_summary 兜底
- [ ] `physical_note` 超过 500 字：后端 CharField(500) 截断或报错
- [ ] 多文件上传，部分勾选物证：当前设计同一配置应用到所有文件（简化交互）
