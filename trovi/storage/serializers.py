import hashlib
import hmac
import random
from datetime import datetime
from typing import Union
from uuid import uuid4

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from trovi.common.serializers import URNSerializerField
from trovi.models import ArtifactVersion
from trovi.storage.backends import get_backend
from trovi.storage.backends.base import StorageBackend
from trovi.storage.links.http import HttpDownloadLink
from trovi.urn import parse_contents_urn


class StorageContentsSerializer(serializers.Serializer):

    urn = URNSerializerField(required=True)

    def update(self, instance, validated_data):
        return NotImplementedError("Improper use of StorageContentsSerializer")

    def create(self, validated_data: dict) -> dict[str, str]:
        return validated_data


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Chameleon Swift",
            value={
                "contents": f"urn:trovi:contents:chameleon:{(example_uuid := uuid4())}",
                "access_methods": [
                    HttpDownloadLink(
                        exp=(example_exp := datetime(year=2049, month=7, day=6)),
                        url=f"https://example.com/swift/"
                        f"{example_uuid}"
                        f"?temp_url_sig={hmac.new(bytes([random.randint(0, 10)]), bytes([random.randint(0, 10)]), hashlib.sha1).hexdigest()}"
                        f"&temp_url_exp={example_exp.strftime(settings.DATETIME_FORMAT)}",
                        headers={},
                        method="GET",
                    ).to_json()
                ],
            },
            description="An archive stored in Chameleon's Swift object storage backend.",
            request_only=False,
            response_only=True,
        )
    ]
)
class StorageRequestSerializer(serializers.Serializer):

    contents = StorageContentsSerializer(read_only=True)
    access_methods = serializers.ListField(
        child=serializers.JSONField(), read_only=True, min_length=1
    )
    data_ = serializers.FileField(required=False, write_only=True, allow_null=True)

    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data: dict) -> StorageBackend:
        backend: StorageBackend = validated_data["backend"]
        # If the backend has already been uploaded, there is nothing to do.
        if backend.content_id:
            return backend

        file = validated_data["file"]
        with backend:
            backend.write(file.file.read())

        return backend

    def get_fields(self) -> dict[str, serializers.Field]:
        fields = super(StorageRequestSerializer, self).get_fields()
        data = fields.pop("data_", None)
        if data is not None:
            fields["data"] = data
        return fields

    def to_internal_value(self, data: dict) -> dict:
        file = data.get("file")
        # If the file returned is a StorageBackend, that means it was already streamed
        # into the storage backend, and there is no more work to do
        if isinstance(file, StorageBackend):
            data["backend"] = file
            return data

        # If we get another file type back, we have to figure out the backend
        if not isinstance(file, UploadedFile):
            raise ValidationError("No file uploaded.")
        request = self.context["request"]
        backend = get_backend(request.query_params.get("backend"), request.content_type)
        data["backend"] = backend

        return data

    def to_representation(
        self, instance: Union[StorageBackend, ArtifactVersion]
    ) -> dict:
        if isinstance(instance, StorageBackend):
            # StoreContents
            return {
                "contents": {"urn": instance.to_urn()},
                "access_methods": instance.get_links(),
            }
        elif isinstance(instance, ArtifactVersion):
            # RetrieveContents
            urn = instance.contents_urn
            urn_info = parse_contents_urn(urn)
            backend = get_backend(urn_info["provider"], version=instance, content_id=urn_info["id"])
            return {"contents": {"urn": urn}, "access_methods": backend.get_links()}
        else:
            raise ValueError(
                f"Received unexpected data in storage content request: {type(instance)}"
            )
