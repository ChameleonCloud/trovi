from typing import Iterable

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from trovi.auth import providers
from trovi.common.exceptions import InvalidToken
from trovi.common.tokens import JWT, TokenTypes
from util.types import JSON


class TokenGrantRequestSerializer(serializers.Serializer):
    """
    (De)serializes grant requests in to JWT objects, including implicit validation
    of the JWT's content, and exchanges with an appropriate token
    """

    grant_type = serializers.ChoiceField(["token_exchange"])
    subject_token = serializers.CharField()
    subject_token_type = serializers.ChoiceField(TokenTypes)
    scope = serializers.MultipleChoiceField(choices=JWT.Scopes, required=False)

    def create(self, validated_data: dict) -> JWT:
        validated_token = providers.validate_subject_token(
            validated_data["subject_token"]
        )
        provider = providers.get_subject_token_provider(validated_token)
        if not provider:
            raise InvalidToken(f"Unknown Identity Provider: {validated_token.iss}")

        requested_scope = validated_data.get("scope")

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
        if not scope:
            raise ValidationError("Requested token with zero authorization scope")
        return [JWT.Scopes(s) for s in scope]

    def to_internal_value(self, data: dict[str, JSON]) -> dict[str, JSON]:
        scope = data.get("scope")
        if scope:
            if not isinstance(scope, str):
                raise ValidationError(
                    f"Scope should be space-separated string of scopes ({scope})"
                )
            data["scope"] = scope.strip().split()
        return super(TokenGrantRequestSerializer, self).to_internal_value(data)
