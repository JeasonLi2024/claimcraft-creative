# -*- coding: utf-8 -*-
"""邮件发送适配层。"""

from __future__ import annotations

import json
import logging
import os
import shutil
import smtplib
import subprocess
import tempfile
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Iterable, Sequence

from django.conf import settings

logger = logging.getLogger(__name__)


class MailDeliveryError(RuntimeError):
    """邮件发送失败。"""


@dataclass
class MailMessagePayload:
    to: list[str]
    subject: str
    text_body: str
    html_body: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class MailSendResult:
    ok: bool
    provider: str
    detail: str = ''
    message_id: str = ''
    raw_output: str = ''


def _normalize_recipients(recipients: Sequence[str] | str) -> list[str]:
    if isinstance(recipients, str):
        recipients = [recipients]
    normalized = []
    for recipient in recipients:
        if recipient and recipient.strip():
            normalized.append(recipient.strip())
    if not normalized:
        raise MailDeliveryError('至少需要一个收件人')
    return normalized


def build_verification_mail_payload(
    *,
    to_email: str,
    code: str,
    scene: str,
    expires_minutes: int = 10,
) -> MailMessagePayload:
    if scene == 'change_email':
        action_label = '修改邮箱'
    else:
        action_label = '验证当前邮箱'

    subject = f'ClaimCraft 邮箱验证码 - {action_label}'
    text_body = (
        f'您好，\n\n'
        f'您正在进行 ClaimCraft 账户的{action_label}操作。\n'
        f'本次验证码为：{code}\n'
        f'验证码 {expires_minutes} 分钟内有效，请勿泄露给他人。\n\n'
        f'如果这不是您的操作，请忽略这封邮件。\n'
    )
    html_body = (
        '<p>您好，</p>'
        f'<p>您正在进行 ClaimCraft 账户的<strong>{action_label}</strong>操作。</p>'
        f'<p>本次验证码为：<strong style="font-size:20px;">{code}</strong></p>'
        f'<p>验证码 <strong>{expires_minutes}</strong> 分钟内有效，请勿泄露给他人。</p>'
        '<p>如果这不是您的操作，请忽略这封邮件。</p>'
    )
    return MailMessagePayload(
        to=[to_email],
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )


class BaseMailProvider:
    provider_name = 'base'

    def is_available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def send(self, payload: MailMessagePayload) -> MailSendResult:
        raise NotImplementedError


class AgentMailCLIProvider(BaseMailProvider):
    provider_name = 'agent_cli'

    def __init__(self):
        self.command = settings.CLAIMCRAFT_AGENT_MAIL_COMMAND
        self.home_dir = settings.CLAIMCRAFT_AGENT_MAIL_HOME
        self.timeout = settings.CLAIMCRAFT_MAIL_SEND_TIMEOUT_SECONDS
        self.working_dir = str(settings.BASE_DIR.parent)

    def is_available(self) -> tuple[bool, str]:
        if not settings.CLAIMCRAFT_AGENT_MAIL_ENABLED:
            return False, 'CLAIMCRAFT_AGENT_MAIL_ENABLED=false'
        executable = shutil.which(self.command)
        if executable is None and not os.path.exists(self.command):
            return False, f'未找到命令: {self.command}'
        return True, ''

    def _run_command(self, args: list[str]) -> subprocess.CompletedProcess:
        logger.info('agent_mail_cli_exec', extra={'args': args})
        command_env = os.environ.copy()
        if self.home_dir:
            appdata_dir = os.path.join(self.home_dir, 'AppData', 'Roaming')
            localappdata_dir = os.path.join(self.home_dir, 'AppData', 'Local')
            os.makedirs(appdata_dir, exist_ok=True)
            os.makedirs(localappdata_dir, exist_ok=True)
            command_env.update({
                'HOME': self.home_dir,
                'USERPROFILE': self.home_dir,
                'APPDATA': appdata_dir,
                'LOCALAPPDATA': localappdata_dir,
            })
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=self.timeout,
            check=False,
            env=command_env,
            cwd=self.working_dir,
        )

    def _parse_json_output(self, stdout: str) -> dict:
        stdout = (stdout or '').strip()
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {}

    def send(self, payload: MailMessagePayload) -> MailSendResult:
        available, reason = self.is_available()
        if not available:
            raise MailDeliveryError(reason)

        temp_dir = os.path.join(self.working_dir, '.tmp-agent-mail')
        os.makedirs(temp_dir, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.html',
            encoding='utf-8',
            dir=temp_dir,
            delete=False,
        ) as body_file:
            body_file.write(payload.html_body or payload.text_body)
            body_file_path = body_file.name
            relative_body_file_path = os.path.relpath(body_file_path, start=self.working_dir)

        try:
            send_args = [self.command, 'message', '+send']
            for recipient in payload.to:
                send_args.extend(['--to', recipient])
            send_args.extend(['--subject', payload.subject, '--body-file', relative_body_file_path])

            first_result = self._run_command(send_args)
            if first_result.returncode != 0:
                raise MailDeliveryError(
                    first_result.stderr.strip() or first_result.stdout.strip() or 'Agent Mail CLI 调用失败'
                )

            parsed = self._parse_json_output(first_result.stdout)
            confirmation_token = (
                parsed.get('data', {}).get('confirmation_token')
                or parsed.get('confirmation_token')
            )

            if confirmation_token:
                confirm_args = send_args + ['--confirmation-token', confirmation_token]
                second_result = self._run_command(confirm_args)
                if second_result.returncode != 0:
                    raise MailDeliveryError(
                        second_result.stderr.strip() or second_result.stdout.strip() or 'Agent Mail CLI 二次确认发送失败'
                    )
                parsed = self._parse_json_output(second_result.stdout) or parsed
                raw_output = second_result.stdout.strip()
            else:
                raw_output = first_result.stdout.strip()

            message_id = (
                parsed.get('data', {}).get('message_id')
                or parsed.get('data', {}).get('id')
                or parsed.get('message_id')
                or ''
            )
            return MailSendResult(
                ok=True,
                provider=self.provider_name,
                detail='sent',
                message_id=message_id,
                raw_output=raw_output,
            )
        finally:
            try:
                os.unlink(body_file_path)
            except OSError:
                pass


class SMTPMailProvider(BaseMailProvider):
    provider_name = 'smtp'

    def __init__(self):
        self.host = settings.CLAIMCRAFT_SMTP_HOST
        self.port = settings.CLAIMCRAFT_SMTP_PORT
        self.username = settings.CLAIMCRAFT_SMTP_USERNAME
        self.password = settings.CLAIMCRAFT_SMTP_PASSWORD
        self.use_tls = settings.CLAIMCRAFT_SMTP_USE_TLS
        self.use_ssl = settings.CLAIMCRAFT_SMTP_USE_SSL
        self.timeout = settings.CLAIMCRAFT_MAIL_SEND_TIMEOUT_SECONDS

    def is_available(self) -> tuple[bool, str]:
        if not settings.CLAIMCRAFT_SMTP_ENABLED:
            return False, 'CLAIMCRAFT_SMTP_ENABLED=false'
        if not self.host:
            return False, '未配置 CLAIMCRAFT_SMTP_HOST'
        if not self.username or not self.password:
            return False, '未配置 SMTP 用户名或密码'
        return True, ''

    def send(self, payload: MailMessagePayload) -> MailSendResult:
        available, reason = self.is_available()
        if not available:
            raise MailDeliveryError(reason)

        from_email = (
            payload.from_email
            or settings.CLAIMCRAFT_MAIL_DEFAULT_FROM_EMAIL
            or self.username
        )
        from_name = payload.from_name or settings.CLAIMCRAFT_MAIL_DEFAULT_FROM_NAME

        message = EmailMessage()
        message['Subject'] = payload.subject
        message['From'] = f'{from_name} <{from_email}>' if from_name else from_email
        message['To'] = ', '.join(payload.to)
        message.set_content(payload.text_body)
        if payload.html_body:
            message.add_alternative(payload.html_body, subtype='html')

        smtp_class = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        with smtp_class(self.host, self.port, timeout=self.timeout) as smtp:
            smtp.ehlo()
            if self.use_tls and not self.use_ssl:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(self.username, self.password)
            smtp.send_message(message)

        return MailSendResult(
            ok=True,
            provider=self.provider_name,
            detail='sent',
        )


class MailDeliveryService:
    """邮件发送服务，按配置顺序依次尝试 provider。"""

    PROVIDER_MAP = {
        'agent_cli': AgentMailCLIProvider,
        'smtp': SMTPMailProvider,
    }

    def __init__(self, providers: Iterable[BaseMailProvider] | None = None):
        if providers is None:
            providers = self._build_default_providers()
        self.providers = list(providers)

    def _build_default_providers(self) -> list[BaseMailProvider]:
        providers = []
        for provider_name in settings.CLAIMCRAFT_MAIL_PROVIDER_ORDER:
            provider_class = self.PROVIDER_MAP.get(provider_name)
            if provider_class is None:
                logger.warning('unknown_mail_provider', extra={'provider': provider_name})
                continue
            providers.append(provider_class())
        return providers

    def send(self, payload: MailMessagePayload) -> MailSendResult:
        errors = []
        payload.to = _normalize_recipients(payload.to)

        for provider in self.providers:
            available, reason = provider.is_available()
            if not available:
                logger.warning(
                    'mail_provider_unavailable',
                    extra={'provider': provider.provider_name, 'reason': reason},
                )
                errors.append(f'{provider.provider_name}: {reason}')
                continue

            try:
                result = provider.send(payload)
                logger.info(
                    'mail_provider_succeeded',
                    extra={'provider': provider.provider_name},
                )
                return result
            except Exception as exc:
                logger.warning(
                    'mail_provider_failed',
                    extra={
                        'provider': provider.provider_name,
                        'error': str(exc),
                    },
                )
                errors.append(f'{provider.provider_name}: {exc}')

        raise MailDeliveryError('; '.join(errors) or '没有可用的邮件发送 provider')

    def send_verification_code(
        self,
        *,
        to_email: str,
        code: str,
        scene: str,
        expires_minutes: int = 10,
    ) -> MailSendResult:
        payload = build_verification_mail_payload(
            to_email=to_email,
            code=code,
            scene=scene,
            expires_minutes=expires_minutes,
        )
        return self.send(payload)


def get_mail_delivery_service() -> MailDeliveryService:
    return MailDeliveryService()
