# Generated for Python 3.13 / Django 4.2+

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0023_workflow_artifact_metadata'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workflowintervention',
            name='intervention_type',
            field=models.CharField(
                choices=[
                    ('quality_review', '质量审核'),
                    ('user_pause', '用户暂停'),
                    ('legal_confirmation', '法律风险确认'),
                    ('missing_information', '缺失信息补充'),
                ],
                help_text=(
                    '介入类型：quality_review / user_pause / '
                    'legal_confirmation / missing_information'
                ),
                max_length=32,
                verbose_name='介入类型',
            ),
        ),
    ]
