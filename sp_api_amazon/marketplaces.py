"""Amazon SP-API marketplaces and regional endpoints.

A single source of truth for marketplace IDs, the region each marketplace
belongs to, and the host endpoints for each region (both production and
sandbox). Everything else in the package resolves hosts/marketplace IDs
through here so there are no magic strings scattered around.
"""
from __future__ import annotations

from dataclasses import dataclass


# Login With Amazon (LWA) token endpoint is global, independent of region.
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"


@dataclass(frozen=True)
class Region:
    """An SP-API region: a production host, a sandbox host, and the AWS
    region used for (optional) SigV4 signing."""

    code: str
    endpoint: str
    sandbox_endpoint: str
    aws_region: str


# The three SP-API regions. A seller's account lives in exactly one of them.
NA = Region(
    code="na",
    endpoint="https://sellingpartnerapi-na.amazon.com",
    sandbox_endpoint="https://sandbox.sellingpartnerapi-na.amazon.com",
    aws_region="us-east-1",
)
EU = Region(
    code="eu",
    endpoint="https://sellingpartnerapi-eu.amazon.com",
    sandbox_endpoint="https://sandbox.sellingpartnerapi-eu.amazon.com",
    aws_region="eu-west-1",
)
FE = Region(
    code="fe",
    endpoint="https://sellingpartnerapi-fe.amazon.com",
    sandbox_endpoint="https://sandbox.sellingpartnerapi-fe.amazon.com",
    aws_region="us-west-2",
)

REGIONS: dict[str, Region] = {r.code: r for r in (NA, EU, FE)}


@dataclass(frozen=True)
class Marketplace:
    """A single Amazon marketplace (one storefront/country)."""

    name: str          # short key, e.g. "US"
    country_code: str  # ISO country, e.g. "US"
    marketplace_id: str
    region: Region


# Common marketplaces grouped by region. Add more as needed; the IDs are
# stable and published by Amazon.
_MARKETPLACE_LIST: list[Marketplace] = [
    # North America
    Marketplace("US", "US", "ATVPDKIKX0DER", NA),
    Marketplace("CA", "CA", "A2EUQ1WTGCTBG2", NA),
    Marketplace("MX", "MX", "A1AM78C64UM0Y8", NA),
    Marketplace("BR", "BR", "A2Q3Y263D1NRT2", NA),
    # Europe
    Marketplace("UK", "GB", "A1F83G8C2ARO7P", EU),
    Marketplace("DE", "DE", "A1PA6795UKMFR9", EU),
    Marketplace("FR", "FR", "A13V1IB3VIYZZH", EU),
    Marketplace("IT", "IT", "APJ6JRA9NG5V4", EU),
    Marketplace("ES", "ES", "A1RKKUPIHCS9HS", EU),
    Marketplace("NL", "NL", "A1805IZSGTT6HS", EU),
    Marketplace("SE", "SE", "A2NODRKZP88ZB9", EU),
    Marketplace("PL", "PL", "A1C3SOZRARQ6R3", EU),
    Marketplace("BE", "BE", "AMEN7PMS3EDWL", EU),
    Marketplace("TR", "TR", "A33AVAJ2PDY3EV", EU),
    Marketplace("AE", "AE", "A2VIGQ35RCS4UG", EU),
    Marketplace("SA", "SA", "A17E79C6D8DWNP", EU),
    Marketplace("EG", "EG", "ARBP9OOSHTCHU", EU),
    Marketplace("IN", "IN", "A21TJRUUN4KGV", EU),
    # Far East
    Marketplace("JP", "JP", "A1VC38T7YXB528", FE),
    Marketplace("AU", "AU", "A39IBJ37TRP1C6", FE),
    Marketplace("SG", "SG", "A19VAU5U5O7RUS", FE),
]

# Lookups by short name and by raw marketplace ID.
MARKETPLACES: dict[str, Marketplace] = {m.name: m for m in _MARKETPLACE_LIST}
MARKETPLACES_BY_ID: dict[str, Marketplace] = {
    m.marketplace_id: m for m in _MARKETPLACE_LIST
}


def resolve_marketplace(value: str) -> Marketplace:
    """Accept a short name ("US"), a country code, or a raw marketplace ID
    and return the matching Marketplace."""
    if value in MARKETPLACES:
        return MARKETPLACES[value]
    if value in MARKETPLACES_BY_ID:
        return MARKETPLACES_BY_ID[value]
    upper = value.upper()
    if upper in MARKETPLACES:
        return MARKETPLACES[upper]
    for m in _MARKETPLACE_LIST:
        if m.country_code == upper:
            return m
    raise KeyError(
        f"Unknown marketplace {value!r}. Known names: "
        f"{', '.join(sorted(MARKETPLACES))}"
    )
