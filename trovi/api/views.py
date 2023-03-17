from functools import cache

from django.db import transaction
from django.utils.decorators import method_decorator
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import mixins, status, generics
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, ValidationError
from rest_framework.parsers import JSONParser, FileUploadParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_extensions.mixins import NestedViewSetMixin

from trovi.api.docs.extensions import (
    ArtifactTagSerializerExtension,
    ArtifactProjectSerializerExtension,
    TroviTokenAuthenticationExtension,
    TokenGrantRequestSerializerExtension,
)
from trovi.api.filters import (
    ListArtifactsOrderingFilter,
    ListArtifactsVisibilityFilter,
    sharing_key_parameter,
)
from trovi.api.paginators import ListArtifactsPagination
from trovi.api.serializers import (
    ArtifactVersionSerializer,
    ArtifactPatchSerializer,
    ArtifactSerializer,
    ArtifactVersionMetricsSerializer,
    ArtifactVersionMigrationSerializer,
)
from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.permissions import (
    ArtifactVersionMetricsUpdatePermission,
    ArtifactViewPermission,
    ArtifactReadScopePermission,
    ArtifactWriteScopePermission,
    ArtifactEditPermission,
    ParentArtifactViewPermission,
    ParentArtifactAdminPermission,
    ParentArtifactEditPermission,
    ArtifactVersionDestroyDOIPermission,
    ArtifactWriteMetricsScopePermission,
)
from trovi.common.views import TroviAPIViewSet
from trovi.fields import URNField
from trovi.models import Artifact, ArtifactVersion
from trovi.storage.serializers import StorageRequestSerializer


@extend_schema_view(
    list=extend_schema(
        description="Lists all visible artifacts for the requesting user.",
    ),
    retrieve=extend_schema(
        parameters=[sharing_key_parameter],
        description="Retrieve an artifact given its ID.",
    ),
    create=extend_schema(description="Create a new Artifact resource."),
    update=extend_schema(
        parameters=[
            OpenApiParameter(
                name="partial",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Signifies that the update specified is partial. "
                "Required 'true' to make PUT requests.",
            )
        ],
        description=(update_description := "Update an Artifact's representation."),
    ),
    partial_update=extend_schema(description=update_description),
)
@method_decorator(transaction.atomic, name="list")
class ArtifactViewSet(
    NestedViewSetMixin,
    TroviAPIViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
):
    """
    Implements all endpoints at /artifacts
    """

    queryset = Artifact.objects.all().prefetch_related()
    serializer_class = ArtifactSerializer
    patch_serializer_class = ArtifactPatchSerializer
    parser_classes = [JSONParser]
    pagination_class = ListArtifactsPagination
    filter_backends = [ListArtifactsVisibilityFilter, ListArtifactsOrderingFilter]
    ordering = "updated_at"
    ordering_fields = ["date", "updated_at", "access_count"]
    authentication_classes = [TroviTokenAuthentication]
    # Individual visibility checks are handled by the visibility filter
    list_permission_classes = [ArtifactReadScopePermission]
    retrieve_permission_classes = [
        ArtifactReadScopePermission,
        ArtifactViewPermission,
    ]
    create_permission_classes = [ArtifactWriteScopePermission]
    update_permission_classes = [
        ArtifactReadScopePermission,
        ArtifactWriteScopePermission,
        ArtifactViewPermission,
        ArtifactEditPermission,
    ]
    lookup_field = "uuid"
    openapi_extensions = [
        ArtifactTagSerializerExtension,
        ArtifactProjectSerializerExtension,
        TroviTokenAuthenticationExtension,
        TokenGrantRequestSerializerExtension,
    ]

    @transaction.atomic
    def update(self, request: Request, *args, **kwargs) -> Response:
        # This method is implemented by the UpdateMixin to support the PUT method
        # We don't support full updates, so this endpoint is overridden here
        # to prevent it from being accessed.
        if not self.is_patch():
            raise MethodNotAllowed(
                "Full Artifact updates are not supported for UpdateArtifact. "
                "Please use PATCH with a properly formatted JSON Patch."
            )
        else:
            return super(ArtifactViewSet, self).update(request, *args, **kwargs)


parent_artifact_parameter = OpenApiParameter(
    name="parent_lookup_artifact",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.PATH,
    required=True,
    allow_blank=False,
    description="The UUID of the Artifact to which the Version belongs.",
)


@extend_schema_view(
    create=extend_schema(
        parameters=[parent_artifact_parameter],
        description="Associate a new Version to an Artifact.",
    ),
    destroy=extend_schema(
        parameters=[
            parent_artifact_parameter,
            OpenApiParameter(
                name="slug__iexact",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                required=True,
                allow_blank=False,
                description="The slug for the Version to be deleted.",
            ),
        ],
        description="Deletes a given Version of an Artifact.",
    ),
    metrics=extend_schema(
        parameters=[
            OpenApiParameter(
                name="origin",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                allow_blank=False,
                description="The Trovi token "
                "of the user who triggered the metric update",
            ),
            OpenApiParameter(
                name="metric",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                allow_blank=False,
                enum=["access_count", "cell_execution_count"],
                description="The metric which will be incremented",
            ),
            OpenApiParameter(
                name="amount",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                default=1,
                description="The amount by which the selected metric "
                "will be incremented",
            ),
        ],
        description="Increments a particular metric for an artifact version",
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None},
    ),
)
@method_decorator(transaction.atomic, name="destroy")
class ArtifactVersionViewSet(
    NestedViewSetMixin,
    TroviAPIViewSet,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
):
    """
    Implements all endpoints at /artifacts/<uuid>/versions
    """

    queryset = ArtifactVersion.objects.all()
    parser_classes = [JSONParser]
    lookup_field = "slug__iexact"
    serializer_class = ArtifactVersionSerializer
    authentication_classes = [TroviTokenAuthentication]
    permission_classes = [
        ArtifactWriteScopePermission,
        ParentArtifactViewPermission,
        ParentArtifactEditPermission,
    ]
    destroy_permission_classes = [ArtifactVersionDestroyDOIPermission]
    lookup_value_regex = "[^/]+"

    # metrics endpoints are defined here, as they are attached to artifact versions
    # and don't represent an additional model. This also allows us to create the
    # URL path as it was designed.
    @transaction.atomic
    @action(
        methods=["put"],
        detail=False,
        url_name="metrics",
        url_path=f"(?P<{lookup_field}>{lookup_value_regex})/metrics",
        # These override the class's variables
        patch_serializer_class=ArtifactVersionMetricsSerializer,
        serializer_class=ArtifactVersionMetricsSerializer,
        permission_classes=[
            ArtifactWriteMetricsScopePermission,
            ArtifactVersionMetricsUpdatePermission,
        ],
    )
    def metrics(
        self, request: Request, parent_lookup_artifact: str, slug__iexact: str
    ) -> Response:
        """
        Increment the metric defined by "metric_name" for the given ArtifactVersion.
        """
        metric = request.query_params.get("metric")
        amount = request.query_params.get("amount", 1)
        origin = request.query_params.get("origin")
        version = self.get_object()
        serializer = self.get_serializer(
            version, data={metric: amount, "origin": origin}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        methods=["get"],
        detail=True,
        url_name="contents",
        serializer_class=StorageRequestSerializer,
        permission_classes=[ParentArtifactViewPermission],
        parser_classes=[FileUploadParser],
    )
    def contents(
        self, request: Request, parent_lookup_artifact: str, slug__iexact: str
    ) -> Response:
        """
        Faster proxy for /contents/?urn=<urn>

        Rather than searching by URN, we grab the contents directly from the object
        """
        return mixins.RetrieveModelMixin.retrieve(
            self, request, parent_lookup_artifact, slug__iexact
        )


@extend_schema_view(
    list=extend_schema(
        description="Check the status of the most-recently queued "
        "artifact version content migration",
    ),
    create=extend_schema(
        description="Queue an artifact version's contents to be transferred "
        "to a different storage backend. "
        "One migration can be in progress at a time.",
        responses={status.HTTP_202_ACCEPTED: ArtifactVersionMigrationSerializer},
    ),
)
class MigrateArtifactVersionViewSet(
    NestedViewSetMixin,
    TroviAPIViewSet,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
):
    """
    Migrate an ArtifactVersion's contents to a different Storage Backend.
    """

    queryset = ArtifactVersion.objects.all()
    parser_classes = [JSONParser]
    serializer_class = ArtifactVersionMigrationSerializer
    authentication_classes = [TroviTokenAuthentication]
    permission_classes = [
        ArtifactWriteScopePermission,
        ParentArtifactEditPermission,
    ]
    lookup_value_regex = "[^/]+"

    def list(self, request: Request, *args, **kwargs) -> Response:
        version = self.get_object()
        latest_migrations = version.migrations.order_by("-created_at")
        if not latest_migrations.exists():
            raise NotFound(
                f"No existing migrations for {version.artifact.uuid}/{version.slug}"
            )
        migration = latest_migrations.first()
        serializer = self.get_serializer(migration)
        return Response(status=status.HTTP_202_ACCEPTED, data=serializer.data)
