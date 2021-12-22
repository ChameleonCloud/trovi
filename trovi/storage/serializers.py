from typing import Union

from django.core.files.uploadedfile import UploadedFile
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from trovi.models import ArtifactVersion
from trovi.storage.backends import get_backend
from trovi.storage.backends.base import StorageBackend


class StorageRequestSerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data: dict) -> StorageBackend:
        backend: StorageBackend = validated_data["backend"]
        # If the backend has already been uploaded, there is nothing to do.
        if backend.content_id:
            return backend

        file = validated_data["file"]
        with backend:
            backend.write(file)

        return backend

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
            return {"contents": {"urn": instance.to_urn()}}
        elif isinstance(instance, ArtifactVersion):
            # RetrieveContents
            urn = instance.contents_urn
            backend = get_backend((fields := urn.split(":"))[-2], content_id=fields[-1])
            return {"contents": {"urn": urn}, "access_methods": backend.get_links()}
        else:
            raise ValueError(
                f"Received unexpected data in storage content request: {type(instance)}"
            )
