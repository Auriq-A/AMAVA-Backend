"""Sellers API (v1).

The simplest API - a good first call to confirm credentials work, since it
takes no parameters and isn't restricted.
"""
from __future__ import annotations

from ..client import SPAPIResponse
from .base import BaseSection


class SellersAPI(BaseSection):
    path_prefix = "/sellers/v1"

    def get_marketplace_participations(self) -> SPAPIResponse:
        """List the marketplaces the seller can sell in, and their
        participation status. Operation: getMarketplaceParticipations."""
        return self._get(
            "/marketplaceParticipations",
            operation="getMarketplaceParticipations",
        )
