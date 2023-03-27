from drf_spectacular.openapi import AutoSchema
from rest_framework import serializers

from trovi.common.views import TroviAPIViewSet


class TroviAPIViewSetAutoSchema(AutoSchema):
    def get_response_serializers(self) -> serializers.Serializer:
        if isinstance(self.view, TroviAPIViewSet) and self.method.upper() in (
            "PATCH",
            "PUT",
        ):
            return self.view.serializer_class()
        return super(TroviAPIViewSetAutoSchema, self).get_response_serializers()


class ArtifactRoleViewSetAutoSchema(TroviAPIViewSetAutoSchema):
    method_mapping = AutoSchema.method_mapping | {"delete": "unassign"}


class StorageViewSetAutoSchema(TroviAPIViewSetAutoSchema):
    def _is_list_view(self, serializer=None):
        return False
