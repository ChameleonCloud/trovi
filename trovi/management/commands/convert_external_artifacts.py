import re
from collections import Counter
from typing import Optional
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from trovi.models import ArtifactVersion, ArtifactVersionSetup
from util.urn import git_contents_urn, parse_contents_urn

SetupType = ArtifactVersionSetup.ArtifactVersionSetupType
ZENODO_RECORD = re.compile(r"^https?://(?:www\.)?zenodo\.org/records?/(\d+)(?:[/?#]|$)")
ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar")


class Skip(Exception):
    """The artifact can't be converted now, for the reason in the message"""


def contents_urn(source_url: str) -> Optional[str]:
    """
    Returns contents to launch for an artifact crawled from source_url: its git
    repository, or the one archive in its Zenodo record. Returns None if it has
    neither, and raises Skip if Zenodo can't be reached.
    """
    if urn := git_contents_urn(source_url):
        return urn
    match = ZENODO_RECORD.match(source_url)
    if not match:
        return None
    record = f"https://zenodo.org/records/{match[1]}"
    try:
        response = requests.get(
            f"https://zenodo.org/api/records/{match[1]}", timeout=30
        )
        response.raise_for_status()
        keys = [f["key"] for f in response.json()["files"]]
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        raise Skip(f"looking up {record} failed: {e}")
    archives = [key for key in keys if key.lower().endswith(ARCHIVE_SUFFIXES)]
    if len(archives) != 1:
        return None
    return f"urn:trovi:contents:http:{record}/files/{quote(archives[0])}?download=1"


class Command(BaseCommand):
    help = (
        "Convert crawled artifacts that launch through the Jupyter deployment "
        "notebook into single node setups whose contents are their git repository "
        "or Zenodo archive. Those with neither keep only their source as contents."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Don't save changes, just print what would be done.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        counts = Counter()
        # So a dry run catches two artifacts that share contents, too
        claimed = set()
        setups = ArtifactVersionSetup.objects.filter(
            type=SetupType.SOURCE_CODE,
            arguments__url=settings.ARTIFACT_JUPYTERHUB_DEFAULT_URL,
        ).select_related("artifact_version")
        for setup in setups:
            version = setup.artifact_version
            source_url = setup.arguments.get("repo_url", "")
            try:
                urn = contents_urn(source_url)
                launchable = urn is not None
                # Otherwise it's only listed, with its source as the contents
                urn = urn or f"urn:trovi:contents:http:{source_url}"
                # Contents URNs are unique, as the API enforces when creating versions
                duplicate = ArtifactVersion.objects.filter(contents_urn__iexact=urn)
                if urn.lower() in claimed or duplicate.exclude(pk=version.pk).exists():
                    raise Skip(f"{urn} is taken")
            except Skip as e:
                counts["skipped"] += 1
                self.stdout.write(f"Skip {version.artifact_id}: {e}")
                continue

            claimed.add(urn.lower())
            counts[parse_contents_urn(urn)["provider"] if launchable else "listed"] += 1
            self.stdout.write(
                f"{version.artifact_id}: {version.contents_urn} -> {urn}"
                + ("" if launchable else ", with no setup")
            )
            if not dry_run:
                # Queryset updates, so the artifacts don't look newly updated
                with transaction.atomic():
                    ArtifactVersion.objects.filter(pk=version.pk).update(
                        contents_urn=urn
                    )
                    setup_query = ArtifactVersionSetup.objects.filter(pk=setup.pk)
                    if launchable:
                        setup_query.update(type=SetupType.SINGLE_NODE, arguments={})
                    else:
                        setup_query.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Would convert' if dry_run else 'Converted'} "
                f"{counts['git']} to git and {counts['http']} to HTTP contents, "
                f"and {counts['listed']} to listings with no setup; "
                f"skipped {counts['skipped']}."
            )
        )
