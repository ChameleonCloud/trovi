from collections import defaultdict
from typing import Hashable

from django.conf import settings
from rest_framework.exceptions import ValidationError

from trovi.models import ArtifactVersion, Artifact
from trovi.storage.backends.base import StorageBackend
from trovi.storage.backends.swift import SwiftBackend
from trovi.storage.backends.zenodo import ZenodoBackend

# Maps backend names to
artifact_locks = defaultdict(set)


def get_backend(
    name: str,
    content_type: str = None,
    content_id: Hashable = None,
    artifact: Artifact = None,
    version: ArtifactVersion = None,
) -> StorageBackend:
    """
    Retrieves a file descriptor to an artifact in remote storage. The UUID should
    be provided for all calls for existing artifacts. It should be excluded for
    new artifacts about to be written.
    """
    if not name:
        raise ValidationError("Missing required 'backend' query parameter.")
    if name == "chameleon":
        return SwiftBackend(
            name,
            content_type,
            keystone_endpoint=settings.CHAMELEON_KEYSTONE_ENDPOINT,
            username=settings.CHAMELEON_SWIFT_USERNAME,
            user_domain_name=settings.CHAMELEON_SWIFT_USER_DOMAIN_NAME,
            password=settings.CHAMELEON_SWIFT_PASSWORD,
            project_name=settings.CHAMELEON_SWIFT_PROJECT_NAME,
            project_domain_name=settings.CHAMELEON_SWIFT_PROJECT_DOMAIN_NAME,
            container=settings.CHAMELEON_SWIFT_CONTAINER,
            region_name=settings.CHAMELEON_SWIFT_REGION_NAME,
            content_id=content_id,
        )
    if name == "zenodo":
        if not version:
            # Create a dummy version so Zenodo has an artifact to access metadata from
            version = ArtifactVersion(
                artifact=artifact, contents_urn="urn:trovi:contents:chameleon:dummy"
            )
        return ZenodoBackend(
            name, version, content_type=content_type, content_id=content_id
        )
    else:
        raise ValidationError(f"Unknown storage backend: {name}")
