import logging
from typing import Optional
from urllib.parse import urljoin

import requests
from jwt import PyJWK, PyJWTError, decode as decode_jws
from requests import HTTPError
from rest_framework.exceptions import AuthenticationFailed

from trovi.auth.providers.base import IdentityProviderClient
from trovi.common.tokens import JWT, OAuth2TokenIntrospection

LOG = logging.getLogger(__name__)

# The RSA digital signature algorithms accepted for subject tokens.
RSA_SIGNING_ALGORITHMS = ["RS256", "RS384", "RS512"]

WELL_KNOWN_PATH = "auth/realms/{}/.well-known/openid-configuration"


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
        self.server_url = server_url
        self.realm_name = realm_name
        self.session = requests.Session()
        self._well_known = None

    @property
    def well_known(self) -> dict:
        """
        The realm's OpenID Connect discovery document, fetched once per client.
        """
        if self._well_known is None:
            self._well_known = self._request(
                "get",
                urljoin(self.server_url, WELL_KNOWN_PATH.format(self.realm_name)),
            )
        return self._well_known

    def _request(self, method: str, url: str, **kwargs) -> dict:
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def _token_request(self, client_id: str, client_secret: str, **payload) -> dict:
        return self._request(
            "post",
            self.well_known["token_endpoint"],
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                **payload,
            },
        )

    def get_name(self) -> str:
        return "CHAMELEON_KEYCLOAK"

    def get_client_token(self, **kwargs) -> dict:
        return self._token_request(
            self.client_id,
            self.client_secret,
            grant_type="client_credentials",
            **kwargs,
        )

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
        creds = self._token_request(
            client_id,
            client_secret,
            grant_type="password",
            username=username,
            password=password,
            **kwargs,
        )
        return creds["access_token"]

    def get_subject(self, subject_token: JWT) -> str:
        return subject_token.additional_claims["preferred_username"]

    def validate_subject_token(self, subject_token: JWT) -> JWT:
        for jwk in self.signing_keys:
            try:
                # Try to use all the signing keys until one works
                token = decode_jws(
                    (jws := subject_token.to_jws()),
                    key=(key := jwk.key),
                    algorithms=RSA_SIGNING_ALGORITHMS,
                    # Keycloak lists every client the token is valid for in "aud".
                    # Trovi's own client must be among them.
                    audience=self.client_id,
                    # A token issued a moment ahead of our clock is not a
                    # security problem, and Keycloak's clock is not ours.
                    # "nbf" and "exp" are still enforced with no leeway.
                    options={"verify_iat": False},
                )
                token["key"] = key
                token["alg"] = JWT.Algorithm.RS256
                token["jws"] = jws
                return JWT.from_dict(token)
            except PyJWTError as e:
                LOG.debug(f"{self.get_name()} signing key failed: {e}")
        raise AuthenticationFailed(f"{self.get_name()} failed to decode subject token.")

    def introspect_token(
        self, subject_token: JWT
    ) -> Optional[OAuth2TokenIntrospection]:
        try:
            introspection_url = self.well_known["introspection_endpoint"]
        except KeyError:
            # If IdP doesn't support introspection, return None
            LOG.warning(f"{self.get_name()} does not support introspection.")
            return None

        try:
            response = self._request(
                "post",
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

    def refresh_signing_keys(self) -> list[PyJWK]:
        # Keys are encoded as JWK set (https://datatracker.ietf.org/doc/html/rfc7517)
        certs = self._request("get", self.well_known["jwks_uri"])
        signing_keys = [k for k in certs["keys"] if k.get("use") == "sig"]
        if not signing_keys:
            raise ValueError("Keycloak exposes no signing keys.")
        return [PyJWK(k) for k in signing_keys]
