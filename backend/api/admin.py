# -*- coding: utf-8 -*-
"""Admin 注册。"""
from django.contrib import admin

from api.models import Case, Evidence, TimelineNode, ComplaintTemplate


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
