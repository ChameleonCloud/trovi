from abc import abstractmethod, ABC
from datetime import datetime
from typing import Optional, Any, Iterable

from django.conf import settings
from jose.backends.base import Key

from trovi.common.exceptions import InvalidToken
from trovi.common.tokens import JWT, OAuth2TokenIntrospection
from util.decorators import timed_asynchronous_lru_cache, retry


class IdentityProviderClient(ABC):
    """
    Base interface for an Identity Provider Client

    TODO As of now, this interface is extremely subject to change as we learn more
         about what way is best to support arbitrary IdPs.

    This class is designed to authenticate users to the Identity Provider by exchanging
    valid IdP subject tokens for for Trovi access tokens.
    The subject token is obtained out-of-band by the end-user, and then provided to
    the ``TokenGrant`` endpoint.
    All tokens are formatted as JWTs (https://datatracker.ietf.org/doc/html/rfc7519)

    Implementers of this class can make the following assumptions
    about the subject token, as these assumptions are validated
    by the ``TokenGrantRequestSerializer``:
        - ``aud`` has Trovi's FQDN in the audience list
        - ``iss`` points to the canonical URL of the Identity Provider
        - ``azp`` must be the client ID of the introspecting application
        - ``scopes`` are valid Trovi scopes
    Any other assumptions pertaining to individual Identity Providers must be
    validated by this class.

    Identity Providers supported by this class SHOULD adhere to the following
    policies:
        - Support OAuth 2.0 Token Introspection
          (https://datatracker.ietf.org/doc/html/rfc7662)
            - If not supported, Trovi users logging in via the IdP
              cannot be properly logged out when tokens are revoked by the IdP.
        - Include a list of groups of which the user is a member
          within the subject token
          - If not, some functionality such as linking an Artifact to a project
            will not be possible.
    """

    @abstractmethod
    def get_name(self) -> str:
        """
        Name used to reference the provider in tests and log messages
        """

    @abstractmethod
    def get_client_token(self, **kwargs) -> Any:
        """
        Obtains the client credentials for this client, as configured by the
        Identity Provider Client implementer.

        The token can be in any form that can be passed directly to any
        authentication agents that will accept it.
        """

    @abstractmethod
    def get_user_token(
        self, username: str, password: str, client_id: str, client_secret: str, **kwargs
    ) -> Any:
        """
        Obtain a user token.

        The client ID/secret should be a client that can provide tokens to a user that
        are used to authenticate to Trovi. The client should not be Trovi itself.
        """

    @abstractmethod
    def get_actor_subject(self) -> str:
        """
        Used to link Trovi Tokens back to the authorizing actor (the IdP)
        This should be the FQDN of the value that the IdP's token endpoint inserts
        into the 'iss' claim for its subject tokens. TODO figure out way to match NIDs without URLs
        """

    @abstractmethod
    def get_authorized_party(self, subject_token: JWT) -> str:
        """
        Used to fill in the "username" (azp) for the Trovi Token. This should be
        the requesting user's email address.
        """

    @abstractmethod
    def validate_subject_token(self, subject_token: JWT) -> JWT:
        """
        Validates a JWT per the specification of the Identity Provider
        """

    def exchange_token(
        self, subject_token: JWT, requested_scope: Iterable[JWT.Scopes] = None
    ) -> JWT:
        """
        Performs OAuth 2.0 Token Exchange
        (https://datatracker.ietf.org/doc/html/rfc8693)

        Exchanges a _valid_ subject token for a Trovi token.
        """
        scopes = (
            requested_scope
            if requested_scope is not None
            else [JWT.Scopes.ARTIFACTS_READ]
        )
        # Tokens which request *:write scopes must be validated online
        if any(scope.is_write_scope() for scope in scopes):
            introspection = self.introspect_token(subject_token)
            if introspection and not introspection.active:
                raise InvalidToken("Subject token revoked.")

        return JWT(
            azp=(email := self.get_authorized_party(subject_token)),
            aud=settings.TROVI_FQDN,
            iss=settings.TROVI_FQDN,
            iat=(now := int(datetime.utcnow().timestamp())),
            sub=email,
            exp=now + settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS,
            scope=scopes,
            alg=settings.AUTH_TROVI_TOKEN_SIGNING_ALGORITHM,
            key=settings.AUTH_TROVI_TOKEN_SIGNING_KEY,
            act={"sub": self.get_actor_subject()},
        )

    @abstractmethod
    def introspect_token(
        self, subject_token: JWT
    ) -> Optional[OAuth2TokenIntrospection]:
        """
        Performs OAuth 2.0 Token Introspection
        (https://datatracker.ietf.org/doc/html/rfc7662)

        If introspection is not supported by the Identity Provider, this method should
        return None.
        """

    @abstractmethod
    def refresh_signing_keys(self) -> list[Key]:
        """
        Attempt one time to refresh the Identity Provider's signing keys.
        """

    @property
    @timed_asynchronous_lru_cache(
        maxsize=1, timeout=settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS
    )
    @retry(
        n=settings.AUTH_IDP_SIGNING_KEY_REFRESH_RETRY_ATTEMPTS,
        cond=lambda keys: isinstance(keys, list)
        and all(isinstance(k, Key) for k in keys),
        wait=settings.AUTH_IDP_SIGNING_KEY_REFRESH_RETRY_SECONDS,
        msg="Failed to refresh token signing key from Identity Provider.",
    )
    def signing_keys(self) -> list[Key]:
        """
        Retains a cached copy of the Identity Provider's signing keys. Lazily refreshes
        every 5 minutes.
        """
        return self.refresh_signing_keys()
