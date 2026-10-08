"""Orchestrates one search end to end. Later phases fill in the demand and supply steps."""

import logging
import uuid
from datetime import UTC, datetime

from app.db import SessionLocal
from app.models import Search, SearchStatus
from app.pipeline.collect import collect

log = logging.getLogger(__name__)


async def run_search(search_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        search = await session.get(Search, search_id)
        if search is None:
            log.error("search %s not found", search_id)
            return
        try:
            search.status = SearchStatus.COLLECTING
            await session.commit()
            await collect(session, search)

            # Phase 3: demand-side analysis (ANALYZING_DEMAND)
            # Phase 5: supply-side verification (CHECKING_SUPPLY)

            search.status = SearchStatus.DONE
        except Exception as e:
            await session.rollback()
            log.exception("search %s failed", search_id)
            search.status = SearchStatus.FAILED
            search.error = f"{type(e).__name__}: {e}"
        search.finished_at = datetime.now(UTC)
        await session.commit()
