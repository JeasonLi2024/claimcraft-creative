# -*- coding: utf-8 -*-
"""Admin 注册。"""
from django.contrib import admin

from api.models import (
    Case,
    ComplaintTemplate,
    EmailVerificationChallenge,
    Evidence,
    RespondTemplate,
    TimelineNode,
    UserProfile,
)


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'created_at')
    search_fields = ('title', 'description')
    list_filter = ('created_at',)


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'evidence_type', 'case', 'source_time', 'has_sensitive_info', 'order')
    list_filter = ('evidence_type', 'has_sensitive_info')
    search_fields = ('code', 'description', 'evidence_type')
    list_editable = ('order',)


@admin.register(TimelineNode)
class TimelineNodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'case', 'datetime', 'related_evidence_codes', 'order')
    list_filter = ('datetime',)
    search_fields = ('event', 'related_evidence_codes')
    list_editable = ('order',)


@admin.register(ComplaintTemplate)
class ComplaintTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'case', 'template_type', 'title')
    list_filter = ('template_type',)
    search_fields = ('title', 'content')


@admin.register(RespondTemplate)
class RespondTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'case', 'template_type', 'title')
    list_filter = ('template_type',)
    search_fields = ('title', 'content')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'display_name',
        'email_verified',
        'avatar_updated_at',
        'updated_at',
    )
    list_filter = ('email_verified', 'locale', 'timezone')
    search_fields = ('user__username', 'user__email', 'display_name')


@admin.register(EmailVerificationChallenge)
class EmailVerificationChallengeAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'scene',
        'target_email',
        'attempt_count',
        'expires_at',
        'verified_at',
        'used_at',
        'created_at',
    )
    list_filter = ('scene', 'verified_at', 'used_at', 'created_at')
    search_fields = ('user__username', 'user__email', 'target_email')
