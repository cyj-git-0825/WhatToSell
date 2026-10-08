import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.registry import available_channels
from app.db import get_session
from app.llm import LLMTask, model_for
from app.models import Post, Search, SearchPost
from app.schemas import PostOut, SearchCreate, SearchOut

router = APIRouter(prefix="/searches", tags=["searches"])


@router.post("", response_model=SearchOut, status_code=status.HTTP_202_ACCEPTED)
async def create_search(body: SearchCreate, request: Request, session: AsyncSession = Depends(get_session)):
    unavailable = [c for c in body.channels if c not in available_channels()]
    if unavailable:
        raise HTTPException(422, f"channels not available yet: {', '.join(unavailable)}")

    search = Search(
        keyword=body.keyword,
        depth=body.depth,
        channels=[c.value for c in body.channels],
        progress={},
        llm_models={t.value: model_for(t) for t in LLMTask},
    )
    session.add(search)
    await session.commit()
    await request.app.state.arq.enqueue_job("run_search_job", str(search.id))
    return search


@router.get("", response_model=list[SearchOut])
async def list_searches(limit: int = 50, session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(select(Search).order_by(Search.created_at.desc()).limit(min(limit, 200)))
    return rows.all()


@router.get("/{search_id}", response_model=SearchOut)
async def get_search(search_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(404, "search not found")
    return search


@router.get("/{search_id}/posts", response_model=list[PostOut])
async def list_search_posts(search_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(
        select(Post).join(SearchPost).where(SearchPost.search_id == search_id).order_by(SearchPost.rank)
    )
    return rows.all()
