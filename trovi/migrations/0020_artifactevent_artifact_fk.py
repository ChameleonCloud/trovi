from django.db import migrations, models
import django.db.models.deletion


def backfill_artifact(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            UPDATE trovi_artifactevent
            SET artifact_id = (
                SELECT artifact_id FROM trovi_artifactversion
                WHERE trovi_artifactversion.id = trovi_artifactevent.artifact_version_id
            )
            WHERE artifact_version_id IS NOT NULL
        """)


class Migration(migrations.Migration):

    dependencies = [
        ("trovi", "0019_artifactevent_composite_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="artifactevent",
            name="artifact",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="events",
                to="trovi.artifact",
            ),
        ),
        migrations.AlterField(
            model_name="artifactevent",
            name="artifact_version",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="events",
                to="trovi.artifactversion",
            ),
        ),
        migrations.RunPython(backfill_artifact, reverse_code=migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="artifactevent",
            index=models.Index(
                fields=["artifact", "event_type", "event_origin"],
                name="ae_artifact_type_origin_idx",
            ),
        ),
    ]
