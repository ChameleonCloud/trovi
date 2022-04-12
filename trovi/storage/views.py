from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    extend_schema_view,
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
)
from rest_framework import viewsets, mixins
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FileUploadParser
from rest_framework.request import Request
from rest_framework.response import Response

from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.permissions import BaseStoragePermission, AdminPermission
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
class StorageViewSet(
    viewsets.GenericViewSet, mixins.CreateModelMixin, mixins.ListModelMixin
):
    """
    Implements all endpoints at /contents

    StoreContents: (self.create)
        POST /contents?backend=<repository>

        Upload a tarfile to store as contents for an ArtifactVersion.

        Required scopes: artifact:write

        Request body: A tarfile, which can optionally be gzip-compressed.
                      Bzip2 or other compression algorithms that do not
                      support streaming are not accepted. The "target" query parameter
                      refers to the repository in which the file will be stored.
                      If the repository does not accept uploads,
                      a 400 error will be issued.

        Response: 201 Created
        Example response body:
        {
          "contents": {
            "urn": "contents:chameleon:108beeac-564f-4030-b126-ec4d903e680e"
          }
        }

    RetrieveContents: (self.retrieve)
        TODO fetch via version endpoint not implemented yet
        GET /artifacts/<uuid>/versions/<version_slug>/contents[?sharing_key=<key>]
        GET /contents?urn=<urn>[&sharing_key=<key>]
        Retrieve a given ArtifactVersion's contents. If the contents URN is known,
        it can be provided directly via /contents; otherwise, it can be retrieved
        via the ArtifactVersion. If the contents are linked to a private Artifact,
        the sharing key can be provided to access the contents.

        Response: 200 OK
        Example response body:
        {
          "contents": {
            "urn": "contents:gitlab:user/repo@d34db3f"
          },
          "access_methods": [
            {
                "protocol": "http",
                "exp": 1633730971,
                "url": "https://api.trovi.example/contents/stream?urn=contents:"
                       "gitlab:user%2Frepo@d34db3f",
                "headers": {"Authorization": "Bearer 10298fasdf…"},
                "method": "get"
            },
            {
                "protocol": "git",
                "exp": 1633730971,
                "remote": "trovi://contents:gitlab:user/repo@d34db3f",
                "env": {"TROVI_GIT_TOKEN": "10298fasdf…"}
            }
          ]
        }

        The response must contain at least one access_method. Each access method is
        associated with a protocol; if contents are available via multiple protocols,
        one access method per protocol is returned. Each access method additionally
        contains an "exp" field, which is a Unix timestamp representing when the
        access will expire.

        Per-protocol response fields include:
            http
                url: the URL of the resource
                headers: a map of HTTP headers to send when making the request
                method: the request method
            git
                remote: the full Git remote location
                env: environment variables to source before performing the
                fetch/checkout, typically for authentication purposes.
    """

    queryset = ArtifactVersion.objects.all()
    parser_classes = [FileUploadParser]
    authentication_classes = [TroviTokenAuthentication]
    permission_classes = [BaseStoragePermission | AdminPermission]
    serializer_class = StorageRequestSerializer
    lookup_field = "contents_urn__iexact"
    lookup_url_kwarg = "urn"

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
