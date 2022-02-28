from typing import Union, List

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from rest_framework.reverse import reverse

from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.tokens import JWT


class TroviTokenAuthenticationExtension(OpenApiAuthenticationExtension):
    target_class = TroviTokenAuthentication
    name = "Trovi Token Authentication"
    priority = 1

    def get_security_definition(
        self, auto_schema: AutoSchema
    ) -> Union[dict, List[dict]]:
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
