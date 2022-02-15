from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "unique"


class InvalidToken(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("Token is invalid or expired")
    default_code = "token_not_valid"
