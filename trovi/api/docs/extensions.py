from django.conf import settings
from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import Direction

from trovi.api.serializers import (
    ArtifactTagSerializer,
    ArtifactProjectSerializer,
)
from trovi.fields import URNField
from util.types import JSON


class ArtifactTagSerializerExtension(OpenApiSerializerExtension):
    target_class = ArtifactTagSerializer
    priority = 1

    def map_serializer(
        self, auto_schema: AutoSchema, direction: Direction
    ) -> dict[str, JSON]:
        schema = build_basic_type(OpenApiTypes.STR)
        return schema | {
            "description": ArtifactTagSerializer.__doc__.strip(),
            "maxLength": settings.ARTIFACT_TAG_MAX_CHARS,
            "readOnly": True,
        }


class ArtifactProjectSerializerExtension(OpenApiSerializerExtension):
    target_class = ArtifactProjectSerializer
    priority = 1

    def map_serializer(
        self, auto_schema: AutoSchema, direction: Direction
    ) -> dict[str, JSON]:
        schema = build_basic_type(OpenApiTypes.STR)
        return schema | {
            "description": ArtifactProjectSerializer.__doc__.strip(),
            "maxLength": settings.URN_MAX_CHARS,
            "pattern": URNField.pattern.pattern,
        }
