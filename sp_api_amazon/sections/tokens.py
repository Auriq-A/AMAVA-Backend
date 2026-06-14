"""Tokens API (2021-03-01).

Mints Restricted Data Tokens (RDTs) used to access PII-bearing operations.
The client mints these automatically for restricted calls (see OrdersAPI), so
this section is only needed when you want to create an RDT explicitly - e.g. to
hand a scoped token to another component.
"""
from __future__ import annotations

from typing import Any

from ..client import SPAPIResponse
from .base import BaseSection


class TokensAPI(BaseSection):
    path_prefix = "/tokens/2021-03-01"

    def create_restricted_data_token(
        self,
        restricted_resources: list[dict[str, Any]],
        *,
        target_application: str | None = None,
    ) -> SPAPIResponse:
        """Create an RDT for the given restricted resources.
        Operation: createRestrictedDataToken.

        Each resource is {"method": "GET", "path": "/orders/v0/orders",
        "dataElements": ["buyerInfo", "shippingAddress"]}.
        """
        body: dict[str, Any] = {"restrictedResources": restricted_resources}
        if target_application:
            body["targetApplication"] = target_application
        return self._post(
            "/restrictedDataToken",
            operation="createRestrictedDataToken",
            json_body=body,
        )
