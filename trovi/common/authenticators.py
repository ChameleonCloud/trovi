from typing import Optional

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.request import Request

from trovi.common.tokens import JWT


class TroviTokenAuthentication(BaseAuthentication):
    """
    Verifies a Trovi token and extracts metadata from it
    """

    def authenticate(self, request: Request) -> Optional[tuple[None, JWT]]:
        access_token = request.query_params.get("access_token")
        if not access_token:
            # If authentication doesn't occur, this method is supposed to return None
            return None
        # The token returned from here is attached to the relevant request object
        # The User model is omitted since all user data is embedded in the token
        # Authentication (token verification) is performed when the token is decoded
        return None, JWT.from_jws(access_token)

    def authenticate_header(self, _: Request) -> str:
        return "Token"


class AlwaysFailAuthentication(BaseAuthentication):
    def authenticate(self, request: Request):
        # Any endpoint which has this authenticator enabled is probably
        # one we don't want anyone to know about
        raise NotFound()


class AlwaysPassAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[None, None]:
        return None, None
