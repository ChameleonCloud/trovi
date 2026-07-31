from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trovi", "0018_artifact_citation_crawlrequest_autocrawledartifact_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="artifactevent",
            index=models.Index(
                fields=["artifact_version", "event_type", "event_origin"],
                name="ae_version_type_origin_idx",
            ),
        ),
    ]
