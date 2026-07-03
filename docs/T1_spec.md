# ClaimCraft T1：产品闭环（多案件 + 状态流转 + 图片打码导出 + PDF 导出）Spec

> 承接 T0 阶段已补全的"截图→OCR→信息抽取→时间线重建→动态投诉生成"核心链路，本阶段聚焦产品闭环：从"单案件硬编码 Demo"进化为"可管理多案件、可流转状态、可打码导出图片证据包、可生成 PDF 投诉材料"的可用产品。

---

## 一、T0 已完成基础（衔接前提）

T0 已交付以下能力，T1 在此基础上扩展，不重复实现：

| 能力 | T0 交付内容 |
|---|---|
| 证据图片上传 | `Evidence.image` 字段、`POST /api/cases/<id>/evidences/upload/`、前端拖拽上传 + lightbox |
| OCR 识别 | `ocr_service.py`（Tesseract 优先，Mock 回退）、`extracted_text`、`ocr_status` |
| 关键信息抽取 | `ExtractedField` 模型、`extraction_service.py`（6 类正则）、抽取字段可校正 |
| 时间线重建 | `timeline_service.rebuild_timeline`、`auto_generated` 标记、手动/自动节点共存 |
| 动态投诉生成 | `complaint_service.generate_complaint`（Jinja2 渲染 `ComplaintTemplateRule`）、`regenerate` API |
| 数据库 | 已切换 MySQL（claimcraft 库，utf8mb4） |

**T1 不改动**：OCR 服务、抽取服务、Jinja2 模板渲染逻辑、T0 的 5 个新 API 端点行为。

---

## 二、Why

T0 虽补全了核心链路，但 Demo 仍存在三个产品闭环缺口：

1. **单案件硬编码**——前端固定 `case_id=1`，无法创建新案件、无法在多案件间切换，无法作为真实产品使用
2. **无状态流转**——案件没有"草稿/处理中/已提交/已结案"状态，用户无法跟踪维权进度，工作台缺乏进度感知
3. **打码与导出能力缺失**——T0 的打码仅作用于文本，图片证据无法打码；导出仅 .txt，PDF 与图片包为禁用占位，无法产出"可直接提交"的材料

本阶段通过多案件管理、状态流转、图片打码、PDF 导出四项能力，让 Demo 形成完整的产品闭环。

---

## 三、What Changes

### 3.1 多案件管理（Task 22）

#### 数据模型
- `Case` 模型新增字段：
  - `case_type`（CharField，纠纷类型：shopping/service/secondhand/other，默认 shopping）
  - `updated_at`（DateTimeField，auto_now=True）

#### 后端
- 新增 `GET /api/cases/`：案件列表，支持 `search`（标题/描述模糊）、`status`、`case_type` 过滤，返回字段含 id/title/description/case_type/status/created_at/updated_at + 统计字段（evidence_count/image_evidence_count/extracted_field_count）
- 新增 `POST /api/cases/`：创建案件，接收 title/description/case_type
- 扩展 `GET /api/cases/<id>/`：返回完整详情（含 status 字段）
- 新增 `PATCH /api/cases/<id>/`：更新案件标题/描述/类型
- 新增 `DELETE /api/cases/<id>/`：删除案件（级联删除证据、时间线、模板规则）
- `CaseSerializer` 扩展 case_type/status/updated_at 字段

#### 前端
- 新增案件列表视图 `CaseListView.vue`：
  - 卡片网格展示所有案件（标题、类型标签、状态标签、证据数、创建时间）
  - 顶部搜索框 + 类型筛选 + 状态筛选
  - "新建案件"按钮 → 弹窗（标题、描述、纠纷类型下拉）
  - 点击案件卡片进入工作台
- 改造 `WorkspaceView.vue`：去除硬编码 `case_id=1`，从路由参数 `caseId` 获取
- 改造 `App.vue` 路由：新增 `/cases`（列表）、`/cases/:caseId`（工作台）
- 顶部导航新增"我的案件"入口
- `stores/case.js` 新增 `fetchCases`、`createCase`、`updateCase`、`deleteCase` actions，新增 `cases` 列表 state
- `stores/case.js` 改造 `fetchCaseDetail(caseId)`：所有 action 接收 caseId 参数，不再硬编码 1

### 3.2 案件状态流转（Task 23）

#### 数据模型
- `Case` 模型新增字段：
  - `status`（CharField，状态：draft/processing/submitted/closed，默认 draft）
- 新增 `CaseStatusLog` 模型：
  - `case`（ForeignKey Case，related_name='status_logs'，on_delete=CASCADE）
  - `from_status`（CharField，允许 null）
  - `to_status`（CharField）
  - `remark`（TextField，备注，blank）
  - `created_at`（DateTimeField，auto_now_add=True）

#### 后端
- 新增 `POST /api/cases/<id>/status/transition/`：推进状态，接收 `to_status` 与可选 `remark`
  - 校验状态转换合法性（draft→processing→submitted→closed，允许跳过中间态但需 remark）
  - 创建 CaseStatusLog 记录
  - 更新 Case.status
- 新增 `GET /api/cases/<id>/status-logs/`：返回状态变更历史列表
- `CaseSerializer` 扩展 status 字段

#### 前端
- `WorkspaceView.vue` 顶部新增状态条：
  - 显示当前状态（草稿/处理中/已提交/已结案）+ 状态色标
  - "推进状态"按钮 → 弹窗选择目标状态 + 填写备注
  - 状态历史时间轴（点击展开，展示 CaseStatusLog 记录）
- 案件列表卡片显示状态标签

### 3.3 图片打码与证据包导出（Task 24）

#### 数据模型
- `Evidence` 模型新增字段：
  - `masked_image`（ImageField，存 `evidences/<case_id>/masked/`，blank/null）
  - `mask_status`（CharField：none/pending/done，默认 none）

#### 后端
- 新增 `services/image_mask_service.py`：
  - `mask_evidence_image(evidence)`：用 Pillow 对证据图片执行打码
    - 优先方案：基于 OCR 文本中的手机号、地址、身份证号正则匹配，在图片上定位文字区域（pytesseract `image_to_data` 获取坐标）并模糊处理
    - 回退方案：若无法精确定位，对图片底部 1/3 区域（常见地址/联系方式位置）整体高斯模糊
    - 保存打码后图片到 `masked_image` 字段，`mask_status=done`
  - `mask_case_images(case)`：批量打码该案件所有图片证据
- 新增 `POST /api/cases/<id>/mask-images/`：触发该案件图片打码，返回打码后证据列表
- 新增 `GET /api/evidences/<id>/mask-preview/`：返回打码前后图片 URL 对比
- 改造 `export_service.py`：
  - 新增 `export_evidence_package(case, with_images=True)`：生成 ZIP 包，含：
    - `complaint.txt`（投诉文本）
    - `evidence_list.txt`（证据清单）
    - `timeline.txt`（时间线）
    - `images/` 目录（打码后图片，文件名含证据编号 E1_xxx.jpg）
    - `manifest.json`（证据编号与文件名映射）
  - 返回 ZIP 文件流
- 新增 `GET /api/cases/<id>/export/package/?type=zip`：下载证据包 ZIP

#### 前端
- 改造 `MaskView.vue`：
  - 新增"图片打码"区：展示图片证据列表，每张含"打码前/打码后"对比缩略图
  - "一键打码所有图片"按钮 → 调用 `POST /api/cases/<id>/mask-images/`
  - 单张打码按钮 + 打码状态标签（未打码/打码中/已打码）
- 改造 `ExportView.vue`：
  - "证据包导出（ZIP）"选项从禁用改为可用
  - 点击下载 → 调用 `GET /api/cases/<id>/export/package/?type=zip`，触发浏览器下载
  - 导出前提示"是否包含打码后图片"（默认是）

### 3.4 PDF 导出（Task 25）

#### 后端
- `requirements.txt` 新增 `reportlab>=4.0`
- 新增 `services/pdf_service.py`：
  - `generate_complaint_pdf(case, template_type='platform')`：用 reportlab 生成 PDF
    - 页面结构：标题 → 投诉人信息 → 事实经过（时间线）→ 关键信息表 → 诉求 → 证据清单（含图片缩略图与编号）→ 签名区
    - 中文字体：使用 reportlab 内置的 `STSong-Light`（或注册系统 TTF 字体）
    - 证据图片：以缩略图形式嵌入，每张配编号与描述
    - 页眉页脚：页眉显示案件标题，页脚显示页码
  - 返回 PDF 文件流
- 新增 `GET /api/cases/<id>/export/pdf/?template=platform`：下载 PDF

#### 前端
- 改造 `ExportView.vue`：
  - "PDF 文档导出"选项从禁用改为可用
  - 模板选择（platform/regulatory/arbitration）+ 下载按钮
  - 点击下载 → 调用 `GET /api/cases/<id>/export/pdf/?template=xxx`

---

## 四、Impact

- Affected specs: `add-image-ocr-dynamic-generation`（T0，向后兼容扩展，不破坏现有 API）
- Affected code:
  - `backend/api/models.py`（Case 加 case_type/status/updated_at；Evidence 加 masked_image/mask_status；新增 CaseStatusLog）
  - `backend/api/migrations/0003_t1_case_status_mask.py`（新增 migration）
  - `backend/api/services/image_mask_service.py`（新建）
  - `backend/api/services/pdf_service.py`（新建）
  - `backend/api/services/export_service.py`（扩展 ZIP 导出）
  - `backend/api/serializers.py`（CaseSerializer 扩展；新增 CaseListSerializer、CaseStatusLogSerializer；EvidenceSerializer 扩展）
  - `backend/api/views.py`（新增 CaseListCreateView、CaseDetailUpdateDeleteView、CaseStatusTransitionView、CaseStatusLogView、MaskImageView、MaskPreviewView、ExportPackageView、ExportPDFView）
  - `backend/api/urls.py`（新增 8 条路由）
  - `backend/seed_data.json`（现有 Case 补 case_type/status 字段；现有 Evidence 补 mask_status）
  - `backend/requirements.txt`（新增 reportlab）
  - `frontend/src/views/CaseListView.vue`（新建）
  - `frontend/src/views/WorkspaceView.vue`（去硬编码 + 状态条）
  - `frontend/src/views/MaskView.vue`（图片打码区）
  - `frontend/src/views/ExportView.vue`（ZIP + PDF 启用）
  - `frontend/src/App.vue`（路由新增）
  - `frontend/src/router/index.js`（如存在）或 `frontend/src/main.js`（路由配置）
  - `frontend/src/api/case.js`（新增 8 个接口封装）
  - `frontend/src/stores/case.js`（新增 cases 列表 state + 8 个 actions + 去 hardcode）

---

## 五、ADDED Requirements

### Requirement: 案件列表与多案件管理
系统 SHALL 提供案件列表 API 与案件列表视图，支持搜索、类型筛选、状态筛选，支持新建/编辑/删除案件，工作台不再硬编码 case_id。

#### Scenario: 查看案件列表
- **WHEN** 用户访问"我的案件"页面
- **THEN** 展示所有案件的卡片网格，每张卡片含标题、类型标签、状态标签、证据数、创建时间，按更新时间倒序

#### Scenario: 搜索与筛选案件
- **WHEN** 用户在搜索框输入关键词或选择类型/状态筛选
- **THEN** 列表实时过滤，只展示匹配案件

#### Scenario: 新建案件
- **WHEN** 用户点击"新建案件"并填写标题、描述、纠纷类型后提交
- **THEN** 后端创建案件（status=draft），列表新增该案件卡片，点击可进入工作台

#### Scenario: 进入案件工作台
- **WHEN** 用户点击案件卡片
- **THEN** 跳转到 `/cases/:caseId`，工作台加载该案件详情与所有关联数据（证据、时间线、投诉文本），不再固定 case_id=1

#### Scenario: 删除案件
- **WHEN** 用户删除某案件
- **THEN** 后端级联删除该案件的证据、时间线、模板规则、状态日志，列表移除该卡片

### Requirement: 案件状态流转
系统 SHALL 支持案件状态流转（draft→processing→submitted→closed），每次流转记录 CaseStatusLog，工作台展示当前状态与历史。

#### Scenario: 推进案件状态
- **WHEN** 用户在工作台点击"推进状态"并选择目标状态（如 processing）并填写备注
- **THEN** 后端校验转换合法性，更新 Case.status，创建 CaseStatusLog（from_status/to_status/remark），返回新状态

#### Scenario: 状态转换校验
- **WHEN** 用户尝试非法转换（如从 closed 回到 draft）
- **THEN** 后端返回 400 错误，提示"不允许的状态转换"

#### Scenario: 查看状态历史
- **WHEN** 用户在工作台展开"状态历史"
- **THEN** 展示 CaseStatusLog 时间轴，含每次变更的 from→to、备注、时间

### Requirement: 图片打码
系统 SHALL 通过 image_mask_service 对证据图片执行打码（手机号/地址/身份证号区域模糊），保存打码后图片，支持打码前后对比预览。

#### Scenario: 一键打码所有图片
- **WHEN** 用户在打码视图点击"一键打码所有图片"
- **THEN** 后端对该案件所有图片证据执行打码，保存 masked_image，mask_status=done，返回打码后证据列表

#### Scenario: 打码前后对比
- **WHEN** 用户查看某图片证据的打码预览
- **THEN** 展示打码前原图与打码后图并排对比

#### Scenario: 精确定位失败回退
- **WHEN** pytesseract 无法精确定位敏感信息区域
- **THEN** 回退对图片底部 1/3 区域整体高斯模糊，mask_status 仍置 done

### Requirement: 证据包 ZIP 导出
系统 SHALL 提供证据包 ZIP 下载，含投诉文本、证据清单、时间线、打码后图片目录、manifest 映射。

#### Scenario: 下载证据包
- **WHEN** 用户在导出视图点击"证据包导出（ZIP）"
- **THEN** 后端生成 ZIP 文件流，浏览器下载，ZIP 内含 complaint.txt、evidence_list.txt、timeline.txt、images/ 目录（打码后图片）、manifest.json

#### Scenario: 导出包含打码图片
- **WHEN** 案件已有打码后图片
- **THEN** ZIP 的 images/ 目录使用 masked_image；若无打码图则使用原图并标注

### Requirement: PDF 投诉材料导出
系统 SHALL 用 reportlab 生成 PDF 投诉材料，含标题、事实经过、关键信息表、诉求、证据清单（含图片缩略图）、签名区。

#### Scenario: 下载 PDF
- **WHEN** 用户在导出视图选择模板类型并点击"PDF 文档导出"
- **THEN** 后端调用 pdf_service 生成 PDF，浏览器下载，PDF 含完整投诉材料与证据图片缩略图

#### Scenario: PDF 中文字体
- **WHEN** PDF 生成时
- **THEN** 使用中文字体（STSong-Light 或注册的系统 TTF），确保中文不乱码

#### Scenario: PDF 含证据图片
- **WHEN** 案件有图片证据
- **THEN** PDF 的证据清单区以缩略图形式嵌入图片，配编号与描述

---

## 六、MODIFIED Requirements

### Requirement: 案件工作台（去硬编码 + 状态条）
原：工作台固定加载 case_id=1 的案件。
现：工作台从路由参数 `caseId` 加载指定案件，顶部新增状态条（当前状态 + 推进按钮 + 状态历史）。

### Requirement: 隐私打码（扩展图片打码）
原：仅对证据描述文本中的手机号/身份证/地址打码。
现：新增图片打码能力，对证据图片中的敏感信息区域模糊处理，支持打码前后对比与一键全量打码。文本打码能力保留。

### Requirement: 导出（扩展 ZIP 与 PDF）
原：仅支持 .txt 文本包下载，ZIP 与 PDF 为禁用占位。
现：新增证据包 ZIP 导出（含打码图片）与 PDF 投诉材料导出，原 .txt 文本包保留。

---

## 七、技术选型

| 能力 | 选型 | 理由 |
|---|---|---|
| 图片打码 | Pillow + pytesseract `image_to_data` | 复用 T0 的 Tesseract，获取文字坐标精确打码 |
| ZIP 打包 | Python `zipfile` + `BytesIO` | 标准库，无额外依赖 |
| PDF 生成 | reportlab | 纯 Python，跨平台，中文字体支持好 |
| 中文字体 | reportlab `STSong-Light` | 内置 CJK 字体，无需额外字体文件；若不可用回退注册系统 simsun.ttf |
| 状态机校验 | 服务层显式校验 | Demo 阶段避免引入 django-fsm 复杂度 |

---

## 八、任务清单（对应 plan.md Task 22-25）

### Task 22：案件列表与多案件管理
- 后端：Case 加 case_type/updated_at；新增 5 个 API（列表/创建/详情/更新/删除）；CaseSerializer 扩展
- 前端：新建 CaseListView.vue；WorkspaceView 去 hardcode；路由新增 `/cases` 与 `/cases/:caseId`；store 新增 cases 列表与 CRUD actions

### Task 23：案件状态流转
- 后端：Case 加 status；新增 CaseStatusLog 模型；新增状态推进 API + 状态历史 API；转换合法性校验
- 前端：WorkspaceView 状态条 + 推进弹窗 + 状态历史时间轴；列表卡片状态标签

### Task 24：图片打码与证据包 ZIP 导出
- 后端：Evidence 加 masked_image/mask_status；新建 image_mask_service（Pillow 打码 + 回退模糊）；扩展 export_service 支持 ZIP；新增打码 API + 预览 API + ZIP 导出 API
- 前端：MaskView 图片打码区 + 一键打码 + 对比预览；ExportView ZIP 选项启用

### Task 25：PDF 导出
- 后端：新增 pdf_service（reportlab）；新增 PDF 导出 API；requirements 加 reportlab
- 前端：ExportView PDF 选项启用 + 模板选择

---

## 九、依赖关系与推进顺序

```
Task 22（多案件管理）→ Task 23（状态流转）→ Task 24（图片打码+ZIP）→ Task 25（PDF 导出）
```

- Task 22 必须先完成：所有后续任务依赖"案件可切换"而非硬编码 case_id=1
- Task 23 依赖 Task 22（状态字段挂在 Case 上，列表需展示状态）
- Task 24 依赖 T0 的图片上传与 OCR（打码需图片与 OCR 坐标）
- Task 25 依赖 Task 22（PDF 导出需接收 caseId）+ T0 图片证据

---

## 十、验收标准

- [ ] 案件列表页展示所有案件，支持搜索/类型/状态筛选
- [ ] 可新建案件并进入其工作台，工作台不再硬编码 case_id=1
- [ ] 可删除案件，级联清理关联数据
- [ ] 工作台展示案件状态，可推进状态并查看状态历史
- [ ] 非法状态转换被拒绝并返回 400
- [ ] 可对图片证据一键打码，打码前后可对比预览
- [ ] 可下载证据包 ZIP，含打码图片与清单文件
- [ ] 可下载 PDF 投诉材料，中文不乱码，含证据图片缩略图
- [ ] T0 的所有能力（OCR/抽取/时间线重建/动态投诉）在新案件上正常工作
- [ ] 原 T0 的 API 端点向后兼容，不破坏已有功能
