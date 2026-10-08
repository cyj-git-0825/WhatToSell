"""Channel adapter contract.

Every source (Reddit, TikTok, later Instagram or a paid data API) is converted into
these normalized records. Analysis code only ever sees RawPost / RawComment, so a
scraper can be swapped for a paid API without touching anything downstream.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models import Channel


@dataclass
class RawComment:
    external_id: str
    text: str
    likes: int = 0
    author: str | None = None
    published_at: datetime | None = None
    parent_external_id: str | None = None  # set for replies


@dataclass
class RawPost:
    channel: Channel
    external_id: str
    url: str
    title: str = ""
    body: str = ""
    author: str | None = None
    community: str | None = None
    views: int | None = None
    likes: int | None = None
    comment_count: int | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class ChannelError(Exception):
    """Raised when a channel is unreachable or blocked; the search continues with other channels."""


class ChannelAdapter(ABC):
    channel: Channel

    @abstractmethod
    def search_posts(self, keyword: str, limit: int) -> AsyncIterator[RawPost]:
        """Yield up to `limit` posts relevant to `keyword`, most relevant first."""

    @abstractmethod
    def fetch_comments(self, post: RawPost, limit: int) -> AsyncIterator[RawComment]:
        """Yield up to `limit` comments for `post`, in the platform's own ranking order."""

    async def healthcheck(self) -> bool:
        """Cheap probe used by the channel health endpoint. Override when a real probe exists."""
        return True

    # Sampling disclosure shown on every report built from this channel.
    sample_note: str = ""
