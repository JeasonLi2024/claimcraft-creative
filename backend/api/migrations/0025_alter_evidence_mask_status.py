from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_alter_workflowintervention_intervention_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='evidence',
            name='mask_status',
            field=models.CharField(
                choices=[
                    ('none', '未处理'),
                    ('pending', '处理中'),
                    ('done', '已完成'),
                    ('failed', '处理失败'),
                ],
                default='none',
                help_text='none/pending/done/failed',
                max_length=20,
                verbose_name='打码状态',
            ),
        ),
    ]
