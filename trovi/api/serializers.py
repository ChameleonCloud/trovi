from django.db import models
from rest_framework import serializers

import settings
from trovi.models import (
    Artifact,
    ArtifactTag,
    ArtifactAuthor,
    ArtifactProject,
    ArtifactVersion,
    ArtifactLink,
)


serializers.ModelSerializer.serializer_field_mapping.update(
    {models.UUIDField: serializers.UUIDField}
)


class ArtifactTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArtifactTag

    def to_representation(self, instance: ArtifactTag) -> str:
        return instance.tag


class ArtifactAuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArtifactAuthor

    def to_representation(self, instance: ArtifactAuthor) -> dict:
        return {
            "name": instance.full_name,
            "affiliation": instance.affiliation,
            "email": instance.email,
        }


class ArtifactProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArtifactProject

    def to_representation(self, instance: ArtifactProject) -> str:
        return instance.urn


class ArtifactLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArtifactLink

    def to_representation(self, instance: ArtifactLink) -> dict:
        return {
            "label": instance.label,
            "verified": instance.verified,
            "urn": instance.urn,
        }


class ArtifactVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArtifactVersion

    def to_representation(self, instance: ArtifactVersion) -> dict:
        return {
            "slug": instance.slug,
            "created_at": instance.created_at.strftime(settings.DATETIME_FORMAT),
            "contents": {
                "urn": instance.contents_urn,
            },
            "metrics": {
                "access_count": instance.access_count,
            },
            "links": ArtifactLinkSerializer(instance.links.all(), many=True).data,
        }


class ArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artifact

    def to_representation(self, instance: Artifact) -> dict:
        return {
            "id": instance.uuid,
            "created_at": instance.created_at.strftime(settings.DATETIME_FORMAT),
            "updated_at": instance.created_at.strftime(settings.DATETIME_FORMAT),
            "title": instance.title,
            "short_description": instance.short_description,
            "long_description": instance.long_description,
            "tags": ArtifactTagSerializer(instance.tags.all(), many=True).data,
            "authors": ArtifactAuthorSerializer(instance.authors.all(), many=True).data,
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

class ListArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artifact


