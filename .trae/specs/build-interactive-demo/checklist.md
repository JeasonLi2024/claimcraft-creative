# Checklist

## 后端（Django + MySQL）
- [x] `backend/` 目录存在，Django 项目 `claimcraft` 与 `api` 应用结构完整
- [x] `settings.py` 已配置 MySQL 数据库、DRF、django-cors-headers
- [x] `requirements.txt` 列出 Django、djangorestframework、django-cors-headers、mysqlclient/PyMySQL
- [x] `api/models.py` 定义了 Case、Evidence、TimelineNode、ComplaintTemplate 四个模型，外键关系正确
- [x] `python manage.py makemigrations && migrate` 可成功执行，MySQL 中表结构创建完成
- [x] `seed_data.json` fixture 包含一个完整案件（含 6-8 条证据、5-6 个时间线节点、3 套投诉模板）
- [x] `python manage.py loaddata seed_data.json` 可成功导入种子数据
- [x] `api/services/` 下实现证据编号、时间线重建、投诉文本生成、打码、导出五个服务
- [x] 投诉文本生成服务输出的文本含证据编号引用（如"见 E2"）
- [x] 打码服务正确处理手机号（`138****5678`）、身份证号（`110***********1234`）、地址关键词
- [x] 所有 REST API 端点可正常响应（GET 案件详情、GET/POST 证据、DELETE 证据、GET 时间线、PATCH 时间线节点、GET 投诉、POST 打码、POST 导出）
- [x] 新增证据 API 可自动分配下一个编号（E1→E2→E3…）
- [x] CORS 配置允许 `http://localhost:5173` 跨域访问

## 前端（Vue 3）
- [x] `frontend/` 目录存在，Vue 3 + Vite 项目结构完整
- [x] `package.json` 包含 vue、vue-router、pinia、axios 依赖
- [x] `npm install && npm run dev` 可在 `http://localhost:5173` 启动
- [x] 全局样式复用展示页主题变量（`--accent: #2f6bff` / `--accent2: #11b981` / 字体栈 / 圆角）
- [x] Axios 实例配置 baseURL `http://localhost:8000/api`
- [x] Pinia store 持有当前案件、证据列表、时间线节点、当前模板、打码状态
- [x] 顶部导航栏含品牌标识与"返回介绍页"链接
- [x] 左侧功能导航含 6 项（案件工作台 / 证据导入 / 时间线校正 / 投诉文本 / 隐私打码 / 导出与提交），点击切换路由并高亮
- [x] 案件工作台视图展示案例标题与概览卡片（证据数量、关键节点数、投诉版本数），数据来自后端 API
- [x] 证据导入视图展示证据卡片列表（编号、类型标签、描述、来源时间），数据来自后端 API
- [x] 证据导入视图"添加示例证据"按钮可新增证据且编号自动递增
- [x] 证据导入视图可删除证据
- [x] 时间线校正视图以纵向时间线展示节点（日期、事件描述、关联证据编号）
- [x] 时间线校正视图支持就地编辑事件描述，失焦后 PATCH 提交并更新视图
- [x] 投诉文本视图提供三套模板切换，切换后文本即时刷新
- [x] 投诉文本中的证据编号引用高亮显示
- [x] 投诉文本视图"复制全文"按钮可复制内容到剪贴板并给出成功提示
- [x] 隐私打码视图展示识别到的敏感信息列表（手机号、地址、身份证号）
- [x] 隐私打码视图"一键打码"开关可切换原文/打码显示，打码格式符合规则
- [x] 导出与提交视图展示导出清单（证据数量、模板版本、打码状态）
- [x] 导出与提交视图选择"文本包"导出时可下载 `.txt` 文件，内容包含投诉文本 + 证据清单 + 时间线

## 互通与视觉
- [x] `claimcraft-creative.html` 导航栏新增"体验交互 Demo"链接指向 `http://localhost:5173`
- [x] Demo 顶部导航栏"返回介绍页"链接指向 `claimcraft-creative.html`
- [x] 前端配色、字体、卡片、按钮与展示页视觉一致，无明显割裂
- [x] 窄屏（≤920px）下导航与各视图布局正常，无溢出或错位
- [x] 未修改 `claimcraft-creative.html` 的原有展示内容（仅新增 Demo 入口链接）、`assets/charts.js`、`assets/hero_claimcraft.jpg`、`_shared/`
