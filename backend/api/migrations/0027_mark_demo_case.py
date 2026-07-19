# Data migration: mark case id=3 as demo
from django.db import migrations


def mark_demo_case(apps, schema_editor):
    Case = apps.get_model('api', 'Case')
    Case.objects.filter(pk=3).update(is_demo=True)


def unmark_demo_case(apps, schema_editor):
    Case = apps.get_model('api', 'Case')
    Case.objects.filter(pk=3).update(is_demo=False)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0026_case_is_demo'),
    ]

    operations = [
        migrations.RunPython(mark_demo_case, unmark_demo_case),
    ]
