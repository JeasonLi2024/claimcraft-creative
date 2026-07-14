# ClaimCraft 用户认证与账户中心后端重构 Spec

## Why
当前前端已经完成重新设计后的 `/cases` 页面和新增的 `/profile` 页面，但后端用户域能力仍停留在基础 `register/login/refresh/me` 阶段，无法支撑服务端偏好、密码修改、设备会话、退出当前设备与全部设备等真实账户中心能力。同时，现有前后端契约还存在字段和请求结构不一致问题，例如注册仍要求 `password2`、案件页存在 `dispute_type` 与 `case_type` 的命名分叉。需要在不破坏现有案件域与工作流主链路的前提下，对认证与账户中心后端进行一次聚焦重构。

## What Changes
- 保留 Django 内置 `auth.User` 作为稳定身份核心，不切换 `AUTH_USER_MODEL`
- 启用 `rest_framework_simplejwt.token_blacklist`，补齐 refresh token 撤销与轮换能力
- 新增 `UserProfile`、`UserPreference`、`UserSession`、`AccountAuditLog` 四类用户域模型
- 将 `/api/auth/login/` 与 `/api/auth/refresh/` 从默认 SimpleJWT 视图改为项目自定义视图，返回与账户中心一致的聚合结果
- 扩展 `/api/auth/me/` 为聚合资料接口，并新增资料修改、偏好读写、密码修改、设备会话与退出接口
- 统一首期接口契约以“后端规范”为准：注册使用 `password_confirm`，案件字段使用 `case_type`
- 前端保持当前“前端持有 token”模式，一期不切换到 HttpOnly Cookie
- 首期不实现头像上传、邮箱验证流程和完整安全平台能力，只保留后续扩展边界

## Impact
- Affected specs: 无直接替代现有 spec，属于用户域新增能力
- Affected code:
  - `backend/claimcraft/settings.py`
  - `backend/api/models.py`
  - `backend/api/serializers.py`
  - `backend/api/views.py`
  - `backend/api/urls.py`
  - `backend/api/migrations/*`
  - `frontend/src/lib/api.ts`
  - `frontend/src/lib/api-client.ts`
  - `frontend/src/stores/auth-store.ts`
  - `frontend/src/types/auth.ts`
  - `frontend/src/types/case.ts`
  - `frontend/src/pages/ProfilePage.tsx`
  - `frontend/src/pages/CaseListPage.tsx`

## ADDED Requirements

### Requirement: 用户资料聚合与编辑
系统 SHALL 在保留 `auth.User` 的前提下，通过 `UserProfile` 聚合并扩展个人资料展示与编辑能力。

#### Scenario: 获取账户中心聚合资料
- **WHEN** 已登录用户请求 `GET /api/auth/me/`
- **THEN** 返回 `id`、`username`、`email`、`display_name`、`bio`、`email_verified`、`locale`、`timezone`、`date_joined`、`last_login` 以及 `preferences`

#### Scenario: 修改基础资料
- **WHEN** 已登录用户请求 `PATCH /api/auth/me/` 并提交允许修改的资料字段
- **THEN** 仅更新 `display_name`、`bio`、`locale`、`timezone`
- **AND** `username`、`email`、权限相关字段保持只读

#### Scenario: 历史用户无扩展资料
- **WHEN** 现有老用户尚未拥有 `UserProfile`
- **THEN** 系统能够通过迁移或接口兜底机制补齐默认资料记录
- **AND** 不因为缺失扩展表记录导致 `/api/auth/me/` 失败

### Requirement: 服务端偏好管理
系统 SHALL 通过 `UserPreference` 将账户偏好从前端本地存储迁移到服务端。

#### Scenario: 获取偏好
- **WHEN** 已登录用户请求 `GET /api/auth/me/preferences/`
- **THEN** 返回 `workflow_reminders`、`export_reminder`、`compact_case_cards`、`default_case_mode`、`default_template_type`

#### Scenario: 修改偏好
- **WHEN** 已登录用户请求 `PATCH /api/auth/me/preferences/`
- **THEN** 仅允许更新白名单偏好字段
- **AND** 更新后再次获取时返回持久化结果

### Requirement: 登录响应与认证闭环
系统 SHALL 将登录与刷新接口升级为账户中心可直接消费的闭环接口。

#### Scenario: 登录成功返回聚合结果
- **WHEN** 用户请求 `POST /api/auth/login/` 且认证成功
- **THEN** 返回 `access`、`refresh`、`access_expires_in`、`refresh_expires_in`、`session_id` 与 `user`
- **AND** 不再要求前端先写入占位用户再调用 `/api/auth/me/`

#### Scenario: 刷新 token 更新会话
- **WHEN** 用户请求 `POST /api/auth/refresh/`
- **THEN** 返回新的 `access` 与轮换后的 `refresh`
- **AND** 同步更新对应 `UserSession` 的 `refresh_jti`、`last_seen_at`、`expires_at`

#### Scenario: refresh token 被撤销
- **WHEN** 已被拉黑或已撤销的 refresh token 再次用于刷新
- **THEN** 刷新失败并返回认证错误

### Requirement: 当前设备退出与全部设备退出
系统 SHALL 支持退出当前设备和退出全部设备，并同步撤销业务会话。

#### Scenario: 退出当前设备
- **WHEN** 已登录用户请求 `POST /api/auth/logout/` 并提交当前 refresh token
- **THEN** 当前 refresh token 被拉黑
- **AND** 对应 `UserSession.revoked_at` 被设置
- **AND** 接口按幂等方式返回成功

#### Scenario: 退出全部设备
- **WHEN** 已登录用户请求 `POST /api/auth/logout-all/`
- **THEN** 当前用户所有活跃 refresh token 被拉黑
- **AND** 当前用户所有未撤销会话被批量标记为已撤销
- **AND** 返回撤销会话数量

### Requirement: 设备会话列表与单设备撤销
系统 SHALL 提供会话列表查询与单设备撤销能力，以支撑账户安全中心展示。

#### Scenario: 查看会话列表
- **WHEN** 已登录用户请求 `GET /api/auth/sessions/`
- **THEN** 返回当前用户所有活跃或近期会话的列表
- **AND** 每项包含 `id`、`device_name`、`device_type`、`created_at`、`last_seen_at`、`expires_at`、`is_current`

#### Scenario: 撤销单个设备会话
- **WHEN** 已登录用户请求 `DELETE /api/auth/sessions/{session_id}/`
- **THEN** 仅能撤销属于自己的目标会话
- **AND** 该会话关联 refresh token 被拉黑
- **AND** 业务会话被标记为撤销

### Requirement: 密码修改与其他设备失效
系统 SHALL 支持校验旧密码、执行 Django 密码规则校验，并可撤销其他设备。

#### Scenario: 修改密码成功
- **WHEN** 已登录用户请求 `POST /api/auth/change-password/`，并提供正确旧密码与合规新密码
- **THEN** 系统更新用户密码
- **AND** 记录最小审计日志

#### Scenario: 修改密码并退出其他设备
- **WHEN** 请求体中 `logout_other_sessions=true`
- **THEN** 当前会话之外的其他活跃会话全部失效
- **AND** 当前会话可按首期设计保留，避免当前页面立即掉线

#### Scenario: 旧密码错误
- **WHEN** 用户提供错误的 `old_password`
- **THEN** 接口返回业务校验错误

### Requirement: JWT 黑名单与轮换配置
系统 SHALL 启用 SimpleJWT 黑名单与 refresh token 轮换，以支持退出与会话撤销能力。

#### Scenario: 启用黑名单应用
- **WHEN** 服务启动并执行迁移
- **THEN** `rest_framework_simplejwt.token_blacklist` 已纳入 `INSTALLED_APPS`
- **AND** 官方 blacklist 迁移表已可用

#### Scenario: 刷新轮换
- **WHEN** refresh token 被正常使用
- **THEN** 旧 refresh token 被加入 blacklist
- **AND** 新 refresh token 成为唯一有效延续凭据

### Requirement: 前后端契约统一
系统 SHALL 将首期接口契约收敛到统一规范，避免用户域与案件域继续分叉。

#### Scenario: 注册字段统一
- **WHEN** 前端调用 `POST /api/auth/register/`
- **THEN** 请求体使用 `password_confirm`
- **AND** 后端不再以 `password2` 作为长期规范字段

#### Scenario: 案件页字段统一
- **WHEN** 前端调用案件列表、创建和筛选接口
- **THEN** 统一使用 `case_type`
- **AND** 不再以 `dispute_type` 作为长期接口字段

## MODIFIED Requirements

### Requirement: 当前用户接口
原有 `GET /api/auth/me/` 仅返回 `id`、`username`、`email`。
现修改为返回聚合用户资料与偏好，作为 `/profile` 页的首屏账户中心接口。

### Requirement: 登录与刷新接口
原有 `/api/auth/login/` 和 `/api/auth/refresh/` 直接使用默认 SimpleJWT 视图。
现修改为项目自定义视图，新增会话写入、轮换同步与统一响应结构。

### Requirement: 注册接口契约
原有注册序列化器要求 `password2`。
现修改为长期规范字段 `password_confirm`，并与前端注册 DTO 对齐。

## REMOVED Requirements

### Requirement: 本地浏览器偏好作为唯一数据源
**Reason**: 当前 `/profile` 页中的偏好只保存在 `localStorage`，无法跨设备同步，也不能被服务端账户中心统一管理。  
**Migration**: 首期将偏好迁移到 `UserPreference`，前端页面改为优先读写偏好接口；旧本地存储仅作为短期过渡数据源，不再作为规范能力。

### Requirement: 认证失败后立即清空登录态且不尝试刷新
**Reason**: 现有前端 `401` 后直接清 token 跳转登录页，无法利用 refresh token 构成正常登录闭环。  
**Migration**: 将前端 `api-client` 改为在非登录/刷新接口出现 `401` 时先执行一次 refresh，refresh 失败后再真正退出。
