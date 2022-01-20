from dataclasses import dataclass, field

from trovi.storage.links.base import ContentDownloadLink
from util.types import JSON


@dataclass(frozen=True)
class HttpDownloadLink(ContentDownloadLink):
    """
    Represents a standard HTTP download link
    """

    # Additional HTTP headers that must be passed in requests to this link
    headers: dict[str, str]
    # HTTP method to use for requests to this link
    method: str
    protocol: str = field(init=False, default="http")

    def to_json(self) -> dict[str, JSON]:
        return super(HttpDownloadLink, self).to_json() | {
            "headers": self.headers,
            "method": self.method,
        }
