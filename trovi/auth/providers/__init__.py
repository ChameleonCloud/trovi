"""
This package provides the interface for implementing Cloud Identity Provider plugins,
as well as implementations for the officially supported Identity Providers
"""

from django.conf import settings

from trovi.auth.providers.base import IdentityProviderClient
from trovi.auth.providers.keycloak import KeycloakIdentityProvider
from trovi.common.exceptions import InvalidToken, InvalidClient
from trovi.common.tokens import JWT
from util.url import url_to_fqdn


def validate_subject_token(jws: str) -> JWT:
    """
    Performs signature validation of a subject token against a supported IdP
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
    azp = settings.AUTH_ISSUERS.get(url_to_fqdn(iss))
    if not azp:
        raise InvalidClient("Unknown identity provider")
    client = get_client_by_authorized_party(azp, subject_token)
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


def get_client_by_authorized_party(azp: str, token: JWT) -> IdentityProviderClient:
    # Look up an Identity Provider by the authorizing party of a token
    provider = next(
        (
            client
            for client in _idp_clients.values()
            if client.subject_iss_to_trovi_azp(token) == azp
        ),
        None,
    )
    if not provider:
        raise InvalidClient(f"Cannot find identity provider for subject {azp}")
    return provider
