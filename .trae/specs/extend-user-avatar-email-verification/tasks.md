# Tasks

- [x] Task 1: 扩展用户资料模型与头像存储字段
  - [x] SubTask 1.1: 在 `backend/api/models.py` 为 `UserProfile` 新增 `avatar_original`、`avatar_display`、`avatar_updated_at`
  - [x] SubTask 1.2: 设计头像 `upload_to` 路径，落到 `media/avatar/<user.id>/original/` 与 `media/avatar/<user.id>/display/`
  - [x] SubTask 1.3: 生成并应用对应迁移

- [x] Task 2: 新增邮箱验证码挑战模型与迁移
  - [x] SubTask 2.1: 新增 `EmailVerificationChallenge` 模型，包含 `user`、`scene`、`target_email`、`code_hash`、`expires_at`、`used_at`、`attempt_count`
  - [x] SubTask 2.2: 为验证码场景定义枚举，至少覆盖 `verify_current_email` 与 `change_email`
  - [x] SubTask 2.3: 生成并应用对应迁移

- [x] Task 3: 实现头像处理与文件存储服务
  - [x] SubTask 3.1: 新增头像图片校验与处理逻辑，限制格式和大小
  - [x] SubTask 3.2: 实现原图保存与展示图生成
  - [x] SubTask 3.3: 统一展示图尺寸与格式
  - [x] SubTask 3.4: 实现头像替换时的旧文件清理逻辑
  - [x] SubTask 3.5: 实现头像删除逻辑

- [x] Task 4: 实现邮件发送适配层
  - [x] SubTask 4.1: 新增统一邮件发送接口，隐藏具体 provider 细节
  - [x] SubTask 4.2: 实现 Agent Mail CLI provider，优先调用 `agently-cli`
  - [x] SubTask 4.3: 实现 SMTP provider 作为 QQ 邮箱兜底
  - [x] SubTask 4.4: 通过环境变量配置 provider 优先级、CLI 命令和 SMTP 参数
  - [x] SubTask 4.5: 统一邮件模板与邮件主题生成逻辑

- [x] Task 5: 完成 Agent Mail CLI 本机安装与授权配置
  - [x] SubTask 5.1: 按官方文档在 Windows 环境安装 `@tencent-qqmail/agently-cli`
  - [x] SubTask 5.2: 安装对应 skill
  - [x] SubTask 5.3: 执行 `agently-cli auth login` 并完成浏览器 OAuth 授权
  - [x] SubTask 5.4: 执行 `agently-cli +me` 验证授权邮箱可用
  - [x] SubTask 5.5: 配置 QQ SMTP 兜底并验证在 Agent Mail CLI 失败时可自动回退

- [x] Task 6: 实现邮箱验证码与邮箱变更接口
  - [x] SubTask 6.1: 实现 `POST /api/auth/me/email/send-code/`
  - [x] SubTask 6.2: 实现 `POST /api/auth/me/email/verify/`
  - [x] SubTask 6.3: 实现 `POST /api/auth/me/email/change/request/`
  - [x] SubTask 6.4: 实现 `POST /api/auth/me/email/change/confirm/`
  - [x] SubTask 6.5: 为验证码过期、重复使用、重发频率与尝试次数限制增加后端校验

- [x] Task 7: 实现头像接口与账户资料聚合扩展
  - [x] SubTask 7.1: 实现 `POST /api/auth/me/avatar/`
  - [x] SubTask 7.2: 实现 `DELETE /api/auth/me/avatar/`
  - [x] SubTask 7.3: 扩展 `GET /api/auth/me/` 返回头像展示 URL
  - [x] SubTask 7.4: 为相关接口补充序列化器与路由注册

- [x] Task 8: 改造前端 ProfilePage 支持头像与邮箱验证
  - [x] SubTask 8.1: 在前端类型中新增头像 URL 与邮箱验证相关字段
  - [x] SubTask 8.2: 在 `frontend/src/lib/api.ts` 接入头像与邮箱验证接口
  - [x] SubTask 8.3: 在 `ProfilePage.tsx` 增加头像上传、删除和展示入口
  - [x] SubTask 8.4: 在 `ProfilePage.tsx` 增加当前邮箱验证码发送与校验入口
  - [x] SubTask 8.5: 在 `ProfilePage.tsx` 增加新邮箱申请与验证码确认入口

- [x] Task 9: 增加测试与回归验证
  - [x] SubTask 9.1: 新增头像上传、替换、删除后端测试
  - [x] SubTask 9.2: 新增当前邮箱验证码发送与验证测试
  - [x] SubTask 9.3: 新增修改邮箱申请与确认测试
  - [x] SubTask 9.4: 新增邮件 provider 优先级与回退测试
  - [x] SubTask 9.5: 新增权限、频率限制与错误路径测试
  - [x] SubTask 9.6: 运行 `python backend/manage.py test api`
  - [x] SubTask 9.7: 运行 `python backend/manage.py check` 与 `makemigrations --check`
  - [x] SubTask 9.8: 运行 `npm run build` 并验证 `ProfilePage` 联调

# Task Dependencies
- Task 2 依赖 Task 1 之前无强依赖，可并行
- Task 3 依赖 Task 1
- Task 4 可独立于 Task 1-3 开始，但会被 Task 5、Task 6 复用
- Task 5 依赖 Task 4 的 provider 设计方向
- Task 6 依赖 Task 2、Task 4、Task 5
- Task 7 依赖 Task 1、Task 3
- Task 8 依赖 Task 6、Task 7
- Task 9 依赖 Task 5、Task 6、Task 7、Task 8
