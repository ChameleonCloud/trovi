import base64
import secrets
import uuid as uuid
from typing import Optional, Union

from django.conf import settings
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
from django.db.models.functions import Lower
from django.db.models.signals import post_save, post_delete
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError as DRFValidationError

from trovi.common.tokens import JWT
from trovi.fields import URNField
from util.urn import parse_contents_urn


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
    created_at = models.DateTimeField(
        default=timezone.now, editable=False, db_index=True
    )
    updated_at = models.DateTimeField(auto_now=True, editable=False, db_index=True)

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

    def save(self, *args, **kwargs) -> "Artifact":
        # For forced updates, the datetime is received as a string.
        # This ensures a datetime is stored
        if isinstance(self.created_at, str):
            try:
                self.created_at = timezone.datetime.strptime(
                    self.created_at, settings.DATETIME_FORMAT
                ).astimezone(timezone.get_current_timezone())
            except ValueError as e:
                raise DRFValidationError(str(e)) from e
        return super(Artifact, self).save(*args, **kwargs)

    def is_public(self) -> bool:
        return self.visibility == Artifact.Visibility.PUBLIC

    def doi_versions(self) -> models.QuerySet:
        """
        Returns all versions whose contents are associated with a DOI

        TODO not a great long-term solution. If there is ever a backend which allows
             user-defined IDs or something like that, this is not a guaranteed
             correct solution
        """
        return self.versions.filter(contents_urn__contains="zenodo")

    def has_doi(self) -> bool:
        """
        True if this artifact has at least one version whose contents are associated
        with a DOI
        """
        return self.doi_versions().exists()

    def has_admin(self, token: Optional[Union[JWT, str]]) -> bool:
        """
        Reports whether a user has the role of Administrator on this Artifact.
        The user string should be in the form of a user URN
        """
        if isinstance(token, JWT):
            urn = token.to_urn()
        else:
            urn = token
        return (
            token
            and self.roles.filter(
                user=urn, role=ArtifactRole.RoleType.ADMINISTRATOR
            ).exists()
        )

    def has_collaborator(self, token: Optional[JWT]) -> bool:
        """
        Reports whether a user has the role of Collaborator on this Artifact.
        The user string should be in the form of a user URN
        """
        return (
            token
            and self.roles.filter(
                user=token.to_urn(), role=ArtifactRole.RoleType.COLLABORATOR
            ).exists()
        )

    def can_be_edited_by(self, token: Optional[JWT]) -> bool:
        """
        Reports whether a user has permission to edit an Artifact.
        The user string should be in the form of a user URN
        """
        return (
            token
            and self.roles.filter(
                user=token.to_urn(),
                role__in=(
                    ArtifactRole.RoleType.COLLABORATOR,
                    ArtifactRole.RoleType.ADMINISTRATOR,
                ),
            ).exists()
        )

    def gives_permission_to(self, token: Optional[JWT]) -> bool:
        """
        Reports whether a user has any elevated permissions on an artifact
        The user string should be in the form of a user URN
        """
        return (
            token
            and self.roles.filter(
                user=token.to_urn(), role__in=ArtifactRole.RoleType.values
            ).exists()
        )

    def can_be_viewed_by(self, token: Optional[JWT]) -> bool:
        """
        Reports whether a user has permission to view an artifact
        The user string should be in the form of a user URN
        """
        return (
            self.is_public()
            or self.has_doi()
            or (token and self.can_be_edited_by(token))
        )

    def can_be_deleted_by(self, token: JWT) -> bool:
        """
        Reports whether a user has permission to delete an artifact
        The user string should be in the form of a user URN
        """
        return token and token.to_urn() == self.owner_urn


class ArtifactVersion(models.Model):
    """Represents a single published version of an artifact"""

    class Meta:
        indexes = [
            models.Index(Lower("contents_urn"), name="version__contents_urn__iexact")
        ]

    artifact = models.ForeignKey(
        Artifact, models.CASCADE, related_name="versions", null=True
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    contents_urn = URNField(max_length=settings.URN_MAX_CHARS, null=True)

    slug = models.SlugField(max_length=settings.SLUG_MAX_CHARS, editable=False)

    @property
    def access_count(self) -> int:
        """
        Shortcut for determining how many times an artifact version has been launched
        :return: The number of LAUNCH events for this artifact version
        """
        return self.events.filter(event_type=ArtifactEvent.EventType.LAUNCH).count()

    @property
    def unique_access_count(self) -> int:
        """
        Shortcut for determining how many unique origins an artifact version
        has been launched by
        :return: The number of unique urns for LAUNCH events for this artifact
        version
        """
        return (
            self.events.filter(event_type=ArtifactEvent.EventType.LAUNCH)
            .values("event_origin")
            .distinct()
            .count()
        )

    @property
    def unique_cell_execution_count(self) -> int:
        """
        Shortcut for determining how many unique origins an artifact version
        has had cell executions
        :return: The number of unique urns for CELL_EXECUTION events for this artifact
        version
        """
        return (
            self.events.filter(event_type=ArtifactEvent.EventType.CELL_EXECUTION)
            .values("event_origin")
            .distinct()
            .count()
        )

    def has_doi(self) -> bool:
        """
        Determines if this version has a DOI (Digital Object Identifier), in which
        case it must be treated specially (cannot be deleted)
        """
        # A Zenodo URN should look like "urn:trovi:contents:zenodo:<doi>"
        urn_info = parse_contents_urn(self.contents_urn)
        return urn_info["provider"] == "zenodo"

    def can_be_viewed_by(self, token: Optional[JWT]) -> bool:
        """
        Reports whether a user has permission to view an ArtifactVersion
        The user string should be in the form of a user URN
        """
        return (
            # Private Artifacts are always publicly visible if any of their versions \
            # have a DOI.
            # When querying the versions for those Artifacts, we will only display
            # versions which have a DOI to public users. Non-DOI versions will remain
            # hidden. That is the reason why we don't just defer this entire check to
            # the Artifact itself.
            self.has_doi()
            or self.artifact.is_public()
            or (
                token
                and self.artifact.roles.filter(
                    user=token.to_urn(),
                    role__in=(
                        ArtifactRole.RoleType.ADMINISTRATOR,
                        ArtifactRole.RoleType.COLLABORATOR,
                    ),
                ).exists()
            )
        )

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
                    versions_today_query = instance.artifact.versions.filter(
                        created_at__date=instance.created_at.date(),
                    ).select_for_update()
                    versions_today = versions_today_query.exclude(
                        slug__exact=""
                    ).count()
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

    def save(self, *args, **kwargs) -> "ArtifactVersion":
        # For forced updates, the datetime is received as a string.
        # This ensures a datetime is stored
        if isinstance(self.created_at, str):
            try:
                self.created_at = timezone.datetime.strptime(
                    self.created_at, settings.DATETIME_FORMAT
                ).astimezone(timezone.get_current_timezone())
            except ValueError as e:
                raise DRFValidationError(str(e)) from e
        if self.artifact:
            self.artifact.updated_at = timezone.now()
            self.artifact.save()
        return super(ArtifactVersion, self).save(*args, **kwargs)


class ArtifactVersionMigration(models.Model):
    """
    Holds metadata related to an Artifact Version storage migration
    """

    class MigrationBackends(models.TextChoices):
        CHAMELEON = _("chameleon")
        ZENODO = _("zenodo")

    class MigrationStatus(models.TextChoices):
        QUEUED = _("queued")
        IN_PROGRESS = _("in_progress")
        SUCCESS = _("success")
        ERROR = _("error")

    artifact_version = models.ForeignKey(
        ArtifactVersion, models.CASCADE, related_name="migrations"
    )

    # The current status of the migration
    status = models.CharField(
        choices=MigrationStatus.choices,
        max_length=max(len(c) for c in MigrationStatus.values),
        default=MigrationStatus.QUEUED,
    )
    # A more detailed description of the status
    message = models.CharField(max_length=140)
    # The percentage (0..1) completeness of the migration
    message_ratio = models.FloatField(
        default=0.0,
        validators=[validators.MaxValueValidator(1), validators.MinValueValidator(0)],
    )
    # The storage backend to which the version will be migrated
    backend = models.CharField(
        choices=MigrationBackends.choices,
        max_length=max(len(c) for c in MigrationBackends.values),
        editable=False,
    )
    # The URN from which the version was migrated
    source_urn = URNField(max_length=settings.URN_MAX_CHARS, editable=False)
    # The URN to which the version has been migrated
    destination_urn = URNField(max_length=settings.URN_MAX_CHARS, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)


class ArtifactEvent(models.Model):
    """Represents an event occurring on an artifact"""

    class EventType(models.TextChoices):
        LAUNCH = _("launch")
        CITE = _("cite")
        FORK = _("fork")
        CELL_EXECUTION = _("cell_execution")

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


class ArtifactRole(models.Model):
    """Describes the role a user has on an Artifact.
    This defines the user's permissions to interact with the Artifact
    in various ways."""

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["artifact", "user", "role"],
                name="artifact_role_unique_constraint",
            )
        ]

    class RoleType(models.TextChoices):
        ADMINISTRATOR = _("administrator")
        COLLABORATOR = _("collaborator")

    artifact = models.ForeignKey(Artifact, models.CASCADE, related_name="roles")
    user = URNField(max_length=settings.URN_MAX_CHARS)
    assigned_by = URNField(max_length=settings.URN_MAX_CHARS)
    role = models.CharField(
        choices=RoleType.choices, max_length=max(len(c) for c in RoleType.values)
    )


class ArtifactVersionSetup(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["artifact_version"],
                name="artifact_version_setup_unique_constraint",
            )
        ]

    class ArtifactVersionSetupType(models.TextChoices):
        JUPYTERHUB = _("jupyterhub")
        ISOLATED_JUPYTER = _("isolated_jupyter")

    artifact_version = models.ForeignKey(
        ArtifactVersion, models.CASCADE, related_name="setupSteps"
    )
    type = models.CharField(choices=ArtifactVersionSetupType.choices, max_length=255)
    arguments = models.JSONField()


# Signals
post_save.connect(ArtifactVersion.generate_slug, sender=ArtifactVersion)
post_save.connect(ArtifactEvent.incr_access_count, sender=ArtifactEvent)
post_delete.connect(ArtifactVersion.delete_access_count, sender=ArtifactVersion)
