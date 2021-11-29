from functools import cache

from django.db import transaction
from rest_framework import viewsets, mixins
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.request import Request
from rest_framework.response import Response

from trovi.api import schema
from trovi.api.filters import ListArtifactsOrderingFilter
from trovi.api.paginators import ListArtifactsPagination
from trovi.api.parsers import JSONSchemaParser
from trovi.api.patches import ArtifactPatch
from trovi.api.permissions import SharedWithPermission
from trovi.api.serializers import ArtifactSerializer
from trovi.models import Artifact
from util.types import DummyRequest


class ArtifactViewSet(
    viewsets.GenericViewSet,
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
    permission_classes = [SharedWithPermission]
    lookup_field = "uuid"

    # JSON Patch used to provide update context to serializers
    patch = None

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
        if "partial" not in kwargs:
            raise MethodNotAllowed(
                "Full Artifact updates are not supported for UpdateArtifact. "
                "Please use PATCH with a properly formatted JSON Patch."
            )
        else:
            return super(ArtifactViewSet, self).update(request, *args, **kwargs)

    def get_parser_context(self, http_request: Request) -> dict:
        context = super(ArtifactViewSet, self).get_parser_context(http_request)
        # Since action has not been defined at this point, we can only provide reference
        # to available schema, and allow the parser to figure it out what schema
        # it needs on its own.
        context["schema"] = {
            "create": schema.CreateArtifactSchema,
            "partial_update": schema.UpdateArtifactSchema,
        }

        return context

    def get_serializer_context(self):
        context = super(ArtifactViewSet, self).get_serializer_context()
        # Plumb JSON Patches into the serializer context
        # so that the update function will understand what operations are performed
        context["patch"] = self.patch

        return context

    def get_queryset(self):
        # This override ensures relevant objects in the database to maintain the same
        # state for any operations which require that behavior.
        qs = super(ArtifactViewSet, self).get_queryset()
        if self.action in ("list", "create", "partial_update"):
            qs = qs.select_for_update()
        return qs

    @cache
    def get_object(self):
        # This override caches ``get`` queries so the same object
        # can be referenced in multiple functions without redundant database round-trips
        return super(ArtifactViewSet, self).get_object()
