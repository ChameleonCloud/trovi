from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken

from trovi.auth import providers
from trovi.auth.tokens import JWT, TokenTypes


class TokenGrantRequestSerializer(serializers.Serializer):
    """
    (De)serializes grant requests in to JWT objects, including implicit validation
    of the JWT's content, and exchanges with an appropriate token
    """

    def create(self, validated_data: dict) -> JWT:
        pass

    def update(self, *_):
        raise NotImplementedError("JWTs should not be manually updated")

    def to_representation(self, instance: JWT) -> str:
        return instance.to_jws()

    def validate_scope(self, scope: str) -> list[JWT.Scopes]:
        scope_list = []
        for s in scope.split():
            if s not in JWT.Scopes:
                raise InvalidToken(f"Unknown scope: {s}")
            scope_list.append(JWT.Scopes(s))
        return scope_list

    def to_internal_value(self, data: dict) -> dict:
        validated_token = providers.validate_subject_token(data["subject_token"])
        provider = providers.get_subject_token_provider(validated_token)
        if not provider:
            raise InvalidToken(f"Unknown Identity Provider: {validated_token.iss}")
        requested_scope = data.get("scope")
        # TODO Error response according to
        #  https://datatracker.ietf.org/doc/html/rfc6749#section-5.2
        trovi_token = provider.exchange_token(validated_token, requested_scope)

        return {
            "access_token": trovi_token.to_jws(),
            "issued_token_type": TokenTypes.ACCESS_TOKEN_TYPE.value,
            "token_type": "bearer",
            "expires_in": trovi_token.exp - trovi_token.iat,
            # TODO validate this. For now, we issue whichever scopes are requested.
            "scope": trovi_token.scope_to_str(),
        }
