# 为 Evidence 添加 updated_at 字段以支持 mask_service._scan_signature 缓存签名。
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_mark_demo_case'),
    ]

    operations = [
        migrations.AddField(
            model_name='evidence',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='更新时间'),
        ),
    ]
