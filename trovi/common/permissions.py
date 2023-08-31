import logging
from typing import Any, Optional, Type

from rest_framework import permissions, views, generics, status
from rest_framework.request import Request

from trovi.common.tokens import JWT
from trovi.models import Artifact, ArtifactVersion, ArtifactRole

LOG = logging.getLogger(__name__)


class TroviPermission(permissions.BasePermission):
    # This property is not required on BasePermission, but it's used
    # by the view which owns a Permission to decide the error message
    # in the response to the user.
    # The way that DRF AND/OR's Permissions together
    # ends up just... deleting the message. So, the message should only be set
    # just before returning False
    message: Optional[str] = None
    code: Optional[int] = None


class BaseScopePermission(TroviPermission):
    """
    Determines if the user has permission to execute their desired action
    """

    required_scopes: set[JWT.Scopes] = None

    def has_permission(self, request: Request, view: views.View) -> bool:
        token = JWT.from_request(request)
        if not token:
            return self.required_scopes == {JWT.Scopes.ARTIFACTS_READ}

        if self.required_scopes is None:
            raise KeyError(
                f"Required scopes not set for action {request.method} "
                f"({request.get_full_path()})"
            )

        return self.required_scopes.issubset(token.scope)

    @property
    def message(self):
        return f"Token does not have required scope: {' '.join(self.required_scopes)}"


class ArtifactReadScopePermission(BaseScopePermission):
    required_scopes = {JWT.Scopes.ARTIFACTS_READ}


class ArtifactWriteScopePermission(BaseScopePermission):
    required_scopes = {JWT.Scopes.ARTIFACTS_WRITE}


class ArtifactWriteMetricsScopePermission(BaseScopePermission):
    required_scopes = {JWT.Scopes.ARTIFACTS_WRITE_METRICS}


class ArtifactViewPermission(TroviPermission):
    """
    Determines if an Artifact is visible to the user
    """

    message = "User does not have permission to view this Artifact"

    def has_object_permission(
        self, request: Request, view: views.View, obj: Artifact
    ) -> bool:
        sharing_key = request.query_params.get("sharing_key")
        if sharing_key == obj.sharing_key:
            return True
        token = JWT.from_request(request)
        return obj.can_be_viewed_by(token)


class ArtifactEditPermission(TroviPermission):
    message = "User does not have permission to edit this Artifact"

    def has_object_permission(
        self, request: Request, view: views.View, obj: Artifact
    ) -> bool:
        token = JWT.from_request(request)
        return obj.can_be_edited_by(token)


class ArtifactAdminPermission(TroviPermission):
    """
    Checks if the user is an admin of the requested Artifact
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: Artifact
    ) -> bool:
        token = JWT.from_request(request)

        return token and obj.has_admin(token.to_urn())


class BaseParentArtifactPermission(TroviPermission):
    """
    Allows models which are children of Artifacts to check permissions based on their
    parent artifact
    """

    parent_permission: Type[TroviPermission] = TroviPermission

    def has_permission(self, request: Request, view: views.View) -> bool:
        artifact_uuid = view.kwargs.get("parent_lookup_artifact")
        if not artifact_uuid:
            raise ValueError(
                "child endpoint of /artifacts was called without a parent artifact. "
                "Routes are misconfigured."
            )
        artifact = generics.get_object_or_404(
            Artifact.objects.all(), uuid=artifact_uuid
        )
        return self.parent_permission().has_object_permission(request, view, artifact)

    @property
    def message(self) -> str:
        return self.parent_permission.message


class ParentArtifactViewPermission(BaseParentArtifactPermission):
    parent_permission = ArtifactViewPermission


class ParentArtifactAdminPermission(BaseParentArtifactPermission):
    parent_permission = ArtifactAdminPermission


class ParentArtifactEditPermission(BaseParentArtifactPermission):
    parent_permission = ArtifactEditPermission


class ArtifactRoleOwnerRolesPermission(TroviPermission):
    message = (
        "Artifact owners cannot have their roles revoked. "
        "The owner must be changed first."
    )

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactRole
    ) -> bool:
        return obj.user != obj.artifact.owner_urn


class ArtifactVersionDestroyDOIPermission(TroviPermission):
    message = "Artifact Versions with associated DOIs cannot be deleted!"

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        return not obj.has_doi()


class ArtifactVersionMetricsUpdatePermission(TroviPermission):
    """
    Determines if a USER has permission to increment artifact metrics.
    """

    message = "User is forbidden from incrementing metrics on this artifact"

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        """
        Confirms that the origin user has permission to update
        an artifact version's metrics
        """

        origin_jws = request.query_params.get("origin")
        if not origin_jws:
            self.message = "Updating metrics requires an origin token"
            self.code = status.HTTP_401_UNAUTHORIZED
            return False

        # Authentication of the origin user is performed here
        origin_token = JWT.from_jws(origin_jws)

        sharing_key = request.query_params.get("sharing_key")
        if sharing_key == obj.artifact.sharing_key:
            return True

        return obj.can_be_viewed_by(origin_token)


class RootStorageDownloadPermission(TroviPermission):
    message = "User is not permitted to download this content"

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        token = JWT.from_request(request)
        return obj.can_be_viewed_by(token)


class AuthenticatedWithTroviTokenPermission(TroviPermission):
    def has_permission(self, request: Request, view: views.View) -> bool:
        return JWT.from_request(request) is not None


class TroviAdminPermission(TroviPermission):
    """
    Checks if the user is an admin of the entire Trovi service
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: Any
    ) -> bool:
        return self.has_permission(request, view)

    def has_permission(self, request: Request, view: views.View) -> bool:
        token = JWT.from_request(request)
        return token and token.is_admin()
