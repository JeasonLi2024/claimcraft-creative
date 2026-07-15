# -*- coding: utf-8 -*-
import io
import os
import tempfile
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from api.models import EmailVerificationChallenge, UserProfile
from api.services.avatar_service import delete_user_avatar, save_user_avatar
from api.services.mail_service import (
    AgentMailCLIProvider,
    MailDeliveryError,
    MailDeliveryService,
    MailMessagePayload,
    build_verification_mail_payload,
)


def _build_uploaded_image(name='avatar.png', image_format='PNG', size=(320, 200)):
    buffer = io.BytesIO()
    image = Image.new('RGB', size, color=(10, 120, 200))
    image.save(buffer, format=image_format)
    return SimpleUploadedFile(
        name=name,
        content=buffer.getvalue(),
        content_type=f'image/{image_format.lower()}',
    )


class AvatarServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='avatar_user',
            email='avatar@example.com',
            password='ClaimCraftPass123!',
        )
        self.profile, _ = UserProfile.objects.get_or_create(
            user=self.user,
            defaults={'display_name': self.user.username},
        )
        self.temp_media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_media_dir.cleanup)

    @override_settings(
        MEDIA_ROOT='',
        CLAIMCRAFT_AVATAR_MAX_UPLOAD_BYTES=5 * 1024 * 1024,
        CLAIMCRAFT_AVATAR_ALLOWED_EXTENSIONS=['jpg', 'jpeg', 'png', 'webp'],
        CLAIMCRAFT_AVATAR_DISPLAY_SIZE=256,
        CLAIMCRAFT_AVATAR_DISPLAY_FORMAT='WEBP',
        CLAIMCRAFT_AVATAR_DISPLAY_QUALITY=85,
    )
    def test_save_user_avatar_creates_original_and_display_files(self):
        with self.settings(MEDIA_ROOT=self.temp_media_dir.name):
            result = save_user_avatar(self.profile, _build_uploaded_image())
            self.profile.refresh_from_db()
            self.assertEqual(result.profile.id, self.profile.id)
            self.assertTrue(self.profile.avatar_original.name.startswith(f'avatar/{self.user.id}/original/'))
            self.assertTrue(self.profile.avatar_display.name.startswith(f'avatar/{self.user.id}/display/'))
            self.assertTrue(os.path.exists(self.profile.avatar_original.path))
            self.assertTrue(os.path.exists(self.profile.avatar_display.path))
            self.assertIsNotNone(self.profile.avatar_updated_at)

            with Image.open(self.profile.avatar_display.path) as display_image:
                self.assertEqual(display_image.size, (256, 256))

    @override_settings(
        CLAIMCRAFT_AVATAR_MAX_UPLOAD_BYTES=5 * 1024 * 1024,
        CLAIMCRAFT_AVATAR_ALLOWED_EXTENSIONS=['jpg', 'jpeg', 'png', 'webp'],
        CLAIMCRAFT_AVATAR_DISPLAY_SIZE=256,
        CLAIMCRAFT_AVATAR_DISPLAY_FORMAT='WEBP',
        CLAIMCRAFT_AVATAR_DISPLAY_QUALITY=85,
    )
    def test_replace_and_delete_avatar_cleanup_old_files(self):
        with self.settings(MEDIA_ROOT=self.temp_media_dir.name):
            save_user_avatar(self.profile, _build_uploaded_image(name='first.png'))
            self.profile.refresh_from_db()
            first_original = self.profile.avatar_original.path
            first_display = self.profile.avatar_display.path

            result = save_user_avatar(
                self.profile,
                _build_uploaded_image(name='second.jpg', image_format='JPEG'),
            )
            self.profile.refresh_from_db()

            self.assertNotEqual(self.profile.avatar_original.path, first_original)
            self.assertNotEqual(self.profile.avatar_display.path, first_display)
            self.assertFalse(os.path.exists(first_original))
            self.assertFalse(os.path.exists(first_display))
            self.assertGreaterEqual(len(result.deleted_files), 2)

            deleted_files = delete_user_avatar(self.profile)
            self.profile.refresh_from_db()

            self.assertFalse(self.profile.avatar_original)
            self.assertFalse(self.profile.avatar_display)
            self.assertGreaterEqual(len(deleted_files), 0)


class EmailVerificationChallengeTests(TestCase):
    def test_plain_code_is_hashed_and_can_be_verified(self):
        user = User.objects.create_user(
            username='mailer',
            email='mailer@example.com',
            password='ClaimCraftPass123!',
        )
        challenge = EmailVerificationChallenge.objects.create(
            user=user,
            scene=EmailVerificationChallenge.Scene.VERIFY_CURRENT_EMAIL,
            target_email=user.email,
            code_hash='',
            expires_at=datetime(2099, 1, 1, 0, 0, 0),
        )

        challenge.set_plain_code('123456')
        challenge.save(update_fields=['code_hash'])

        self.assertNotEqual(challenge.code_hash, '123456')
        self.assertTrue(challenge.check_plain_code('123456'))
        self.assertFalse(challenge.check_plain_code('654321'))


class MailServiceTests(TestCase):
    def test_build_verification_mail_payload_supports_new_password_scenes(self):
        reset_payload = build_verification_mail_payload(
            to_email='user@example.com',
            code='123456',
            scene='reset_password',
            expires_minutes=10,
        )
        change_payload = build_verification_mail_payload(
            to_email='user@example.com',
            code='654321',
            scene='change_password_email',
            expires_minutes=10,
        )

        self.assertIn('重置密码', reset_payload.subject)
        self.assertIn('123456', reset_payload.text_body)
        self.assertIn('修改密码校验', change_payload.subject)
        self.assertIn('654321', change_payload.html_body)

    @override_settings(
        CLAIMCRAFT_AGENT_MAIL_ENABLED=True,
        CLAIMCRAFT_AGENT_MAIL_COMMAND='agently-cli',
        CLAIMCRAFT_MAIL_SEND_TIMEOUT_SECONDS=5,
    )
    @mock.patch('api.services.mail_service.os.unlink')
    @mock.patch('api.services.mail_service.subprocess.run')
    @mock.patch('api.services.mail_service.shutil.which', return_value='C:\\Tools\\agently-cli.cmd')
    def test_agent_mail_cli_provider_handles_two_step_confirmation(
        self,
        mock_which,
        mock_run,
        mock_unlink,
    ):
        mock_run.side_effect = [
            SimpleNamespace(
                returncode=0,
                stdout='{"data":{"confirmation_token":"confirm-123"}}',
                stderr='',
            ),
            SimpleNamespace(
                returncode=0,
                stdout='{"data":{"message_id":"msg_123"}}',
                stderr='',
            ),
        ]

        provider = AgentMailCLIProvider()
        result = provider.send(
            MailMessagePayload(
                to=['user@example.com'],
                subject='Test Subject',
                text_body='Plain body',
                html_body='<p>HTML body</p>',
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.provider, 'agent_cli')
        self.assertEqual(result.message_id, 'msg_123')
        self.assertEqual(mock_run.call_count, 2)
        first_call_args = mock_run.call_args_list[0].args[0]
        second_call_args = mock_run.call_args_list[1].args[0]
        self.assertEqual(first_call_args[:3], ['agently-cli', 'message', '+send'])
        self.assertIn('--body-file', first_call_args)
        self.assertEqual(second_call_args[-2:], ['--confirmation-token', 'confirm-123'])
        mock_unlink.assert_called_once()
        mock_which.assert_called_once_with('agently-cli')

    def test_mail_delivery_service_falls_back_to_next_provider(self):
        failing_provider = mock.Mock()
        failing_provider.provider_name = 'agent_cli'
        failing_provider.is_available.return_value = (True, '')
        failing_provider.send.side_effect = MailDeliveryError('cli failed')

        smtp_provider = mock.Mock()
        smtp_provider.provider_name = 'smtp'
        smtp_provider.is_available.return_value = (True, '')
        smtp_provider.send.return_value = SimpleNamespace(
            ok=True,
            provider='smtp',
            detail='sent',
        )

        service = MailDeliveryService([failing_provider, smtp_provider])
        result = service.send(
            MailMessagePayload(
                to=['user@example.com'],
                subject='Fallback test',
                text_body='hello',
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.provider, 'smtp')
        failing_provider.send.assert_called_once()
        smtp_provider.send.assert_called_once()
