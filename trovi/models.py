import secrets
import uuid as uuid

from django.core import validators
from django.db import models
from django.utils.translation import gettext_lazy as _

from trovi.fields import URNField
from util.types import JSON, APIFormat, APISerializable


class APIModel(models.Model):
    """
    Base model class which implements helpers for translating it between API objects
    and Django database Models
    """

    class Meta:
        abstract = True

    @property
    def api_items(self) -> APIFormat:
        """
        Dict which maps the layout of an API response to the appropriate models.
        This method should be implemented for any models
        which are represented as JSON objects (as opposed to an ID) in API responses.
        """
        return {}

    def to_json(self) -> JSON:
        """
        Serializes a model to a valid JSON representation.
        """
        return {
            name: self._serialize_api_item(item)
            for name, item in self.api_items.items()
        }

    def _serialize_api_item(self, item: APISerializable) -> JSON:
        """
        Takes a value that is intended to be returned in an API response,
        and serializes it to a valid JSON value.
        """
        if isinstance(item, models.Field):
            return self.serializable_value(item.name)
        elif isinstance(item, models.Manager):
            return [
                model.to_json()
                if isinstance(model, APIModel)
                else self.serializable_value(item.name)
                for model in item.all()
            ]
        elif isinstance(item, dict):
            return {k: self._serialize_api_item(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [self._serialize_api_item(e) for e in item]
        elif type(item) in (str, int, float, None):
            return item
        elif hasattr(item, "__str__"):
            return str(item)
        else:
            raise ValueError(f"Object unserializable for JSON API: {item}")


class Artifact(APIModel):
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

    @property
    def api_items(self) -> APIFormat:
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

    @property
    def api_items(self) -> APIFormat:
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


class ArtifactTag(APIModel):
    """Represents a searchable and sortable tag which can be applied to any artifact"""

    artifact = models.ForeignKey(Artifact, models.CASCADE, related_name="tags")
    tag = models.CharField(max_length=32, unique=True)

    def to_json(self) -> JSON:
        return str(self.tag)


class ArtifactAuthor(APIModel):
    """Represents an author of an artifact"""

    artifact = models.ForeignKey(Artifact, models.CASCADE, related_name="authors")
    full_name = models.CharField(max_length=200)
    affiliation = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(max_length=254)

    @property
    def api_items(self) -> APIFormat:
        return {
            "name": self.full_name,
            "affiliation": self.affiliation,
            "email": self.email,
        }


class ArtifactProject(APIModel):
    """Represents the project associated with an artifact"""

    artifact = models.ForeignKey(
        Artifact, models.CASCADE, related_name="linked_projects"
    )
    urn = URNField(max_length=255, unique=True)

    def to_json(self) -> JSON:
        return str(self.urn)


class ArtifactLink(APIModel):
    """Represents a piece of data linked to an artifact"""

    artifact_version = models.ForeignKey(
        ArtifactVersion, models.CASCADE, related_name="links"
    )
    urn = URNField(max_length=255)
    label = models.TextField(max_length=40)
    verified_at = models.DateTimeField(auto_now=True)
    verified = models.BooleanField(default=False)

    @property
    def api_items(self) -> APIFormat:
        return {
            "label": self.label,
            "verified": self.verified,
            "urn": self.urn,
        }
