# Checklist

## 认证基础配置
- [x] `rest_framework_simplejwt.token_blacklist` 已加入 `INSTALLED_APPS`
- [x] `SIMPLE_JWT` 已启用 refresh token 轮换与轮换后 blacklist
- [x] blacklist 相关迁移已成功执行

## 用户域模型
- [x] `UserProfile` 模型存在，包含 `display_name`、`bio`、`locale`、`timezone`、`email_verified`
- [x] `UserPreference` 模型存在，包含三个当前页面实际使用的偏好开关及默认模式字段
- [x] `UserSession` 模型存在，包含 `refresh_jti`、设备信息、活跃时间、过期时间、撤销时间
- [x] `AccountAuditLog` 模型存在，且未记录密码与 token 原文
- [x] 历史用户已能补齐 `UserProfile` 与 `UserPreference`

## 认证闭环接口
- [x] `POST /api/auth/register/` 使用 `password_confirm`
- [x] `POST /api/auth/login/` 返回 `access`、`refresh`、`user`、`session_id`
- [x] `POST /api/auth/refresh/` 会同步更新 `UserSession`
- [x] `POST /api/auth/logout/` 会拉黑 refresh token 并撤销对应业务会话
- [x] `POST /api/auth/logout-all/` 会撤销当前用户全部活跃会话

## 账户中心接口
- [x] `GET /api/auth/me/` 返回聚合用户资料与偏好
- [x] `PATCH /api/auth/me/` 仅允许更新白名单资料字段
- [x] `GET /api/auth/me/preferences/` 可返回服务端偏好
- [x] `PATCH /api/auth/me/preferences/` 可持久化偏好修改
- [x] `POST /api/auth/change-password/` 校验旧密码与 Django 密码规则

## 会话管理与审计
- [x] `GET /api/auth/sessions/` 可列出设备会话并标记当前设备
- [x] `DELETE /api/auth/sessions/{session_id}/` 仅允许撤销本人会话
- [x] 登录、登出、全部登出、修改密码、撤销会话会写入最小审计日志

## 前端契约对齐
- [x] `frontend/src/stores/auth-store.ts` 已持有完整认证状态，不再使用占位用户
- [x] `frontend/src/lib/api-client.ts` 已具备 refresh 自动续期逻辑
- [x] `ProfilePage.tsx` 的偏好已从 `localStorage` 迁移为服务端接口
- [x] `ProfilePage.tsx` 已接入密码修改、全部退出和会话管理入口
- [x] `/cases` 相关前后端契约已统一为 `case_type`
- [x] 注册前后端契约已统一为 `password_confirm`

## 验证与回归
- [x] 现有用户登录、获取资料、访问案件列表不受影响
- [x] 注册、登录、刷新、退出、全部退出流程已形成闭环
- [x] 会话列表、单设备撤销、修改密码撤销其他设备符合设计预期
- [x] 后端新增接口具备基本单测与权限测试
- [x] 前端构建与关键页面联调通过
