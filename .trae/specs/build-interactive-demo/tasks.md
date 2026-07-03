# Tasks

- [x] Task 1: 搭建 Django 后端项目骨架
  - [x] SubTask 1.1: 在 `backend/` 下创建 Django 项目 `claimcraft` 与 `api` 应用
  - [x] SubTask 1.2: 配置 `settings.py`（MySQL 数据库连接、DRF、CORS、INSTALLED_APPS）
  - [x] SubTask 1.3: 编写 `requirements.txt`（Django、djangorestframework、django-cors-headers、mysqlclient 或 PyMySQL）
  - [x] SubTask 1.4: 配置根 `urls.py` 挂载 `/api/` 路由

- [x] Task 2: 设计并实现 MySQL 数据模型
  - [x] SubTask 2.1: 在 `api/models.py` 定义 `Case` 模型（标题、描述、创建时间）
  - [x] SubTask 2.2: 定义 `Evidence` 模型（case 外键、编号、类型、描述、来源时间、是否含敏感信息、排序序号）
  - [x] SubTask 2.3: 定义 `TimelineNode` 模型（case 外键、日期时间、事件描述、关联证据编号、排序序号）
  - [x] SubTask 2.4: 定义 `ComplaintTemplate` 模型（case 外键、模板类型、标题、正文）
  - [x] SubTask 2.5: 生成并执行 migration

- [x] Task 3: 编写种子数据 fixture
  - [x] SubTask 3.1: 创建"网购退款纠纷"案件
  - [x] SubTask 3.2: 创建 6-8 条证据数据（订单页、聊天记录、物流页、客服回复等，含敏感信息样本）
  - [x] SubTask 3.3: 创建 5-6 个时间线节点（含日期时间、事件描述、关联证据编号）
  - [x] SubTask 3.4: 创建三套投诉模板（platform / regulatory / arbitration），正文含证据编号引用
  - [x] SubTask 3.5: 导出为 `seed_data.json` fixture

- [x] Task 4: 实现后端业务逻辑服务
  - [x] SubTask 4.1: `services/evidence_service.py`：证据自动编号（根据案件现有证据数生成下一个 E 编号）
  - [x] SubTask 4.2: `services/timeline_service.py`：时间线重建（按时间排序节点）
  - [x] SubTask 4.3: `services/complaint_service.py`：投诉文本生成（根据模板类型与案件数据组装文本，插入证据引用）
  - [x] SubTask 4.4: `services/mask_service.py`：打码服务（正则识别手机号 11 位、身份证号 18 位、地址关键词并替换）
  - [x] SubTask 4.5: `services/export_service.py`：导出服务（组装投诉文本 + 证据清单 + 时间线为纯文本）

- [x] Task 5: 实现后端 REST API
  - [x] SubTask 5.1: 编写 `serializers.py`（CaseSerializer、EvidenceSerializer、TimelineNodeSerializer、ComplaintTemplateSerializer）
  - [x] SubTask 5.2: 实现 `GET /api/cases/<id>/`（案件详情含统计）
  - [x] SubTask 5.3: 实现 `GET/POST /api/cases/<id>/evidences/` 与 `DELETE /api/evidences/<id>/`（新增时调用编号服务）
  - [x] SubTask 5.4: 实现 `GET /api/cases/<id>/timeline/` 与 `PATCH /api/timeline-nodes/<id>/`
  - [x] SubTask 5.5: 实现 `GET /api/cases/<id>/complaints/?template=<type>`（调用投诉生成服务）
  - [x] SubTask 5.6: 实现 `POST /api/cases/<id>/mask/`（调用打码服务）
  - [x] SubTask 5.7: 实现 `POST /api/cases/<id>/export/`（调用导出服务）
  - [x] SubTask 5.8: 配置 `api/urls.py` 注册所有路由

- [x] Task 6: 搭建 Vue 3 前端项目骨架
  - [x] SubTask 6.1: 在 `frontend/` 下用 Vite 创建 Vue 3 项目
  - [x] SubTask 6.2: 安装依赖（vue-router、pinia、axios）
  - [x] SubTask 6.3: 配置 `vite.config.js`（dev server 端口 5173、可选代理 `/api` 到后端）
  - [x] SubTask 6.4: 建立目录结构（views、components、stores、api、router、styles）
  - [x] SubTask 6.5: 编写全局样式文件，复用展示页主题变量（`--accent` / `--accent2` / 字体栈 / 圆角）

- [x] Task 7: 实现前端 API 层与 Pinia store
  - [x] SubTask 7.1: `api/index.js`：配置 Axios 实例（baseURL `http://localhost:8000/api`）
  - [x] SubTask 7.2: `api/case.js`：封装案件、证据、时间线、投诉、打码、导出接口调用
  - [x] SubTask 7.3: `stores/case.js`：Pinia store 持有当前案件、证据列表、时间线节点、当前模板、打码状态

- [x] Task 8: 实现工作台主框架与路由
  - [x] SubTask 8.1: `App.vue`：顶部导航栏（品牌标识 + 返回介绍页链接）+ 左侧功能导航 + 右侧 `<router-view>`
  - [x] SubTask 8.2: `router/index.js`：注册 6 个路由（workspace、evidence、timeline、complaint、mask、export），默认重定向到 workspace
  - [x] SubTask 8.3: 左侧导航项高亮当前路由

- [x] Task 9: 实现案件工作台视图
  - [x] SubTask 9.1: `views/WorkspaceView.vue`：调用 `GET /api/cases/<id>/` 获取案件详情
  - [x] SubTask 9.2: 渲染概览卡片（案例标题、证据数量、关键节点数、投诉版本数）

- [x] Task 10: 实现证据导入视图
  - [x] SubTask 10.1: `views/EvidenceView.vue`：调用 `GET /api/cases/<id>/evidences/` 渲染证据卡片列表（编号、类型标签、描述、来源时间）
  - [x] SubTask 10.2: "添加示例证据"按钮调用 `POST /api/cases/<id>/evidences/`，列表实时更新
  - [x] SubTask 10.3: 证据卡片删除按钮调用 `DELETE /api/evidences/<id>/`

- [x] Task 11: 实现时间线校正视图
  - [x] SubTask 11.1: `views/TimelineView.vue`：调用 `GET /api/cases/<id>/timeline/` 渲染纵向时间线（日期、事件描述、关联证据编号）
  - [x] SubTask 11.2: 事件描述就地编辑（contenteditable 或 input），失焦调用 `PATCH /api/timeline-nodes/<id>/`

- [x] Task 12: 实现投诉文本视图
  - [x] SubTask 12.1: `views/ComplaintView.vue`：模板切换器（平台客服版 / 监管投诉版 / 仲裁准备版）
  - [x] SubTask 12.2: 切换时调用 `GET /api/cases/<id>/complaints/?template=<type>`，渲染文本，证据编号引用高亮
  - [x] SubTask 12.3: "复制全文"按钮调用剪贴板 API，给出成功提示

- [x] Task 13: 实现隐私打码视图
  - [x] SubTask 13.1: `views/MaskView.vue`：展示识别到的敏感信息列表（类型 + 原文）
  - [x] SubTask 13.2: "一键打码"开关，开启时调用 `POST /api/cases/<id>/mask/`，预览区显示打码结果
  - [x] SubTask 13.3: 关闭时恢复原文显示

- [x] Task 14: 实现导出与提交视图
  - [x] SubTask 14.1: `views/ExportView.vue`：导出格式选项（PDF / 图片包 / 文本包，前两者为模拟提示）
  - [x] SubTask 14.2: 展示导出清单（证据数量、模板版本、打码状态）
  - [x] SubTask 14.3: 选择"文本包"时调用 `POST /api/cases/<id>/export/`，触发浏览器下载 `.txt` 文件

- [x] Task 15: 实现展示页与 Demo 互通导航
  - [x] SubTask 15.1: 在 `claimcraft-creative.html` 导航栏新增"体验交互 Demo"链接指向 `http://localhost:5173`
  - [x] SubTask 15.2: 在 `frontend/src/App.vue` 顶部导航栏新增"返回介绍页"链接指向 `../claimcraft-creative.html`

- [x] Task 16: 视觉一致性校验与响应式适配
  - [x] SubTask 16.1: 确认前端配色、字体、卡片、按钮与展示页一致
  - [x] SubTask 16.2: 窄屏（≤920px）下左侧导航折叠为顶部横向滚动条或抽屉
  - [x] SubTask 16.3: 验证各视图在常见分辨率下无溢出、无错位

# Task Dependencies
- Task 2 依赖 Task 1（模型依赖项目骨架）
- Task 3 依赖 Task 2（种子数据依赖模型）
- Task 4 依赖 Task 2（服务依赖模型）
- Task 5 依赖 Task 4（API 调用服务）
- Task 7 依赖 Task 6（API 层依赖前端骨架）
- Task 8 依赖 Task 7（主框架依赖 store 与 API）
- Task 9 / 10 / 11 / 12 / 13 / 14 依赖 Task 8（各视图依赖主框架与路由）
- Task 9 / 10 / 11 / 12 / 13 / 14 之间相互独立，可并行实现
- Task 15 依赖 Task 8（Demo 入口存在后才能互链）
- Task 16 依赖 Task 9 / 10 / 11 / 12 / 13 / 14 全部完成
- 前端 Task 9-14 与后端 Task 5 可并行（前端先用 mock，后端就绪后切换）
