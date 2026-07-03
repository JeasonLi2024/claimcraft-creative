# Tasks

- [x] Task 1: 后端数据模型扩展与 migration
  - [x] SubTask 1.1: `Evidence` 模型新增 image（ImageField，upload_to 按 case_id 分目录）、extracted_text（TextField，blank）、ocr_status（CharField，default='pending'）
  - [x] SubTask 1.2: 新增 `ExtractedField` 模型（evidence 外键、field_name、field_value、confidence FloatField、created_at）
  - [x] SubTask 1.3: `TimelineNode` 模型新增 auto_generated（BooleanField，default=False）
  - [x] SubTask 1.4: 新增 `ComplaintTemplateRule` 模型（template_type、rule_title、rule_content），保留原 ComplaintTemplate
  - [x] SubTask 1.5: `settings.py` 新增 MEDIA_ROOT=BASE_DIR/'media'、MEDIA_URL='/media/'
  - [x] SubTask 1.6: 生成并执行 migration `0002_t0_image_ocr`

- [x] Task 2: 后端 OCR 服务（Tesseract 优先，Mock 回退）
  - [x] SubTask 2.1: 新建 `services/ocr_service.py`，实现 `ocr_image(image_path, evidence)` 函数
  - [x] SubTask 2.2: 默认使用本机 Tesseract（pytesseract.pytesseract.tesseract_cmd = `D:\tesseract\tesseract.exe`，lang='chi_sim+eng'）
  - [x] SubTask 2.3: Tesseract 调用异常或路径不存在时回退 Mock OCR，返回预置识别文本（含订单号/金额/手机号/地址/时间/承诺话术样本），日志记录回退原因
  - [x] SubTask 2.4: 异常处理：OCR 失败时返回空字符串并标记 ocr_status=failed
  - [x] SubTask 2.5: `requirements.txt` 新增 pytesseract、Pillow、Jinja2

- [x] Task 3: 后端关键信息抽取服务
  - [x] SubTask 3.1: 新建 `services/extraction_service.py`，实现 `extract_fields(evidence)` 函数
  - [x] SubTask 3.2: 正则规则：订单号（`订单号[：:]\s*(\d+)`）、金额（`(\d+(?:\.\d+)?)\s*元`）、手机号（`1[3-9]\d{9}`）、地址（`([\u4e00-\u9fa5]{2,6}市[\u4e00-\u9fa5\d\w号路街]+)`）、时间（`\d{4}-\d{2}-\d{2}[\s\d:]+`）、承诺话术（`\d+\s*小时.*?发货`）
  - [x] SubTask 3.3: 每条抽取结果创建 ExtractedField 记录，confidence 根据匹配类型赋值（精确匹配 0.9，模糊 0.6）

- [x] Task 4: 后端时间线重建服务改造
  - [x] SubTask 4.1: 改造 `services/timeline_service.py`，新增 `rebuild_timeline(case)` 函数
  - [x] SubTask 4.2: 删除该 case 所有 auto_generated=True 的节点
  - [x] SubTask 4.3: 从证据 source_time 与 ExtractedField 中 field_name='时间' 的值生成新节点（auto_generated=True），event 描述用证据 description
  - [x] SubTask 4.4: 返回合并手动节点与自动节点并按 datetime 排序的完整列表

- [x] Task 5: 后端投诉文本动态生成改造
  - [x] SubTask 5.1: 改造 `services/complaint_service.py`，`generate_complaint(case, template_type)` 改为从 ComplaintTemplateRule 取 Jinja2 源码渲染
  - [x] SubTask 5.2: 构建上下文 {case, evidences, timeline_nodes, extracted_fields}，Jinja2 渲染 rule_title 与 rule_content
  - [x] SubTask 5.3: 模板源码中用 `{{ evidence.code }}` 等变量插入证据编号引用
  - [x] SubTask 5.4: 若 ComplaintTemplateRule 无对应模板类型，回退读原 ComplaintTemplate 静态 content

- [x] Task 6: 后端种子数据迁移与扩展
  - [x] SubTask 6.1: 新增 fixture：3 个 ComplaintTemplateRule 记录（platform/regulatory/arbitration 的 Jinja2 模板源码）
  - [x] SubTask 6.2: Jinja2 模板源码引用 evidences、timeline_nodes、extracted_fields 变量，含"（见 {{ evidence.code }}）"引用
  - [x] SubTask 6.3: 为现有 E1-E8 证据补充预置 ExtractedField 数据（订单号、金额、手机号、地址等），供 Mock OCR 与动态生成使用
  - [x] SubTask 6.4: 现有 TimelineNode 标记 auto_generated=False（用户手动节点）

- [x] Task 7: 后端新增 REST API
  - [x] SubTask 7.1: `serializers.py` 新增 ExtractedFieldSerializer、ComplaintTemplateRuleSerializer，扩展 EvidenceSerializer 含 image/extracted_text/ocr_status
  - [x] SubTask 7.2: 实现 `POST /api/cases/<id>/evidences/upload/`（multipart 上传，校验格式大小，保存图片，创建 Evidence，同步调用 ocr_service + extraction_service）
  - [x] SubTask 7.3: 实现 `GET /api/evidences/<id>/extracted-fields/` 与 `PATCH /api/extracted-fields/<id>/`
  - [x] SubTask 7.4: 实现 `POST /api/cases/<id>/timeline/rebuild/`（调用 timeline_service.rebuild_timeline）
  - [x] SubTask 7.5: 实现 `POST /api/cases/<id>/complaints/regenerate/`（调用 complaint_service 强制重新生成）
  - [x] SubTask 7.6: `urls.py` 注册新路由
  - [x] SubTask 7.7: `urls.py` 根路由追加 media 文件服务（开发环境）

- [x] Task 8: 前端 API 层与 store 扩展
  - [x] SubTask 8.1: `api/case.js` 新增 uploadEvidence、getExtractedFields、updateExtractedField、rebuildTimeline、regenerateComplaint 接口封装
  - [x] SubTask 8.2: `stores/case.js` 新增 uploadEvidence、rebuildTimeline、regenerateComplaint、fetchExtractedFields、updateExtractedField actions

- [x] Task 9: 前端证据导入视图改造
  - [x] SubTask 9.1: `EvidenceView.vue` 顶部新增拖拽上传区（dragover/drop 事件），支持点击选择文件
  - [x] SubTask 9.2: 上传后证据卡片展示图片缩略图（img src 指向 media URL），点击弹出 lightbox
  - [x] SubTask 9.3: 证据卡片新增 OCR 状态标签（识别中/完成/失败）
  - [x] SubTask 9.4: 证据卡片新增"OCR 识别结果"可展开区，显示 extracted_text 与抽取字段表
  - [x] SubTask 9.5: 抽取字段值支持就地编辑，失焦调用 PATCH

- [x] Task 10: 前端时间线视图改造
  - [x] SubTask 10.1: `TimelineView.vue` 顶部新增"重新生成时间线"按钮
  - [x] SubTask 10.2: 点击调用 store.rebuildTimeline(1)，成功后刷新时间线列表
  - [x] SubTask 10.3: 自动生成节点与手动节点视觉区分（auto_generated 节点加"自动"标签）

- [x] Task 11: 前端投诉文本视图改造
  - [x] SubTask 11.1: `ComplaintView.vue` 模板切换器旁新增"重新生成"按钮
  - [x] SubTask 11.2: 点击调用 store.regenerateComplaint(1, currentTemplate)，成功后刷新文本预览

- [x] Task 12: 前端案件工作台视图改造
  - [x] SubTask 12.1: `WorkspaceView.vue` 概览卡片新增"图片证据数"与"抽取字段数"
  - [x] SubTask 12.2: 案件详情 API 返回 image_evidence_count 与 extracted_field_count（后端 CaseSerializer 扩展）

- [x] Task 13: 端到端验证
  - [x] SubTask 13.1: 后端 `python manage.py makemigrations && migrate` 成功
  - [x] SubTask 13.2: 后端 `loaddata` 新增 fixture 成功
  - [x] SubTask 13.3: 上传图片 API 返回证据对象含 image URL 与 ocr_status=done
  - [x] SubTask 13.4: 抽取字段 API 返回订单号/金额/手机号等
  - [x] SubTask 13.5: 时间线 rebuild API 返回含自动节点
  - [x] SubTask 13.6: 投诉文本 regenerate API 返回含证据编号引用的动态文本
  - [x] SubTask 13.7: 前端 `npm run build` 无错误
  - [x] SubTask 13.8: 现有文本证据与原 API 端点向后兼容（不破坏已有功能）

# Task Dependencies
- Task 2 / 3 / 4 / 5 依赖 Task 1（服务依赖模型）
- Task 6 依赖 Task 1（fixture 依赖模型）
- Task 7 依赖 Task 2 / 3 / 4 / 5 / 6（API 调用服务与数据）
- Task 8 依赖 Task 7（前端 API 层依赖后端端点定义）
- Task 9 / 10 / 11 / 12 依赖 Task 8（视图依赖 store）
- Task 9 / 10 / 11 / 12 之间相互独立，可并行实现
- Task 13 依赖 Task 9 / 10 / 11 / 12 全部完成
