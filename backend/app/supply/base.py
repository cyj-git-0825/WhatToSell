"""Supply-side adapter contract: one per marketplace (Amazon, TikTok Shop, Temu, 1688, ...)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from app.models import SupplyMethod, SupplyPlatform


@dataclass
class Listing:
    title: str
    url: str
    price: Decimal | None = None
    currency: str = "USD"
    rating: float | None = None
    review_count: int | None = None
    monthly_sales: int | None = None
    top_complaints: list[str] = field(default_factory=list)


@dataclass
class SupplyResult:
    platform: SupplyPlatform
    method: SupplyMethod
    query: str
    listings: list[Listing]
    notes: str = ""
    # True when the numbers are estimates a seller should confirm by hand (e.g. 1688 in v1).
    needs_manual_review: bool = False


class SupplyAdapter(ABC):
    platform: SupplyPlatform

    @abstractmethod
    async def check(self, query: str, limit: int = 10) -> SupplyResult:
        """Look up existing listings for a product query on this platform."""
