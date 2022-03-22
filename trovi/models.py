import base64
import secrets
import uuid as uuid

from django.conf import settings
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
from django.db.models.functions import Lower
from django.db.models.signals import post_save, post_delete
from django.utils.translation import gettext_lazy as _

from trovi.fields import URNField


def generate_sharing_key() -> str:
    return secrets.token_urlsafe(nbytes=settings.SHARING_KEY_LENGTH)


def validate_sharing_key(k: bytes):
    if not len(base64.decodebytes(k)) == settings.SHARING_KEY_LENGTH:
        raise ValidationError(f"Invalid sharing key: {k}")


class Artifact(models.Model):
    """
    Represents artifacts
    These could be research projects, Zenodo depositions, etc.
    """

    class Meta:
        indexes = [
            models.Index("created_at", name="artifact__created_at"),
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Descriptive information
    title = models.CharField(max_length=settings.ARTIFACT_TITLE_MAX_CHARS)
    short_description = models.CharField(
        max_length=settings.ARTIFACT_SHORT_DESCRIPTION_MAX_CHARS
    )
    long_description = models.TextField(
        max_length=settings.ARTIFACT_LONG_DESCRIPTION_MAX_CHARS, null=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    # Author who owns this Artifact
    owner_urn = URNField(max_length=settings.URN_MAX_CHARS)

    # Experiment reproduction metadata
    is_reproducible = models.BooleanField(default=False)
    repro_requests = models.IntegerField(
        default=0,
        validators=[
            validators.MinValueValidator(0),
        ],
    )
    repro_access_hours = models.IntegerField(null=True)

    # Hidden field which tracks how many times this artifact has been launched
    access_count = models.PositiveIntegerField(default=0)

    # Sharing metadata
    class Visibility(models.TextChoices):
        PUBLIC = _("public")
        PRIVATE = _("private")

    visibility = models.CharField(
        max_length=max(len(v) for v, _ in Visibility.choices),
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
        db_index=True,
    )
    sharing_key = models.CharField(
        # Since sharing keys are base64 encoded, we use the base64 length formula here
        max_length=(((4 * settings.SHARING_KEY_LENGTH) // 3) + 3) & ~3,
        default=generate_sharing_key,
        validators=[validate_sharing_key],
    )


class ArtifactVersion(models.Model):
    """Represents a single published version of an artifact"""

    class Meta:
        indexes = [
            models.Index(Lower("contents_urn"), name="version__contents_urn__iexact")
        ]

    artifact = models.ForeignKey(
        Artifact, models.CASCADE, related_name="versions", null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    contents_urn = URNField(max_length=settings.URN_MAX_CHARS, null=True)

    slug = models.SlugField(max_length=settings.SLUG_MAX_CHARS, editable=False)

    @property
    def access_count(self) -> int:
        """
        Shortcut for determining how many times an artifact version has been launched
        :return: The number of LAUNCH events for this artifact version
        """
        return self.events.filter(event_type=ArtifactEvent.EventType.LAUNCH).count()

    def has_doi(self) -> bool:
        """
        Determines if this version has a DOI (Digital Object Identifier), in which
        case it must be treated specially (cannot be deleted)
        """
        # A Zenodo URN should look like "urn:trovi:zenodo:<doi>"
        urn_parts = self.contents_urn.split(":")
        return len(urn_parts) == 4 and urn_parts[3] == "zenodo"

    @staticmethod
    def generate_slug(instance: "ArtifactVersion", created: bool = False, **_):
        """
        Generates a slug in the format of YYYY-MM-DD((.#)?) where ".#"
        is an index starting at 1 which increments automatically for each version
        published on the same given day.

        The slug is stored in the instance's slug field and saved
        """
        if created:
            time_stamp = instance.created_at.strftime("%Y-%m-%d")
            with transaction.atomic():
                if instance.artifact:
                    versions_today = (
                        instance.artifact.versions.filter(
                            artifact__created_at__date=instance.created_at.date(),
                        )
                        .exclude(slug__exact="")
                        .select_for_update()
                        .count()
                    )
                else:
                    versions_today = 0
                if versions_today:
                    time_stamp += f".{versions_today}"
                instance.slug = time_stamp
                instance.save(update_fields=["slug"])

    @staticmethod
    def delete_access_count(instance: "ArtifactVersion", **_):
        """
        Updates the parent artifact's access_count such that it no longer counts
        accesses of the deleted version
        """
        try:
            with transaction.atomic():
                if instance.artifact:
                    instance.artifact.access_count = (
                        F("access_count") - instance.access_count
                    )
                    instance.artifact.save(update_fields=["access_count"])
        except Artifact.DoesNotExist:
            pass


class ArtifactEvent(models.Model):
    """Represents an event occurring on an artifact"""

    class EventType(models.TextChoices):
        LAUNCH = _("launch")
        CITE = _("cite")
        FORK = _("fork")

    # The artifact version this event is for
    artifact_version = models.ForeignKey(
        ArtifactVersion, models.CASCADE, related_name="events", null=True
    )

    # The type of event
    event_type = models.CharField(
        max_length=max(len(choice) for choice in EventType.values),
        choices=EventType.choices,
        db_index=True,
    )
    # The user who initiated the event
    event_origin = URNField(max_length=settings.URN_MAX_CHARS, null=True)

    # The time at which the event occurred
    timestamp = models.DateTimeField(auto_now_add=True, editable=False)

    @staticmethod
    def incr_access_count(instance: "ArtifactEvent", created: bool = False, **_):
        if created:
            try:
                with transaction.atomic():
                    if (
                        not instance.artifact_version
                        or not instance.artifact_version.artifact
                    ):
                        pass
                    if instance.event_type == ArtifactEvent.EventType.LAUNCH:
                        artifact = instance.artifact_version.artifact
                        artifact.access_count = F("access_count") + 1
                        artifact.save(update_fields=["access_count"])
            except (Artifact.DoesNotExist, ArtifactVersion.DoesNotExist):
                pass


class ArtifactTag(models.Model):
    """Represents a searchable and sortable tag which can be applied to any artifact"""

    class Meta:
        indexes = [models.Index(Lower("tag"), name="tag__iexact")]

    artifacts = models.ManyToManyField(Artifact, related_name="tags", blank=True)
    tag = models.CharField(
        max_length=settings.ARTIFACT_TAG_MAX_CHARS, unique=True, db_index=True
    )


class ArtifactAuthor(models.Model):
    """Represents an author of an artifact"""

    artifact = models.ForeignKey(
        Artifact, models.CASCADE, related_name="authors", null=True
    )
    full_name = models.CharField(max_length=settings.ARTIFACT_AUTHOR_NAME_MAX_CHARS)
    affiliation = models.CharField(
        max_length=settings.ARTIFACT_AUTHOR_AFFILIATION_MAX_CHARS, blank=True, null=True
    )
    email = models.EmailField(max_length=settings.EMAIL_ADDRESS_MAX_CHARS)


class ArtifactProject(models.Model):
    """Represents the project associated with an artifact"""

    class Meta:
        indexes = [models.Index(Lower("urn"), name="artifact_project__urn__iexact")]

    artifacts = models.ManyToManyField(
        Artifact, related_name="linked_projects", blank=True
    )
    urn = URNField(max_length=settings.URN_MAX_CHARS, unique=True)


class ArtifactLink(models.Model):
    """Represents a piece of data linked to an artifact"""

    artifact_version = models.ForeignKey(
        ArtifactVersion, models.CASCADE, related_name="links", null=True
    )
    urn = URNField(max_length=settings.URN_MAX_CHARS)
    label = models.TextField(max_length=settings.ARTIFACT_LINK_LABEL_MAX_CHARS)
    verified_at = models.DateTimeField(null=True)
    verified = models.BooleanField(default=False)


# Signals
post_save.connect(ArtifactVersion.generate_slug, sender=ArtifactVersion)
post_save.connect(ArtifactEvent.incr_access_count, sender=ArtifactEvent)
post_delete.connect(ArtifactVersion.delete_access_count, sender=ArtifactVersion)
