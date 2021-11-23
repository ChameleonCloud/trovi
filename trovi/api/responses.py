import http
from django.http import JsonResponse

from util.types import JSON


class TroviErrorResponse(JsonResponse):
    status_code = 500

    def __init__(self, data: JSON, **kwargs):
        if not isinstance(data, dict):
            data = {"error": data}
        super().__init__(data, **kwargs)


class JsonServerErrorResponse(TroviErrorResponse):
    status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR


class JsonNotFoundResponse(TroviErrorResponse):
    status_code = http.HTTPStatus.NOT_FOUND


class JsonBadRequestResponse(TroviErrorResponse):
    status_code = http.HTTPStatus.BAD_REQUEST
