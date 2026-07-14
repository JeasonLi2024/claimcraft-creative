# ClaimCraft 用户体系与 JWT 认证后端优化设计

> 文档状态：设计稿，不包含后端代码修改  
> 适用项目：ClaimCraft（Django 4.2、Django REST Framework、SimpleJWT、MySQL）  
> 目标：支撑个人信息管理、头像、使用偏好、密码安全、登录设备和令牌撤销等前端能力。

## 1. 背景与结论

### 1.1 Django 是否自带 JWT

Django 自带的是 Session、Cookie、用户认证、权限和密码哈希机制，**Django 本身不原生提供 JWT**。当前项目使用的是第三方库 `djangorestframework-simplejwt`，它是 DRF 生态中成熟、常用的 JWT 实现，可以继续使用，无需自行开发 JWT 签发、解析和校验逻辑。

当前项目已经具备：

- `JWTAuthentication`；
- `TokenObtainPairView`：签发 access token 和 refresh token；
- `TokenRefreshView`：刷新 access token；
- `TokenVerifyView`：校验 token；
- access token 2 小时、refresh token 7 天的基础配置。

当前项目尚未启用：

- `rest_framework_simplejwt.token_blacklist` 应用；
- refresh token 轮换；
- token 轮换后的自动拉黑；
- 主动登出接口；
- 全设备退出；
- 登录设备和会话元数据；
- 前端 refresh token 的完整保存与自动刷新闭环。

因此结论是：**可以且应该继续使用 SimpleJWT，并启用其 blacklist 能力；但 blacklist 只解决 refresh/sliding token 的撤销，不等同于完整的设备会话管理。**

### 1.2 设计原则

1. 不自研 JWT 密码学和 token 格式。
2. access token 短时有效、无状态校验；refresh token 可轮换、可撤销。
3. 用户基础身份与业务资料解耦。
4. 当前已经上线并被外键引用的 Django `auth.User` 不做高风险替换。
5. 个人资料、偏好和安全会话使用扩展模型承载。
6. 所有账户修改接口仅作用于 `request.user`，不接收任意用户 ID。
7. 敏感操作需要旧密码、限流、审计和会话撤销。
8. API 返回结构与前端 `/profile` 页面展示保持一致。

## 2. 现状分析

### 2.1 当前认证配置

项目配置了：

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}
```

认证路由为：

```text
POST /api/auth/login/
POST /api/auth/refresh/
POST /api/auth/verify/
GET  /api/auth/me/
POST /api/auth/register/
```

### 2.2 当前用户信息能力

`UserSerializer` 只暴露：

```text
id、username、email
```

`CurrentUserView` 只支持 `GET /api/auth/me/`，不支持：

- 修改用户名、邮箱或展示名称；
- 上传头像；
- 修改密码；
- 保存偏好；
- 查看登录会话；
- 撤销 refresh token。

### 2.3 当前风险与缺口

1. 前端退出登录只清理本地 token，服务端 refresh token 仍可继续使用。
2. access token 有效期 2 小时，泄露后的风险窗口偏长。
3. 没有 token 轮换，单个 refresh token 可在 7 天内反复使用。
4. 没有 token 黑名单，无法主动撤销 refresh token。
5. 没有记录登录设备，无法实现“退出其他设备”。
6. 用户扩展资料不足，无法支撑头像、展示名、手机号状态、个人简介等功能。
7. 注册接口的请求契约需要统一确认：当前后端序列化器要求 `password2`，前端 DTO 只包含 `password`。
8. 当前 `CORS_ALLOW_ALL_ORIGINS = True` 仅适合开发环境，生产环境需要白名单。

## 3. 总体架构

建议使用以下分层：

```text
Django auth.User
├── 负责：登录标识、密码、email、is_active、权限、last_login、date_joined
│
├── UserProfile（OneToOne）
│   └── 负责：展示名、头像、简介、时区、语言、邮箱验证状态
│
├── UserPreference（OneToOne）
│   └── 负责：提醒、导出安全检查、案件卡片密度、默认文稿模板
│
├── UserSession（OneToMany）
│   └── 负责：设备、登录时间、IP 摘要、refresh JTI、撤销状态
│
└── AccountAuditLog（OneToMany）
    └── 负责：登录、退出、资料修改、密码修改和会话撤销审计

SimpleJWT
├── AccessToken：短期、无状态 API 访问凭据
├── RefreshToken：长期、轮换并可拉黑
└── token_blacklist：OutstandingToken / BlacklistedToken
```

## 4. 用户模型策略

### 4.1 推荐策略：保留 `auth.User`，增加扩展模型

当前项目已经存在用户、案件 owner 外键和历史迁移。此时切换 `AUTH_USER_MODEL` 成本高，容易影响：

- `Case.owner` 等现有外键；
- 管理后台；
- 迁移依赖；
- 现有用户数据；
- LangGraph 中按 user ID 建立的命名空间。

因此本阶段推荐保留 Django `auth.User`，通过一对一模型扩展业务字段。

只有在项目尚未产生任何正式数据、允许重建数据库时，才考虑改为 `AbstractUser` 自定义用户模型。不要在已有生产迁移中直接切换。

### 4.2 `UserProfile`

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `user` | OneToOneField | 主键或唯一关联 `AUTH_USER_MODEL` |
| `display_name` | CharField(64) | 页面展示名，允许为空，回退 username |
| `avatar` | ImageField | 用户头像，可为空 |
| `bio` | CharField(200) | 简短个人说明，可为空 |
| `phone` | CharField(32) | 可选手机号；如无业务需要可暂缓 |
| `phone_verified` | BooleanField | 手机号是否验证 |
| `email_verified` | BooleanField | 邮箱是否验证 |
| `locale` | CharField(16) | 默认 `zh-hans` |
| `timezone` | CharField(64) | 默认 `Asia/Shanghai` |
| `created_at` | DateTimeField | 创建时间 |
| `updated_at` | DateTimeField | 更新时间 |

约束与建议：

- `display_name` 不是登录凭据，不要求唯一；
- `username` 仍作为当前登录标识；
- 手机号不要直接公开返回；需要展示时返回掩码值；
- Profile 可通过 `post_save(User)` 信号创建，也可在注册事务中显式创建；
- 推荐注册事务中显式创建，信号作为历史数据兜底或使用数据迁移补齐。

### 4.3 `UserPreference`

建议字段：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---:|---|
| `user` | OneToOneField | - | 所属用户 |
| `workflow_reminders` | BooleanField | true | 工作流复核提醒 |
| `export_reminder` | BooleanField | true | 导出前隐私检查提醒 |
| `compact_case_cards` | BooleanField | false | 紧凑案件卡片 |
| `default_case_mode` | CharField | complain | 默认案件模式 |
| `default_template_type` | CharField | platform | 默认文稿模板 |
| `updated_at` | DateTimeField | - | 更新时间 |

不建议第一版使用完全无约束的 JSONField。显式字段更容易校验、检索、迁移和生成 API 文档。如果后续偏好快速增长，可增加 `extra = JSONField(default=dict)`，但必须通过白名单序列化器写入。

### 4.4 `UserSession`

SimpleJWT blacklist 能判断 refresh token 是否被撤销，但其 `OutstandingToken` 不包含完整设备体验所需的信息。建议增加业务会话表：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUIDField | 对外会话 ID |
| `user` | ForeignKey | 所属用户 |
| `refresh_jti` | CharField(255), unique | 对应 refresh token 的 JTI |
| `device_name` | CharField(128) | 前端提供或由 User-Agent 解析 |
| `device_type` | CharField(32) | desktop/mobile/tablet/unknown |
| `user_agent` | TextField | 原始 UA，限制长度 |
| `ip_hash` | CharField(64) | IP 加盐哈希，不长期保存明文 |
| `ip_display` | CharField(64) | 可选脱敏展示，如 `10.20.*.*` |
| `last_seen_at` | DateTimeField | 最近刷新或访问时间 |
| `expires_at` | DateTimeField | refresh token 到期时间 |
| `revoked_at` | DateTimeField, null | 主动撤销时间 |
| `created_at` | DateTimeField | 登录时间 |

建议索引：

- `(user, revoked_at, expires_at)`；
- `refresh_jti` 唯一索引；
- `expires_at` 普通索引，便于清理。

### 4.5 `AccountAuditLog`

建议记录：

| 字段 | 说明 |
|---|---|
| `user` | 用户，可为空以记录登录失败 |
| `event_type` | login_success/login_failed/logout/profile_updated/password_changed/session_revoked |
| `session_id` | 可选会话 ID |
| `ip_hash` | IP 哈希 |
| `user_agent` | 客户端摘要 |
| `metadata` | 受控 JSON，不记录密码和 token |
| `created_at` | 时间 |

审计日志禁止记录：

- 密码；
- access token；
- refresh token 原文；
- 完整证件号；
- 完整敏感证据内容。

## 5. SimpleJWT 完善方案

### 5.1 启用 blacklist 应用

设计上需要在 `INSTALLED_APPS` 增加：

```python
"rest_framework_simplejwt.token_blacklist"
```

随后执行官方迁移，创建 `OutstandingToken` 和 `BlacklistedToken` 表。

### 5.2 推荐配置

```python
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "JTI_CLAIM": "jti",
    "CHECK_REVOKE_TOKEN": True,
}
```

说明：

- access token 从 2 小时建议缩短至 15～30 分钟；
- refresh token 保持 7 天；
- 每次刷新都返回新的 refresh token；
- 旧 refresh token 在轮换后进入 blacklist；
- 前端必须原子替换 access 和 refresh token；
- `CHECK_REVOKE_TOKEN` 的具体可用性需依据项目锁定的 SimpleJWT 版本验证；若版本不支持则删除该项，不应自行模拟。

### 5.3 blacklist 能撤销什么

SimpleJWT 官方 blacklist 主要针对：

- refresh token；
- sliding token。

已经签发的普通 access token 默认仍保持无状态，在到期前通常不会逐请求查询 blacklist。因此：

- 主动退出后，refresh token 立即失效；
- 现有 access token 最多还能存活一个 access 生命周期；
- 这正是 access token 应设置为 15～30 分钟的原因。

如果业务要求“退出后 access token 秒级失效”，需要引入 token version、用户级 `password_changed_at`、Redis denylist 或逐请求数据库查询。第一版不建议这样做，因为会削弱 JWT 无状态优势并增加复杂度。

### 5.4 token 存储建议

推荐的 Web 安全方案：

- access token：仅保存在内存状态；
- refresh token：由后端写入 `HttpOnly + Secure + SameSite=Lax/Strict` Cookie；
- refresh、logout 接口从 Cookie 读取 refresh token；
- 前端 JavaScript 不读取 refresh token。

如果当前架构短期内必须继续使用 localStorage：

- access 和 refresh 分开存储；
- 强化 CSP，避免 XSS；
- 任何用户输入输出必须防注入；
- 刷新时原子替换 refresh token；
- 退出时先调用后端 blacklist，再清理本地 token；
- 将迁移到 HttpOnly Cookie 列为安全优化任务。

注意：Cookie 模式需要明确 CSRF 策略。若 refresh/logout 依赖跨站 Cookie，应启用 CSRF Token 或严格 SameSite 与 Origin 校验。

## 6. API 设计

统一前缀：`/api/auth/`。

### 6.1 注册

```http
POST /api/auth/register/
```

请求：

```json
{
  "username": "demo_user",
  "email": "demo@example.com",
  "password": "StrongPassword123!",
  "password_confirm": "StrongPassword123!"
}
```

建议响应 `201`：

```json
{
  "user": {
    "id": 1,
    "username": "demo_user",
    "email": "demo@example.com",
    "display_name": "demo_user",
    "avatar_url": null
  }
}
```

注册与登录建议保持职责分离。注册成功后前端再调用登录接口；如果决定注册即登录，则响应结构必须统一返回 user、access、refresh，并创建 `UserSession`。

### 6.2 登录

```http
POST /api/auth/login/
```

请求：

```json
{
  "username": "demo_user",
  "password": "StrongPassword123!",
  "device_name": "MacBook Pro · Chrome"
}
```

响应：

```json
{
  "access": "...",
  "refresh": "...",
  "access_expires_in": 900,
  "refresh_expires_in": 604800,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user": {
    "id": 1,
    "username": "demo_user",
    "email": "demo@example.com",
    "display_name": "demo_user",
    "avatar_url": null
  }
}
```

若采用 HttpOnly Cookie，JSON 中不返回 `refresh`。

实现建议：自定义 `TokenObtainPairSerializer` 和 View，在 SimpleJWT 签发成功后：

1. 读取 refresh token 的 JTI 和过期时间；
2. 创建 `UserSession`；
3. 记录登录审计；
4. 返回用户摘要和会话 ID。

### 6.3 刷新 token

```http
POST /api/auth/refresh/
```

请求：

```json
{
  "refresh": "..."
}
```

响应：

```json
{
  "access": "new-access",
  "refresh": "new-refresh",
  "access_expires_in": 900,
  "refresh_expires_in": 604800
}
```

refresh 轮换后同步更新 `UserSession.refresh_jti` 和 `expires_at`，旧 refresh 由 SimpleJWT 自动拉黑。

需要考虑并发刷新：同一页面多个请求同时 401 时，只允许一个 refresh Promise 执行，其余请求等待并复用结果。

### 6.4 退出当前设备

```http
POST /api/auth/logout/
Authorization: Bearer <access>
```

请求：

```json
{
  "refresh": "current-refresh-token"
}
```

后端行为：

1. `RefreshToken(refresh).blacklist()`；
2. 校验 token user 与 `request.user` 一致；
3. 将对应 `UserSession.revoked_at` 置为当前时间；
4. 记录审计日志；
5. 返回 `204 No Content`。

即使 token 已经拉黑，也建议按幂等语义返回成功。

### 6.5 退出全部设备

```http
POST /api/auth/logout-all/
```

后端行为：

- 查询当前用户所有未过期、未撤销的 OutstandingToken；
- 为其创建 BlacklistedToken；
- 批量撤销 UserSession；
- 当前 access token 仍可能存活至短期过期。

响应：

```json
{
  "revoked_sessions": 3
}
```

### 6.6 当前用户聚合信息

```http
GET /api/auth/me/
```

建议响应：

```json
{
  "id": 1,
  "username": "demo_user",
  "email": "demo@example.com",
  "display_name": "李用户",
  "avatar_url": "https://.../avatars/1/thumb.webp",
  "bio": "",
  "email_verified": true,
  "phone_masked": "138****1234",
  "phone_verified": false,
  "locale": "zh-hans",
  "timezone": "Asia/Shanghai",
  "date_joined": "2026-07-01T10:00:00+08:00",
  "last_login": "2026-07-14T15:30:00+08:00",
  "preferences": {
    "workflow_reminders": true,
    "export_reminder": true,
    "compact_case_cards": false,
    "default_case_mode": "complain",
    "default_template_type": "platform"
  }
}
```

### 6.7 修改个人信息

```http
PATCH /api/auth/me/
```

允许字段：

```json
{
  "display_name": "李用户",
  "bio": "",
  "locale": "zh-hans",
  "timezone": "Asia/Shanghai"
}
```

用户名和邮箱建议使用独立流程，不与普通资料混改：

- 登录用户名修改需要校验密码、唯一性和修改频率；
- 邮箱修改需要验证新邮箱后再生效。

### 6.8 修改使用偏好

```http
GET   /api/auth/me/preferences/
PATCH /api/auth/me/preferences/
```

请求：

```json
{
  "workflow_reminders": true,
  "export_reminder": true,
  "compact_case_cards": false,
  "default_case_mode": "complain",
  "default_template_type": "platform"
}
```

所有枚举和字段必须由序列化器白名单校验。

### 6.9 头像上传与删除

```http
POST   /api/auth/me/avatar/
DELETE /api/auth/me/avatar/
```

上传使用 `multipart/form-data`，字段名 `avatar`。

约束：

- 文件最大 2 MB；
- 仅 JPEG、PNG、WebP；
- 通过 Pillow 解码验证真实图片，不信任文件扩展名；
- 清除 EXIF；
- 自动纠正旋转；
- 中心裁剪正方形；
- 生成 256×256 WebP 缩略图；
- 文件路径使用随机 UUID，不使用原始文件名；
- 替换头像后异步或事务提交后删除旧文件。

### 6.10 修改密码

```http
POST /api/auth/change-password/
```

请求：

```json
{
  "old_password": "OldPassword123!",
  "new_password": "NewPassword123!",
  "new_password_confirm": "NewPassword123!",
  "logout_other_sessions": true
}
```

行为：

1. 校验旧密码；
2. 使用 Django `validate_password`；
3. `set_password` 保存；
4. 拉黑其他 refresh token；
5. 当前会话是否保留由参数或统一安全策略决定；
6. 写审计日志；
7. 不在响应或日志中返回密码。

### 6.11 会话管理

```http
GET    /api/auth/sessions/
DELETE /api/auth/sessions/{session_id}/
```

响应示例：

```json
{
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "device_name": "MacBook Pro · Chrome",
      "device_type": "desktop",
      "ip_display": "10.20.*.*",
      "created_at": "2026-07-14T10:00:00+08:00",
      "last_seen_at": "2026-07-14T15:30:00+08:00",
      "expires_at": "2026-07-21T10:00:00+08:00",
      "is_current": true
    }
  ]
}
```

删除会话时拉黑其当前 refresh JTI，并标记 `revoked_at`。用户只能操作自己的会话。

## 7. 序列化器边界

建议拆分序列化器，避免一个 `UserSerializer` 同时承担读取、编辑和安全操作：

- `UserSummarySerializer`：菜单和登录响应；
- `UserDetailSerializer`：`GET /auth/me/`；
- `UserProfileUpdateSerializer`：普通资料修改；
- `UserPreferenceSerializer`：偏好读写；
- `RegisterSerializer`：注册；
- `ChangePasswordSerializer`：修改密码；
- `AvatarUploadSerializer`：头像上传；
- `UserSessionSerializer`：会话只读展示；
- `EmailChangeRequestSerializer`：邮箱变更申请；
- `EmailVerifySerializer`：邮箱验证码确认。

字段权限：

- `id`、`date_joined`、`last_login`、验证状态只读；
- `is_staff`、`is_superuser`、`groups`、`permissions` 永不通过普通用户接口开放；
- `username`、`email` 不通过通用 Profile Serializer 直接修改。

## 8. 权限、限流与安全

### 8.1 权限

| 接口 | 权限 |
|---|---|
| 注册、登录、刷新 | AllowAny，但需要限流 |
| 当前用户、资料、偏好、头像、密码 | IsAuthenticated |
| 会话列表和撤销 | IsAuthenticated，仅本人 |
| 邮箱验证回调 | Token/验证码校验 |

### 8.2 限流建议

DRF throttling 或网关限流：

- 登录：按 IP 5 次/分钟、20 次/小时；按用户名增加独立维度；
- 注册：按 IP 3 次/小时；
- refresh：按会话 30 次/分钟；
- 修改密码：5 次/小时；
- 邮箱验证码：3 次/小时；
- 头像上传：10 次/小时。

登录失败响应避免暴露“用户名不存在”或“密码错误”的区别，统一返回“账号或密码错误”。

### 8.3 生产环境配置

- `DEBUG = False`；
- `SECRET_KEY` 仅通过密钥管理或环境变量注入；
- `ALLOWED_HOSTS` 明确配置；
- CORS 使用前端域名白名单，关闭 `CORS_ALLOW_ALL_ORIGINS`；
- 全站 HTTPS；
- Cookie 模式启用 `Secure`、`HttpOnly`、合理 `SameSite`；
- 配置 CSP、HSTS、Referrer-Policy、X-Content-Type-Options；
- 上传文件域名与主站隔离更安全；
- 管理后台启用更严格权限和审计。

### 8.4 账户枚举与隐私

- 注册用户名重复可明确提示，但应限流；
- 密码找回统一返回“如果账号存在，将发送邮件”；
- 会话 IP 只展示脱敏值；
- API 不返回手机号明文；
- 头像 URL 不包含用户名、邮箱等 PII；
- 审计日志设置保留期，例如 180 天。

## 9. 前端对接要求

### 9.1 Auth Store

建议扩展状态：

```text
user
accessToken
isAuthenticated
isInitializing
currentSessionId
```

扩展动作：

```text
login
logout
logoutAll
refreshAccessToken
fetchMe
updateProfile
updatePreferences
changePassword
uploadAvatar
fetchSessions
revokeSession
```

### 9.2 Axios 自动刷新

请求流程：

1. 请求携带 access token；
2. 收到 401 且不是 login/refresh 接口；
3. 使用单例 Promise 发起一次 refresh；
4. 刷新成功后更新 token 并重放队列请求；
5. 刷新失败则清理认证状态并跳转 `/login`；
6. 每个请求最多重试一次，避免无限循环。

### 9.3 与当前页面对应

当前前端页面可以按阶段接入：

| 前端能力 | 当前状态 | 后端完成后 |
|---|---|---|
| 头像菜单用户摘要 | 可用 username/email | 增加 display_name/avatar_url |
| 个人资料页 | 基础信息只读 | 开放资料编辑 |
| 使用偏好 | localStorage | 改为 Preferences API，同步多设备 |
| 修改密码 | 未开放 | 接入 change-password API |
| 登录设备 | 未展示 | 新增会话列表和撤销 |
| 退出登录 | 仅清本地 token | 先调用 logout 拉黑 refresh |
| 全部退出 | 未开放 | 接入 logout-all |

## 10. 数据迁移方案

### 阶段 1：启用 blacklist

1. 加入 `token_blacklist` 应用；
2. 执行官方迁移；
3. 开启 refresh 轮换和轮换后拉黑；
4. 自定义 logout 接口；
5. 前端保存并替换 refresh token；
6. 定期执行 `flushexpiredtokens` 清理过期记录。

建议每天运行：

```bash
python manage.py flushexpiredtokens
```

### 阶段 2：用户扩展资料

1. 新建 `UserProfile`、`UserPreference`；
2. 数据迁移为已有用户批量创建记录；
3. 调整 `/auth/me/` 聚合序列化器；
4. 前端从只读页逐步开放编辑。

数据迁移必须使用历史模型：

```python
User = apps.get_model("auth", "User")
UserProfile = apps.get_model("api", "UserProfile")
```

避免在迁移中直接导入运行时模型。

### 阶段 3：设备会话

1. 新建 `UserSession` 和审计日志；
2. 自定义登录、刷新 View；
3. 建立 JTI 与业务会话映射；
4. 提供会话列表、单设备退出、全部退出；
5. 增加过期会话清理任务。

### 阶段 4：头像、密码和邮箱验证

1. 头像上传处理与存储；
2. 修改密码及其他会话撤销；
3. 邮箱验证令牌和邮件服务；
4. 安全通知和审计展示。

## 11. 测试设计

### 11.1 JWT 测试

- 正确账号密码可签发 token；
- 错误密码不泄漏账户是否存在；
- access 过期后可用 refresh 获取新 token；
- refresh 轮换后旧 refresh 被拉黑；
- 被拉黑 refresh 无法再次使用；
- logout 幂等；
- logout-all 只撤销当前用户 token；
- 用户停用后不能刷新；
- 修改密码后其他会话失效；
- 并发刷新行为符合预期。

### 11.2 用户资料测试

- 用户只能读取和修改自己；
- 只读字段不可篡改；
- display_name、bio 长度校验；
- locale、timezone 枚举或合法值校验；
- 偏好字段白名单；
- 历史用户缺失 Profile 时可安全补建。

### 11.3 头像测试

- 正常 JPEG/PNG/WebP 上传；
- 伪造扩展名拒绝；
- 超大文件拒绝；
- 解码炸弹防护；
- EXIF 被移除；
- 删除头像幂等；
- 用户不能删除他人头像。

### 11.4 会话测试

- 登录创建设备会话；
- refresh 更新 JTI 和 last_seen；
- 当前设备标记正确；
- 撤销其他设备不影响当前设备；
- 用户不能访问或撤销他人会话；
- 过期会话按计划清理。

## 12. 监控与运维

建议监控指标：

- 登录成功率和失败率；
- refresh 成功率；
- token blacklist 命中次数；
- 单用户活跃会话数；
- 异常地区或设备登录；
- 修改密码和全部退出次数；
- 头像上传失败率；
- `OutstandingToken` 表增长速度。

清理任务：

- 每日 `flushexpiredtokens`；
- 每日清理过期 `UserSession`；
- 定期清理无引用头像文件；
- 按保留期归档或删除审计日志。

## 13. 实施优先级

### P0：认证闭环

- 启用 SimpleJWT blacklist；
- access 缩短至 15～30 分钟；
- refresh 轮换和旧 token 拉黑；
- logout 与 logout-all；
- 前端自动刷新和失败退出；
- 修正注册请求契约不一致。

### P1：个人信息页后端化

- `UserProfile`；
- `UserPreference`；
- 扩展 `/auth/me/`；
- Profile 与 Preferences 更新接口；
- 头像上传。

### P2：账户安全中心

- `UserSession`；
- 单设备撤销；
- 修改密码并退出其他设备；
- 审计日志；
- 邮箱验证。

### P3：增强能力

- 密码找回；
- 登录异常通知；
- MFA/OTP；
- 第三方 OAuth 或企业 SSO（如有业务需求）。

## 14. 验收标准

1. refresh token 可轮换、可拉黑，旧 token 不能复用。
2. 用户退出后服务端 refresh token 失效，而不是只清理前端状态。
3. 用户可以读取完整个人资料和跨设备偏好。
4. 用户只能修改自己的资料、偏好、头像和会话。
5. 密码修改使用 Django 密码校验器，并可撤销其他会话。
6. 个人信息页可展示头像、展示名、邮箱验证状态和账户安全状态。
7. 会话页可识别当前设备并退出其他设备。
8. 敏感字段、token 和密码不会进入日志。
9. 生产环境关闭全开放 CORS，并使用 HTTPS 和安全 Cookie 策略。
10. 所有新增接口具备单元测试、权限测试和异常路径测试。

## 15. 最终建议

ClaimCraft 不需要替换 SimpleJWT，也不需要自行实现 JWT。最合理的方案是：

- 保留 Django `auth.User` 作为稳定身份核心；
- 用 `UserProfile` 和 `UserPreference` 扩展个人信息与偏好；
- 启用 SimpleJWT 官方 `token_blacklist`、refresh 轮换和旧 token 自动拉黑；
- 用 `UserSession` 补足设备管理和用户可见的会话体验；
- 用短生命周期 access token 控制退出后的剩余风险窗口；
- 分阶段将当前前端个人信息页从本地只读/本地偏好升级为完整后端能力。

该方案复用 Django 与 SimpleJWT 的成熟能力，兼顾现有数据迁移风险、安全性和后续产品扩展。
