from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "unique"


class InvalidToken(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "invalid_token"
    error_uri = None
    default_detail = _(
        "The request is missing a required parameter, "
        "includes an unsupported parameter value (other than grant type), "
        "repeats a parameter, includes multiple credentials, "
        "utilizes more than one mechanism for authenticating the client, "
        "or is otherwise malformed."
    )


class InvalidClient(InvalidToken):
    default_code = "invalid_client"
    default_detail = _(
        "Client authentication failed "
        "(e.g., unknown client, no client authentication included, "
        "or unsupported authentication method)"
    )


class InvalidGrant(InvalidToken):
    default_code = "invalid_grant"
    default_detail = _(
        "The provided authorization grant "
        "(e.g., authorization code, resource owner credentials) or refresh token is "
        "invalid, expired, revoked, does not match the redirection URI used in the "
        "authorization request, or was issued to another client."
    )


class UnauthorizedClient(InvalidToken):
    default_code = "unauthorized_client"
    default_detail = _(
        "The authenticated client is not authorized to use this "
        "authorization grant type."
    )


class UnsupportedGrantType(InvalidToken):
    default_code = "unsupported_grant_type"
    default_detail = _(
        "The authorization grant type is not supported by the authorization server."
    )


class InvalidScope(InvalidToken):
    default_code = "invalid_scope"
    default_detail = _(
        "The requested scope is invalid, unknown, malformed, "
        "or exceeds the scope granted by the resource owner."
    )
