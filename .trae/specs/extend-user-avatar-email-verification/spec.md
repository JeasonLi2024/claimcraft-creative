# ClaimCraft 头像上传与邮箱验证扩展 Spec

## Why
现有账户中心已经完成基础资料、偏好、密码与设备会话能力，但头像仍停留在首字母占位，邮箱验证状态也只是字段展示，缺少真实上传、发送验证码、验证当前邮箱与修改邮箱后的确认流程。同时，邮件发送通道需要优先接入 Agent Mail CLI，并在不可用时自动回退到 SMTP，避免验证链路被单一邮件提供方阻塞。

## What Changes
- 扩展 `UserProfile`，新增头像原图、展示图与更新时间字段
- 新增头像上传与删除接口，文件存储在 `media/avatar/<user.id>/...`
- 新增邮箱验证码挑战模型，支持“验证当前邮箱”和“修改邮箱后验证”两类场景
- 新增邮箱验证码发送、当前邮箱验证、新邮箱变更申请与确认接口
- 新增邮件发送适配层，优先调用 Agent Mail CLI，失败时自动回退 QQ SMTP
- 统一邮件配置从环境变量读取，禁止在业务代码中硬编码邮箱凭据
- 扩展 `/api/auth/me/` 和前端 `ProfilePage`，展示头像与邮箱验证状态，提供头像和邮箱操作入口

## Impact
- Affected specs: `restructure-user-auth-backend` 的账户中心能力基础上继续扩展
- Affected code:
  - `backend/api/models.py`
  - `backend/api/serializers.py`
  - `backend/api/views.py`
  - `backend/api/urls.py`
  - `backend/api/migrations/*`
  - `backend/api/tests/*`
  - `backend/claimcraft/settings.py`
  - `backend/.env*` 或相应环境变量说明
  - `frontend/src/lib/api.ts`
  - `frontend/src/types/auth.ts`
  - `frontend/src/stores/auth-store.ts`
  - `frontend/src/pages/ProfilePage.tsx`

## ADDED Requirements

### Requirement: 头像上传与展示
系统 SHALL 支持用户上传、替换和删除头像，并对外提供稳定的展示图 URL。

#### Scenario: 上传头像成功
- **WHEN** 已登录用户请求 `POST /api/auth/me/avatar/` 并上传合法图片
- **THEN** 系统保存原图到 `media/avatar/<user.id>/original/...`
- **AND** 生成展示图到 `media/avatar/<user.id>/display/...`
- **AND** 返回最新头像 URL

#### Scenario: 替换旧头像
- **WHEN** 用户再次上传头像
- **THEN** 系统更新 `UserProfile` 中的头像字段
- **AND** 删除或清理旧头像文件，避免孤儿文件堆积

#### Scenario: 删除头像
- **WHEN** 用户请求 `DELETE /api/auth/me/avatar/`
- **THEN** 系统删除头像引用
- **AND** 清理相关头像文件
- **AND** 前端回退到默认占位头像

### Requirement: 头像处理安全边界
系统 SHALL 对上传图片执行最小安全与展示处理，避免前端直接依赖原图。

#### Scenario: 非法图片拒绝
- **WHEN** 用户上传非 `jpg/jpeg/png/webp` 文件、超大文件或伪造图片
- **THEN** 接口返回上传失败

#### Scenario: 生成统一展示图
- **WHEN** 用户上传合法头像
- **THEN** 系统处理 EXIF 方向
- **AND** 生成统一尺寸的展示图
- **AND** 前端默认使用展示图而非原图

### Requirement: 当前邮箱验证码验证
系统 SHALL 支持对当前主邮箱发送 6 位验证码，并完成邮箱归属验证。

#### Scenario: 发送当前邮箱验证码
- **WHEN** 已登录用户请求 `POST /api/auth/me/email/send-code/`
- **THEN** 系统为当前邮箱创建有效验证码挑战
- **AND** 通过邮件发送适配层向该邮箱发送验证码

#### Scenario: 验证当前邮箱成功
- **WHEN** 用户请求 `POST /api/auth/me/email/verify/` 并提交正确验证码
- **THEN** `UserProfile.email_verified` 被设置为 `True`
- **AND** 该验证码挑战被标记为已使用

### Requirement: 新邮箱变更需验证后生效
系统 SHALL 在新邮箱验证成功之前保持旧邮箱为系统正式邮箱。

#### Scenario: 申请修改邮箱
- **WHEN** 用户请求 `POST /api/auth/me/email/change/request/` 并提交新邮箱
- **THEN** 系统校验邮箱格式与唯一性
- **AND** 为该新邮箱创建验证码挑战
- **AND** 在验证码通过前不修改 `auth.User.email`

#### Scenario: 确认修改邮箱成功
- **WHEN** 用户请求 `POST /api/auth/me/email/change/confirm/` 并提交新邮箱与正确验证码
- **THEN** 系统将 `auth.User.email` 更新为新邮箱
- **AND** `UserProfile.email_verified` 被设置为 `True`
- **AND** 对应验证码挑战被标记为已使用

#### Scenario: 新邮箱被占用
- **WHEN** 用户申请或确认一个已被其他账户占用的新邮箱
- **THEN** 接口返回冲突错误
- **AND** 不修改当前正式邮箱

### Requirement: 邮箱验证码挑战模型
系统 SHALL 将验证码状态独立存储，而不是将临时验证状态直接堆积到 `UserProfile`。

#### Scenario: 挑战记录保存最小必要信息
- **WHEN** 系统创建邮箱验证码挑战
- **THEN** 记录用户、场景、目标邮箱、验证码哈希、过期时间、尝试次数、使用状态与创建时间

#### Scenario: 验证码不以明文存库
- **WHEN** 系统保存验证码
- **THEN** 仅保存验证码哈希值
- **AND** 不在数据库中保存明文验证码

### Requirement: 邮件发送适配层
系统 SHALL 将邮件发送能力抽象为统一适配层，以支持多提供方回退。

#### Scenario: Agent Mail CLI 优先
- **WHEN** 系统发送验证邮件
- **THEN** 优先尝试 `Agent Mail CLI`

#### Scenario: SMTP 自动兜底
- **WHEN** Agent Mail CLI 不可用、未授权或执行失败
- **THEN** 系统自动尝试 SMTP 发送

#### Scenario: 所有邮件提供方失败
- **WHEN** Agent Mail CLI 与 SMTP 都发送失败
- **THEN** 接口返回明确发送失败结果
- **AND** 记录邮件通道失败日志

### Requirement: 邮件配置解耦
系统 SHALL 通过环境变量配置邮件发送通道，避免将敏感凭据硬编码进业务代码。

#### Scenario: SMTP 配置来自环境变量
- **WHEN** 系统使用 SMTP 发送邮件
- **THEN** 主机、端口、账号、授权码、发件人地址均来自环境变量

#### Scenario: CLI 命令可配置
- **WHEN** 系统调用 Agent Mail CLI
- **THEN** CLI 命令路径和提供方优先级来自环境变量配置

## MODIFIED Requirements

### Requirement: 当前用户聚合信息
原有 `GET /api/auth/me/` 返回资料、偏好与邮箱验证状态，但未返回可用头像信息。
现修改为返回头像展示 URL，并让邮箱验证状态具备真实业务含义。

### Requirement: ProfilePage 账户中心交互
原有个人页仅支持资料、偏好、密码与会话管理。
现修改为同时支持头像上传/删除、当前邮箱验证码验证以及新邮箱修改验证。

## REMOVED Requirements

### Requirement: 邮箱验证状态仅作静态展示
**Reason**: 当前 `email_verified` 只是展示字段，没有真实验证链路，无法作为可信账户状态。  
**Migration**: 通过邮箱验证码挑战模型与邮件发送适配层实现真实验证流程，并由接口驱动状态变化。

### Requirement: 头像仅使用首字母占位
**Reason**: 账户中心已经具备较完整资料能力，继续仅靠首字母占位会让个人资料体验长期停留在半成品状态。  
**Migration**: 新增头像字段、上传与删除接口；未上传头像时继续回退到占位方案。
