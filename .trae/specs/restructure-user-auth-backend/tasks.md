# Tasks

- [x] Task 1: 调整认证基础配置与 JWT 撤销能力
  - [x] SubTask 1.1: 在 `backend/claimcraft/settings.py` 启用 `rest_framework_simplejwt.token_blacklist`
  - [x] SubTask 1.2: 调整 `SIMPLE_JWT` 配置，开启 refresh token 轮换与轮换后 blacklist
  - [x] SubTask 1.3: 确认 access / refresh 生命周期与当前“前端持 token”策略一致
  - [x] SubTask 1.4: 生成并应用 blacklist 相关迁移

- [x] Task 2: 新增用户域扩展模型与迁移
  - [x] SubTask 2.1: 在 `backend/api/models.py` 新增 `UserProfile`
  - [x] SubTask 2.2: 在 `backend/api/models.py` 新增 `UserPreference`
  - [x] SubTask 2.3: 在 `backend/api/models.py` 新增 `UserSession`
  - [x] SubTask 2.4: 在 `backend/api/models.py` 新增最小化 `AccountAuditLog`
  - [x] SubTask 2.5: 编写迁移为现有用户补齐 `UserProfile` 和 `UserPreference`
  - [x] SubTask 2.6: 明确 `UserSession` 仅从新登录开始创建，不伪造历史会话

- [x] Task 3: 重构认证与账户中心序列化器
  - [x] SubTask 3.1: 重写注册序列化器，长期规范字段改为 `password_confirm`
  - [x] SubTask 3.2: 拆分 `UserSummarySerializer`、`UserDetailSerializer`
  - [x] SubTask 3.3: 新增 `UserProfileUpdateSerializer`
  - [x] SubTask 3.4: 新增 `UserPreferenceSerializer`
  - [x] SubTask 3.5: 新增 `ChangePasswordSerializer`
  - [x] SubTask 3.6: 新增 `UserSessionSerializer`

- [x] Task 4: 重构认证视图与认证闭环接口
  - [x] SubTask 4.1: 用自定义登录视图替换默认 `TokenObtainPairView`
  - [x] SubTask 4.2: 登录成功时创建 `UserSession` 并返回 `access/refresh/user/session_id`
  - [x] SubTask 4.3: 用自定义 refresh 视图替换默认 `TokenRefreshView`
  - [x] SubTask 4.4: refresh 成功时同步更新 `UserSession.refresh_jti/last_seen_at/expires_at`
  - [x] SubTask 4.5: 实现 `POST /api/auth/logout/`
  - [x] SubTask 4.6: 实现 `POST /api/auth/logout-all/`

- [x] Task 5: 实现账户中心资料、偏好与密码接口
  - [x] SubTask 5.1: 扩展 `GET /api/auth/me/` 为聚合资料接口
  - [x] SubTask 5.2: 实现 `PATCH /api/auth/me/`
  - [x] SubTask 5.3: 实现 `GET /api/auth/me/preferences/`
  - [x] SubTask 5.4: 实现 `PATCH /api/auth/me/preferences/`
  - [x] SubTask 5.5: 实现 `POST /api/auth/change-password/`
  - [x] SubTask 5.6: 修改密码成功时支持按参数撤销其他会话

- [x] Task 6: 实现会话管理与最小审计
  - [x] SubTask 6.1: 实现 `GET /api/auth/sessions/`
  - [x] SubTask 6.2: 实现 `DELETE /api/auth/sessions/{session_id}/`
  - [x] SubTask 6.3: 补充当前设备识别逻辑与 `is_current` 标记
  - [x] SubTask 6.4: 在登录、登出、全部登出、修改密码、撤销会话时写入最小审计日志

- [x] Task 7: 统一路由与接口契约
  - [x] SubTask 7.1: 在 `backend/api/urls.py` 注册新的账户中心接口
  - [x] SubTask 7.2: 调整前端 `frontend/src/lib/api.ts` 对应新的认证与账户中心接口
  - [x] SubTask 7.3: 更新 `frontend/src/types/auth.ts` 与 `/profile` 所需用户类型
  - [x] SubTask 7.4: 更新 `frontend/src/types/case.ts` 与 `frontend/src/pages/CaseListPage.tsx`，统一使用 `case_type`
  - [x] SubTask 7.5: 清理前端注册 DTO 与后端 `password_confirm` 规范差异

- [x] Task 8: 改造前端认证状态与个人页接入
  - [x] SubTask 8.1: 重构 `frontend/src/stores/auth-store.ts`，保存 `refresh_token`、`user`、`currentSessionId`
  - [x] SubTask 8.2: 登录后直接写入真实用户摘要，不再写占位用户
  - [x] SubTask 8.3: 在 `frontend/src/lib/api-client.ts` 增加 refresh 自动续期逻辑
  - [x] SubTask 8.4: 将 `ProfilePage.tsx` 的偏好存储从 `localStorage` 迁移到偏好接口
  - [x] SubTask 8.5: 在 `ProfilePage.tsx` 接入密码修改、退出全部设备与会话展示入口

- [x] Task 9: 验证与回归测试
  - [x] SubTask 9.1: 验证迁移执行成功，现有用户可正常登录
  - [x] SubTask 9.2: 验证注册、登录、刷新、退出、全部退出完整闭环
  - [x] SubTask 9.3: 验证 `/profile` 资料展示与偏好写入
  - [x] SubTask 9.4: 验证密码修改与其他设备失效逻辑
  - [x] SubTask 9.5: 验证会话列表、当前设备标记与单设备撤销
  - [x] SubTask 9.6: 验证 `/cases` 相关接口与页面已统一 `case_type`
  - [x] SubTask 9.7: 补充后端单测、权限测试与前端构建验证

- [x] Task 10: 为用户认证与账户中心新增后端单测和权限测试
  - [x] SubTask 10.1: 新增注册、登录、刷新、退出、全部退出接口测试
  - [x] SubTask 10.2: 新增 `/auth/me`、`/auth/me/preferences/`、`/auth/change-password/` 测试
  - [x] SubTask 10.3: 新增 `/auth/sessions/` 列表与单设备撤销测试
  - [x] SubTask 10.4: 新增越权与未认证访问的权限测试
  - [x] SubTask 10.5: 运行 `python backend/manage.py test api` 并确认测试通过

# Task Dependencies
- Task 2 依赖 Task 1（模型与会话撤销依赖 JWT blacklisting 配置）
- Task 3 依赖 Task 2（序列化器依赖新增模型）
- Task 4 依赖 Task 1、Task 2、Task 3
- Task 5 依赖 Task 2、Task 3
- Task 6 依赖 Task 2、Task 4
- Task 7 依赖 Task 4、Task 5、Task 6
- Task 8 依赖 Task 7
- Task 9 依赖 Task 4、Task 5、Task 6、Task 8
- Task 10 依赖 Task 4、Task 5、Task 6，并用于完成 Task 9.7
