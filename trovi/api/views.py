from functools import cache
from typing import Mapping

from django.db import transaction, models
from django.db.models import QuerySet
from django.utils.decorators import method_decorator
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound
from rest_framework.parsers import JSONParser, FileUploadParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
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
    ArtifactVisibilityPermission,
    ArtifactScopedPermission,
    ArtifactVersionVisibilityPermission,
    ArtifactVersionScopedPermission,
    ArtifactVersionMetricsScopedPermission,
    AdminPermission,
    ArtifactVersionMetricsVisibilityPermission,
    ArtifactVersionOwnershipPermission,
    BaseStoragePermission,
)
from trovi.models import Artifact, ArtifactVersion
from trovi.storage.serializers import StorageRequestSerializer


class APIViewSet(viewsets.GenericViewSet):
    """
    Implements generic behavior useful to all API views
    """

    action_schema_map: Mapping = None
    # Serializer used for
    patch_serializer_class: Serializer = None

    @cache
    def get_object(self) -> models.Model:
        # This override caches ``get`` queries so the same object
        # can be referenced in multiple functions without redundant database round-trips
        return super(APIViewSet, self).get_object()

    def get_queryset(self) -> QuerySet:
        # This override ensures relevant objects in the database to maintain the same
        # state for any operations which require that behavior.
        qs = super(APIViewSet, self).get_queryset()
        if self.action.lower() in ("list", "create", "update", "partial_update"):
            qs = qs.select_for_update()
        return qs

    def get_serializer_class(self):
        if self.is_patch():
            return self.patch_serializer_class
        else:
            return super(APIViewSet, self).get_serializer_class()

    def is_patch(self) -> bool:
        return self.request.method.upper() in ("PATCH", "PUT")


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
@method_decorator(transaction.atomic, name="partial_update")
class ArtifactViewSet(
    NestedViewSetMixin,
    APIViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
):
    """
    Implements all endpoints at /artifacts

    ListArtifacts: (self.list)
        GET /artifacts[?after=<cursor>&limit=<limit>&sort_by=<field>]

        Lists all visible artifacts for the requesting user.

        The optional "after" parameter enables pagination; it marks
        the starting point for the response.

        The optional "limit" parameter dictates how many artifacts should be returned
        in the response

        The list can be sorted by "date" or by any of the "metrics" counters.

    GetArtifact: (self.retrieve)
        GET /artifacts/<uuid>[?sharing_key=<key>]

        Retrieve an artifact given its ID.

    CreateArtifact: (self.create)
        POST /artifacts
        Create a new Artifact resource.

        Required scopes: artifact:write

    UpdateArtifact: (self.partial_update)
        PATCH /artifacts/<uuid>
        Update an Artifact's representation.

        Required scopes: artifact:write

        Request body: a JSON patch in the request body, which can update
        the set of parameters accepted by CreateArtifact (user-editable parameters.)

        Simple nested resources (such as tags, authors,
        linked_projects, or reproducibility) can be adjusted via this mechanism, e.g.:

        updating an author's name:
        [{"op": "replace", "path": "/authors/0/name", "value": "New name"}]

        adding an author to the end of the list:
        [{
            "op": "add",
            "path": "/authors/-",
            "value": {
                "name": "Author name",
                "affiliation": "Author affiliation",
                "email": "Author email"
            }
        }]

        adding an author to the front of the list
        (insertion happens before the index in "path"):
        [{
            "op": "add",
            "path": "/authors/0",
            "value": {
                "name": "Author name",
                "affiliation": "Author affiliation",
                "email": "Author email"
            }
        }]

        enabling reproducibility requests:
        [{"op": "replace", "path": "/reproducibility/enable_requests", "value": true}]

        Resetting sharing key is a special operation,
        which is accomplished by deleting the sharing_key parameter;
        this property can only be deleted, it cannot be replaced
        (i.e., users can not provide their own sharing key):
        [{"op": "delete", "path": "/sharing_key"}]

        TODO ?diff returns output in diff format
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
    permission_classes = [
        (ArtifactVisibilityPermission & ArtifactScopedPermission) | AdminPermission
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
    APIViewSet,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
):
    """
    Implements all endpoints at /artifacts/<uuid>/versions

    CreateArtifactVersion (self.create):
        POST /artifacts/<uuid>/versions
        Associate a new Version to an Artifact.

        Required scopes: artifact:write

        Request body:
            - contents (required):
                - urn: a URN "urn:trovi:contents:<backend>:<id>" where the ID depends
                  on the backend:
                    - chameleon: the ID is the object UUID of the artifact's tarball
                      contents in Swift
                    - zenodo: the ID is the DOI assigned by Zenodo
                    - github: the ID is the GitHub repository with an optional Git
                      reference (tag, branch) ({username|org}/{repo}[@{git_ref}])
            - links[]:
                - label: display name for the link
                - location: URN describing the type of link ("disk_image" or "dataset")
                  and its location; the precise structure can vary depending on where
                  the link points to, e.g.:
                    - disk_image:chameleon:CHI@UC:<uuid>: a Glance disk image located on
                      Chameleon site CHI@UC.
                    - disk_image:fabric:<hank>:<uuid>: a Glance disk image located on
                      some Fabric hank.
                    - dataset:globus:<endpoint>:<path>: a Globus data asset located on
                      a given endpoint at a certain path
                    - dataset:chameleon:CHI@UC:<path>: an object stored in the
                      Chameleon object store at CHI@UC at a given path.
                    - dataset:zenodo:<doi>:<path>: an asset published on Zenodo under
                      a deposition with given DOI, within a given path inside
                      that deposition.

        Version Slug:
        On creation, the artifact version is given a version slug derived from
        the date published. It has the format:

            YYYY-MM-DD[.#]
                - YYYY: current year
                - MM: current month, 0-padded
                - DD: current day, 0-padded
                - #: incrementing index, starting at 1. Increments automatically for
                  each new version published on a given day. The 1st version published
                  on a given day will not have this suffix;
                  the 2nd version will be given suffix .1, and so on.

        Unique contents
        Two ArtifactVersions cannot reference the same contents;
        if a second ArtifactVersion is created referencing the same contents URN
        as one that already exists, a 409 Conflict error is raised.

        Response: 201 Created
        Example response body:
        {
          "slug": "2021-10-07.0",
          "created_at": "2021-10-07T05:00Z",
          "contents": {
            "urn": "chameleon:108beeac-564f-4030-b126-ec4d903e680e"
          },
          "metrics": {
            "access_count": 0
          },
          "links": [
            {
              "label": "Training data",
              "verified": true,
              "urn": "dataset:globus:979a1221-8c42-41bf-bb08-4a16ed981447:/training_set"
            },
            {
              "label": "Our training image",
              "verified": true,
              "urn": "disk_image:chameleon:CHI@TACC:fd13fbc0-2d53-4084-b348-3dbd60cdc5e1"
            }
          ]
        }


    DeleteArtifactVersion (self.destroy):
        DELETE /artifacts/<uuid>/versions/<version_slug>
        Deletes a given Version of an Artifact.

        Required scopes: artifact:write

        Response: 204 No Content
    """

    queryset = ArtifactVersion.objects.all()
    parser_classes = [JSONParser]
    lookup_field = "slug__iexact"
    serializer_class = ArtifactVersionSerializer
    authentication_classes = [TroviTokenAuthentication]
    permission_classes = [
        (ArtifactVersionVisibilityPermission & ArtifactVersionScopedPermission)
        | AdminPermission,
    ]
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
            (
                ArtifactVersionMetricsScopedPermission
                & ArtifactVersionMetricsVisibilityPermission
            )
            | AdminPermission
        ],
    )
    def metrics(
        self, request: Request, parent_lookup_artifact: str, slug__iexact: str
    ) -> Response:
        """
        PUT /artifacts/<uuid>/versions/<slug>/metrics?metric=<metric_name>
        Increment the metric defined by "metric_name" for the given ArtifactVersion.

        Required scopes: artifact:write_metric (separate from :write because
        it is needed for launch actions, which don't modify artifact contents
        but must update metrics)

        Response: 204 No Content
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
        permission_classes=[BaseStoragePermission | AdminPermission],
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
    APIViewSet,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
):
    """
    POST /artifacts/<uuid>/versions/<slug>/migration
    Migrate an ArtifactVersion's contents to a different Storage Backend.

    Request body:
    * backend: the name of the Storage Backend to migrate to (e.g., "zenodo")

    Response: 202 Accepted
    {
      "status": "queued",
      "message": "Submitted",
      "message_ratio": 0.0,
    }
    """

    queryset = ArtifactVersion.objects.all()
    parser_classes = [JSONParser]
    serializer_class = ArtifactVersionMigrationSerializer
    authentication_classes = [TroviTokenAuthentication]
    permission_classes = [
        (ArtifactVersionOwnershipPermission & ArtifactVersionScopedPermission)
        | AdminPermission,
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
