"""Orders API (v0).

Reads order data and updates shipment status. Buyer PII (name, address) is
restricted: pass ``restricted=True`` to the relevant methods and the client
will automatically mint a Restricted Data Token (RDT) for the call.
"""
from __future__ import annotations

from typing import Any

from ..client import SPAPIResponse
from .base import BaseSection


class OrdersAPI(BaseSection):
    path_prefix = "/orders/v0"

    def get_orders(
        self,
        *,
        marketplace_ids: list[str] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        last_updated_after: str | None = None,
        last_updated_before: str | None = None,
        order_statuses: list[str] | None = None,
        fulfillment_channels: list[str] | None = None,
        payment_methods: list[str] | None = None,
        buyer_email: str | None = None,
        seller_order_id: str | None = None,
        max_results_per_page: int | None = None,
        amazon_order_ids: list[str] | None = None,
        next_token: str | None = None,
        restricted: bool = False,
    ) -> SPAPIResponse:
        """List orders matching the filters. Operation: getOrders.

        One of created_after / last_updated_after (or next_token) is required by
        Amazon. Set ``restricted=True`` to include buyer info / shipping address
        (uses an RDT).
        """
        params = {
            "MarketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "CreatedAfter": created_after,
            "CreatedBefore": created_before,
            "LastUpdatedAfter": last_updated_after,
            "LastUpdatedBefore": last_updated_before,
            "OrderStatuses": order_statuses,
            "FulfillmentChannels": fulfillment_channels,
            "PaymentMethods": payment_methods,
            "BuyerEmail": buyer_email,
            "SellerOrderId": seller_order_id,
            "MaxResultsPerPage": max_results_per_page,
            "AmazonOrderIds": amazon_order_ids,
            "NextToken": next_token,
        }
        rr = (
            [self._rdt_resource("GET", "/orders/v0/orders")]
            if restricted
            else None
        )
        return self._get("/orders", operation="getOrders", params=params,
                         restricted_resources=rr)

    def get_order(self, order_id: str, *, restricted: bool = False) -> SPAPIResponse:
        """Get a single order. Operation: getOrder."""
        path = f"/orders/{order_id}"
        rr = (
            [self._rdt_resource("GET", f"/orders/v0/orders/{order_id}")]
            if restricted
            else None
        )
        return self._get(path, operation="getOrder", restricted_resources=rr)

    def get_order_items(
        self, order_id: str, *, next_token: str | None = None, restricted: bool = False
    ) -> SPAPIResponse:
        """List the line items of an order. Operation: getOrderItems."""
        path = f"/orders/{order_id}/orderItems"
        rr = (
            [self._rdt_resource("GET", f"/orders/v0/orders/{order_id}/orderItems")]
            if restricted
            else None
        )
        return self._get(
            path,
            operation="getOrderItems",
            params={"NextToken": next_token},
            restricted_resources=rr,
        )

    def get_order_buyer_info(self, order_id: str) -> SPAPIResponse:
        """Get buyer info for an order (restricted - always uses an RDT).
        Operation: getOrderBuyerInfo."""
        path = f"/orders/{order_id}/buyerInfo"
        rr = [
            self._rdt_resource(
                "GET",
                f"/orders/v0/orders/{order_id}/buyerInfo",
                data_elements=["buyerInfo"],
            )
        ]
        return self._get(path, operation="getOrderBuyerInfo", restricted_resources=rr)

    def get_order_address(self, order_id: str) -> SPAPIResponse:
        """Get the shipping address for an order (restricted - uses an RDT).
        Operation: getOrderAddress."""
        path = f"/orders/{order_id}/address"
        rr = [
            self._rdt_resource(
                "GET",
                f"/orders/v0/orders/{order_id}/address",
                data_elements=["shippingAddress"],
            )
        ]
        return self._get(path, operation="getOrderAddress", restricted_resources=rr)

    def update_shipment_status(
        self,
        order_id: str,
        *,
        shipment_status: str,
        marketplace_id: str | None = None,
        order_items: list[dict[str, Any]] | None = None,
    ) -> SPAPIResponse:
        """Mark an order shipped/cancelled etc. Operation: updateShipmentStatus."""
        body: dict[str, Any] = {
            "marketplaceId": marketplace_id or self.marketplace_id,
            "shipmentStatus": shipment_status,
        }
        if order_items is not None:
            body["orderItems"] = order_items
        return self._post(
            f"/orders/{order_id}/shipment",
            operation="updateShipmentStatus",
            json_body=body,
        )

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _rdt_resource(
        method: str, path: str, data_elements: list[str] | None = None
    ) -> dict[str, Any]:
        resource: dict[str, Any] = {"method": method, "path": path}
        # buyerInfo + shippingAddress are the PII elements an RDT can unlock.
        resource["dataElements"] = data_elements or ["buyerInfo", "shippingAddress"]
        return resource
