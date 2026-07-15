from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from api.models import (
    AccountAuditLog,
    EmailVerificationChallenge,
    UserPreference,
    UserProfile,
    UserSession,
)


class AuthAPITestMixin:
    register_url = '/api/auth/register/'
    login_url = '/api/auth/login/'
    password_reset_send_code_url = '/api/auth/password-reset/send-code/'
    password_reset_verify_code_url = '/api/auth/password-reset/verify-code/'
    password_reset_confirm_url = '/api/auth/password-reset/confirm/'
    refresh_url = '/api/auth/refresh/'
    logout_url = '/api/auth/logout/'
    logout_all_url = '/api/auth/logout-all/'
    me_url = '/api/auth/me/'
    preferences_url = '/api/auth/me/preferences/'
    change_password_send_code_url = '/api/auth/change-password/send-code/'
    change_password_verify_code_url = '/api/auth/change-password/verify-code/'
    change_password_url = '/api/auth/change-password/'
    sessions_url = '/api/auth/sessions/'
    default_password = 'ClaimCraftPass123!'
    changed_password = 'ClaimCraftPass456!'
    default_user_agent = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    )

    def create_user(self, username='alice', email=None, password=None):
        email = email or f'{username}@example.com'
        password = password or self.default_password
        return User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

    def login_user(self, user, password=None, client=None, user_agent=None):
        client = client or APIClient()
        password = password or self.default_password
        user_agent = user_agent or self.default_user_agent
        response = client.post(
            self.login_url,
            {'account': user.username, 'password': password},
            format='json',
            HTTP_USER_AGENT=user_agent,
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return client, response.json()

    def create_verified_register_challenge(self, email):
        challenge = EmailVerificationChallenge.objects.create(
            user=None,
            scene=EmailVerificationChallenge.Scene.REGISTER_EMAIL,
            target_email=email.lower(),
            code_hash='',
            expires_at=timezone.now() + timedelta(minutes=10),
            verified_at=timezone.now(),
        )
        challenge.set_plain_code('123456')
        challenge.save(update_fields=['code_hash', 'verified_at'])
        return challenge

    def create_verified_email_challenge(self, *, user, scene, email=None, code='123456'):
        challenge = EmailVerificationChallenge.objects.create(
            user=user,
            scene=scene,
            target_email=(email or user.email).lower(),
            code_hash='',
            expires_at=timezone.now() + timedelta(minutes=10),
            verified_at=timezone.now(),
        )
        challenge.set_plain_code(code)
        challenge.save(update_fields=['code_hash', 'verified_at'])
        return challenge

    def build_authed_client(self, access_token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        return client

    def assert_refresh_rejected(self, refresh_token):
        response = self.client.post(
            self.refresh_url,
            {'refresh': refresh_token},
            format='json',
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
            response.content,
        )

    def assert_auth_required(self, method, path, data=None):
        client = APIClient()
        response = getattr(client, method)(path, data=data, format='json')
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
            response.content,
        )


class AuthenticationFlowTests(AuthAPITestMixin, APITestCase):
    def test_register_uses_password_confirm_and_bootstraps_profile_preferences(self):
        challenge = self.create_verified_register_challenge('newuser@example.com')
        response = self.client.post(
            self.register_url,
            {
                'username': 'newuser',
                'email': 'newuser@example.com',
                'password': self.default_password,
                'password_confirm': self.default_password,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        user = User.objects.get(username='newuser')
        challenge.refresh_from_db()
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertTrue(UserPreference.objects.filter(user=user).exists())
        self.assertTrue(UserProfile.objects.get(user=user).email_verified)
        self.assertIsNotNone(challenge.used_at)
        self.assertEqual(response.json()['email'], 'newuser@example.com')

    def test_register_requires_verified_email_challenge(self):
        response = self.client.post(
            self.register_url,
            {
                'username': 'plainuser',
                'email': 'plainuser@example.com',
                'password': self.default_password,
                'password_confirm': self.default_password,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)
        self.assertIn('先发送验证码', response.json()['detail'])

    def test_login_accepts_username_or_email_in_account_field(self):
        user = self.create_user(username='multiway', email='multiway@example.com')

        username_response = self.client.post(
            self.login_url,
            {'account': user.username, 'password': self.default_password},
            format='json',
        )
        self.assertEqual(
            username_response.status_code,
            status.HTTP_200_OK,
            username_response.content,
        )

        email_response = self.client.post(
            self.login_url,
            {'account': 'MULTIWAY@example.com', 'password': self.default_password},
            format='json',
        )
        self.assertEqual(
            email_response.status_code,
            status.HTTP_200_OK,
            email_response.content,
        )
        self.assertEqual(email_response.json()['user']['id'], user.id)

    def test_login_refresh_logout_flow_rotates_tokens_and_revokes_session(self):
        user = self.create_user()
        _, login_payload = self.login_user(user)

        self.assertEqual(
            sorted(login_payload.keys()),
            [
                'access',
                'access_expires_in',
                'refresh',
                'refresh_expires_in',
                'session_id',
                'user',
            ],
        )
        access_token = AccessToken(login_payload['access'])
        refresh_token = RefreshToken(login_payload['refresh'])
        session = UserSession.objects.get(id=login_payload['session_id'])
        original_jti = refresh_token['jti']

        self.assertEqual(access_token['session_id'], session.id)
        self.assertEqual(refresh_token['session_id'], session.id)
        self.assertEqual(session.refresh_jti, original_jti)
        self.assertTrue(
            AccountAuditLog.objects.filter(
                user=user,
                action=AccountAuditLog.ACTION_LOGIN,
                session=session,
            ).exists()
        )

        refresh_response = self.client.post(
            self.refresh_url,
            {'refresh': login_payload['refresh']},
            format='json',
        )
        self.assertEqual(
            refresh_response.status_code,
            status.HTTP_200_OK,
            refresh_response.content,
        )
        refresh_payload = refresh_response.json()
        rotated_refresh = RefreshToken(refresh_payload['refresh'])

        self.assertEqual(refresh_payload['session_id'], session.id)
        self.assertNotEqual(rotated_refresh['jti'], original_jti)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=original_jti).exists()
        )

        session.refresh_from_db()
        self.assertEqual(session.refresh_jti, rotated_refresh['jti'])
        self.assertIsNone(session.revoked_at)

        logout_client = self.build_authed_client(refresh_payload['access'])
        logout_response = logout_client.post(
            self.logout_url,
            {'refresh': refresh_payload['refresh']},
            format='json',
        )
        self.assertEqual(
            logout_response.status_code,
            status.HTTP_200_OK,
            logout_response.content,
        )
        self.assertEqual(logout_response.json()['detail'], '已退出当前设备')

        session.refresh_from_db()
        self.assertIsNotNone(session.revoked_at)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=rotated_refresh['jti']).exists()
        )
        self.assertTrue(
            AccountAuditLog.objects.filter(
                user=user,
                action=AccountAuditLog.ACTION_LOGOUT,
                session=session,
            ).exists()
        )

        repeated_logout = logout_client.post(
            self.logout_url,
            {'refresh': refresh_payload['refresh']},
            format='json',
        )
        self.assertEqual(
            repeated_logout.status_code,
            status.HTTP_200_OK,
            repeated_logout.content,
        )
        self.assert_refresh_rejected(refresh_payload['refresh'])

    def test_logout_all_revokes_every_active_session(self):
        user = self.create_user()
        client_a, login_a = self.login_user(
            user,
            client=APIClient(),
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0',
        )
        _, login_b = self.login_user(
            user,
            client=APIClient(),
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile',
        )

        response = self.build_authed_client(login_b['access']).post(
            self.logout_all_url,
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(response.json()['revoked_sessions'], 2)

        revoked_sessions = UserSession.objects.filter(
            user=user,
            revoked_at__isnull=False,
        ).count()
        self.assertEqual(revoked_sessions, 2)
        self.assert_refresh_rejected(login_a['refresh'])
        self.assert_refresh_rejected(login_b['refresh'])
        self.assertTrue(
            AccountAuditLog.objects.filter(
                user=user,
                action=AccountAuditLog.ACTION_LOGOUT_ALL,
            ).exists()
        )


class AccountCenterTests(AuthAPITestMixin, APITestCase):
    def test_me_get_and_patch_return_aggregated_profile(self):
        user = self.create_user()
        _, login_payload = self.login_user(user)
        client = self.build_authed_client(login_payload['access'])

        get_response = client.get(self.me_url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK, get_response.content)
        data = get_response.json()
        self.assertEqual(data['username'], user.username)
        self.assertIn('preferences', data)
        self.assertEqual(data['display_name'], user.username)

        patch_response = client.patch(
            self.me_url,
            {
                'display_name': 'Alice Chen',
                'bio': '专注消费维权',
                'locale': 'zh-CN',
                'timezone': 'Asia/Shanghai',
            },
            format='json',
        )
        self.assertEqual(
            patch_response.status_code,
            status.HTTP_200_OK,
            patch_response.content,
        )

        user.refresh_from_db()
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.display_name, 'Alice Chen')
        self.assertEqual(profile.bio, '专注消费维权')
        self.assertEqual(profile.timezone, 'Asia/Shanghai')
        self.assertEqual(user.email, 'alice@example.com')

    def test_preferences_get_and_patch_persist_changes(self):
        user = self.create_user()
        _, login_payload = self.login_user(user)
        client = self.build_authed_client(login_payload['access'])

        get_response = client.get(self.preferences_url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK, get_response.content)
        self.assertTrue(get_response.json()['workflow_reminders'])

        patch_response = client.patch(
            self.preferences_url,
            {
                'workflow_reminders': False,
                'export_reminder': False,
                'compact_case_cards': True,
                'default_case_mode': 'respond',
                'default_template_type': 'regulatory',
            },
            format='json',
        )
        self.assertEqual(
            patch_response.status_code,
            status.HTTP_200_OK,
            patch_response.content,
        )

        preferences = UserPreference.objects.get(user=user)
        self.assertFalse(preferences.workflow_reminders)
        self.assertFalse(preferences.export_reminder)
        self.assertTrue(preferences.compact_case_cards)
        self.assertEqual(preferences.default_case_mode, 'respond')
        self.assertEqual(preferences.default_template_type, 'regulatory')

    def test_change_password_rejects_wrong_old_password(self):
        user = self.create_user()
        _, login_payload = self.login_user(user)
        client = self.build_authed_client(login_payload['access'])
        self.create_verified_email_challenge(
            user=user,
            scene=EmailVerificationChallenge.Scene.CHANGE_PASSWORD_EMAIL,
        )

        response = client.post(
            self.change_password_url,
            {
                'old_password': 'wrong-password',
                'new_password': self.changed_password,
                'new_password_confirm': self.changed_password,
                'logout_other_sessions': False,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertIn('old_password', response.json())

    def test_change_password_requires_verified_email_challenge(self):
        user = self.create_user()
        _, login_payload = self.login_user(user)
        client = self.build_authed_client(login_payload['access'])

        response = client.post(
            self.change_password_url,
            {
                'old_password': self.default_password,
                'new_password': self.changed_password,
                'new_password_confirm': self.changed_password,
                'logout_other_sessions': False,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)
        self.assertIn('先发送验证码', response.json()['detail'])

    def test_change_password_can_revoke_other_sessions_and_keep_current(self):
        user = self.create_user()
        _, other_login = self.login_user(user, client=APIClient())
        _, current_login = self.login_user(
            user,
            client=APIClient(),
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/127.0',
        )
        challenge = self.create_verified_email_challenge(
            user=user,
            scene=EmailVerificationChallenge.Scene.CHANGE_PASSWORD_EMAIL,
        )

        response = self.build_authed_client(current_login['access']).post(
            self.change_password_url,
            {
                'old_password': self.default_password,
                'new_password': self.changed_password,
                'new_password_confirm': self.changed_password,
                'logout_other_sessions': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(response.json()['revoked_other_sessions'], 1)
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.used_at)

        current_session = UserSession.objects.get(id=current_login['session_id'])
        other_session = UserSession.objects.get(id=other_login['session_id'])
        current_session.refresh_from_db()
        other_session.refresh_from_db()

        self.assertIsNone(current_session.revoked_at)
        self.assertIsNotNone(other_session.revoked_at)
        self.assert_refresh_rejected(other_login['refresh'])

        old_login_response = self.client.post(
            self.login_url,
            {'account': user.username, 'password': self.default_password},
            format='json',
        )
        self.assertEqual(
            old_login_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
            old_login_response.content,
        )

        _, new_login = self.login_user(user, password=self.changed_password)
        self.assertIn('access', new_login)
        self.assertTrue(
            AccountAuditLog.objects.filter(
                user=user,
                action=AccountAuditLog.ACTION_CHANGE_PASSWORD,
                session=current_session,
            ).exists()
        )


class SessionPermissionTests(AuthAPITestMixin, APITestCase):
    def test_sessions_list_marks_current_session(self):
        user = self.create_user()
        _, first_login = self.login_user(user, client=APIClient())
        _, current_login = self.login_user(
            user,
            client=APIClient(),
            user_agent='Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)',
        )

        response = self.build_authed_client(current_login['access']).get(self.sessions_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

        sessions = {item['id']: item for item in response.json()}
        self.assertIn(first_login['session_id'], sessions)
        self.assertIn(current_login['session_id'], sessions)
        self.assertFalse(sessions[first_login['session_id']]['is_current'])
        self.assertTrue(sessions[current_login['session_id']]['is_current'])

    def test_revoke_session_revokes_only_owned_target_session(self):
        user = self.create_user()
        _, target_login = self.login_user(user, client=APIClient())
        _, current_login = self.login_user(user, client=APIClient())
        current_client = self.build_authed_client(current_login['access'])

        response = current_client.delete(
            f'{self.sessions_url}{target_login["session_id"]}/',
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(response.json()['session_id'], target_login['session_id'])

        target_session = UserSession.objects.get(id=target_login['session_id'])
        current_session = UserSession.objects.get(id=current_login['session_id'])
        self.assertIsNotNone(target_session.revoked_at)
        self.assertIsNone(current_session.revoked_at)
        self.assert_refresh_rejected(target_login['refresh'])
        self.assertTrue(
            AccountAuditLog.objects.filter(
                user=user,
                action=AccountAuditLog.ACTION_REVOKE_SESSION,
                session=target_session,
            ).exists()
        )

    def test_cannot_revoke_other_users_session(self):
        owner = self.create_user(username='owner')
        attacker = self.create_user(username='attacker')
        _, owner_login = self.login_user(owner, client=APIClient())
        attacker_client = self.build_authed_client(self.login_user(attacker)[1]['access'])

        response = attacker_client.delete(
            f'{self.sessions_url}{owner_login["session_id"]}/',
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)

        owner_session = UserSession.objects.get(id=owner_login['session_id'])
        self.assertIsNone(owner_session.revoked_at)

    def test_logout_rejects_refresh_token_of_another_user(self):
        owner = self.create_user(username='owner')
        attacker = self.create_user(username='attacker')
        _, owner_login = self.login_user(owner, client=APIClient())
        attacker_access = self.login_user(attacker, client=APIClient())[1]['access']

        response = self.build_authed_client(attacker_access).post(
            self.logout_url,
            {'refresh': owner_login['refresh']},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.content)

        owner_session = UserSession.objects.get(id=owner_login['session_id'])
        self.assertIsNone(owner_session.revoked_at)
        self.assertFalse(
            BlacklistedToken.objects.filter(
                token__jti=RefreshToken(owner_login['refresh'])['jti']
            ).exists()
        )

    def test_protected_endpoints_require_authentication(self):
        protected_calls = [
            ('get', self.me_url, None),
            ('patch', self.me_url, {'display_name': 'NoAuth'}),
            ('get', self.preferences_url, None),
            ('patch', self.preferences_url, {'compact_case_cards': True}),
            (
                'post',
                self.change_password_url,
                {
                    'old_password': 'old',
                    'new_password': 'new',
                    'new_password_confirm': 'new',
                    'logout_other_sessions': False,
                },
            ),
            ('post', self.change_password_send_code_url, {}),
            ('post', self.change_password_verify_code_url, {'code': '123456'}),
            ('post', self.logout_url, {'refresh': 'fake-token'}),
            ('post', self.logout_all_url, None),
            ('get', self.sessions_url, None),
            ('delete', f'{self.sessions_url}9999/', None),
        ]

        for method, path, data in protected_calls:
            with self.subTest(method=method, path=path):
                self.assert_auth_required(method, path, data=data)
