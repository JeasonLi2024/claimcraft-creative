# Generated for Task 5.2.3: WorkflowArtifact.metadata 字段（迁移失败时只读标记）

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0022_add_paragraphs_to_templates_and_document_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowartifact",
            name="metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="产物级元数据（Task 5.2.3：迁移失败时写入 {readonly: True, readonly_reason: ...}）",
                verbose_name="元数据",
            ),
        ),
    ]
