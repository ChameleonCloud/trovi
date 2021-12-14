import logging
from datetime import datetime
from typing import Optional

from django.conf import settings
from jose import jwk, JOSEError
from jose.backends.base import Key
from jose.constants import ALGORITHMS
from keycloak.realm import KeycloakRealm
from requests import HTTPError
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken

from trovi.auth.providers.base import IdentityProviderClient
from trovi.auth.tokens import JWT, OAuth2TokenIntrospection

LOG = logging.getLogger(__name__)


class KeycloakIdentityProvider(IdentityProviderClient):
    """
    Implements the Identity Provider interface for
    """

    def __init__(
        self, client_id: str, client_secret: str, server_url: str, realm_name: str
    ):
        super(KeycloakIdentityProvider, self).__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.realm = KeycloakRealm(server_url, realm_name)
        self.openid = self.realm.open_id_connect(client_id, client_secret)

    def get_name(self) -> str:
        return "CHAMELEON_KEYCLOAK"

    def get_client_token(self, **kwargs) -> dict:
        return self.openid.client_credentials(**kwargs)

    def get_test_user_token(
        self, username: str, password: str, client_id: str, client_secret: str, **kwargs
    ) -> dict:
        if not username or not password or not client_id or not client_secret:
            raise RuntimeError("No Keycloak configured for testing.")
        openid = self.realm.open_id_connect(client_id, client_secret)
        creds = openid.password_credentials(username, password)
        return creds["access_token"]

    def get_actor_subject(self) -> str:
        return self.openid.get_url("issuer")

    def validate_subject_token(self, subject_token: JWT) -> JWT:
        for key in self.signing_keys:
            try:
                # Try to use all the signing keys until one works
                token = self.openid.decode_token(
                    (jws := subject_token.to_jws()),
                    key := key.public_key(),
                    algorithms=ALGORITHMS.RSA_DS,
                )
                token["key"] = key
                token["alg"] = JWT.Algorithm.RS256
                token["jws"] = jws
                return JWT.from_dict(token)
            except JOSEError as e:
                LOG.debug(f"{self.get_name()} signing key failed: {e}")
        raise AuthenticationFailed(f"{self.get_name()} failed to decode subject token.")

    def introspect_token(
        self, subject_token: JWT
    ) -> Optional[OAuth2TokenIntrospection]:
        try:
            introspection_url = self.openid.get_url("token_introspection_endpoint")
        except KeyError:
            # If IdP doesn't support introspection, return None
            LOG.warning(f"{self.get_name()} does not support introspection.")
            return None

        try:
            response = self.realm.client.post(
                introspection_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "token": subject_token.to_jws(),
                },
            )
        except HTTPError:
            raise AuthenticationFailed("Failed to introspect subject token.")

        response["token"] = subject_token
        return OAuth2TokenIntrospection.from_dict(response)

    def exchange_token(
        self, subject_token: JWT, requested_scope: list[JWT.Scopes] = None
    ) -> JWT:
        introspection = self.introspect_token(subject_token)
        if introspection and not introspection.active:
            raise InvalidToken("Subject token revoked.")
        scopes = (
            requested_scope
            if requested_scope is not None
            else [JWT.Scopes.ARTIFACTS_READ]
        )
        return JWT(
            azp=(email := subject_token.additional_claims["email"]),
            aud=settings.TROVI_FQDN,
            iss=settings.TROVI_FQDN,
            iat=(now := int(datetime.utcnow().timestamp())),
            sub=email,
            exp=now + settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS,
            scope=scopes,
            alg=settings.AUTH_TROVI_TOKEN_SIGNING_ALGORITHM,
            key=settings.AUTH_TROVI_TOKEN_SIGNING_KEY,
            act={"sub": subject_token.iss},
        )

    def refresh_signing_keys(self) -> list[Key]:
        # Keys are encoded as JWK set (https://datatracker.ietf.org/doc/html/rfc7517)
        certs = self.openid.certs()
        signing_keys = [k for k in certs["keys"] if k.get("use") == "sig"]
        if not signing_keys:
            raise ValueError("Keycloak exposes no signing keys.")
        return [jwk.construct(k) for k in signing_keys]
