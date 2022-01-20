from dataclasses import dataclass, field

from trovi.storage.links.base import ContentDownloadLink
from util.types import JSON


@dataclass(frozen=True)
class GitDownloadLink(ContentDownloadLink):
    """
    Represents a git remote repository
    """

    # Any environment variables relevant to source before git operations
    env: dict[str, str]
    protocol: str = field(init=False, default="git")

    def to_json(self) -> dict[str, JSON]:
        out = super(GitDownloadLink, self).to_json()
        out["remote"] = out.pop("url")
        out["env"] = self.env
        return out
