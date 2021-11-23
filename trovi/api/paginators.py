from django.db.models import QuerySet
from django.http import JsonResponse
from rest_framework import views
from rest_framework.exceptions import NotFound
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.request import Request

from trovi.models import Artifact
from util.types import JSON


class ListArtifactsPagination(LimitOffsetPagination):
    limit_query_param = "limit"
    offset_query_param = "after"
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
            try:
                # This should only be acceptable if it is wrapped
                # by an atomic transaction, such as ListArtifacts.get
                self.offset = (*queryset,).index(queryset.get(uuid=after))
            except Artifact.DoesNotExist:
                raise NotFound(f"Artifact with uuid {after} not found in query.")
        if self.limit is None:
            self.limit = queryset.count()
        return super(ListArtifactsPagination, self).paginate_queryset(
            queryset, request, view
        )

    def get_paginated_response_schema(self, schema: JSON) -> JSON:
        return {
            "type": "object",
            "properties": {
                "artifacts": schema,
                "next": {
                    "type": "object",
                    "properties": {
                        "after": {"type": "UUID4"},
                        "limit": {"type": "int", "nullable": True},
                    },
                },
            },
        }

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
