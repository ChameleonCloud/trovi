from django.conf import settings
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
        required_scopes = self.action_scope_map.get(request.method)
        if required_scopes is None:
            raise KeyError(
                f"Required scopes not set for action {request.method} "
                f"({request.get_full_path()})"
            )
        if not token:
            return len(required_scopes) == 0
        else:
            return required_scopes.issubset(token.scope)


class ArtifactScopedPermission(BaseScopedPermission):
    """
    Determines if the user's authorization scope permits them to interact with the
    Artifact in the way they desire.

    TODO allow owners to specify writability for their Artifacts
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: Artifact
    ) -> bool:
        token = JWT.from_request(request)
        user = token.azp
        if not obj.authors.filter(email__iexact=user).exists():
            return not any(scope.is_write_scope() for scope in token.scope)
        return True


class ArtifactVisibilityPermission(permissions.BasePermission):
    """
    Determines if an Artifact is visible to the user
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: Artifact
    ) -> bool:
        if obj.visibility == Artifact.Visibility.PRIVATE:
            sharing_key = request.query_params.get("sharing_key")
            if sharing_key:
                return sharing_key == obj.sharing_key
            else:
                token = JWT.from_request(request)
                if not token:
                    return False
                user = token.azp
                # If the viewer is one of the authors, then they may access the Artifact
                return obj.authors.filter(email__iexact=user).exists()
        else:
            # If the Artifact is public, then everyone may view
            return True


class ArtifactVersionVisibilityPermission(ArtifactVisibilityPermission):
    """
    Determines if a user has permission to view an ArtifactVersion
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        return super(ArtifactVersionVisibilityPermission, self).has_object_permission(
            request, view, obj.artifact
        )


class ArtifactVersionScopedPermission(ArtifactScopedPermission):
    """
    Determines if the user's authorization scope permits them to interact with the
    ArtifactVersion in the way they desire.
    """

    def has_object_permission(
        self, request: Request, view: views.View, obj: ArtifactVersion
    ) -> bool:
        return super(ArtifactVersionScopedPermission, self).has_object_permission(
            request, view, obj.artifact
        )


class StorageVisibilityPermission(permissions.BasePermission):
    """
    Determines if a user is authenticated, which is the only requirement to upload to
    storage.

    TODO downloads can be performed regardless of permission. Users should only be
         able to download content linked to an artifact they can view
    """

    def has_permission(self, request: Request, view: views.View) -> bool:
        token = JWT.from_request(request)
        return token and token.iss == settings.TROVI_FQDN
