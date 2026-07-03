# ClaimCraft 生态完善任务规划

> 基于现有 Demo（Django + Vue 3 + SQLite/MySQL）的实现现状，规划下一阶段的产品能力补全与工程化路径。
> 目标：让 Demo 从"可交互展示"进化为"能体现截图→OCR→投诉包核心卖点的可落地产品"。

---

## 一、现有实现盘点

### 已实现能力
| 模块 | 能力 | 关键文件 |
|---|---|---|
| 案件工作台 | 案件概览与统计 | `frontend/src/views/WorkspaceView.vue` |
| 证据管理 | 文本证据列表、自动编号、增删 | `frontend/src/views/EvidenceView.vue`、`backend/api/services/evidence_service.py` |
| 时间线 | 按时间排序展示、就地编辑 | `frontend/src/views/TimelineView.vue`、`backend/api/services/timeline_service.py` |
| 投诉文本 | 三套模板切换、证据编号高亮、复制 | `frontend/src/views/ComplaintView.vue`、`backend/api/services/complaint_service.py` |
| 隐私打码 | 手机号/身份证/地址文本打码 | `frontend/src/views/MaskView.vue`、`backend/api/services/mask_service.py` |
| 导出 | 文本包下载 | `frontend/src/views/ExportView.vue`、`backend/api/services/export_service.py` |

### 主要局限（生态完善切入点）
1. 证据仅为文本描述，无截图/图片上传，无法体现"截图→OCR→信息抽取"核心
2. 单案件硬编码（case_id=1），无案件列表、创建、切换
3. 投诉模板为静态 fixture，非根据证据动态生成
4. 时间线靠 fixture 预置，非从证据自动重建
5. 打码仅作用于文本，无图片打码
6. 导出仅 .txt，PDF/图片包为禁用占位
7. 无用户体系、无案件归属、无多用户隔离
8. 无案件状态流转

---

## 二、分阶段任务规划

### P0：补全创意核心能力（证据图片 + OCR + 动态生成）

**目标**：补全创意描述中"截图+聊天记录一键变成可提交投诉包"的核心卖点。

| Task | 名称 | 交付物 |
|---|---|---|
| Task 17 | 证据图片上传与存储 | Evidence.image 字段、上传 API、前端拖拽上传与预览 |
| Task 18 | OCR 文字识别接入 | ocr_service.py、上传后自动 OCR、识别结果可校正 |
| Task 19 | 关键信息自动抽取 | ExtractedField 模型、extraction_service.py、字段表展示 |
| Task 20 | 时间线自动重建 | timeline_service 改造、rebuild API、手动增删节点 |
| Task 21 | 投诉文本动态生成 | complaint_service 改造、模板引擎渲染、重新生成按钮 |

**推进顺序**：17 → 18 → 19 → 20 → 21

---

### P1：产品闭环（多案件 + 状态流转 + 图片打码导出）

**目标**：让 Demo 可作为多案件产品使用，补全打码与导出能力。

| Task | 名称 | 交付物 |
|---|---|---|
| Task 22 | 案件列表与多案件管理 | 案件列表页、新建案件、工作台去硬编码 |
| Task 23 | 案件状态流转 | Case.status 字段、状态推进、CaseStatusLog |
| Task 24 | 图片打码与证据包导出 | image_mask_service、ZIP 打包下载、打码前后对比 |
| Task 25 | PDF 导出 | WeasyPrint/reportlab 接入、PDF 含图片缩略图 |

**推进顺序**：22 → 23 → 24 → 25

---

### P2：工程化与体验提升

**目标**：让 Demo 可落地部署、可多人使用。

| Task | 名称 | 交付物 |
|---|---|---|
| Task 26 | 用户体系与案件归属 | User 模型、登录注册、JWT 鉴权、案件归属 |
| Task 27 | 案件模板预设 | 常见纠纷类型模板库、新建案件套用骨架 |
| Task 28 | 数据统计仪表盘 | echarts 仪表盘、stats 聚合 API |
| Task 29 | 前端打包与部署优化 | 单服务部署、生产配置、README |
| Task 30 | 浏览器插件入口 | Chrome 扩展、右键发送证据、实时同步 |

**推进顺序**：26 → 27 → 28 → 29 → 30

---

## 三、整体路线图

```
P0（补全创意核心）       P1（产品闭环）         P2（工程化）
17 → 18 → 19 → 20 → 21 → 22 → 23 → 24 → 25 → 26 → 27 → 28 → 29 → 30
```

**最优先**：Task 17 + Task 18 + Task 21，直接补全"截图变投诉包"核心卖点。

---

## 四、依赖关系

- Task 18（OCR）依赖 Task 17（图片上传）
- Task 19（信息抽取）依赖 Task 18（OCR 文本）
- Task 20（时间线重建）依赖 Task 19（抽取时间字段）
- Task 21（动态投诉生成）依赖 Task 19 + Task 20
- Task 24（图片打码）依赖 Task 17 + Task 18（OCR 坐标）
- Task 25（PDF）依赖 Task 17（图片素材）
- Task 30（插件）依赖 Task 26（用户鉴权）
