from requests.structures import CaseInsensitiveDict
from rest_framework import permissions, views
from rest_framework.request import Request

from trovi.common.tokens import JWT
from trovi.models import Artifact, ArtifactVersion


class BaseScopedPermission(permissions.BasePermission):
    """
    Determines if the user has permission to execute their desired action
    """

    # Maps actions to required authorization scopes
    action_scope_map = CaseInsensitiveDict(
        {
            "POST": {JWT.Scopes.ARTIFACTS_WRITE},
            "DELETE": {JWT.Scopes.ARTIFACTS_WRITE},
            "UPDATE": {JWT.Scopes.ARTIFACTS_WRITE, JWT.Scopes.ARTIFACTS_READ},
            "PATCH": {JWT.Scopes.ARTIFACTS_WRITE, JWT.Scopes.ARTIFACTS_READ},
            "GET": {JWT.Scopes.ARTIFACTS_READ},
        }
    )

    def has_permission(self, request: Request, view: views.View) -> bool:
        token = JWT.from_request(request)
        if token.is_admin():
            return True
        required_scopes = self.action_scope_map.get(request.method)
        if required_scopes is None:
            raise KeyError(
                f"Required scopes not set for action {request.method} "
                f"({request.get_full_path()})"
            )
        return required_scopes.issubset(token.scope)


class ArtifactScopedPermission(BaseScopedPermission):
    """
    Determines if the user's authorization scope permits them to interact with the
    Artifact in the way they desire.

    TODO allow owners to specify which users may write to their artifacts
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: Artifact
    ) -> bool:
        token = JWT.from_request(request)
        if not token:
            return False
        if token.is_admin():
            return True
        # If the authenticated user is not the artifact owner,
        # they may not write to the artifact
        if token.to_urn() != obj.owner_urn:
            return not any(scope.is_write_scope() for scope in token.scope)
        return True


class ArtifactVisibilityPermission(permissions.BasePermission):
    """
    Determines if an Artifact is visible to the user
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: Artifact
    ) -> bool:
        token = JWT.from_request(request)
        if not token:
            return False
        if token.is_admin() or obj.visibility == Artifact.Visibility.PUBLIC:
            return True
        sharing_key = request.query_params.get("sharing_key")
        if sharing_key:
            return sharing_key == obj.sharing_key
        else:
            # If the authenticated user owns the Artifact,
            # then they may access the Artifact
            return token.to_urn() == obj.owner_urn


class ArtifactVersionVisibilityPermission(ArtifactVisibilityPermission):
    """
    Determines if a user has permission to view an ArtifactVersion
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        artifact_visibility = ArtifactVisibilityPermission()
        return artifact_visibility.has_object_permission(request, view, obj.artifact)


class ArtifactVersionScopedPermission(ArtifactScopedPermission):
    """
    Determines if the user's authorization scope permits them to interact with the
    ArtifactVersion in the way they desire.
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        artifact_scope = ArtifactScopedPermission()
        return artifact_scope.has_object_permission(request, view, obj.artifact)


class BaseMetadataPermission(permissions.BasePermission):
    """
    Base permissions for viewing API metadata
    """

    def has_permission(self, request: Request, view: views.View) -> bool:
        if request.method.upper() == "GET":
            return True
        else:
            token = JWT.from_request(request)
            return token.is_admin()

class IsAuthenticatedWithTroviToken(permissions.BasePermission):
    def has_permission(self, request: Request, view: views.View) -> bool:
        return JWT.from_request(request) is not None
