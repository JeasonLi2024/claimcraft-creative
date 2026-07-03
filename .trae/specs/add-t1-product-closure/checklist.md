# Checklist

## 后端数据模型与状态机
- [x] `Case` 模型含 case_type（CharField）、status（FSMField default draft）、updated_at（auto_now）字段
- [x] django-fsm @transition 声明 5 条转换（draft→processing、draft→cancelled、processing→submitted、processing→cancelled、submitted→closed）
- [x] submitted→cancelled 转换不存在（submitted 后不可取消）
- [x] `Evidence` 模型含 masked_image（ImageField）、mask_status（CharField default none）字段
- [x] `CaseStatusLog` 模型含 case 外键、from_status、to_status、remark、created_at 字段
- [x] `requirements.txt` 含 django-fsm、reportlab
- [x] `0003_t1_case_status_mask` migration 生成且 migrate 成功

## 后端图片打码服务
- [x] `services/image_mask_service.py` 存在且 `mask_evidence_image` 用 pytesseract image_to_data 定位敏感信息区域
- [x] 定位失败回退底部 1/3 高斯模糊
- [x] 打码后图片保存到 masked_image，mask_status=done
- [x] `mask_case_images` 批量处理函数存在

## 后端 PDF 导出服务
- [x] `services/pdf_service.py` 存在且 `generate_complaint_pdf` 用 reportlab 生成 PDF
- [x] 字体三级回退：simsun.ttc → STSong-Light → Helvetica
- [x] PDF 含标题、事实经过、关键信息表、诉求、证据清单（含图片缩略图）、签名区
- [x] PDF 含页眉（案件标题）与页脚（页码）

## 后端 ZIP 导出
- [x] `export_service.export_evidence_package` 用 zipfile+BytesIO 生成 ZIP
- [x] ZIP 含 complaint.txt、evidence_list.txt、timeline.txt、images/、manifest.json
- [x] 无打码图时使用原图并在 manifest 标注

## 后端 REST API
- [x] GET /api/cases/ 支持 search/status/case_type 过滤，返回 case_type/status
- [x] POST /api/cases/ 创建案件 status=draft
- [x] PATCH /api/cases/<id>/ 更新标题/描述/类型
- [x] DELETE /api/cases/<id>/ 级联删除
- [x] POST /api/cases/<id>/status/transition/ 调用 fsm，TransitionNotAllowed 返回 400
- [x] POST 状态推进创建 CaseStatusLog 记录
- [x] GET /api/cases/<id>/status-logs/ 返回状态历史
- [x] POST /api/cases/<id>/mask-images/ 返回打码后证据列表
- [x] GET /api/cases/<id>/export/package/?type=zip 下载 ZIP
- [x] GET /api/cases/<id>/export/pdf/?template=platform 下载 PDF
- [x] `urls.py` 注册 7 条新路由

## 后端种子数据
- [x] 现有 Case（pk=1）含 case_type=shopping、status=draft
- [x] 现有 Evidence 含 mask_status=none
- [x] loaddata 导入成功

## 前端 API 与 store
- [x] `api/case.js` 含 fetchCases、createCase、updateCase、deleteCase、transitionCaseStatus、fetchStatusLogs、maskImages、exportPackage、exportPDF
- [x] `stores/case.js` 含 cases 列表 state + 9 个 actions

## 前端路由
- [x] `/` 重定向到 `/cases`
- [x] `/cases` → CaseListView
- [x] 工作台视图路由改为 `/cases/:caseId/workspace` 等
- [x] 顶部导航含"我的案件"入口

## 前端案件列表视图
- [x] CaseListView 卡片网格展示标题、类型标签、状态标签、证据数、更新时间
- [x] 搜索框 + 类型筛选 + 状态筛选
- [x] "新建案件"按钮弹窗（标题、描述、纠纷类型），调用 createCase
- [x] 点击卡片跳转 /cases/:caseId/workspace
- [x] 卡片支持删除（确认弹窗）

## 前端工作台状态条
- [x] WorkspaceView 从路由参数 caseId 加载（去硬编码 1）
- [x] 状态色标（draft 灰/processing 蓝/submitted 橙/closed 绿/cancelled 红）
- [x] "推进状态"按钮弹窗（to_status 下拉 + remark 输入）
- [x] 状态历史时间轴可展开，调用 fetchStatusLogs

## 前端打码视图
- [x] MaskView 图片打码区展示图片证据列表
- [x] "一键打码所有图片"按钮调用 maskImages，打码中 loading
- [x] 打码前后对比缩略图
- [x] mask_status 标签

## 前端导出视图
- [x] "证据包导出（ZIP）"选项可用，点击下载
- [x] "PDF 文档导出"选项可用，含模板选择
- [x] 点击下载调用 exportPDF

## 端到端与兼容性
- [x] npm run build 无编译错误
- [x] 首页 / 重定向到 /cases，列表展示案件
- [x] T0 的所有能力（OCR/抽取/时间线重建/动态投诉）在新案件上正常工作
- [x] 原 T0 的 API 端点向后兼容，不破坏已有功能
