# Generated manually for the case lifecycle workflow redesign.
# Applied after the physical-evidence 0017 migration to keep a single migration leaf.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_add_physical_evidence_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='case',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='归档时间'),
        ),
        migrations.AddField(
            model_name='case',
            name='document_stale',
            field=models.BooleanField(default=False, verbose_name='文稿是否已过期'),
        ),
        migrations.AddField(
            model_name='case',
            name='workflow_error',
            field=models.TextField(blank=True, default='', verbose_name='工作流错误'),
        ),
        migrations.AddField(
            model_name='case',
            name='workflow_finished_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='工作流结束时间'),
        ),
        migrations.AddField(
            model_name='case',
            name='workflow_revision',
            field=models.PositiveIntegerField(default=0, verbose_name='工作流版本'),
        ),
        migrations.AddField(
            model_name='case',
            name='workflow_started_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='工作流开始时间'),
        ),
        migrations.AddField(
            model_name='case',
            name='workflow_status',
            field=models.CharField(
                choices=[
                    ('idle', '未启动'),
                    ('running', '处理中'),
                    ('waiting_review', '等待用户校正'),
                    ('succeeded', '处理完成'),
                    ('failed', '处理失败'),
                ],
                default='idle',
                max_length=20,
                verbose_name='工作流状态',
            ),
        ),
        migrations.AddField(
            model_name='casestatuslog',
            name='actor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='case_status_actions',
                to=settings.AUTH_USER_MODEL,
                verbose_name='操作人',
            ),
        ),
        migrations.AddField(
            model_name='casestatuslog',
            name='metadata',
            field=models.JSONField(blank=True, default=dict, verbose_name='扩展信息'),
        ),
        migrations.AddField(
            model_name='casestatuslog',
            name='thread_id',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='工作流线程 ID'),
        ),
        migrations.AddField(
            model_name='casestatuslog',
            name='trigger',
            field=models.CharField(
                blank=True,
                choices=[
                    ('workflow_started', '工作流启动'),
                    ('document_generated', '文稿生成'),
                    ('user_archived', '用户归档'),
                    ('user_cancelled', '用户取消'),
                    ('admin_override', '管理员调整'),
                ],
                default='',
                max_length=40,
                verbose_name='触发来源',
            ),
        ),
    ]
