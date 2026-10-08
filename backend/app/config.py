from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://wts:wts@localhost:55432/wts"
    redis_url: str = "redis://localhost:6380/0"

    llm_model_cluster_naming: str = "anthropic/claude-sonnet-5-5"
    llm_model_opportunity: str = "anthropic/claude-opus-5-5"
    llm_model_verdict: str = "anthropic/claude-opus-5-5"

    # Reuse already-fetched raw data for the same keyword within this window.
    raw_cache_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()


class Depth(StrEnum):
    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass(frozen=True)
class DepthTier:
    posts_per_channel: int
    comments_per_post: int
    credits: int


DEPTH_TIERS: dict[Depth, DepthTier] = {
    Depth.LIGHT: DepthTier(posts_per_channel=10, comments_per_post=100, credits=1),
    Depth.STANDARD: DepthTier(posts_per_channel=20, comments_per_post=200, credits=3),
    Depth.DEEP: DepthTier(posts_per_channel=50, comments_per_post=500, credits=8),
}
