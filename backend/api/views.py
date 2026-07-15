# -*- coding: utf-8 -*-
"""DRF 视图。"""
import asyncio
import json
import logging
import secrets
import string
import threading
import time

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_fsm import can_proceed
from datetime import timedelta
from rest_framework import status
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    ListAPIView,
)
from rest_framework.permissions import AllowAny
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
    ocr_service,
    extraction_service,
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
        has_sensitive_info = data.get('has_sensitive_info', False)

        evidence = Evidence.objects.create(
            case=case,
            code=code,
            evidence_type=evidence_type,
            description=description,
            source_time=source_time,
            has_sensitive_info=bool(has_sensitive_info),
            order=max_order + 1,
            image=image_file,
            ocr_status='pending',
        )

        # OCR 识别
        try:
            text = ocr_service.ocr_image(evidence.image.path)
            evidence.extracted_text = text
            evidence.ocr_status = 'done'
            evidence.save()
        except Exception:
            evidence.ocr_status = 'failed'
            evidence.save()
            text = ''

        # 字段抽取（失败也不影响返回）
        try:
            extraction_service.extract_fields(evidence)
        except Exception:
            pass

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

        code = evidence.code
        case = evidence.case
        evidence.delete()

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
        result = complaint_service.generate_complaint(case, template_type)
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

        template_type = request.data.get('template_type', 'platform')
        masked = bool(request.data.get('masked', False))

        content = export_service.generate_export_text(
            case, template_type=template_type, masked=masked
        )
        filename = f'claimcraft_case_{case.id}_{template_type}.txt'
        return Response({
            'filename': filename,
            'content': content,
        })


# ===== T1 新增视图 =====

# to_status -> 转换方法名（cancelled 除外，需按当前状态二选一）
_STATUS_TRANSITION_METHODS = {
    'processing': 'to_processing',
    'submitted': 'to_submitted',
    'closed': 'to_closed',
}


class CaseStatusTransitionView(APIView):
    """案件状态转换：POST /cases/<id>/status/transition/。

    接收 {to_status, remark}，根据 FSM 校验并执行转换，
    成功后写入 CaseStatusLog。
    """

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)

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
        )
        return Response({
            'id': case.id,
            'from_status': old_status,
            'to_status': to_status,
            'status': case.status,
        })


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


class ExportPackageView(APIView):
    """证据包导出：GET /cases/<id>/export/package/?template_type=<type> 返回 ZIP 文件流。"""

    def get(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        template_type = request.query_params.get('template_type', 'platform')
        buf = export_service.export_evidence_package(case, template_type=template_type)
        resp = HttpResponse(buf.read(), content_type='application/zip')
        resp['Content-Disposition'] = (
            f'attachment; filename="case_{case.id}_{template_type}_package.zip"'
        )
        return resp


class ExportPDFView(APIView):
    """PDF 投诉材料导出：GET /cases/<id>/export/pdf/?template_type=<type>。"""

    def get(self, request, pk):
        case = get_object_or_404(Case, pk=pk, owner=request.user)
        template_type = request.query_params.get('template_type', 'platform')
        buf = pdf_service.generate_complaint_pdf(case, template_type=template_type)
        resp = HttpResponse(buf.read(), content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'attachment; filename="case_{case.id}_{template_type}.pdf"'
        )
        return resp


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

        # 1. 获取或生成 thread_id（持久化到 Case 模型）
        if not case.thread_id:
            case.thread_id = f"case-{case.id}-{int(time.time())}"
            case.save(update_fields=['thread_id'])
        thread_id = case.thread_id

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


def _format_sse_event(evt: dict) -> str:
    """格式化 SSE 事件字符串。

    格式：event: {type}\nid: {event_id}\ndata: {json}\n\n

    Args:
        evt: EventDepot 返回的事件 dict（含 event_id / event_type / payload / created_at）

    Returns:
        SSE 协议格式的字符串
    """
    event_type = evt.get('event_type', 'message')
    event_id = evt.get('event_id')
    payload = evt.get('payload', {}) or {}

    # data 字段包含 event_id + event_type + ts + payload 展开
    data = {
        'event_id': event_id,
        'event_type': event_type,
        'ts': evt.get('created_at'),
    }
    if isinstance(payload, dict):
        data.update(payload)
    elif payload is not None:
        data['payload'] = payload

    return (
        f"event: {event_type}\n"
        f"id: {event_id}\n"
        f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    )


class CaseWorkflowStartView(APIView):
    """启动工作流：POST /api/cases/<id>/workflow/start/

    创建后台 WorkflowRunner 任务，返回 thread_id + stream_url。
    前端收到响应后建立 SSE 连接消费事件。

    Body:
        evidence_ids: list[int] (可选，指定处理的证据；不传则处理案件全部有图证据)

    Response:
        {
            "status": "started",
            "case_id": int,
            "thread_id": str,
            "stream_url": "/api/cases/<id>/workflow/stream/?thread_id=<thread_id>"
        }
    """

    def post(self, request, pk):
        from api.agents import WorkflowRunner

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        evidence_ids = request.data.get('evidence_ids', [])

        # 生成或复用 thread_id（持久化到 Case 模型）
        if not case.thread_id:
            case.thread_id = f"case-{case.id}-{int(time.time())}"
            case.save(update_fields=['thread_id'])
        thread_id = case.thread_id

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

        # 启动后台任务（asyncio.create_task，不阻塞响应）
        runner = WorkflowRunner()
        runner.start_in_background(
            case_id=case.id, thread_id=thread_id, initial_state=initial_state
        )

        return Response({
            "status": "started",
            "case_id": case.id,
            "thread_id": thread_id,
            "stream_url": f"/api/cases/{case.id}/workflow/stream/?thread_id={thread_id}",
        })


class CaseWorkflowStreamView(APIView):
    """SSE 流式端点：GET /api/cases/<id>/workflow/stream/

    从 EventDepot 读取事件推送给前端，支持断连续传。
    流程：
        1. 读取 Last-Event-ID header 或 ?last_event_id= query 参数
        2. 从 EventDepot 批量回放漏掉的事件（event_id > last）
        3. 订阅 NotifyEmitter(thread_id) 获取新事件通知
        4. 收到通知 → 拉取新事件 → SSE 推送
        5. 每 15s 心跳保活

    需要 ASGI 部署（uvicorn），Django 4.2+ 支持异步生成器。
    """

    async def get(self, request, pk):
        from asgiref.sync import sync_to_async
        from api.agents import EventDepot, NotifyEmitter

        case = await sync_to_async(get_object_or_404)(Case, pk=pk, owner=request.user)
        thread_id = request.query_params.get('thread_id') or case.thread_id
        if not thread_id:
            return Response(
                {'detail': '案件尚未启动工作流'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 读取 last_event_id（兼容 Last-Event-ID header 和 ?last_event_id= query）
        last_event_id_str = (
            request.headers.get('Last-Event-ID')
            or request.query_params.get('last_event_id', '0')
        )
        try:
            last_event_id = int(last_event_id_str)
        except (TypeError, ValueError):
            last_event_id = 0

        async def event_stream():
            """SSE 异步生成器：回放 + 订阅 + 心跳。"""
            depot = EventDepot()
            emitter = NotifyEmitter()

            # 1. 回放漏掉的事件（断连续传）
            missed = await depot.get_events_after(thread_id, last_event_id)
            for evt in missed:
                yield _format_sse_event(evt)
                if evt['event_type'] in ('workflow.complete', 'workflow.error'):
                    return

            # 2. 检查工作流是否已结束
            if await depot.is_workflow_completed(thread_id):
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
                            yield _format_sse_event(evt)
                            current_last = evt['event_id']
                            if evt['event_type'] in (
                                'workflow.complete', 'workflow.error'
                            ):
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

        response = StreamingHttpResponse(
            event_stream(), content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Connection'] = 'keep-alive'
        return response


class CaseWorkflowResumeView(APIView):
    """HITL 校正提交：POST /api/cases/<id>/workflow/resume/

    接收人工校正数据，启动新的后台 WorkflowRunner 任务恢复工作流。
    复用同一 thread_id，LangGraph 从 checkpointer 恢复中断前状态。

    Body:
        corrections: list[{evidence_id, field_name, corrected_value}]

    Response:
        {"status": "resumed", "case_id": int, "thread_id": str}
    """

    def post(self, request, pk):
        from api.agents import WorkflowRunner

        case = get_object_or_404(Case, pk=pk, owner=request.user)
        if not case.thread_id:
            return Response(
                {'detail': '案件尚未启动工作流'},
                status=status.HTTP_404_NOT_FOUND,
            )

        corrections = request.data.get('corrections', [])
        if not corrections:
            return Response(
                {'detail': 'corrections 不能为空'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        thread_id = case.thread_id
        runner = WorkflowRunner()
        runner.start_in_background(
            case_id=case.id,
            thread_id=thread_id,
            resume={'corrections': corrections},
        )

        return Response({
            "status": "resumed",
            "case_id": case.id,
            "thread_id": thread_id,
        })
