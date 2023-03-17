from django.db import transaction
from django.utils.decorators import method_decorator
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    extend_schema_view,
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
)
from rest_framework import mixins
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FileUploadParser
from rest_framework.request import Request
from rest_framework.response import Response

from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.permissions import (
    ArtifactWriteScopePermission,
    ArtifactReadScopePermission,
    AuthenticatedWithTroviTokenPermission,
    RootStorageDownloadPermission,
)
from trovi.common.schema import StorageViewSetAutoSchema
from trovi.common.views import TroviAPIViewSet
from trovi.models import ArtifactVersion
from trovi.storage.serializers import StorageRequestSerializer


@extend_schema_view(
    create=extend_schema(
        description="Upload an artifact archive to a storage backend.",
        parameters=[
            OpenApiParameter(
                name="backend",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                enum=["chameleon"],
                description="The storage backend to which the archive will be uploaded.",
            ),
            OpenApiParameter(
                name="content-disposition",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                examples=[
                    OpenApiExample(
                        name="filename",
                        value="attachment; filename=foo.tar.gz",
                        media_type="application/tar+gz",
                        description="Pass a filename",
                    )
                ],
                description="Includes metadata about the uploaded file.",
            ),
        ],
    ),
    list=extend_schema(
        description="Retrieve metadata about an artifact archive.",
        parameters=[
            OpenApiParameter(
                name="urn",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="The URN of the archive for which metadata will be fetched.",
            ),
            OpenApiParameter(
                name="content-type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                enum=["application/tar+gz"],
            ),
        ],
    ),
)
@method_decorator(transaction.atomic, name="create")
class StorageViewSet(TroviAPIViewSet, mixins.CreateModelMixin, mixins.ListModelMixin):
    """
    Implements all endpoints at /contents
    """

    queryset = ArtifactVersion.objects.all()
    parser_classes = [FileUploadParser]
    authentication_classes = [TroviTokenAuthentication]
    create_permission_classes = [
        ArtifactWriteScopePermission,
        AuthenticatedWithTroviTokenPermission,
    ]
    list_permission_classes = [
        ArtifactReadScopePermission,
        RootStorageDownloadPermission,
    ]
    serializer_class = StorageRequestSerializer
    lookup_field = "contents_urn__iexact"
    lookup_url_kwarg = "urn"

    @transaction.atomic
    def list(self, request: Request, *args, **kwargs) -> Response:
        # Because of the weird way this method is implemented as a hack to give it the
        # correct URL path, we have to shove the necessary URL params into self.kwargs
        # because they are not resolved properly. Pre-processing for .list ignores
        # the lookup_url_kwarg, since DRF intends only for it to be used for .retrieve
        urn = request.query_params.get(self.lookup_url_kwarg)
        if not urn:
            raise ValidationError("Missing required ?urn parameter")
        self.kwargs[self.lookup_url_kwarg] = urn
        return mixins.RetrieveModelMixin.retrieve(self, request, *args, **kwargs)
