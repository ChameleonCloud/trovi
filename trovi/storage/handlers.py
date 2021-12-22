import logging
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopFutureHandlers
from django.core.handlers.wsgi import WSGIRequest
from rest_framework.exceptions import ValidationError

from trovi.storage.backends import get_backend
from trovi.storage.backends.base import StorageBackend

LOG = logging.getLogger(__name__)


class StreamingFileUploadHandler(FileUploadHandler):
    """
    Handles streaming uploads to remote storage. Uploaded chunks are
    immediately forwarded without additional buffering.
    """
    storage_backend: StorageBackend = None
    supported_filetypes = {".tar", ".tar.gz"}

    def handle_raw_input(
        self,
        input_data: WSGIRequest,
        META,
        content_length: int,
        boundary,
        encoding=None,
    ):
        if (
            content_length > settings.FILE_UPLOAD_MAX_MEMORY_SIZE
            and not self.storage_backend
        ):
            self.storage_backend = get_backend(
                (backend_type := input_data.GET.get("backend")),
                input_data.headers.get("Content-Type"),
            )
            if not self.storage_backend.writable():
                raise ValidationError(f"Backend {backend_type} does not allow uploads.")
            self.storage_backend.open()

    def new_file(
        self,
        field_name: str,
        file_name: str,
        content_type: str,
        content_length: int,
        charset=None,
        content_type_extra=None,
    ):
        super(StreamingFileUploadHandler, self).new_file(
            field_name,
            file_name,
            content_type,
            content_length,
            charset=charset,
            content_type_extra=content_type_extra,
        )
        # If the filetype isn't supported, skip it
        # This is evaluated either by a supported file extension, or a content type
        # of application/tar(+gz, etc.)
        if (
            "".join(exts := Path(file_name).suffixes) not in self.supported_filetypes
            or content_type != f"application/{'+'.join(e[1:] for e in exts)}"
        ):
            return

        # If the upload is above a certain threshold, we use this handler to stream
        # the file to remote storage
        if (
            content_length > settings.FILE_UPLOAD_MAX_MEMORY_SIZE
            and not self.storage_backend
        ):
            self.storage_backend = get_backend(
                self.request.GET.get("backend"), content_type
            )
            self.storage_backend.open()
            raise StopFutureHandlers

    def receive_data_chunk(self, raw_data: bytes, start: int) -> Optional[bytes]:
        if self.storage_backend:
            self.storage_backend.write(raw_data)
        else:
            return raw_data

    def file_complete(self, file_size: int):
        if self.storage_backend and not self.storage_backend.closed:
            self.storage_backend.close()
        return self.storage_backend

    def upload_interrupted(self):
        if not self.storage_backend.closed:
            try:
                self.storage_backend.close()
            except Exception as e:
                LOG.error(
                    f"Failed to close remote storage {self.storage_backend.to_urn()}: "
                    f"{str(e)}"
                )
        raise IOError(f"Upload of {self.storage_backend.to_urn()} failed.")
