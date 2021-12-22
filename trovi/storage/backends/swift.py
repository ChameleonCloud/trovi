import hashlib
import hmac
import uuid
from datetime import datetime
from typing import Hashable, Any, Mapping, Optional

import keystoneauth1.exceptions
from django.conf import settings
from keystoneauth1.adapter import Adapter
from keystoneauth1.identity.v3 import Password
from keystoneauth1.session import Session
from rest_framework import status

from trovi.storage.backends.base import StorageBackend
from trovi.storage.links.http import HttpDownloadLink
from util.types import ReadableBuffer


class SwiftBackend(StorageBackend):
    """
    Implements storage backend for Swift

    TODO reaper which finds and deletes all dangling objects
    """

    MAX_SEGMENT_URL_DIGITS = 8
    MAX_SEGMENTS = 1000

    _keystone_adapter = None

    def __init__(
        self,
        name: str,
        content_type: str,
        content_id: Hashable = None,
        keystone_endpoint: str = None,
        username: str = None,
        user_domain_name: str = None,
        password: str = None,
        project_name: str = None,
        project_domain_name: str = None,
        container: str = None,
        *args,
        **kwargs,
    ):
        super(SwiftBackend, self).__init__(
            name, content_type, content_id=content_id, *args, **kwargs
        )
        self.keystone_endpoint = keystone_endpoint
        self.username = username
        self.user_domain_name = user_domain_name
        self.password = password
        self.project_name = project_name
        self.project_domain_name = project_domain_name
        self.container = container
        self.content_id = content_id
        self.adapter_kwargs = kwargs

        self.container_url = f"/{self.container}"

    @property
    def object_url(self) -> str:
        if not self.content_id:
            raise ValueError(f"Cannot make calls for unknown object.")
        return f"{self.container_url}/{self.content_id}"

    @property
    def segment_url(self) -> str:
        return (
            f"{self.object_url}/{str(self.tell()).zfill(self.MAX_SEGMENT_URL_DIGITS)}"
        )

    def get_object_metadata(self) -> Mapping[str, Any]:
        try:
            return self.keystone.head(self.object_url).headers
        except keystoneauth1.exceptions.NotFound:
            return {}

    def generate_content_id(self) -> Hashable:
        new_uuid = None
        while True:
            try:
                new_uuid = uuid.uuid4()
                self.keystone.head(f"{self.container_url}/{new_uuid}")
            except keystoneauth1.exceptions.NotFound:
                return new_uuid

    def update_size(self) -> int:
        if not self.content_id:
            return 0
        metadata = self.get_object_metadata()
        return metadata.get("Content-Length", 0)

    def update_closed_status(self) -> bool:
        metadata = self.get_object_metadata()
        return bool(metadata)

    def cleanup(self):
        # Upload the manifest which declares the Dynamic Large Object as complete
        # TODO on failure, delete unfinished content

        # We don't want to overwrite existing manifests
        if self.closed:
            return

        response = self.keystone.put(
            self.object_url,
            headers={
                "X-Object-Manifest": self.object_url,
                "content-type": self.content_type,
            },
            data="",
        )

        if response.status_code != status.HTTP_201_CREATED:
            raise IOError(f"Failed to create large object manifest for {self.to_urn()}")

    @property
    def keystone(self) -> Adapter:
        if not self._keystone_adapter:
            auth = Password(
                auth_url=self.keystone_endpoint,
                username=self.username,
                user_domain_name=self.user_domain_name,
                password=self.password,
                project_name=self.project_name,
                project_domain_name=self.project_domain_name,
            )
            sess = Session(auth)
            self._keystone_adapter = Adapter(
                session=sess,
                connect_retries=settings.STORAGE_BACKEND_AUTH_RETRY_ATTEMPTS,
                service_type="object-store",
                interface="public",
                **self.adapter_kwargs,
            )
        return self._keystone_adapter

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        if not self.content_id:
            return True
        else:
            return not self.closed

    def write_segment(self, buffer: ReadableBuffer) -> int:
        response = self.keystone.put(
            self.segment_url,
            headers={"content-type": "application/octet-stream"},
            data=buffer,
        )

        if response.status_code != status.HTTP_201_CREATED:
            raise IOError(
                f"Failed to upload segment {self.tell()} for content {self.to_urn()}"
            )

        return len(buffer)

    def get_temporary_download_url(self) -> Optional[HttpDownloadLink]:
        path = self.object_url
        endpoint = self.keystone.get_endpoint()
        account = endpoint[endpoint.index("/v1/") :]
        exp = int(
            datetime.utcnow().timestamp() + settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS
        )
        hmac_body = f"GET\n{exp}\n{account + path}"
        key = settings.CHAMELEON_SWIFT_TEMP_URL_KEY
        encoding = "utf-8"

        # TODO upgrade to SHA256 when it's supported
        signature = hmac.new(
            key.encode(encoding), hmac_body.encode(encoding), hashlib.sha1
        ).hexdigest()

        return HttpDownloadLink(
            url=f"{endpoint + path}?temp_url_sig={signature}&temp_url_expires={exp}",
            exp=datetime.fromtimestamp(exp),
            headers={},
            method="GET",
        )
