from django.shortcuts import get_object_or_404
from rest_framework import mixins
from rest_framework.parsers import JSONParser

from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.permissions import (
    ArtifactReadScopePermission,
    ArtifactWriteScopePermission,
    AuthenticatedWithTroviTokenPermission,
)
from trovi.common.tokens import JWT
from trovi.common.views import TroviAPIViewSet
from trovi.models import UserProfile
from trovi.users.serializers import UserProfileSerializer


class UserProfileView(
    TroviAPIViewSet, mixins.RetrieveModelMixin, mixins.UpdateModelMixin
):
    """
    Reads the requesting user's contact details and updates their email preferences
    """

    serializer_class = UserProfileSerializer
    patch_serializer_class = UserProfileSerializer
    parser_classes = [JSONParser]
    authentication_classes = [TroviTokenAuthentication]
    permission_classes = [AuthenticatedWithTroviTokenPermission]
    retrieve_permission_classes = [ArtifactReadScopePermission]
    update_permission_classes = [ArtifactWriteScopePermission]

    def get_object(self) -> UserProfile:
        return get_object_or_404(
            UserProfile, urn=JWT.from_request(self.request).to_urn()
        )
