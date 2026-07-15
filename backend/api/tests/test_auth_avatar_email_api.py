# -*- coding: utf-8 -*-
import io
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import EmailVerificationChallenge, UserProfile


def _build_uploaded_image(name='avatar.png', image_format='PNG', size=(320, 240)):
    buffer = io.BytesIO()
    image = Image.new('RGB', size, color=(33, 88, 166))
    image.save(buffer, format=image_format)
    return SimpleUploadedFile(
        name=name,
        content=buffer.getvalue(),
        content_type=f'image/{image_format.lower()}',
    )


class AuthAvatarEmailAPITests(APITestCase):
    register_url = '/api/auth/register/'
    register_send_code_url = '/api/auth/register/send-code/'
    register_verify_code_url = '/api/auth/register/verify-code/'
    login_url = '/api/auth/login/'
    login_send_code_url = '/api/auth/login/send-code/'
    login_email_code_url = '/api/auth/login/email-code/'
    password_reset_send_code_url = '/api/auth/password-reset/send-code/'
    password_reset_verify_code_url = '/api/auth/password-reset/verify-code/'
    password_reset_confirm_url = '/api/auth/password-reset/confirm/'
    me_url = '/api/auth/me/'
    avatar_url = '/api/auth/me/avatar/'
    send_code_url = '/api/auth/me/email/send-code/'
    verify_email_url = '/api/auth/me/email/verify/'
    change_request_url = '/api/auth/me/email/change/request/'
    change_confirm_url = '/api/auth/me/email/change/confirm/'
    change_password_send_code_url = '/api/auth/change-password/send-code/'
    change_password_verify_code_url = '/api/auth/change-password/verify-code/'
    change_password_url = '/api/auth/change-password/'
    password = 'ClaimCraftPass123!'

    def setUp(self):
        self.user = User.objects.create_user(
            username='account_user',
            email='account@example.com',
            password=self.password,
        )

    def login_user(self, user=None):
        user = user or self.user
        client = APIClient()
        response = client.post(
            self.login_url,
            {'account': user.username, 'password': self.password},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
        return client

    @override_settings(
        CLAIMCRAFT_AVATAR_MAX_UPLOAD_BYTES=5 * 1024 * 1024,
        CLAIMCRAFT_AVATAR_ALLOWED_EXTENSIONS=['jpg', 'jpeg', 'png', 'webp'],
        CLAIMCRAFT_AVATAR_DISPLAY_SIZE=256,
        CLAIMCRAFT_AVATAR_DISPLAY_FORMAT='WEBP',
        CLAIMCRAFT_AVATAR_DISPLAY_QUALITY=85,
    )
    def test_avatar_upload_delete_and_me_payload(self):
        client = self.login_user()
        temp_media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_media_dir.cleanup)

        with self.settings(MEDIA_ROOT=temp_media_dir.name):
            upload_response = client.post(
                self.avatar_url,
                {
                    'avatar': _build_uploaded_image(),
                },
                format='multipart',
            )
            self.assertEqual(
                upload_response.status_code,
                status.HTTP_200_OK,
                upload_response.content,
            )

            profile = UserProfile.objects.get(user=self.user)
            self.assertTrue(profile.avatar_original.name.startswith(f'avatar/{self.user.id}/original/'))
            self.assertTrue(profile.avatar_display.name.startswith(f'avatar/{self.user.id}/display/'))
            self.assertIn('/media/avatar/', upload_response.json()['user']['avatar_url'])

            me_response = client.get(self.me_url)
            self.assertEqual(me_response.status_code, status.HTTP_200_OK, me_response.content)
            self.assertEqual(
                me_response.json()['avatar_url'],
                upload_response.json()['user']['avatar_url'],
            )

            delete_response = client.delete(self.avatar_url)
            self.assertEqual(
                delete_response.status_code,
                status.HTTP_200_OK,
                delete_response.content,
            )
            self.assertEqual(delete_response.json()['user']['avatar_url'], '')

    @mock.patch('api.views._generate_email_verification_code', return_value='123456')
    @mock.patch('api.views.get_mail_delivery_service')
    def test_send_code_and_verify_current_email_success(self, mock_get_mail_service, _mock_code):
        mock_get_mail_service.return_value.send_verification_code.return_value = SimpleNamespace(
            provider='smtp'
        )
        client = self.login_user()

        send_response = client.post(self.send_code_url, {}, format='json')
        self.assertEqual(send_response.status_code, status.HTTP_200_OK, send_response.content)
        self.assertEqual(send_response.json()['provider'], 'smtp')

        challenge = EmailVerificationChallenge.objects.get(
            user=self.user,
            scene=EmailVerificationChallenge.Scene.VERIFY_CURRENT_EMAIL,
        )
        self.assertNotEqual(challenge.code_hash, '123456')
        self.assertTrue(challenge.check_plain_code('123456'))

        verify_response = client.post(
            self.verify_email_url,
            {'code': '123456'},
            format='json',
        )
        self.assertEqual(
            verify_response.status_code,
            status.HTTP_200_OK,
            verify_response.content,
        )

        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.email_verified)
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.verified_at)
        self.assertIsNotNone(challenge.used_at)

        repeated_response = client.post(
            self.verify_email_url,
            {'code': '123456'},
            format='json',
        )
        self.assertEqual(
            repeated_response.status_code,
            status.HTTP_400_BAD_REQUEST,
            repeated_response.content,
        )
        self.assertIn('已使用', repeated_response.json()['detail'])

    @mock.patch('api.views._generate_email_verification_code', return_value='123456')
    @mock.patch('api.views.get_mail_delivery_service')
    def test_send_code_respects_cooldown_limit(self, mock_get_mail_service, _mock_code):
        mock_get_mail_service.return_value.send_verification_code.return_value = SimpleNamespace(
            provider='smtp'
        )
        client = self.login_user()

        first_response = client.post(self.send_code_url, {}, format='json')
        self.assertEqual(first_response.status_code, status.HTTP_200_OK, first_response.content)

        second_response = client.post(self.send_code_url, {}, format='json')
        self.assertEqual(
            second_response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
            second_response.content,
        )
        self.assertIn('频繁', second_response.json()['detail'])

    @override_settings(CLAIMCRAFT_EMAIL_VERIFICATION_MAX_ATTEMPTS=2)
    def test_verify_current_email_rejects_expired_and_attempt_over_limit(self):
        client = self.login_user()
        expired = EmailVerificationChallenge.objects.create(
            user=self.user,
            scene=EmailVerificationChallenge.Scene.VERIFY_CURRENT_EMAIL,
            target_email=self.user.email.lower(),
            code_hash='',
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        expired.set_plain_code('123456')
        expired.save(update_fields=['code_hash'])

        expired_response = client.post(
            self.verify_email_url,
            {'code': '123456'},
            format='json',
        )
        self.assertEqual(
            expired_response.status_code,
            status.HTTP_400_BAD_REQUEST,
            expired_response.content,
        )
        self.assertIn('已过期', expired_response.json()['detail'])

        expired.delete()
        challenge = EmailVerificationChallenge.objects.create(
            user=self.user,
            scene=EmailVerificationChallenge.Scene.VERIFY_CURRENT_EMAIL,
            target_email=self.user.email.lower(),
            code_hash='',
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        challenge.set_plain_code('123456')
        challenge.save(update_fields=['code_hash'])

        first_wrong = client.post(
            self.verify_email_url,
            {'code': '000000'},
            format='json',
        )
        self.assertEqual(first_wrong.status_code, status.HTTP_400_BAD_REQUEST, first_wrong.content)
        self.assertEqual(first_wrong.json()['remaining_attempts'], 1)

        second_wrong = client.post(
            self.verify_email_url,
            {'code': '000000'},
            format='json',
        )
        self.assertEqual(second_wrong.status_code, status.HTTP_400_BAD_REQUEST, second_wrong.content)
        self.assertIn('次数过多', second_wrong.json()['detail'])

        third_wrong = client.post(
            self.verify_email_url,
            {'code': '123456'},
            format='json',
        )
        self.assertEqual(third_wrong.status_code, status.HTTP_400_BAD_REQUEST, third_wrong.content)
        self.assertIn('已达上限', third_wrong.json()['detail'])

    @mock.patch('api.views._generate_email_verification_code', return_value='654321')
    @mock.patch('api.views.get_mail_delivery_service')
    def test_change_email_request_and_confirm_success(self, mock_get_mail_service, _mock_code):
        mock_get_mail_service.return_value.send_verification_code.return_value = SimpleNamespace(
            provider='smtp'
        )
        client = self.login_user()

        request_response = client.post(
            self.change_request_url,
            {'new_email': 'new-address@example.com'},
            format='json',
        )
        self.assertEqual(
            request_response.status_code,
            status.HTTP_200_OK,
            request_response.content,
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'account@example.com')

        confirm_response = client.post(
            self.change_confirm_url,
            {
                'new_email': 'new-address@example.com',
                'code': '654321',
            },
            format='json',
        )
        self.assertEqual(
            confirm_response.status_code,
            status.HTTP_200_OK,
            confirm_response.content,
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new-address@example.com')
        self.assertTrue(UserProfile.objects.get(user=self.user).email_verified)

    @mock.patch('api.views._generate_email_verification_code', return_value='112233')
    @mock.patch('api.views.get_mail_delivery_service')
    def test_register_send_code_and_verify_supports_anonymous_challenge(
        self,
        mock_get_mail_service,
        _mock_code,
    ):
        mock_get_mail_service.return_value.send_verification_code.return_value = SimpleNamespace(
            provider='smtp'
        )

        send_response = self.client.post(
            self.register_send_code_url,
            {'email': 'fresh@example.com'},
            format='json',
        )
        self.assertEqual(send_response.status_code, status.HTTP_200_OK, send_response.content)

        challenge = EmailVerificationChallenge.objects.get(
            user__isnull=True,
            scene=EmailVerificationChallenge.Scene.REGISTER_EMAIL,
            target_email='fresh@example.com',
        )
        self.assertTrue(challenge.check_plain_code('112233'))
        self.assertIsNone(challenge.verified_at)
        self.assertIsNone(challenge.used_at)

        verify_response = self.client.post(
            self.register_verify_code_url,
            {'email': 'fresh@example.com', 'code': '112233'},
            format='json',
        )
        self.assertEqual(
            verify_response.status_code,
            status.HTTP_200_OK,
            verify_response.content,
        )

        challenge.refresh_from_db()
        self.assertIsNone(challenge.user_id)
        self.assertIsNotNone(challenge.verified_at)
        self.assertIsNone(challenge.used_at)

    @mock.patch('api.views._generate_email_verification_code', return_value='445566')
    @mock.patch('api.views.get_mail_delivery_service')
    def test_login_send_code_and_email_code_login_success(
        self,
        mock_get_mail_service,
        _mock_code,
    ):
        mock_get_mail_service.return_value.send_verification_code.return_value = SimpleNamespace(
            provider='smtp'
        )

        send_response = self.client.post(
            self.login_send_code_url,
            {'email': self.user.email.upper()},
            format='json',
        )
        self.assertEqual(send_response.status_code, status.HTTP_200_OK, send_response.content)

        challenge = EmailVerificationChallenge.objects.get(
            user__isnull=True,
            scene=EmailVerificationChallenge.Scene.LOGIN_EMAIL,
            target_email=self.user.email.lower(),
        )
        self.assertTrue(challenge.check_plain_code('445566'))

        login_response = self.client.post(
            self.login_email_code_url,
            {'email': self.user.email, 'code': '445566'},
            format='json',
        )
        self.assertEqual(
            login_response.status_code,
            status.HTTP_200_OK,
            login_response.content,
        )
        self.assertEqual(
            sorted(login_response.json().keys()),
            [
                'access',
                'access_expires_in',
                'refresh',
                'refresh_expires_in',
                'session_id',
                'user',
            ],
        )

        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.verified_at)
        self.assertIsNotNone(challenge.used_at)

    @mock.patch('api.views._generate_email_verification_code', return_value='778899')
    @mock.patch('api.views.get_mail_delivery_service')
    def test_change_password_send_code_and_verify_code_success(
        self,
        mock_get_mail_service,
        _mock_code,
    ):
        mock_get_mail_service.return_value.send_verification_code.return_value = SimpleNamespace(
            provider='smtp'
        )
        client = self.login_user()

        send_response = client.post(self.change_password_send_code_url, {}, format='json')
        self.assertEqual(send_response.status_code, status.HTTP_200_OK, send_response.content)

        challenge = EmailVerificationChallenge.objects.get(
            user=self.user,
            scene=EmailVerificationChallenge.Scene.CHANGE_PASSWORD_EMAIL,
            target_email=self.user.email.lower(),
        )
        self.assertTrue(challenge.check_plain_code('778899'))
        self.assertIsNone(challenge.verified_at)
        self.assertIsNone(challenge.used_at)

        verify_response = client.post(
            self.change_password_verify_code_url,
            {'code': '778899'},
            format='json',
        )
        self.assertEqual(
            verify_response.status_code,
            status.HTTP_200_OK,
            verify_response.content,
        )

        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.verified_at)
        self.assertIsNone(challenge.used_at)

    @mock.patch('api.views._generate_email_verification_code', return_value='991122')
    @mock.patch('api.views.get_mail_delivery_service')
    def test_password_reset_send_verify_and_confirm_success(
        self,
        mock_get_mail_service,
        _mock_code,
    ):
        mock_get_mail_service.return_value.send_verification_code.return_value = SimpleNamespace(
            provider='smtp'
        )
        new_password = 'ClaimCraftPass456!'
        current_client = self.login_user()
        current_session_response = current_client.get(self.me_url)
        self.assertEqual(
            current_session_response.status_code,
            status.HTTP_200_OK,
            current_session_response.content,
        )

        send_response = self.client.post(
            self.password_reset_send_code_url,
            {'email': self.user.email.upper()},
            format='json',
        )
        self.assertEqual(send_response.status_code, status.HTTP_200_OK, send_response.content)

        verify_response = self.client.post(
            self.password_reset_verify_code_url,
            {'email': self.user.email, 'code': '991122'},
            format='json',
        )
        self.assertEqual(
            verify_response.status_code,
            status.HTTP_200_OK,
            verify_response.content,
        )

        confirm_response = self.client.post(
            self.password_reset_confirm_url,
            {
                'email': self.user.email,
                'new_password': new_password,
                'new_password_confirm': new_password,
            },
            format='json',
        )
        self.assertEqual(
            confirm_response.status_code,
            status.HTTP_200_OK,
            confirm_response.content,
        )
        self.assertEqual(confirm_response.json()['revoked_sessions'], 1)

        challenge = EmailVerificationChallenge.objects.get(
            user__isnull=True,
            scene=EmailVerificationChallenge.Scene.RESET_PASSWORD,
            target_email=self.user.email.lower(),
        )
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.verified_at)
        self.assertIsNotNone(challenge.used_at)

        old_password_login = self.client.post(
            self.login_url,
            {'account': self.user.username, 'password': self.password},
            format='json',
        )
        self.assertEqual(
            old_password_login.status_code,
            status.HTTP_401_UNAUTHORIZED,
            old_password_login.content,
        )

        new_password_login = self.client.post(
            self.login_url,
            {'account': self.user.email, 'password': new_password},
            format='json',
        )
        self.assertEqual(
            new_password_login.status_code,
            status.HTTP_200_OK,
            new_password_login.content,
        )

    def test_register_send_code_rejects_occupied_email(self):
        response = self.client.post(
            self.register_send_code_url,
            {'email': self.user.email},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.content)

    def test_login_send_code_rejects_unknown_email(self):
        response = self.client.post(
            self.login_send_code_url,
            {'email': 'missing@example.com'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)

    def test_change_email_request_rejects_occupied_email(self):
        User.objects.create_user(
            username='other_user',
            email='occupied@example.com',
            password=self.password,
        )
        client = self.login_user()

        response = client.post(
            self.change_request_url,
            {'new_email': 'occupied@example.com'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.content)
        self.assertIn('占用', response.json()['detail'])
