import logging

import cmarkgfm as commonmark
from django.conf import settings
from django.db import transaction, IntegrityError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

from trovi.common.exceptions import ConflictError, InvalidToken
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
from util.url import fqdn_to_nid

LOG = logging.getLogger(__name__)

serializers.ModelSerializer.serializer_field_mapping.update(
    {URNField: serializers.CharField}
)


class ArtifactTagSerializer(serializers.ModelSerializer):
    """
    Does forward and reverse-serialization of ``ArtifactTag``s
    While tags are read-only via the API, the reverse-serialization of the tags
    exists to validate each tag's existence rather than create a new one.

    Serializes:
        ``ArtifactTag -> .tag: str``
    De-Serializes:
        ``tag: str -> {"tag": tag}``
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
        # Ensure that 1 and only 1 of the given tag exists
        if self.Meta.model.objects.filter(tag__iexact=tag).count() != 1:
            raise ValidationError(f"Unknown tag: {tag}")
        return tag


class ArtifactAuthorSerializer(serializers.ModelSerializer):
    """
    Does forward serialization of ``ArtifactAuthor``s.

    Since ``ArtifactAuthor`` fields are 1:1 with their API representation,
    no de-serialization logic is required.
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
    Does forward and reverse serialization of ``ArtifactProject``s.

    Since all projects are unique, and can be applied to multiple ``Artifact``s,
    this class overrides the ``create`` method to return an existing project that
    matches the unique provided URN, or create one if it doesn't exist.

    Serializes:
        ``ArtifactProject -> .urn: str``
    De-Serializes:
        ``urn: str -> {"urn": urn}``
    """

    class Meta:
        model = ArtifactProject
        fields = "__all__"

    def to_representation(self, instance: ArtifactProject) -> str:
        return instance.urn

    def to_internal_value(self, data: str) -> dict:
        return {"urn": data}

    def create(self, validated_data: dict) -> ArtifactProject:
        project, _ = self.Meta.model.objects.get_or_create(
            urn__iexact=validated_data["urn"], defaults={"urn": validated_data["urn"]}
        )
        return project

    def validate_urn(self, urn: str) -> str:
        # TODO check if valid project
        return urn


class ArtifactLinkSerializer(serializers.ModelSerializer):
    """
    Does forward serialization of ``ArtifactLink``s.

    Since ``ArtifactAuthor`` fields are 1:1 with their API representation,
    no de-serialization logic is required.
    """

    class Meta:
        model = ArtifactLink
        fields = "__all__"

    def to_representation(self, instance: ArtifactLink) -> dict:
        return {
            "label": instance.label,
            "verified": instance.verified,
            # TODO check if this is a valid resource
            "urn": instance.urn,
        }


class ArtifactVersionSerializer(serializers.ModelSerializer):
    """
    Does forward and reverse serialization of ``ArtifactVersion``s.
    """

    class Meta:
        model = ArtifactVersion
        fields = "__all__"

    links = ArtifactLinkSerializer(many=True, required=False)

    def create(self, validated_data: dict) -> ArtifactVersion:
        links = validated_data.pop("links", [])
        link_serializer = ArtifactLinkSerializer()

        with transaction.atomic():
            try:
                version = self.Meta.model.objects.create(**validated_data)
            except IntegrityError as e:
                LOG.error(f"Failed to create ArtifactVersion: {str(e)}")
                raise e

            for link in links:
                link["artifact_version_id"] = version.id
                link_serializer.create(link)

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

    def validate_contents_urn(self, urn: str) -> str:
        # Since versions cannot be patched, we can skip uniqueness validation
        if "patch" in self.context:
            return urn
        try:
            ArtifactVersion.objects.get(contents_urn__iexact=urn)
        except ArtifactVersion.DoesNotExist:
            return urn
        raise ConflictError(f"Version with contents {urn} already exists.")

    def to_internal_value(self, data: dict) -> dict:
        contents = data.pop("contents")
        if contents:
            data["contents_urn"] = contents.get("urn")

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
            artifact_error = e.detail.get("artifact")
            if artifact_error:
                if any(detail.code == "does_not_exist" for detail in artifact_error):
                    raise NotFound(e.detail)
            raise e


class ArtifactSerializer(serializers.ModelSerializer):
    """
    Does forward and reverse serialization of ``ArtifactVersion``s.
    """

    class Meta:
        model = Artifact
        fields = "__all__"

    # Related fields used for validating on writes
    tags = ArtifactTagSerializer(many=True, required=False)
    authors = ArtifactAuthorSerializer(many=True, required=False)
    linked_projects = ArtifactProjectSerializer(many=True, required=False)
    versions = ArtifactVersionSerializer(many=True, required=False)

    def create(self, validated_data: dict) -> Artifact:
        # All nested fields have to be manually created, so that is done here
        tags = {t["tag"] for t in validated_data.pop("tags", [])}
        authors = validated_data.pop("authors", [])
        linked_projects = validated_data.pop("linked_projects", [])
        versions = validated_data.pop("versions", [])

        # For some reason, member serializers are not accessible in here
        author_serializer = ArtifactAuthorSerializer()
        project_serializer = ArtifactProjectSerializer()
        version_serializer = ArtifactVersionSerializer()

        with transaction.atomic():
            artifact = self.Meta.model.objects.create(**validated_data)

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
            for version in versions:
                version["artifact"] = artifact
                version_serializer.create(version)

        return artifact

    def update(self, instance: Artifact, validated_data: dict) -> Artifact:
        # All nested fields have to be manually updated, so that is done here
        tags = {t["tag"] for t in validated_data.pop("tags", [])}
        authors = validated_data.pop("authors", [])
        linked_projects = [p["urn"] for p in validated_data.pop("linked_projects", [])]

        # Pop off non-mutable fields
        validated_data.pop("versions", [])

        # Update unrelated fields
        fields_to_update = {
            f.name
            for f in instance._meta.local_fields
            if validated_data.get(f.name, (real := f.value_from_object(instance)))
            != real
        }
        for f in fields_to_update:
            setattr(instance, f, validated_data[f])

        # Remove unrelated fields
        fields_to_remove = {
            patch["path"][1:] if op == "remove" else patch["from"][1:]
            for patch in self.context.get("patch", [])
            if (op := patch["op"]) in ("remove", "move")
        }
        # Translate field names that require it
        if (sub := "reproducibility/access_hours") in fields_to_remove:
            fields_to_remove.remove(sub)
            fields_to_remove.add("repro_access_hours")
        if (sub := "reproducibility/enable_requests") in fields_to_remove:
            fields_to_remove.remove(sub)
            fields_to_remove.add("is_reproducible")
        for field in instance._meta.local_fields:
            if (name := field.name) in fields_to_remove:
                # Special exception for sharing_key, which is regenerated on remove
                if name == "sharing_key":
                    instance.sharing_key = field.default()
                # Special exception for repro_access_hours,
                # which should disable requests if removed
                elif name == "repro_access_hours":
                    instance.repro_access_hours = None
                    instance.is_reproducible = False
                    fields_to_update.add("is_reproducible")
                elif field.null:
                    setattr(instance, name, None)
                else:
                    raise PermissionDenied(f"Field {name} can not be removed.")

        # For some reason, member serializers are not accessible in here
        author_serializer = ArtifactAuthorSerializer()
        project_serializer = ArtifactProjectSerializer()

        with transaction.atomic():
            if tags:
                # Since ArtifactTags are only supposed to be created internally, we look
                # for existing ones that match those in the request, and add the new
                # Artifact as a relationship
                tag_objs = ArtifactTag.objects.filter(tag__in=tags)
                instance.tags.set(tag_objs)
            else:
                instance.tags.clear()

            # Since authors are ManyToOne, and it's hard to tell what is an update
            # vs removal, we just rewrite all the authors
            instance.authors.clear()
            for author in authors:
                author["artifact"] = instance
                author_serializer.create(author)

            # Remove any linked projects that are not in the updated list
            for project in instance.linked_projects.all():
                if project.urn not in linked_projects:
                    instance.linked_projects.remove(project)
                else:
                    linked_projects.remove(project.urn)
            # Add new/updated projects to the relationship
            for project in linked_projects:
                # This will retrieve the project with the matching URN,
                # or create a new one if it doesn't yet exist
                project_obj = project_serializer.create(project)
                instance.linked_projects.add(project_obj)

            instance.save(update_fields=fields_to_update & fields_to_remove)

        return instance

    @transaction.atomic
    def to_representation(self, instance: Artifact) -> dict:
        return {
            "id": str(instance.uuid),
            "created_at": instance.created_at.strftime(settings.DATETIME_FORMAT),
            "updated_at": instance.created_at.strftime(settings.DATETIME_FORMAT),
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
            "reproducibility": {
                "enable_requests": instance.is_reproducible,
                "access_hours": instance.repro_access_hours,
            },
            "versions": ArtifactVersionSerializer(
                instance.versions.all(), many=True
            ).data,
        }

    def to_internal_value(self, data: dict) -> dict:
        data = data.copy()
        initial_version = data.pop("version", None)
        if initial_version:
            data["versions"] = [initial_version]

        reproducibility = data.pop("reproducibility", None)
        if reproducibility:
            enable_requests = reproducibility.get("enable_requests")
            access_hours = reproducibility.get("access_hours")
            data["is_reproducible"] = enable_requests
            data["repro_access_hours"] = access_hours

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

    def validate_long_description(self, long_description: str) -> str:
        try:
            commonmark.github_flavored_markdown_to_html(long_description)
        except ValueError as e:
            raise ValidationError(f"Invalid CommonMark syntax: {str(e)}")
        return long_description
