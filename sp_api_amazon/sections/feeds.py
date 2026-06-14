"""Feeds API (2021-06-30).

Bulk uploads (inventory, pricing, listings). The typical flow:
    1. create_feed_document(contentType=...) -> {feedDocumentId, url}
    2. upload the feed contents to that URL (caller's responsibility)
    3. create_feed(feedType=..., inputFeedDocumentId=...) -> feedId
    4. poll get_feed(feedId) until processingStatus == "DONE"
    5. get_feed_document(resultFeedDocumentId) for the processing report
"""
from __future__ import annotations

from typing import Any

from ..client import SPAPIResponse
from .base import BaseSection


class FeedsAPI(BaseSection):
    path_prefix = "/feeds/2021-06-30"

    def create_feed_document(self, *, content_type: str) -> SPAPIResponse:
        """Create an upload destination for feed contents.
        Operation: createFeedDocument. e.g. content_type
        "text/tab-separated-values; charset=UTF-8" or "application/json"."""
        return self._post(
            "/documents",
            operation="createFeedDocument",
            json_body={"contentType": content_type},
        )

    def create_feed(
        self,
        *,
        feed_type: str,
        input_feed_document_id: str,
        marketplace_ids: list[str] | None = None,
        feed_options: dict[str, Any] | None = None,
    ) -> SPAPIResponse:
        """Submit a feed for processing. Operation: createFeed."""
        body: dict[str, Any] = {
            "feedType": feed_type,
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "inputFeedDocumentId": input_feed_document_id,
        }
        if feed_options:
            body["feedOptions"] = feed_options
        return self._post("/feeds", operation="createFeed", json_body=body)

    def get_feed(self, feed_id: str) -> SPAPIResponse:
        """Check a feed's processing status. Operation: getFeed."""
        return self._get(f"/feeds/{feed_id}", operation="getFeed")

    def cancel_feed(self, feed_id: str) -> SPAPIResponse:
        """Cancel a queued feed. Operation: cancelFeed."""
        return self._delete(f"/feeds/{feed_id}", operation="cancelFeed")

    def get_feed_document(self, feed_document_id: str) -> SPAPIResponse:
        """Get the download URL + compression for a feed's result document.
        Operation: getFeedDocument."""
        return self._get(
            f"/documents/{feed_document_id}", operation="getFeedDocument"
        )
