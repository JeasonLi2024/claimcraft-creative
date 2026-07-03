# ClaimCraft T1：产品闭环（多案件 + 状态流转 + 图片打码 + PDF 导出）Spec

> 承接 T0 已补全的"截图→OCR→信息抽取→时间线重建→动态投诉生成"核心链路，本阶段聚焦产品闭环：多案件管理、状态流转、图片打码导出、PDF 投诉材料生成。

## Why
T0 虽补全核心链路，但 Demo 仍存在三个产品闭环缺口：单案件硬编码（无法创建/切换案件）、无状态流转（无法跟踪维权进度）、打码与导出能力缺失（图片无法打码、PDF/ZIP 为禁用占位）。本阶段通过四项能力补全，让 Demo 形成完整产品闭环。

## What Changes

### 数据模型变更
- `Case` 模型新增字段：
  - `case_type`（CharField：shopping/service/secondhand/other，默认 shopping）
  - `status`（django-fsm 的 FSMField：draft/processing/submitted/closed/cancelled，默认 draft）
  - `updated_at`（DateTimeField，auto_now=True）
- `Evidence` 模型新增字段：
  - `masked_image`（ImageField，存 `evidences/<case_id>/masked/`，blank/null）
  - `mask_status`（CharField：none/pending/done，默认 none）
- 新增 `CaseStatusLog` 模型：case 外键、from_status、to_status、remark（TextField blank）、created_at（auto_now_add）

### 状态机（django-fsm 声明）
```python
# 合法转换（5 条）：
draft → processing
draft → cancelled
processing → submitted
processing → cancelled
submitted → closed
# submitted 后不可取消（无 submitted → cancelled 转换）
# closed 为终态，不可再转换
```
调用 `make_transition` 时 fsm 自动校验，非法转换抛 `TransitionNotAllowed`。

### 后端新增/改造
- `requirements.txt` 新增 `django-fsm>=2.8`、`reportlab>=4.0`
- 新增 `services/image_mask_service.py`：
  - `mask_evidence_image(evidence)`：pytesseract `image_to_data` 定位手机号/地址/身份证号文字区域，Pillow 高斯模糊该区域；定位失败回退底部 1/3 模糊。保存到 `masked_image`，`mask_status=done`
  - `mask_case_images(case)`：批量打码该案件所有图片证据
- 新增 `services/pdf_service.py`：
  - `generate_complaint_pdf(case, template_type='platform')`：reportlab 生成 PDF
  - 字体方案：优先注册 `C:\Windows\Fonts\simsun.ttc`（TTFont），失败回退 `STSong-Light`，再失败 `Helvetica`（仅英文+记日志）
  - PDF 结构：标题 → 投诉人信息 → 事实经过（时间线）→ 关键信息表 → 诉求 → 证据清单（含图片缩略图+编号）→ 签名区
  - 页眉（案件标题）+ 页脚（页码）
- 扩展 `services/export_service.py`：新增 `export_evidence_package(case)` 用 `zipfile`+`BytesIO` 生成 ZIP（complaint.txt + evidence_list.txt + timeline.txt + images/ 含打码图 + manifest.json）
- 新增 7 条 URL 路由（9 个 API 方法，见下文 API 章节）

### 前端改造
- 路由改造：`/` → `/cases`；所有工作台视图路由加 `:caseId` 前缀
- 新增 `CaseListView.vue`：卡片网格 + 搜索 + 筛选 + 新建案件弹窗
- `WorkspaceView.vue`：去硬编码 case_id=1 + 状态条（色标 + 推进弹窗 + 状态历史时间轴）
- `MaskView.vue`：新增图片打码区（图片列表 + 一键打码 + 前后对比 + mask_status 标签）
- `ExportView.vue`：ZIP 选项启用 + PDF 选项启用（模板选择）
- `stores/case.js`：新增 `cases` 列表 state + 8 个 actions（fetchCases/createCase/updateCase/deleteCase/transitionCaseStatus/fetchStatusLogs/maskImages/exportPackage/exportPDF）

### 不变更
- T0 的 5 个新 API 端点行为不变（向后兼容）
- T0 的 OCR/抽取/时间线/投诉服务逻辑不改动
- 展示页 `claimcraft-creative.html` 不改动

## Impact
- Affected specs: `add-image-ocr-dynamic-generation`（T0，向后兼容扩展）
- Affected code:
  - `backend/api/models.py`（Case 加 3 字段；Evidence 加 2 字段；新增 CaseStatusLog；fsm 转换声明）
  - `backend/api/migrations/0003_t1_case_status_mask.py`
  - `backend/api/services/image_mask_service.py`（新建）
  - `backend/api/services/pdf_service.py`（新建）
  - `backend/api/services/export_service.py`（扩展 ZIP）
  - `backend/api/serializers.py`（CaseSerializer 扩展；新增 CaseListSerializer、CaseStatusLogSerializer；EvidenceSerializer 扩展 masked_image/mask_status）
  - `backend/api/views.py`（新增 CaseListCreateView、CaseUpdateDeleteView、CaseStatusTransitionView、CaseStatusLogView、MaskImageView、ExportPackageView、ExportPDFView）
  - `backend/api/urls.py`（新增 7 条路由）
  - `backend/seed_data.json`（现有 Case 补 case_type=shopping/status=draft；现有 Evidence 补 mask_status=none）
  - `backend/requirements.txt`（新增 django-fsm、reportlab）
  - `frontend/src/views/CaseListView.vue`（新建）
  - `frontend/src/views/WorkspaceView.vue`（去硬编码 + 状态条）
  - `frontend/src/views/MaskView.vue`（图片打码区）
  - `frontend/src/views/ExportView.vue`（ZIP + PDF 启用）
  - `frontend/src/router/index.js`（路由重构）
  - `frontend/src/api/case.js`（新增 9 个接口封装）
  - `frontend/src/stores/case.js`（新增 cases state + 9 个 actions）

## ADDED Requirements

### Requirement: 案件列表与多案件管理
系统 SHALL 提供案件列表 API 与视图，支持搜索、类型筛选、状态筛选，支持新建/编辑/删除案件，工作台从路由参数加载案件。

#### Scenario: 查看案件列表
- **WHEN** 用户访问首页（`/` 重定向到 `/cases`）
- **THEN** 展示所有案件卡片网格（标题、类型标签、状态标签、证据数、更新时间），按更新时间倒序

#### Scenario: 搜索与筛选案件
- **WHEN** 用户输入关键词或选择类型/状态筛选
- **THEN** 列表实时过滤，只展示匹配案件

#### Scenario: 新建案件
- **WHEN** 用户点击"新建案件"并填写标题、描述、纠纷类型后提交
- **THEN** 后端创建案件（status=draft），列表新增卡片，点击进入 `/cases/:caseId/workspace`

#### Scenario: 工作台去硬编码
- **WHEN** 用户从列表点击某案件进入工作台
- **THEN** 工作台从路由参数 `caseId` 加载该案件所有数据，不再固定 case_id=1

#### Scenario: 删除案件
- **WHEN** 用户删除某案件
- **THEN** 级联删除证据、时间线、模板规则、状态日志，列表移除卡片

### Requirement: 案件状态流转（django-fsm）
系统 SHALL 用 django-fsm 声明 5 条合法状态转换，调用时自动校验，非法转换返回 400。每次转换记录 CaseStatusLog。

#### Scenario: 合法推进状态
- **WHEN** 用户从 draft 推进到 processing 并填写备注
- **THEN** Case.status 更新为 processing，创建 CaseStatusLog（from=draft/to=processing/remark），返回新状态

#### Scenario: 非法转换被拒
- **WHEN** 用户尝试 submitted → cancelled（submitted 后不可取消）
- **THEN** fsm 抛 TransitionNotAllowed，API 返回 400，提示"不允许的状态转换"

#### Scenario: 查看状态历史
- **WHEN** 用户在工作台展开"状态历史"
- **THEN** 展示 CaseStatusLog 时间轴（from→to、备注、时间）

### Requirement: 图片打码
系统 SHALL 通过 image_mask_service 对证据图片执行打码，保存打码后图片，支持前后对比。

#### Scenario: 一键打码所有图片
- **WHEN** 用户点击"一键打码所有图片"
- **THEN** 对该案件所有图片证据执行打码，保存 masked_image，mask_status=done，返回打码后列表

#### Scenario: 精确定位失败回退
- **WHEN** pytesseract 无法精确定位敏感信息区域
- **THEN** 回退对图片底部 1/3 区域高斯模糊，mask_status 仍置 done

#### Scenario: 打码前后对比
- **WHEN** 用户查看某图片证据打码预览
- **THEN** 展示打码前原图与打码后图并排对比

### Requirement: 证据包 ZIP 导出
系统 SHALL 生成 ZIP 下载，含投诉文本、证据清单、时间线、打码后图片目录、manifest 映射。

#### Scenario: 下载证据包
- **WHEN** 用户点击"证据包导出（ZIP）"
- **THEN** 生成 ZIP 文件流，浏览器下载，含 complaint.txt、evidence_list.txt、timeline.txt、images/ 目录（打码后图片）、manifest.json

### Requirement: PDF 投诉材料导出
系统 SHALL 用 reportlab 生成 PDF，优先系统 TTF 字体，含完整投诉材料与证据图片缩略图。

#### Scenario: 下载 PDF
- **WHEN** 用户选择模板类型并点击"PDF 文档导出"
- **THEN** 调用 pdf_service 生成 PDF，浏览器下载，中文不乱码，含证据图片缩略图

#### Scenario: 字体回退链
- **WHEN** PDF 生成时
- **THEN** 优先注册 `C:\Windows\Fonts\simsun.ttc`，失败回退 `STSong-Light`，再失败 `Helvetica`（记日志）

## MODIFIED Requirements

### Requirement: 案件工作台（去硬编码 + 状态条）
原：固定加载 case_id=1。
现：从路由参数 `caseId` 加载，顶部新增状态条（色标 + 推进按钮 + 状态历史时间轴）。

### Requirement: 隐私打码（扩展图片打码）
原：仅对证据描述文本打码。
现：新增图片打码（Pillow + pytesseract 定位），支持一键全量打码与前后对比。文本打码保留。

### Requirement: 导出（扩展 ZIP 与 PDF）
原：仅 .txt 文本包，ZIP/PDF 为禁用占位。
现：新增证据包 ZIP 导出（含打码图片）与 PDF 投诉材料导出。原 .txt 保留。

## 技术选型
| 能力 | 选型 | 理由 |
|---|---|---|
| 状态机 | django-fsm | 声明式转换，自动校验，TransitionNotAllowed 异常清晰 |
| 图片打码 | Pillow + pytesseract image_to_data | 复用 T0 Tesseract，获取文字坐标精确打码 |
| ZIP 打包 | Python zipfile + BytesIO | 标准库 |
| PDF 生成 | reportlab + TTFont | 纯 Python，系统 TTF 字体可靠 |
| 字体回退 | simsun.ttc → STSong-Light → Helvetica | 三级保证可用 |
