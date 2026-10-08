import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Depth
from app.models import Channel, SearchStatus

V1_CHANNELS = [Channel.REDDIT, Channel.TIKTOK]


class SearchCreate(BaseModel):
    keyword: str = Field(min_length=2, max_length=200)
    depth: Depth = Depth.STANDARD
    channels: list[Channel] = Field(default_factory=lambda: list(V1_CHANNELS), min_length=1)

    @field_validator("keyword")
    @classmethod
    def _strip(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("channels")
    @classmethod
    def _dedupe(cls, v: list[Channel]) -> list[Channel]:
        return list(dict.fromkeys(v))


class SearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    keyword: str
    depth: Depth
    channels: list[Channel]
    status: SearchStatus
    progress: dict[str, Any]
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: Channel
    url: str
    title: str
    author: str | None
    community: str | None
    views: int | None
    likes: int | None
    comment_count: int | None
    published_at: datetime | None
