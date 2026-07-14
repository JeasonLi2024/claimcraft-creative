# ClaimCraft 服务器邮件服务部署说明

> 适用范围：ClaimCraft 后端在 Linux 服务器或容器环境中部署时，复用当前 Windows 开发环境已经实现的邮件发送能力。  
> 当前策略：`Agent Mail CLI` 优先发送，失败后自动回退到 `QQ SMTP`。

## 1. 背景说明

当前项目的邮件发送链路已经实现为：

1. Django 业务代码调用统一邮件发送服务；
2. 服务优先尝试 `Agent Mail CLI`；
3. 如果 CLI 不可用、未授权或发送失败，则自动回退到 `QQ SMTP`；
4. 邮箱验证码、邮箱修改验证等功能都复用这套链路。

因此，**服务器部署时通常不需要修改业务代码**，重点是补齐运行环境、OAuth 授权目录、环境变量和部署脚本。

相关代码位置：

- `backend/claimcraft/settings.py`
- `backend/api/services/mail_service.py`

## 2. 部署目标

服务器环境需要达到以下状态：

- 可以执行 `agently-cli`；
- Django 运行进程可以读取 `Agent Mail CLI` 的授权凭据；
- 邮件配置通过 `.env` 注入；
- `Agent Mail CLI` 失效时，`QQ SMTP` 可以自动兜底；
- 容器重建或服务重启后，CLI 授权信息不会丢失。

## 3. 服务器需要做的修改

## 3.1 安装 Node.js 与 Agent Mail CLI

服务器必须先具备 Node.js 与 npm。

示例：

```bash
npm install -g @tencent-qqmail/agently-cli
npx skills add https://agent.qq.com --skill -g -y
which agently-cli
```

安装完成后，确认 `agently-cli` 可执行文件路径，例如：

```bash
/usr/local/bin/agently-cli
```

后续 `.env` 中的 `CLAIMCRAFT_AGENT_MAIL_COMMAND` 应填写这个实际路径。

## 3.2 为 Agent Mail CLI 准备持久化授权目录

Windows 开发环境使用的是：

```text
D:/claimcraft-creative/.agently-home
```

服务器上建议单独准备一个持久化目录，例如：

```bash
mkdir -p /srv/claimcraft/.agently-home/AppData/Roaming
mkdir -p /srv/claimcraft/.agently-home/AppData/Local
chown -R <运行Django的用户>:<运行Django的组> /srv/claimcraft/.agently-home
```

建议使用：

```text
/srv/claimcraft/.agently-home
```

这个目录必须满足两个条件：

1. Django 进程有读写权限；
2. 目录会被持久化保存，不能随着容器或临时目录销毁。

## 3.3 在服务器上完成 Agent Mail CLI OAuth 授权

授权时必须使用**与 Django 运行时一致的授权目录**，否则线上进程无法读取凭据。

先导出以下环境变量：

```bash
export CLAIMCRAFT_AGENT_MAIL_HOME=/srv/claimcraft/.agently-home
export HOME=$CLAIMCRAFT_AGENT_MAIL_HOME
export USERPROFILE=$CLAIMCRAFT_AGENT_MAIL_HOME
export APPDATA=$CLAIMCRAFT_AGENT_MAIL_HOME/AppData/Roaming
export LOCALAPPDATA=$CLAIMCRAFT_AGENT_MAIL_HOME/AppData/Local
```

然后执行：

```bash
agently-cli auth login
```

命令会输出一个 OAuth 授权链接。  
在浏览器中完成授权后，继续验证：

```bash
agently-cli +me
```

如果授权成功，应能看到当前授权邮箱别名信息。

## 3.4 配置服务器 `.env`

服务器环境变量中需要补齐以下邮件配置。

示例：

```env
CLAIMCRAFT_MAIL_PROVIDER_ORDER=agent_cli,smtp
CLAIMCRAFT_MAIL_DEFAULT_FROM_NAME=ClaimCraft
CLAIMCRAFT_MAIL_DEFAULT_FROM_EMAIL=1708976770@qq.com
CLAIMCRAFT_MAIL_SEND_TIMEOUT_SECONDS=30

CLAIMCRAFT_AGENT_MAIL_ENABLED=true
CLAIMCRAFT_AGENT_MAIL_COMMAND=/usr/local/bin/agently-cli
CLAIMCRAFT_AGENT_MAIL_HOME=/srv/claimcraft/.agently-home

CLAIMCRAFT_SMTP_ENABLED=true
CLAIMCRAFT_SMTP_HOST=smtp.qq.com
CLAIMCRAFT_SMTP_PORT=465
CLAIMCRAFT_SMTP_USERNAME=1708976770@qq.com
CLAIMCRAFT_SMTP_PASSWORD=你的QQ邮箱授权码
CLAIMCRAFT_SMTP_USE_TLS=false
CLAIMCRAFT_SMTP_USE_SSL=true
```

说明：

- `CLAIMCRAFT_MAIL_PROVIDER_ORDER=agent_cli,smtp` 表示优先走 CLI，失败再走 SMTP；
- `CLAIMCRAFT_AGENT_MAIL_HOME` 必须与授权时使用的目录一致；
- `CLAIMCRAFT_SMTP_PASSWORD` 必须填写 QQ 邮箱授权码，而不是网页登录密码；
- 真实敏感信息只能放服务器 `.env`，**不要写入 `.env.example`**。

## 3.5 非 Docker 部署的额外要求

如果你使用 `systemd`、`supervisor` 或手工启动 Django，需要保证：

1. 启动用户对 `/srv/claimcraft/.agently-home` 有读写权限；
2. `.env` 中的 `CLAIMCRAFT_AGENT_MAIL_HOME` 已正确加载；
3. `CLAIMCRAFT_AGENT_MAIL_COMMAND` 指向实际安装路径。

以 `systemd` 为例，服务运行用户必须和授权目录权限一致，否则会出现：

- CLI 明明已授权；
- 但 Django 运行时仍读取不到凭据；
- 最终所有邮件都退回到 SMTP。

## 3.6 Docker 部署的额外要求

如果后端运行在 Docker 容器中，还需要额外做两件事：

### 1. 在镜像中安装 Node.js 与 `agently-cli`

你的 Dockerfile 需要包含：

```dockerfile
RUN npm install -g @tencent-qqmail/agently-cli \
    && npx skills add https://agent.qq.com --skill -g -y
```

如果基础镜像没有 npm，还需要先安装 Node.js。

### 2. 将 `.agently-home` 做成持久化卷

例如：

```yaml
volumes:
  - /srv/claimcraft/agently-home:/app/.agently-home
```

容器环境变量：

```env
CLAIMCRAFT_AGENT_MAIL_HOME=/app/.agently-home
CLAIMCRAFT_AGENT_MAIL_COMMAND=/usr/local/bin/agently-cli
```

这样做的原因是：

- OAuth 授权结果保存在 `.agently-home`；
- 如果这个目录不挂卷，容器一重建，授权就会丢失；
- 届时服务会退回 SMTP，甚至在 SMTP 也未配置时直接发信失败。

## 4. 推荐的上线顺序

为了降低风险，建议按以下顺序部署：

1. 先配置 `QQ SMTP` 兜底，确保邮箱验证码功能可用；
2. 再安装 `Agent Mail CLI`；
3. 再配置 `CLAIMCRAFT_AGENT_MAIL_HOME`；
4. 再执行服务器 OAuth 授权；
5. 最后验证 Django 实际发信是否优先走 `agent_cli`。

这样即使 CLI 授权过程暂时失败，也不会阻塞业务功能。

## 5. 部署后验证清单

服务器部署完成后，建议至少验证以下几项。

### 5.1 CLI 自检

```bash
agently-cli +me
```

预期结果：

- 能返回授权邮箱信息；
- 不出现未登录或权限错误。

### 5.2 Django 配置检查

```bash
python backend/manage.py check
```

预期结果：

- 系统检查通过；
- 无额外配置错误。

### 5.3 真实邮件发送验证

建议通过 Django shell 或测试接口验证一次真实发送。

例如验证码发送接口：

```http
POST /api/auth/me/email/send-code/
```

预期结果：

- 接口返回 `200`；
- 返回体中 `provider` 优先为 `agent_cli`；
- 如果 `agent_cli` 失败，返回体应显示 SMTP 已成功兜底或日志中可见回退行为。

### 5.4 日志观察

建议观察后端日志中是否出现以下事件：

- `mail_provider_succeeded`
- `mail_provider_failed`
- `mail_provider_unavailable`

这可以帮助定位：

- CLI 路径是否错误；
- 授权目录是否不可读；
- SMTP 是否配置异常。

## 6. 常见问题

## 6.1 为什么服务器上明明执行过授权，Django 还是走 SMTP？

常见原因有：

1. `CLAIMCRAFT_AGENT_MAIL_HOME` 与授权时使用的目录不一致；
2. Django 运行用户对授权目录没有权限；
3. 容器重建后 `.agently-home` 没有持久化；
4. `CLAIMCRAFT_AGENT_MAIL_COMMAND` 指向了错误路径。

## 6.2 为什么需要单独配置 `CLAIMCRAFT_AGENT_MAIL_HOME`？

因为项目运行时需要强制 CLI 使用指定目录保存与读取凭据。  
否则它可能默认写入用户主目录，而不同部署方式下：

- 运行用户可能不同；
- 容器内默认 HOME 可能不稳定；
- 沙箱或权限控制可能阻止默认路径写入。

显式配置后，部署行为会稳定很多。

## 6.3 服务器上是否必须启用 Agent Mail CLI？

不是必须。  
如果短期只想保证业务可用，可以只启用 `QQ SMTP`。但按当前项目实现，推荐保留：

- `Agent Mail CLI` 作为主通道；
- `QQ SMTP` 作为兜底通道。

这样既保留了当前本地开发环境的能力，也能避免单点失败。

## 7. 建议的后续改进

为了让服务器部署更标准，后续建议继续补充：

1. 在 `.env.example` 中增加邮件相关配置模板；
2. 在 Dockerfile / docker-compose 中显式安装 `agently-cli`；
3. 在部署文档中加入“首次 OAuth 授权”步骤；
4. 在运维脚本中增加发信健康检查；
5. 将 SMTP 密码和敏感变量接入更安全的密钥管理方式。

## 8. 最终结论

要让服务器邮件服务与当前 Windows 开发环境保持一致，核心不是继续改业务代码，而是完成以下四件事：

1. 安装并配置 `agently-cli`；
2. 准备并持久化 `CLAIMCRAFT_AGENT_MAIL_HOME`；
3. 在服务器上完成 OAuth 授权；
4. 在 `.env` 中同时配置 `Agent Mail CLI` 和 `QQ SMTP`。

完成后，ClaimCraft 服务端就可以在生产环境中复用当前已经实现的邮件发送策略：**CLI 优先，SMTP 兜底。**
