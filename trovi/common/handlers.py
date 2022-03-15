from rest_framework.response import Response
from rest_framework.views import exception_handler

from trovi.common.exceptions import InvalidToken


def trovi_exception_handler(exc: Exception, context: dict) -> Response:
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    if isinstance(exc, InvalidToken):
        response.data = {
            "error": exc.default_code,
            "error_description": exc.detail,
        }
        if exc.error_uri:
            response.data["error_uri"] = exc.error_uri

    return response
