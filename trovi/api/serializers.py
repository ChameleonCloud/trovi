import logging
from typing import Optional

import cmarkgfm as commonmark
from django.conf import settings
from django.db import transaction, IntegrityError
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

from trovi.api.patches import ArtifactPatch
from trovi.common.exceptions import ConflictError, InvalidToken
from trovi.common.serializers import JsonPatchOperationSerializer, URNSerializerField
from trovi.common.tokens import JWT
from trovi.fields import URNField
from trovi.models import (
    Artifact,
    ArtifactTag,
    ArtifactAuthor,
    ArtifactProject,
    ArtifactVersion,
    ArtifactLink,
)
from util.types import JSON
from util.url import fqdn_to_nid

LOG = logging.getLogger(__name__)

serializers.ModelSerializer.serializer_field_mapping.update(
    {URNField: URNSerializerField}
)


def artifact_to_json(instance: Artifact) -> dict[str, JSON]:
    return {
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
        "versions": ArtifactVersionSerializer(instance.versions.all(), many=True).data,
    }


class ArtifactTagSerializer(serializers.ModelSerializer):
    """
    A tag which categorizes an artifact
    """

    class Meta:
        model = ArtifactTag
        fields = "__all__"

    def to_representation(self, instance: ArtifactTag) -> str:
        return instance.tag

    def to_internal_value(self, data: str) -> dict:
        # We skip the super call here to avoid running into the uniqueness validator
        return {"tag": self.validate_tag(data)}

    def validate_tag(self, tag: str) -> str:
        """
        While tags are read-only via the API, the reverse-serialization of the tags
        exists to validate each tag's existence rather than create a new one.
        """
        # Ensure that 1 and only 1 of the given tag exists
        if self.Meta.model.objects.filter(tag__iexact=tag).count() != 1:
            raise ValidationError(f"Unknown tag: {tag}")
        return tag


@extend_schema_serializer(exclude_fields=["id", "artifact"])
class ArtifactAuthorSerializer(serializers.ModelSerializer):
    """
    Description of a single artifact author
    """

    class Meta:
        model = ArtifactAuthor
        fields = "__all__"

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
        fields = "__all__"

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
        project, _ = self.Meta.model.objects.get_or_create(
            urn__iexact=validated_data["urn"], defaults={"urn": validated_data["urn"]}
        )
        return project

    def validate_urn(self, urn: str) -> str:
        # TODO check if valid project
        return urn


class ArtifactLinkSerializer(serializers.ModelSerializer):
    """
    Describes an external link relevant to an artifact version
    """

    class Meta:
        model = ArtifactLink
        exclude = ["artifact_version", "id", "verified_at"]

    verified = serializers.BooleanField(default=False, read_only=True)

    def to_representation(self, instance: ArtifactLink) -> dict:
        return {
            "label": instance.label,
            "verified": instance.verified,
            # TODO check if this is a valid resource
            "urn": instance.urn,
        }


class ArtifactVersionContentsSerializer(serializers.Serializer):
    """
    Represents metadata regarding an artifact version's contents
    """

    urn = URNSerializerField()

    def create(self, validated_data: dict[str, JSON]) -> ArtifactVersion:
        self.instance.contents_urn = validated_data["urn"]
        return self.instance

    def update(self, _, validated_data: dict[str, JSON]) -> ArtifactVersion:
        return self.create(validated_data)

    def validate_urn(self, urn: str) -> str:
        # Since versions cannot be patched, we can skip uniqueness validation
        if self.instance:
            return urn
        if not urn:
            raise ValidationError("Missing required field contents.urn")
        try:
            # TODO check if this is a valid resource
            ArtifactVersion.objects.get(contents_urn__iexact=urn)
        except ArtifactVersion.DoesNotExist:
            return urn
        raise ConflictError(f"Version with contents {urn} already exists.")


@extend_schema_serializer(exclude_fields=["id", "artifact", "contents_urn"])
class ArtifactVersionSerializer(serializers.ModelSerializer):
    """
    Describes a single version of an artifact
    """

    class Meta:
        model = ArtifactVersion
        fields = "__all__"

    contents = ArtifactVersionContentsSerializer(required=True)
    links = ArtifactLinkSerializer(many=True, required=False)

    def create(self, validated_data: dict) -> ArtifactVersion:
        links = validated_data.pop("links", [])
        link_serializer = ArtifactLinkSerializer()
        contents = validated_data.pop("contents", {})

        with transaction.atomic():
            try:
                version = self.Meta.model.objects.create(**validated_data)
            except IntegrityError as e:
                LOG.error(f"Failed to create ArtifactVersion: {str(e)}")
                raise e

            for link in links:
                link["artifact_version_id"] = version.id
                link_serializer.create(link)

            contents_serializer = ArtifactVersionContentsSerializer(version)
            contents_serializer.create(contents)

            version.save()

        return version

    def to_representation(self, instance: ArtifactVersion) -> dict:
        return {
            "slug": instance.slug,
            "created_at": instance.created_at.strftime(settings.DATETIME_FORMAT),
            "contents": {
                # TODO check if this is a valid resource
                "urn": instance.contents_urn,
            },
            "metrics": {
                "access_count": instance.access_count,
            },
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
        instance.save(update_fields=["repro_access_hours", "is_reproducible"])
        return instance

    def validate(self, attrs: dict[str, JSON]) -> dict[str, JSON]:
        enable_requests = attrs.get("enable_requests")
        access_hours = attrs.get("access_hours")

        if not enable_requests and access_hours:
            raise ValidationError(
                "Attempted to set reproducibility access hours "
                "without enabling reproducibility requests."
            )

        return super(ArtifactReproducibilitySerializer, self).validate(attrs)

    def to_representation(self, instance: Artifact) -> dict[str, JSON]:
        return {
            "enable_requests": instance.is_reproducible,
            "access_hours": instance.repro_access_hours,
            "requests": instance.repro_requests,
        }


class ArtifactSerializer(serializers.ModelSerializer):
    """
    Represents a single artifact
    """

    class Meta:
        model = Artifact
        exclude = [
            "sharing_key",
            "is_reproducible",
            "repro_access_hours",
            "repro_requests",
        ]

    # Related fields used for validating on writes
    tags = ArtifactTagSerializer(many=True, required=False)
    authors = ArtifactAuthorSerializer(many=True, required=False)
    linked_projects = ArtifactProjectSerializer(many=True, required=False)
    reproducibility = ArtifactReproducibilitySerializer(required=False)
    versions = ArtifactVersionSerializer(many=True, read_only=True)
    version = ArtifactVersionSerializer(required=False, write_only=True)

    @transaction.atomic
    def to_representation(self, instance: Artifact) -> dict[str, JSON]:
        return artifact_to_json(instance)

    def create(self, validated_data: dict) -> Artifact:
        # All nested fields have to be manually created, so that is done here
        tags = {t["tag"] for t in validated_data.pop("tags", [])}
        authors = validated_data.pop("authors", [])
        linked_projects = validated_data.pop("linked_projects", [])
        version = validated_data.pop("version", {})
        reproducibility = validated_data.pop("reproducibility", {})

        # For some reason, member serializers are not accessible in here
        author_serializer = ArtifactAuthorSerializer()
        project_serializer = ArtifactProjectSerializer()
        version_serializer = ArtifactVersionSerializer()

        with transaction.atomic():
            artifact = self.Meta.model.objects.create(**validated_data)
            reproducibility_serializer = ArtifactReproducibilitySerializer(artifact)

            # Since ArtifactTags are only supposed to be created internally, we look
            # for existing ones that match those in the request, and add the new
            # Artifact as a relationship
            tag_objs = ArtifactTag.objects.filter(tag__in=tags)
            artifact.tags.add(*tag_objs)

            # New relationships have to be created here,
            # with the new Artifact's ID manually shoved in
            for author in authors:
                author["artifact"] = artifact
                author_serializer.create(author)
            for project in linked_projects:
                # This will retrieve the project with the matching URN,
                # or create a new one if it doesn't yet exist
                project_obj = project_serializer.create(project)
                project_obj.artifacts.add(artifact.uuid)
            if version:
                version["artifact"] = artifact
                version_serializer.create(version)
            if reproducibility:
                artifact = reproducibility_serializer.create(reproducibility)

        return artifact

    def update(self, instance: Artifact, validated_data: dict) -> Artifact:
        if (sharing_key := "sharing_key") in validated_data:
            # Special exception for sharing_key, which is regenerated on remove
            sharing_key_field = instance._meta.local_fields[sharing_key]
            validated_data[sharing_key] = sharing_key_field.default()

        return super(ArtifactSerializer, self).update(instance, validated_data)

    def to_internal_value(self, data: dict) -> dict:
        # If this is a new Artifact, its default owner is the user who is creating it
        if not self.instance:
            data.setdefault("owner_urn", self.get_token_owner_urn())

        return super(ArtifactSerializer, self).to_internal_value(data)

    def validate_owner_urn(self, owner_urn: str) -> str:
        token_urn = self.get_token_owner_urn()
        if JWT.Scopes.TROVI_ADMIN in JWT.from_request(self.context["request"]).scope:
            return owner_urn
        elif self.instance and self.instance.owner_urn != token_urn:
            raise PermissionDenied("Non-owners cannot modify owner_urn")
        elif not self.instance and owner_urn != token_urn:
            raise PermissionDenied("The owner of an artifact can only be set")
        return owner_urn

    def get_token_owner_urn(self) -> str:
        """
        Generates a default owner URN based on the requesting user's auth token
        """
        token = JWT.from_request(self.context["request"])
        if not (actor_sub := token.act.get("sub")):
            raise InvalidToken("Cannot derive owner_urn")
        return f"urn:{fqdn_to_nid(actor_sub)}:{token.azp}"

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


class ArtifactPatchSerializer(serializers.Serializer):
    """
    Serializes an Artifact Update (JSON Patch) request and converts it into a
    new Artifact representation, which is then passed to the ArtifactSerializer,
    where the actual update is performed
    """

    patch = JsonPatchOperationSerializer(many=True, required=True, write_only=True)

    def update(self, instance: Artifact, validated_data: dict[str, JSON]) -> Artifact:
        patch = ArtifactPatch(validated_data["patch"])
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
        return artifact_to_json(instance)
