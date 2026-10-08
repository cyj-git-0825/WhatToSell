from sqlalchemy import func, select

from app.channels.registry import register
from app.config import Depth
from app.models import Channel, Comment, Search, SearchPost, SearchStatus
from app.pipeline.run import run_search
from tests.fakes import FakeAdapter


async def _new_search(session, keyword="camping chair", channels=("reddit", "tiktok"), depth=Depth.LIGHT):
    s = Search(keyword=keyword, depth=depth, channels=list(channels), progress={}, llm_models={})
    session.add(s)
    await session.commit()
    return s.id


async def _count(session, model, *where):
    return await session.scalar(select(func.count()).select_from(model).where(*where))


async def test_collects_all_channels(session):
    register(FakeAdapter(Channel.REDDIT))
    register(FakeAdapter(Channel.TIKTOK))
    sid = await _new_search(session)

    await run_search(sid)

    search = await session.get(Search, sid)
    assert search.status == SearchStatus.DONE
    assert search.finished_at is not None
    assert await _count(session, SearchPost, SearchPost.search_id == sid) == 6
    assert await _count(session, Comment) == 30
    stats = search.progress["collect"]
    assert stats["reddit"] == {"posts": 3, "comments": 15, "cached_posts": 0, "error": None}


async def test_depth_tier_caps_posts(session):
    register(FakeAdapter(Channel.REDDIT, n_posts=40, n_comments=150))
    sid = await _new_search(session, channels=["reddit"], depth=Depth.LIGHT)

    await run_search(sid)

    stats = (await session.get(Search, sid)).progress["collect"]["reddit"]
    assert stats["posts"] == 10  # light tier: 10 posts x 100 comments
    assert stats["comments"] == 1000


async def test_repeat_search_reuses_fresh_comments(session):
    adapter = FakeAdapter(Channel.REDDIT)
    register(adapter)
    await run_search(await _new_search(session, channels=["reddit"]))
    assert adapter.comment_fetches == 3

    sid2 = await _new_search(session, channels=["reddit"])
    await run_search(sid2)

    assert adapter.comment_fetches == 3  # nothing re-fetched
    stats = (await session.get(Search, sid2)).progress["collect"]["reddit"]
    assert stats["cached_posts"] == 3
    assert await _count(session, SearchPost, SearchPost.search_id == sid2) == 3
    assert await _count(session, Comment) == 15  # deduplicated


async def test_one_channel_failing_does_not_fail_search(session):
    register(FakeAdapter(Channel.REDDIT))
    register(FakeAdapter(Channel.TIKTOK, fail=True))
    sid = await _new_search(session)

    await run_search(sid)

    search = await session.get(Search, sid)
    assert search.status == SearchStatus.DONE
    assert search.progress["collect"]["tiktok"]["error"] == "tiktok blocked"
    assert search.progress["collect"]["reddit"]["posts"] == 3


async def test_all_channels_failing_fails_search(session):
    register(FakeAdapter(Channel.REDDIT, fail=True))
    sid = await _new_search(session, channels=["reddit", "tiktok"])  # tiktok not registered

    await run_search(sid)

    search = await session.get(Search, sid)
    assert search.status == SearchStatus.FAILED
    assert "all channels failed" in search.error
