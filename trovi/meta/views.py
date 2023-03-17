from django.db import transaction
from django.utils.decorators import method_decorator
from rest_framework import filters, mixins
from rest_framework.parsers import JSONParser

from trovi.api.serializers import ArtifactTagSerializerWritable
from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.permissions import TroviAdminPermission
from trovi.common.views import TroviAPIViewSet
from trovi.meta.paginators import ListTagsPagination
from trovi.models import ArtifactTag


@method_decorator(transaction.atomic, name="list")
@method_decorator(transaction.atomic, name="create")
class ArtifactTagsView(TroviAPIViewSet, mixins.ListModelMixin, mixins.CreateModelMixin):
    """
    Simple view for fetching tags. Only admins may upload new tags
    """

    queryset = ArtifactTag.objects.all()
    serializer_class = ArtifactTagSerializerWritable
    parser_classes = [JSONParser]
    ordering = "tag"
    filter_backends = [filters.OrderingFilter]
    pagination_class = ListTagsPagination
    authentication_classes = [TroviTokenAuthentication]
    list_permission_classes = []
    create_permission_classes = [TroviAdminPermission]
