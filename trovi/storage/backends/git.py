from datetime import datetime
import logging
from typing import Hashable, Optional
from giturlparse import parse

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
        parts = content_id.rsplit("@")
        parse_result = parse(parts[0])
        if getattr(parse_result, "protocol", None) != "https":
            raise RuntimeError("Can't create a git backend from non HTTPS git remote")
        self.remote_url = parts[0]
        self.parsed_git_url = parse_result

        if len(parts) > 1:
            self.ref = parts[1]
        else:
            self.ref = "HEAD"

        self.content_id = content_id
        self.content_type = content_type

    def seekable(self) -> bool:
        return False

    def get_temporary_download_url(self) -> Optional[HttpDownloadLink]:
        if self.parsed_git_url.host == "github.com":
            url = f"https://github.com/{self.parsed_git_url.owner}/{self.parsed_git_url.repo}/archive/{self.ref}.zip"
        elif self.parsed_git_url.host == "gitlab.com":
            url = f"https://gitlab.com/{self.parsed_git_url.owner}/{self.parsed_git_url.repo}/-/archive/{self.ref}/{self.parsed_git_url.repo}-{self.ref}.zip"
        else:
            return None

        return HttpDownloadLink(
            url=url,
            exp=datetime.max,
            headers={},
            method="GET",
        )

    def get_git_remote(self) -> Optional[GitDownloadLink]:
        """
        Resolves a git remote repository for the content.

        This method returns None if it is not supported, and raises if the git
        remote cannot be resolved.
        """
        return GitDownloadLink(
            url=self.remote_url,
            ref=self.ref,
            exp=datetime.max,
            env={},
        )
