"""Supplier profile registry.

Register one SupplierProfile per wholesaler so the agent can scrape by name
(`scraper.scrape_supplier("avasam")`) instead of re-specifying login/pagination
every time. The profiles below are TEMPLATES - fill in the real login/pagination
selectors from each site (use the browser devtools or a quick recording).

Credentials are always read from environment variables, never stored here.
"""
from __future__ import annotations

from .models import LoginConfig, PaginationConfig, SupplierProfile

# name -> profile
SUPPLIERS: dict[str, SupplierProfile] = {}


def register(profile: SupplierProfile) -> SupplierProfile:
    SUPPLIERS[profile.name.lower()] = profile
    return profile


def get_supplier(name: str) -> SupplierProfile:
    try:
        return SUPPLIERS[name.lower()]
    except KeyError:
        known = ", ".join(sorted(SUPPLIERS)) or "(none registered)"
        raise KeyError(f"Unknown supplier {name!r}. Registered: {known}") from None


# --- Templates -------------------------------------------------------------
# AVASAM: login-gated -> Scraping Browser. Reuses the project's AVASAM creds.
# NOTE: confirm the exact selectors and the username env var name (.env has
# AVAWSAM_EMAIL; adjust username_env below if needed).
register(
    SupplierProfile(
        name="avasam",
        base_url="https://app.avasam.com/seller/product/search",
        requires_login=True,
        transport="browser",
        login=LoginConfig(
            url="https://app.avasam.com/seller/sellerregister/login",            # TODO confirm
            username_selector="input[type=email]",          # TODO confirm
            password_selector="input[type=password]",        # TODO confirm
            submit_selector="button[type=submit]",           # TODO confirm
            username_env="AVASAM_EMAIL",
            password_env="AVASAM_PASSWORD",
            success_selector=None,                            # TODO optional
        ),
        pagination=PaginationConfig(strategy="query", page_param="page", max_pages=1),
        extraction_hint="Wholesale dropshipping catalog; capture SKU, title, "
        "price, and MOQ if shown.",
        # TODO: avasam's product detail page is a React/Ant Design SPA - set
        # this to a selector that only appears once the detail page has
        # rendered (e.g. the product title or price block), otherwise
        # enrich=True will fetch an empty shell.
        detail_wait_for=None,
    )
)

# 888Lots: public liquidation listings -> cheaper Web Unlocker is usually fine.
register(
    SupplierProfile(
        name="888lots",
        base_url="https://www.888lots.com",
        requires_login=False,
        transport="unlocker",
        pagination=PaginationConfig(strategy="query", page_param="page", max_pages=1),
        extraction_hint="Liquidation lots; each item may list ASIN, retail price, "
        "and unit cost.",
    )
)

# Frontier: template - set requires_login/transport once you know the site.
register(
    SupplierProfile(
        name="frontier",
        base_url="https://www.frontierwholesale.com",        # TODO confirm
        requires_login=False,
        transport="auto",
        pagination=PaginationConfig(strategy="query", page_param="page", max_pages=1),
    )
)
