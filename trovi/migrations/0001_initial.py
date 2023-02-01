# Generated by Django 3.2.9 on 2021-11-23 03:51

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import trovi.fields
import trovi.models
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Artifact",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("title", models.CharField(max_length=70)),
                ("short_description", models.CharField(max_length=70)),
                ("long_description", models.TextField(max_length=5000, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner_urn",
                    trovi.fields.URNField(default="urn:foo:bar", max_length=254),
                ),
                ("is_reproducible", models.BooleanField(default=False)),
                (
                    "repro_requests",
                    models.IntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("repro_access_hours", models.IntegerField(null=True)),
                (
                    "visibility",
                    models.CharField(
                        choices=[("public", "Public"), ("private", "Private")],
                        default="private",
                        max_length=7,
                    ),
                ),
                (
                    "sharing_key",
                    models.CharField(
                        default=trovi.models.generate_sharing_key,
                        max_length=44,
                        validators=[trovi.models.validate_sharing_key],
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ArtifactVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("contents_urn", trovi.fields.URNField(max_length=254)),
                ("slug", models.SlugField(editable=False, max_length=16)),
                (
                    "artifact",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="trovi.artifact",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ArtifactTag",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("tag", models.CharField(max_length=32, unique=True)),
                (
                    "artifacts",
                    models.ManyToManyField(
                        blank=True, related_name="tags", to="trovi.Artifact"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ArtifactProject",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("urn", trovi.fields.URNField(max_length=254, unique=True)),
                (
                    "artifacts",
                    models.ManyToManyField(
                        blank=True, related_name="linked_projects", to="trovi.Artifact"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ArtifactLink",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("urn", trovi.fields.URNField(max_length=254)),
                ("label", models.TextField(max_length=40)),
                ("verified_at", models.DateTimeField(null=True)),
                ("verified", models.BooleanField(default=False)),
                (
                    "artifact_version",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="links",
                        to="trovi.artifactversion",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ArtifactEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("launch", "Launch"),
                            ("cite", "Cite"),
                            ("fork", "Fork"),
                        ],
                        max_length=6,
                    ),
                ),
                ("event_origin", trovi.fields.URNField(max_length=254, null=True)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                (
                    "artifact_version",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="trovi.artifactversion",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ArtifactAuthor",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("full_name", models.CharField(max_length=200)),
                (
                    "affiliation",
                    models.CharField(blank=True, max_length=200, null=True),
                ),
                ("email", models.EmailField(max_length=254)),
                (
                    "artifact",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="authors",
                        to="trovi.artifact",
                    ),
                ),
            ],
        ),
    ]
