# Checklist

## 后端数据模型
- [x] `Evidence` 模型含 image（ImageField）、extracted_text（TextField）、ocr_status（CharField default pending）字段
- [x] `ExtractedField` 模型含 evidence 外键、field_name、field_value、confidence、created_at 字段
- [x] `TimelineNode` 模型含 auto_generated（BooleanField default False）字段
- [x] `ComplaintTemplateRule` 模型含 template_type、rule_title、rule_content 字段
- [x] `settings.py` 配置了 MEDIA_ROOT 与 MEDIA_URL
- [x] `0002_t0_image_ocr` migration 生成且 `migrate` 成功

## 后端 OCR 服务
- [x] `services/ocr_service.py` 存在且 `ocr_image` 函数默认调用本机 Tesseract（`D:\tesseract\tesseract.exe`，chi_sim+eng）
- [x] Tesseract 路径不存在或调用异常时回退 Mock OCR，返回预置识别文本
- [x] Mock 文本含订单号、金额、手机号、地址、时间、承诺话术样本
- [x] OCR 失败时 ocr_status 置为 failed，不阻断流程
- [x] `requirements.txt` 含 pytesseract、Pillow、Jinja2

## 后端抽取服务
- [x] `services/extraction_service.py` 用正则抽取 6 类字段（订单号/金额/手机号/地址/时间/承诺话术）
- [x] 每条抽取结果创建 ExtractedField 记录含 confidence

## 后端时间线重建
- [x] `timeline_service.rebuild_timeline(case)` 删除 auto_generated=True 节点
- [x] 从证据 source_time 与抽取时间字段生成新 auto_generated=True 节点
- [x] 保留 auto_generated=False 手动节点，合并按时间排序返回

## 后端投诉文本动态生成
- [x] `complaint_service.generate_complaint` 从 ComplaintTemplateRule 取 Jinja2 源码渲染
- [x] 上下文含 case、evidences、timeline_nodes、extracted_fields
- [x] 渲染结果含"（见 E2）"证据编号引用
- [x] 无对应 Rule 时回退读原 ComplaintTemplate 静态 content

## 后端种子数据
- [x] fixture 含 3 个 ComplaintTemplateRule（platform/regulatory/arbitration 的 Jinja2 源码）
- [x] fixture 为现有 E1-E8 补充预置 ExtractedField 数据
- [x] 现有 TimelineNode 标记 auto_generated=False
- [x] `loaddata` 导入成功

## 后端 REST API
- [x] `POST /api/cases/<id>/evidences/upload/` 接收 multipart，校验格式（jpg/png/webp）与大小（≤10MB）
- [x] 上传后创建 Evidence 含 image 路径，同步 OCR 后 ocr_status=done，返回图片 URL
- [x] `GET /api/evidences/<id>/extracted-fields/` 返回抽取字段列表
- [x] `PATCH /api/extracted-fields/<id>/` 更新 field_value
- [x] `POST /api/cases/<id>/timeline/rebuild/` 触发重建并返回节点列表
- [x] `POST /api/cases/<id>/complaints/regenerate/` 强制重新生成投诉文本
- [x] `urls.py` 注册所有新路由
- [x] 根 `urls.py` 追加 media 文件服务（`static()` + `MEDIA_URL`）

## 前端 API 与 store
- [x] `api/case.js` 含 uploadEvidence、getExtractedFields、updateExtractedField、rebuildTimeline、regenerateComplaint
- [x] `stores/case.js` 含对应 actions

## 前端证据导入视图
- [x] 拖拽上传区支持拖入与点击选择文件
- [x] 上传后证据卡片展示图片缩略图，点击弹出 lightbox
- [x] 证据卡片展示 OCR 状态标签（识别中/完成/失败）
- [x] "OCR 识别结果"可展开区显示 extracted_text 与抽取字段表
- [x] 抽取字段值可就地编辑，失焦调用 PATCH

## 前端时间线视图
- [x] "重新生成时间线"按钮调用 rebuild API 并刷新列表
- [x] auto_generated 节点有"自动"标签视觉区分

## 前端投诉文本视图
- [x] "重新生成"按钮调用 regenerate API 并刷新文本预览

## 前端案件工作台
- [x] 概览卡片含"图片证据数"与"抽取字段数"
- [x] 数据来自案件详情 API（CaseSerializer 扩展 image_evidence_count、extracted_field_count）

## 端到端与兼容性
- [x] `npm run build` 无编译错误
- [x] 现有文本证据与原 8 个 API 端点向后兼容，不破坏已有功能
- [x] 删除某证据后重新生成投诉文本，不引用已删除证据编号
