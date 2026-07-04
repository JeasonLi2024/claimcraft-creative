# -*- coding: utf-8 -*-
"""DRF 序列化器。"""
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from api.models import (
    Case, Evidence, ExtractedField, TimelineNode,
    ComplaintTemplate, ComplaintTemplateRule, CaseStatusLog,
    CaseTypePreset,
)


class UserSerializer(serializers.ModelSerializer):
    """用户序列化器。"""

    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class RegisterSerializer(serializers.ModelSerializer):
    """注册序列化器。"""

    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': '两次密码不一致'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user


class CaseSerializer(serializers.ModelSerializer):
    """案件序列化器，含统计字段。"""

    status = serializers.CharField(read_only=True)
    owner = UserSerializer(read_only=True)
    evidence_count = serializers.SerializerMethodField()
    timeline_count = serializers.SerializerMethodField()
    template_count = serializers.SerializerMethodField()
    image_evidence_count = serializers.SerializerMethodField()
    extracted_field_count = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = [
            'id', 'title', 'description', 'case_type', 'status',
            'created_at', 'updated_at', 'owner',
            'evidence_count', 'timeline_count', 'template_count',
            'image_evidence_count', 'extracted_field_count',
        ]
        read_only_fields = ['status', 'created_at', 'updated_at', 'owner']

    def get_evidence_count(self, obj):
        return obj.evidences.count()

    def get_timeline_count(self, obj):
        return obj.timeline_nodes.count()

    def get_template_count(self, obj):
        return obj.complaint_templates.count()

    def get_image_evidence_count(self, obj):
        return obj.evidences.exclude(image='').count()

    def get_extracted_field_count(self, obj):
        count = 0
        for ev in obj.evidences.all():
            count += ev.extracted_fields.count()
        return count


class CaseListSerializer(serializers.ModelSerializer):
    """案件列表轻量序列化器。"""

    owner = UserSerializer(read_only=True)
    evidence_count = serializers.SerializerMethodField()
    image_evidence_count = serializers.SerializerMethodField()
    extracted_field_count = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = [
            'id', 'title', 'description', 'case_type', 'status',
            'created_at', 'updated_at', 'owner',
            'evidence_count', 'image_evidence_count',
            'extracted_field_count',
        ]
        read_only_fields = ['status', 'created_at', 'updated_at', 'owner']

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
        ]
        read_only_fields = ['mask_status']

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
            'related_evidence_codes', 'order', 'auto_generated',
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
            'id', 'case', 'from_status', 'to_status',
            'remark', 'created_at',
        ]


class CaseTypePresetSerializer(serializers.ModelSerializer):
    """案件类型预设序列化器。"""

    class Meta:
        model = CaseTypePreset
        fields = '__all__'
