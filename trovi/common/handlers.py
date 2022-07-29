import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from trovi.common.exceptions import InvalidToken

LOG = logging.getLogger(__name__)


def trovi_exception_handler(exc: Exception, context: dict) -> Response:
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    if not response:
        LOG.exception(exc)
        return Response(
            {"detail": "An unknown error occurred."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, InvalidToken):
        response.data = {
            "error": exc.default_code,
            "error_description": exc.detail,
        }
        if exc.error_uri:
            response.data["error_uri"] = exc.error_uri

    request = context["request"]
    status_code = response.status_code
    log_msg = f"{request.get_full_path()} {exc} {response.status_code}"
    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        LOG.error(log_msg)
    else:
        LOG.warning(log_msg)

    return response
