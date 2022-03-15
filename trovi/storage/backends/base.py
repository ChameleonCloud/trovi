import io
import logging
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
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
    # The size, in bytes, of the entire artifact
    # None means it hasn't been checked yet
    _size = None
    # The number of segments (fragments, chunks, etc.) that make up the artifact
    _written_segments = 0
    # Pointer to the next segment that will be written
    _next_segment = 0
    # The maximum number of segments an artifact can have
    MAX_SEGMENTS = (1 << 64) - 1

    # Maps content identifiers to locks. Contents should only be allowed to be
    # read or written by one handle at a time.
    # This variable should _exclusively_ be accessed statically.
    # TODO this is a memory leak
    content_locks = defaultdict(threading.Lock)

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
        return not self.closed

    @abstractmethod
    def update_size(self) -> int:
        """
        Fetches the size, in bytes, of the artifact in storage. If the artifact
        hasn't been stored yet, this should return 0.
        """

    def __len__(self) -> int:
        if self._size is None:
            self._size = self.update_size()
        return self._size

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
        if not self.content_id:
            self.content_id = self.generate_content_id()
        self.__class__.content_locks[self.content_id].acquire()

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
        except Exception as error:
            LOG.error(f"StorageBackend failed cleanup: {str(error)}")
        finally:
            self._closed = True
            self.__class__.content_locks[self.content_id].release()
            if error:
                raise error

    @abstractmethod
    def update_closed_status(self) -> bool:
        """
        Fetches whether the artifact in storage is closed. If the artifact hasn't been
        stored yet, this should return False
        """

    @property
    def closed(self) -> bool:
        if self._closed is None:
            self._closed = self.update_closed_status()
        return self._closed

    def __enter__(self) -> "StorageBackend":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @abstractmethod
    def write_segment(self, buffer: ReadableBuffer) -> int:
        """
        Writes a segment to the remote storage. Returns the number of bytes written.
        """

    def write(self, buffer: ReadableBuffer) -> int:
        if not self.writable():
            raise IOError(
                f"Attempted write to unwritable artifact content: {self.to_urn()}"
            )
        write_size = self.write_segment(buffer)
        if self._next_segment == self.MAX_SEGMENTS:
            raise ValueError(f"Wrote too many segments ({self.to_urn()})")
        self._next_segment += 1
        if self._size is None:
            self._size = 0
        self._size += write_size
        self._written_segments += 1
        return write_size

    def tell(self) -> int:
        return self._next_segment

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if not self.seekable():
            raise LookupError(f"Storage backend {self.name} is not seekable.")
        if whence == io.SEEK_SET:
            target = offset
        elif whence == io.SEEK_CUR:
            target = self._next_segment + offset
        elif whence == io.SEEK_END:
            target = len(self) + offset
        else:
            raise ValueError(f"Unknown 'whence' argument: {whence}")
        if target >= self.MAX_SEGMENTS or target < 0:
            raise ValueError(
                f"Tried to seek to invalid position {target} ({self.to_urn()})"
            )
        self._next_segment = target
        return self._next_segment

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
