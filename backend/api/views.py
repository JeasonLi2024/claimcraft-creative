# -*- coding: utf-8 -*-
"""DRF 视图。"""
import asyncio
import json
import logging
import secrets
import string
import threading
import time
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View
from django_fsm import can_proceed
from datetime import timedelta
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    ListAPIView,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import (
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings as simplejwt_api_settings
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from api.models import (
    AccountAuditLog,
    Case, Evidence, ExtractedField, TimelineNode, CaseStatusLog,
    CaseTypePreset, ComplaintTemplate, ComplaintTemplateRule,
    EmailVerificationChallenge,
    UserPreference,
    UserProfile,
    UserSession,
)
from api.serializers import (
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    ChangePasswordCodeVerifySerializer,
    CaseSerializer,
    CaseListSerializer,
    CaseStatusLogSerializer,
    EmailAddressSerializer,
    EmailChangeConfirmSerializer,
    EmailChangeRequestSerializer,
    EmailCodeWithAddressSerializer,
    EmailCodeVerifySerializer,
    EvidenceSerializer,
    EmailSendCodeSerializer,
    ExportOptionsSerializer,
    ExtractedFieldSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetVerifySerializer,
    TimelineNodeSerializer,
    UserDetailSerializer,
    UserPreferenceSerializer,
    UserProfileUpdateSerializer,
    UserSessionSerializer,
    UserSerializer,
    RegisterSerializer,
    CaseTypePresetSerializer,
)
from api.services.avatar_service import (
    AvatarValidationError,
    delete_user_avatar,
    save_user_avatar,
)
from api.services.mail_service import (
    MailDeliveryError,
    get_mail_delivery_service,
)
from api.services import (
    evidence_service,
    timeline_service,
    complaint_service,
    mask_service,
    export_service,
    image_mask_service,
    pdf_service,
)

logger = logging.getLogger(__name__)
token_backend = TokenBackend(
    algorithm=simplejwt_api_settings.ALGORITHM,
    signing_key=simplejwt_api_settings.SIGNING_KEY,
    verifying_key=simplejwt_api_settings.VERIFYING_KEY,
    audience=simplejwt_api_settings.AUDIENCE,
    issuer=simplejwt_api_settings.ISSUER,
    jwk_url=simplejwt_api_settings.JWK_URL,
    leeway=simplejwt_api_settings.LEEWAY,
)

EMAIL_CODE_DIGITS = string.digits

# 允许的图片扩展名与最大文件大小（10MB）
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
MAX_IMAGE_SIZE = 10 * 1024 * 1024


def _get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _get_user_agent(request):
    return request.META.get('HTTP_USER_AGENT', '')[:1000]


def _detect_device_type(user_agent: str) -> str:
    ua = (user_agent or '').lower()
    if any(token in ua for token in ('iphone', 'android', 'mobile')):
        return 'mobile'
    if any(token in ua for token in ('ipad', 'tablet')):
        return 'tablet'
    if any(token in ua for token in ('windows', 'macintosh', 'linux')):
        return 'desktop'
    if ua:
        return 'web'
    return 'other'


def _build_device_name(user_agent: str) -> str:
    ua = user_agent or ''
    ua_lower = ua.lower()

    platform = 'Unknown'
    if 'windows' in ua_lower:
        platform = 'Windows'
    elif 'macintosh' in ua_lower or 'mac os x' in ua_lower:
        platform = 'macOS'
    elif 'iphone' in ua_lower or 'ios' in ua_lower:
        platform = 'iPhone'
    elif 'ipad' in ua_lower:
        platform = 'iPad'
    elif 'android' in ua_lower:
        platform = 'Android'
    elif 'linux' in ua_lower:
        platform = 'Linux'

    browser = 'Browser'
    if 'edg/' in ua_lower:
        browser = 'Edge'
    elif 'chrome/' in ua_lower and 'edg/' not in ua_lower:
        browser = 'Chrome'
    elif 'firefox/' in ua_lower:
        browser = 'Firefox'
    elif 'safari/' in ua_lower and 'chrome/' not in ua_lower:
        browser = 'Safari'

    return f'{platform} / {browser}'


def _get_refresh_expiry():
    return timezone.now() + settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']


def _get_access_lifetime_seconds():
    return int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())


def _get_refresh_lifetime_seconds():
    return int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())


def _get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={'display_name': user.username},
    )
    return profile


def _get_or_create_preferences(user):
    preferences, _ = UserPreference.objects.get_or_create(user=user)
    return preferences


def _normalize_email(email: str) -> str:
    return (email or '').strip().lower()


def _get_email_code_length() -> int:
    return max(4, settings.CLAIMCRAFT_EMAIL_VERIFICATION_CODE_LENGTH)


def _get_email_code_expiry_minutes() -> int:
    return max(1, settings.CLAIMCRAFT_EMAIL_VERIFICATION_EXPIRES_MINUTES)


def _get_email_code_max_attempts() -> int:
    return max(1, settings.CLAIMCRAFT_EMAIL_VERIFICATION_MAX_ATTEMPTS)


def _get_email_resend_cooldown_seconds() -> int:
    return max(1, settings.CLAIMCRAFT_EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS)


def _get_email_hourly_send_limit() -> int:
    return max(1, settings.CLAIMCRAFT_EMAIL_VERIFICATION_MAX_SENDS_PER_HOUR)


def _generate_email_verification_code() -> str:
    length = _get_email_code_length()
    return ''.join(secrets.choice(EMAIL_CODE_DIGITS) for _ in range(length))


def _get_email_challenge_queryset(user, scene, target_email=None):
    queryset = EmailVerificationChallenge.objects.filter(user=user, scene=scene)
    if target_email is not None:
        queryset = queryset.filter(target_email=_normalize_email(target_email))
    return queryset.order_by('-created_at', '-id')


def _get_latest_email_challenge(user, scene, target_email=None):
    return _get_email_challenge_queryset(user, scene, target_email).first()


def _validate_new_email_for_change(user: User, new_email: str) -> str:
    normalized_email = _normalize_email(new_email)
    if not normalized_email:
        raise ValueError('新邮箱不能为空')
    if normalized_email == _normalize_email(user.email):
        raise ValueError('新邮箱不能与当前邮箱相同')
    if User.objects.filter(email__iexact=normalized_email).exclude(pk=user.pk).exists():
        raise LookupError('该邮箱已被其他账户占用')
    return normalized_email


def _build_email_rate_limit_error(detail: str, *, cooldown_seconds=None, hourly_limit=None):
    payload = {'detail': detail}
    if cooldown_seconds is not None:
        payload['cooldown_seconds'] = cooldown_seconds
    if hourly_limit is not None:
        payload['hourly_limit'] = hourly_limit
    return payload


def _check_email_send_limits(user, scene, target_email=None):
    now = timezone.now()
    hourly_limit = _get_email_hourly_send_limit()
    cooldown_seconds = _get_email_resend_cooldown_seconds()
    recent_since = now - timedelta(hours=1)

    recent_queryset = EmailVerificationChallenge.objects.filter(
        user=user,
        scene=scene,
        created_at__gte=recent_since,
    ).order_by('-created_at', '-id')
    if target_email is not None:
        recent_queryset = recent_queryset.filter(
            target_email=_normalize_email(target_email)
        )

    if recent_queryset.count() >= hourly_limit:
        return _build_email_rate_limit_error(
            '验证码发送过于频繁，请稍后再试',
            hourly_limit=hourly_limit,
        )

    latest = recent_queryset.first()
    if latest is not None:
        delta_seconds = (now - latest.created_at).total_seconds()
        if delta_seconds < cooldown_seconds:
            return _build_email_rate_limit_error(
                '发送过于频繁，请稍后再试',
                cooldown_seconds=int(cooldown_seconds - delta_seconds),
            )
    return None


def _create_and_send_email_challenge(*, user=None, scene, target_email):
    target_email = _normalize_email(target_email)
    rate_limit_payload = _check_email_send_limits(
        user,
        scene,
        target_email=target_email,
    )
    if rate_limit_payload is not None:
        return None, rate_limit_payload

    code = _generate_email_verification_code()
    expires_minutes = _get_email_code_expiry_minutes()
    challenge = EmailVerificationChallenge(
        user=user,
        scene=scene,
        target_email=target_email,
        expires_at=timezone.now() + timedelta(minutes=expires_minutes),
    )
    challenge.set_plain_code(code)
    challenge.save()

    try:
        mail_result = get_mail_delivery_service().send_verification_code(
            to_email=target_email,
            code=code,
            scene=scene,
            expires_minutes=expires_minutes,
        )
    except MailDeliveryError:
        challenge.delete()
        raise

    return challenge, {
        'detail': '验证码发送成功',
        'scene': scene,
        'target_email': target_email,
        'expires_at': challenge.expires_at,
        'provider': mail_result.provider,
    }


def _build_user_detail_response(request):
    return UserDetailSerializer(
        request.user,
        context={'request': request},
    ).data


def _get_verifiable_challenge_or_response(
    *,
    user,
    scene,
    target_email,
    allow_already_verified=False,
):
    challenge = _get_latest_email_challenge(user, scene, target_email)
    if challenge is None:
        return None, Response(
            {'detail': '未找到验证码请求，请先发送验证码'},
            status=status.HTTP_404_NOT_FOUND,
        )
    if challenge.is_used:
        return None, Response(
            {'detail': '验证码已使用，请重新发送'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if allow_already_verified and challenge.is_verified:
        return challenge, None
    if challenge.is_expired:
        return None, Response(
            {'detail': '验证码已过期，请重新发送'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    max_attempts = _get_email_code_max_attempts()
    if challenge.attempt_count >= max_attempts:
        return None, Response(
            {
                'detail': '验证码尝试次数已达上限，请重新发送',
                'max_attempts': max_attempts,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return challenge, None


def _check_email_challenge_code(challenge, submitted_code):
    max_attempts = _get_email_code_max_attempts()
    if challenge.check_plain_code(submitted_code):
        return None

    challenge.mark_attempt()
    remaining_attempts = max(0, max_attempts - challenge.attempt_count)
    if challenge.attempt_count >= max_attempts:
        return Response(
            {
                'detail': '验证码错误次数过多，请重新发送',
                'max_attempts': max_attempts,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {
            'detail': '验证码错误',
            'remaining_attempts': remaining_attempts,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _get_current_session_id(request):
    token = getattr(request, 'auth', None)
    session_id = None
    if token is not None:
        session_id = token.get('session_id')
    if not session_id:
        session_id = request.headers.get('X-Session-ID')
    if not session_id and hasattr(request, 'data'):
        session_id = request.data.get('current_session_id')
    try:
        return int(session_id) if session_id is not None else None
    except (TypeError, ValueError):
        return None


def _blacklist_refresh_by_jti(refresh_jti: str) -> bool:
    if not refresh_jti:
        return False
    try:
        outstanding = OutstandingToken.objects.get(jti=refresh_jti)
    except OutstandingToken.DoesNotExist:
        return False
    BlacklistedToken.objects.get_or_create(token=outstanding)
    return True


def _write_account_audit_log(user, action, request, session=None, metadata=None):
    AccountAuditLog.objects.create(
        user=user,
        session=session,
        action=action,
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
        metadata=metadata or {},
    )


def _get_verified_email_challenge_or_response(*, user, scene, target_email):
    challenge = _get_latest_email_challenge(user, scene, target_email)
    if challenge is None:
        return None, Response(
            {'detail': '未找到验证码请求，请先发送验证码'},
            status=status.HTTP_404_NOT_FOUND,
        )
    if challenge.is_used:
        return None, Response(
            {'detail': '该邮箱验证码已被消费，请重新发送并校验'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not challenge.is_verified:
        return None, Response(
            {'detail': '邮箱验证码尚未校验通过'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return challenge, None


def _get_user_by_email(email: str):
    normalized_email = _normalize_email(email)
    queryset = User.objects.filter(
        email__iexact=normalized_email,
        is_active=True,
    ).order_by('id')
    if queryset.count() != 1:
        return None
    return queryset.first()


def _get_current_email_or_response(user):
    current_email = _normalize_email(user.email)
    if current_email:
        return current_email, None
    return None, Response(
        {'detail': '当前账户未绑定邮箱'},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _revoke_active_sessions(*, user, exclude_session_id=None):
    revoked_count = 0
    active_sessions = UserSession.objects.filter(
        user=user,
        revoked_at__isnull=True,
    )
    if exclude_session_id is not None:
        active_sessions = active_sessions.exclude(id=exclude_session_id)

    for session in active_sessions:
        _blacklist_refresh_by_jti(session.refresh_jti)
        session.revoked_at = timezone.now()
        session.save(update_fields=['revoked_at'])
        revoked_count += 1
    return revoked_count


def _get_login_user_from_account(account: str):
    normalized_account = (account or '').strip()
    if not normalized_account:
        return None

    user = User.objects.filter(
        username=normalized_account,
        is_active=True,
    ).first()
    if user is not None:
        return user
    return _get_user_by_email(normalized_account)


def _build_login_success_payload(request, user):
    _get_or_create_profile(user)
    _get_or_create_preferences(user)

    user_agent = _get_user_agent(request)
    with transaction.atomic():
        refresh = RefreshToken.for_user(user)
        session = UserSession.objects.create(
            user=user,
            refresh_jti=refresh['jti'],
            device_name=_build_device_name(user_agent),
            device_type=_detect_device_type(user_agent),
            ip_address=_get_client_ip(request),
            user_agent=user_agent,
            last_seen_at=timezone.now(),
            expires_at=_get_refresh_expiry(),
        )
        refresh['session_id'] = session.id
        access = refresh.access_token

        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        _write_account_audit_log(
            user=user,
            action=AccountAuditLog.ACTION_LOGIN,
            request=request,
            session=session,
            metadata={'session_id': session.id},
        )

    return {
        'access': str(access),
        'refresh': str(refresh),
        'access_expires_in': _get_access_lifetime_seconds(),
        'refresh_expires_in': _get_refresh_lifetime_seconds(),
        'session_id': session.id,
        'user': UserDetailSerializer(
            user,
            context={'request': request},
        ).data,
    }


# ===== 鉴权视图 =====

class RegisterView(APIView):
    """用户注册：POST /auth/register/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        challenge, error_response = _get_verified_email_challenge_or_response(
            user=None,
            scene=EmailVerificationChallenge.Scene.REGISTER_EMAIL,
            target_email=email,
        )
        if error_response is not None:
            return error_response

        with transaction.atomic():
            user = serializer.save()
            profile = _get_or_create_profile(user)
            if not profile.email_verified:
                profile.email_verified = True
                profile.save(update_fields=['email_verified', 'updated_at'])
            challenge.mark_used()

        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class RegisterSendCodeView(APIView):
    """注册邮箱发码：POST /auth/register/send-code/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {'detail': '该邮箱已被注册'},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            challenge, payload = _create_and_send_email_challenge(
                user=None,
                scene=EmailVerificationChallenge.Scene.REGISTER_EMAIL,
                target_email=email,
            )
        except MailDeliveryError as exc:
            return Response(
                {'detail': f'验证码发送失败：{exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if challenge is None:
            return Response(payload, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response(payload)


class RegisterVerifyCodeView(APIView):
    """注册邮箱验码：POST /auth/register/verify-code/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailCodeWithAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {'detail': '该邮箱已被注册'},
                status=status.HTTP_409_CONFLICT,
            )

        challenge, error_response = _get_verifiable_challenge_or_response(
            user=None,
            scene=EmailVerificationChallenge.Scene.REGISTER_EMAIL,
            target_email=email,
            allow_already_verified=True,
        )
        if error_response is not None:
            return error_response

        if not challenge.is_verified:
            invalid_code_response = _check_email_challenge_code(
                challenge,
                serializer.validated_data['code'],
            )
            if invalid_code_response is not None:
                return invalid_code_response
            challenge.mark_verified()

        return Response(
            {
                'detail': '邮箱验证码校验成功',
                'scene': challenge.scene,
                'target_email': challenge.target_email,
                'verified_at': challenge.verified_at,
            }
        )


class LoginView(APIView):
    """用户登录：POST /auth/login/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        user = _get_login_user_from_account(serializer.validated_data['account'])
        if user is None:
            return Response(
                {'detail': '账号或密码错误'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        authenticated_user = authenticate(
            request=request,
            username=user.username,
            password=serializer.validated_data['password'],
        )
        if authenticated_user is None:
            return Response(
                {'detail': '账号或密码错误'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(_build_login_success_payload(request, authenticated_user))


class LoginSendCodeView(APIView):
    """登录邮箱发码：POST /auth/login/send-code/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        if _get_user_by_email(email) is None:
            return Response(
                {'detail': '该邮箱尚未注册'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            challenge, payload = _create_and_send_email_challenge(
                user=None,
                scene=EmailVerificationChallenge.Scene.LOGIN_EMAIL,
                target_email=email,
            )
        except MailDeliveryError as exc:
            return Response(
                {'detail': f'验证码发送失败：{exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if challenge is None:
            return Response(payload, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response(payload)


class LoginEmailCodeView(APIView):
    """邮箱验证码登录：POST /auth/login/email-code/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailCodeWithAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = _get_user_by_email(email)
        if user is None:
            return Response(
                {'detail': '该邮箱尚未注册'},
                status=status.HTTP_404_NOT_FOUND,
            )

        challenge, error_response = _get_verifiable_challenge_or_response(
            user=None,
            scene=EmailVerificationChallenge.Scene.LOGIN_EMAIL,
            target_email=email,
        )
        if error_response is not None:
            return error_response

        invalid_code_response = _check_email_challenge_code(
            challenge,
            serializer.validated_data['code'],
        )
        if invalid_code_response is not None:
            return invalid_code_response

        with transaction.atomic():
            challenge.mark_used()
            payload = _build_login_success_payload(request, user)
        return Response(payload)


class PasswordResetSendCodeView(APIView):
    """重置密码发码：POST /auth/password-reset/send-code/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        if _get_user_by_email(email) is None:
            return Response(
                {'detail': '该邮箱尚未注册'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            challenge, payload = _create_and_send_email_challenge(
                user=None,
                scene=EmailVerificationChallenge.Scene.RESET_PASSWORD,
                target_email=email,
            )
        except MailDeliveryError as exc:
            return Response(
                {'detail': f'验证码发送失败：{exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if challenge is None:
            return Response(payload, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response(payload)


class PasswordResetVerifyCodeView(APIView):
    """重置密码验码：POST /auth/password-reset/verify-code/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        if _get_user_by_email(email) is None:
            return Response(
                {'detail': '该邮箱尚未注册'},
                status=status.HTTP_404_NOT_FOUND,
            )

        challenge, error_response = _get_verifiable_challenge_or_response(
            user=None,
            scene=EmailVerificationChallenge.Scene.RESET_PASSWORD,
            target_email=email,
            allow_already_verified=True,
        )
        if error_response is not None:
            return error_response

        if not challenge.is_verified:
            invalid_code_response = _check_email_challenge_code(
                challenge,
                serializer.validated_data['code'],
            )
            if invalid_code_response is not None:
                return invalid_code_response
            challenge.mark_verified()

        return Response(
            {
                'detail': '邮箱验证码校验成功',
                'scene': challenge.scene,
                'target_email': challenge.target_email,
                'verified_at': challenge.verified_at,
            }
        )


class PasswordResetConfirmView(APIView):
    """确认重置密码：POST /auth/password-reset/confirm/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = _get_user_by_email(email)
        if user is None:
            return Response(
                {'detail': '该邮箱尚未注册'},
                status=status.HTTP_404_NOT_FOUND,
            )

        challenge, error_response = _get_verified_email_challenge_or_response(
            user=None,
            scene=EmailVerificationChallenge.Scene.RESET_PASSWORD,
            target_email=email,
        )
        if error_response is not None:
            return error_response

        with transaction.atomic():
            user.set_password(serializer.validated_data['new_password'])
            user.save(update_fields=['password'])
            challenge.mark_used()
            revoked_count = _revoke_active_sessions(user=user)

        return Response(
            {
                'detail': '密码重置成功',
                'revoked_sessions': revoked_count,
            }
        )


class RefreshView(APIView):
    """刷新 token：POST /auth/refresh/。"""

    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'refresh': ['该字段是必填项。']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            old_refresh = RefreshToken(refresh_token)
        except TokenError:
            return Response(
                {'detail': 'refresh token 无效'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        old_jti = old_refresh.get('jti')
        session_id = old_refresh.get('session_id')

        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)

        new_refresh_value = payload.get('refresh')
        if new_refresh_value:
            new_refresh = RefreshToken(new_refresh_value)
        else:
            new_refresh = old_refresh

        if session_id is not None:
            new_refresh['session_id'] = session_id

        access = new_refresh.access_token
        payload['access'] = str(access)
        payload['refresh'] = str(new_refresh)
        payload['access_expires_in'] = _get_access_lifetime_seconds()
        payload['refresh_expires_in'] = _get_refresh_lifetime_seconds()
        payload['session_id'] = session_id

        session = None
        if session_id is not None:
            session = UserSession.objects.filter(
                id=session_id,
                user_id=new_refresh.get('user_id'),
            ).first()
        if session is None and old_jti:
            session = UserSession.objects.filter(refresh_jti=old_jti).first()

        if session is not None:
            session.refresh_jti = new_refresh.get('jti')
            session.last_seen_at = timezone.now()
            session.expires_at = _get_refresh_expiry()
            session.revoked_at = None
            session.save(
                update_fields=[
                    'refresh_jti',
                    'last_seen_at',
                    'expires_at',
                    'revoked_at',
                ]
            )

        return Response(payload)


class LogoutView(APIView):
    """退出当前设备：POST /auth/logout/。"""

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'refresh': ['该字段是必填项。']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_token)
        except TokenError:
            try:
                payload = token_backend.decode(refresh_token, verify=True)
            except Exception:
                return Response(
                    {'detail': 'refresh token 无效'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            refresh = payload

        session = None
        session_id = refresh.get('session_id')
        refresh_jti = refresh.get('jti')
        token_user_id = refresh.get('user_id')

        if token_user_id != request.user.id:
            return Response(
                {'detail': '无权操作该 refresh token'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if session_id is not None:
            session = UserSession.objects.filter(
                id=session_id,
                user=request.user,
            ).first()
        if session is None and refresh_jti:
            session = UserSession.objects.filter(
                user=request.user,
                refresh_jti=refresh_jti,
            ).first()

        _blacklist_refresh_by_jti(refresh_jti)

        if session is not None and session.revoked_at is None:
            session.revoked_at = timezone.now()
            session.save(update_fields=['revoked_at'])

        _write_account_audit_log(
            user=request.user,
            action=AccountAuditLog.ACTION_LOGOUT,
            request=request,
            session=session,
            metadata={'session_id': getattr(session, 'id', session_id)},
        )

        return Response({'detail': '已退出当前设备'})


class LogoutAllView(APIView):
    """退出全部设备：POST /auth/logout-all/。"""

    def post(self, request):
        active_sessions = list(
            UserSession.objects.filter(
                user=request.user,
                revoked_at__isnull=True,
            )
        )
        revoked_count = 0

        for outstanding in OutstandingToken.objects.filter(
            user=request.user,
            expires_at__gt=timezone.now(),
        ):
            BlacklistedToken.objects.get_or_create(token=outstanding)

        for session in active_sessions:
            if session.revoked_at is None:
                session.revoked_at = timezone.now()
                session.save(update_fields=['revoked_at'])
                revoked_count += 1

        _write_account_audit_log(
            user=request.user,
            action=AccountAuditLog.ACTION_LOGOUT_ALL,
            request=request,
            metadata={'revoked_sessions': revoked_count},
        )

        return Response(
            {'detail': '已退出全部设备', 'revoked_sessions': revoked_count}
        )


class CurrentUserView(APIView):
    """当前登录用户：GET/PATCH /auth/me/。"""

    def get(self, request):
        _get_or_create_profile(request.user)
        _get_or_create_preferences(request.user)
        return Response(_build_user_detail_response(request))

    def patch(self, request):
        profile = _get_or_create_profile(request.user)
        serializer = UserProfileUpdateSerializer(
            profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(_build_user_detail_response(request))


class UserPreferenceView(APIView):
    """账户偏好：GET/PATCH /auth/me/preferences/。"""

    def get(self, request):
        preferences = _get_or_create_preferences(request.user)
        return Response(UserPreferenceSerializer(preferences).data)

    def patch(self, request):
        preferences = _get_or_create_preferences(request.user)
        serializer = UserPreferenceSerializer(
            preferences,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ChangePasswordSendCodeView(APIView):
    """修改密码发码：POST /auth/change-password/send-code/。"""

    def post(self, request):
        serializer = EmailSendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        current_email, error_response = _get_current_email_or_response(request.user)
        if error_response is not None:
            return error_response

        try:
            challenge, payload = _create_and_send_email_challenge(
                user=request.user,
                scene=EmailVerificationChallenge.Scene.CHANGE_PASSWORD_EMAIL,
                target_email=current_email,
            )
        except MailDeliveryError as exc:
            return Response(
                {'detail': f'验证码发送失败：{exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if challenge is None:
            return Response(payload, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response(payload)


class ChangePasswordVerifyCodeView(APIView):
    """修改密码验码：POST /auth/change-password/verify-code/。"""

    def post(self, request):
        serializer = ChangePasswordCodeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        current_email, error_response = _get_current_email_or_response(request.user)
        if error_response is not None:
            return error_response

        challenge, error_response = _get_verifiable_challenge_or_response(
            user=request.user,
            scene=EmailVerificationChallenge.Scene.CHANGE_PASSWORD_EMAIL,
            target_email=current_email,
            allow_already_verified=True,
        )
        if error_response is not None:
            return error_response

        if not challenge.is_verified:
            invalid_code_response = _check_email_challenge_code(
                challenge,
                serializer.validated_data['code'],
            )
            if invalid_code_response is not None:
                return invalid_code_response
            challenge.mark_verified()

        return Response(
            {
                'detail': '邮箱验证码校验成功',
                'scene': challenge.scene,
                'target_email': challenge.target_email,
                'verified_at': challenge.verified_at,
            }
        )


class ChangePasswordView(APIView):
    """修改密码：POST /auth/change-password/。"""

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request, 'user': request.user},
        )
        serializer.is_valid(raise_exception=True)

        current_email, error_response = _get_current_email_or_response(request.user)
        if error_response is not None:
            return error_response

        challenge, error_response = _get_verified_email_challenge_or_response(
            user=request.user,
            scene=EmailVerificationChallenge.Scene.CHANGE_PASSWORD_EMAIL,
            target_email=current_email,
        )
        if error_response is not None:
            return error_response

        current_session_id = _get_current_session_id(request)
        current_session = None
        if current_session_id is not None:
            current_session = UserSession.objects.filter(
                id=current_session_id,
                user=request.user,
            ).first()

        with transaction.atomic():
            request.user.set_password(serializer.validated_data['new_password'])
            request.user.save(update_fields=['password'])
            challenge.mark_used()

            revoked_count = 0
            if serializer.validated_data.get('logout_other_sessions'):
                revoked_count = _revoke_active_sessions(
                    user=request.user,
                    exclude_session_id=current_session_id,
                )

            _write_account_audit_log(
                user=request.user,
                action=AccountAuditLog.ACTION_CHANGE_PASSWORD,
                request=request,
                session=current_session,
                metadata={
                    'logout_other_sessions': serializer.validated_data.get(
                        'logout_other_sessions', False
                    ),
                    'revoked_other_sessions': revoked_count,
                    'challenge_id': challenge.id,
                },
            )

        return Response(
            {
                'detail': '密码修改成功',
                'revoked_other_sessions': revoked_count,
            }
        )


class UserSessionListView(APIView):
    """会话列表：GET /auth/sessions/。"""

    def get(self, request):
        current_session_id = _get_current_session_id(request)
        recent_threshold = timezone.now() - timedelta(days=30)
        sessions = UserSession.objects.filter(user=request.user).filter(
            Q(revoked_at__isnull=True) | Q(last_seen_at__gte=recent_threshold)
        )
        serializer = UserSessionSerializer(
            sessions,
            many=True,
            context={'current_session_id': current_session_id},
        )
        return Response(serializer.data)


class UserSessionDetailView(APIView):
    """撤销单个会话：DELETE /auth/sessions/<id>/。"""

    def delete(self, request, session_id):
        session = get_object_or_404(
            UserSession,
            id=session_id,
            user=request.user,
        )

        _blacklist_refresh_by_jti(session.refresh_jti)
        if session.revoked_at is None:
            session.revoked_at = timezone.now()
            session.save(update_fields=['revoked_at'])

        _write_account_audit_log(
            user=request.user,
            action=AccountAuditLog.ACTION_REVOKE_SESSION,
            request=request,
            session=session,
            metadata={'session_id': session.id},
        )

        return Response({'detail': '会话已撤销', 'session_id': session.id})


class CurrentUserAvatarView(APIView):
    """头像上传/删除：POST/DELETE /auth/me/avatar/。"""

    def post(self, request):
        profile = _get_or_create_profile(request.user)
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            save_user_avatar(profile, serializer.validated_data['avatar'])
        except AvatarValidationError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'detail': '头像上传成功',
                'user': _build_user_detail_response(request),
            }
        )

    def delete(self, request):
        profile = _get_or_create_profile(request.user)
        delete_user_avatar(profile)
        return Response(
            {
                'detail': '头像已删除',
                'user': _build_user_detail_response(request),
            }
        )


class CurrentEmailSendCodeView(APIView):
    """当前邮箱发送验证码：POST /auth/me/email/send-code/。"""

    def post(self, request):
        serializer = EmailSendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        current_email, error_response = _get_current_email_or_response(request.user)
        if error_response is not None:
            return error_response

        try:
            challenge, payload = _create_and_send_email_challenge(
                user=request.user,
                scene=EmailVerificationChallenge.Scene.VERIFY_CURRENT_EMAIL,
                target_email=current_email,
            )
        except MailDeliveryError as exc:
            return Response(
                {'detail': f'验证码发送失败：{exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if challenge is None:
            return Response(payload, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response(payload)


class CurrentEmailVerifyView(APIView):
    """校验当前邮箱验证码：POST /auth/me/email/verify/。"""

    def post(self, request):
        serializer = EmailCodeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        current_email, error_response = _get_current_email_or_response(request.user)
        if error_response is not None:
            return error_response

        challenge, error_response = _get_verifiable_challenge_or_response(
            user=request.user,
            scene=EmailVerificationChallenge.Scene.VERIFY_CURRENT_EMAIL,
            target_email=current_email,
        )
        if error_response is not None:
            return error_response

        invalid_code_response = _check_email_challenge_code(
            challenge,
            serializer.validated_data['code'],
        )
        if invalid_code_response is not None:
            return invalid_code_response

        with transaction.atomic():
            challenge.mark_used()
            profile = _get_or_create_profile(request.user)
            if not profile.email_verified:
                profile.email_verified = True
                profile.save(update_fields=['email_verified', 'updated_at'])

        return Response(
            {
                'detail': '邮箱验证成功',
                'user': _build_user_detail_response(request),
            }
        )


class EmailChangeRequestView(APIView):
    """新邮箱发送验证码：POST /auth/me/email/change/request/。"""

    def post(self, request):
        serializer = EmailChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            new_email = _validate_new_email_for_change(
                request.user,
                serializer.validated_data['new_email'],
            )
        except ValueError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except LookupError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            challenge, payload = _create_and_send_email_challenge(
                user=request.user,
                scene=EmailVerificationChallenge.Scene.CHANGE_EMAIL,
                target_email=new_email,
            )
        except MailDeliveryError as exc:
            return Response(
                {'detail': f'验证码发送失败：{exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if challenge is None:
            return Response(payload, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response(payload)


class EmailChangeConfirmView(APIView):
    """确认新邮箱变更：POST /auth/me/email/change/confirm/。"""

    def post(self, request):
        serializer = EmailChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            new_email = _validate_new_email_for_change(
                request.user,
                serializer.validated_data['new_email'],
            )
        except ValueError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except LookupError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        challenge, error_response = _get_verifiable_challenge_or_response(
            user=request.user,
            scene=EmailVerificationChallenge.Scene.CHANGE_EMAIL,
            target_email=new_email,
        )
        if error_response is not None:
            return error_response

        invalid_code_response = _check_email_challenge_code(
            challenge,
            serializer.validated_data['code'],
        )
        if invalid_code_response is not None:
            return invalid_code_response

        with transaction.atomic():
            challenge.mark_used()
            request.user.email = new_email
            request.user.save(update_fields=['email'])
            profile = _get_or_create_profile(request.user)
            if not profile.email_verified:
                profile.email_verified = True
                profile.save(update_fields=['email_verified', 'updated_at'])

        return Response(
            {
                'detail': '邮箱修改成功',
                'user': _build_user_detail_response(request),
            }
        )


# ===== 案件视图 =====

class CaseDetailView(APIView):
    """案件详情：GET /cases/<id>/ 返回案件详情含统计。"""

    def get(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        serializer = CaseSerializer(case)
        return Response(serializer.data)


class CaseListCreateView(ListCreateAPIView):
    """案件列表与创建：GET/POST /cases/。

    GET 支持 ?search=&status=&case_type=，返回 CaseListSerializer 列表。
    POST 创建案件，status 由模型默认值决定为 draft。
    """

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CaseSerializer
        return CaseListSerializer

    def get_queryset(self):
        qs = Case.objects.filter(owner=self.request.user)
        params = self.request.query_params
        search = params.get('search')
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        status_filter = params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        case_type = params.get('case_type')
        if case_type:
            qs = qs.filter(case_type=case_type)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class CaseUpdateDeleteView(RetrieveUpdateDestroyAPIView):
    """案件更新与删除：GET/PATCH/PUT/DELETE /cases/<id>/manage/。

    PATCH 仅更新 title/description/case_type（status 为只读，
    通过状态转换接口变更）。
    """

    serializer_class = CaseSerializer

    def get_queryset(self):
        return Case.objects.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        if instance.is_demo:
            raise ValidationError({'detail': '示例案件不可删除'})
        return super().perform_destroy(instance)


# ===== 证据视图 =====

class EvidenceListCreateView(APIView):
    """证据列表与新增：GET/POST /cases/<id>/evidences/。"""

    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        evidences = case.evidences.all().order_by('order', 'id')
        serializer = EvidenceSerializer(evidences, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        # 自动编号
        if 'code' not in data or not data.get('code'):
            data['code'] = evidence_service.generate_next_evidence_code(case)

        # order 设为当前最大 + 1
        max_order = case.evidences.aggregate(m=Max('order'))['m'] or 0
        if 'order' not in data or data.get('order') in (None, ''):
            data['order'] = max_order + 1

        serializer = EvidenceSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            serializer.save(case=case)
            from api.services.case_lifecycle_service import mark_document_stale
            mark_document_stale(case.id)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EvidenceUploadView(APIView):
    """证据图片上传：POST /cases/<id>/evidences/upload/。

    接收 multipart 文件（key: image），校验格式与大小，
    生成证据编号，保存图片，执行 OCR + 字段抽取，返回序列化结果。
    """

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        image_file = request.FILES.get('image')
        if not image_file:
            return Response({'detail': '未上传图片（key: image）'}, status=status.HTTP_400_BAD_REQUEST)

        # 校验扩展名
        name = image_file.name.lower()
        ext = name.rsplit('.', 1)[-1] if '.' in name else ''
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return Response(
                {'detail': f'不支持的图片格式：{ext}，仅支持 {sorted(ALLOWED_IMAGE_EXTENSIONS)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 校验大小
        if image_file.size > MAX_IMAGE_SIZE:
            return Response(
                {'detail': '图片大小超过 10MB 限制'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 自动编号与 order
        code = evidence_service.generate_next_evidence_code(case)
        max_order = case.evidences.aggregate(m=Max('order'))['m'] or 0

        # 取表单附加字段（可选）
        data = request.data
        evidence_type = data.get('evidence_type', '上传图片')
        description = data.get('description', f'{image_file.name} OCR 上传')
        source_time = data.get('source_time') or timezone.now()
        has_sensitive_info = (
            str(data.get('has_sensitive_info', 'false')).strip().lower()
            in {'1', 'true', 'yes', 'on'}
        )
        # 纯物证图片标记（multipart 表单值为字符串）
        is_physical_evidence = str(data.get('is_physical_evidence', 'false')).lower() == 'true'
        physical_note = (data.get('physical_note') or '').strip()[:500]

        evidence = Evidence.objects.create(
            case=case,
            code=code,
            evidence_type=evidence_type,
            description=description,
            source_time=source_time,
            has_sensitive_info=has_sensitive_info,
            order=max_order + 1,
            image=image_file,
            # 物证无需识别，直接 done；其余保持 pending，由工作流统一 OCR + LLM 抽取
            ocr_status='done' if is_physical_evidence else 'pending',
            is_physical_evidence=is_physical_evidence,
            physical_note=physical_note,
        )

        # 上传阶段不再同步执行 OCR / 字段抽取：
        #   1) 正则抽取准确率约 60%，容易给用户错误预期；
        #   2) PaddleOCR-VL + LLM 调用阻塞 5-10s，严重影响上传体验；
        #   3) 工作流（LangGraph 6 节点）会重新做更准确的语义抽取，是唯一权威源。
        # 物证图片天然不需要识别。

        from api.services.case_lifecycle_service import mark_document_stale
        mark_document_stale(case.id)
        serializer = EvidenceSerializer(evidence, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EvidenceDeleteView(APIView):
    """证据删除：DELETE /evidences/<id>/。

    删除证据时同步清理时间线节点引用：
    - 删除引用该证据编号的 auto_generated 节点；
    - 从手动节点的 related_evidence_codes 中移除该证据编号，
      若手动节点清空后无任何引用，也一并删除（避免悬空节点）。
    """

    def delete(self, request, pk):
        evidence = get_object_or_404(
            Evidence, pk=pk, case__owner=request.user
        )

        # 示例案件的已有证据禁止删除
        if evidence.case.is_demo:
            return Response(
                {'detail': '示例案件的证据不可删除'},
                status=status.HTTP_403_FORBIDDEN,
            )

        code = evidence.code
        case = evidence.case
        evidence.delete()
        from api.services.case_lifecycle_service import mark_document_stale
        mark_document_stale(case.id)

        # 清理时间线节点引用
        if code:
            # 1. 删除引用该证据编号的自动节点
            case.timeline_nodes.filter(
                auto_generated=True, related_evidence_codes=code
            ).delete()
            # 2. 清理手动节点中 related_evidence_codes 包含该编号的节点
            for node in case.timeline_nodes.filter(auto_generated=False):
                codes = [c.strip() for c in (node.related_evidence_codes or '').split(',') if c.strip()]
                if code in codes:
                    codes = [c for c in codes if c != code]
                    node.related_evidence_codes = ','.join(codes)
                    node.save(update_fields=['related_evidence_codes'])

        return Response({'detail': '已删除'}, status=status.HTTP_204_NO_CONTENT)


# ===== 抽取字段视图 =====

class ExtractedFieldListView(APIView):
    """抽取字段列表：GET /evidences/<id>/extracted-fields/。"""

    def get(self, request, evidence_id):
        evidence = get_object_or_404(
            Evidence, pk=evidence_id, case__owner=request.user
        )
        fields = evidence.extracted_fields.all()
        serializer = ExtractedFieldSerializer(fields, many=True)
        return Response(serializer.data)


class ExtractedFieldUpdateView(APIView):
    """抽取字段更新：PATCH /extracted-fields/<pk>/ 更新 field_value。"""

    def patch(self, request, pk):
        field = get_object_or_404(
            ExtractedField, pk=pk, evidence__case__owner=request.user
        )

        data = request.data
        if 'field_value' in data:
            field.field_value = data['field_value']
        if 'field_name' in data:
            field.field_name = data['field_name']
        if 'confidence' in data:
            field.confidence = data['confidence']
        field.save()
        from api.services.case_lifecycle_service import mark_document_stale
        mark_document_stale(field.evidence.case_id)
        serializer = ExtractedFieldSerializer(field)
        return Response(serializer.data)

    def put(self, request, pk):
        return self.patch(request, pk)


# ===== 时间线视图 =====

class TimelineListView(APIView):
    """时间线列表：GET /cases/<id>/timeline/ 返回排序后的时间线。"""

    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        nodes = timeline_service.get_sorted_timeline(case)
        serializer = TimelineNodeSerializer(nodes, many=True)
        return Response(serializer.data)


class TimelineRebuildView(APIView):
    """时间线重建：POST /cases/<id>/timeline/rebuild/。"""

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        nodes = timeline_service.rebuild_timeline(case)
        from api.services.case_lifecycle_service import mark_document_stale
        mark_document_stale(case.id)
        serializer = TimelineNodeSerializer(nodes, many=True)
        return Response(serializer.data)


class TimelineNodeUpdateView(APIView):
    """时间线节点更新：PATCH /timeline-nodes/<id>/ 更新 event 字段。"""

    def patch(self, request, pk):
        node = get_object_or_404(
            TimelineNode, pk=pk, case__owner=request.user
        )

        data = request.data
        if 'event' in data:
            node.event = data['event']
        # 允许顺带更新其它字段
        for field in ['datetime', 'related_evidence_codes', 'order']:
            if field in data:
                setattr(node, field, data[field])
        node.save()
        from api.services.case_lifecycle_service import mark_document_stale
        mark_document_stale(node.case_id)
        serializer = TimelineNodeSerializer(node)
        return Response(serializer.data)

    # 兼容 PUT
    def put(self, request, pk):
        return self.patch(request, pk)


# ===== 投诉视图 =====

class ComplaintView(APIView):
    """投诉文本：GET /cases/<id>/complaints/?template_type=<type>。

    返回 {title, content, template_type, tone}。
    tone 从 ComplaintTemplate 表读取（工作流生成时存储），无则不返回。
    """

    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        template_type = request.query_params.get('template_type', 'platform')
        saved = ComplaintTemplate.objects.filter(case=case, template_type=template_type).order_by("-id").first()
        result = ({"title": saved.title, "content": saved.content, "template_type": template_type, "tone": saved.tone} if saved else complaint_service.generate_complaint(case, template_type))
        if result is None:
            return Response(
                {'detail': f'未找到模板类型：{template_type}'},
                status=status.HTTP_404_NOT_FOUND
            )
        # 补充 tone（从 ComplaintTemplate 读取）
        try:
            tmpl = ComplaintTemplate.objects.get(case=case, template_type=template_type)
            result['tone'] = tmpl.tone if hasattr(tmpl, 'tone') else ''
        except ComplaintTemplate.DoesNotExist:
            pass
        return Response(result)


class ComplaintRegenerateView(APIView):
    """投诉文本重新生成：POST /cases/<id>/complaints/regenerate/。

    接收 {template_type, tone?}，返回 {title, content, template_type}。
    tone 可选，指定后会存储到 ComplaintTemplate 记录中。
    """

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        template_type = request.data.get('template_type', 'platform')
        tone = request.data.get('tone', '')

        result = complaint_service.generate_complaint(case, template_type)
        if result is None:
            return Response(
                {'detail': f'未找到模板类型：{template_type}'},
                status=status.HTTP_404_NOT_FOUND
            )
        # 如果指定了 tone，更新 ComplaintTemplate 记录
        if tone:
            try:
                tmpl = ComplaintTemplate.objects.get(case=case, template_type=template_type)
                if hasattr(tmpl, 'tone'):
                    tmpl.tone = tone
                    tmpl.save(update_fields=['tone'])
            except ComplaintTemplate.DoesNotExist:
                pass
            result['tone'] = tone
        return Response(result)


class RespondTemplateView(APIView):
    """反证答辩书：GET /cases/<id>/respond-templates/?template_type=<type>。

    优先从 RespondTemplate 表读取工作流产物，无则回退投诉模板预览。
    """

    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        template_type = request.query_params.get('template_type', 'platform')
        result = complaint_service.generate_respond_complaint(case, template_type)
        if result is None:
            return Response(
                {'detail': f'未找到答辩模板类型：{template_type}'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(result)


class RespondTemplateRegenerateView(APIView):
    """反证答辩书重新生成：POST /cases/<id>/respond-templates/regenerate/。

    接收 {template_type}，返回 {title, content, template_type}。
    注意：实际 LLM 重写需通过工作流触发，此接口仅重新渲染 Jinja2 模板。
    """

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        template_type = request.data.get('template_type', 'platform')
        result = complaint_service.generate_respond_complaint(case, template_type)
        if result is None:
            return Response(
                {'detail': f'未找到答辩模板类型：{template_type}'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(result)


# ===== 打码视图 =====

class MaskView(APIView):
    """敏感信息打码：GET/POST /cases/<id>/mask/。

    GET：获取当前打码结果（实时计算，不修改数据库）。
    POST：同 GET，保持兼容。
    """

    def get(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        result = mask_service.mask_case_sensitive_info(case)
        return Response({
            'case_id': case.id,
            'count': len(result),
            'items': result,
        })

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)

        result = mask_service.mask_case_sensitive_info(case)
        return Response({
            'case_id': case.id,
            'count': len(result),
            'items': result,
        })


# ===== 导出视图 =====

class ExportView(APIView):
    """导出文本：POST /cases/<id>/export/ 接收 {template_type, masked}。"""

    def post(self, request, case_id):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        options = ExportOptionsSerializer(data=request.data)
        options.is_valid(raise_exception=True)
        template_type = options.validated_data['template_type']
        masked = options.validated_data['masked']

        try:
            content = export_service.generate_export_text(
                case, template_type=template_type, masked=masked
            )
        except Exception:
            logger.exception('文本导出失败 (case=%s, template=%s)', case.id, template_type)
            return Response(
                {'detail': '文本导出失败，请稍后重试'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        filename = f'claimcraft_case_{case.id}_{template_type}.txt'
        return Response({'filename': filename, 'content': content})


# ===== T1 新增视图 =====

# to_status -> 转换方法名（cancelled 除外，需按当前状态二选一）
_STATUS_TRANSITION_METHODS = {
    'processing': 'to_processing',
    'submitted': 'to_submitted',
    'closed': 'to_closed',
}


class CaseStatusTransitionView(APIView):
    """兼容管理端的状态纠正接口；普通用户不得直接选择案件状态。"""

    def post(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {'detail': '案件状态由系统流程维护，请使用归档或取消操作'},
                status=status.HTTP_403_FORBIDDEN,
            )
        case = get_object_or_404(Case, pk=pk)

        to_status = request.data.get('to_status')
        remark = request.data.get('remark', '')

        if not to_status:
            return Response(
                {'detail': '缺少 to_status'}, status=status.HTTP_400_BAD_REQUEST
            )

        # cancelled 需按当前状态选择对应取消方法
        if to_status == 'cancelled':
            if case.status == 'draft':
                method_name = 'cancel_from_draft'
            elif case.status == 'processing':
                method_name = 'cancel_from_processing'
            else:
                return Response(
                    {'detail': f'当前状态 {case.status} 不可取消'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            method_name = _STATUS_TRANSITION_METHODS.get(to_status)
            if not method_name:
                return Response(
                    {'detail': f'非法的目标状态：{to_status}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        method = getattr(case, method_name)
        if not can_proceed(method):
            return Response(
                {'detail': f'当前状态 {case.status} 不允许转换至 {to_status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = case.status
        method()
        case.save()
        CaseStatusLog.objects.create(
            case=case,
            from_status=old_status,
            to_status=to_status,
            remark=remark,
            trigger='admin_override',
            actor=request.user,
        )
        return Response({
            'id': case.id,
            'from_status': old_status,
            'to_status': to_status,
            'status': case.status,
        })


class CaseArchiveView(APIView):
    """用户确认材料无误后归档案件。"""

    def post(self, request, pk):
        from api.services.case_lifecycle_service import LifecycleError, archive_case

        get_object_or_404(Case, pk=pk, owner=request.user)
        try:
            result = archive_case(pk, actor=request.user)
        except LifecycleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(CaseSerializer(result.case).data)


class CaseCancelView(APIView):
    """用户取消尚未提交或归档的案件。"""

    def post(self, request, pk):
        from api.services.case_lifecycle_service import LifecycleError, cancel_case

        get_object_or_404(Case, pk=pk, owner=request.user)
        try:
            result = cancel_case(
                pk, actor=request.user, reason=str(request.data.get('reason', '')).strip()
            )
        except LifecycleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(CaseSerializer(result.case).data)


class CaseStatusLogView(ListAPIView):
    """案件状态日志：GET /cases/<id>/status-logs/。"""

    serializer_class = CaseStatusLogSerializer

    def get_queryset(self):
        return CaseStatusLog.objects.filter(
            case_id=self.kwargs['pk'], case__owner=self.request.user
        )


class MaskImageView(APIView):
    """证据图片打码：POST /cases/<id>/mask-images/。

    对该案件所有图片证据执行打码，返回打码后证据列表。
    """

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        results = image_mask_service.mask_case_images(case)
        serializer = EvidenceSerializer(
            results, many=True, context={'request': request}
        )
        return Response({
            'case_id': case.id,
            'count': len(results),
            'items': serializer.data,
        })


def _download_response(payload, filename, content_type):
    """构造适合公网反向代理和浏览器下载的二进制响应。"""
    ascii_fallback = ''.join(
        char if char.isascii() and (char.isalnum() or char in '._-') else '_'
        for char in filename
    )
    response = HttpResponse(payload, content_type=content_type)
    response['Content-Disposition'] = (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    response['X-Export-Filename'] = quote(filename)
    response['Content-Length'] = len(payload)
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['Pragma'] = 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


class ExportPackageView(APIView):
    """证据包导出：GET /cases/<id>/export/package/?template_type=<type> 返回 ZIP 文件流。"""

    def get(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        options = ExportOptionsSerializer(data=request.query_params)
        options.is_valid(raise_exception=True)
        template_type = options.validated_data['template_type']
        try:
            buf = export_service.export_evidence_package(
                case, template_type=template_type
            )
            payload = buf.getvalue()
            buf.close()
        except Exception:
            logger.exception('ZIP 导出失败 (case=%s, template=%s)', case.id, template_type)
            return Response(
                {'detail': '证据包生成失败，请检查案件材料后重试'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        filename = f'case_{case.id}_{template_type}_package.zip'
        return _download_response(payload, filename, 'application/zip')


class ExportPDFView(APIView):
    """PDF 投诉材料导出：GET /cases/<id>/export/pdf/?template_type=<type>。"""

    def get(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        options = ExportOptionsSerializer(data=request.query_params)
        options.is_valid(raise_exception=True)
        template_type = options.validated_data['template_type']
        try:
            buf = pdf_service.generate_complaint_pdf(
                case, template_type=template_type
            )
            payload = buf.getvalue()
            buf.close()
        except Exception:
            logger.exception('PDF 导出失败 (case=%s, template=%s)', case.id, template_type)
            return Response(
                {'detail': 'PDF 生成失败，请检查案件材料后重试'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        filename = f'case_{case.id}_{template_type}.pdf'
        return _download_response(payload, filename, 'application/pdf')


class ExportWordView(APIView):
    """Word 正式文书导出：GET /cases/<id>/export/word/?template_type=<type>。"""

    def get(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        options = ExportOptionsSerializer(data=request.query_params)
        options.is_valid(raise_exception=True)
        template_type = options.validated_data['template_type']
        try:
            buf = pdf_service.generate_word_document(case, template_type=template_type)
            payload = buf.getvalue()
            buf.close()
        except Exception:
            logger.exception('Word 导出失败 (case=%s, template=%s)', case.id, template_type)
            return Response(
                {'detail': 'Word 生成失败，请检查案件材料或服务器 Pandoc 环境后重试'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        filename = f'case_{case.id}_{template_type}.docx'
        return _download_response(
            payload,
            filename,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )


# ===== Task 27：案件模板预设 =====

class CaseTypePresetListView(APIView):
    """案件类型预设列表：GET /case-presets/?case_type=<type>。

    返回所有预设，支持按 case_type 过滤。预设为全局共享，所有登录用户可见。
    """

    def get(self, request):
        qs = CaseTypePreset.objects.all()
        case_type = request.query_params.get('case_type')
        if case_type:
            qs = qs.filter(case_type=case_type)
        serializer = CaseTypePresetSerializer(qs, many=True)
        return Response(serializer.data)


class ApplyPresetView(APIView):
    """套用预设到案件：POST /cases/<id>/apply-preset/。

    接收 {preset_id}，根据预设创建：
    - 证据骨架（仅类型，无图片，描述占位"（待填写）"）
    - 时间线骨架（datetime 可为空，待用户后续补充）
    - 投诉模板规则（platform 类型，update_or_create）
    """

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        preset_id = request.data.get('preset_id')
        preset = get_object_or_404(CaseTypePreset, pk=preset_id)

        # 创建证据骨架（仅类型，无图片）
        created_evidences = []
        for i, ev_type in enumerate(preset.evidence_types):
            code = evidence_service.generate_next_evidence_code(case)
            ev = Evidence.objects.create(
                case=case,
                code=code,
                evidence_type=ev_type,
                description='（待填写）',
                source_time=timezone.now(),
                order=i,
            )
            created_evidences.append(ev)

        # 创建时间线骨架（datetime 可为 None）
        for i, node_data in enumerate(preset.timeline_skeleton):
            TimelineNode.objects.create(
                case=case,
                datetime=node_data.get('datetime'),
                event=node_data.get('event', ''),
                related_evidence_codes=node_data.get('related_evidence_codes', ''),
                order=i,
                auto_generated=False,
            )

        # 创建/更新投诉模板规则（platform 类型）
        if preset.complaint_template:
            ComplaintTemplateRule.objects.update_or_create(
                case=case,
                template_type='platform',
                defaults={
                    'rule_title': preset.name,
                    'rule_content': preset.complaint_template,
                }
            )

        return Response({
            'message': '预设套用成功',
            'evidences_created': len(created_evidences),
            'timeline_created': len(preset.timeline_skeleton),
            'complaint_template': bool(preset.complaint_template),
        })


# ===== Task 28：数据统计仪表盘 =====

class StatsView(APIView):
    """聚合统计：GET /stats/dashboard/ 按当前用户过滤。

    返回：案件类型分布、状态分布、证据总数、抽取字段总数、
    最近 30 天每日新建案件数、状态转换统计、案件总数。
    """

    def get(self, request):
        user_cases = Case.objects.filter(owner=request.user)

        # 案件类型分布
        case_type_dist = list(
            user_cases.values('case_type').annotate(count=Count('id')).order_by('case_type')
        )

        # 案件状态分布
        status_dist = list(
            user_cases.values('status').annotate(count=Count('id')).order_by('status')
        )

        # 证据总数
        evidence_total = Evidence.objects.filter(case__in=user_cases).count()

        # 抽取字段总数
        extracted_field_total = ExtractedField.objects.filter(
            evidence__case__in=user_cases
        ).count()

        # 最近 30 天每日新建案件数（TruncDate 跨数据库兼容）
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        recent_cases = list(
            user_cases.filter(created_at__gte=thirty_days_ago)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
        )

        # 状态转换统计（从 CaseStatusLog 聚合）
        status_transitions = list(
            CaseStatusLog.objects.filter(case__in=user_cases)
            .values('to_status')
            .annotate(count=Count('id'))
            .order_by('to_status')
        )

        return Response({
            'case_type_distribution': case_type_dist,
            'status_distribution': status_dist,
            'evidence_total': evidence_total,
            'extracted_field_total': extracted_field_total,
            'cases_recent_30days': recent_cases,
            'status_transitions': status_transitions,
            'case_total': user_cases.count(),
        })


# ===== B10：案件工作流（LangGraph 智能体）=====

class CaseWorkflowView(APIView):
    """案件工作流：POST /api/cases/<id>/run-workflow/

    @deprecated（2026-07-07 SSE 改造）：本端点同步阻塞 ainvoke 返回全部产物，
    保留 1 个版本便于回滚。新前端请改用：
        - POST /api/cases/<id>/workflow/start/   （启动后台任务）
        - GET  /api/cases/<id>/workflow/stream/  （SSE 流式推送）
        - POST /api/cases/<id>/workflow/resume/  （HITL 校正提交）

    基于 LangGraph StateGraph 构建 6 节点工作流（多证据聚合版）：
    OCR → 证据分类 → 字段抽取 → (HITL 校正?) → 证据链构造 → 投诉生成

    Body:
        evidence_ids: list[int] (可选，指定多个证据；不传则处理案件全部有图证据)
        resume: dict (可选，HITL 恢复时传入人工校正结果)

    响应：
        - 首次启动 + 无低置信度字段：status="completed"，含 complaint_draft
        - 首次启动 + 有低置信度字段：status="interrupted"，含 interrupt_data
        - HITL 恢复：status="completed"，含 complaint_draft
    """

    def post(self, request, pk):
        from asgiref.sync import async_to_sync
        from langgraph.types import Command
        from api.agents import build_case_workflow
        from api.services.langsmith_service import trace_for_case

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        evidence_ids = request.data.get('evidence_ids', [])
        resume_value = request.data.get('resume')

        # 1. 新运行使用新 thread；HITL 恢复复用现有 thread
        if resume_value is None:
            thread_id = f"case-{case.id}-{time.time_ns()}"
            case.thread_id = thread_id
            case.save(update_fields=['thread_id'])
        else:
            thread_id = case.thread_id
            if not thread_id:
                return Response(
                    {'detail': '案件尚未启动工作流'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        from api.services.case_lifecycle_service import (
            LifecycleError, resume_processing, start_processing,
        )
        try:
            if resume_value is None:
                start_processing(case.id, actor=request.user, thread_id=thread_id)
            else:
                resume_processing(case.id)
        except LifecycleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        # 2. 单例 workflow（不再每次重新编译）
        workflow = build_case_workflow()
        config = {"configurable": {"thread_id": thread_id}}

        # 3. 探测敏感证据（LangSmith 条件追踪：敏感证据 enabled=False 零数据保留）
        has_sensitive = case.evidences.filter(has_sensitive_info=True).exists()

        try:
            # 按 case 注入 LangSmith 追踪上下文（metadata + tags + project 路由）
            with trace_for_case(
                case_id=case.id,
                owner_id=request.user.id,
                case_type=case.case_type,
                has_sensitive=has_sensitive,
            ):
                # async 节点必须用 ainvoke；checkpointer 已包装支持 async 接口
                if resume_value is not None:
                    # HITL 恢复
                    result = async_to_sync(workflow.ainvoke)(Command(resume=resume_value), config)
                else:
                    # 首次启动
                    initial_state = {
                        "case_id": case.id,
                        "evidence_ids": evidence_ids,
                        "evidence_preclassify_results": [],
                        "evidence_ocr_results": [],
                        "evidence_classify_results": [],
                        "evidence_extract_results": [],
                        "needs_human_review": False,
                        "evidence_chain": [],
                        "complaint_draft": None,
                        "review_decision": None,
                        "errors": [],
                    }
                    result = async_to_sync(workflow.ainvoke)(initial_state, config)
        except Exception as e:
            from api.services.case_lifecycle_service import fail_processing
            fail_processing(case.id, str(e))
            logger.error(f"案件 {case.id} 工作流执行失败: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "case_id": case.id,
                    "thread_id": thread_id,
                    "error": f"工作流执行失败: {e}",
                    "errors": [str(e)],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 检查是否在 interrupt 处暂停
        interrupted = "__interrupt__" in result

        # 序列化 interrupt_data（Interrupt 对象不可直接 JSON 序列化）
        interrupt_data = None
        if interrupted:
            try:
                interrupts = result.get("__interrupt__", [])
                if interrupts:
                    interrupt_data = [
                        {"id": getattr(i, "id", None), "value": getattr(i, "value", str(i))}
                        for i in interrupts
                    ]
            except Exception as e:
                logger.warning(f"序列化 interrupt 失败: {e}", exc_info=True)
                interrupt_data = [{"error": f"序列化 interrupt 失败: {e}"}]

        from api.services.case_lifecycle_service import complete_processing, mark_waiting_review
        if interrupted:
            mark_waiting_review(case.id)
        else:
            complete_processing(case.id, thread_id=thread_id)

        return Response({
            "status": "interrupted" if interrupted else "completed",
            "case_id": case.id,
            "thread_id": thread_id,
            "interrupt_data": interrupt_data,
            "complaint_draft": result.get("complaint_draft"),
            "errors": result.get("errors", []),
        })


class CaseWorkflowHistoryView(APIView):
    """工作流状态历史：GET /api/cases/<id>/workflow/history/

    返回 checkpoint 列表摘要（时间、当前节点、错误数、是否含 complaint_draft），
    用于调试与审计。基于 langgraph `graph.get_state_history(config)`。

    安全：仅返回摘要（不暴露完整 state，避免敏感字段泄漏）；owner 校验同其他视图。
    """
    def get(self, request, pk):
        from api.agents import build_case_workflow
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        if not case.thread_id:
            return Response(
                {'detail': '案件尚未启动工作流'},
                status=status.HTTP_404_NOT_FOUND,
            )

        workflow = build_case_workflow()
        config = {"configurable": {"thread_id": case.thread_id}}
        history = []
        for state in workflow.get_state_history(config):
            values = state.values or {}
            history.append({
                'checkpoint_id': state.config.get('configurable', {}).get('checkpoint_id'),
                'created_at': state.created_at.isoformat() if state.created_at else None,
                'next': list(state.next) if state.next else [],
                'error_count': len(values.get('errors', [])),
                'has_complaint': bool(values.get('complaint_draft')),
                'evidence_processed': len(values.get('evidence_ocr_results', [])),
            })
        return Response({
            'case_id': case.id,
            'thread_id': case.thread_id,
            'history': history,
        })


# ===== SSE 工作流流式改造（2026-07-07）=====


def _format_sse_event(evt: dict, thread_id: str | None = None) -> str:
    """格式化 SSE 事件字符串（Task 1.3.3: 统一信封）。

    输出格式：event: {type}\nid: {event_id}\ndata: {json}\n\n

    统一信封（data JSON 顶层）含 7 个字段：
        - event_id: 事件序号（thread_id 范围内单调递增）
        - event_type: 事件类型（保留旧类型字符串，向后兼容前端 addEventListener；
          新类型可通过 payload.mapped_event_type 获取）
        - run_id: WorkflowRun.id（Task 3.1 引入前为 None）
        - thread_id: 工作流线程 ID（从调用方传入，depot 行不含此字段）
        - revision: state.revision 快照（Task 2.4 引入前为 None）
        - occurred_at: 业务发生时间 ISO 8601（fallback 到 created_at）
        - payload: 事件负载（嵌套 dict）

    向后兼容：
        - 保留 ts 字段（旧前端读取）
        - 保留 payload 字段展开到顶层（旧前端 reducer 直接读 data.node / data.delta 等）
        - 保留 event_type 为旧类型字符串（前端 dispatch 的 data.event_type === "workflow.complete"
          等检查继续工作；SSE wire event: 行也用旧类型，addEventListener 正常触发）
        - 新增 legacy_event_type 字段（= event_type，显式标注旧类型供调试）

    Args:
        evt: EventDepot 返回的事件 dict（含 event_id / event_type / payload /
            run_id / revision / occurred_at / created_at）
        thread_id: 工作流线程 ID（由调用方从 case / request 注入）

    Returns:
        SSE 协议格式的字符串
    """
    event_type = evt.get('event_type', 'message')
    event_id = evt.get('event_id')
    payload = evt.get('payload', {}) or {}
    # occurred_at 优先取业务时间，回退到 DB 写入时间 created_at
    occurred_at = evt.get('occurred_at') or evt.get('created_at')

    # Task 1.3.3: 统一信封 7 字段
    data = {
        'event_id': event_id,
        'event_type': event_type,
        'run_id': evt.get('run_id'),
        'thread_id': thread_id,
        'revision': evt.get('revision'),
        'occurred_at': occurred_at,
        'payload': payload,
        # 向后兼容字段
        'ts': evt.get('created_at'),
        'legacy_event_type': event_type,
    }
    # 向后兼容：payload 字段展开到顶层（旧前端 reducer 直接读 data.node / data.delta 等）
    if isinstance(payload, dict):
        for k, v in payload.items():
            # 不覆盖信封字段（event_id / event_type / run_id / thread_id / revision /
            # occurred_at / payload / ts / legacy_event_type）
            if k not in data:
                data[k] = v

    return (
        f"event: {event_type}\n"
        f"id: {event_id}\n"
        f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    )


class CaseWorkflowReplayView(APIView):
    """返回当前工作流的持久化事件，用于页面刷新后重建展示状态。"""

    def get(self, request, pk):
        from asgiref.sync import async_to_sync
        from api.agents import EventDepot

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        events = []
        if case.thread_id:
            events = async_to_sync(EventDepot().get_all_events)(case.thread_id)

        # 与 SSE data 保持同一统一信封结构，前端可复用同一个事件 reducer。
        # Task 1.3.3: 同步 _format_sse_event 的 7 字段信封 + 向后兼容扁平字段。
        replay_events = []
        for evt in events:
            payload = evt.get('payload') or {}
            occurred_at = evt.get('occurred_at') or evt.get('created_at')
            data = {
                # 统一信封 7 字段
                'event_id': evt.get('event_id'),
                'event_type': evt.get('event_type'),
                'run_id': evt.get('run_id'),
                'thread_id': case.thread_id,
                'revision': evt.get('revision'),
                'occurred_at': occurred_at,
                'payload': payload,
                # 向后兼容字段
                'ts': evt.get('created_at'),
                'legacy_event_type': evt.get('event_type'),
            }
            # 向后兼容：payload 字段展开到顶层（旧前端 reducer 直接读 data.node 等）
            if isinstance(payload, dict):
                for k, v in payload.items():
                    if k not in data:
                        data[k] = v
            replay_events.append(data)

        return Response({
            'case_id': case.id,
            'thread_id': case.thread_id or None,
            'workflow_status': case.workflow_status,
            'workflow_error': case.workflow_error,
            'paused_after': case.workflow_paused_after or None,
            'events': replay_events,
            'last_event_id': replay_events[-1]['event_id'] if replay_events else 0,
            'history_available': bool(replay_events),
        })


class CaseWorkflowPauseView(APIView):
    """请求工作流在当前业务节点完成后安全暂停。"""

    def post(self, request, pk):
        from asgiref.sync import async_to_sync
        from api.agents import EventDepot, NotifyEmitter
        from api.services.case_lifecycle_service import LifecycleError, request_pause

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        if not case.thread_id:
            return Response({'detail': '案件尚未启动工作流'}, status=status.HTTP_404_NOT_FOUND)
        try:
            case = request_pause(case.id)
        except LifecycleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        depot = EventDepot()
        event_id = async_to_sync(depot.persist)(case.thread_id, 'workflow.pause_requested', {
            'thread_id': case.thread_id,
            'case_id': case.id,
            'reason': request.data.get('reason', ''),
            'ts': timezone.now().isoformat(),
        })
        async_to_sync(NotifyEmitter().notify)(case.thread_id, event_id)
        return Response({'status': 'pausing', 'case_id': case.id, 'thread_id': case.thread_id})


class CaseWorkflowCancelView(APIView):
    """取消已暂停的工作流，但保留案件与已生成产物。"""

    def post(self, request, pk):
        from asgiref.sync import async_to_sync
        from api.agents import EventDepot, NotifyEmitter
        from api.services.case_lifecycle_service import LifecycleError, cancel_workflow

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        thread_id = case.thread_id
        try:
            case = cancel_workflow(case.id)
        except LifecycleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        if thread_id:
            depot = EventDepot()
            event_id = async_to_sync(depot.persist)(thread_id, 'workflow.cancelled', {
                'thread_id': thread_id,
                'case_id': case.id,
                'ts': timezone.now().isoformat(),
            })
            async_to_sync(NotifyEmitter().notify)(thread_id, event_id)
        return Response({'status': 'idle', 'case_id': case.id, 'thread_id': thread_id or None})


class CaseWorkflowStateView(APIView):
    """返回当前工作流状态、暂停编辑范围与数据库产物快照。"""

    def get(self, request, pk):
        from api.services.workflow_pause_service import get_stage_editable_scope, get_stage_products

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        paused_after = case.workflow_paused_after or ''
        return Response({
            'case_id': case.id,
            'thread_id': case.thread_id or None,
            'workflow_status': case.workflow_status,
            'workflow_paused_after': paused_after,
            'editable_scope': get_stage_editable_scope(paused_after),
            'stage_products': get_stage_products(case, paused_after),
        })


class CaseWorkflowStartView(APIView):
    """启动工作流：POST /api/cases/<id>/workflow/start/

    创建后台 WorkflowRunner 任务，返回 thread_id + stream_ticket + stream_url。
    前端收到响应后使用 stream_ticket 建立 SSE 连接消费事件。

    Body:
        evidence_ids: list[int] (可选，指定处理的证据；不传则处理案件全部有图证据)

    Response:
        {
            "status": "started",
            "case_id": int,
            "thread_id": str,
            "stream_ticket": str,  # 一次性 SSE Ticket，TTL 3 分钟
            "stream_url": "/api/cases/<id>/workflow/stream/?thread_id=<thread_id>&ticket=<stream_ticket>"
        }

    TODO（Task 3.1）：当前 stream_ticket 绑定 case_id 作为 run_id 占位；
    引入 WorkflowRun 后改为真正的 run_id。
    """

    def post(self, request, pk):
        from api.agents import WorkflowRunner
        from api.services.sse_ticket_service import issue_ticket

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        evidence_ids = request.data.get('evidence_ids', [])

        # 每次完整启动使用新 thread，避免历史终止事件污染重跑；HITL resume 仍复用该 thread
        thread_id = f"case-{case.id}-{time.time_ns()}"
        case.thread_id = thread_id
        case.save(update_fields=['thread_id'])

        # 构建初始状态（与 CaseWorkflowView 保持一致）
        initial_state = {
            "case_id": case.id,
            "evidence_ids": evidence_ids,
            "evidence_preclassify_results": [],
            "evidence_ocr_results": [],
            "evidence_classify_results": [],
            "evidence_extract_results": [],
            "needs_human_review": False,
            "evidence_chain": [],
            "complaint_draft": None,
            "review_decision": None,
            "errors": [],
        }

        # 后端接受任务时原子更新生命周期，再启动后台任务
        from api.services.case_lifecycle_service import LifecycleError, start_processing
        try:
            start_processing(case.id, actor=request.user, thread_id=thread_id)
        except LifecycleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        runner = WorkflowRunner()
        runner.start_in_background(
            case_id=case.id, thread_id=thread_id, initial_state=initial_state
        )

        # 签发一次性 SSE Ticket（Task 1.4.3）
        # TODO（Task 3.1）：当前以 case.id 占位 run_id；引入 WorkflowRun 后改为真正的 run_id
        stream_ticket = issue_ticket(run_id=case.id, user_id=request.user.id)

        return Response({
            "status": "started",
            "case_id": case.id,
            "thread_id": thread_id,
            "stream_ticket": stream_ticket,
            "stream_url": (
                f"/api/cases/{case.id}/workflow/stream/"
                f"?thread_id={thread_id}&ticket={stream_ticket}"
            ),
        })


async def authenticate_sse_request(request):
    """SSE 端点手动 JWT 认证，返回 User 或 None。

    SSE 端点使用 Django 原生 View，无法走 DRF 认证，需手动解析 token。
    支持两种传递方式：
      1. Authorization: Bearer <token> header（标准方式）
      2. ?token=<token> query parameter（EventSource 不支持自定义 header 时的回退）

    抽取为模块级函数，供 CaseWorkflowStreamView 与 WorkflowRunEventsView 共用，
    避免跨视图调用私有方法造成的耦合。
    """
    from asgiref.sync import sync_to_async
    from rest_framework_simplejwt.tokens import AccessToken
    from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    else:
        token = request.GET.get('token', '')

    if not token:
        return None
    try:
        access_token = AccessToken(token)
        user_id = access_token['user_id']
        return await sync_to_async(User.objects.get)(pk=user_id)
    except (TokenError, InvalidToken, User.DoesNotExist):
        return None


class CaseWorkflowStreamView(View):
    """SSE 流式端点：GET /api/cases/<id>/workflow/stream/

    从 EventDepot 读取事件推送给前端，支持断连续传。
    流程：
        1. JWT 认证（Authorization header 或 ?token=）
        2. SSE Ticket 鉴权（?ticket=，一次性，验证后立即撤销）
        3. 读取 Last-Event-ID header 或 ?last_event_id= query 参数
        4. 从 EventDepot 批量回放漏掉的事件（event_id > last）
        5. 订阅 NotifyEmitter(thread_id) 获取新事件通知
        6. 收到通知 → 拉取新事件 → SSE 推送
        7. 每 15s 心跳保活

    鉴权（双重，Task 1.4.2）：
        - 原有 JWT 鉴权保留（用户身份校验）
        - 新增 SSE Ticket 鉴权（一次性，防止 SSE URL 被复制滥用）
        - 缺少 ticket → 401 {"detail": "Missing SSE ticket"}
        - ticket 无效/过期/已使用 → 401 {"detail": "Invalid or expired SSE ticket"}
        - TODO（Task 3.1）：当前以 case_id 占位 run_id 进行校验；引入 WorkflowRun 后
          改为真正的 run_id，并区分 401（无效 ticket）与 403（run_id 不匹配）

    需要 ASGI 部署（uvicorn），Django 4.2+ 支持异步生成器。
    继承 Django 原生 View（非 DRF APIView）以支持 async def get。
    """

    async def get(self, request, pk):
        from asgiref.sync import sync_to_async
        from api.agents import EventDepot, NotifyEmitter
        from api.services.sse_ticket_service import revoke_ticket, validate_ticket

        # 手动 JWT 认证（DRF APIView 在 ASGI 下不支持 async）
        user = await self._authenticate(request)
        if user is None:
            return HttpResponse(
                json.dumps({'detail': '认证失败'}),
                content_type='application/json',
                status=401,
            )

        # SSE Ticket 鉴权（Task 1.4.2）：在原有 JWT 之上新增一次性 ticket 校验
        # TODO（Task 3.1）：当前以 case_id 占位 run_id；引入 WorkflowRun 后改为
        #   真正的 run_id，并区分 401（无效 ticket）与 403（run_id 不匹配）
        ticket = request.GET.get('ticket', '')
        if not ticket:
            return HttpResponse(
                json.dumps({'detail': 'Missing SSE ticket'}),
                content_type='application/json',
                status=401,
            )
        try:
            case_id_for_ticket = int(pk)
        except (TypeError, ValueError):
            return HttpResponse(
                json.dumps({'detail': 'Invalid case id'}),
                content_type='application/json',
                status=400,
            )
        if not validate_ticket(ticket, case_id_for_ticket):
            return HttpResponse(
                json.dumps({'detail': 'Invalid or expired SSE ticket'}),
                content_type='application/json',
                status=401,
            )
        # 不在此处撤销：本端点由 EventSource 消费，会自动重连到同一 URL+ticket。
        # 过早撤销会使断线自动重连、以及暂停/等待后恢复再连接时校验失败。
        # 改为仅在事件流因运行「真正终态」（complete/error/cancelled）结束时撤销；
        # 暂停/等待复原等中间态保留票据，允许在短 TTL 内重连续传。

        case = await sync_to_async(get_object_or_404)(Case, pk=pk, owner=user)
        thread_id = request.GET.get('thread_id') or case.thread_id
        if not thread_id:
            return HttpResponse(
                json.dumps({'detail': '案件尚未启动工作流'}),
                content_type='application/json',
                status=404,
            )

        # 读取 last_event_id（兼容 Last-Event-ID header 和 ?last_event_id= query）
        last_event_id_str = (
            request.headers.get('Last-Event-ID')
            or request.GET.get('last_event_id', '0')
        )
        try:
            last_event_id = int(last_event_id_str)
        except (TypeError, ValueError):
            last_event_id = 0

        # 结束事件流的事件（含中间态）；其中「真正终态」才撤销票据。
        stream_end_events = {
            'workflow.complete', 'workflow.error', 'workflow.waiting_review',
            'workflow.paused', 'workflow.cancelled',
        }
        truly_terminal_events = {
            'workflow.complete', 'workflow.error', 'workflow.cancelled',
        }

        async def event_stream():
            """SSE 异步生成器：回放 + 订阅 + 心跳。"""
            # 仅在运行进入真正终态时置 True，用于决定是否撤销票据。
            normal_end = False
            depot = EventDepot()
            emitter = NotifyEmitter()
            try:
                # 1. 回放漏掉的事件（断连续传）
                missed = await depot.get_events_after(thread_id, last_event_id)
                for evt in missed:
                    yield _format_sse_event(evt, thread_id=thread_id)
                    if evt['event_type'] in stream_end_events:
                        normal_end = evt['event_type'] in truly_terminal_events
                        return

                # 2. 检查工作流是否已结束
                if await depot.is_workflow_completed(thread_id):
                    normal_end = True
                    return
                current_case = await sync_to_async(Case.objects.get)(pk=pk)
                if current_case.workflow_status in {'waiting_review', 'paused', 'idle'}:
                    # 中间态：保留票据以便恢复后重连续传
                    return

                # 3. 订阅 NOTIFY（通过线程桥接到 asyncio.Queue）
                loop = asyncio.get_running_loop()
                notify_queue: asyncio.Queue = asyncio.Queue()
                stop_event = threading.Event()

                def on_notify(pid, channel, payload):
                    """NOTIFY 回调（在线程中执行），通过 call_soon_threadsafe 投递到事件循环。"""
                    try:
                        event_id = int(payload)
                        loop.call_soon_threadsafe(notify_queue.put_nowait, event_id)
                    except (TypeError, ValueError):
                        pass

                subscribe_task = asyncio.create_task(
                    emitter.subscribe(thread_id, on_notify, stop_event)
                )

                # 4. 心跳 + 新事件推送循环
                current_last = missed[-1]['event_id'] if missed else last_event_id
                try:
                    while True:
                        try:
                            # 等待通知，15s 超时则发心跳
                            await asyncio.wait_for(notify_queue.get(), timeout=15)
                            # 收到通知，拉取新事件
                            new_events = await depot.get_events_after(
                                thread_id, current_last
                            )
                            for evt in new_events:
                                yield _format_sse_event(evt, thread_id=thread_id)
                                current_last = evt['event_id']
                                if evt['event_type'] in stream_end_events:
                                    normal_end = evt['event_type'] in truly_terminal_events
                                    return
                        except asyncio.TimeoutError:
                            # 心跳保活（SSE 注释行，不触发前端事件）
                            yield ': heartbeat\n\n'
                finally:
                    # 清理：通知订阅线程退出 + 取消任务
                    stop_event.set()
                    subscribe_task.cancel()
                    try:
                        await subscribe_task
                    except asyncio.CancelledError:
                        pass
            finally:
                # 仅运行真正终态时撤销票据；中间态/客户端断线保留，允许重连续传
                if normal_end:
                    revoke_ticket(ticket)

        response = StreamingHttpResponse(
            event_stream(), content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Connection'] = 'keep-alive'
        return response

    async def _authenticate(self, request):
        """手动 JWT 认证，返回 User 或 None（委托给模块级 authenticate_sse_request）。"""
        return await authenticate_sse_request(request)


class CaseWorkflowResumeView(APIView):
    """HITL 校正提交：POST /api/cases/<id>/workflow/resume/

    接收人工校正数据，启动新的后台 WorkflowRunner 任务恢复工作流。
    复用同一 thread_id，LangGraph 从 checkpointer 恢复中断前状态。

    Body:
        corrections: list[{evidence_id, field_name, corrected_value}]

    Response:
        {
            "status": "resumed",
            "case_id": int,
            "thread_id": str,
            "stream_ticket": str,  # 一次性 SSE Ticket，TTL 3 分钟（Task 1.4.3）
            "stream_url": "/api/cases/<id>/workflow/stream/?thread_id=<thread_id>&ticket=<stream_ticket>"
        }

    TODO（Task 3.1）：当前 stream_ticket 绑定 case_id 作为 run_id 占位；
    引入 WorkflowRun 后改为真正的 run_id。
    """

    def post(self, request, pk):
        from api.agents import WorkflowRunner
        from api.services.sse_ticket_service import issue_ticket

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        if not case.thread_id:
            return Response(
                {'detail': '案件尚未启动工作流'},
                status=status.HTTP_404_NOT_FOUND,
            )

        thread_id = case.thread_id
        from api.services.case_lifecycle_service import (
            LifecycleError,
            clear_pause_boundary,
            resume_processing,
        )
        from api.services.workflow_pause_service import (
            StagePauseValidationError,
            build_stage_resume_payload,
        )

        paused_after = case.workflow_paused_after
        is_stage_resume = case.workflow_status == 'paused'
        if is_stage_resume:
            if request.data.get('action') != 'continue':
                return Response({'detail': '暂停工作流仅支持 continue 操作'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                resume_payload = build_stage_resume_payload(case, request.data.get('edits', {}))
            except StagePauseValidationError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            corrections = request.data.get('corrections', [])
            if not corrections:
                return Response({'detail': 'corrections 不能为空'}, status=status.HTTP_400_BAD_REQUEST)
            resume_payload = {'corrections': corrections}

        try:
            resume_processing(case.id)
            runner = WorkflowRunner()
            runner.start_in_background(
                case_id=case.id,
                thread_id=thread_id,
                resume=resume_payload,
            )
            if is_stage_resume:
                clear_pause_boundary(case.id, paused_after)
        except LifecycleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        except RuntimeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        # 签发新的一次性 SSE Ticket（Task 1.4.3）：resume 后前端需重新建立 SSE 连接，
        # 旧 ticket 已在连接建立时被 revoke，故每次 resume 都签发新 ticket
        # TODO（Task 3.1）：当前以 case.id 占位 run_id；引入 WorkflowRun 后改为真正的 run_id
        stream_ticket = issue_ticket(run_id=case.id, user_id=request.user.id)

        return Response({
            "status": "resumed",
            "case_id": case.id,
            "thread_id": thread_id,
            "stream_ticket": stream_ticket,
            "stream_url": (
                f"/api/cases/{case.id}/workflow/stream/"
                f"?thread_id={thread_id}&ticket={stream_ticket}"
            ),
        })


# ===== Task 2.4：介入提交占位端点 =====


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_intervention_view(request, case_id: int, intervention_id: int):
    """提交介入：POST /api/cases/<case_id>/interventions/<intervention_id>/submit/

    占位端点（Task 2.4）：当前以 case_id 作为 URL 占位，Task 3.2 引入 WorkflowRun 后
    迁移到 `/api/workflow-runs/{run_id}/interventions/{intervention_id}/submit/`。

    Body:
        submitted_values: dict  # 用户提交的值

    响应：
        - 200: {"intervention": {...}, "status": "submitted"}
        - 400: {"detail": str}       # 介入状态非 pending 等 ValueError
        - 404: {"detail": "介入记录不存在"}
        - 409: {"code": "REVISION_CONFLICT", "detail": str, "current_revision": int}

    TODO（Task 3.2）：迁移到 /api/workflow-runs/{run_id}/interventions/{intervention_id}/submit/
    """
    from api.agents.schemas import WorkflowInterventionSchema
    from api.models import WorkflowIntervention
    from api.services.intervention_service import (
        RevisionConflictError,
        submit_intervention,
    )

    try:
        intervention = submit_intervention(
            intervention_id=intervention_id,
            submitted_values=request.data.get("submitted_values", {}),
            submitted_by_id=request.user.id,
        )
    except RevisionConflictError as e:
        return Response({
            "code": "REVISION_CONFLICT",
            "detail": str(e),
            "current_revision": e.current_revision,
        }, status=status.HTTP_409_CONFLICT)
    except WorkflowIntervention.DoesNotExist:
        return Response(
            {"detail": "介入记录不存在"}, status=status.HTTP_404_NOT_FOUND
        )
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "intervention": WorkflowInterventionSchema.from_model(intervention).model_dump(),
        "status": "submitted",
    })


# ===== Task 3.2：/workflow-runs/* API 端点（新统一接口，保留旧 /cases/<id>/workflow/* 兼容）=====
#
# 设计要点：
# - 7 个端点对齐 spec.md「Requirement: Unified WorkflowRun API」
# - 权限：IsAuthenticated + case owner 校验（workflow_run.case.owner == request.user）
# - 异步服务调用：使用 async_to_sync 包装 RetryService（async def）
#   参考 views.py 现有 `from asgiref.sync import async_to_sync` 用法
# - SSE Ticket 集成：WorkflowRunCreateView 签发一次性 ticket 绑定 run_id
# - 双写兼容策略（Task 3.4.2）：新 API 内部使用 WorkflowRun.status 新枚举，
#   同时通过 case_lifecycle_service 维护 Case.workflow_status 旧值兼容旧 API
# - revision 冲突检测：WorkflowRunInterventionSubmitView 捕获 RevisionConflictError 返回 409
# - 延迟导入避免循环依赖（如 api.agents.WorkflowRunner / api.services.* 在方法内导入）


class WorkflowRunCreateView(APIView):
    """SubTask 3.2.1：创建工作流运行

    POST /api/cases/{case_id}/workflow-runs/

    创建新 WorkflowRun 记录并启动后台 WorkflowRunner，返回 run_id + thread_id +
    一次性 SSE Ticket + stream_url。前端收到响应后使用 stream_ticket 建立 SSE 连接。

    Body:
        evidence_ids: list[int] (可选，指定处理的证据；不传则处理案件全部有图证据)
        run_options: dict (可选，运行选项，如 {"template_type": "platform", "case_mode": "complain"})

    Response:
        {
            "run_id": int,
            "case_id": int,
            "thread_id": str,
            "status": "queued",
            "stream_ticket": str,  # 一次性 SSE Ticket，TTL 3 分钟
            "stream_url": "/api/workflow-runs/{run_id}/events/?ticket=<stream_ticket>"
        }

    错误响应：
        - 404: 案件不存在
        - 403: 非案件 owner
        - 409: 案件已归档/取消 / 工作流任务正在运行
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, case_id: int):
        """返回案件运行历史；与 POST 共用资源路径。"""
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        return Response(_build_case_workflow_runs_payload(case))

    def post(self, request, case_id: int):
        from api.agents import WorkflowRunner
        from api.services.case_lifecycle_service import (
            LifecycleError,
            start_processing,
        )
        from api.services.sse_ticket_service import issue_ticket

        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        evidence_ids = request.data.get('evidence_ids', [])
        run_options = request.data.get('run_options', {}) or {}

        # 创建 WorkflowRun（thread_id 由模型 save() 自动生成 case-{case_id}-run-{id}）
        from api.models import WorkflowRun
        run = WorkflowRun.objects.create(
            case=case,
            status='queued',
            selected_evidence_ids=evidence_ids,
            run_options=run_options,
            started_by_id=request.user.id,
        )

        # 同步 Case.active_workflow_run + workflow_status（双写兼容）
        Case.objects.filter(pk=case.id).update(
            active_workflow_run=run,
            thread_id=run.thread_id,
        )
        try:
            start_processing(case.id, actor=request.user, thread_id=run.thread_id)
        except LifecycleError as exc:
            run.status = 'failed'
            run.error_message = str(exc)
            run.save(update_fields=['status', 'error_message'])
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        # 启动后台 WorkflowRunner（initial_state 与 resume/fork_config 互斥）
        initial_state = {
            "case_id": case.id,
            "workflow_run_id": run.id,
            "evidence_ids": evidence_ids,
            "evidence_preclassify_results": [],
            "evidence_ocr_results": [],
            "evidence_classify_results": [],
            "evidence_extract_results": [],
            "needs_human_review": False,
            "evidence_chain": [],
            "complaint_draft": None,
            "review_decision": None,
            "errors": [],
        }
        try:
            runner = WorkflowRunner()
            runner.start_in_background(
                case_id=case.id,
                thread_id=run.thread_id,
                initial_state=initial_state,
            )
        except RuntimeError as exc:
            # 后台任务已存在等冲突
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        # 签发一次性 SSE Ticket（绑定真正的 run_id）
        stream_ticket = issue_ticket(run_id=run.id, user_id=request.user.id)

        return Response({
            "run_id": run.id,
            "case_id": case.id,
            "thread_id": run.thread_id,
            "status": run.status,
            "stream_ticket": stream_ticket,
            "stream_url": (
                f"/api/workflow-runs/{run.id}/events/?ticket={stream_ticket}"
            ),
        }, status=status.HTTP_201_CREATED)


class WorkflowRunEventsView(View):
    """按 WorkflowRun 提供带票据鉴权的 SSE 事件流。

    票据鉴权语义：进入时仅校验（不撤销）。票据在事件流「正常结束」（运行进入终态）
    时撤销；客户端中途断线不撤销，允许在票据短 TTL 内携 Last-Event-ID 用同一票据
    重连续传。TTL 兜底防止票据被长期滥用。
    """

    _terminal_events = {
        'workflow.complete',
        'workflow.error',
        'workflow.waiting_review',
        'workflow.paused',
        'workflow.cancelled',
    }

    async def get(self, request, run_id: int):
        from asgiref.sync import sync_to_async
        from api.agents import EventDepot, NotifyEmitter
        from api.models import WorkflowRun
        from api.services.sse_ticket_service import revoke_ticket, validate_ticket

        user = await authenticate_sse_request(request)
        if user is None:
            return HttpResponse(
                json.dumps({'detail': '认证失败'}),
                content_type='application/json',
                status=401,
            )
        run = await sync_to_async(
            WorkflowRun.objects.select_related('case').filter(pk=run_id).first
        )()
        if run is None or run.case.owner_id != user.id:
            return HttpResponse(
                json.dumps({'detail': '未找到或无权访问该工作流运行'}),
                content_type='application/json',
                status=404,
            )
        ticket = request.GET.get('ticket', '')
        if not ticket or not validate_ticket(ticket, run.id):
            return HttpResponse(
                json.dumps({'detail': 'Invalid or expired SSE ticket'}),
                content_type='application/json',
                status=401,
            )
        # 不在此处撤销票据：过早撤销会导致客户端携 Last-Event-ID 用同一票据重连时
        # 校验失败、无法续传事件流。改为在 event_stream 正常结束（运行进入终态）时撤销；
        # 中途断线（GeneratorExit）不撤销，允许在短 TTL 内以同一票据重连续传，TTL 兜底防滥用。
        try:
            last_event_id = int(
                request.headers.get('Last-Event-ID')
                or request.GET.get('last_event_id', '0')
            )
        except (TypeError, ValueError):
            last_event_id = 0

        async def event_stream():
            # 仅在事件流正常结束（运行终态）时置 True，用于决定是否撤销票据。
            normal_end = False
            depot = EventDepot()
            emitter = NotifyEmitter()
            try:
                missed = await depot.get_events_after(run.thread_id, last_event_id)
                for event in missed:
                    yield _format_sse_event(event, thread_id=run.thread_id)
                    if event['event_type'] in self._terminal_events:
                        normal_end = True
                        return
                current_last = missed[-1]['event_id'] if missed else last_event_id
                if await depot.is_workflow_completed(run.thread_id):
                    normal_end = True
                    return

                loop = asyncio.get_running_loop()
                queue: asyncio.Queue = asyncio.Queue()
                stop_event = threading.Event()

                def on_notify(_pid, _channel, payload):
                    try:
                        loop.call_soon_threadsafe(queue.put_nowait, int(payload))
                    except (TypeError, ValueError):
                        pass

                subscribe_task = asyncio.create_task(
                    emitter.subscribe(run.thread_id, on_notify, stop_event)
                )
                try:
                    while True:
                        try:
                            await asyncio.wait_for(queue.get(), timeout=15)
                            new_events = await depot.get_events_after(
                                run.thread_id, current_last
                            )
                            for event in new_events:
                                yield _format_sse_event(event, thread_id=run.thread_id)
                                current_last = event['event_id']
                                if event['event_type'] in self._terminal_events:
                                    normal_end = True
                                    return
                        except asyncio.TimeoutError:
                            yield ': heartbeat\n\n'
                finally:
                    stop_event.set()
                    subscribe_task.cancel()
                    try:
                        await subscribe_task
                    except asyncio.CancelledError:
                        pass
            finally:
                # 运行正常结束才撤销票据（此时无需再重连）；中途断线保留票据以便重连续传。
                if normal_end:
                    revoke_ticket(ticket)

        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class WorkflowRunStreamTicketView(APIView):
    """为已存在的运行签发一次性 SSE 票据。

    createRun / retry / submitIntervention 会随响应返回票据；但页面加载、刷新、
    重连或切换到历史运行时没有票据，需要单独签发。票据 TTL 短、仅可读该 run。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, run_id: int):
        from api.models import WorkflowRun
        from api.services.sse_ticket_service import issue_ticket

        run = get_object_or_404(WorkflowRun, pk=run_id, case__owner=request.user)
        ticket = issue_ticket(run_id=run.id, user_id=request.user.id)
        return Response({
            "run_id": run.id,
            "stream_ticket": ticket,
            "stream_url": f"/api/workflow-runs/{run.id}/events/?ticket={ticket}",
        })


class WorkflowRunSnapshotView(APIView):
    """SubTask 3.2.2：获取权威快照

    GET /api/workflow-runs/{run_id}/snapshot/

    调用 SnapshotService.get_snapshot 聚合 run + stages + active_intervention +
    artifacts + issues + actions，作为前端展示的权威数据源。

    Response:
        {
            "run": {...},
            "stages": [...],               # 4 业务阶段
            "active_intervention": {...} | null,
            "artifacts": [...],
            "issues": [...],
            "actions": {can_pause, can_resume, can_cancel, can_retry,
                       can_restart_from_stage, can_submit_intervention}
        }

    错误响应：
        - 404: 运行不存在 / 非 case owner
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, run_id: int):
        from api.models import WorkflowRun
        from api.services.snapshot_service import SnapshotService

        run = get_object_or_404(WorkflowRun, pk=run_id)
        # case owner 校验
        if run.case_id is None or run.case.owner_id != request.user.id:
            return Response(
                {'detail': '未找到或无权访问该工作流运行'},
                status=status.HTTP_404_NOT_FOUND,
            )

        snapshot = SnapshotService().get_snapshot(run_id)
        if snapshot is None:
            return Response(
                {'detail': '工作流运行不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(snapshot)


class WorkflowRunPauseView(APIView):
    """SubTask 3.2.3：请求暂停工作流运行

    POST /api/workflow-runs/{run_id}/pause/

    调用 case_lifecycle_service.pause_workflow_run 将 WorkflowRun.status 置为 pausing。
    实际暂停在下一个 stage_gate 节点检测到 workflow_pause_requested 时完成
    （WorkflowRunner 负责监听并触发 mark_paused）。

    Response:
        {
            "run_id": int,
            "status": "pausing",
            "message": "暂停请求已提交，将在当前阶段完成后生效"
        }

    错误响应：
        - 404: 运行不存在
        - 403: 非 case owner
        - 409: 当前状态不允许暂停（非 running）
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, run_id: int):
        from api.models import WorkflowRun
        from api.services.case_lifecycle_service import (
            LifecycleError,
            request_pause,
        )

        run = get_object_or_404(WorkflowRun, pk=run_id)
        if run.case_id is None or run.case.owner_id != request.user.id:
            return Response(
                {'detail': '未找到或无权访问该工作流运行'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if run.status != 'running':
            return Response(
                {
                    'detail': f'当前运行状态 {run.status} 不允许暂停（仅 running 允许）',
                    'current_status': run.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # 同步 Case.workflow_pause_requested 标志 + workflow_status='pausing'（双写兼容）
        try:
            request_pause(run.case_id)
        except LifecycleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        # 同步 WorkflowRun.status='pausing'（新枚举）
        WorkflowRun.objects.filter(pk=run.id).update(status='pausing')

        return Response({
            "run_id": run.id,
            "status": "pausing",
            "message": "暂停请求已提交，将在当前阶段完成后生效",
        })


class WorkflowRunInterventionSubmitView(APIView):
    """SubTask 3.2.4：提交介入

    POST /api/workflow-runs/{run_id}/interventions/{intervention_id}/submit/

    调用 intervention_service.submit_intervention 提交用户介入数据。
    含 revision 冲突检测：base_revision != current_revision 时返回 409。

    Body:
        submitted_values: dict  # 用户提交的值

    Response:
        {
            "intervention": {...},  # WorkflowInterventionSchema 序列化
            "status": "submitted"
        }

    错误响应：
        - 404: 运行 / 介入记录不存在 / 非 case owner
        - 400: 介入状态非 pending（ValueError）
        - 409: revision 冲突（RevisionConflictError → REVISION_CONFLICT + current_revision）
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, run_id: int, intervention_id: int):
        from api.agents.schemas import WorkflowInterventionSchema
        from api.models import WorkflowIntervention, WorkflowRun
        from api.services.intervention_service import (
            RevisionConflictError,
            submit_intervention,
        )

        run = get_object_or_404(WorkflowRun, pk=run_id)
        if run.case_id is None or run.case.owner_id != request.user.id:
            return Response(
                {'detail': '未找到或无权访问该工作流运行'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            intervention = WorkflowIntervention.objects.get(
                pk=intervention_id,
                workflow_run_id=run.id,
            )
            intervention = submit_intervention(
                intervention_id=intervention.id,
                submitted_values=request.data.get("submitted_values", {}),
                submitted_by_id=request.user.id,
            )
        except RevisionConflictError as e:
            return Response({
                "code": "REVISION_CONFLICT",
                "detail": str(e),
                "current_revision": e.current_revision,
                "base_revision": e.base_revision,
            }, status=status.HTTP_409_CONFLICT)
        except WorkflowIntervention.DoesNotExist:
            return Response(
                {"detail": "介入记录不存在"}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        from api.agents import WorkflowRunner
        from api.services.sse_ticket_service import issue_ticket

        try:
            WorkflowRunner().start_in_background(
                case_id=run.case_id,
                thread_id=run.thread_id,
                resume={
                    "interrupt_type": intervention.intervention_type,
                    "intervention_id": intervention.id,
                    "submitted_values": intervention.submitted_values or {},
                },
            )
        except RuntimeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        stream_ticket = issue_ticket(run_id=run.id, user_id=request.user.id)
        return Response({
            "intervention": WorkflowInterventionSchema.from_model(intervention).model_dump(),
            "intervention_id": intervention.id,
            "status": "submitted",
            "stream_ticket": stream_ticket,
            "stream_url": (
                f"/api/workflow-runs/{run.id}/events/?ticket={stream_ticket}"
            ),
        })


class WorkflowRunRetryView(APIView):
    """SubTask 3.2.5：局部重跑（基于 LangGraph Time Travel）

    POST /api/workflow-runs/{run_id}/retry/

    调用 RetryService.retry_from_stage（async）从指定阶段 fork 出新运行。
    使用 async_to_sync 包装异步调用，避免阻塞 Django 同步视图。

    Body:
        from_stage: str  # 重跑起始阶段
            (material_understanding / fact_checking / case_organization / document_generation)
        preserve_user_confirmed: bool = True  # 是否保留 user_confirmed_fields
        fork_state_overrides: dict = {}  # 额外的 state 覆盖

    Response:
        {
            "new_run_id": int,
            "source_run_id": int,
            "from_stage": str,
            "thread_id": str,
            "status": "queued",
            "message": "局部重跑已启动"
        }

    错误响应：
        - 404: 运行不存在 / 非 case owner
        - 400: 无效的 from_stage 或 fork_state_overrides 格式
        - 409: 源运行状态不允许重跑（非 failed/succeeded/waiting_user）或 fork 失败
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, run_id: int):
        from asgiref.sync import async_to_sync
        from api.models import WorkflowRun
        from api.services.retry_service import RetryService

        run = get_object_or_404(WorkflowRun, pk=run_id)
        if run.case_id is None or run.case.owner_id != request.user.id:
            return Response(
                {'detail': '未找到或无权访问该工作流运行'},
                status=status.HTTP_404_NOT_FOUND,
            )

        from_stage = request.data.get('from_stage', '')
        if not from_stage:
            return Response(
                {'detail': 'from_stage 为必填字段'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        preserve_user_confirmed = request.data.get('preserve_user_confirmed', True)
        fork_state_overrides = request.data.get('fork_state_overrides', {}) or {}
        if not isinstance(fork_state_overrides, dict):
            return Response(
                {'detail': 'fork_state_overrides 必须为对象'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = RetryService()
        try:
            # RetryService.retry_from_stage 是 async，用 async_to_sync 包装
            new_run = async_to_sync(service.retry_from_stage)(
                source_run_id=run.id,
                from_stage=from_stage,
                preserve_user_confirmed=bool(preserve_user_confirmed),
                fork_state_overrides=fork_state_overrides or None,
                started_by_id=request.user.id,
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as e:
            return Response(
                {'detail': f'局部重跑失败: {e}'},
                status=status.HTTP_409_CONFLICT,
            )
        except WorkflowRun.DoesNotExist:
            return Response(
                {'detail': '源工作流运行不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        from api.services.sse_ticket_service import issue_ticket
        stream_ticket = issue_ticket(run_id=new_run.id, user_id=request.user.id)
        return Response({
            "run_id": new_run.id,
            "new_run_id": new_run.id,
            "parent_run_id": run.id,
            "source_run_id": run.id,
            "from_stage": from_stage,
            "thread_id": new_run.thread_id,
            "status": new_run.status,
            "stream_ticket": stream_ticket,
            "stream_url": (
                f"/api/workflow-runs/{new_run.id}/events/?ticket={stream_ticket}"
            ),
            "message": "局部重跑已启动",
        }, status=status.HTTP_201_CREATED)


class WorkflowRunCancelView(APIView):
    """SubTask 3.2.6：取消工作流运行

    POST /api/workflow-runs/{run_id}/cancel/

    调用 case_lifecycle_service.cancel_workflow_run 将 WorkflowRun.status 置为 cancelled。
    仅允许在 queued / running / pausing / waiting_user 状态下取消。

    Response:
        {
            "run_id": int,
            "status": "cancelled",
            "message": "工作流运行已取消"
        }

    错误响应：
        - 404: 运行不存在 / 非 case owner
        - 409: 当前状态不允许取消（已 succeeded / failed / cancelled）
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, run_id: int):
        from api.models import WorkflowRun
        from api.services.case_lifecycle_service import cancel_workflow_run

        run = get_object_or_404(WorkflowRun, pk=run_id)
        if run.case_id is None or run.case.owner_id != request.user.id:
            return Response(
                {'detail': '未找到或无权访问该工作流运行'},
                status=status.HTTP_404_NOT_FOUND,
            )

        cancellable_statuses = {'queued', 'running', 'pausing', 'waiting_user'}
        if run.status not in cancellable_statuses:
            return Response(
                {
                    'detail': f'当前运行状态 {run.status} 不允许取消',
                    'current_status': run.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # 同步 WorkflowRun.status='cancelled'（新枚举）
        cancel_workflow_run(run.id)
        # 同步 Case.workflow_status='idle'（双写兼容，便于旧 API 显示已取消）
        Case.objects.filter(pk=run.case_id).update(
            workflow_status='idle',
            workflow_pause_requested=False,
            workflow_paused_after='',
            workflow_finished_at=timezone.now(),
        )

        return Response({
            "run_id": run.id,
            "status": "cancelled",
            "message": "工作流运行已取消",
        })


def _build_case_workflow_runs_payload(case):
    """构造统一运行历史响应，供根资源和旧 list 别名复用。"""
    from api.models import WorkflowRun

    runs_data = []
    for run in WorkflowRun.objects.filter(case=case).order_by('-created_at'):
        runs_data.append({
            "id": run.id,
            "case_id": run.case_id,
            "thread_id": run.thread_id,
            "status": run.status,
            "current_stage": run.current_stage,
            "current_node": run.current_node,
            "progress": run.progress,
            "revision": run.revision,
            "workflow_version": run.workflow_version,
            "state_schema_version": run.state_schema_version,
            "policy_version": run.policy_version,
            "prompt_bundle_version": run.prompt_bundle_version,
            "parent_run_id": run.parent_run_id,
            "started_by_id": run.started_by_id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "quality_summary": run.quality_summary or {},
            "error_message": run.error_message,
        })
    return {
        "case_id": case.id,
        "runs": runs_data,
        "active_run_id": case.active_workflow_run_id,
        "total": len(runs_data),
    }


class CaseWorkflowRunsListView(APIView):
    """SubTask 3.2.7：历史运行列表

    GET /api/cases/{case_id}/workflow-runs/

    返回指定案件的所有 WorkflowRun 历史（按 created_at 降序），含 parent_run_id
    用于追溯 fork 链。每条返回基础信息（不含 artifacts / interventions 详情，前端按需
    调用 snapshot 端点获取详情）。

    Response:
        {
            "case_id": int,
            "runs": [
                {
                    "id": int, "case_id": int, "thread_id": str,
                    "status": str, "current_stage": str, "progress": float,
                    "revision": int, "workflow_version": str,
                    "parent_run_id": int | null,
                    "started_at": str | null, "finished_at": str | null,
                    "created_at": str, "updated_at": str,
                    "error_message": str
                },
                ...
            ],
            "total": int
        }

    错误响应：
        - 404: 案件不存在
        - 403: 非 case owner
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, case_id: int):
        case = get_object_or_404(Case, pk=case_id, owner=request.user)
        return Response(_build_case_workflow_runs_payload(case))


class DocumentParagraphRegenerateView(APIView):
    """SubTask 4.1.4：段落级重新生成

    POST /api/workflow-runs/{run_id}/documents/{document_id}/paragraphs/{paragraph_id}/regenerate/

    基于现有 DocumentVersion 创建新版本，仅替换目标段落内容。
    LLM 调用通过 _regenerate_paragraph_content 辅助函数封装，便于测试 mock。

    Body (可选):
        instructions: str  - 重新生成指令（如「更详细地描述当事人信息」）
        evidence_codes: list[str] - 段落新证据编号（不传则保留原值）
        tone: str - 语气（firm/restrained/neutral，默认沿用原文档）

    Response:
        {
            "document_id": int,       # 新 DocumentVersion ID
            "version": int,           # 新版本号
            "paragraph_id": str,      # 重新生成的段落 ID
            "paragraph": {...},       # 更新后的段落 dict
            "changelog": str
        }

    错误响应：
        - 404: 运行 / 文书版本 / 段落不存在
        - 403: 非 case owner
        - 400: 段落结构为空
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, run_id: int, document_id: int, paragraph_id: str):
        from api.models import DocumentVersion, WorkflowRun
        from api.services.document_version_service import regenerate_paragraph

        run = get_object_or_404(WorkflowRun, pk=run_id)
        if run.case_id is None or run.case.owner_id != request.user.id:
            return Response(
                {'detail': '未找到或无权访问该工作流运行'},
                status=status.HTTP_404_NOT_FOUND,
            )

        doc_version = get_object_or_404(
            DocumentVersion, pk=document_id, workflow_run_id=run_id
        )

        paragraphs = doc_version.paragraphs or []
        if not paragraphs:
            return Response(
                {'detail': '文书版本段落结构为空，无法重新生成段落'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_idx = next(
            (i for i, p in enumerate(paragraphs)
             if p.get('paragraph_id') == paragraph_id),
            None,
        )
        if target_idx is None:
            return Response(
                {'detail': f'段落 {paragraph_id} 不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 手动编辑直接保存提交内容；未提交 content 时才调用 LLM 重写。
        submitted_content = request.data.get('content')
        instructions = request.data.get('instructions', '') or request.data.get('prompt', '') or ''
        tone = request.data.get('tone', '') or ''
        if isinstance(submitted_content, str):
            new_content = submitted_content
        else:
            try:
                new_content = _regenerate_paragraph_content(
                    doc_version=doc_version,
                    paragraph=paragraphs[target_idx],
                    instructions=instructions,
                    tone=tone,
                )
            except Exception as exc:
                return Response(
                    {'detail': f'段落重新生成失败: {exc}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        if not new_content or not new_content.strip():
            return Response(
                {'detail': '段落重新生成返回空内容'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        evidence_codes = request.data.get('evidence_codes')
        changelog = (
            f'段落 {paragraph_id} 重新生成'
            + (f'（指令：{instructions}）' if instructions else '')
        )

        try:
            new_doc, new_paragraph, _ = regenerate_paragraph(
                doc_version=doc_version,
                paragraph_id=paragraph_id,
                new_content=new_content.strip(),
                evidence_codes=evidence_codes,
                changelog=changelog,
                created_by_type='user',
                created_by_id=request.user.id,
            )
        except ValueError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            'document_id': new_doc.id,
            'version': new_doc.version,
            'paragraph_id': paragraph_id,
            'paragraph': _serialize_paragraph(new_paragraph),
            'changelog': new_doc.changelog,
        })


def _serialize_paragraph(paragraph):
    """将后端存储的段落 dict 归一化为前端契约。

    后端段落以 ``paragraph_id``（paragraph_splitter 输出）作为键，而前端
    ``Paragraph`` 类型与 ``DocumentEditor`` 统一使用 ``id``。在 API 边界做一次
    映射，避免前端读取 ``p.id`` 得到 undefined 导致段落定位、重生成失效。
    """
    if not isinstance(paragraph, dict):
        return paragraph
    normalized = dict(paragraph)
    if 'id' not in normalized and 'paragraph_id' in normalized:
        normalized['id'] = normalized['paragraph_id']
    return normalized


class WorkflowRunDocumentDetailView(APIView):
    """读取指定运行中的文书版本详情。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, run_id: int, document_id: int):
        from api.models import DocumentVersion, WorkflowArtifact, WorkflowRun

        run = get_object_or_404(WorkflowRun, pk=run_id, case__owner=request.user)
        doc = get_object_or_404(DocumentVersion, pk=document_id, workflow_run=run)
        latest_version = (
            DocumentVersion.objects
            .filter(case_id=doc.case_id, document_type=doc.document_type)
            .order_by('-version')
            .values_list('version', flat=True)
            .first()
        )
        # input-quality-guard Gate 3：透出数据充分性（存于 complaint/respond 产物
        # content.data_sufficiency），供前端 DocumentEditor 顶部 Banner 提示。
        data_sufficiency = None
        draft_artifact = (
            WorkflowArtifact.objects
            .filter(
                workflow_run=run,
                artifact_type__in=['complaint_draft', 'respond_complaint_draft'],
            )
            .order_by('-created_at')
            .first()
        )
        if draft_artifact and isinstance(draft_artifact.content, dict):
            ds = draft_artifact.content.get('data_sufficiency')
            if isinstance(ds, dict):
                data_sufficiency = ds
        return Response({
            'id': str(doc.id),
            'run_id': run.id,
            'title': doc.title,
            'template_type': doc.document_type,
            'content': doc.content,
            'paragraphs': [_serialize_paragraph(p) for p in (doc.paragraphs or [])],
            'current_version': latest_version or doc.version,
            'created_at': doc.created_at.isoformat(),
            'updated_at': doc.created_at.isoformat(),
            'data_sufficiency': data_sufficiency,
        })


class WorkflowRunDocumentVersionsView(APIView):
    """列出同案件、同文书类型的完整版本历史。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, run_id: int, document_id: int):
        from api.models import DocumentVersion, WorkflowRun

        run = get_object_or_404(WorkflowRun, pk=run_id, case__owner=request.user)
        doc = get_object_or_404(DocumentVersion, pk=document_id, workflow_run=run)
        versions = DocumentVersion.objects.filter(
            case_id=doc.case_id,
            document_type=doc.document_type,
        ).order_by('-version')
        return Response([
            {
                'id': str(item.id),
                'document_id': str(doc.id),
                'version': item.version,
                'content': item.content,
                'changelog': item.changelog,
                'created_by_type': item.created_by_type,
                'created_by_id': str(item.created_by_id) if item.created_by_id else None,
                'created_at': item.created_at.isoformat(),
                'workflow_version': item.workflow_version,
            }
            for item in versions
        ])


class WorkflowRunDocumentRollbackView(APIView):
    """将历史版本复制为新的最新版本，保留完整审计链。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, run_id: int, document_id: int, version: int):
        from api.models import DocumentVersion, WorkflowRun
        from api.services.document_version_service import create_document_version

        run = get_object_or_404(WorkflowRun, pk=run_id, case__owner=request.user)
        current = get_object_or_404(DocumentVersion, pk=document_id, workflow_run=run)
        target = get_object_or_404(
            DocumentVersion,
            case_id=current.case_id,
            document_type=current.document_type,
            version=version,
        )
        rolled_back = create_document_version(
            case=current.case,
            document_type=current.document_type,
            content=target.content,
            title=target.title,
            paragraphs=target.paragraphs or [],
            workflow_run=run,
            complaint_template=target.complaint_template,
            respond_template=target.respond_template,
            changelog=f'回滚至版本 v{version}',
            created_by_type='user',
            created_by_id=request.user.id,
            workflow_version=run.workflow_version,
        )
        return Response({
            'id': str(rolled_back.id),
            'document_id': str(current.id),
            'version': rolled_back.version,
            'content': rolled_back.content,
            'changelog': rolled_back.changelog,
            'created_by_type': rolled_back.created_by_type,
            'created_by_id': str(request.user.id),
            'created_at': rolled_back.created_at.isoformat(),
            'workflow_version': rolled_back.workflow_version,
        }, status=status.HTTP_201_CREATED)


def _regenerate_paragraph_content(
    *,
    doc_version,
    paragraph: dict,
    instructions: str = '',
    tone: str = '',
) -> str:
    """调用 LLM 重新生成单个段落内容。

    封装为模块级函数，便于测试通过 unittest.mock.patch 替换。

    Args:
        doc_version: DocumentVersion 实例（提供文书上下文）
        paragraph: 目标段落 dict（含 title / content / evidence_codes）
        instructions: 用户重新生成指令（可空）
        tone: 语气（可空，默认沿用原文档语气）

    Returns:
        重新生成的段落内容（str）
    """
    from api.services import llm_service

    paragraph_title = paragraph.get('title', '')
    original_content = paragraph.get('content', '')
    evidence_codes = paragraph.get('evidence_codes', [])
    legal_refs = paragraph.get('legal_references', [])

    prompt = (
        f'你是法律文书写作助手。请重新生成以下文书的指定段落，保持与上下文一致。\n\n'
        f'文书类型：{doc_version.get_document_type_display()}\n'
        f'文书标题：{doc_version.title}\n'
        + (f'语气要求：{tone}\n' if tone else '')
        + f'\n段落标题：{paragraph_title}\n'
        f'段落当前内容：\n{original_content}\n'
        + (f'关联证据编号：{", ".join(evidence_codes)}\n' if evidence_codes else '')
        + (
            f'引用法条：{"; ".join(r.get("law_name", "") + r.get("article_number", "") for r in legal_refs)}\n'
            if legal_refs else ''
        )
        + (f'\n用户重新生成指令：{instructions}\n' if instructions else '')
        + '\n请直接输出重新生成的段落正文（含段落标题），不要额外解释。'
    )

    if llm_service.is_llm_available():
        result = llm_service.chat_with_retry([
            {'role': 'user', 'content': prompt}
        ])
        if isinstance(result, str) and result.strip():
            return result.strip()

    # LLM 不可用时返回原内容（允许流程继续，由调用方决定是否接受）
    return original_content


class DocumentExportCheckView(APIView):
    """SubTask 4.2.4：导出前质量门检查端点

    POST /api/workflow-runs/{run_id}/documents/{document_id}/export-check/

    调用 document_quality_service.run_export_check 执行 5 项导出前检查：
    1. 法条引用真实性（validate_legal_references 三级降级）
    2. 金额一致性（文书正文 vs ExtractedField 金额字段）
    3. 主体名称一致性（文书 vs ExtractedField 主体字段）
    4. 必备要素完整性（事实段 / 依据段 / 诉求段）
    5. stale 产物引用（WorkflowArtifact.status='stale'）

    Response:
        {
            "passed": bool,            # True 当且仅当无 blocking issues
            "issues": [...],           # ExportCheckIssue 列表（model_dump）
            "missing_elements": [...], # 缺失的必备要素子集
            "checks_run": [...]        # 已执行的检查项列表
        }

    错误响应：
        - 404: 运行 / 文书不存在或不属于该运行（含非 owner，不暴露存在性）
        - 401: 未认证
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, run_id: int, document_id: int):
        from asgiref.sync import async_to_sync
        from api.models import DocumentVersion, WorkflowRun
        from api.services.document_quality_service import run_export_check

        run = get_object_or_404(WorkflowRun, pk=run_id)
        if run.case_id is None or run.case.owner_id != request.user.id:
            return Response(
                {'detail': '未找到或无权访问该工作流运行'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 校验 document_id 属于该 run（404 if not）
        get_object_or_404(
            DocumentVersion, pk=document_id, workflow_run_id=run_id
        )

        # 调用导出前质量门检查（async → sync via async_to_sync）
        result = async_to_sync(run_export_check)(
            document_id=document_id, run_id=run_id,
        )

        return Response({
            'passed': result.passed,
            'issues': [issue.model_dump() for issue in result.issues],
            'missing_elements': result.missing_elements,
            'checks_run': result.checks_run,
        })
