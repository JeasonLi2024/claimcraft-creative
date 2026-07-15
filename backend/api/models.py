# -*- coding: utf-8 -*-
"""
ClaimCraft 维权材料工坊数据模型。

包含核心模型：
- Case：维权案件
- Evidence：证据
- ExtractedField：抽取字段
- TimelineNode：时间线节点
- ComplaintTemplate：投诉模板（静态）
- ComplaintTemplateRule：投诉模板规则（Jinja2 动态）
- LawArticle：法律条文（v10 新增，RAG 知识库）
"""


import os
import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django_fsm import FSMField, transition
from django.contrib.auth.models import User
from django.utils import timezone


def evidence_image_path(instance, filename):
    """证据图片上传路径：evidences/<case_id>/<filename>。"""
    return f'evidences/{instance.case_id}/{filename}'


def masked_image_path(instance, filename):
    """打码后图片上传路径：evidences/<case_id>/masked/<filename>。"""
    return f'evidences/{instance.case_id}/masked/{filename}'


def _avatar_upload_path(instance, filename, variant):
    user_id = instance.user_id or 'unassigned'
    _, ext = os.path.splitext(filename or '')
    ext = ext.lower() or '.bin'
    return f'avatar/{user_id}/{variant}/{uuid.uuid4().hex}{ext}'


def avatar_original_upload_path(instance, filename):
    """头像原图上传路径：avatar/<user_id>/original/<filename>。"""
    return _avatar_upload_path(instance, filename, 'original')


def avatar_display_upload_path(instance, filename):
    """头像展示图上传路径：avatar/<user_id>/display/<filename>。"""
    return _avatar_upload_path(instance, filename, 'display')


class Case(models.Model):
    """维权案件。"""

    CASE_TYPES = [
        ('shopping', '网购纠纷'),
        ('service', '服务违约'),
        ('secondhand', '二手交易'),
        ('other', '其他'),
    ]

    CASE_MODE_CHOICES = [
        ('complain', '维权投诉'),
        ('respond', '商家反证'),
    ]

    title = models.CharField('案件标题', max_length=200)
    description = models.TextField('案件描述', blank=True, default='')
    case_type = models.CharField(
        '纠纷类型', max_length=20, choices=CASE_TYPES, default='shopping'
    )
    case_mode = models.CharField(
        '案件模式', max_length=20, choices=CASE_MODE_CHOICES,
        default='complain'
    )
    status = FSMField('案件状态', default='draft', protected=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='cases',
        verbose_name='所属用户', null=True, blank=True
    )
    thread_id = models.CharField(
        'LangGraph Thread ID', max_length=100, blank=True, default='',
        help_text='LangGraph checkpointer 的 thread_id，用于 HITL 状态恢复'
    )

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


class UserProfile(models.Model):
    """用户扩展资料。"""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='用户',
    )
    display_name = models.CharField('显示名称', max_length=150, blank=True, default='')
    bio = models.TextField('个人简介', blank=True, default='')
    locale = models.CharField('语言地区', max_length=20, default='zh-CN')
    timezone = models.CharField('时区', max_length=64, default='Asia/Shanghai')
    email_verified = models.BooleanField('邮箱已验证', default=False)
    avatar_original = models.ImageField(
        '头像原图',
        upload_to=avatar_original_upload_path,
        blank=True,
        null=True,
    )
    avatar_display = models.ImageField(
        '头像展示图',
        upload_to=avatar_display_upload_path,
        blank=True,
        null=True,
    )
    avatar_updated_at = models.DateTimeField(
        '头像更新时间',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = '用户资料'

    def __str__(self):
        return self.display_name or self.user.username


class EmailVerificationChallenge(models.Model):
    """邮箱验证码挑战。"""

    class Scene(models.TextChoices):
        REGISTER_EMAIL = 'register_email', '注册邮箱'
        LOGIN_EMAIL = 'login_email', '登录邮箱'
        RESET_PASSWORD = 'reset_password', '重置密码'
        VERIFY_CURRENT_EMAIL = 'verify_current_email', '验证当前邮箱'
        CHANGE_PASSWORD_EMAIL = 'change_password_email', '修改密码校验'
        CHANGE_EMAIL = 'change_email', '修改邮箱'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='email_verification_challenges',
        verbose_name='用户',
        null=True,
        blank=True,
    )
    scene = models.CharField(
        '验证场景',
        max_length=32,
        choices=Scene.choices,
    )
    target_email = models.EmailField('目标邮箱', max_length=254)
    code_hash = models.CharField('验证码哈希', max_length=255)
    expires_at = models.DateTimeField('过期时间')
    verified_at = models.DateTimeField('验证成功时间', null=True, blank=True)
    used_at = models.DateTimeField('使用时间', null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField('尝试次数', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '邮箱验证码挑战'
        verbose_name_plural = '邮箱验证码挑战'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'scene', 'created_at']),
            models.Index(fields=['target_email', 'scene', 'created_at']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        user_label = self.user.username if self.user_id else 'anonymous'
        return f'{user_label} {self.scene} {self.target_email}'

    @property
    def is_used(self):
        return self.used_at is not None

    @property
    def is_verified(self):
        return self.verified_at is not None

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def set_plain_code(self, code: str):
        self.code_hash = make_password(code)

    def check_plain_code(self, code: str) -> bool:
        if not self.code_hash:
            return False
        return check_password(code, self.code_hash)

    def mark_attempt(self, save: bool = True):
        self.attempt_count += 1
        if save:
            self.save(update_fields=['attempt_count', 'updated_at'])

    def mark_verified(self, save: bool = True):
        if self.verified_at is not None:
            return
        self.verified_at = timezone.now()
        if save:
            self.save(update_fields=['verified_at', 'updated_at'])

    def mark_used(self, save: bool = True):
        now = timezone.now()
        update_fields = ['used_at', 'updated_at']
        if self.verified_at is None:
            self.verified_at = now
            update_fields.insert(0, 'verified_at')
        self.used_at = now
        if save:
            self.save(update_fields=update_fields)


class UserPreference(models.Model):
    """用户偏好设置。"""

    DEFAULT_TEMPLATE_CHOICES = [
        ('platform', '平台客服版'),
        ('regulatory', '监管投诉版'),
        ('arbitration', '仲裁准备版'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='preferences',
        verbose_name='用户',
    )
    workflow_reminders = models.BooleanField('工作流提醒', default=True)
    export_reminder = models.BooleanField('导出安全提醒', default=True)
    compact_case_cards = models.BooleanField('紧凑案件卡片', default=False)
    default_case_mode = models.CharField(
        '默认案件模式',
        max_length=20,
        choices=Case.CASE_MODE_CHOICES,
        default='complain',
    )
    default_template_type = models.CharField(
        '默认模板类型',
        max_length=20,
        choices=DEFAULT_TEMPLATE_CHOICES,
        default='platform',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '用户偏好'
        verbose_name_plural = '用户偏好'

    def __str__(self):
        return f'{self.user.username} 偏好'


class UserSession(models.Model):
    """用户设备会话。"""

    DEVICE_TYPE_CHOICES = [
        ('web', 'Web'),
        ('mobile', 'Mobile'),
        ('tablet', 'Tablet'),
        ('desktop', 'Desktop'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sessions',
        verbose_name='用户',
    )
    refresh_jti = models.CharField(
        'Refresh Token JTI',
        max_length=255,
        unique=True,
        db_index=True,
    )
    device_name = models.CharField('设备名称', max_length=255, blank=True, default='')
    device_type = models.CharField(
        '设备类型',
        max_length=20,
        choices=DEVICE_TYPE_CHOICES,
        default='web',
    )
    ip_address = models.GenericIPAddressField(
        'IP 地址',
        null=True,
        blank=True,
        unpack_ipv4=True,
    )
    user_agent = models.TextField('User Agent', blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    last_seen_at = models.DateTimeField('最近活跃时间', default=timezone.now)
    expires_at = models.DateTimeField('过期时间')
    revoked_at = models.DateTimeField('撤销时间', null=True, blank=True)

    class Meta:
        verbose_name = '用户会话'
        verbose_name_plural = '用户会话'
        ordering = ['-last_seen_at', '-created_at']
        indexes = [
            models.Index(fields=['user', 'revoked_at']),
            models.Index(fields=['user', 'expires_at']),
        ]

    def __str__(self):
        return f'{self.user.username} {self.device_name or self.device_type}'


class AccountAuditLog(models.Model):
    """账户相关最小审计日志。"""

    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'
    ACTION_LOGOUT_ALL = 'logout_all'
    ACTION_CHANGE_PASSWORD = 'change_password'
    ACTION_REVOKE_SESSION = 'revoke_session'
    ACTION_CHOICES = [
        (ACTION_LOGIN, '登录'),
        (ACTION_LOGOUT, '退出当前设备'),
        (ACTION_LOGOUT_ALL, '退出全部设备'),
        (ACTION_CHANGE_PASSWORD, '修改密码'),
        (ACTION_REVOKE_SESSION, '撤销会话'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='account_audit_logs',
        verbose_name='用户',
    )
    session = models.ForeignKey(
        UserSession,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
        null=True,
        blank=True,
        verbose_name='关联会话',
    )
    action = models.CharField('动作', max_length=32, choices=ACTION_CHOICES)
    ip_address = models.GenericIPAddressField(
        'IP 地址',
        null=True,
        blank=True,
        unpack_ipv4=True,
    )
    user_agent = models.TextField('User Agent', blank=True, default='')
    metadata = models.JSONField('附加信息', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '账户审计日志'
        verbose_name_plural = '账户审计日志'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'action']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.user.username} {self.action}'


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
    evidence_category = models.CharField(
        'LLM分类', max_length=50, blank=True, default='',
        help_text='chat_screenshot/product_order/logistics_tracking/payment_record/invoice/service_contract/work_record/communication_record/contract_document/medical_record/other'
    )
    ocr_summary = models.TextField(
        'OCR摘要', blank=True, default='',
        help_text='视觉预分类生成的100-200字摘要'
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
    field_category = models.CharField(
        '字段分类', max_length=50, blank=True, default='',
        help_text='订单信息/支付信息/物流信息/发票信息/联系信息/时间信息/其他'
    )
    source_hash = models.CharField(
        '源文本哈希', max_length=32, blank=True, default='',
        help_text='OCR文本MD5，用于缓存比对避免重复抽取'
    )
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
    datetime = models.DateTimeField('发生时间', null=True, blank=True)
    event = models.TextField('事件描述')
    related_evidence_codes = models.CharField(
        '关联证据编号', max_length=200, blank=True, default='',
        help_text='逗号分隔，如 E1,E2'
    )
    category = models.CharField(
        '事件类别', max_length=16, blank=True, default='',
        help_text='下单/付款/发货/沟通/退款/承诺/违约/其他'
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


class RespondTemplate(models.Model):
    """商家反证答辩书模板。"""

    case = models.ForeignKey(
        Case,
        related_name='respond_templates',
        on_delete=models.CASCADE,
        verbose_name='所属案件'
    )
    template_type = models.CharField(
        '答辩类型', max_length=20,
        choices=[('platform', '平台申诉版'), ('regulatory', '监管申诉版'), ('legal', '法律答辩版')],
        default='platform'
    )
    title = models.CharField('标题', max_length=200)
    content = models.TextField('答辩内容')

    class Meta:
        verbose_name = '反证答辩书'
        verbose_name_plural = '反证答辩书'
        ordering = ['id']

    def __str__(self):
        return f'[{self.get_template_type_display()}] {self.title}'


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


class CaseTypePreset(models.Model):
    """案件类型预设。

    为不同纠纷类型预置证据类型、时间线骨架与投诉模板，
    套用后可快速生成案件骨架结构。
    """

    case_type = models.CharField('纠纷类型', max_length=20, choices=Case.CASE_TYPES)
    name = models.CharField('预设名称', max_length=100)
    description = models.TextField('预设说明', blank=True, default='')
    evidence_types = models.JSONField('证据类型建议', default=list, help_text='证据类型列表')
    timeline_skeleton = models.JSONField('时间线骨架', default=list, help_text='时间线节点骨架')
    complaint_template = models.TextField('投诉模板', blank=True, default='', help_text='Jinja2 模板')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['case_type', 'id']
        verbose_name = '案件类型预设'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.name} ({self.get_case_type_display()})'


class LawArticle(models.Model):
    """法律条文（v10 新增 - RAG 知识库结构化存储）。

    数据源：国家法律法规数据库 flk.npc.gov.cn 官方文本，脚本化导入。
    真实性保证：content 存储官方原文，law_name + article_number 可溯源校验。

    设计说明：
    - 结构化数据存 MySQL（本表），向量索引存 PostgreSQL（pgvector）
    - 检索流程：PG 向量 top-k → 取 law_name+article_number → MySQL 取完整内容
    - embedding 字段不在此表，由 rag_service 管理 PG 侧的 law_article_vectors 表
    """
    # 法律分类枚举（与 design doc 一致）
    CATEGORY_CONSUMER = 'consumer_protection'      # 消费者权益保护法
    CATEGORY_ECOMMERCE = 'e-commerce'              # 电子商务法
    CATEGORY_CONTRACT = 'contract'                 # 民法典合同编
    CATEGORY_QUALITY = 'quality'                   # 产品质量法
    CATEGORY_SAFETY = 'safety'                     # 食品安全法
    CATEGORY_PRIVACY = 'privacy'                   # 个人信息保护法
    CATEGORY_PLATFORM = 'platform_rule'            # 平台规则
    CATEGORY_SERVICE = 'service'                  # 服务违约相关
    CATEGORY_MEDICAL = 'medical'                   # 医疗纠纷相关
    CATEGORY_LABOR = 'labor'                       # 劳动争议相关
    CATEGORY_OTHER = 'other'
    CATEGORY_CHOICES = [
        (CATEGORY_CONSUMER, '消费者权益保护法'),
        (CATEGORY_ECOMMERCE, '电子商务法'),
        (CATEGORY_CONTRACT, '民法典合同编'),
        (CATEGORY_QUALITY, '产品质量法'),
        (CATEGORY_SAFETY, '食品安全法'),
        (CATEGORY_PRIVACY, '个人信息保护法'),
        (CATEGORY_PLATFORM, '平台规则'),
        (CATEGORY_SERVICE, '服务违约相关'),
        (CATEGORY_MEDICAL, '医疗纠纷相关'),
        (CATEGORY_LABOR, '劳动争议相关'),
        (CATEGORY_OTHER, '其他'),
    ]

    # ===== 基础元信息 =====
    law_name = models.CharField('法律名称', max_length=100, db_index=True,
        help_text='如：中华人民共和国消费者权益保护法')
    article_number = models.CharField('条文编号', max_length=20, db_index=True,
        help_text='如：第五十五条（保持官方原文格式）')
    chapter = models.CharField('章节', max_length=100, blank=True, default='',
        help_text='如：第七章 法律责任')

    # ===== 条文内容（官方原文，不可篡改）=====
    content = models.TextField('条文内容', help_text='官方颁布原文，逐字校验')
    summary = models.CharField('条文摘要', max_length=200, blank=True, default='',
        help_text='一句话概括，用于快速检索展示')

    # ===== 适用场景标签（预过滤 + 精确匹配）=====
    category = models.CharField('法律分类', max_length=30, db_index=True,
        choices=CATEGORY_CHOICES, default=CATEGORY_OTHER)
    keywords = models.JSONField('关键词', default=list, blank=True,
        help_text='如：["退一赔三", "欺诈", "三倍赔偿"]')
    applicable_scenarios = models.JSONField('适用场景', default=list, blank=True,
        help_text='如：["虚假宣传", "假冒伪劣", "价格欺诈"]')

    # ===== 生效信息 =====
    effective_date = models.DateField('生效日期', null=True, blank=True)
    is_active = models.BooleanField('现行有效', default=True, db_index=True)

    # ===== 数据源溯源 =====
    source_url = models.URLField('数据源URL', max_length=500, blank=True, default='',
        help_text='flk.npc.gov.cn 官方法条 URL，用于溯源校验')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '法律条文'
        verbose_name_plural = verbose_name
        unique_together = [('law_name', 'article_number')]
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['law_name', 'is_active']),
        ]

    def __str__(self):
        return f'{self.law_name} {self.article_number}'

    def to_retrieval_dict(self) -> dict:
        """转换为检索结果字典（供 RAG 检索器返回）。"""
        return {
            'law_name': self.law_name,
            'article_number': self.article_number,
            'chapter': self.chapter,
            'content': self.content,
            'summary': self.summary,
            'category': self.category,
            'keywords': self.keywords,
            'applicable_scenarios': self.applicable_scenarios,
            'source_url': self.source_url,
        }


class PlatformRule(models.Model):
    """电商平台投诉规则（v10 新增 - Tools 工具集数据源）。

    存储各电商平台的投诉处理规则、服务承诺、赔偿标准。
    数据源：各平台官方规则页面，定期更新。
    """
    PLATFORM_CHOICES = [
        ('taobao', '淘宝'),
        ('tmall', '天猫'),
        ('jd', '京东'),
        ('pdd', '拼多多'),
        ('douyin', '抖音电商'),
        ('kuaishou', '快手电商'),
        ('vipshop', '唯品会'),
        ('suning', '苏宁易购'),
        ('meituan', '美团'),
        ('eleme', '饿了么'),
        ('ctrip', '携程'),
        ('keelage', 'Keep'),
        ('classin', 'ClassIn'),
        ('labor_arbitration', '劳动仲裁委'),
        ('court_small', '法院小额诉讼'),
        ('medical_dispute', '医疗纠纷调解'),
        ('other', '其他'),
    ]

    RULE_TYPE_CHOICES = [
        ('platform', '平台规则'),
        ('regulatory', '监管规则'),
        ('industry', '行业规则'),
    ]

    platform = models.CharField('平台', max_length=30, db_index=True, choices=PLATFORM_CHOICES)
    rule_type = models.CharField(
        '规则类型', max_length=20, db_index=True,
        choices=RULE_TYPE_CHOICES, default='platform'
    )
    rule_name = models.CharField('规则名称', max_length=200,
        help_text='如：延迟发货规则、假货处理规则')
    issue_type = models.CharField('问题类型', max_length=50, db_index=True,
        help_text='如：late_delivery, counterfeit, quality_issue, refund_dispute')
    content = models.TextField('规则内容', help_text='官方规则原文')
    compensation_standard = models.TextField('赔偿标准', blank=True, default='',
        help_text='如：订单金额30%赔付，最高不超过500元')
    handling_process = models.TextField('处理流程', blank=True, default='',
        help_text='投诉处理步骤')
    source_url = models.URLField('数据源URL', max_length=500, blank=True, default='')
    effective_date = models.DateField('生效日期', null=True, blank=True)
    is_active = models.BooleanField('现行有效', default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '平台规则'
        verbose_name_plural = verbose_name
        unique_together = [('platform', 'rule_name')]
        indexes = [
            models.Index(fields=['platform', 'issue_type', 'is_active']),
        ]

    def __str__(self):
        return f'[{self.get_platform_display()}] {self.rule_name}'

    def to_retrieval_dict(self) -> dict:
        return {
            'platform': self.platform,
            'platform_label': self.get_platform_display(),
            'rule_name': self.rule_name,
            'issue_type': self.issue_type,
            'content': self.content,
            'compensation_standard': self.compensation_standard,
            'handling_process': self.handling_process,
            'source_url': self.source_url,
        }
