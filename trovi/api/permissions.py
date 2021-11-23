from rest_framework import permissions, views
from rest_framework.request import Request

from trovi.models import Artifact


class SharedWithPermission(permissions.BasePermission):
    def has_object_permission(
        self, request: Request, view: views.View, obj: Artifact
    ) -> bool:
        if obj.visibility == Artifact.Visibility.PRIVATE:
            sharing_key = request.query_params.get("sharing_key")
            return sharing_key == obj.sharing_key
        else:
            # TODO only return true if user is object owner (requires auth)
            return True
