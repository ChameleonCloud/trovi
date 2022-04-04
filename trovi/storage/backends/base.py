from __future__ import annotations

import io
import logging
from abc import ABC, abstractmethod
from typing import Hashable, Optional

from trovi.storage.links.git import GitDownloadLink
from trovi.storage.links.http import HttpDownloadLink
from util.types import ReadableBuffer, JSON

LOG = logging.getLogger(__name__)


class StorageBackend(io.BufferedIOBase, ABC):
    """
    Represents the base storage file streaming object.

    Writes should be performed only on non-closed objects, and only on new segments
    i.e. no data should ever be _overwritten_. Any artifact can be deleted, and any
    artifact can be read/seeked-to from any segment.

    StorageBackends should always be used as context managers, as it is the only way
    to guarantee that their locks will be released if any exceptions are thrown.
    """

    # Boolean flag to prevent redundant network round trips for closed artifacts
    # None means it hasn't been checked yet.
    _closed = None

    bytes_read = 0

    def __init__(
        self,
        name: str,
        content_type: str,
        content_id: Hashable = None,
        *args,
        **kwargs,
    ):
        """
        name is the name of the backend itself, and should be constant across all
        backends of the same origin.

        content_id is the ID of the contents known by the backend service (should be
        a UUID)
        """
        self.name = name
        self.content_id = content_id
        self.content_type = content_type
        self.buffer = bytes()

    def to_urn(self) -> str:
        """
        Returns a URN representation of the online file, e.g.
        contents:chameleon:108beeac-564f-4030-b126-ec4d903e680e

        If the file is not online, raises ``FileNotFoundError``
        """
        if not self.content_id:
            raise FileNotFoundError
        return f"urn:trovi:contents:{self.name}:{self.content_id}"

    def writable(self) -> bool:
        """
        Storage backends are, by default, not writeable.

        This method should describe whether the content is "generally" writeable.
        It should not describe if the exact state of the content is writeable.
        """
        return False

    def readable(self) -> bool:
        return not self.closed and self.bytes_read < len(self.buffer)

    @abstractmethod
    def update_length(self) -> int:
        """
        Fetches the size, in bytes, of the artifact in storage. If the artifact
        hasn't been stored yet, this should return 0.
        """

    def __len__(self) -> int:
        if not self.buffer:
            return self.update_length()
        return len(self.buffer)

    def __bool__(self) -> bool:
        return True

    @abstractmethod
    def generate_content_id(self) -> Hashable:
        """
        Generates a new content identifier, which should be guaranteed unique.

        Even though the odds of UUID collision are astronomically low, it is better
        to be safe than sorry.
        """

    def open(self):
        """
        Performs setup and acquires a lock for the content identifier
        """
        if self.content_id:
            self.download()
        else:
            self.content_id = self.generate_content_id()

    @abstractmethod
    def cleanup(self):
        """
        Performs cleanup operations during close.
        """

    def close(self):
        # TODO parse file to confirm it is actually tar+gz
        if self.closed:
            raise RuntimeError(
                "Tried to close a StorageBackend which was already closed."
            )
        error = None
        try:
            self.cleanup()
        except Exception as e:
            LOG.error(f"StorageBackend failed cleanup: {str(error)}")
            error = e
        finally:
            self._closed = True
            if error:
                raise error

        if self.buffer:
            self.upload()

    @abstractmethod
    def update_closed_status(self) -> bool:
        """
        Fetches whether the artifact in storage is closed. If the artifact hasn't been
        stored yet, this should return False
        """

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> "StorageBackend":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @abstractmethod
    def download(self):
        """
        Downloads remote bytes into local buffer
        """

    @abstractmethod
    def upload(self):
        """
        Uploads local buffer to remote storage
        """

    def read(self, __size: int | None = ...) -> bytes:
        if not self.buffer:
            self.download()
        chunk = self.buffer[self.bytes_read : __size]
        self.bytes_read = min(len(self.buffer), self.bytes_read + __size)
        return chunk

    def write(self, buffer: ReadableBuffer) -> int:
        if not self.writable():
            raise IOError(
                f"Attempted write to unwritable artifact content: {self.to_urn()}"
            )
        self.buffer += buffer
        return len(buffer)

    def get_links(self) -> list[dict[str, JSON]]:
        """
        Creates a list of access link metadata for all possible link methods
        """
        links = []
        temp_url = self.get_temporary_download_url()
        if temp_url:
            links.append(temp_url.to_json())
        git_remote = self.get_git_remote()
        if git_remote:
            links.append(git_remote.to_json())

        if not links:
            raise AttributeError(f"Storage backend {self.name} could not generate ")

        return links

    def get_temporary_download_url(self) -> Optional[HttpDownloadLink]:
        """
        Creates a temporary access url to download content

        This method returns None if it is not supported, and raises if
        URL generation fails.
        """
        return None

    def get_git_remote(self) -> Optional[GitDownloadLink]:
        """
        Resolves a git remote repository for the content.

        This method returns None if it is not supported, and raises if the git
        remote cannot be resolved.
        """
        return None
