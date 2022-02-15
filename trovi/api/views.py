from functools import cache
from typing import Mapping

from django.db import transaction, models
from django.db.models import QuerySet
from requests.structures import CaseInsensitiveDict
from rest_framework import viewsets, mixins
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_extensions.mixins import NestedViewSetMixin

from trovi.api import schema
from trovi.api.filters import ListArtifactsOrderingFilter
from trovi.api.paginators import ListArtifactsPagination
from trovi.api.parsers import JSONSchemaParser
from trovi.api.patches import ArtifactPatch
from trovi.api.serializers import ArtifactSerializer, ArtifactVersionSerializer
from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.permissions import (
    ArtifactVisibilityPermission,
    ArtifactScopedPermission,
    ArtifactVersionVisibilityPermission,
    ArtifactVersionScopedPermission,
)
from trovi.models import Artifact, ArtifactVersion
from util.types import DummyRequest


class APIViewSet(viewsets.GenericViewSet):
    """
    Implements generic behavior useful to all API views
    """

    action_schema_map: Mapping

    @cache
    def get_object(self) -> models.Model:
        # This override caches ``get`` queries so the same object
        # can be referenced in multiple functions without redundant database round-trips
        return super(APIViewSet, self).get_object()

    def get_queryset(self) -> QuerySet:
        # This override ensures relevant objects in the database to maintain the same
        # state for any operations which require that behavior.
        qs = super(APIViewSet, self).get_queryset()
        if self.action in ("list", "create", "partial_update"):
            qs = qs.select_for_update()
        return qs

    def get_parser_context(self, http_request: Request) -> dict:
        context = super(APIViewSet, self).get_parser_context(http_request)

        # Since action has not been defined at this point, we determine the appropriate
        # schema via the request method
        if (json_schema := self.action_schema_map.get(self.request.method)) is not None:
            context["schema"] = json_schema

        return context


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

    queryset = Artifact.objects.all()
    serializer_class = ArtifactSerializer
    parser_classes = [JSONSchemaParser]
    pagination_class = ListArtifactsPagination
    filter_backends = [ListArtifactsOrderingFilter]
    authentication_classes = [TroviTokenAuthentication]
    permission_classes = [ArtifactVisibilityPermission, ArtifactScopedPermission]
    lookup_field = "uuid"

    # JSON Patch used to provide update context to serializers
    patch = None

    action_schema_map = CaseInsensitiveDict(
        {
            "POST": schema.CreateArtifactSchema,
            "PATCH": schema.UpdateArtifactSchema,
            "UPDATE": schema.UpdateArtifactSchema,
        }
    )

    @transaction.atomic
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super(ArtifactViewSet, self).list(request, *args, **kwargs)

    @transaction.atomic
    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        # Since the serializer doesn't understand JSON Patch,
        # we apply the patch here, and then pass the resultant object on
        # as a regular update.
        artifact = self.get_serializer(self.get_object()).data
        raw = request.data
        self.patch = ArtifactPatch(raw)
        diff = self.patch.apply(artifact)
        # Here, we get around request objects being mostly immutable (for good reason).
        # This could be dangerous if rest_framework makes changes to its mixins.
        # If this endpoint starts failing, don't be surprised if this is why.
        # Since the super call only needs the request to pull the body (data) from it,
        # we can simply just pass it a named tuple with the attribute it references.
        dummy_request = DummyRequest(data=diff)
        return super(ArtifactViewSet, self).partial_update(
            dummy_request, *args, **kwargs
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        # This method is implemented by the UpdateMixin to support the PUT method
        # We don't support full updates, so this endpoint is overridden here
        # to prevent it from being accessed.
        if not self.patch:
            raise MethodNotAllowed(
                "Full Artifact updates are not supported for UpdateArtifact. "
                "Please use PATCH with a properly formatted JSON Patch."
            )
        else:
            return super(ArtifactViewSet, self).update(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super(ArtifactViewSet, self).get_serializer_context()
        # Plumb JSON Patches into the serializer context
        # so that the update function will understand what operations are performed
        context["patch"] = self.patch

        return context


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
                - urn: a URN "contents:<backend>:<id>" where the ID depends on the
                  backend:
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
    parser_classes = [JSONSchemaParser]
    lookup_field = "slug__iexact"
    serializer_class = ArtifactVersionSerializer
    authentication_classes = [TroviTokenAuthentication]
    permission_classes = [
        ArtifactVersionVisibilityPermission,
        ArtifactVersionScopedPermission,
    ]
    lookup_value_regex = "[^/]+"

    action_schema_map = CaseInsensitiveDict(
        {
            "POST": schema.CreateArtifactVersionSchema,
        }
    )
