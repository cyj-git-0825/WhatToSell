"""ORM models. Mirrors the data model section of docs/DESIGN.md."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import Depth
from app.db import Base


def _enum(cls: type[StrEnum]) -> Enum:
    # Store as VARCHAR so adding a member never needs an ALTER TYPE migration.
    return Enum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class Channel(StrEnum):
    REDDIT = "reddit"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"


class SearchStatus(StrEnum):
    QUEUED = "queued"
    COLLECTING = "collecting"
    ANALYZING_DEMAND = "analyzing_demand"
    CHECKING_SUPPLY = "checking_supply"
    DONE = "done"
    FAILED = "failed"


class InsightCategory(StrEnum):
    COMPLAINT = "complaint"  # 他们在骂什么
    DELIGHT = "delight"  # 被什么打动
    QUESTION = "question"  # 在问什么
    WORKAROUND = "workaround"  # 在凑合什么


class SupplyPlatform(StrEnum):
    AMAZON = "amazon"
    TIKTOK_SHOP = "tiktok_shop"
    TEMU = "temu"
    ALIEXPRESS = "aliexpress"
    ALIBABA_1688 = "1688"


class SupplyMethod(StrEnum):
    API = "api"
    AGENT_SEARCH = "agent_search"
    ESTIMATE = "estimate"


class VerdictOutcome(StrEnum):
    NOBODY = "nobody"  # 没人做
    DONE_POORLY = "done_poorly"  # 有人做但做得烂
    DONE_WELL = "done_well"  # 有人做且做得好


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    credits: Mapped[int] = mapped_column(default=0)


class Search(TimestampMixin, Base):
    __tablename__ = "searches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Nullable until accounts land in phase 6.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    keyword: Mapped[str] = mapped_column(String(200), index=True)
    depth: Mapped[Depth] = mapped_column(_enum(Depth))
    channels: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[SearchStatus] = mapped_column(_enum(SearchStatus), default=SearchStatus.QUEUED)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    llm_models: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    credits_charged: Mapped[int] = mapped_column(default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    search_posts: Mapped[list["SearchPost"]] = relationship(back_populates="search")


class Post(Base):
    """A post or video, deduplicated globally so repeat searches reuse it."""

    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("channel", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel: Mapped[Channel] = mapped_column(_enum(Channel))
    external_id: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str | None] = mapped_column(String(200))
    community: Mapped[str | None] = mapped_column(String(200))  # subreddit, hashtag, ...
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comment_count: Mapped[int | None] = mapped_column(BigInteger)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    comments: Mapped[list["Comment"]] = relationship(back_populates="post")


class SearchPost(Base):
    __tablename__ = "search_posts"

    search_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("searches.id", ondelete="CASCADE"), primary_key=True)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    rank: Mapped[int]

    search: Mapped[Search] = relationship(back_populates="search_posts")
    post: Mapped[Post] = relationship()


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (UniqueConstraint("post_id", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(64))
    parent_external_id: Mapped[str | None] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(200))
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    post: Mapped[Post] = relationship(back_populates="comments")


class DemandReport(TimestampMixin, Base):
    """post_id is null for the keyword-level aggregate; set for a per-post drill-down."""

    __tablename__ = "demand_reports"
    # NULLS NOT DISTINCT so a search can have only one aggregate (post_id null) report.
    __table_args__ = (UniqueConstraint("search_id", "post_id", postgresql_nulls_not_distinct=True),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    search_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("searches.id", ondelete="CASCADE"), index=True)
    post_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    summary: Mapped[str] = mapped_column(Text, default="")
    # Sampling disclosure, e.g. "top comments by platform ranking, not a random sample".
    sample_note: Mapped[str] = mapped_column(Text, default="")
    comments_analyzed: Mapped[int] = mapped_column(default=0)

    clusters: Mapped[list["InsightCluster"]] = relationship(back_populates="report")


class InsightCluster(Base):
    __tablename__ = "insight_clusters"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("demand_reports.id", ondelete="CASCADE"), index=True)
    category: Mapped[InsightCategory] = mapped_column(_enum(InsightCategory))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    comment_count: Mapped[int]
    weighted_score: Mapped[float]  # like-weighted heat
    # [{comment_id, text, likes, translation}]
    quotes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    rank: Mapped[int]

    report: Mapped[DemandReport] = relationship(back_populates="clusters")


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    search_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("searches.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text)
    hypothesis: Mapped[str] = mapped_column(Text)
    evidence_cluster_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    rank: Mapped[int]

    supply_checks: Mapped[list["SupplyCheck"]] = relationship(back_populates="opportunity")
    verdict: Mapped["Verdict | None"] = relationship(back_populates="opportunity")


class SupplyCheck(TimestampMixin, Base):
    __tablename__ = "supply_checks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    platform: Mapped[SupplyPlatform] = mapped_column(_enum(SupplyPlatform))
    method: Mapped[SupplyMethod] = mapped_column(_enum(SupplyMethod))
    query: Mapped[str] = mapped_column(Text)
    # [{title, url, price, rating, review_count, sales, top_complaints}]
    listings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    price_low: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_high: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    notes: Mapped[str] = mapped_column(Text, default="")
    needs_manual_review: Mapped[bool] = mapped_column(default=False)

    opportunity: Mapped[Opportunity] = relationship(back_populates="supply_checks")


class Verdict(TimestampMixin, Base):
    __tablename__ = "verdicts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True
    )
    outcome: Mapped[VerdictOutcome] = mapped_column(_enum(VerdictOutcome))
    reasoning: Mapped[str] = mapped_column(Text)
    est_gross_margin: Mapped[float | None]  # 0–1, from sourcing price vs. retail price
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    opportunity: Mapped[Opportunity] = relationship(back_populates="verdict")
