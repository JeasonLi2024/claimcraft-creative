# -*- coding: utf-8 -*-
"""
ClaimCraft 维权材料工坊数据模型。

包含六个核心模型：
- Case：维权案件
- Evidence：证据
- ExtractedField：抽取字段
- TimelineNode：时间线节点
- ComplaintTemplate：投诉模板（静态）
- ComplaintTemplateRule：投诉模板规则（Jinja2 动态）
"""


from django.db import models
from django_fsm import FSMField, transition


def evidence_image_path(instance, filename):
    """证据图片上传路径：evidences/<case_id>/<filename>。"""
    return f'evidences/{instance.case_id}/{filename}'


def masked_image_path(instance, filename):
    """打码后图片上传路径：evidences/<case_id>/masked/<filename>。"""
    return f'evidences/{instance.case_id}/masked/{filename}'


class Case(models.Model):
    """维权案件。"""

    CASE_TYPES = [
        ('shopping', '网购纠纷'),
        ('service', '服务违约'),
        ('secondhand', '二手交易'),
        ('other', '其他'),
    ]

    title = models.CharField('案件标题', max_length=200)
    description = models.TextField('案件描述', blank=True, default='')
    case_type = models.CharField(
        '纠纷类型', max_length=20, choices=CASE_TYPES, default='shopping'
    )
    status = FSMField('案件状态', default='draft', protected=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '案件'
        verbose_name_plural = '案件'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @transition(field=status, source='draft', target='processing')
    def to_processing(self, by=None):
        pass

    @transition(field=status, source='draft', target='cancelled')
    def cancel_from_draft(self, by=None):
        pass

    @transition(field=status, source='processing', target='submitted')
    def to_submitted(self, by=None):
        pass

    @transition(field=status, source='processing', target='cancelled')
    def cancel_from_processing(self, by=None):
        pass

    @transition(field=status, source='submitted', target='closed')
    def to_closed(self, by=None):
        pass


class Evidence(models.Model):
    """证据。"""

    case = models.ForeignKey(
        Case,
        related_name='evidences',
        on_delete=models.CASCADE,
        verbose_name='所属案件'
    )
    code = models.CharField('证据编号', max_length=20, help_text='如 E1、E2')
    evidence_type = models.CharField(
        '证据类型', max_length=50,
        help_text='如 订单页/聊天记录/物流页/客服回复'
    )
    description = models.TextField('证据描述')
    source_time = models.DateTimeField('证据发生时间')
    has_sensitive_info = models.BooleanField('是否含敏感信息', default=False)
    order = models.IntegerField('排序', default=0)
    image = models.ImageField(
        '证据图片', upload_to=evidence_image_path,
        blank=True, null=True
    )
    extracted_text = models.TextField('OCR 抽取文本', blank=True, default='')
    ocr_status = models.CharField(
        'OCR 状态', max_length=20, default='pending',
        help_text='pending/done/failed'
    )
    masked_image = models.ImageField(
        '打码后图片', upload_to=masked_image_path,
        blank=True, null=True
    )
    mask_status = models.CharField(
        '打码状态', max_length=20, default='none',
        help_text='none/pending/done'
    )

    class Meta:
        verbose_name = '证据'
        verbose_name_plural = '证据'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.code} - {self.evidence_type}'


class ExtractedField(models.Model):
    """从证据中抽取的关键字段。"""

    evidence = models.ForeignKey(
        Evidence,
        related_name='extracted_fields',
        on_delete=models.CASCADE,
        verbose_name='所属证据'
    )
    field_name = models.CharField('字段名', max_length=50, help_text='订单号/金额/手机号/地址/时间/承诺话术')
    field_value = models.CharField('字段值', max_length=500)
    confidence = models.FloatField('置信度', default=0.9)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '抽取字段'
        verbose_name_plural = '抽取字段'
        ordering = ['id']

    def __str__(self):
        return f'{self.field_name}: {self.field_value}'


class TimelineNode(models.Model):
    """时间线节点。"""

    case = models.ForeignKey(
        Case,
        related_name='timeline_nodes',
        on_delete=models.CASCADE,
        verbose_name='所属案件'
    )
    datetime = models.DateTimeField('发生时间')
    event = models.TextField('事件描述')
    related_evidence_codes = models.CharField(
        '关联证据编号', max_length=200, blank=True, default='',
        help_text='逗号分隔，如 E1,E2'
    )
    order = models.IntegerField('排序', default=0)
    auto_generated = models.BooleanField('是否自动生成', default=False)

    class Meta:
        verbose_name = '时间线节点'
        verbose_name_plural = '时间线节点'
        ordering = ['order', 'datetime']

    def __str__(self):
        return f'{self.datetime} - {self.event[:20]}'


class ComplaintTemplate(models.Model):
    """投诉模板（静态）。"""

    PLATFORM = 'platform'
    REGULATORY = 'regulatory'
    ARBITRATION = 'arbitration'
    TEMPLATE_TYPE_CHOICES = [
        (PLATFORM, '平台客服版'),
        (REGULATORY, '监管投诉版'),
        (ARBITRATION, '仲裁准备版'),
    ]

    case = models.ForeignKey(
        Case,
        related_name='complaint_templates',
        on_delete=models.CASCADE,
        verbose_name='所属案件'
    )
    template_type = models.CharField(
        '模板类型', max_length=20, choices=TEMPLATE_TYPE_CHOICES,
        default=PLATFORM
    )
    title = models.CharField('标题', max_length=200)
    content = models.TextField('内容')

    class Meta:
        verbose_name = '投诉模板'
        verbose_name_plural = '投诉模板'
        ordering = ['id']

    def __str__(self):
        return f'[{self.get_template_type_display()}] {self.title}'


class ComplaintTemplateRule(models.Model):
    """投诉模板规则（Jinja2 动态渲染）。"""

    PLATFORM = 'platform'
    REGULATORY = 'regulatory'
    ARBITRATION = 'arbitration'
    TEMPLATE_TYPES = [
        (PLATFORM, '平台客服版'),
        (REGULATORY, '监管投诉版'),
        (ARBITRATION, '仲裁准备版'),
    ]

    case = models.ForeignKey(
        Case,
        related_name='template_rules',
        on_delete=models.CASCADE,
        null=True, blank=True,
        verbose_name='所属案件（null 表示全局规则）'
    )
    template_type = models.CharField('模板类型', max_length=20, choices=TEMPLATE_TYPES)
    rule_title = models.TextField('标题 Jinja2 源码')
    rule_content = models.TextField('正文 Jinja2 源码')

    class Meta:
        verbose_name = '投诉模板规则'
        verbose_name_plural = '投诉模板规则'
        ordering = ['id']

    def __str__(self):
        case_label = f'Case#{self.case_id}' if self.case_id else '全局'
        return f'[{case_label}][{self.get_template_type_display()}] 规则'


class CaseStatusLog(models.Model):
    """案件状态变更日志。"""

    case = models.ForeignKey(
        Case,
        related_name='status_logs',
        on_delete=models.CASCADE,
        verbose_name='所属案件'
    )
    from_status = models.CharField('原状态', max_length=20, blank=True, default='')
    to_status = models.CharField('目标状态', max_length=20)
    remark = models.TextField('备注', blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '案件状态日志'
        verbose_name_plural = '案件状态日志'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.case_id} {self.from_status}->{self.to_status}'
