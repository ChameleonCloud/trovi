"""
This package provides the interface for implementing Cloud Identity Provider plugins,
as well as implementations for the officially supported Identity Providers
"""

from functools import cache

from django.conf import settings

from trovi.auth.providers.base import IdentityProviderClient
from trovi.common.exceptions import InvalidToken
from trovi.common.tokens import JWT


def validate_subject_token(jws: str) -> JWT:
    """
    Attempts to verify a token in JWS format against all Identity Providers.

    If anu succeed, returns the decoded JWT. If zero providers can
    validate the token, raises ``AuthenticationFailed``.
    """
    jwt = JWT.from_jws(jws, validate=False)
    provider = get_subject_token_provider(jwt)
    validated_token = provider.validate_subject_token(jwt)

    # Internal validation
    # Ensure token authorized party is approved client ID
    if validated_token.azp not in settings.AUTH_APPROVED_AUTHORIZED_PARTIES:
        raise InvalidToken(
            f"Authorized party is not approved client ID: {validated_token.azp}"
        )

    return validated_token


def get_subject_token_provider(subject_token: JWT) -> IdentityProviderClient:
    """
    Figures out which Identity Provider authorized a subject token
    """
    iss = subject_token.iss
    if not iss:
        raise InvalidToken("Token does not contain required claim 'iss'.")
    client = get_clients().get(iss.replace("https://", "").split("/")[0])
    if not client:
        raise InvalidToken(f"Unknown Identity Provider: {iss}")
    return client


@cache
def get_clients() -> dict[str, IdentityProviderClient]:
    # Dictionary used for registering Identity Providers
    # TODO replace with Python entry_point to allow for pluggable providers
    from trovi.auth.providers.keycloak import KeycloakIdentityProvider

    return {
        client.get_actor_subject(): client
        for client in [
            KeycloakIdentityProvider(
                client_id=settings.CHAMELEON_KEYCLOAK_TROVI_ADMIN_CLIENT_ID,
                client_secret=settings.CHAMELEON_KEYCLOAK_TROVI_ADMIN_CLIENT_SECRET,
                server_url=settings.CHAMELEON_KEYCLOAK_SERVER_URL,
                realm_name=settings.CHAMELEON_KEYCLOAK_REALM_NAME,
            )
        ]
    }
