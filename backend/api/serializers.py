# -*- coding: utf-8 -*-
"""DRF 序列化器。"""
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from api.models import (
    EmailVerificationChallenge,
    UserProfile,
    UserPreference,
    UserSession,
    Case, Evidence, ExtractedField, TimelineNode,
    ComplaintTemplate, ComplaintTemplateRule, CaseStatusLog,
    CaseTypePreset,
)


def _get_user_profile(user: User) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={'display_name': user.username},
    )
    return profile


def _get_user_preferences(user: User) -> UserPreference:
    preferences, _ = UserPreference.objects.get_or_create(user=user)
    return preferences


def _build_media_url(request, file_field) -> str:
    if not file_field:
        return ''
    url = file_field.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


class UserSummarySerializer(serializers.ModelSerializer):
    """用户摘要序列化器。"""

    display_name = serializers.SerializerMethodField()
    email_verified = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email',
            'display_name', 'email_verified', 'avatar_url',
        ]

    def get_display_name(self, obj):
        profile = _get_user_profile(obj)
        return profile.display_name or obj.username

    def get_email_verified(self, obj):
        return _get_user_profile(obj).email_verified

    def get_avatar_url(self, obj):
        profile = _get_user_profile(obj)
        return _build_media_url(self.context.get('request'), profile.avatar_display)


class UserPreferenceSerializer(serializers.ModelSerializer):
    """用户偏好序列化器。"""

    class Meta:
        model = UserPreference
        fields = [
            'workflow_reminders',
            'export_reminder',
            'compact_case_cards',
            'default_case_mode',
            'default_template_type',
        ]


class UserDetailSerializer(serializers.ModelSerializer):
    """用户详情序列化器。"""

    display_name = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    locale = serializers.SerializerMethodField()
    timezone = serializers.SerializerMethodField()
    email_verified = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    avatar_updated_at = serializers.SerializerMethodField()
    preferences = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email',
            'display_name', 'bio', 'locale', 'timezone',
            'email_verified', 'avatar_url', 'avatar_updated_at',
            'date_joined', 'last_login',
            'preferences',
        ]

    def get_display_name(self, obj):
        profile = _get_user_profile(obj)
        return profile.display_name or obj.username

    def get_bio(self, obj):
        return _get_user_profile(obj).bio

    def get_locale(self, obj):
        return _get_user_profile(obj).locale

    def get_timezone(self, obj):
        return _get_user_profile(obj).timezone

    def get_email_verified(self, obj):
        return _get_user_profile(obj).email_verified

    def get_avatar_url(self, obj):
        profile = _get_user_profile(obj)
        return _build_media_url(self.context.get('request'), profile.avatar_display)

    def get_avatar_updated_at(self, obj):
        return _get_user_profile(obj).avatar_updated_at

    def get_preferences(self, obj):
        preferences = _get_user_preferences(obj)
        return UserPreferenceSerializer(preferences).data


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """用户资料更新序列化器。"""

    class Meta:
        model = UserProfile
        fields = ['display_name', 'bio', 'locale', 'timezone']


class ExportOptionsSerializer(serializers.Serializer):
    """导出请求参数。"""

    template_type = serializers.ChoiceField(
        choices=ComplaintTemplate.TEMPLATE_TYPE_CHOICES,
        default=ComplaintTemplate.PLATFORM,
    )
    masked = serializers.BooleanField(default=False, required=False)


class AvatarUploadSerializer(serializers.Serializer):
    """头像上传请求序列化器。"""

    avatar = serializers.ImageField(required=True)


class EmailSendCodeSerializer(serializers.Serializer):
    """当前邮箱验证码发送请求。"""


class EmailAddressSerializer(serializers.Serializer):
    """邮箱地址请求。"""

    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        return value.strip().lower()


class EmailCodeVerifySerializer(serializers.Serializer):
    """邮箱验证码校验请求。"""

    code = serializers.RegexField(r'^\d{6}$', error_messages={'invalid': '验证码必须为 6 位数字'})


class EmailCodeWithAddressSerializer(EmailCodeVerifySerializer):
    """邮箱验证码校验请求（含邮箱）。"""

    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        return value.strip().lower()


class EmailChangeRequestSerializer(serializers.Serializer):
    """新邮箱变更申请请求。"""

    new_email = serializers.EmailField(required=True)

    def validate_new_email(self, value):
        return value.strip().lower()


class EmailChangeConfirmSerializer(EmailCodeVerifySerializer):
    """新邮箱确认请求。"""

    new_email = serializers.EmailField(required=True)

    def validate_new_email(self, value):
        return value.strip().lower()


class PasswordResetVerifySerializer(EmailCodeWithAddressSerializer):
    """重置密码验证码校验请求。"""


class PasswordResetConfirmSerializer(serializers.Serializer):
    """重置密码确认请求。"""

    email = serializers.EmailField(required=True)
    new_password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)
    new_password_confirm = serializers.CharField(write_only=True, required=True, trim_whitespace=False)

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': '两次新密码输入不一致'})
        validate_password(attrs['new_password'])
        return attrs


class ChangePasswordCodeVerifySerializer(EmailCodeVerifySerializer):
    """修改密码验证码校验请求。"""


class EmailVerificationChallengeSerializer(serializers.ModelSerializer):
    """邮箱验证码挑战摘要序列化器。"""

    class Meta:
        model = EmailVerificationChallenge
        fields = [
            'id',
            'scene',
            'target_email',
            'expires_at',
            'attempt_count',
            'verified_at',
            'used_at',
            'created_at',
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """修改密码序列化器。"""

    old_password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)
    new_password_confirm = serializers.CharField(write_only=True, required=True, trim_whitespace=False)
    logout_other_sessions = serializers.BooleanField(required=False, default=False)

    def validate_old_password(self, value):
        user = self.context.get('user') or getattr(self.context.get('request'), 'user', None)
        if user is None or not user.check_password(value):
            raise serializers.ValidationError('旧密码错误')
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': '两次新密码输入不一致'})
        validate_password(attrs['new_password'])
        return attrs


class UserSessionSerializer(serializers.ModelSerializer):
    """用户会话序列化器。"""

    is_current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = [
            'id', 'device_name', 'device_type',
            'created_at', 'last_seen_at', 'expires_at',
            'revoked_at', 'is_current',
        ]

    def get_is_current(self, obj):
        current_session_id = self.context.get('current_session_id')
        if current_session_id is None:
            return False
        return obj.id == current_session_id


class UserSerializer(serializers.ModelSerializer):
    """兼容旧视图的用户基础序列化器。"""

    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class RegisterSerializer(serializers.ModelSerializer):
    """注册序列化器。"""

    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm']

    def validate_username(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('用户名不能为空')
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('该邮箱已被注册')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': '两次密码不一致'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data.pop('password_confirm')
        user = User.objects.create_user(password=password, **validated_data)
        UserProfile.objects.get_or_create(
            user=user,
            defaults={'display_name': user.username},
        )
        UserPreference.objects.get_or_create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    """账号或邮箱密码登录请求。"""

    account = serializers.CharField(write_only=True, required=True, trim_whitespace=True)
    password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)

    def validate_account(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('账号或邮箱不能为空')
        return value


class CaseSerializer(serializers.ModelSerializer):
    """案件序列化器，含统计字段与系统计算的工作进度。"""

    status = serializers.CharField(read_only=True)
    owner = UserSerializer(read_only=True)
    evidence_count = serializers.SerializerMethodField()
    timeline_count = serializers.SerializerMethodField()
    template_count = serializers.SerializerMethodField()
    image_evidence_count = serializers.SerializerMethodField()
    extracted_field_count = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = [
            'id', 'title', 'description', 'case_type', 'case_mode', 'status',
            'created_at', 'updated_at', 'owner',
            'evidence_count', 'timeline_count', 'template_count',
            'image_evidence_count', 'extracted_field_count',
            'thread_id', 'workflow_status', 'workflow_started_at', 'workflow_finished_at',
            'workflow_error', 'workflow_revision', 'document_stale', 'archived_at',
            'progress',
        ]
        read_only_fields = [
            'status', 'created_at', 'updated_at', 'owner', 'thread_id', 'workflow_status',
            'workflow_started_at', 'workflow_finished_at', 'workflow_error',
            'workflow_revision', 'document_stale', 'archived_at', 'progress',
        ]

    def get_evidence_count(self, obj):
        return obj.evidences.count()

    def get_timeline_count(self, obj):
        return obj.timeline_nodes.count()

    def get_template_count(self, obj):
        if obj.case_mode == 'respond':
            return obj.respond_templates.count()
        return obj.complaint_templates.count()

    def get_image_evidence_count(self, obj):
        return obj.evidences.exclude(image='').count()

    def get_extracted_field_count(self, obj):
        count = 0
        for ev in obj.evidences.all():
            count += ev.extracted_fields.count()
        return count

    def get_progress(self, obj):
        from api.services.case_lifecycle_service import get_case_progress
        return get_case_progress(obj)


class CaseListSerializer(serializers.ModelSerializer):
    """案件列表轻量序列化器。"""

    owner = UserSerializer(read_only=True)
    evidence_count = serializers.SerializerMethodField()
    image_evidence_count = serializers.SerializerMethodField()
    extracted_field_count = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = [
            'id', 'title', 'description', 'case_type', 'case_mode', 'status',
            'workflow_status', 'document_stale',
            'created_at', 'updated_at', 'owner',
            'evidence_count', 'image_evidence_count',
            'extracted_field_count',
        ]
        read_only_fields = [
            'status', 'workflow_status', 'document_stale',
            'created_at', 'updated_at', 'owner',
        ]

    def get_evidence_count(self, obj):
        return obj.evidences.count()

    def get_image_evidence_count(self, obj):
        return obj.evidences.exclude(image='').count()

    def get_extracted_field_count(self, obj):
        count = 0
        for ev in obj.evidences.all():
            count += ev.extracted_fields.count()
        return count


class EvidenceSerializer(serializers.ModelSerializer):
    """证据序列化器。

    case 设为只读，由视图通过 save(case=case) 注入，
    避免新增时因 case 必填校验失败。
    image / masked_image 以完整 URL 返回。
    """

    case = serializers.PrimaryKeyRelatedField(read_only=True)
    image = serializers.SerializerMethodField()
    masked_image = serializers.SerializerMethodField()

    class Meta:
        model = Evidence
        fields = [
            'id', 'case', 'code', 'evidence_type', 'description',
            'source_time', 'has_sensitive_info', 'order',
            'image', 'extracted_text', 'ocr_status',
            'masked_image', 'mask_status',
            'is_physical_evidence', 'physical_note',
        ]
        read_only_fields = ['mask_status', 'is_physical_evidence']

    def get_image(self, obj):
        if not obj.image:
            return ''
        request = self.context.get('request')
        url = obj.image.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url

    def get_masked_image(self, obj):
        if not obj.masked_image:
            return ''
        request = self.context.get('request')
        url = obj.masked_image.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class ExtractedFieldSerializer(serializers.ModelSerializer):
    """抽取字段序列化器。"""

    evidence = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ExtractedField
        fields = [
            'id', 'evidence', 'field_name', 'field_value',
            'confidence', 'created_at',
        ]


class TimelineNodeSerializer(serializers.ModelSerializer):
    """时间线节点序列化器。"""

    case = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = TimelineNode
        fields = [
            'id', 'case', 'datetime', 'event',
            'related_evidence_codes', 'category', 'order', 'auto_generated',
        ]


class ComplaintTemplateSerializer(serializers.ModelSerializer):
    """投诉模板序列化器。"""

    class Meta:
        model = ComplaintTemplate
        fields = [
            'id', 'case', 'template_type', 'title', 'content',
        ]


class ComplaintTemplateRuleSerializer(serializers.ModelSerializer):
    """投诉模板规则序列化器。"""

    class Meta:
        model = ComplaintTemplateRule
        fields = [
            'id', 'case', 'template_type', 'rule_title', 'rule_content',
        ]


class CaseStatusLogSerializer(serializers.ModelSerializer):
    """案件状态日志序列化器。"""

    class Meta:
        model = CaseStatusLog
        fields = [
            'id', 'case', 'from_status', 'to_status', 'remark',
            'trigger', 'actor', 'thread_id', 'metadata', 'created_at',
        ]


class CaseTypePresetSerializer(serializers.ModelSerializer):
    """案件类型预设序列化器。"""

    class Meta:
        model = CaseTypePreset
        fields = '__all__'
