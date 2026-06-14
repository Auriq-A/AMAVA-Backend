"""Exception hierarchy for the supplier scraper.

Every failure surfaces as a ScraperError (or subclass) so callers can catch one
base type and still distinguish config / transport / extraction / login faults.
"""
from __future__ import annotations


class ScraperError(Exception):
    """Base class for all supplier-scraper errors."""


class ScraperConfigError(ScraperError):
    """Missing or invalid configuration / credentials (no network performed)."""


class TransportError(ScraperError):
    """A fetch/render failed at the Bright Data transport layer."""

    def __init__(self, message: str, *, url: str | None = None,
                 status_code: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class LoginError(ScraperError):
    """Authentication to a supplier site failed."""


class ExtractionError(ScraperError):
    """The LLM extraction step failed or returned unusable output."""
