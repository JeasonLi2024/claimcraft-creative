# -*- coding: utf-8 -*-
"""Generated migration: add category field to TimelineNode."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_casetypepreset_alter_timelinenode_datetime'),
    ]

    operations = [
        migrations.AddField(
            model_name='timelinenode',
            name='category',
            field=models.CharField(
                blank=True,
                default='',
                help_text='下单/付款/发货/沟通/退款/承诺/违约/其他',
                max_length=16,
                verbose_name='事件类别',
            ),
        ),
    ]
