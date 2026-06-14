"""Extractor interface.

An extractor turns a page's HTML into a list of Product records. The default
implementation is LLM-based (GeminiExtractor), which adapts to any supplier
layout; a selector-based extractor could implement the same interface later.
"""
from __future__ import annotations

from ..models import Product


class Extractor:
    async def extract(
        self,
        html: str,
        *,
        page_url: str | None = None,
        hint: str = "",
    ) -> list[Product]:
        raise NotImplementedError

    async def extract_detail(
        self,
        html: str,
        *,
        page_url: str | None = None,
        hint: str = "",
    ) -> Product | None:
        """Extract fuller details for a SINGLE product from its detail page.

        Used by ``SupplierScraper``'s optional enrichment step. Should return
        a ``Product`` populated with whatever it can find (description,
        images, specifications, rating, stock_quantity, plus anything from
        the listing fields it can confirm), or ``None`` if nothing useful was
        found on the page.
        """
        raise NotImplementedError
