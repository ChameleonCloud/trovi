from django.core.management.base import BaseCommand
from trovi.models import ArtifactVersion


class Command(BaseCommand):
    help = "Fix artifact versions with duplicate slugs, preventing deletion."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Don't save changes, just print what would be done."
        )


    def handle(self, *args, **options):
        dry_run = options['dry_run']
        # Get all distinct (artifact, slug) pairs
        distinct_pairs = (
            ArtifactVersion.objects.values("artifact", "slug").distinct()
        )

        # Get the results for all pairs
        for pair in distinct_pairs:
            versions = ArtifactVersion.objects.filter(
                artifact=pair["artifact"],
                slug=pair["slug"]
            ).order_by("created_at")

            if len(versions) > 1:
                self.stdout.write(self.style.SUCCESS(
                    f"\nArtifact ID: {pair['artifact']}, Slug: {pair['slug']}"
                ))
                for (i, version) in enumerate(versions):
                    suffix = ""
                    if (i):
                        suffix = f".{i}"
                    new_slug = f"\t{version.slug}{suffix}"
                    self.stdout.write(f"{version.slug} -> {new_slug}")
                    if not dry_run:
                        version.slug = new_slug
                        version.save()
