from django.db import transaction
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response

from trovi.api.filters import ListArtifactsOrderingFilter
from trovi.api.paginators import ListArtifactsPagination
from trovi.api.serializers import ArtifactSerializer
from trovi.models import Artifact


class ListArtifacts(generics.ListAPIView):
    """
    /artifacts[?after=<cursor>&limit=<limit>&sort_by=<field>]

    Lists all visible artifacts for the requesting user.

    The optional "after" parameter enables pagination; it marks
    the starting point for the response.

    The optional "limit" parameter dictates how many artifacts should be returned
    in the response

    The list can be sorted by "date" or by any of the "metrics" counters.

    TODO auth
    """

    queryset = Artifact.objects.all()
    serializer_class = ArtifactSerializer
    pagination_class = ListArtifactsPagination
    filter_backends = [ListArtifactsOrderingFilter]

    @transaction.atomic
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super(ListArtifacts, self).get(request, *args, **kwargs)


class GetArtifact(generics.RetrieveAPIView):
    """
    GET /artifacts/<uuid>[?sharing_key=<key>]

    Retrieve an artifact given its ID.

    TODO auth, sharing_key
    """

    serializer_class = ArtifactSerializer
    queryset = Artifact.objects.all()

    def get_object(self) -> Artifact:
        """
        Gets an artifact model by its UUID (primary key)
        and returns its JSON representation
        """
        artifact_uuid = self.kwargs.get("artifact_uuid")
        if not artifact_uuid:
            raise ValidationError("GetArtifact request requires UUID.")
        return get_object_or_404(self.get_queryset(), uuid=artifact_uuid)
