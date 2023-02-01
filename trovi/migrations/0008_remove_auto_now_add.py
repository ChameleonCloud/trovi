# Generated by Django 4.0.3 on 2022-03-25 00:43

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trovi", "0007_artifact_access_count"),
    ]

    operations = [
        migrations.AlterField(
            model_name="artifact",
            name="created_at",
            field=models.DateTimeField(
                db_index=True, default=django.utils.timezone.now, editable=False
            ),
        ),
        migrations.AlterField(
            model_name="artifactversion",
            name="created_at",
            field=models.DateTimeField(
                default=django.utils.timezone.now, editable=False
            ),
        ),
    ]
