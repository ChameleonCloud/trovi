from drf_spectacular.openapi import AutoSchema
from rest_framework import serializers

from trovi.api.views import APIViewSet


class APIViewSetAutoSchema(AutoSchema):
    def get_response_serializers(self) -> serializers.Serializer:
        if isinstance(self.view, APIViewSet) and self.method.upper() in (
            "PATCH",
            "PUT",
        ):
            return self.view.serializer_class()
        return super(APIViewSetAutoSchema, self).get_response_serializers()
