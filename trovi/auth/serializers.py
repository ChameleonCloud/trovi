from datetime import datetime
from typing import Iterable

from django.conf import settings
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from trovi.auth import providers
from trovi.common.exceptions import InvalidToken
from trovi.common.tokens import JWT, TokenTypes
from util.types import JSON


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Token Grant Request",
            value={
                "grant_type": "token_exchange",
                "subject_token": JWT(
                    azp=(email := "user@example.com"),
                    aud=[(url := "https://example.com")],
                    iss=url,
                    iat=int(datetime.utcnow().timestamp()),
                    sub=email,
                    exp=(exp := int(datetime(year=2049, month=7, day=6).timestamp())),
                    alg=JWT.Algorithm.HS256.value,
                    key="A" * 256,
                ).to_jws(),
                "subject_token_type": TokenTypes.JWT_TOKEN_TYPE,
                "scope": " ".join(
                    example_scope := [
                        JWT.Scopes.ARTIFACTS_READ,
                        JWT.Scopes.ARTIFACTS_WRITE,
                    ]
                ),
            },
            request_only=True,
            response_only=False,
        ),
        OpenApiExample(
            name="Token Grant Response",
            value={
                "access_token": JWT(
                    azp=email,
                    aud=settings.TROVI_FQDN,
                    iss=settings.TROVI_FQDN,
                    iat=int(datetime.utcnow().timestamp()),
                    sub=email,
                    exp=exp,
                    scope=example_scope,
                    alg=JWT.Algorithm.HS256.value,
                    key="B" * 256,
                    act={"sub": url},
                ).to_jws(),
                "issued_token_type": TokenTypes.ACCESS_TOKEN_TYPE,
                "token_type": "bearer",
                "expires_in": settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS,
                "scope": " ".join(example_scope),
            },
        ),
    ]
)
class TokenGrantRequestSerializer(serializers.Serializer):
    """
    (De)serializes grant requests in to JWT objects, including implicit validation
    of the JWT's content, and exchanges with an appropriate token
    """

    # Request
    grant_type = serializers.ChoiceField(
        ["token_exchange"], write_only=True, required=True
    )
    subject_token = serializers.CharField(write_only=True, required=True)
    subject_token_type = serializers.ChoiceField(
        [TokenTypes.JWT_TOKEN_TYPE], write_only=True, required=True
    )

    # Response
    access_token = serializers.CharField(read_only=True)
    issued_token_type = serializers.ChoiceField(
        [TokenTypes.ACCESS_TOKEN_TYPE], read_only=True
    )
    token_type = serializers.ChoiceField(["bearer"], read_only=True)
    expires_in = serializers.IntegerField(
        min_value=settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS,
        max_value=settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS,
        read_only=True,
    )

    # Both
    scope = serializers.MultipleChoiceField(choices=JWT.Scopes, required=False)

    def create(self, validated_data: dict) -> JWT:
        validated_token = providers.validate_subject_token(
            validated_data["subject_token"]
        )
        provider = providers.get_subject_token_provider(validated_token)
        if not provider:
            raise InvalidToken(f"Unknown Identity Provider: {validated_token.iss}")

        requested_scope = validated_data.get("scope", [JWT.Scopes.ARTIFACTS_READ])

        # TODO Error response according to
        #  https://datatracker.ietf.org/doc/html/rfc6749#section-5.2
        trovi_token = provider.exchange_token(validated_token, requested_scope)

        return trovi_token

    def update(self, *_):
        raise NotImplementedError("JWTs should not be manually updated")

    def to_representation(self, instance: JWT) -> dict[str, JSON]:
        return {
            "access_token": instance.to_jws(),
            "issued_token_type": TokenTypes.ACCESS_TOKEN_TYPE.value,
            "token_type": "bearer",
            "expires_in": instance.exp - instance.iat,
            # TODO validate this. For now, we issue whichever scopes are requested.
            "scope": instance.scope_to_str(),
        }

    def validate_scope(self, scope: Iterable[str]) -> list[JWT.Scopes]:
        # Valid scope values are handled by the scope field's validators
        return [JWT.Scopes(s) for s in scope]

    def to_internal_value(self, data: dict[str, JSON]) -> dict[str, JSON]:
        scope = data.get("scope")
        if scope:
            if not isinstance(scope, str):
                raise ValidationError(
                    f"Scope should be space-separated string of scopes ({scope})"
                )
            data["scope"] = scope.split()
        return super(TokenGrantRequestSerializer, self).to_internal_value(data)
