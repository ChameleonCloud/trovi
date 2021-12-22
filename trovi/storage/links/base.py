from dataclasses import dataclass
from datetime import datetime

from util.types import JSON


@dataclass(frozen=True)
class ContentDownloadLink:
    """
    Represents a temporary content download link consumable by users
    """

    # The protocol over which to download the content
    protocol: str
    # The URL at which the content is located
    url: str
    # The expiration timestamp of this link,
    # either via the link itself or via access token
    exp: datetime

    def to_json(self) -> dict[str, JSON]:
        return {
            "protocol": self.protocol,
            "url": self.url,
            "exp": int(self.exp.timestamp()),
        }
