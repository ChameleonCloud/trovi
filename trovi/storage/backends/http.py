from __future__ import annotations

from datetime import datetime
from typing import Optional

from trovi.storage.backends.base import StorageBackend
from trovi.storage.links.http import HttpDownloadLink


class HttpBackend(StorageBackend):
    """
    A lightweight HTTP backend used for artifacts whose primary access
    method is an external HTTP content URL, which is the content ID.
    """

    def seekable(self) -> bool:
        return False

    def get_temporary_download_url(self) -> Optional[HttpDownloadLink]:
        return HttpDownloadLink(
            url=self.content_id, exp=datetime.max, headers={}, method="GET"
        )
