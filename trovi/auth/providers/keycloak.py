import logging
from typing import Optional

from jose import jwk, JOSEError
from jose.backends.base import Key
from jose.constants import ALGORITHMS
from keycloak.realm import KeycloakRealm
from requests import HTTPError
from rest_framework.exceptions import AuthenticationFailed

from trovi.auth.providers.base import IdentityProviderClient
from trovi.common.tokens import JWT, OAuth2TokenIntrospection

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

    def get_user_token(
        self, username: str, password: str, client_id: str, client_secret: str, **kwargs
    ) -> dict:
        if not username or not password or not client_id or not client_secret:
            raise RuntimeError(
                f"Missing required user data for obtaining token: "
                f"{username=} "
                f"password={'*****' if password else password} "
                f"{client_id=} "
                f"client_secret={'*****' if client_secret else client_secret}"
            )
        openid = self.realm.open_id_connect(client_id, client_secret)
        creds = openid.password_credentials(username, password)
        return creds["access_token"]

    def get_subject(self, subject_token: JWT) -> str:
        return subject_token.additional_claims["preferred_username"]

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

    def refresh_signing_keys(self) -> list[Key]:
        # Keys are encoded as JWK set (https://datatracker.ietf.org/doc/html/rfc7517)
        certs = self.openid.certs()
        signing_keys = [k for k in certs["keys"] if k.get("use") == "sig"]
        if not signing_keys:
            raise ValueError("Keycloak exposes no signing keys.")
        return [jwk.construct(k) for k in signing_keys]
