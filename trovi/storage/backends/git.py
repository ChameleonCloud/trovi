from datetime import datetime
from django.conf import settings
import logging
from typing import Hashable, Optional
from urllib.parse import urljoin

from trovi.storage.backends.base import StorageBackend
from trovi.storage.links.http import HttpDownloadLink
from trovi.storage.links.git import GitDownloadLink

LOG = logging.getLogger(__name__)

class GitBackend(StorageBackend):
    """
    Implements storage backend for Git
    """
    def __init__(
        self,
        name: str,
        content_type: str,
        content_id: Hashable = None,
    ):
        self.name = name
        parts = content_id.split("@")
        self.remote_url = parts[0]
        if len(parts) > 1:
            self.ref = parts[1]
        else:
            self.ref = "HEAD"

        self.content_id = content_id
        self.content_type = content_type

    def seekable(self) -> bool:
        return False

    def get_temporary_download_url(self) -> Optional[HttpDownloadLink]:
        exp = int(
            datetime.utcnow().timestamp() + settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS
        )

        # Temporary download url for github only, and only with HTTP remote
        if "github.com" not in self.remote_url or not self.remote_url.startswith("http"):
            return None

        github_base_url = self.remote_url
        if github_base_url.endswith(".git"):
            github_base_url = github_base_url[:-4]
        if not github_base_url.endswith("/"):
            github_base_url += "/"
        url = urljoin(github_base_url, f"archive/{self.ref}.zip")

        return HttpDownloadLink(
            url=url,
            exp=datetime.fromtimestamp(exp),
            headers={},
            method="GET",
        )

    def get_git_remote(self) -> Optional[GitDownloadLink]:
        """
        Resolves a git remote repository for the content.

        This method returns None if it is not supported, and raises if the git
        remote cannot be resolved.
        """
        exp = int(
            datetime.utcnow().timestamp() + settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS
        )

        return GitDownloadLink(
            url=self.remote_url,
            ref=self.ref,
            exp=datetime.fromtimestamp(exp),
            env={},
        )
