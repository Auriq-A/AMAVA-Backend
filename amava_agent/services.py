"""Per-user orchestration: ties the credential vault + scraper + DB together.

These functions are the tenant boundary. Given a user_id they load that user's
own credentials, run the work, and persist results under that user. They are
transport/LLM-agnostic and accept injected dependencies for testing.
"""
from __future__ import annotations

from typing import Any

from amava_db import CredentialVault, ScrapeStore

from .runtime import get_box, get_db


async def run_supplier_scrape(
    user_id: int,
    supplier: str,
    *,
    start_url: str | None = None,
    max_pages: int = 1,
    enrich: bool = False,
    max_enrich: int | None = None,
    scraper: Any | None = None,
    db: Any | None = None,
    box: Any | None = None,
) -> tuple[int, Any]:
    """Scrape one supplier for a user and persist the result.

    Returns (run_id, ScrapeResult). Uses the user's stored supplier login (from
    the encrypted vault) if present; otherwise the scraper falls back to env.

    ``enrich``/``max_enrich`` are passed through to
    ``SupplierScraper.scrape_supplier`` - see its docstring for the cost
    tradeoff of visiting each product's detail page.
    """
    db = db or get_db()
    box = box or get_box()

    def credential_provider(name: str) -> tuple[str, str] | None:
        with db.session() as s:
            login = CredentialVault(s, box).get_supplier_login(user_id, name)
        if login and login.get("username") and login.get("password"):
            return login["username"], login["password"]
        return None

    if scraper is None:
        # Imported lazily so this module loads without scraper deps installed.
        from supplier_scraper import SupplierScraper

        scraper = SupplierScraper(credential_provider=credential_provider)

    transport = _resolve_transport(supplier)
    with db.session() as s:
        run_id = ScrapeStore(s).create_run(
            user_id, supplier, source_url=start_url or "", transport=transport
        ).id

    try:
        result = await scraper.scrape_supplier(
            supplier, start_url=start_url, max_pages=max_pages,
            enrich=enrich, max_enrich=max_enrich,
        )
    except Exception as exc:  # persist the failure, then re-raise
        with db.session() as s:
            ScrapeStore(s).fail_run(run_id, str(exc))
        raise

    with db.session() as s:
        ScrapeStore(s).save_result(run_id, result)
    return run_id, result


def build_user_spapi(user_id: int, *, db: Any | None = None, box: Any | None = None):
    """Construct an AmazonSPAPI client from the user's stored SP-API creds."""
    db = db or get_db()
    box = box or get_box()
    with db.session() as s:
        creds = CredentialVault(s, box).get_spapi(user_id)
    if not creds:
        raise ValueError(f"User {user_id} has no stored Amazon SP-API credentials.")

    from sp_api_amazon import AmazonSPAPI, Credentials

    return AmazonSPAPI(
        Credentials(
            lwa_client_id=creds["lwa_client_id"],
            lwa_client_secret=creds["lwa_client_secret"],
            refresh_token=creds["refresh_token"],
        ),
        marketplace=creds.get("marketplace", "US"),
        seller_id=creds.get("seller_id"),
    )


def _resolve_transport(supplier: str) -> str | None:
    try:
        from supplier_scraper.suppliers import get_supplier

        return get_supplier(supplier).resolve_transport()
    except Exception:  # noqa: BLE001 - unknown supplier; leave transport unset
        return None
