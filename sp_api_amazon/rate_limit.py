"""In-process token-bucket rate limiting, keyed per SP-API operation.

SP-API enforces a separate rate + burst for each operation and returns the
current rate in the ``x-amzn-RateLimit-Limit`` response header. We model each
operation as a token bucket:

  * ``rate``     - tokens refilled per second (the steady-state request rate).
  * ``capacity`` - max tokens (the burst allowance).

This keeps a single process well-behaved without external infrastructure. The
interface is deliberately small so a Redis-backed distributed limiter can be
dropped in later (see RateLimiter) when more than one process makes calls.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class RateConfig:
    rate: float       # tokens per second
    capacity: float   # burst size


# Conservative published defaults for the operations this package implements.
# These are starting points; the limiter self-corrects from response headers.
DEFAULT_RATES: dict[str, RateConfig] = {
    # Sellers
    "getMarketplaceParticipations": RateConfig(0.016, 15),
    # Orders
    "getOrders": RateConfig(0.0167, 20),
    "getOrder": RateConfig(0.0167, 20),
    "getOrderItems": RateConfig(0.5, 30),
    "getOrderBuyerInfo": RateConfig(0.0167, 20),
    "getOrderAddress": RateConfig(0.0167, 20),
    "updateShipmentStatus": RateConfig(0.0167, 15),
    # FBA Inventory
    "getInventorySummaries": RateConfig(2.0, 2),
    # Catalog Items
    "searchCatalogItems": RateConfig(2.0, 2),
    "getCatalogItem": RateConfig(2.0, 2),
    # Listings Items
    "getListingsItem": RateConfig(5.0, 10),
    "putListingsItem": RateConfig(5.0, 10),
    "patchListingsItem": RateConfig(5.0, 10),
    "deleteListingsItem": RateConfig(5.0, 10),
    # Listings Restrictions
    "getListingsRestrictions": RateConfig(5.0, 10),
    # Product Pricing
    "getPricing": RateConfig(0.5, 1),
    "getCompetitivePricing": RateConfig(0.5, 1),
    "getItemOffers": RateConfig(0.5, 1),
    "getListingOffers": RateConfig(0.5, 1),
    # Product Fees
    "getMyFeesEstimateForASIN": RateConfig(1.0, 2),
    # Product Type Definitions
    "searchDefinitionsProductTypes": RateConfig(5.0, 10),
    "getDefinitionsProductType": RateConfig(5.0, 10),
    # Reports
    "createReport": RateConfig(0.0167, 15),
    "getReport": RateConfig(2.0, 15),
    "getReports": RateConfig(0.0222, 10),
    "getReportDocument": RateConfig(0.0167, 15),
    # Feeds
    "createFeed": RateConfig(0.0083, 15),
    "getFeed": RateConfig(2.0, 15),
    "createFeedDocument": RateConfig(0.0083, 15),
    "getFeedDocument": RateConfig(0.0167, 15),
    # Sales
    "getOrderMetrics": RateConfig(0.5, 1),
    # Tokens
    "createRestrictedDataToken": RateConfig(1.0, 10),
}

# Fallback for any operation not in the table above.
_FALLBACK = RateConfig(rate=1.0, capacity=5)


class _Bucket:
    """A single thread-safe token bucket."""

    def __init__(self, cfg: RateConfig) -> None:
        self.rate = cfg.rate
        self.capacity = cfg.capacity
        self._tokens = cfg.capacity
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._updated = now

    def acquire(self, *, block: bool = True, max_wait: float | None = None) -> bool:
        """Take one token. If ``block`` is True, sleep until one is available
        (up to ``max_wait`` seconds). Returns True if a token was acquired."""
        deadline = None if max_wait is None else time.monotonic() + max_wait
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return True
                if not block:
                    return False
                # Seconds until the next whole token is available.
                needed = (1 - self._tokens) / self.rate if self.rate > 0 else 1.0
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                needed = min(needed, remaining)
            time.sleep(max(needed, 0.01))

    def update_rate(self, rate: float) -> None:
        with self._lock:
            if rate > 0:
                self.rate = rate


class RateLimiter:
    """Holds one bucket per operation and lazily creates them on first use."""

    def __init__(self, overrides: dict[str, RateConfig] | None = None) -> None:
        self._rates = {**DEFAULT_RATES, **(overrides or {})}
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _bucket(self, operation: str) -> _Bucket:
        with self._lock:
            bucket = self._buckets.get(operation)
            if bucket is None:
                cfg = self._rates.get(operation, _FALLBACK)
                bucket = _Bucket(cfg)
                self._buckets[operation] = bucket
            return bucket

    def acquire(
        self, operation: str, *, block: bool = True, max_wait: float | None = None
    ) -> bool:
        """Block (by default) until a token is free for ``operation``."""
        return self._bucket(operation).acquire(block=block, max_wait=max_wait)

    def update_from_header(self, operation: str, header_value: str | None) -> None:
        """Adjust an operation's refill rate from the x-amzn-RateLimit-Limit
        header Amazon returns, so we converge on the account's real quota."""
        if not header_value:
            return
        try:
            self._bucket(operation).update_rate(float(header_value))
        except (TypeError, ValueError):
            pass
