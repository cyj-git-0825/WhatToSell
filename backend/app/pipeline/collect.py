"""Collection step: run every requested channel adapter and persist normalized posts/comments."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import ChannelAdapter, ChannelError, RawComment, RawPost
from app.channels.registry import get_adapter
from app.config import DEPTH_TIERS, get_settings
from app.models import Channel, Comment, Post, Search, SearchPost

log = logging.getLogger(__name__)


async def collect(session: AsyncSession, search: Search) -> dict[str, dict]:
    """Collect all channels for `search`. Returns per-channel stats; raises only if every channel failed."""
    tier = DEPTH_TIERS[search.depth]
    stats: dict[str, dict] = {}
    rank = 0
    linked: set[uuid.UUID] = set()

    for channel_name in search.channels:
        channel = Channel(channel_name)
        channel_stats = {"posts": 0, "comments": 0, "cached_posts": 0, "error": None}
        stats[channel] = channel_stats
        try:
            adapter = get_adapter(channel)
            async for raw_post in adapter.search_posts(search.keyword, tier.posts_per_channel):
                post_id, fresh = await _upsert_post(session, raw_post)
                if post_id in linked:  # adapter yielded a duplicate
                    continue
                linked.add(post_id)
                session.add(SearchPost(search_id=search.id, post_id=post_id, rank=rank))
                rank += 1
                channel_stats["posts"] += 1
                if fresh:
                    channel_stats["cached_posts"] += 1
                else:
                    channel_stats["comments"] += await _collect_comments(
                        session, adapter, raw_post, post_id, tier.comments_per_post
                    )
                await session.commit()
        except (ChannelError, LookupError) as e:
            await session.rollback()
            await session.refresh(search)  # rollback expired it; async can't lazy-load
            log.warning("channel %s failed for search %s: %s", channel, search.id, e)
            channel_stats["error"] = str(e)

        search.progress = {**search.progress, "collect": stats}
        await session.commit()

    if all(s["error"] for s in stats.values()):
        raise ChannelError("all channels failed: " + "; ".join(f"{c}: {s['error']}" for c, s in stats.items()))
    return stats


async def _upsert_post(session: AsyncSession, p: RawPost) -> tuple[uuid.UUID, bool]:
    """Insert or refresh a post. Returns (post_id, fresh) where fresh means its comments are
    recent enough (within raw_cache_hours) to reuse instead of re-fetching."""
    cutoff = datetime.now(UTC) - timedelta(hours=get_settings().raw_cache_hours)
    existing = await session.scalar(
        select(Post).where(Post.channel == p.channel, Post.external_id == p.external_id)
    )
    if existing is not None:
        has_comments = await session.scalar(
            select(func.count()).select_from(Comment).where(Comment.post_id == existing.id)
        )
        fresh = existing.fetched_at >= cutoff and bool(has_comments)
        for attr in ("url", "title", "body", "author", "community", "views", "likes", "comment_count", "raw"):
            setattr(existing, attr, getattr(p, attr))
        if not fresh:
            existing.fetched_at = datetime.now(UTC)
        return existing.id, fresh

    post = Post(
        channel=p.channel,
        external_id=p.external_id,
        url=p.url,
        title=p.title,
        body=p.body,
        author=p.author,
        community=p.community,
        views=p.views,
        likes=p.likes,
        comment_count=p.comment_count,
        published_at=p.published_at,
        raw=p.raw,
    )
    session.add(post)
    await session.flush()
    return post.id, False


async def _collect_comments(
    session: AsyncSession, adapter: ChannelAdapter, post: RawPost, post_id: uuid.UUID, limit: int
) -> int:
    n = 0
    async for c in adapter.fetch_comments(post, limit):
        await session.execute(_comment_upsert(post_id, c))
        n += 1
    return n


def _comment_upsert(post_id: uuid.UUID, c: RawComment):
    stmt = insert(Comment).values(
        id=uuid.uuid4(),
        post_id=post_id,
        external_id=c.external_id,
        parent_external_id=c.parent_external_id,
        text=c.text,
        author=c.author,
        likes=c.likes,
        published_at=c.published_at,
    )
    return stmt.on_conflict_do_update(
        index_elements=[Comment.post_id, Comment.external_id],
        set_={"likes": stmt.excluded.likes, "text": stmt.excluded.text, "fetched_at": func.now()},
    )
