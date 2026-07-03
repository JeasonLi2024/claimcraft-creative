# T0 Spec：补全创意核心能力（证据图片 + OCR + 动态生成）

## Why

现有 Demo 的证据管理、时间线、投诉文本均基于静态文本 fixture，未实现创意描述中"截图+聊天记录一键变成可提交投诉包"的核心卖点。本阶段通过引入证据图片上传、OCR 识别、关键信息抽取、时间线自动重建、投诉文本动态生成，让 Demo 真正体现"从截图到投诉包"的自动化链路，缩小与创意设想之间的核心差距。

## What Changes

### 数据模型变更
- `Evidence` 模型新增 `image` 字段（ImageField，存储路径 `evidences/<case_id>/<filename>`）、`extracted_text` 字段（TextField，OCR 识别全文）、`ocr_status` 字段（CharField，pending/done/failed）
- 新增 `ExtractedField` 模型：evidence 外键、field_name（订单号/金额/手机号/地址/时间/承诺话术）、field_value、confidence、created_at
- `TimelineNode` 模型新增 `auto_generated` 字段（BooleanField，标记是否自动重建生成）
- 新增 `ComplaintTemplateRule` 模型：template_type、rule_text（Jinja2 模板源码），用于动态渲染投诉文本（替代原 ComplaintTemplate 的静态 content）

### 后端新增/改造
- 新增 `POST /api/cases/<id>/evidences/upload/`：multipart 图片上传，自动保存、创建 Evidence 记录、触发 OCR
- 新增 `services/ocr_service.py`：接入 Tesseract（本地优先）或云端 OCR API，返回识别文本
- 新增 `services/extraction_service.py`：用正则规则从 OCR 文本抽取订单号、金额、手机号、地址、时间、承诺话术
- 改造 `services/timeline_service.py`：新增 `rebuild_timeline(case)`，从证据 source_time + 抽取的时间字段自动生成时间线节点
- 新增 `POST /api/cases/<id>/timeline/rebuild/`：触发时间线重建
- 改造 `services/complaint_service.py`：基于证据列表 + 时间线 + 抽取字段，用 Jinja2 渲染模板动态生成投诉文本
- 新增 `POST /api/cases/<id>/complaints/regenerate/`：强制重新生成投诉文本
- 新增 `GET /api/evidences/<id>/extracted-fields/`：获取某证据的抽取字段列表
- 新增 `PATCH /api/extracted-fields/<id>/`：校正抽取字段值

### 前端改造
- `EvidenceView.vue` 新增拖拽上传区，上传后展示图片缩略图与 OCR 状态（识别中/完成/失败）
- 证据卡片新增"OCR 识别结果"展开区，显示识别全文与抽取字段表，支持校正
- `TimelineView.vue` 新增"重新生成时间线"按钮，调用 rebuild API
- `ComplaintView.vue` 新增"重新生成"按钮，调用 regenerate API；投诉文本切换模板时动态渲染
- `WorkspaceView.vue` 概览卡片增加"已识别图片证据数""抽取字段数"统计

### 不变更
- 现有 8 个 API 端点保持向后兼容（新增字段为可选）
- 展示页 `claimcraft-creative.html` 不改动
- 现有种子数据保留可用（新增字段有默认值）

## Impact

- Affected specs: `build-interactive-demo`（向后兼容扩展）
- Affected code:
  - `backend/api/models.py`（新增字段 + 新模型）
  - `backend/api/migrations/0002_p0_image_ocr_extraction.py`（新增 migration）
  - `backend/api/services/ocr_service.py`（新建）
  - `backend/api/services/extraction_service.py`（新建）
  - `backend/api/services/timeline_service.py`（改造）
  - `backend/api/services/complaint_service.py`（改造）
  - `backend/api/serializers.py`（新增 ExtractedFieldSerializer、扩展 EvidenceSerializer）
  - `backend/api/views.py`（新增 4 个 APIView）
  - `backend/api/urls.py`（新增 4 条路由）
  - `backend/requirements.txt`（新增 pytesseract、Pillow、Jinja2）
  - `frontend/src/views/EvidenceView.vue`（上传区 + 图片预览 + OCR 结果）
  - `frontend/src/views/TimelineView.vue`（重建按钮）
  - `frontend/src/views/ComplaintView.vue`（重新生成按钮）
  - `frontend/src/views/WorkspaceView.vue`（新增统计卡片）
  - `frontend/src/stores/case.js`（新增 uploadEvidence、rebuildTimeline、regenerateComplaint 等 action）
  - `frontend/src/api/case.js`（新增接口封装）

---

## ADDED Requirements

### Requirement: 证据图片上传与存储
系统 SHALL 支持用户通过 multipart/form-data 上传截图（jpg/png/webp），后端将图片存入 `media/evidences/<case_id>/`，并自动创建 Evidence 记录，初始 ocr_status 为 pending。

#### Scenario: 上传单张证据截图
- **WHEN** 用户在证据导入视图拖入一张截图并释放
- **THEN** 前端调用 `POST /api/cases/<id>/evidences/upload/`（multipart），后端保存图片、创建 Evidence 记录（code 自动编号、image 字段指向存储路径、ocr_status=pending），返回完整证据对象含图片 URL

#### Scenario: 上传后自动触发 OCR
- **WHEN** Evidence 记录创建成功
- **THEN** 后端异步或同步调用 ocr_service 识别图片文字，识别完成后将文本存入 extracted_text，ocr_status 置为 done；识别失败置为 failed

#### Scenario: 图片格式与大小校验
- **WHEN** 用户上传非图片文件或超过 10MB 的图片
- **THEN** 后端返回 400 错误，提示"仅支持 jpg/png/webp 格式，且不超过 10MB"

### Requirement: OCR 文字识别
系统 SHALL 通过 ocr_service 对证据图片执行文字识别，返回识别文本。本地优先使用 Tesseract（中文+英文语言包），并提供云端 OCR API 的可选接入点（环境变量配置）。

#### Scenario: 本地 Tesseract 识别
- **WHEN** ocr_service 调用且未配置云端 API
- **THEN** 使用 pytesseract 对图片执行 chi_sim+eng 识别，返回识别文本字符串

#### Scenario: 云端 OCR 回退
- **WHEN** 环境变量 `CLAIMCRAFT_OCR_PROVIDER` 设置为云端服务商
- **THEN** ocr_service 调用对应云端 API，返回识别文本

#### Scenario: 识别失败处理
- **WHEN** OCR 过程抛出异常（如 Tesseract 未安装、图片损坏）
- **THEN** Evidence.ocr_status 置为 failed，extracted_text 留空，不阻断上传流程

### Requirement: 关键信息自动抽取
系统 SHALL 通过 extraction_service 用正则规则从 OCR 识别文本中抽取关键字段，包括订单号、金额、手机号、地址、时间、承诺话术，存入 ExtractedField 表。

#### Scenario: 抽取订单号与金额
- **WHEN** OCR 文本含"订单号：202506101234"和"金额：699 元"
- **THEN** 创建两条 ExtractedField 记录：{field_name: 订单号, field_value: 202506101234}、{field_name: 金额, field_value: 699 元}，confidence 根据匹配规则赋值

#### Scenario: 抽取手机号与地址
- **WHEN** OCR 文本含"联系电话 13812345678"和"收货地址 北京市朝阳区XX路1号"
- **THEN** 创建 ExtractedField 记录：{field_name: 手机号, field_value: 13812345678}、{field_name: 地址, field_value: 北京市朝阳区XX路1号}

#### Scenario: 抽取时间与承诺话术
- **WHEN** OCR 文本含"2025-06-10 09:32"和"48 小时内发货"
- **THEN** 创建 ExtractedField 记录：{field_name: 时间, field_value: 2025-06-10 09:32}、{field_name: 承诺话术, field_value: 48 小时内发货}

#### Scenario: 抽取结果可校正
- **WHEN** 用户编辑某抽取字段值并提交
- **THEN** 前端调用 `PATCH /api/extracted-fields/<id>/`，后端更新 field_value，返回更新后对象

### Requirement: 时间线自动重建
系统 SHALL 提供 `POST /api/cases/<id>/timeline/rebuild/`，从证据的 source_time 与抽取的时间字段自动生成时间线节点，标记 auto_generated=True，并清除旧的自动生成节点（保留用户手动节点）。

#### Scenario: 重建时间线
- **WHEN** 用户点击"重新生成时间线"按钮
- **THEN** 前端调用 rebuild API，后端删除该案件所有 auto_generated=True 的节点，根据证据 source_time 与抽取时间字段重新生成节点，返回新节点列表

#### Scenario: 保留用户手动节点
- **WHEN** 时间线重建执行
- **THEN** auto_generated=False 的用户手动节点不被删除，与自动节点合并后按时间排序返回

#### Scenario: 手动增删节点
- **WHEN** 用户在时间线视图手动新增或删除节点
- **THEN** 新增节点 auto_generated=False，删除节点直接移除，不影响其他节点

### Requirement: 投诉文本动态生成
系统 SHALL 改造 complaint_service，基于证据列表 + 时间线节点 + 抽取字段，用 Jinja2 渲染 ComplaintTemplateRule 中的模板源码，动态生成三套投诉文本（platform/regulatory/arbitration），并自动插入证据编号引用。

#### Scenario: 动态生成平台客服版
- **WHEN** 调用 `generate_complaint(case, 'platform')`
- **THEN** 从 ComplaintTemplateRule 取 platform 模板源码，注入 {case, evidences, timeline_nodes, extracted_fields} 上下文，Jinja2 渲染后返回 {title, content, template_type}，content 含形如"（见 E2）"的证据编号引用

#### Scenario: 重新生成投诉文本
- **WHEN** 用户点击"重新生成"按钮
- **THEN** 前端调用 `POST /api/cases/<id>/complaints/regenerate/`，后端强制重新渲染当前模板类型，返回新文本，前端刷新预览

#### Scenario: 证据变更后引用一致
- **WHEN** 证据列表新增 E5 后重新生成投诉文本
- **THEN** 生成的文本中证据编号引用与当前证据列表一致，不会引用已删除的证据编号

### Requirement: 前端证据图片预览与 OCR 结果展示
前端 SHALL 在证据卡片中展示图片缩略图，点击可放大预览；并展示 OCR 识别状态与结果，支持查看识别全文与抽取字段表。

#### Scenario: 查看证据图片
- **WHEN** 用户点击证据卡片的缩略图
- **THEN** 弹出 lightbox 显示原图，支持关闭

#### Scenario: 查看 OCR 识别结果
- **WHEN** 用户展开证据卡片的"OCR 识别结果"区
- **THEN** 显示 ocr_status（识别中/完成/失败），若完成则显示 extracted_text 全文与抽取字段表（字段名、值、置信度），值可就地编辑

### Requirement: 工作台统计扩展
案件工作台 SHALL 在概览卡片中新增"已识别图片证据数"与"抽取字段总数"统计，数据来自案件详情 API。

#### Scenario: 展示图片证据与抽取字段统计
- **WHEN** 用户进入案件工作台
- **THEN** 概览区展示：证据数量、关键节点数、投诉版本数、已识别图片证据数、抽取字段总数

---

## MODIFIED Requirements

### Requirement: 证据管理（扩展图片能力）
原：证据为文本描述，支持新增/删除。
现：证据支持文本与图片两种形式。图片证据上传后自动 OCR 与信息抽取，文本证据保留原有能力。证据卡片根据类型展示不同内容（图片缩略图或文本描述）。

### Requirement: 时间线（扩展自动重建）
原：时间线节点由 fixture 预置，支持就地编辑。
现：时间线节点支持自动重建（从证据时间字段生成）与手动增删，自动节点与手动节点共存，按时间排序。就地编辑能力保留。

### Requirement: 投诉文本（扩展动态生成）
原：投诉文本从 ComplaintTemplate 静态 content 读取。
现：投诉文本由 ComplaintTemplateRule 模板源码经 Jinja2 动态渲染生成，依赖证据列表、时间线、抽取字段。三套模板切换与复制全文能力保留，新增"重新生成"能力。

---

## 技术选型

| 能力 | 选型 | 理由 |
|---|---|---|
| 图片处理 | Pillow | Django ImageField 依赖，轻量 |
| OCR | pytesseract + Tesseract | 本地优先，零成本，离线可用；中文需 chi_sim 语言包 |
| 模板渲染 | Jinja2 | 灵活强大，Django 内置支持 |
| 异步处理 | 同步优先（Demo 阶段） | OCR 较快，避免引入 Celery 复杂度；后续可升级 |
| 文件存储 | 本地 media 目录 | Demo 阶段足够，后续可换对象存储 |

---

## 验收标准

- [ ] 用户可拖拽上传截图，上传后证据卡片显示缩略图，ocr_status 从 pending 变为 done
- [ ] OCR 识别完成后，证据卡片可展开查看识别全文与抽取字段表
- [ ] 抽取字段表含订单号/金额/手机号/地址/时间/承诺话术，值可校正
- [ ] 点击"重新生成时间线"后，时间线根据证据时间字段重建，手动节点保留
- [ ] 点击"重新生成"投诉文本后，文本根据当前证据与时间线动态渲染，含证据编号引用
- [ ] 删除某证据后重新生成投诉文本，不引用已删除证据编号
- [ ] 案件工作台展示图片证据数与抽取字段数统计
- [ ] 现有文本证据与原 API 端点向后兼容，不破坏已有功能
