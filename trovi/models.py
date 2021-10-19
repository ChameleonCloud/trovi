import secrets

from django.core import validators
from django.db import models

from fields import URNField


class Artifact(models.Model):
    """
    Represents artifacts
    These could be research projects, Zenodo depositions, etc.
    """

    # Identifiers
    id = models.IntegerField(primary_key=True)
    uuid = models.UUIDField(primary_key=True)

    # Descriptive information
    title = models.CharField(max_length=200)
    short_description = models.CharField(max_length=70, blank=True, null=True)
    long_description = models.TextField(max_length=5000)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Author who owns this Artifact
    owner_urn = URNField(max_length=255)

    # Experiment reproduction metadata
    is_reproducible = models.BooleanField(default=False)
    repro_requests = models.IntegerField(
        default=0,
        validators=[validators.MinValueValidator(0), validators.MaxValueValidator(10)],
    )
    repro_access_hours = models.IntegerField(null=True)

    # Sharing metadata
    sharing_key = models.CharField(
        max_length=32, null=True, default=lambda: secrets.token_urlsafe(nbytes=32)
    )


class ArtifactVersion(models.Model):
    """Represents a single published version of an artifact"""

    # Identifiers
    id = models.IntegerField(primary_key=True)
    slug = models.SlugField(primary_key=True, max_length=12)

    artifact_id = models.ForeignKey(
        Artifact, models.CASCADE, related_name="artifact_version"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    contents_urn = URNField(max_length=255)
    access_count = models.IntegerField(default=0)


class ArtifactTag(models.Model):
    """Represents a searchable and sortable tag which can be applied to any artifact"""

    artifact_id = models.ForeignKey(
        Artifact, models.CASCADE, related_name="artifact_tag"
    )
    tag = models.CharField(max_length=32)


class ArtifactAuthor(models.Model):
    """Represents an author of an artifact"""

    artifact_id = models.ForeignKey(
        Artifact, models.CASCADE, related_name="artifact_author"
    )
    full_name = models.CharField(max_length=200)
    affiliation = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(max_length=254)


class ArtifactProject(models.Model):
    """Represents the project associated with an artifact"""

    artifact_id = models.ForeignKey(
        Artifact, models.CASCADE, related_name="artifact_project"
    )
    urn = URNField(max_length=255)
