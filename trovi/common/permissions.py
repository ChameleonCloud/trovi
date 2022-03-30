from typing import Any

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
        required_scopes = self.action_scope_map.get(request.method)
        token = JWT.from_request(request)
        if not token:
            return required_scopes == {JWT.Scopes.ARTIFACTS_READ}
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
        if token:
            token_urn = token.to_urn()
        else:
            token_urn = None
        # If the authenticated user is not the artifact owner,
        # they may not write to the artifact
        if token_urn != obj.owner_urn:
            return not any(scope.is_write_scope() for scope in token.scope)
        return True


class ArtifactVisibilityPermission(permissions.BasePermission):
    """
    Determines if an Artifact is visible to the user
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: Artifact
    ) -> bool:
        is_public = obj.is_public()
        token = JWT.from_request(request)
        if not token or is_public:
            return is_public or obj.has_doi()
        sharing_key = request.query_params.get("sharing_key")
        if sharing_key:
            return sharing_key == obj.sharing_key
        else:
            # If the authenticated user owns the Artifact,
            # then they may access the Artifact
            return token.to_urn() == obj.owner_urn


class ArtifactVersionVisibilityPermission(permissions.BasePermission):
    """
    Determines if a user has permission to view an ArtifactVersion
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        artifact_visibility = ArtifactVisibilityPermission()
        return (
            artifact_visibility.has_object_permission(request, view, obj.artifact)
            or obj.has_doi()
        )


class ArtifactVersionScopedPermission(permissions.BasePermission):
    """
    Determines if the user's authorization scope permits them to interact with the
    ArtifactVersion in the way they desire.
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        if request.method.upper() == "DELETE" and obj.has_doi():
            return False
        artifact_scope = ArtifactScopedPermission()
        return artifact_scope.has_object_permission(request, view, obj.artifact)


class ArtifactVersionMetricsVisibilityPermission(permissions.BasePermission):
    """
    Determines if a USER has permission to increment artifact metrics.
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        """
        Confirms that the origin user has permission to update
        an artifact version's metrics
        """
        if obj.artifact.visibility == Artifact.Visibility.PUBLIC:
            return True
        sharing_key = request.query_params.get("sharing_key")
        if sharing_key and sharing_key == obj.artifact.sharing_key:
            return True
        origin_jws = request.query_params.get("origin")
        if not origin_jws:
            return False
        origin_token = JWT.from_jws(origin_jws)
        return origin_token.to_urn() == obj.artifact.owner_urn


class ArtifactVersionMetricsScopedPermission(permissions.BasePermission):
    """
    Determines if a SERVICE has permission to increment artifact metrics.
    """

    def has_permission(self, request: Request, view: views.View) -> bool:
        """
        The only users with permission to change metrics are admins. Only admins
        are allowed to obtain the trovi:admin or artifacts:write_metrics scopes
        """
        token = JWT.from_request(request)
        return JWT.Scopes.ARTIFACTS_WRITE_METRICS in token.scope


class ArtifactVersionOwnershipPermission(permissions.BasePermission):
    """
    Determines if a user is the owner of the parent artifact of an artifact version
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        token = JWT.from_request(request)
        return token.to_urn() == obj.artifact.owner_urn


class BaseMetadataPermission(permissions.BasePermission):
    """
    Base permissions for viewing API metadata
    """

    def has_permission(self, request: Request, view: views.View) -> bool:
        if request.method.upper() == "GET":
            # Listing metadata is public
            return True
        else:
            admin_permission = AdminPermission()
            return admin_permission.has_permission(request, view)


class IsAuthenticatedWithTroviToken(permissions.BasePermission):
    def has_permission(self, request: Request, view: views.View) -> bool:
        return JWT.from_request(request) is not None


class AdminPermission(permissions.BasePermission):
    def has_object_permission(
        self, request: Request, view: views.View, obj: Any
    ) -> bool:
        return self.has_permission(request, view)

    def has_permission(self, request: Request, view: views.View) -> bool:
        token = JWT.from_request(request)
        return token and token.is_admin()
