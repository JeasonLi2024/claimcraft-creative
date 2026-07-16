# Generated for workflow stage pause and editable response documents.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_case_lifecycle_workflow_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='case',
            name='workflow_status',
            field=models.CharField(
                choices=[
                    ('idle', '未启动'),
                    ('running', '处理中'),
                    ('pausing', '暂停中'),
                    ('paused', '已暂停'),
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
            model_name='case',
            name='workflow_pause_requested',
            field=models.BooleanField(default=False, verbose_name='工作流请求暂停'),
        ),
        migrations.AddField(
            model_name='case',
            name='workflow_paused_after',
            field=models.CharField(
                blank=True,
                default='',
                help_text='安全暂停发生在该业务节点完成后',
                max_length=50,
                verbose_name='工作流暂停边界',
            ),
        ),
        migrations.AddField(
            model_name='respondtemplate',
            name='tone',
            field=models.CharField(
                blank=True,
                default='',
                help_text='LLM 生成的语气（firm/restrained/neutral），由工作流写入',
                max_length=20,
                verbose_name='语气',
            ),
        ),
    ]
