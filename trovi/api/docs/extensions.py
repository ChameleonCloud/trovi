from typing import Union

from django.conf import settings
from drf_spectacular.extensions import (
    OpenApiSerializerExtension,
    OpenApiAuthenticationExtension,
)
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import Direction
from rest_framework.reverse import reverse

from trovi.api.serializers import (
    ArtifactTagSerializer,
    ArtifactProjectSerializer,
)
from trovi.auth.serializers import TokenGrantRequestSerializer
from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.tokens import JWT
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


class TokenGrantRequestSerializerExtension(OpenApiSerializerExtension):
    target_class = TokenGrantRequestSerializer
    priority = 1

    def map_serializer(
        self, auto_schema: AutoSchema, direction: Direction
    ) -> dict[str, JSON]:
        schema = super(TokenGrantRequestSerializerExtension, self).map_serializer(
            auto_schema, direction
        )
        scope_schema = build_basic_type(OpenApiTypes.STR) | {
            "description": f"A space separated string consisting of "
            f"the following scopes: \n{', '.join(JWT.Scopes)}"
        }
        schema["properties"]["scope"] = scope_schema
        return schema


class TroviTokenAuthenticationExtension(OpenApiAuthenticationExtension):
    target_class = TroviTokenAuthentication
    name = "Trovi Token Authentication"
    priority = 1

    def get_security_definition(
        self, auto_schema: AutoSchema
    ) -> Union[dict, list[dict]]:
        # Derived via https://swagger.io/docs/specification/authentication/oauth2/
        return {
            "description": "Trovi tokens are JWS-formatted OAuth JavaScript Web Tokens "
            "(JWTs) obtained via the /token/ endpoint. "
            "Tokens are obtained via the OAuth 2.0 Token Exchange Flow (RFC 8693).",
            "type": "bearer",
            "flows": {
                "implicit": {
                    "authorizationUrl": reverse("TokenGrant"),
                    "scopes": {
                        JWT.Scopes.ARTIFACTS_READ: "Read an Artifact's metadata and content.",
                        JWT.Scopes.ARTIFACTS_WRITE: "Write an Artifact's metadata and content.",
                        JWT.Scopes.ARTIFACTS_WRITE_METRICS: "Write to an Artifact's metrics.",
                    },
                }
            },
        }
