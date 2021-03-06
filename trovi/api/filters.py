from django.db import models
from django.db.models import F
from django.utils.translation import gettext_lazy as _
from drf_spectacular.plumbing import build_parameter_type, build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import filters, views
from rest_framework.request import Request

from trovi.common.tokens import JWT
from trovi.models import Artifact
from util.types import JSON

sharing_key_parameter = OpenApiParameter(
    name="sharing_key",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=False,
    allow_blank=False,
    description="An artifact sharing key.",
)


class ListArtifactsOrderingFilter(filters.OrderingFilter):
    """
    Handles sorting for ListArtifacts
    """

    ordering_param = "sort_by"
    ordering_fields = ["date", "access_count", "updated_at"]
    ordering_description = _("The criteria by which to sort the Artifacts.")

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:

        # Annotate the query such that the database understands our sort_by params
        prepared_query = queryset.annotate(date=F("created_at"))

        # The prepared query from above will be sorted properly using the
        # sort_by url param in the super call here
        return (
            super(ListArtifactsOrderingFilter, self)
            .filter_queryset(request, prepared_query, view)
            .reverse()
        )

    def get_schema_operation_parameters(
        self, view: views.View
    ) -> list[dict[str, JSON]]:
        return [
            build_parameter_type(
                name=self.ordering_param,
                schema=build_basic_type(OpenApiTypes.STR),
                location=OpenApiParameter.QUERY,
                required=False,
                description=self.ordering_description,
                enum=self.ordering_fields,
                default=getattr(view, "ordering", "-"),
            ),
        ]


class ListArtifactsVisibilityFilter(filters.BaseFilterBackend):
    """
    Filters the queryset for Artifacts that the user has permission to see
    """

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        # TODO support multiple sharing keys
        sharing_key = request.query_params.get("sharing_key")
        token = JWT.from_request(request)

        if token:
            if token.is_admin():
                return queryset
            owner_urn = token.to_urn()
        else:
            owner_urn = None

        public = queryset.filter(visibility=Artifact.Visibility.PUBLIC)
        private = queryset.filter(visibility=Artifact.Visibility.PRIVATE)

        if sharing_key:
            shared_with = private.filter(sharing_key=sharing_key)
        else:
            shared_with = Artifact.objects.none()
        owner_of = private.filter(owner_urn=owner_urn)

        has_zenodo = queryset.filter(versions__contents_urn__contains="zenodo")

        return (public | shared_with | owner_of | has_zenodo).distinct()

    def get_schema_operation_parameters(
        self, view: views.View
    ) -> list[dict[str, JSON]]:
        return [
            build_parameter_type(
                name=sharing_key_parameter.name,
                schema=build_basic_type(sharing_key_parameter.type),
                location=sharing_key_parameter.location,
                required=sharing_key_parameter.required,
                description=sharing_key_parameter.description,
            )
        ]
