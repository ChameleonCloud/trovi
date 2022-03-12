from rest_framework import filters, viewsets, mixins
from rest_framework.parsers import JSONParser

from trovi.api.serializers import ArtifactTagSerializerWritable
from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.permissions import BaseMetadataPermission
from trovi.meta.paginators import ListTagsPagination
from trovi.models import ArtifactTag


class ArtifactTagsView(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.CreateModelMixin
):
    """
    Simple view for fetching tags. Only admins may upload new tags
    """

    queryset = ArtifactTag.objects.all()
    serializer_class = ArtifactTagSerializerWritable
    parser_classes = [JSONParser]
    ordering_fields = ["tag"]
    filter_backends = [filters.OrderingFilter]
    pagination_class = ListTagsPagination
    authentication_classes = [TroviTokenAuthentication]
    permission_classes = [BaseMetadataPermission]
