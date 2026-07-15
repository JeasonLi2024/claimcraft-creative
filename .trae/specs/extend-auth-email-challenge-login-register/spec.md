# 认证邮箱挑战扩展与登录注册统一升级 Spec

## Why
当前项目已经具备个人信息页的邮箱验证能力，但注册页和登录页仍停留在旧认证形态，无法复用现有邮箱验证码能力，也无法支持邮箱验证码登录。需要把邮箱挑战能力从“账户资料场景”扩展为统一认证能力，并同步升级登录与注册交互。

## What Changes
- 扩展 `EmailVerificationChallenge`，支持匿名场景与更多 `scene`
- 新增注册邮箱验证码发送与校验接口
- 新增邮箱验证码登录接口，并扩展现有密码登录为“账号或邮箱 + 密码”
- 调整注册接口，使邮箱验证码通过成为注册前置条件
- 重构登录页为双 Tab：`账号/邮箱 + 密码` 与 `邮箱 + 验证码`
- 改造注册页，增加邮箱验证码自动校验和确认密码自动一致性反馈

## Impact
- Affected specs: 用户认证、邮箱验证码、登录注册前端交互
- Affected code: `backend/api/models.py`, `backend/api/views.py`, `backend/api/serializers.py`, `backend/api/urls.py`, `backend/api/tests/*`, `frontend/src/components/auth/*`, `frontend/src/lib/api.ts`, `frontend/src/stores/auth-store.ts`, `frontend/src/types/auth.ts`

## ADDED Requirements
### Requirement: Unified Email Challenge Scenes
系统 SHALL 复用现有 `EmailVerificationChallenge` 作为统一邮箱挑战模型，并扩展支持注册与登录场景。

#### Scenario: Register challenge scene
- **WHEN** 未登录用户为注册流程请求邮箱验证码
- **THEN** 系统使用 `scene=register_email` 创建挑战记录

#### Scenario: Login challenge scene
- **WHEN** 未登录用户为邮箱验证码登录请求验证码
- **THEN** 系统使用 `scene=login_email` 创建挑战记录

### Requirement: Anonymous Email Challenge Support
系统 SHALL 支持未登录用户发起邮箱挑战，不要求挑战记录必须绑定已登录用户。

#### Scenario: Anonymous register challenge
- **WHEN** 用户尚未登录并请求注册邮箱验证码
- **THEN** 系统允许创建不绑定 `user` 的挑战记录，并基于 `scene + target_email` 进行校验

#### Scenario: Anonymous login challenge
- **WHEN** 用户尚未登录并请求邮箱验证码登录
- **THEN** 系统允许创建不绑定 `user` 的挑战记录，并基于 `scene + target_email` 进行校验

### Requirement: Register Email Verification Flow
系统 SHALL 为注册流程提供独立的发码与校验接口，并要求邮箱验证码验证成功后才能完成注册。

#### Scenario: Send register email code
- **WHEN** 用户调用 `POST /api/auth/register/send-code/` 并提交合法且未被占用的邮箱
- **THEN** 系统发送注册验证码并返回发送结果

#### Scenario: Verify register email code
- **WHEN** 用户调用 `POST /api/auth/register/verify-code/` 并提交正确验证码
- **THEN** 系统标记该挑战已验证成功

#### Scenario: Register requires verified challenge
- **WHEN** 用户调用 `POST /api/auth/register/`
- **THEN** 系统必须确认该邮箱存在最近一条已验证成功且未被消费的 `register_email` 挑战，否则拒绝注册

### Requirement: Login With Account Or Email And Password
系统 SHALL 将当前密码登录扩展为“账号或邮箱 + 密码”。

#### Scenario: Login by username
- **WHEN** 用户在密码登录入口提交用户名和密码
- **THEN** 系统按用户名认证并返回现有登录响应结构

#### Scenario: Login by email
- **WHEN** 用户在密码登录入口提交邮箱和密码
- **THEN** 系统按邮箱查找用户并认证成功后返回现有登录响应结构

### Requirement: Login With Email Code
系统 SHALL 支持邮箱 + 验证码登录。

#### Scenario: Send login email code
- **WHEN** 用户调用 `POST /api/auth/login/send-code/` 并提交存在的邮箱
- **THEN** 系统发送 `login_email` 场景验证码

#### Scenario: Login by email code
- **WHEN** 用户调用 `POST /api/auth/login/email-code/` 并提交正确验证码
- **THEN** 系统完成登录并返回与密码登录一致的 token、session 与用户摘要

### Requirement: Login Page Dual Tabs
系统 SHALL 在登录页提供两种登录模式的 Tab 切换。

#### Scenario: Password login tab
- **WHEN** 用户打开登录页的密码登录 Tab
- **THEN** 页面展示“账号或邮箱 + 密码”表单

#### Scenario: Email code login tab
- **WHEN** 用户切换到邮箱验证码登录 Tab
- **THEN** 页面展示“邮箱 + 获取验证码 + 条件显示验证码输入栏”的表单

### Requirement: Register Form Email Code Interaction
系统 SHALL 在注册页提供邮箱验证码获取与自动校验交互。

#### Scenario: Verification field hidden by default
- **WHEN** 用户首次打开注册页
- **THEN** 验证码输入栏默认不显示

#### Scenario: Show code input after sending
- **WHEN** 用户点击“获取验证码”并发码成功
- **THEN** 页面展示验证码输入栏

#### Scenario: Auto verify code
- **WHEN** 用户输入满验证码位数
- **THEN** 前端自动触发校验，无需额外点击验证按钮

#### Scenario: Lock verified code field
- **WHEN** 邮箱验证码校验成功
- **THEN** 验证码输入栏右侧显示绿色对勾，输入栏禁用、变灰并隐藏光标

#### Scenario: Reset verified state on email change
- **WHEN** 用户修改已发码或已验证过的邮箱输入内容
- **THEN** 页面清空验证码内容并取消已验证状态

### Requirement: Register Form Password Confirmation Feedback
系统 SHALL 在注册页提供确认密码自动一致性提示。

#### Scenario: Show mismatch hint
- **WHEN** 用户输入的确认密码与原密码不一致
- **THEN** 在确认密码输入栏下方显示红色提示文本

#### Scenario: Show matched check icon
- **WHEN** 用户输入的确认密码与原密码一致
- **THEN** 在确认密码输入栏右侧显示绿色对勾

#### Scenario: Keep confirm field editable
- **WHEN** 确认密码校验一致
- **THEN** 输入栏保持可编辑，不进入禁用状态

## MODIFIED Requirements
### Requirement: Email Challenge Lifecycle
系统 SHALL 保持邮箱验证码哈希存储、过期控制、尝试次数限制、发送频率限制与邮件发送回退逻辑，并在统一邮箱挑战体系下适用于匿名与登录后场景。

### Requirement: Register API Contract
系统 SHALL 在保留 `username`、`email`、`password`、`password_confirm` 契约的前提下，将“邮箱验证码已验证”作为注册成功的必要条件。

### Requirement: Login API Contract
系统 SHALL 在保留现有登录成功响应结构的前提下，将密码登录请求字段从单一用户名扩展为 `account`，并允许账号或邮箱作为输入。

## REMOVED Requirements
### Requirement: Register Without Email Verification
**Reason**: 注册页已升级为邮箱验证码前置验证流程，继续允许未验证邮箱直接注册会削弱邮箱可信度与后续邮箱登录能力。  
**Migration**: 前端注册页在提交前必须完成邮箱验证码自动校验，后端注册接口同步强制检查对应挑战状态。
