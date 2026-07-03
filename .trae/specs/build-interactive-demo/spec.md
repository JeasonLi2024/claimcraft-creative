# ClaimCraft 全栈 Demo 开发 Spec

## Why
现有 `claimcraft-creative.html` 是一个静态展示页，仅用文字和示意图描述了 ClaimCraft 的创意概念。为了让评委和用户直观感受产品能力，需要一个**基于 Vue + Django + MySQL 的全栈可交互 Demo**，实现"导入材料 → 重建时间线 → 生成投诉文本 → 隐私打码 → 导出"的完整工作流。前端用 Vue 3 SPA 复用现有视觉语言，后端用 Django REST Framework 提供数据与业务逻辑接口，MySQL 持久化案件、证据、时间线、模板等数据。

## What Changes
- 新增 `backend/`：Django 项目，提供 REST API（案件管理、证据管理、时间线、投诉文本生成、打码、导出）
- 新增 `frontend/`：Vue 3 + Vite SPA 项目，实现 6 个功能视图的工作台界面
- 新增 MySQL 数据库 schema：`cases` / `evidences` / `timeline_nodes` / `complaint_templates` 表
- 后端预置一个"网购退款纠纷"案例的种子数据（通过 Django migrations 或 fixture 导入）
- 后端实现核心业务逻辑：证据自动编号、时间线重建、三套投诉模板生成、敏感信息打码
- 前端复用展示页主题变量与组件风格，保持视觉统一
- 不修改现有 `claimcraft-creative.html` 与 `assets/charts.js`，仅在其导航栏新增"体验交互 Demo"入口

## Impact
- Affected specs: 无（首次建立）
- Affected code:
  - 新增 `backend/`（Django 项目：settings、api app、models、serializers、views、urls、services、fixtures）
  - 新增 `frontend/`（Vue 3 项目：views、components、stores、api、router、styles）
  - 修改 `claimcraft-creative.html`：仅在导航栏新增一个指向 `frontend` dev server 的"体验交互 Demo"链接
  - 不改动 `assets/charts.js`、`assets/hero_claimcraft.jpg`、`_shared/`

## ADDED Requirements

### Requirement: 后端 Django 项目结构
系统 SHALL 在 `backend/` 目录下建立 Django 项目，包含一个 `api` 应用，使用 Django REST Framework 提供 JSON API，通过 MySQL 持久化数据，并配置 CORS 允许前端跨域访问。

#### Scenario: 启动后端服务
- **WHEN** 开发者执行 `python manage.py migrate && python manage.py loaddata seed_data.json && python manage.py runserver`
- **THEN** 后端在 `http://localhost:8000` 启动，数据库表结构创建完成，种子数据导入成功

#### Scenario: 前端跨域访问 API
- **WHEN** 前端从 `http://localhost:5173`（Vite dev server）请求后端 API
- **THEN** 后端返回正确的 CORS 头，前端能正常获取数据

### Requirement: MySQL 数据模型
系统 SHALL 在 MySQL 中建立以下数据表：
- `cases`：案件（id、标题、描述、创建时间）
- `evidences`：证据（id、case_id 外键、编号、类型、描述、来源时间、是否含敏感信息、排序序号）
- `timeline_nodes`：时间线节点（id、case_id 外键、日期时间、事件描述、关联证据编号、排序序号）
- `complaint_templates`：投诉模板（id、case_id 外键、模板类型、标题、正文）

#### Scenario: 数据表关系完整性
- **WHEN** 查询某个案件的完整数据
- **THEN** 能通过 case_id 外键关联查出该案件的所有证据、时间线节点、投诉模板

### Requirement: 后端 REST API
系统 SHALL 提供以下 REST API 端点：
- `GET /api/cases/<id>/`：获取案件详情（含证据数、节点数、模板数统计）
- `GET /api/cases/<id>/evidences/`：获取证据列表
- `POST /api/cases/<id>/evidences/`：新增证据（后端自动分配编号）
- `DELETE /api/evidences/<id>/`：删除证据
- `GET /api/cases/<id>/timeline/`：获取时间线节点
- `PATCH /api/timeline-nodes/<id>/`：更新时间线节点描述
- `GET /api/cases/<id>/complaints/?template=<type>`：获取指定模板的投诉文本
- `POST /api/cases/<id>/mask/`：对指定内容执行打码并返回结果
- `POST /api/cases/<id>/export/`：生成导出包（返回文本内容供前端下载）

#### Scenario: 获取案件详情
- **WHEN** 前端请求 `GET /api/cases/1/`
- **THEN** 返回 JSON 包含案件标题、描述、证据数量、时间线节点数量、投诉模板数量

#### Scenario: 新增证据自动编号
- **WHEN** 前端请求 `POST /api/cases/1/evidences/` 提交新证据
- **THEN** 后端根据当前最大编号自动分配下一个编号（如已有 E4 则新证据为 E5），返回完整证据对象

### Requirement: 后端业务逻辑服务
系统 SHALL 在 `backend/api/services/` 下实现核心业务逻辑：
- 证据编号服务：根据案件现有证据数自动生成下一个编号
- 时间线重建服务：从证据的来源时间字段排序生成时间线节点
- 投诉文本生成服务：根据模板类型与案件数据生成结构化投诉文本，自动插入证据编号引用
- 打码服务：用正则识别手机号（11 位）、身份证号（18 位）、地址关键词并替换为打码形式

#### Scenario: 投诉文本含证据引用
- **WHEN** 调用投诉文本生成服务生成"平台客服版"
- **THEN** 返回的文本中包含形如"（见 E2）"的证据编号引用，引用编号与证据列表一致

#### Scenario: 打码服务处理敏感信息
- **WHEN** 调用打码服务处理含 `13812345678` 的文本
- **THEN** 返回 `138****5678`；身份证号 `110101199001011234` 返回 `110***********1234`；地址中"北京市朝阳区XX路"返回"北京市******"

### Requirement: 前端 Vue 项目结构
系统 SHALL 在 `frontend/` 目录下建立 Vue 3 + Vite 项目，使用 Vue Router 管理路由、Pinia 管理全局状态、Axios 调用后端 API，实现单页应用式工作台。

#### Scenario: 启动前端开发服务
- **WHEN** 开发者执行 `npm install && npm run dev`
- **THEN** Vite dev server 在 `http://localhost:5173` 启动，浏览器打开后显示工作台界面

#### Scenario: 前端调用后端 API
- **WHEN** 前端视图组件通过 Axios 调用后端 API
- **THEN** 请求带正确的 baseURL（`http://localhost:8000/api`），响应数据被 Pinia store 持有并驱动视图渲染

### Requirement: Demo 工作台主框架
前端 SHALL 提供一个单页应用式工作台界面，左侧为功能导航（案件工作台 / 证据导入 / 时间线校正 / 投诉文本 / 隐私打码 / 导出与提交），右侧为对应功能视图，点击导航切换视图且保持状态。

#### Scenario: 用户进入 Demo
- **WHEN** 用户打开前端首页
- **THEN** 默认显示"案件工作台"视图，顶部展示案例标题、证据数量、关键节点数、投诉版本数等概览卡片，数据来自后端 API

#### Scenario: 切换功能视图
- **WHEN** 用户点击左侧导航中的"时间线校正"
- **THEN** 右侧内容区切换为时间线校正视图，导航项高亮状态同步更新，Pinia 中的状态不丢失

### Requirement: 证据导入与自动编号视图
前端 SHALL 在"证据导入"视图中调用后端 API 展示证据列表，每条证据显示编号（E1、E2…）、类型标签、描述、来源时间，并支持新增与删除。

#### Scenario: 查看证据清单
- **WHEN** 用户进入"证据导入"视图
- **THEN** 组件调用 `GET /api/cases/<id>/evidences/` 获取数据并渲染证据卡片列表

#### Scenario: 新增证据
- **WHEN** 用户点击"添加示例证据"按钮
- **THEN** 前端调用 `POST /api/cases/<id>/evidences/`，后端自动编号后返回，列表实时更新

### Requirement: 事实时间线重建与校正视图
前端 SHALL 在"时间线校正"视图中调用后端 API 展示按时间排序的时间线节点，每个节点显示日期时间、事件描述、关联证据编号，支持就地编辑描述。

#### Scenario: 查看自动重建的时间线
- **WHEN** 用户进入"时间线校正"视图
- **THEN** 组件调用 `GET /api/cases/<id>/timeline/` 获取数据，以纵向时间线形式渲染节点

#### Scenario: 校正时间线节点
- **WHEN** 用户编辑某节点描述并失焦
- **THEN** 前端调用 `PATCH /api/timeline-nodes/<id>/` 提交修改，成功后视图更新

### Requirement: 多模板投诉文本视图
前端 SHALL 在"投诉文本"视图中提供三套模板切换（平台客服版 / 监管投诉版 / 仲裁准备版），切换时调用后端 API 获取对应模板文本，证据编号引用高亮显示，支持复制全文。

#### Scenario: 切换投诉模板
- **WHEN** 用户选择"监管投诉版"
- **THEN** 前端调用 `GET /api/cases/<id>/complaints/?template=regulatory`，文本预览区刷新为监管投诉版内容

#### Scenario: 复制投诉文本
- **WHEN** 用户点击"复制全文"按钮
- **THEN** 当前模板纯文本被复制到剪贴板，页面给出复制成功提示

### Requirement: 隐私打码视图
前端 SHALL 在"隐私打码"视图中展示证据中的敏感信息，提供"一键打码"开关，开关切换时调用后端打码服务并预览效果。

#### Scenario: 开启一键打码
- **WHEN** 用户打开"一键打码"开关
- **THEN** 前端调用 `POST /api/cases/<id>/mask/`，预览区中手机号、地址、身份证号被替换为打码形式

#### Scenario: 关闭打码查看原文
- **WHEN** 用户关闭"一键打码"开关
- **THEN** 预览区恢复显示原始敏感信息

### Requirement: 导出与提交视图
前端 SHALL 在"导出与提交"视图中提供导出格式选项，展示导出清单，选择"文本包"时调用后端导出 API 并触发浏览器下载 `.txt` 文件。

#### Scenario: 模拟导出
- **WHEN** 用户选择"文本包"并点击"导出"
- **THEN** 前端调用 `POST /api/cases/<id>/export/` 获取文本内容，展示导出清单，并触发浏览器下载包含投诉文本 + 证据清单 + 时间线的 `.txt` 文件

### Requirement: 视觉一致性
前端 SHALL 复用展示页的主题变量与组件风格，包括配色（`--accent: #2f6bff` / `--accent2: #11b981`）、字体栈、圆角、卡片样式、按钮样式，确保 Demo 与展示页视觉统一。

#### Scenario: 视觉风格延续
- **WHEN** 用户从展示页跳转到 Demo
- **THEN** 两个页面的配色、字体、卡片圆角、按钮形态保持一致，无明显视觉割裂

### Requirement: 展示页与 Demo 互通导航
展示页 `claimcraft-creative.html` 与前端 Demo SHALL 互相提供入口链接。

#### Scenario: 从展示页进入 Demo
- **WHEN** 用户在展示页点击"体验交互 Demo"入口
- **THEN** 浏览器跳转到前端 dev server 地址（`http://localhost:5173`）

#### Scenario: 从 Demo 返回展示页
- **WHEN** 用户在 Demo 顶部点击"返回介绍页"
- **THEN** 浏览器跳转回 `claimcraft-creative.html`
