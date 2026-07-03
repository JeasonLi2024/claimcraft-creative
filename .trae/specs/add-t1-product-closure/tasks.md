# Tasks

- [x] Task 1: 后端数据模型扩展与 migration
  - [x] SubTask 1.1: `Case` 模型新增 `case_type`（CharField，choices shopping/service/secondhand/other，default shopping）、`status`（django-fsm FSMField，default draft）、`updated_at`（DateTimeField auto_now）
  - [x] SubTask 1.2: 用 django-fsm `@transition` 装饰器声明 5 条合法转换（draft→processing、draft→cancelled、processing→submitted、processing→cancelled、submitted→closed）
  - [x] SubTask 1.3: `Evidence` 模型新增 `masked_image`（ImageField upload_to=evidences/<case_id>/masked/，blank/null）、`mask_status`（CharField default none）
  - [x] SubTask 1.4: 新增 `CaseStatusLog` 模型（case 外键、from_status、to_status、remark TextField blank、created_at auto_now_add）
  - [x] SubTask 1.5: `requirements.txt` 新增 django-fsm>=2.8、reportlab>=4.0
  - [x] SubTask 1.6: 生成并执行 migration `0003_t1_case_status_mask`

- [x] Task 2: 后端图片打码服务
  - [x] SubTask 2.1: 新建 `services/image_mask_service.py`，实现 `mask_evidence_image(evidence)`
  - [x] SubTask 2.2: 用 pytesseract `image_to_data` 获取文字坐标，正则匹配手机号/地址/身份证号文字区域，Pillow 高斯模糊该区域
  - [x] SubTask 2.3: 定位失败回退：对图片底部 1/3 区域整体高斯模糊
  - [x] SubTask 2.4: 保存打码后图片到 `masked_image` 字段，`mask_status=done`
  - [x] SubTask 2.5: 实现 `mask_case_images(case)` 批量处理

- [x] Task 3: 后端 PDF 导出服务
  - [x] SubTask 3.1: 新建 `services/pdf_service.py`，实现 `generate_complaint_pdf(case, template_type='platform')`
  - [x] SubTask 3.2: 字体注册：优先 `C:\Windows\Fonts\simsun.ttc`（reportlab TTFont），失败回退 `STSong-Light`，再失败 `Helvetica`（记日志）
  - [x] SubTask 3.3: PDF 结构：标题 → 投诉人信息 → 事实经过（时间线列表）→ 关键信息表 → 诉求 → 证据清单（含图片缩略图+编号）→ 签名区
  - [x] SubTask 3.4: 页眉（案件标题）+ 页脚（页码）
  - [x] SubTask 3.5: 返回 PDF 文件流（BytesIO）

- [x] Task 4: 后端 ZIP 导出扩展
  - [x] SubTask 4.1: 扩展 `services/export_service.py`，新增 `export_evidence_package(case)`
  - [x] SubTask 4.2: 用 zipfile + BytesIO 生成 ZIP：complaint.txt、evidence_list.txt、timeline.txt、images/ 目录（打码后图片，文件名含证据编号 E1_xxx.jpg）、manifest.json（证据编号与文件名映射）
  - [x] SubTask 4.3: 无打码图时使用原图并在 manifest 标注

- [x] Task 5: 后端 REST API（7 条新路由，9 个方法）
  - [x] SubTask 5.1: `serializers.py` 新增 CaseListSerializer、CaseStatusLogSerializer，扩展 CaseSerializer（case_type/status/updated_at）、EvidenceSerializer（masked_image/mask_status）
  - [x] SubTask 5.2: `CaseListCreateView`：GET /api/cases/（search/status/case_type 过滤）、POST /api/cases/（创建，status=draft）
  - [x] SubTask 5.3: `CaseUpdateDeleteView`：PATCH /api/cases/<id>/（更新标题/描述/类型）、DELETE /api/cases/<id>/（级联删除）
  - [x] SubTask 5.4: `CaseStatusTransitionView`：POST /api/cases/<id>/status/transition/（接收 to_status+remark，调用 fsm make_transition，创建 CaseStatusLog，TransitionNotAllowed 返回 400）
  - [x] SubTask 5.5: `CaseStatusLogView`：GET /api/cases/<id>/status-logs/（返回状态历史列表）
  - [x] SubTask 5.6: `MaskImageView`：POST /api/cases/<id>/mask-images/（调用 mask_case_images，返回打码后证据列表）
  - [x] SubTask 5.7: `ExportPackageView`：GET /api/cases/<id>/export/package/?type=zip（返回 ZIP 文件流）
  - [x] SubTask 5.8: `ExportPDFView`：GET /api/cases/<id>/export/pdf/?template=platform（返回 PDF 文件流）
  - [x] SubTask 5.9: `urls.py` 注册 7 条新路由

- [x] Task 6: 后端种子数据更新
  - [x] SubTask 6.1: 现有 Case（pk=1）补 `case_type=shopping`、`status=draft`
  - [x] SubTask 6.2: 现有 Evidence（E1-E8）补 `mask_status=none`
  - [x] SubTask 6.3: loaddata 导入成功验证

- [x] Task 7: 前端 API 层与 store 扩展
  - [x] SubTask 7.1: `api/case.js` 新增 fetchCases、createCase、updateCase、deleteCase、transitionCaseStatus、fetchStatusLogs、maskImages、exportPackage、exportPDF 接口封装
  - [x] SubTask 7.2: `stores/case.js` 新增 `cases` 列表 state + 9 个 actions
  - [x] SubTask 7.3: 所有现有 actions 确认接收 caseId 参数（已部分完成，补全）

- [x] Task 8: 前端路由重构
  - [x] SubTask 8.1: `/` 重定向到 `/cases`
  - [x] SubTask 8.2: 新增 `/cases` → CaseListView
  - [x] SubTask 8.3: 所有工作台视图路由改为 `/cases/:caseId/workspace`、`/cases/:caseId/evidence` 等
  - [x] SubTask 8.4: 顶部导航新增"我的案件"入口指向 `/cases`

- [x] Task 9: 前端案件列表视图（CaseListView.vue）
  - [x] SubTask 9.1: 案件卡片网格（标题、类型标签、状态标签、证据数、更新时间），按更新时间倒序
  - [x] SubTask 9.2: 顶部搜索框 + 类型筛选下拉 + 状态筛选下拉
  - [x] SubTask 9.3: "新建案件"按钮 → 弹窗（标题、描述、纠纷类型下拉），调用 createCase
  - [x] SubTask 9.4: 点击案件卡片跳转 `/cases/:caseId/workspace`
  - [x] SubTask 9.5: 卡片支持删除（确认弹窗）

- [x] Task 10: 前端工作台状态条
  - [x] SubTask 10.1: `WorkspaceView.vue` 从路由参数 `caseId` 加载（去硬编码 1）
  - [x] SubTask 10.2: 顶部状态条：当前状态色标（draft 灰/processing 蓝/submitted 橙/closed 绿/cancelled 红）
  - [x] SubTask 10.3: "推进状态"按钮 → 弹窗（选择 to_status 下拉 + remark 输入），调用 transitionCaseStatus
  - [x] SubTask 10.4: 状态历史时间轴（可展开），调用 fetchStatusLogs 展示

- [x] Task 11: 前端打码视图改造（MaskView.vue）
  - [x] SubTask 11.1: 新增"图片打码"区：展示图片证据列表
  - [x] SubTask 11.2: "一键打码所有图片"按钮，调用 maskImages，打码中 loading
  - [x] SubTask 11.3: 每张图片展示打码前后对比缩略图
  - [x] SubTask 11.4: mask_status 标签（未打码/打码中/已打码）

- [x] Task 12: 前端导出视图改造（ExportView.vue）
  - [x] SubTask 12.1: "证据包导出（ZIP）"选项从禁用改为可用，点击调用 exportPackage 下载
  - [x] SubTask 12.2: "PDF 文档导出"选项从禁用改为可用，含模板选择（platform/regulatory/arbitration）
  - [x] SubTask 12.3: 点击下载调用 exportPDF，触发浏览器下载

- [x] Task 13: 端到端验证
  - [x] SubTask 13.1: 后端 makemigrations && migrate 成功
  - [x] SubTask 13.2: loaddata 种子数据成功（Case 含 case_type/status，Evidence 含 mask_status）
  - [x] SubTask 13.3: GET /api/cases/ 返回案件列表含 status/case_type
  - [x] SubTask 13.4: POST /api/cases/ 创建新案件 status=draft
  - [x] SubTask 13.5: POST 状态推进 draft→processing 成功，创建 CaseStatusLog
  - [x] SubTask 13.6: POST submitted→cancelled 返回 400
  - [x] SubTask 13.7: POST mask-images 返回打码后证据列表
  - [x] SubTask 13.8: GET export/package 下载 ZIP 含图片
  - [x] SubTask 13.9: GET export/pdf 下载 PDF 中文不乱码
  - [x] SubTask 13.10: 前端 npm run build 无错误
  - [x] SubTask 13.11: 首页 / 重定向到 /cases，列表展示案件
  - [x] SubTask 13.12: T0 的所有能力在新案件上正常工作
  - [x] SubTask 13.13: 原 T0 的 API 端点向后兼容

# Task Dependencies
- Task 2/3/4 依赖 Task 1（服务依赖模型）
- Task 5 依赖 Task 2/3/4（API 调用服务）
- Task 6 依赖 Task 1（fixture 依赖模型字段）
- Task 7 依赖 Task 5（前端 API 层依赖后端端点）
- Task 8 依赖 Task 7（路由依赖 store）
- Task 9/10/11/12 依赖 Task 8（视图依赖路由），可并行实现
- Task 13 依赖 Task 9/10/11/12 全部完成
