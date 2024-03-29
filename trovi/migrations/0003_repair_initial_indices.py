# Generated by Django 3.2.9 on 2021-12-20 19:16

import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trovi", "0002_add_initial_indexes_and_nullability"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="artifactproject",
            name="urn__iexact",
        ),
        migrations.RemoveIndex(
            model_name="artifacttag",
            name="tag__iexact",
        ),
        migrations.AddIndex(
            model_name="artifactproject",
            index=models.Index(
                django.db.models.functions.text.Lower("urn"),
                name="artifact_project__urn__iexact",
            ),
        ),
        migrations.AddIndex(
            model_name="artifacttag",
            index=models.Index(
                django.db.models.functions.text.Lower("tag"), name="tag__iexact"
            ),
        ),
        migrations.AddIndex(
            model_name="artifactversion",
            index=models.Index(
                django.db.models.functions.text.Lower("contents_urn"),
                name="version__contents_urn__iexact",
            ),
        ),
    ]
