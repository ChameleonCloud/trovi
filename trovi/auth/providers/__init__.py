"""
This package provides the interface for implementing Cloud Identity Provider plugins,
as well as implementations for the officially supported Identity Providers
"""

from django.conf import settings

from trovi.auth.providers.base import IdentityProviderClient
from trovi.auth.providers.keycloak import KeycloakIdentityProvider
from trovi.common.exceptions import InvalidToken
from trovi.common.tokens import JWT
from util.url import url_to_fqdn


def validate_subject_token(jws: str) -> JWT:
    """
    Attempts to verify a token in JWS format against all Identity Providers.

    If anu succeed, returns the decoded JWT. If zero providers can
    validate the token, raises ``AuthenticationFailed``.
    """
    jwt = JWT.from_jws(jws, validate=False)
    provider = get_subject_token_provider(jwt)
    validated_token = provider.validate_subject_token(jwt)

    return validated_token


def get_subject_token_provider(subject_token: JWT) -> IdentityProviderClient:
    """
    Figures out which Identity Provider authorized a subject token
    """
    iss = subject_token.iss
    if not iss:
        raise InvalidToken("Token does not contain required claim 'iss'.")
    client = get_client_by_issuer(url_to_fqdn(iss))
    return client


_idp_clients = {
    # TODO replace with Python entry_point to allow for pluggable providers
    client.get_name(): client
    for client in [
        KeycloakIdentityProvider(
            client_id=settings.CHAMELEON_KEYCLOAK_TROVI_ADMIN_CLIENT_ID,
            client_secret=settings.CHAMELEON_KEYCLOAK_TROVI_ADMIN_CLIENT_SECRET,
            server_url=settings.CHAMELEON_KEYCLOAK_SERVER_URL,
            realm_name=settings.CHAMELEON_KEYCLOAK_REALM_NAME,
        )
    ]
}


def get_client_by_name(name: str) -> IdentityProviderClient:
    # Look up an identity provider client by its internal name
    client = _idp_clients.get(name)
    if not client:
        raise ValueError(f"Unknown identity provider: {name}")
    return client


def get_client_by_issuer(issuer: str) -> IdentityProviderClient:
    # Look up an Identity Provider by the actor subject of a token
    provider = next(
        (client for client in _idp_clients.values() if client.get_issuer() == issuer),
        None,
    )
    if not provider:
        raise InvalidToken(f"Unknown identity provider: {issuer}")
    return provider
