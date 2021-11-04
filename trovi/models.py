import secrets
import uuid as uuid
from datetime import datetime
from typing import Optional

from django.core import validators
from django.db import models
from django.db.models.signals import post_save
from django.utils.translation import gettext_lazy as _

from trovi import settings
from trovi.fields import URNField
from util.types import JSON, APIObject, APISerializable


class APIModel(models.Model):
    """
    Base model class which implements helpers for translating it between API objects
    and Django database Models
    """

    class Meta:
        abstract = True

    @property
    def api_items(self) -> APIObject:
        """
        Dict which maps the layout of an API response to the appropriate models.
        This method should be implemented for any models
        which are represented as JSON objects (as opposed to an ID) in API responses.
        """
        return {}

    def to_json(self, all_fields: bool = False) -> JSON:
        """
        Serializes a model to a valid JSON representation.

        ``all_fields`` indicates that all fields should be included in the output
        rather than just those indicated by api_items
        """
        if all_fields:
            fields = {
                field.name: self._meta.get_field(field)
                for field in self._meta.fields + self._meta.many_to_many
            }
        else:
            fields = self.api_items
        return {
            name: self._serialize_api_item(item, all_fields)
            for name, item in fields.items()
        }

    def _serialize_api_item(
        self, item: APISerializable, all_fields: bool
    ) -> Optional[JSON]:
        """
        Takes a value that is intended to be returned in an API response,
        and serializes it to a valid JSON value.
        """
        if isinstance(item, models.Field):
            return self.serializable_value(item.name)
        elif isinstance(item, models.Manager):
            return [
                model.to_json(all_fields=all_fields)
                if isinstance(model, APIModel)
                else self.serializable_value(item.name)
                for model in item.all()
            ]
        elif isinstance(item, dict):
            return {k: self._serialize_api_item(v, all_fields) for k, v in item.items()}
        elif isinstance(item, list):
            return [self._serialize_api_item(e, all_fields) for e in item]
        elif isinstance(item, (str, int, float)) or item is None:
            return item
        elif isinstance(item, (datetime, uuid.UUID)):
            return str(item)
        else:
            raise ValueError(
                f"Object unserializable for JSON API: {item} ({type(item)}"
            )


class Artifact(APIModel):
    """
    Represents artifacts
    These could be research projects, Zenodo depositions, etc.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Descriptive information
    title = models.CharField(max_length=settings.ARTIFACT_TITLE_MAX_CHARS)
    short_description = models.CharField(
        max_length=settings.ARTIFACT_SHORT_DESCRIPTION_MAX_CHARS, blank=True, null=True
    )
    long_description = models.TextField(
        max_length=settings.ARTIFACT_LONG_DESCRIPTION_MAX_CHARS
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

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

    @property
    def api_items(self) -> APIObject:
        return {
            "id": self.uuid,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "title": self.title,
            "short_description": self.short_description,
            "long_description": self.long_description,
            "tags": self.tags,
            "authors": self.authors,
            "visibility": self.visibility,
            "linked_projects": self.linked_projects,
            "reproducibility": {
                "enable_requests": self.is_reproducible,
                "access_hours": self.repro_access_hours,
            },
            "versions": self.versions,
        }


class ArtifactVersion(APIModel):
    """Represents a single published version of an artifact"""

    artifact = models.ForeignKey(Artifact, models.CASCADE, related_name="versions")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    contents_urn = URNField(max_length=settings.URN_MAX_CHARS)

    slug = models.SlugField(max_length=settings.SLUG_MAX_CHARS, editable=False)

    @property
    def access_count(self) -> int:
        """
        Shortcut for determining how many times an artifact version has been launched
        :return: The number of LAUNCH events for this artifact version
        """
        return self.events.filter(event_type=ArtifactEvent.EventType.LAUNCH).count()

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
            versions_today = ArtifactVersion.objects.filter(
                artifact__created_at__year=instance.created_at.year,
                artifact__created_at__month=instance.created_at.month,
                artifact__created_at__day=instance.created_at.day,
            ).count()
            if versions_today:
                time_stamp += f".{versions_today}"
            instance.slug = time_stamp
            instance.save()

    @property
    def api_items(self) -> APIObject:
        return {
            "slug": self.slug,
            "created_at": self.created_at,
            "contents": {
                "urn": self.contents_urn,
            },
            "metrics": {
                "access_count": self.access_count,
            },
            "links": self.links,
        }


class ArtifactEvent(APIModel):
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
    event_origin = URNField(max_length=settings.URN_MAX_CHARS, null=True)

    # The time at which the event occurred
    timestamp = models.DateTimeField(auto_now_add=True, editable=False)


class ArtifactTag(APIModel):
    """Represents a searchable and sortable tag which can be applied to any artifact"""

    artifacts = models.ManyToManyField(Artifact, related_name="tags")
    tag = models.CharField(max_length=settings.ARTIFACT_TAG_MAX_CHARS, unique=True)

    def to_json(self, all_fields: bool = False) -> JSON:
        if all_fields:
            return super(ArtifactTag, self).to_json(all_fields)
        else:
            return str(self.tag)


class ArtifactAuthor(APIModel):
    """Represents an author of an artifact"""

    artifact = models.ForeignKey(Artifact, models.CASCADE, related_name="authors")
    full_name = models.CharField(max_length=settings.ARTIFACT_AUTHOR_NAME_MAX_CHARS)
    affiliation = models.CharField(
        max_length=settings.ARTIFACT_AUTHOR_AFFILIATION_MAX_CHARS, blank=True, null=True
    )
    email = models.EmailField(max_length=settings.EMAIL_ADDRESS_MAX_CHARS)

    @property
    def api_items(self) -> APIObject:
        return {
            "name": self.full_name,
            "affiliation": self.affiliation,
            "email": self.email,
        }


class ArtifactProject(APIModel):
    """Represents the project associated with an artifact"""

    artifact = models.ManyToManyField(Artifact, related_name="linked_projects")
    urn = URNField(max_length=settings.URN_MAX_CHARS, unique=True)

    def to_json(self, all_fields: bool = False) -> JSON:
        if all_fields:
            return super(ArtifactProject, self).to_json(all_fields)
        else:
            return str(self.urn)


class ArtifactLink(APIModel):
    """Represents a piece of data linked to an artifact"""

    artifact_version = models.ForeignKey(
        ArtifactVersion, models.CASCADE, related_name="links"
    )
    urn = URNField(max_length=settings.URN_MAX_CHARS)
    label = models.TextField(max_length=settings.ARTIFACT_LINK_LABEL_MAX_CHARS)
    verified_at = models.DateTimeField(null=True)
    verified = models.BooleanField(default=False)

    @property
    def api_items(self) -> APIObject:
        return {
            "label": self.label,
            "verified": self.verified,
            "urn": self.urn,
        }


# Signals
post_save.connect(ArtifactVersion.generate_slug, sender=ArtifactVersion)
