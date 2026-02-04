from __future__ import annotations

from datetime import datetime
import logging
from typing import Hashable, Optional

from trovi.storage.backends.base import StorageBackend
from trovi.storage.links.http import HttpDownloadLink
from trovi.models import ArtifactVersionSetup

LOG = logging.getLogger(__name__)


class HttpBackend(StorageBackend):
    """
    A lightweight HTTP backend used for artifacts whose primary access
    method is an external HTTP content URL.
    """

    def __init__(
        self,
        name: str,
        content_type: str,
        content_id: Hashable = None,
        version=None,
    ):
        super().__init__(name, content_type, content_id=content_id)
        self.version = version

    def seekable(self) -> bool:
        return False

    def get_temporary_download_url(self) -> Optional[HttpDownloadLink]:
        """
        Expose the JupyterHub (or other) URL saved in the ArtifactVersionSetup
        for SOURCE_CODE as the HTTP access method.
        """
        try:
            setup = None
            if self.version:
                setup = ArtifactVersionSetup.objects.filter(
                    artifact_version=self.version,
                    type=ArtifactVersionSetup.ArtifactVersionSetupType.SOURCE_CODE,
                ).first()
            else:
                setup = (
                    ArtifactVersionSetup.objects.filter(
                        artifact_version__artifact__uuid=self.content_id,
                        type=ArtifactVersionSetup.ArtifactVersionSetupType.SOURCE_CODE,
                    )
                    .order_by("-artifact_version__created_at")
                    .first()
                )

            if not setup:
                return None

            url = setup.arguments.get("url")
            if not url:
                return None

            return HttpDownloadLink(url=url, exp=datetime.max, headers={}, method="GET")
        except Exception:
            LOG.exception("Failed to build HttpBackend temporary URL")
            return None

    def get_git_remote(self):
        return None
