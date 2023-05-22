import logging
from typing import Optional

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request

from trovi.common.tokens import JWT

LOG = logging.getLogger(__name__)


class TroviTokenAuthentication(BaseAuthentication):
    """
    Verifies a Trovi token and extracts metadata from it
    """

    def authenticate(self, request: Request) -> Optional[tuple[None, Optional[JWT]]]:
        # First attempt to fetch the token from the access_token parameter.
        # This parameter will override the header if both are provided.
        access_token = request.query_params.get("access_token")
        # If the user doesn't provide access_token, we check the headers
        # since that's usually where tokens are delivered
        if not access_token:
            # The header should be in the format Authorization: bearer <token>
            authz_header = request.headers.get("Authorization", "").split()
            if not authz_header:
                return None, None
            if len(authz_header) != 2:
                raise ValidationError("Malformed Authorization header")
            scheme, access_token = authz_header
            if scheme != "bearer":
                raise ValidationError(
                    f"Unknown authentication scheme: {scheme}. "
                    f"Supported scheme is 'bearer'"
                )
        # The token returned from here is attached to the relevant request object
        # The User model is omitted since all user data is embedded in the token
        # Authentication (token verification) is performed when the token is decoded
        token = JWT.from_jws(access_token)
        if token:
            LOG.debug(f"Authenticated user {token.to_urn()}")
        return None, token

    def authenticate_header(self, _: Request) -> str:
        return "Bearer"


class AlwaysFailAuthentication(BaseAuthentication):
    def authenticate(self, request: Request):
        # Any endpoint which has this authenticator enabled is probably
        # one we don't want anyone to know about
        raise NotFound()
