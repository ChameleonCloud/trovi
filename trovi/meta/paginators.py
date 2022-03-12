from django.db.models import QuerySet
from django.http import JsonResponse
from drf_spectacular.plumbing import build_object_type
from rest_framework import views
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.request import Request

from trovi.models import ArtifactTag
from util.types import JSON


class ListTagsPagination(LimitOffsetPagination):
    """
    Basic pagination class to format ListTags output.
    DRF does not make it easy to format output and having it show up in the docs
    """

    max_limit = None
    default_limit = None

    def paginate_queryset(
        self, queryset: QuerySet, request: Request, view: views.View = None
    ) -> list[ArtifactTag]:
        return list(queryset)

    def get_paginated_response(self, data: JSON) -> JsonResponse:
        return JsonResponse({"tags": data})

    def get_paginated_response_schema(self, schema: dict[str, JSON]) -> dict[str, JSON]:
        return build_object_type(properties={"tags": schema})
