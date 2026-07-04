# T2 阶段方案：工程化与体验提升（用户体系 + 案件模板预设 + 数据仪表盘 + Docker 部署）

> 承接 T0（核心链路）与 T1（产品闭环），本阶段聚焦工程化：从"单机 Demo"进化为"可多人使用、可数据洞察、可容器化部署"的产品。

---

## 一、当前状态分析

### 已完成基础（T0 + T1）
- **后端**：Django 5 + DRF + MySQL，6 个模型，20 条 API 路由，9 个业务服务，django-fsm 状态机
- **前端**：Vue 3 + Vite + Pinia，7 个视图，路由 `/cases/:caseId/xxx`，20 个 store actions
- **展示页**：claimcraft-creative.html，含 echarts 效率对比图

### T2 需解决的 4 个核心缺口
| 缺口 | 现状 | 影响 |
|---|---|---|
| 无用户体系 | 全 `AllowAny`，Case 无 owner，无登录注册 | 无法多人使用，无数据隔离 |
| 无案件模板预设 | 仅 case_type 4 选项，无预设骨架 | 新建案件需手动填写所有内容 |
| 无数据仪表盘 | 无 stats API，前端无 echarts | 无法洞察案件分布与趋势 |
| 无法容器化部署 | DEBUG=True，baseURL 硬编码，无 Dockerfile/nginx | 无法一键部署 |

### 关键架构约束（探索发现）
1. **不能新增自定义 User 模型**：项目已有 migration 与数据，Django 中 `AUTH_USER_MODEL` 必须在项目初始时设置。**解决方案**：直接使用 Django 内置 `django.contrib.auth.models.User`，Case 加 `owner` 外键指向它
2. **前端 baseURL 硬编码** `http://localhost:8000/api`：T2 改为相对路径 `/api`（vite proxy 已配置，Docker nginx 反代也走 `/api`）
3. **echarts 已存在于展示页**（`_shared/js/echarts.min.js`）：前端仪表盘可复用主题色变量 `--accent`/`--accent2`
4. **Case 已有 case_type + status + CaseStatusLog**：仪表盘统计可直接聚合这些字段
5. **ComplaintTemplateRule 已有 case=null 的全局规则**：案件模板预设可复用此机制

---

## 二、决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| T2 范围 | Task 26-29（浏览器插件 Task 30 延后至 T3） | 插件是独立大工程，延后更聚焦 |
| 鉴权方案 | JWT（djangorestframework-simplejwt） | 无状态，适合 SPA + 未来插件扩展 |
| 部署方式 | Docker 全量（docker-compose: mysql + backend + nginx） | 一键启动，可移植，生产就绪 |
| User 模型 | Django 内置 User（不新建自定义模型） | 避免已有 migration 冲突，最小改动 |
| 前端 baseURL | 改为相对路径 `/api` | 同时适配 dev proxy 与 Docker nginx 反代 |

---

## 三、任务拆解与实现方案

### Task 26：用户体系与案件归属

#### 3.1.1 后端改动

**`backend/requirements.txt`** — 新增：
```
djangorestframework-simplejwt>=5.3
```

**`backend/claimcraft/settings.py`** — 修改 REST_FRAMEWORK 配置：
```python
from datetime import timedelta
from datetime import timezone  # 如需

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
# JWT 配置
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}
```
- 注意：开发期可保留一个 `AllowAny` 的白名单（登录/注册端点）

**`backend/api/models.py`** — Case 模型新增 owner 外键：
```python
from django.contrib.auth.models import User

class Case(models.Model):
    # ... 现有字段 ...
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='cases',
        verbose_name='所属用户', null=True, blank=True  # null=True 兼容现有数据
    )
```
- 迁移后需将现有 Case(pk=1) 的 owner 设为 admin 用户（在 migration 或 seed_data 中处理）

**`backend/api/serializers.py`** — 新增：
- `UserSerializer`：序列化 id/username/email
- `RegisterSerializer`：username/email/password/password2，含 validate 方法
- `CaseSerializer`/`CaseListSerializer`：新增 `owner` 字段（只读）

**`backend/api/views.py`** — 新增鉴权视图 + 改造现有视图：
- `RegisterView`（APIView）：POST 注册，返回用户信息
- 使用 simplejwt 内置 `TokenObtainPairView`（登录）、`TokenRefreshView`（刷新）、`TokenVerifyView`（验证）
- **改造所有 Case 相关视图**：
  - `CaseListCreateView.get_queryset()`：`return Case.objects.filter(owner=request.user)`（仅返回当前用户案件）
  - `CaseListCreateView.perform_create()`：`instance.owner = request.user`
  - `CaseDetailView`/`CaseUpdateDeleteView`：检查 `obj.owner == request.user`，否则 404
  - Evidence/Timeline/Complaint 等子资源视图：通过 case.owner 间接校验归属

**`backend/api/permissions.py`**（新建）：
```python
from rest_framework.permissions import BasePermission

class IsOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        if hasattr(obj, 'case'):
            return obj.case.owner == request.user
        if hasattr(obj, 'evidence'):
            return obj.evidence.case.owner == request.user
        return False
```

**`backend/api/urls.py`** — 新增路由：
```python
path('auth/register/', RegisterView.as_view()),
path('auth/login/', TokenObtainPairView.as_view()),
path('auth/refresh/', TokenRefreshView.as_view()),
path('auth/verify/', TokenVerifyView.as_view()),
path('auth/me/', CurrentUserView.as_view()),  # GET 返回当前用户信息
```
- `login`/`register`/`refresh`/`verify` 端点设为 `AllowAny`，其余 `IsAuthenticated`

**`backend/seed_data.json`** — 新增 admin 用户（或 migration 中创建）：
- 创建 superuser：username=admin, password=admin123, email=admin@example.com
- 将现有 Case(pk=1) 的 owner 设为 admin

#### 3.1.2 前端改动

**`frontend/src/api/index.js`** — 改造 axios 实例：
```js
const api = axios.create({
  baseURL: '/api',  // 从 http://localhost:8000/api 改为相对路径
  timeout: 30000,
})

// 请求拦截器：注入 JWT
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截器：401 → 清除 token + 跳转登录
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      router.push('/login')
    }
    return Promise.reject(err)
  }
)
```

**`frontend/src/api/auth.js`**（新建）：
```js
export const login = (data) => api.post('/auth/login/', data)
export const register = (data) => api.post('/auth/register/', data)
export const refreshToken = (data) => api.post('/auth/refresh/', data)
export const verifyToken = (data) => api.post('/auth/verify/', data)
export const getMe = () => api.get('/auth/me/')
```

**`frontend/src/stores/auth.js`**（新建 Pinia store）：
- state：`user`（null）、`token`（null）、`isAuthenticated`（computed）
- actions：`login`、`register`、`logout`、`fetchMe`、`initialize`（mounted 时从 localStorage 恢复）

**`frontend/src/views/LoginView.vue`**（新建）：
- 登录表单（用户名/密码）+ "切换注册"链接
- 调用 login，成功后存 token + 跳转 `/cases`

**`frontend/src/views/RegisterView.vue`**（新建）：
- 注册表单（用户名/邮箱/密码/确认密码）
- 调用 register，成功后自动登录 + 跳转 `/cases`

**`frontend/src/router/index.js`** — 新增路由 + 路由守卫：
```js
{ path: '/login', name: 'login', component: LoginView, meta: { public: true } },
{ path: '/register', name: 'register', component: RegisterView, meta: { public: true } },

// beforeEach 守卫
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  if (to.meta.public || authStore.isAuthenticated) {
    next()
  } else {
    next('/login')
  }
})
```

**`frontend/src/App.vue`** — 导航栏改造：
- 未登录：显示"登录"/"注册"按钮
- 已登录：显示用户名 + "退出"按钮
- "我的案件"仅登录后可见

---

### Task 27：案件模板预设

#### 3.2.1 后端改动

**`backend/api/models.py`** — 新增 `CaseTypePreset` 模型：
```python
class CaseTypePreset(models.Model):
    case_type = models.CharField('纠纷类型', max_length=20, choices=Case.CASE_TYPES)
    name = models.CharField('预设名称', max_length=100)
    description = models.TextField('预设说明', blank=True, default='')
    # 预设证据类型列表（JSON）
    evidence_types = models.JSONField('证据类型建议', default=list)
    # 预设时间线骨架（JSON）
    timeline_skeleton = models.JSONField('时间线骨架', default=list)
    # 预设投诉模板（Jinja2）
    complaint_template = models.TextField('投诉模板', blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['case_type', 'id']
```

**`backend/api/serializers.py`** — 新增 `CaseTypePresetSerializer`

**`backend/api/views.py`** — 新增 `CaseTypePresetListView`：
- `GET /api/case-presets/`：返回所有预设（支持 `?case_type=shopping` 过滤）
- `POST /api/cases/<id>/apply-preset/`：将预设套用到案件（创建证据骨架 + 时间线骨架 + 投诉模板规则）

**`backend/api/urls.py`** — 新增路由：
```python
path('case-presets/', CaseTypePresetListView.as_view()),
path('cases/<int:pk>/apply-preset/', ApplyPresetView.as_view()),
```

**`backend/seed_data.json`** — 为 4 种 case_type 各预置 1 个预设：
- shopping：证据类型建议（订单截图/聊天记录/商品照片/物流信息）、时间线骨架（下单/付款/发货/收货/沟通）、投诉模板（Jinja2）
- service：证据类型建议（合同/聊天记录/付款凭证/服务结果）、时间线骨架（签约/付款/服务开始/沟通/违约）
- secondhand：证据类型建议（商品描述截图/聊天记录/付款凭证/收货照片）、时间线骨架（浏览/沟通/付款/收货/发现问题）
- other：通用骨架

#### 3.2.2 前端改动

**`frontend/src/views/CaseListView.vue`** — 新建案件弹窗改造：
- 选择纠纷类型后，展示"可用预设"下拉（调用 `GET /api/case-presets/?case_type=xxx`）
- 勾选"套用预设骨架"选项
- 创建案件后，如勾选则调用 `POST /api/cases/<id>/apply-preset/`

**`frontend/src/api/case.js`** — 新增：
```js
export const fetchCasePresets = (caseType) => api.get('/case-presets/', { params: { case_type: caseType } })
export const applyPreset = (caseId, presetId) => api.post(`/cases/${caseId}/apply-preset/`, { preset_id: presetId })
```

---

### Task 28：数据统计仪表盘

#### 3.3.1 后端改动

**`backend/api/views.py`** — 新增 `StatsView`：
```python
class StatsView(APIView):
    def get(self, request):
        return Response({
            'case_type_distribution': ...,  # 按 case_type 分组计数
            'status_distribution': ...,      # 按 status 分组计数
            'evidence_total': ...,
            'extracted_field_total': ...,
            'cases_recent_30days': ...,     # 最近 30 天每日新建案件数
            'status_transitions': ...,       # CaseStatusLog 按 to_status 分组
        })
```
- 所有统计仅针对 `request.user` 的案件（数据隔离）

**`backend/api/urls.py`** — 新增：
```python
path('stats/', StatsView.as_view()),
```

#### 3.3.2 前端改动

**`frontend/package.json`** — 新增依赖：`echarts`（npm 包，非展示页的本地文件）

**`frontend/src/views/DashboardView.vue`**（新建）：
- 顶部统计卡片：案件总数 / 证据总数 / 抽取字段总数 / 处理中案件数
- 饼图：案件类型分布（case_type）
- 柱状图：案件状态分布（status）
- 折线图：最近 30 天案件创建趋势
- 柱状图：状态转换统计（从 CaseStatusLog 聚合）
- 所有图表复用 `--accent`/`--accent2` 主题色

**`frontend/src/api/stats.js`**（新建）：
```js
export const fetchStats = () => api.get('/stats/')
```

**`frontend/src/stores/case.js`** — 新增 `stats` state + `fetchStats` action

**`frontend/src/router/index.js`** — 新增路由：
```js
{ path: '/dashboard', name: 'dashboard', component: DashboardView }
```

**`frontend/src/App.vue`** — 导航栏新增"数据仪表盘"入口

---

### Task 29：Docker 全量部署

#### 3.4.1 后端改动

**`backend/claimcraft/settings.py`** — 环境变量分层：
```python
import os
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-xxx')
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',')

# MySQL（从环境变量读取）
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'claimcraft'),
        'USER': os.environ.get('DB_USER', 'root'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'Xx041123@#'),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        ...
    }
}

STATIC_ROOT = BASE_DIR / 'staticfiles'  # collectstatic 输出目录
```

**`backend/requirements.txt`** — 新增：
```
gunicorn>=21.2
whitenoise>=6.6
```

**`backend/claimcraft/wsgi.py`** — 添加 whitenoise 中间件（可选，如用 nginx 则不需要）

#### 3.4.2 新建 Docker 相关文件

**`Dockerfile.backend`**（后端镜像）：
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-chi-sim && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
EXPOSE 8000
CMD ["gunicorn", "claimcraft.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
```

**`Dockerfile.frontend`**（前端构建 + nginx）：
```dockerfile
FROM node:18-alpine AS build
WORKDIR /app
COPY frontend/package*.json .
RUN npm install
COPY frontend/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

**`nginx.conf`**：
```nginx
server {
    listen 80;
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    location /media/ {
        proxy_pass http://backend:8000;
    }
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

**`docker-compose.yml`**：
```yaml
version: '3.8'
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_DATABASE: claimcraft
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    environment:
      - DJANGO_DEBUG=False
      - DJANGO_SECRET_KEY=${SECRET_KEY}
      - DB_HOST=mysql
      - DB_PASSWORD=${DB_PASSWORD}
    depends_on:
      - mysql
    command: >
      sh -c "python manage.py migrate &&
             python manage.py loaddata seed_data.json &&
             gunicorn claimcraft.wsgi:application --bind 0.0.0.0:8000 --workers 3"
    volumes:
      - media_data:/app/media

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  mysql_data:
  media_data:
```

**`.env.example`**：
```
DB_PASSWORD=changeme
SECRET_KEY=changeme-too
```

**`.dockerignore`**：
```
node_modules/
__pycache__/
*.pyc
.git/
media/
db.sqlite3
.venv/
dist/
```

#### 3.4.3 前端改动

**`frontend/src/api/index.js`** — baseURL 改为 `/api`（已在 Task 26 完成）

**`frontend/vite.config.js`** — 确认 proxy 配置（已有，无需改）：
```js
server: { proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } } }
```

#### 3.4.4 文档

**`README.md`** — 更新部署说明：
- 新增 Docker 部署章节（`docker-compose up -d`）
- 新增环境变量说明
- 开发模式说明保留

---

## 四、文件变更清单

### 新建文件
| 文件 | 任务 |
|---|---|
| `backend/api/permissions.py` | Task 26 |
| `frontend/src/api/auth.js` | Task 26 |
| `frontend/src/stores/auth.js` | Task 26 |
| `frontend/src/views/LoginView.vue` | Task 26 |
| `frontend/src/views/RegisterView.vue` | Task 26 |
| `frontend/src/views/DashboardView.vue` | Task 28 |
| `frontend/src/api/stats.js` | Task 28 |
| `Dockerfile.backend` | Task 29 |
| `Dockerfile.frontend` | Task 29 |
| `nginx.conf` | Task 29 |
| `docker-compose.yml` | Task 29 |
| `.env.example` | Task 29 |
| `.dockerignore` | Task 29 |

### 修改文件
| 文件 | 任务 | 改动 |
|---|---|---|
| `backend/api/models.py` | 26 | Case 加 owner FK；新增 CaseTypePreset 模型 |
| `backend/api/views.py` | 26/27/28 | 鉴权视图 + owner 过滤 + 预设视图 + stats 视图 |
| `backend/api/serializers.py` | 26/27 | UserSerializer + RegisterSerializer + CaseTypePresetSerializer |
| `backend/api/urls.py` | 26/27/28 | auth 路由 + preset 路由 + stats 路由 |
| `backend/api/migrations/0004_t2_owner_preset.py` | 26/27 | owner + CaseTypePreset |
| `backend/claimcraft/settings.py` | 26/29 | JWT 配置 + 环境变量分层 + STATIC_ROOT |
| `backend/requirements.txt` | 26/29 | simplejwt + gunicorn + whitenoise |
| `backend/seed_data.json` | 26/27 | admin 用户 + owner 赋值 + 4 套预设 |
| `frontend/src/api/index.js` | 26 | baseURL→/api + 拦截器 |
| `frontend/src/stores/case.js` | 28 | stats state + fetchStats |
| `frontend/src/router/index.js` | 26/28 | login/register/dashboard 路由 + 守卫 |
| `frontend/src/App.vue` | 26/28 | 用户信息 + 仪表盘入口 |
| `frontend/src/views/CaseListView.vue` | 27 | 预设选择 |
| `frontend/src/api/case.js` | 27 | preset 接口 |
| `frontend/package.json` | 28 | echarts 依赖 |
| `README.md` | 29 | Docker 部署说明 |

---

## 五、推进顺序与依赖

```
Task 26（用户体系）→ Task 27（模板预设）→ Task 28（仪表盘）→ Task 29（Docker 部署）
```

- **Task 26 必须最先**：owner FK + JWT 是后续所有任务的基础（仪表盘统计需按 owner 过滤，部署需包含鉴权配置）
- **Task 27 依赖 Task 26**：预设套用到案件需鉴权
- **Task 28 依赖 Task 26**：stats 按 owner 过滤
- **Task 29 依赖 Task 26-28**：Docker 镜像需包含全部功能

---

## 六、验证步骤

### Task 26 验证
- [ ] POST /api/auth/register/ 创建用户返回 201
- [ ] POST /api/auth/login/ 返回 access_token + refresh_token
- [ ] GET /api/auth/me/ 携带 Bearer token 返回用户信息
- [ ] GET /api/cases/ 只返回当前用户案件
- [ ] 无 token 访问 /api/cases/ 返回 401
- [ ] 前端登录后能正常使用所有功能
- [ ] 前端未登录访问任何页面重定向到 /login

### Task 27 验证
- [ ] GET /api/case-presets/ 返回 4 套预设
- [ ] POST /api/cases/<id>/apply-preset/ 创建证据+时间线骨架
- [ ] 前端新建案件时可选预设

### Task 28 验证
- [ ] GET /api/stats/ 返回正确聚合数据
- [ ] 前端仪表盘 4 种图表正常渲染
- [ ] 图表颜色与主题一致

### Task 29 验证
- [ ] `docker-compose up -d` 一键启动成功
- [ ] 浏览器访问 http://localhost 可正常使用
- [ ] Tesseract OCR 在容器内正常工作
- [ ] 媒体文件（上传图片）持久化到 volume

---

## 七、风险与注意事项

1. **Django User 模型迁移风险**：不新建自定义 User，直接用内置 User + Case.owner FK。owner 设为 nullable 兼容现有数据，migration 后将 pk=1 的 owner 设为 admin
2. **Docker 内 Tesseract**：Dockerfile.backend 需安装 tesseract-ocr + tesseract-ocr-chi-sim 包，OCR 在容器内运行
3. **前端 baseURL 变更**：从 `http://localhost:8000/api` 改为 `/api`，dev 模式走 vite proxy，Docker 模式走 nginx 反代。需确认现有功能不受影响
4. **JWT 与现有 AllowAny 的兼容**：登录/注册端点设为 AllowAny，其余 IsAuthenticated。migration 后需确保现有种子数据案件有 owner
5. **echarts 版本兼容**：前端 npm 安装 echarts 5.x，与展示页的本地 echarts.min.js 独立，互不影响
