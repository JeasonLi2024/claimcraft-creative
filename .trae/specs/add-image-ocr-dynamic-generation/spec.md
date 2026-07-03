# ClaimCraft T0：补全创意核心能力（证据图片 + OCR + 动态生成）Spec

## Why
现有 Demo 的证据管理、时间线、投诉文本均基于静态文本 fixture，未实现创意描述中"截图+聊天记录一键变成可提交投诉包"的核心卖点。本阶段通过引入证据图片上传、OCR 识别、关键信息抽取、时间线自动重建、投诉文本动态生成，让 Demo 真正体现"从截图到投诉包"的自动化链路。

## What Changes

### 数据模型变更
- `Evidence` 模型新增 `image`（ImageField，存 `evidences/<case_id>/`）、`extracted_text`（TextField，OCR 全文）、`ocr_status`（CharField：pending/done/failed，默认 pending）
- 新增 `ExtractedField` 模型：evidence 外键、field_name、field_value、confidence、created_at
- `TimelineNode` 模型新增 `auto_generated`（BooleanField，默认 False）
- 新增 `ComplaintTemplateRule` 模型：template_type、rule_title（Jinja2 标题源码）、rule_content（Jinja2 正文源码）；保留原 `ComplaintTemplate` 向后兼容
- 种子数据迁移：原 3 个 ComplaintTemplate 的静态 content 转换为 ComplaintTemplateRule 的 Jinja2 模板源码

### 后端新增/改造
- 新增 `POST /api/cases/<id>/evidences/upload/`：multipart 图片上传，自动保存、创建 Evidence、触发 OCR
- 新增 `services/ocr_service.py`：默认 Mock OCR（根据图片文件名/内容返回预置文本），预留 Tesseract 接入点
- 新增 `services/extraction_service.py`：正则抽取订单号、金额、手机号、地址、时间、承诺话术
- 改造 `services/timeline_service.py`：新增 `rebuild_timeline(case)`，从证据时间字段自动生成节点
- 新增 `POST /api/cases/<id>/timeline/rebuild/`：触发时间线重建
- 改造 `services/complaint_service.py`：基于证据+时间线+抽取字段用 Jinja2 动态渲染
- 新增 `POST /api/cases/<id>/complaints/regenerate/`：强制重新生成投诉文本
- 新增 `GET /api/evidences/<id>/extracted-fields/` 与 `PATCH /api/extracted-fields/<id>/`
- `settings.py` 新增 MEDIA_ROOT/MEDIA_URL 配置

### 前端改造
- `EvidenceView.vue` 新增拖拽上传区、图片缩略图、OCR 状态、识别结果展开区、抽取字段表
- `TimelineView.vue` 新增"重新生成时间线"按钮
- `ComplaintView.vue` 新增"重新生成"按钮
- `WorkspaceView.vue` 概览卡片新增图片证据数与抽取字段数

### 不变更
- 现有 8 个 API 端点向后兼容（新增字段有默认值）
- 展示页 `claimcraft-creative.html` 不改动
- 现有文本证据与种子数据保留可用

## Impact
- Affected specs: `build-interactive-demo`（向后兼容扩展）
- Affected code:
  - `backend/api/models.py`、`backend/api/migrations/0002_t0_image_ocr.py`
  - `backend/api/services/ocr_service.py`（新建）、`extraction_service.py`（新建）
  - `backend/api/services/timeline_service.py`、`complaint_service.py`（改造）
  - `backend/api/serializers.py`、`views.py`、`urls.py`
  - `backend/requirements.txt`（新增 Pillow、Jinja2）
  - `backend/claimcraft/settings.py`（MEDIA 配置）
  - `frontend/src/views/` 下 4 个视图、`stores/case.js`、`api/case.js`

## ADDED Requirements

### Requirement: 证据图片上传与存储
系统 SHALL 支持用户通过 multipart/form-data 上传截图（jpg/png/webp），后端将图片存入 `media/evidences/<case_id>/`，自动创建 Evidence 记录（image 字段、ocr_status=pending），并同步触发 OCR。

#### Scenario: 上传单张证据截图
- **WHEN** 用户在证据导入视图拖入一张截图并释放
- **THEN** 前端调用 `POST /api/cases/<id>/evidences/upload/`（multipart），后端保存图片、创建 Evidence 记录（code 自动编号、image 指向存储路径、ocr_status=pending），同步执行 OCR 后返回完整证据对象含图片 URL

#### Scenario: 图片格式与大小校验
- **WHEN** 用户上传非图片文件或超过 10MB 的图片
- **THEN** 后端返回 400 错误，提示"仅支持 jpg/png/webp 格式，且不超过 10MB"

### Requirement: OCR 文字识别（Tesseract 优先）
系统 SHALL 通过 ocr_service 对证据图片执行文字识别。默认使用本机已安装的 Tesseract（路径 `D:\tesseract\tesseract.exe`，语言 chi_sim+eng）执行真实 OCR；若 Tesseract 不可用（如路径错误、语言包缺失）则回退 Mock OCR（返回预置识别文本），保证流程不中断。

#### Scenario: Tesseract 真实识别
- **WHEN** ocr_service 调用且 `D:\tesseract\tesseract.exe` 存在
- **THEN** 使用 pytesseract 指定 chi_sim+eng 语言对图片执行识别，返回真实识别文本

#### Scenario: Tesseract 不可用时回退 Mock
- **WHEN** Tesseract 路径不存在或调用抛出异常
- **THEN** 回退 Mock OCR，返回预置识别文本（含订单号、金额、手机号、地址、时间、承诺话术样本），并在日志记录回退原因

#### Scenario: 识别结果存储
- **WHEN** OCR 完成
- **THEN** Evidence.extracted_text 存入识别全文，ocr_status 置为 done；失败置为 failed

### Requirement: 关键信息自动抽取
系统 SHALL 通过 extraction_service 用正则规则从 OCR 文本抽取订单号、金额、手机号、地址、时间、承诺话术，存入 ExtractedField 表。

#### Scenario: 抽取订单号与金额
- **WHEN** OCR 文本含"订单号：202506101234"和"金额：699 元"
- **THEN** 创建 ExtractedField：{field_name: 订单号, field_value: 202506101234}、{field_name: 金额, field_value: 699 元}

#### Scenario: 抽取结果可校正
- **WHEN** 用户编辑某抽取字段值并提交
- **THEN** 前端调用 `PATCH /api/extracted-fields/<id>/`，后端更新 field_value

### Requirement: 时间线自动重建
系统 SHALL 提供 `POST /api/cases/<id>/timeline/rebuild/`，从证据 source_time 与抽取的时间字段自动生成时间线节点（auto_generated=True），清除旧自动节点，保留用户手动节点。

#### Scenario: 重建时间线
- **WHEN** 用户点击"重新生成时间线"
- **THEN** 后端删除该案件 auto_generated=True 的节点，根据证据时间重新生成，返回合并排序后的完整节点列表

#### Scenario: 保留用户手动节点
- **WHEN** 时间线重建执行
- **THEN** auto_generated=False 的手动节点不被删除，与自动节点合并按时间排序

### Requirement: 投诉文本动态生成
系统 SHALL 改造 complaint_service，基于证据列表+时间线+抽取字段，用 Jinja2 渲染 ComplaintTemplateRule 模板源码，动态生成三套投诉文本，自动插入证据编号引用。

#### Scenario: 动态生成平台客服版
- **WHEN** 调用 `generate_complaint(case, 'platform')`
- **THEN** 从 ComplaintTemplateRule 取模板源码，注入 {case, evidences, timeline_nodes, extracted_fields} 上下文，Jinja2 渲染返回 {title, content, template_type}，content 含"（见 E2）"引用

#### Scenario: 重新生成投诉文本
- **WHEN** 用户点击"重新生成"
- **THEN** 前端调用 `POST /api/cases/<id>/complaints/regenerate/`，后端强制重新渲染，返回新文本

### Requirement: 前端证据图片预览与 OCR 结果展示
前端 SHALL 在证据卡片展示图片缩略图（点击放大）、OCR 状态、识别全文、抽取字段表（可校正）。

#### Scenario: 查看证据图片
- **WHEN** 用户点击证据卡片缩略图
- **THEN** 弹出 lightbox 显示原图

#### Scenario: 查看 OCR 识别结果
- **WHEN** 用户展开证据卡片"OCR 识别结果"区
- **THEN** 显示 ocr_status，若完成则显示 extracted_text 与抽取字段表，值可就地编辑

### Requirement: 工作台统计扩展
案件工作台 SHALL 新增"已识别图片证据数"与"抽取字段总数"统计。

#### Scenario: 展示扩展统计
- **WHEN** 用户进入案件工作台
- **THEN** 概览区展示证据数量、关键节点数、投诉版本数、图片证据数、抽取字段数

## MODIFIED Requirements

### Requirement: 证据管理（扩展图片能力）
原：证据为文本描述，支持新增/删除。
现：证据支持文本与图片两种形式。图片证据上传后自动 OCR 与信息抽取。证据卡片根据类型展示图片缩略图或文本描述。

### Requirement: 时间线（扩展自动重建）
原：时间线节点由 fixture 预置，支持就地编辑。
现：支持自动重建（从证据时间字段生成）与手动增删，自动节点与手动节点共存按时间排序。

### Requirement: 投诉文本（扩展动态生成）
原：投诉文本从 ComplaintTemplate 静态 content 读取。
现：由 ComplaintTemplateRule 模板源码经 Jinja2 动态渲染生成。三套模板切换与复制全文保留，新增"重新生成"。
