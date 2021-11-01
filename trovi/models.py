import secrets

import uuid as uuid
from django.core import validators
from django.db import models
from django.utils.translation import gettext_lazy as _

from fields import URNField


class Artifact(models.Model):
    """
    Represents artifacts
    These could be research projects, Zenodo depositions, etc.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Descriptive information
    title = models.CharField(max_length=70)
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
        validators=[
            validators.MinValueValidator(0),
        ],
    )
    repro_access_hours = models.IntegerField(null=True)

    # Sharing metadata
    class Visibility(models.TextChoices):
        PUBLIC = _("public")
        PRIVATE = _("private")

    visibility = models.CharField(
        max_length=max(len(v) for v, _ in Visibility.choices),
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
    )
    sharing_key = models.CharField(
        max_length=32, null=True, default=lambda: secrets.token_urlsafe(nbytes=32)
    )


class ArtifactVersion(models.Model):
    """Represents a single published version of an artifact"""

    slug = models.SlugField(primary_key=True, max_length=12)

    artifact = models.ForeignKey(Artifact, models.CASCADE, related_name="versions")
    created_at = models.DateTimeField(auto_now_add=True)
    contents_urn = URNField(max_length=255)

    @property
    def access_count(self) -> int:
        """
        Shortcut for determining how many times an artifact version has been launched
        :return: The number of LAUNCH events for this artifact version
        """
        return self.events.filter(event_type=ArtifactEvent.EventType.LAUNCH).count()


class ArtifactEvent(models.Model):
    """Represents an event occurring on an artifact"""

    class EventType(models.TextChoices):
        LAUNCH = _("launch")
        CITE = _("cite")
        FORK = _("fork")

    # The artifact version this event is for
    artifact_version = models.ForeignKey(
        ArtifactVersion, models.CASCADE, related_name="events"
    )

    # The type of event
    event_type = models.CharField(
        max_length=max(len(key) for key, _ in EventType.choices),
        choices=EventType.choices,
    )
    # The user who initiated the event
    event_origin = URNField(max_length=255, null=True)

    # The time at which the event occurred
    timestamp = models.DateTimeField(auto_now_add=True)


class ArtifactTag(models.Model):
    """Represents a searchable and sortable tag which can be applied to any artifact"""

    artifact = models.ForeignKey(Artifact, models.CASCADE, related_name="tags")
    tag = models.CharField(max_length=32, unique=True)


class ArtifactAuthor(models.Model):
    """Represents an author of an artifact"""

    artifact = models.ForeignKey(Artifact, models.CASCADE, related_name="authors")
    full_name = models.CharField(max_length=200)
    affiliation = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(max_length=254)


class ArtifactProject(models.Model):
    """Represents the project associated with an artifact"""

    artifact = models.ForeignKey(
        Artifact, models.CASCADE, related_name="linked_projects"
    )
    urn = URNField(max_length=255, unique=True)


class ArtifactLink(models.Model):
    """Represents a piece of data linked to an artifact"""

    artifact_version = models.ForeignKey(
        ArtifactVersion, models.CASCADE, related_name="links"
    )
    urn = URNField(max_length=255)
    label = models.TextField(max_length=40)
    verified_at = models.DateTimeField(auto_now=True)
    verified = models.BooleanField(default=False)
