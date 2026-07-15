# Checklist

## 模型与迁移
- [x] `EmailVerificationChallenge` 已支持 `register_email` 与 `login_email` 场景
- [x] 挑战模型已支持匿名场景，不要求所有挑战都绑定已登录用户
- [x] 挑战模型已能区分“验证码校验成功”和“最终消费完成”
- [x] 相关迁移已成功执行且 `makemigrations --check` 无新增变更

## 注册邮箱验证码
- [x] `POST /api/auth/register/send-code/` 可对未注册邮箱发送验证码
- [x] `POST /api/auth/register/verify-code/` 可校验注册验证码
- [x] 未通过邮箱验证码校验的邮箱不能完成注册
- [x] 注册成功后对应挑战会被正确消费

## 登录能力扩展
- [x] `POST /api/auth/login/` 支持“账号或邮箱 + 密码”
- [x] `POST /api/auth/login/send-code/` 可为已存在邮箱发送登录验证码
- [x] `POST /api/auth/login/email-code/` 可通过邮箱验证码完成登录
- [x] 邮箱验证码登录成功响应与密码登录保持一致

## 前端登录页
- [x] 登录页提供“账号/邮箱 + 密码”和“邮箱 + 验证码”两个 Tab
- [x] 密码登录 Tab 已使用新的 `account` 字段
- [x] 邮箱验证码登录 Tab 在发码成功前不显示验证码输入栏
- [x] 验证码输入满位数后会自动校验

## 前端注册页
- [x] 注册页邮箱输入区右侧已增加“获取验证码”按钮
- [x] 点击“获取验证码”前不显示验证码输入栏
- [x] 邮箱验证码校验成功后输入栏右侧显示绿色对勾且输入栏进入禁用灰态
- [x] 修改邮箱后已验证状态会被清空
- [x] 确认密码不一致时会显示红色提示文字
- [x] 确认密码一致时会显示绿色对勾且输入栏保持可编辑

## 测试与验证
- [x] 后端新增注册验证码、邮箱验证码登录、账号/邮箱密码登录相关测试
- [x] `python backend/manage.py test api` 通过
- [x] `python backend/manage.py check` 通过
- [x] `npm run build` 通过
