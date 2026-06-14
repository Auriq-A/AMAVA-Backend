"""ADK tools exposed to AMAVAGENT.

Each tool resolves the current user from the ADK context and scopes all work to
that tenant. Tools return plain dicts (JSON-serializable) for the model.
"""
from __future__ import annotations

from google.adk.tools import ToolContext

from .context import current_user_id
from .runtime import get_db
from .services import run_supplier_scrape

_NO_USER = {
    "status": "error",
    "error": "No authenticated user in session context. The API layer must open "
    "the ADK session with the AMAVA user id.",
}


async def scrape_supplier(
    supplier: str,
    max_pages: int = 1,
    start_url: str = "",
    enrich: bool = False,
    max_enrich: int = 0,
    tool_context: ToolContext = None,  # injected by ADK; hidden from the model
) -> dict:
    """Scrape a wholesaler/supplier for the current user and save the products.

    Args:
        supplier: Registered supplier name (e.g. "888lots", "avasam").
        max_pages: How many catalog pages to scrape.
        start_url: Optional URL to start at (defaults to the supplier's base).
        enrich: If true, also visit each product's detail page to fetch its
            full description, gallery images, specifications, rating and
            stock. Slower and uses more API calls - only enable when the user
            asks for full product details (e.g. to prep an Amazon listing).
        max_enrich: Max number of products to enrich when enrich=true. 0 uses
            a small default cap (~10) to control cost; raise it for more.

    Returns:
        A summary with how many products were found/enriched and a sample.
    """
    user_id = current_user_id(tool_context)
    if user_id is None:
        return _NO_USER
    try:
        run_id, result = await run_supplier_scrape(
            user_id, supplier, start_url=start_url or None, max_pages=max_pages,
            enrich=enrich, max_enrich=(max_enrich or None),
        )
    except Exception as exc:  # noqa: BLE001 - report cleanly to the model
        return {"status": "error", "supplier": supplier, "error": str(exc)}

    return {
        "status": "ok",
        "run_id": run_id,
        "supplier": supplier,
        "products_found": result.count,
        "products_enriched": result.metadata.get("products_enriched", 0),
        "pages_scraped": result.pages_scraped,
        "transport": result.transport_used,
        "sample": [
            {k: v for k, v in p.to_dict().items()
             if k in ("sku", "title", "price", "currency", "moq", "brand",
                      "description", "images", "rating")}
            for p in result.products[:5]
        ],
    }


def list_recent_products(
    limit: int = 20,
    supplier: str = "",
    tool_context: ToolContext = None,
) -> dict:
    """List the current user's most recently scraped products.

    Args:
        limit: Maximum number of products to return.
        supplier: Optional supplier name to filter by.
    """
    user_id = current_user_id(tool_context)
    if user_id is None:
        return _NO_USER

    from amava_db import ScrapeStore

    with get_db().session() as s:
        products = ScrapeStore(s).list_products(
            user_id, supplier=supplier or None, limit=limit
        )
        items = [
            {
                "sku": p.sku, "title": p.title, "price": p.price,
                "currency": p.currency, "brand": p.brand,
                "image_url": p.image_url, "description": p.description,
            }
            for p in products
        ]
    return {"status": "ok", "count": len(items), "products": items}
