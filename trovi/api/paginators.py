from django.db.models import QuerySet
from django.http import JsonResponse
from drf_spectacular.plumbing import (
    build_parameter_type,
    build_basic_type,
    build_object_type,
)
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import views
from rest_framework.exceptions import NotFound
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.request import Request

from trovi.models import Artifact
from util.types import JSON


class ListArtifactsPagination(LimitOffsetPagination):
    limit_query_param = "limit"
    offset_query_param = "after"
    offset_query_description = "The initial artifact from which to start the page"
    default_limit = None
    max_limit = None
    limit = None
    offset = 0

    def get_limit(self, request: Request):
        limit = super(ListArtifactsPagination, self).get_limit(request)
        if limit is not None:
            self.limit = limit
        if self.limit is None:
            raise ValueError(
                "ListArtifact limit should not be accessed before it is set"
            )
        return self.limit

    def get_offset(self, request: Request) -> int:
        return self.offset

    def paginate_queryset(
        self, queryset: QuerySet, request: Request, view: views.View = None
    ) -> list[Artifact]:
        after = request.query_params.get(self.offset_query_param)
        if after:
            # Use values_list to get the UUIDs. This avoids getting full Artifact
            # objects with all their prefetches just to calculate an array index.
            try:
                uuids = list(str(u) for u in queryset.values_list("uuid", flat=True))
                self.offset = uuids.index(str(after))
            except ValueError:
                raise NotFound(f"Artifact with uuid {after} not found in query.")

        if self.limit is None:
            self.limit = queryset.count()

        return super(ListArtifactsPagination, self).paginate_queryset(
            queryset, request, view
        )

    def get_paginated_response_schema(self, schema: JSON) -> JSON:
        return build_object_type(
            properties={
                "artifacts": schema,
                "next": build_object_type(
                    properties={
                        "after": build_basic_type(OpenApiTypes.UUID),
                        "limit": build_basic_type(OpenApiTypes.INT),
                    }
                ),
            }
        )

    def get_schema_operation_parameters(
        self, view: views.View
    ) -> list[dict[str, JSON]]:
        return [
            build_parameter_type(
                name=self.limit_query_param,
                schema=build_basic_type(OpenApiTypes.INT),
                location=OpenApiParameter.QUERY,
                required=False,
                description=self.limit_query_description,
            ),
            build_parameter_type(
                name=self.offset_query_param,
                schema=build_basic_type(OpenApiTypes.UUID),
                location=OpenApiParameter.QUERY,
                required=False,
                description=self.offset_query_description,
            ),
        ]

    def get_paginated_response(self, data: JSON) -> JsonResponse:
        return JsonResponse(
            {
                "artifacts": data,
                "next": {
                    "after": self.get_next_link(),
                    "limit": self.limit,
                },
            }
        )
