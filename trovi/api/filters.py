from django.db import models
from django.db.models import F
from django.utils.translation import gettext_lazy as _
from drf_spectacular.plumbing import build_parameter_type, build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import filters, views
from rest_framework.request import Request

from trovi.common.tokens import JWT
from trovi.models import Artifact, ArtifactRole
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
            user_urn = token.to_urn()
        else:
            user_urn = None

        public = queryset.filter(visibility=Artifact.Visibility.PUBLIC)
        private = queryset.filter(visibility=Artifact.Visibility.PRIVATE)

        shared_with = private.filter(sharing_key=sharing_key)

        collaborator_of = private.filter(
            roles__user=user_urn,
            roles__role__in=(
                ArtifactRole.RoleType.COLLABORATOR,
                ArtifactRole.RoleType.ADMINISTRATOR,
            ),
        )

        has_zenodo = queryset.filter(versions__contents_urn__contains="zenodo")

        return (public | shared_with | collaborator_of | has_zenodo).distinct()

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


class ArtifactRoleFilter(filters.BaseFilterBackend):
    """
    Allows Artifact roles to be filters on user= and/or role=
    """

    role_parameter = OpenApiParameter(
        name="role",
        type=OpenApiTypes.STR,
        enum=ArtifactRole.RoleType,
        location=OpenApiParameter.QUERY,
        required=False,
        allow_blank=False,
        description="A specific role type",
    )
    user_parameter = OpenApiParameter(
        name="user",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        allow_blank=False,
        description="A user URN",
    )

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        new_queryset = queryset.all()
        if user := view.kwargs.get("user"):
            new_queryset = new_queryset.filter(user=user)
        if role := view.kwargs.get("role"):
            new_queryset = new_queryset.filter(role=role)

        return new_queryset

    def get_schema_operation_parameters(
        self, view: views.View
    ) -> list[dict[str, JSON]]:
        return [
            build_parameter_type(
                name=self.role_parameter.name,
                schema=build_basic_type(self.role_parameter.type),
                enum=self.role_parameter.enum,
                location=self.role_parameter.location,
                required=self.role_parameter.required,
                description=self.role_parameter.description,
            ),
            build_parameter_type(
                name=self.user_parameter.name,
                schema=build_basic_type(self.user_parameter.type),
                location=self.user_parameter.location,
                required=self.user_parameter.required,
                description=self.user_parameter.description,
            ),
        ]


class ArtifactRoleOrderingFilter(filters.OrderingFilter):
    """
    Handles default ordering for roles. The fields used to sort the roles is not
    accessible to users, so this class also overrides the default schema definition
    to reflect that.
    """

    ordering_param = None
    ordering_fields = ["user", "role"]

    def get_schema_fields(self, view: views.View) -> list:
        return []

    def get_schema_operation_parameters(self, view: views.View) -> list:
        return []
