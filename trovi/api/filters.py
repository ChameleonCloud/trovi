import shlex
from django.db import models
from django.db.models import F, Q, Count
from django.utils.translation import gettext_lazy as _
from drf_spectacular.plumbing import build_parameter_type, build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import filters, views
from rest_framework.request import Request

from trovi.common.tokens import JWT
from trovi.models import Artifact, ArtifactRole, ArtifactEvent
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
    ordering_fields = [
        "date",
        "created_at",
        "access_count",
        "updated_at",
        "unique_access_count",
        "unique_cell_execution_count",
    ]
    ordering_description = _("The criteria by which to sort the Artifacts.")

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        # Annotate the query such that the database understands our sort_by params
        prepared_query = queryset.annotate(
            date=F("created_at"),
            unique_access_count=Count(
                "versions__events__event_origin",
                distinct=True,
                filter=Q(
                    versions__events__event_type=ArtifactEvent.EventType.LAUNCH.value
                ),
            ),
            unique_cell_execution_count=Count(
                "versions__events__event_origin",
                distinct=True,
                filter=Q(
                    versions__events__event_type=ArtifactEvent.EventType.CELL_EXECUTION.value
                ),
            ),
        )

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


class ArtifactSearchFilter(filters.BaseFilterBackend):
    """
    Filters artifacts by a search query.
    The query will search across title, description, owners, authors, and tags.
    """

    search_param = "q"
    search_description = _(
        "A search term to filter artifacts by. "
        "Supports boolean operators: implicit AND, OR, and - for NOT. "
    )

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        search_term = request.query_params.get(self.search_param)
        if not search_term:
            return queryset

        def get_term_query(term: str) -> Q:
            return (
                Q(title__icontains=term)
                | Q(short_description__icontains=term)
                | Q(long_description__icontains=term)
                | Q(owner_urn__icontains=term)
                | Q(authors__full_name__icontains=term)
                | Q(tags__tag__icontains=term)
            )

        # Handle quoted phrases
        tokens = shlex.split(search_term)

        # Handles boolean precedence.
        # It splits the query by "OR" to create groups of terms.
        # Each group is then processed for implicit "AND"s and "NOT"s.
        # e.g. "a b OR c -d" -> ( (a AND b) OR (c AND NOT d) )
        final_query = Q()
        or_groups = " ".join(tokens).split(" OR ")

        for or_group_str in or_groups:
            if not or_group_str.strip():
                continue

            and_query = Q()
            and_tokens = shlex.split(or_group_str)
            for token in and_tokens:
                if token.startswith("-"):
                    and_query &= ~get_term_query(token[1:])
                else:
                    and_query &= get_term_query(token)

            final_query |= and_query

        return queryset.filter(final_query).distinct()

    def get_schema_operation_parameters(
        self, view: views.View
    ) -> list[dict[str, JSON]]:
        return [
            build_parameter_type(
                name=self.search_param,
                schema=build_basic_type(OpenApiTypes.STR),
                location=OpenApiParameter.QUERY,
                description=self.search_description,
            )
        ]


class ArtifactTagFilter(filters.BaseFilterBackend):
    """
    Filters artifacts by one or more tags.
    """

    tag_param = "tag"
    tag_description = _("An artifact tag to filter by. Can be specified multiple times.")

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        tags = request.query_params.getlist(self.tag_param)
        if not tags:
            return queryset

        for tag in tags:
            queryset = queryset.filter(tags__tag__iexact=tag)

        return queryset

    def get_schema_operation_parameters(
        self, view: views.View
    ) -> list[dict[str, JSON]]:
        return [
            build_parameter_type(
                name=self.tag_param,
                schema=build_object_type(
                    type=OpenApiTypes.ARRAY, items={"type": OpenApiTypes.STR}
                ),
                location=OpenApiParameter.QUERY,
                description=self.tag_description,
                explode=False,
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


class ArtifactOwnerFilter(filters.BaseFilterBackend):
    """
    Filters artifacts by owner URN.
    """

    owner_param = "owner"
    owner_description = _("The URN of the artifact owner to filter by.")

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        owner_urn = request.query_params.get(self.owner_param)
        if owner_urn:
            return queryset.filter(owner_urn=owner_urn)
        return queryset

    def get_schema_operation_parameters(
        self, view: views.View
    ) -> list[dict[str, JSON]]:
        return [
            build_parameter_type(
                name=self.owner_param,
                schema=build_basic_type(OpenApiTypes.STR),
                location=OpenApiParameter.QUERY,
                required=False,
                description=self.owner_description,
            )
        ]


class ArtifactAuthorNameFilter(filters.BaseFilterBackend):
    """
    Filters artifacts by author's name.
    """

    author_param = "author_name"
    author_description = _("A partial or full name of an author to filter by.")

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        author_name = request.query_params.get(self.author_param)
        if author_name:
            return queryset.filter(authors__full_name__icontains=author_name).distinct()
        return queryset

    def get_schema_operation_parameters(
        self, view: views.View
    ) -> list[dict[str, JSON]]:
        return [
            build_parameter_type(
                name=self.author_param,
                schema=build_basic_type(OpenApiTypes.STR),
                location=OpenApiParameter.QUERY,
                required=False,
                description=self.author_description,
            )
        ]


class ArtifactAccessCountFilter(filters.BaseFilterBackend):
    """
    Filters artifacts by their total access count within a specified range.
    """

    min_access_param = "min_access_count"
    max_access_param = "max_access_count"
    min_access_description = _("Minimum total access count for an artifact.")
    max_access_description = _("Maximum total access count for an artifact.")

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        min_count = request.query_params.get(self.min_access_param)
        max_count = request.query_params.get(self.max_access_param)

        if min_count:
            try:
                queryset = queryset.filter(access_count__gte=int(min_count))
            except ValueError:
                raise ValidationError({self.min_access_param: "Must be an integer."})
        if max_count:
            try:
                queryset = queryset.filter(access_count__lte=int(max_count))
            except ValueError:
                raise ValidationError({self.max_access_param: "Must be an integer."})
        return queryset

    def get_schema_operation_parameters(
        self, view: views.View
    ) -> list[dict[str, JSON]]:
        return [
            build_parameter_type(
                name=self.min_access_param,
                schema=build_basic_type(OpenApiTypes.INT),
                location=OpenApiParameter.QUERY,
                required=False,
                description=self.min_access_description
            ),
            build_parameter_type(
                name=self.max_access_param,
                schema=build_basic_type(OpenApiTypes.INT),
                location=OpenApiParameter.QUERY,
                required=False,
                description=self.max_access_description
            ),
        ]
