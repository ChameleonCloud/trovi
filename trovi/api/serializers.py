import logging
from typing import Optional, Any

import cmarkgfm as commonmark
from django.conf import settings
from django.db import transaction, IntegrityError
from drf_spectacular.utils import extend_schema_serializer
from jsonpatch import JsonPatch
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

from trovi.api.patches import ArtifactPatch
from trovi.common.exceptions import ConflictError, InvalidToken
from trovi.common.serializers import (
    JsonPatchOperationSerializer,
    URNSerializerField,
    allow_force,
    strict_schema,
    _is_valid_force_request,
)
from trovi.common.tokens import JWT
from trovi.fields import URNField
from trovi.models import (
    Artifact,
    ArtifactTag,
    ArtifactAuthor,
    ArtifactProject,
    ArtifactVersion,
    ArtifactLink,
    ArtifactEvent,
)
from util.types import JSON

LOG = logging.getLogger(__name__)

serializers.ModelSerializer.serializer_field_mapping.update(
    {URNField: URNSerializerField}
)


class ArtifactTagSerializer(serializers.ModelSerializer):
    """
    A tag which categorizes an artifact
    """

    class Meta:
        model = ArtifactTag
        fields = []

    def create(self, validated_data: dict[str, str]) -> ArtifactTag:
        tag = validated_data["tag"]
        try:
            return ArtifactTag.objects.get(tag__iexact=tag)
        except ArtifactTag.DoesNotExist:
            raise NotFound(f"Unknown tag {tag}")

    def to_representation(self, instance: ArtifactTag) -> str:
        return instance.tag

    def to_internal_value(self, data: str) -> dict:
        # We skip the super call here to avoid running into the uniqueness validator
        return {"tag": data}


class ArtifactTagSerializerWritable(serializers.ModelSerializer):
    class Meta:
        model = ArtifactTag
        exclude = ["id"]


@extend_schema_serializer(exclude_fields=["id", "artifact"])
@allow_force
@strict_schema
class ArtifactAuthorSerializer(serializers.ModelSerializer):
    """
    Description of a single artifact author
    """

    class Meta:
        model = ArtifactAuthor
        exclude = ["id"]

    def to_representation(self, instance: ArtifactAuthor) -> dict:
        return {
            "full_name": instance.full_name,
            "affiliation": instance.affiliation,
            "email": instance.email,
        }


class ArtifactProjectSerializer(serializers.ModelSerializer):
    """
    Describes a project linked to an artifact
    """

    class Meta:
        model = ArtifactProject
        fields = []

    def to_representation(self, instance: ArtifactProject) -> str:
        return instance.urn

    def to_internal_value(self, data: str) -> dict:
        return {"urn": data}

    def create(self, validated_data: dict) -> ArtifactProject:
        """
        Since all projects are unique, and can be applied to multiple ``Artifact``s,
        this class overrides the ``create`` method to return an existing project that
        matches the unique provided URN, or create one if it doesn't exist.
        """
        with transaction.atomic():
            project, _ = self.Meta.model.objects.get_or_create(
                urn__iexact=validated_data["urn"],
                defaults={"urn": validated_data["urn"]},
            )
        return project

    def validate_urn(self, urn: str) -> str:
        # TODO check if valid project
        return urn


@extend_schema_serializer(exclude_fields=["artifact_version"])
@allow_force
@strict_schema
class ArtifactLinkSerializer(serializers.ModelSerializer):
    """
    Describes an external link relevant to an artifact version
    """

    class Meta:
        model = ArtifactLink
        exclude = ["id", "verified_at"]

    verified = serializers.BooleanField(default=False, read_only=True)

    def to_representation(self, instance: ArtifactLink) -> dict:
        return {
            "label": instance.label,
            "verified": instance.verified,
            # TODO check if this is a valid resource
            "urn": instance.urn,
        }


@allow_force
@strict_schema
class ArtifactVersionContentsSerializer(serializers.Serializer):
    """
    Represents metadata regarding an artifact version's contents
    """

    urn = URNSerializerField(required=True)

    def create(self, validated_data: dict[str, JSON]) -> ArtifactVersion:
        self.instance.contents_urn = validated_data["urn"]
        with transaction.atomic():
            self.instance.save()
        return self.instance

    def update(self, _, validated_data: dict[str, JSON]) -> ArtifactVersion:
        return self.create(validated_data)

    def validate_urn(self, urn: str) -> str:
        # Since versions cannot be patched, we can skip uniqueness validation
        if self.instance:
            return urn
        if ArtifactVersion.objects.filter(contents_urn__iexact=urn).exists():
            raise ConflictError(f"Version with contents {urn} already exists.")
        # TODO check if this is a valid resource
        return urn

    def to_representation(self, instance: ArtifactVersion) -> dict[str, JSON]:
        return {"urn": instance.contents_urn}


@allow_force
@strict_schema
class ArtifactVersionMetricsSerializer(serializers.Serializer):
    """
    Describes an artifact version's metrics, which are related to events
    """

    # Translates to a launch event
    access_count = serializers.IntegerField(
        min_value=1, max_value=1000, allow_null=False, required=False
    )
    # The Trovi token of the user who initiated the event(s)
    origin = URNSerializerField(write_only=True, required=True)

    def update(
        self, instance: ArtifactVersion, validated_data: dict[str, Any]
    ) -> ArtifactVersion:
        """
        This serializer's update method is a touch different from other serializers.
        Rather than receive all the updated info, it will receive the amount by which
        to increment the metrics. The reason for this is because of how the metrics
        endpoint is designed, and that ArtifactEvents need to be created in bulk.
        If we were to use this in the way update methods are typically used, we would
        need to add the metric from the version to the amount in the request,
        and then subtract them here to determine how many events need to be created.
        This is not a huge deal, but it's unnecessary work that is confusing.
        """
        access_count = validated_data.pop("access_count", None)
        origin = validated_data["origin"]
        # We don't call bulk_create here, because it doesn't run any save signals
        # even though it persists the models to the database
        with transaction.atomic():
            for _ in range(access_count or 0):
                ArtifactEvent.objects.create(
                    event_type=ArtifactEvent.EventType.LAUNCH,
                    event_origin=origin,
                    artifact_version=instance,
                )
        instance.refresh_from_db()
        return instance

    def create(self, validated_data):
        raise NotImplementedError("Initial metrics are set automatically")

    def to_representation(self, instance: ArtifactVersion) -> dict[str, JSON]:
        return {"access_count": instance.access_count}

    def to_internal_value(self, data: dict[str, JSON]) -> dict[str, JSON]:
        """
        Performs JWT validation of the origin user and returns that user's URN
        This is done in here because DRF calls its own validators before ours :(
        """
        # We have to do a tiny bit of validation of the origin token here because
        # DRF calls its own validators before ours. So, we have to decode and turn it
        # into a URN before the serializer's validation step is run.
        # The token's signature is validated by the endpoint permissions, so
        # it does not need to repeat that step here.
        origin = data.get("origin")
        if not origin or type(origin) is not str:
            raise ValidationError({"origin": "Must be a valid JWT string"})

        try:
            origin_token = JWT.from_jws(origin, validate=False)
        except InvalidToken as e:
            exc_type = type(e)
            raise exc_type(detail={"origin": e.detail}, code=e.status_code) from e

        data["origin"] = origin_token.to_urn()
        return super(ArtifactVersionMetricsSerializer, self).to_internal_value(data)


@extend_schema_serializer(exclude_fields=["artifact"])
@allow_force
@strict_schema
class ArtifactVersionSerializer(serializers.ModelSerializer):
    """
    Describes a single version of an artifact
    """

    class Meta:
        model = ArtifactVersion
        exclude = ["id", "contents_urn"]

    slug = serializers.SlugField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    contents = ArtifactVersionContentsSerializer(required=True)
    links = ArtifactLinkSerializer(many=True, required=False)
    metrics = ArtifactVersionMetricsSerializer(read_only=True)

    def create(self, validated_data: dict) -> ArtifactVersion:
        links = validated_data.pop("links", [])
        contents = validated_data.pop("contents", {})

        with transaction.atomic():
            try:
                version = super(ArtifactVersionSerializer, self).create(validated_data)
            except IntegrityError as e:
                LOG.error(f"Failed to create ArtifactVersion: {str(e)}")
                raise e

            if links:
                link_serializer = ArtifactLinkSerializer(
                    data=links, many=True, context=self.context
                )
                link_serializer.is_valid(raise_exception=True)
                version.links.add(*link_serializer.save())

            contents_serializer = ArtifactVersionContentsSerializer(
                data=contents, instance=version, context=self.context
            )
            contents_serializer.is_valid(raise_exception=True)
            contents_serializer.save()

        return version

    def to_representation(self, instance: ArtifactVersion) -> dict:
        return {
            "slug": instance.slug,
            "created_at": instance.created_at.strftime(settings.DATETIME_FORMAT),
            "contents": ArtifactVersionContentsSerializer(instance).data,
            "metrics": ArtifactVersionMetricsSerializer(instance).data,
            "links": ArtifactLinkSerializer(instance.links.all(), many=True).data,
        }

    def to_internal_value(self, data):
        # On CreateArtifactVersion requests, the Artifact UUID is attached to
        # the view by the router, so we need to extract it from there. On
        # CreateArtifact requests, the Artifact UUID should already be inserted
        # into the data by the parent serializer in ArtifactSerializer.create
        # It is safe to retrieve the artifact from the view's kwargs,
        # as it will be overwritten by the router if the user tries to pass their own
        # kwargs
        view = self.context["view"]
        data.setdefault("artifact", view.kwargs.get("parent_lookup_artifact"))

        try:
            return super(ArtifactVersionSerializer, self).to_internal_value(data)
        except ValidationError as e:
            # This is to trap Validation errors thrown from non-existent artifacts.
            # By default, this will return a 400 error. We want to return 404 instead.
            if artifact_error := e.detail.get("artifact"):
                if any(detail.code == "does_not_exist" for detail in artifact_error):
                    raise NotFound(e.detail)
            raise e


@allow_force
@strict_schema
class ArtifactReproducibilitySerializer(serializers.Serializer):
    """
    Contains reproducibility metadata for an artifact
    """

    enable_requests = serializers.BooleanField(default=False)
    access_hours = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, default=None
    )
    requests = serializers.IntegerField(
        min_value=0,
        max_value=settings.ARTIFACT_SHARING_MAX_REPRO_REQUESTS,
        read_only=True,
    )

    def create(self, validated_data: dict[str, JSON]) -> Artifact:
        return self.update(self.instance, validated_data)

    def update(self, instance: Artifact, validated_data: dict[str, JSON]) -> Artifact:
        access_hours = validated_data["access_hours"]
        is_reproducible = validated_data["enable_requests"]

        # If access hours were removed, the artifact is not reproducible
        if not access_hours and is_reproducible:
            raise ValidationError("Must set access hours for reproducible artifact.")

        # If the artifact is not reproducible, it doesn't have access hours
        if not is_reproducible:
            access_hours = None

        instance.repro_access_hours = access_hours
        instance.is_reproducible = is_reproducible
        with transaction.atomic():
            instance.save(update_fields=["repro_access_hours", "is_reproducible"])
        return instance

    def to_representation(self, instance: Artifact) -> dict[str, JSON]:
        return {
            "enable_requests": instance.is_reproducible,
            "access_hours": instance.repro_access_hours,
            "requests": instance.repro_requests,
        }


@allow_force
@strict_schema
class ArtifactSerializer(serializers.ModelSerializer):
    """
    Represents a single artifact
    """

    class Meta:
        model = Artifact
        exclude = [
            "sharing_key",
            "access_count",
            "is_reproducible",
            "repro_access_hours",
            "repro_requests",
        ]

    uuid = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    # Related fields used for validating on writes
    tags = ArtifactTagSerializer(many=True, required=False)
    authors = ArtifactAuthorSerializer(many=True, required=False)
    linked_projects = ArtifactProjectSerializer(many=True, required=False)
    reproducibility = ArtifactReproducibilitySerializer(required=False)
    versions = ArtifactVersionSerializer(many=True, read_only=True)
    version = ArtifactVersionSerializer(required=False, write_only=True)

    @transaction.atomic
    def to_representation(self, instance: Artifact) -> dict[str, JSON]:
        artifact_json = {
            "uuid": str(instance.uuid),
            "created_at": instance.created_at.strftime(settings.DATETIME_FORMAT),
            "updated_at": instance.updated_at.strftime(settings.DATETIME_FORMAT),
            "title": instance.title,
            "short_description": instance.short_description,
            "long_description": instance.long_description,
            "tags": ArtifactTagSerializer(instance.tags.all(), many=True).data,
            "authors": ArtifactAuthorSerializer(instance.authors.all(), many=True).data,
            "owner_urn": instance.owner_urn,
            "visibility": instance.visibility,
            "linked_projects": ArtifactProjectSerializer(
                instance.linked_projects.all(), many=True
            ).data,
            "reproducibility": ArtifactReproducibilitySerializer(instance).data,
            "versions": ArtifactVersionSerializer(
                instance.versions.all(), many=True
            ).data,
        }
        if self.get_requesting_user_urn() == instance.owner_urn:
            artifact_json["sharing_key"] = instance.sharing_key
        return artifact_json

    def create(self, validated_data: dict) -> Artifact:
        # All nested fields have to be manually created, so that is done here
        tags = [t["tag"] for t in validated_data.pop("tags", [])]
        authors = validated_data.pop("authors", [])
        linked_projects = validated_data.pop("linked_projects", [])
        version = validated_data.pop("version", {})
        reproducibility = validated_data.pop("reproducibility", {})

        with transaction.atomic():
            artifact = super(ArtifactSerializer, self).create(validated_data)

            # New relationships have to be created here,
            # with the new Artifact's ID manually shoved in
            if tags:
                tag_serializer = ArtifactTagSerializer(
                    data=tags, many=True, context=self.context
                )
                tag_serializer.is_valid(raise_exception=True)
                artifact.tags.add(*tag_serializer.save())
            if authors:
                author_serializer = ArtifactAuthorSerializer(
                    data=authors, many=True, context=self.context
                )
                author_serializer.is_valid(raise_exception=True)
                artifact.authors.add(*author_serializer.save())
            if linked_projects:
                project_serializer = ArtifactProjectSerializer(
                    data=linked_projects, many=True, context=self.context
                )
                project_serializer.is_valid(raise_exception=True)
                artifact.linked_projects.add(*project_serializer.save())
            if version:
                version_serializer = ArtifactVersionSerializer(
                    data=version, context=self.context
                )
                version_serializer.is_valid(raise_exception=True)
                artifact.versions.add(version_serializer.save())
            if reproducibility:
                reproducibility_serializer = ArtifactReproducibilitySerializer(
                    data=reproducibility, instance=artifact, context=self.context
                )
                reproducibility_serializer.is_valid(raise_exception=True)
                artifact = reproducibility_serializer.save()

        return artifact

    def update(self, instance: Artifact, validated_data: dict) -> Artifact:
        # Special exception for forced updates
        # DRF bypasses the Django DB-level validation (WHY), so if an admin attempts
        # to update the Artifact's primary key, all the related fields break
        if "uuid" in validated_data:
            raise ValidationError(
                "Cannot edit Artifact UUID. Primary keys are immutable"
            )
        # All nested fields have to be manually updated, so that is done here
        authors = validated_data.pop("authors", None)
        linked_projects = validated_data.pop("linked_projects", None)
        if linked_projects is not None:
            linked_projects = [p["urn"] for p in linked_projects]
        tags = validated_data.pop("tags", None)
        if tags is not None:
            tags = [t["tag"] for t in tags]
        reproducibility = validated_data.pop("reproducibility", None)

        with transaction.atomic():
            if authors is not None:
                # Since authors are ManyToOne, and it's hard to tell what is an update
                # vs removal, we just rewrite all the authors
                instance.authors.clear()
                author_serializer = ArtifactAuthorSerializer(
                    data=authors, many=True, context=self.context
                )
                author_serializer.is_valid(raise_exception=True)
                instance.authors.add(*author_serializer.save())

            if tags is not None:
                tag_serializer = ArtifactTagSerializer(
                    data=tags, many=True, context=self.context
                )
                tag_serializer.is_valid(raise_exception=True)
                instance.tags.clear()
                instance.tags.add(*tag_serializer.save())

            if linked_projects is not None:
                instance.linked_projects.clear()
                # Add new/updated projects to the relationship
                project_serializer = ArtifactProjectSerializer(
                    data=linked_projects, many=True, context=self.context
                )
                project_serializer.is_valid(raise_exception=True)
                for project in project_serializer.save():
                    project.artifacts.add(instance)

            # Handle reproducibility changes
            if reproducibility is not None:
                repro_serializer = ArtifactReproducibilitySerializer(
                    data=reproducibility, instance=instance, context=self.context
                )
                repro_serializer.is_valid(raise_exception=True)
                repro_serializer.save()

            # Special exception for sharing_key, which is regenerated on remove
            if (sharing_key := "sharing_key") in validated_data:
                sharing_key_field = instance._meta.local_fields[sharing_key]
                validated_data[sharing_key] = sharing_key_field.default()

            return super(ArtifactSerializer, self).update(instance, validated_data)

    def to_internal_value(self, data: dict) -> dict:
        # If this is a new Artifact, its default owner is the user who is creating it
        if not self.instance:
            data.setdefault("owner_urn", self.get_requesting_user_urn())

        return super(ArtifactSerializer, self).to_internal_value(data)

    def validate_owner_urn(self, owner_urn: str) -> str:
        token_urn = self.get_requesting_user_urn()
        if not token_urn:
            raise PermissionDenied("Setting the owner_urn requires authentication.")
        if JWT.Scopes.TROVI_ADMIN in JWT.from_request(self.context["request"]).scope:
            return owner_urn
        elif self.instance and self.instance.owner_urn != token_urn:
            raise PermissionDenied("Non-owners cannot modify owner_urn")
        elif not self.instance and owner_urn != token_urn:
            raise PermissionDenied(
                "The owner of an artifact can only be edited by the artifact owner "
                "after creation. "
                "The default artifact owner is the user who created the artifact."
            )
        return owner_urn

    def validate_linked_projects(self, linked_projects: list[str]) -> list[str]:
        token = JWT.from_request(self.context["request"])
        if token and token.is_admin():
            return linked_projects
        raise PermissionDenied(
            "Only Trovi admins are allowed to modify an artifact's linked projects."
        )

    def get_requesting_user_urn(self) -> Optional[str]:
        """
        Generates a default owner URN based on the requesting user's auth token
        """
        request = self.context.get("request")
        if not request:
            return None
        token = JWT.from_request(request)
        if not token:
            return None
        return token.to_urn()

    def validate_long_description(
        self, long_description: Optional[str]
    ) -> Optional[str]:
        if not long_description:
            return long_description
        try:
            commonmark.github_flavored_markdown_to_html(long_description)
        except ValueError as e:
            raise ValidationError(f"Invalid CommonMark syntax: {str(e)}")
        return long_description


@allow_force
@strict_schema
class ArtifactPatchSerializer(serializers.Serializer):
    """
    Serializes an Artifact Update (JSON Patch) request and converts it into a
    new Artifact representation, which is then passed to the ArtifactSerializer,
    where the actual update is performed
    """

    patch = JsonPatchOperationSerializer(many=True, required=True, write_only=True)

    def update(self, instance: Artifact, validated_data: dict[str, JSON]) -> Artifact:
        patch = ArtifactPatch(
            validated_data["patch"], forced=_is_valid_force_request(self)
        )
        diff = patch.apply(ArtifactSerializer(instance).data)
        artifact_serializer = ArtifactSerializer(
            instance, data=diff, partial=True, context=self.context
        )
        artifact_serializer.is_valid(raise_exception=True)
        updated_artifact = artifact_serializer.save()

        return updated_artifact

    def create(self, _):
        raise ValueError("Incorrect usage of ArtifactPatchSerializer")

    @transaction.atomic
    def to_representation(self, instance: Artifact) -> dict[str, JSON]:
        serializer = ArtifactSerializer(context=self.context)
        return serializer.to_representation(instance)

    @property
    def context(self):
        return super(ArtifactPatchSerializer, self).context | {"patch": True}
