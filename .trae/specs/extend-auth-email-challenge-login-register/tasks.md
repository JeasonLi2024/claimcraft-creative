# Tasks

- [x] Task 1: 扩展统一邮箱挑战模型与迁移
  - [x] SubTask 1.1: 为 `EmailVerificationChallenge` 增加 `register_email` 与 `login_email` 场景
  - [x] SubTask 1.2: 调整挑战模型以支持匿名场景（未登录用户）
  - [x] SubTask 1.3: 增加 `verified_at` 或等价状态字段，区分“校验成功”和“最终消费完成”
  - [x] SubTask 1.4: 生成并应用对应迁移

- [x] Task 2: 实现注册邮箱验证码接口
  - [x] SubTask 2.1: 实现 `POST /api/auth/register/send-code/`
  - [x] SubTask 2.2: 实现 `POST /api/auth/register/verify-code/`
  - [x] SubTask 2.3: 复用邮件发送、频率限制、过期与尝试次数限制逻辑
  - [x] SubTask 2.4: 确保注册邮箱已占用时拒绝发码

- [x] Task 3: 改造注册接口并接入验证码前置校验
  - [x] SubTask 3.1: 在 `POST /api/auth/register/` 中校验对应 `register_email` 挑战状态
  - [x] SubTask 3.2: 确保注册成功后挑战被正确消费
  - [x] SubTask 3.3: 保持现有 `password_confirm` 与资料初始化逻辑不回退

- [x] Task 4: 扩展登录认证方式
  - [x] SubTask 4.1: 将密码登录请求字段调整为 `account`
  - [x] SubTask 4.2: 实现“账号或邮箱 + 密码”双入口认证
  - [x] SubTask 4.3: 实现 `POST /api/auth/login/send-code/`
  - [x] SubTask 4.4: 实现 `POST /api/auth/login/email-code/`
  - [x] SubTask 4.5: 保持邮箱验证码登录成功响应与现有登录响应结构一致

- [x] Task 5: 改造前端登录页为双 Tab 模式
  - [x] SubTask 5.1: 在登录页增加 `账号/邮箱 + 密码` 与 `邮箱 + 验证码` 两个 Tab
  - [x] SubTask 5.2: 接入密码登录新的 `account` 请求字段
  - [x] SubTask 5.3: 接入邮箱验证码发送与自动校验/登录流程
  - [x] SubTask 5.4: 确保两个 Tab 的表单状态互不污染

- [x] Task 6: 改造注册页邮箱验证码与确认密码自动校验交互
  - [x] SubTask 6.1: 在邮箱输入区右侧增加“获取验证码”按钮
  - [x] SubTask 6.2: 默认隐藏验证码输入栏，并在发码成功后显示
  - [x] SubTask 6.3: 输入满验证码位数后自动校验并在成功时锁定输入栏
  - [x] SubTask 6.4: 在确认密码输入栏实现自动一致性提示与绿色对勾反馈
  - [x] SubTask 6.5: 当邮箱变更时重置验证码输入与已验证状态

- [x] Task 7: 补充类型、状态管理与 API 封装
  - [x] SubTask 7.1: 更新前端认证相关类型定义
  - [x] SubTask 7.2: 更新 `frontend/src/lib/api.ts` 与 `auth-store` 的登录注册调用
  - [x] SubTask 7.3: 为挑战校验状态、错误提示和自动校验节流补齐前端状态管理

- [x] Task 8: 增加测试与回归验证
  - [x] SubTask 8.1: 新增后端匿名 challenge、注册发码/校验、邮箱验证码登录测试
  - [x] SubTask 8.2: 新增账号/邮箱密码登录兼容测试
  - [x] SubTask 8.3: 补充注册接口“未验证邮箱不可注册”的测试
  - [x] SubTask 8.4: 运行 `python backend/manage.py test api`
  - [x] SubTask 8.5: 运行 `python backend/manage.py check` 与 `makemigrations --check`
  - [x] SubTask 8.6: 运行 `npm run build`

# Task Dependencies
- Task 2 依赖 Task 1
- Task 3 依赖 Task 1、Task 2
- Task 4 依赖 Task 1
- Task 5 依赖 Task 4、Task 7
- Task 6 依赖 Task 2、Task 3、Task 7
- Task 7 可与 Task 4 并行推进，但最终由 Task 5、Task 6 消费
- Task 8 依赖 Task 3、Task 4、Task 5、Task 6、Task 7
