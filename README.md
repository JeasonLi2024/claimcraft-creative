# ClaimCraft 维权材料工坊

> 把"截图 + 聊天记录"一键变成可提交的投诉与证据包。

普通用户遇到网购纠纷、退款扯皮、服务违约时，往往"证据散、时间线乱、不会写投诉材料"。ClaimCraft 通过 OCR + 信息抽取 + 时间线重建 + 模板渲染，把最费时间的整理工作自动化，输出可直接复制粘贴的标准化证据包。

---

## 功能特性

- **证据图片上传**：拖拽上传截图，自动存储与预览（lightbox）
- **OCR 文字识别**：Tesseract 优先（中文 + 英文），自动识别截图文字，异常时 Mock 回退保证流程不中断
- **关键信息自动抽取**：正则识别订单号、金额、手机号、地址、时间、承诺话术，支持人工校正
- **时间线自动重建**：从证据时间字段生成时间线节点，手动节点与自动节点共存，支持重新生成
- **投诉文本动态生成**：Jinja2 模板渲染，三套模板切换（平台客服版 / 监管投诉版 / 仲裁准备版），自动插入证据编号引用
- **隐私打码**：手机号 / 身份证 / 地址文本打码（图片打码与 ZIP 导出规划中）
- **多格式导出**：文本包导出（PDF / 证据包 ZIP 规划中）

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Django 5 + Django REST Framework + MySQL（PyMySQL） |
| 前端 | Vue 3 + Vite + Pinia + Vue Router + Axios |
| OCR | Tesseract（pytesseract，chi_sim + eng） |
| 模板引擎 | Jinja2 |
| 图片处理 | Pillow |

---

## 项目结构

```
claimcraft-creative/
├── backend/                  # Django 后端
│   ├── api/
│   │   ├── models.py        # 数据模型（Case/Evidence/ExtractedField/TimelineNode/...）
│   │   ├── views.py         # REST API 视图
│   │   ├── serializers.py   # 序列化器
│   │   ├── urls.py          # API 路由
│   │   └── services/        # 业务服务
│   │       ├── ocr_service.py          # OCR 识别
│   │       ├── extraction_service.py   # 关键信息抽取
│   │       ├── timeline_service.py     # 时间线重建
│   │       ├── complaint_service.py    # 投诉文本动态生成
│   │       ├── evidence_service.py     # 证据管理
│   │       ├── mask_service.py         # 隐私打码
│   │       └── export_service.py       # 导出
│   ├── claimcraft/          # Django 项目配置
│   ├── media/               # 上传图片存储（gitignored）
│   ├── seed_data.json       # 种子数据
│   ├── requirements.txt
│   └── manage.py
├── frontend/                # Vue 3 前端
│   ├── src/
│   │   ├── views/           # 6 个功能视图
│   │   ├── stores/          # Pinia store
│   │   ├── api/             # Axios 接口封装
│   │   ├── router/          # 路由
│   │   └── styles/          # 样式
│   ├── package.json
│   └── vite.config.js
├── docs/                    # 文档
│   ├── plan.md              # 生态完善任务规划
│   ├── T0_spec.md           # T0 阶段 spec
│   └── T1_spec.md           # T1 阶段 spec
├── claimcraft-creative.html # 项目展示页
└── README.md
```

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- MySQL 8.0+（已配置，也可回退 SQLite）
- Tesseract OCR（可选，未安装时自动回退 Mock）

### 后端启动

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置数据库
# 默认 MySQL，配置见 backend/claimcraft/settings.py
# 如需切换 SQLite，注释 MySQL 块、取消注释 SQLite 块
# 如需创建 MySQL 数据库：
# mysql -u root -p -e "CREATE DATABASE claimcraft DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 执行迁移
python manage.py migrate

# 导入种子数据（含示例案件、8 条证据、抽取字段、时间线、3 套投诉模板）
python manage.py loaddata seed_data.json

# 启动开发服务器
python manage.py runserver
```

后端运行在 `http://localhost:8000`

### 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端运行在 `http://localhost:5173`

### Tesseract 安装（可选，用于真实 OCR）

未安装 Tesseract 时，系统自动回退 Mock OCR，识别预置样本文本，不影响流程。

如需真实 OCR 识别：

1. 下载安装 Tesseract：[GitHub Releases](https://github.com/UB-Mannheim/tesseract/wiki)
2. 安装时勾选 Chinese (Simplified) 语言包
3. 确认安装路径为 `D:\tesseract\tesseract.exe`（或修改 `backend/api/services/ocr_service.py` 中的 `TESSERACT_CMD`）

---

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/cases/<id>/` | 案件详情（含统计） |
| GET | `/api/cases/<id>/evidences/` | 证据列表 |
| POST | `/api/cases/<id>/evidences/upload/` | 上传证据图片（multipart） |
| GET | `/api/evidences/<id>/extracted-fields/` | 证据的抽取字段 |
| PATCH | `/api/extracted-fields/<id>/` | 校正抽取字段 |
| POST | `/api/cases/<id>/timeline/rebuild/` | 重建时间线 |
| GET | `/api/cases/<id>/complaints/?template=platform` | 获取投诉文本 |
| POST | `/api/cases/<id>/complaints/regenerate/` | 重新生成投诉文本 |

完整 API 见后端 `backend/api/urls.py`。

---

## 开发路线

项目采用分阶段迭代：

- **T0（已完成）**：补全创意核心能力——证据图片上传 + OCR + 信息抽取 + 时间线重建 + 动态投诉生成
- **T1（规划中）**：产品闭环——多案件管理 + 状态流转 + 图片打码 + ZIP/PDF 导出
- **T2（规划中）**：工程化——用户体系 + 案件模板预设 + 数据仪表盘 + 部署优化 + 浏览器插件

详见 [docs/plan.md](docs/plan.md)、[docs/T0_spec.md](docs/T0_spec.md)、[docs/T1_spec.md](docs/T1_spec.md)。

---

## 种子数据

导入 `seed_data.json` 后包含：

- 1 个示例案件（网购退款纠纷）
- 8 条证据（E1-E8，含文本与图片证据）
- 12 条抽取字段（订单号、金额、手机号、地址、时间、承诺话术）
- 6 个时间线节点（手动）
- 3 套投诉模板规则（platform / regulatory / arbitration，Jinja2 源码）

---

## 许可证

本项目仅用于学习与演示目的。
