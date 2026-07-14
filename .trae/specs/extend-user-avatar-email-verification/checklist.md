# Checklist

## 模型与迁移
- [x] `UserProfile` 已包含头像原图、展示图与更新时间字段
- [x] `EmailVerificationChallenge` 模型已存在，并包含场景、目标邮箱、验证码哈希、过期时间、使用状态与尝试次数
- [x] 相关迁移已成功执行且 `makemigrations --check` 无新增变更

## 头像能力
- [x] `POST /api/auth/me/avatar/` 可上传合法图片并返回头像 URL
- [x] 头像原图实际存储在 `media/avatar/<user.id>/original/...`
- [x] 头像展示图实际存储在 `media/avatar/<user.id>/display/...`
- [x] 上传时会校验格式、大小并生成统一展示图
- [x] 替换或删除头像时旧文件会被清理

## 邮箱验证能力
- [x] `POST /api/auth/me/email/send-code/` 可为当前邮箱发送验证码
- [x] `POST /api/auth/me/email/verify/` 可验证当前邮箱并更新 `email_verified`
- [x] `POST /api/auth/me/email/change/request/` 可为新邮箱发送验证码
- [x] `POST /api/auth/me/email/change/confirm/` 只有验证通过后才更新 `auth.User.email`
- [x] 验证码不会以明文保存在数据库
- [x] 验证码过期、重复使用、尝试次数超限、重发过快时会返回明确错误

## 邮件发送通道
- [x] 系统优先尝试 Agent Mail CLI 发送验证邮件
- [x] Agent Mail CLI 不可用时会自动回退 SMTP
- [x] SMTP 配置与 CLI 配置均来自环境变量
- [x] Agent Mail CLI 在目标 Windows 环境完成安装与授权，或已明确验证失败并切换到 SMTP 兜底

## 前端账户中心
- [x] `GET /api/auth/me/` 返回头像展示 URL 与真实邮箱验证状态
- [x] `ProfilePage.tsx` 支持头像上传、删除与展示
- [x] `ProfilePage.tsx` 支持当前邮箱验证码发送与校验
- [x] `ProfilePage.tsx` 支持新邮箱申请与验证码确认

## 测试与验证
- [x] 后端新增头像、邮箱验证、邮件 provider 相关测试
- [x] `python backend/manage.py test api` 通过
- [x] `python backend/manage.py check` 通过
- [x] `npm run build` 通过
- [x] 关键账户中心流程联调通过
