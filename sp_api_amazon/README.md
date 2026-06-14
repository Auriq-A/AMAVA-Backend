# sp_api_amazon

A lean, dependency-light OOP client for the Amazon **Selling Partner API
(SP-API)**. One facade class, operations grouped by API. Synchronous, built on
`requests`. No cloud infrastructure required.

> Status: foundation. Implements the core engine (auth, rate limiting, retries,
> RDT) and a first set of APIs. Adding more operations is a small, repeatable
> pattern (see *Extending* below).

## Install / requirements

Only `requests` is required (already in the project venv). `python-dotenv` is
used if present to auto-load `.env`, otherwise the real environment is used.

## Configure

Set these environment variables (or pass a `Credentials` object directly). See
[.env.example](.env.example):

| Variable | Required | Purpose |
|---|---|---|
| `SPAPI_LWA_CLIENT_ID` | yes | LWA application client id |
| `SPAPI_LWA_CLIENT_SECRET` | yes | LWA application client secret |
| `SPAPI_REFRESH_TOKEN` | yes | Seller authorization refresh token |
| `SPAPI_MARKETPLACE` | no | Default marketplace (default `US`) |
| `SPAPI_SELLER_ID` | no | Merchant token; needed by Listings Items API |
| `SPAPI_SANDBOX` | no | `true` to hit sandbox hosts |
| `SPAPI_AWS_*` | no | Only if `use_sigv4=True` (not normally needed) |

## Usage

```python
from sp_api_amazon import AmazonSPAPI

sp = AmazonSPAPI()  # reads env; or AmazonSPAPI(Credentials(...), marketplace="UK")

# Sanity check (no parameters, not restricted):
parts = sp.sellers.get_marketplace_participations()
print(parts.payload)

# Orders
orders = sp.orders.get_orders(created_after="2024-01-01T00:00:00Z",
                              order_statuses=["Unshipped"])
for o in orders.get("Orders", []):
    print(o["AmazonOrderId"])

# Buyer PII -> client auto-mints a Restricted Data Token:
addr = sp.orders.get_order_address("111-2222222-3333333")

# Catalog / pricing
sp.catalog.search_catalog_items(keywords=["usb-c cable"], page_size=10)
sp.pricing.get_item_offers("B08N5WRWNW", item_condition="New")

# Listings (needs seller_id)
sp.listings.delete_listings_item(sku="MY-SKU-1")   # the "removeListing" op

# Reports (request -> poll -> download)
rep = sp.reports.create_report(report_type="GET_MERCHANT_LISTINGS_ALL_DATA")
```

Every call returns an `SPAPIResponse` with:
`.payload` (results, unwrapped), `.errors`, `.next_token` (pagination),
`.status_code`, `.headers`, `.raw`, and `.get(key)`.

Failures raise a typed `SPAPIError` subclass: `SPAPIAuthError`,
`SPAPIThrottledError`, `SPAPINotFoundError`, `SPAPIValidationError`,
`SPAPIServerError`, `SPAPIConfigError`.

## What's handled for you

- **Auth** — LWA token exchange + caching + auto-refresh; grantless tokens.
- **Restricted Data Tokens** — minted and cached automatically for PII calls.
- **Rate limiting** — per-operation token buckets, self-correcting from the
  `x-amzn-RateLimit-Limit` response header.
- **Retries** — exponential backoff + jitter on 429/5xx; one token refresh on
  401/403; honors `Retry-After`.
- **SigV4** — available but off by default (modern SP-API doesn't need it).

## Implemented APIs

`sellers` · `orders` · `inventory` (FBA) · `listings` · `catalog` · `pricing`
· `product_types` · `reports` · `feeds` · `sales` · `tokens`

### Not yet (planned, same pattern)

Fulfillment Inbound/Outbound, Merchant Fulfillment, Finances, Notifications,
Data Kiosk (GraphQL), Amazon Advertising API (separate auth).

## Layout

```
sp_api_amazon/
  __init__.py        AmazonSPAPI facade + public exports
  config.py          Credentials, SPAPIConfig (+ .from_env / .resolve)
  marketplaces.py    marketplace IDs, regions, endpoints
  auth.py            LWA access/grantless token manager
  rate_limit.py      per-operation token buckets
  signers.py         optional AWS SigV4
  client.py          core request engine (retry, RDT, errors) + SPAPIResponse
  exceptions.py      SPAPIError hierarchy
  sections/          one module per API (orders.py, listings.py, ...)
    base.py          shared _get/_post/_put/_patch/_delete helpers
```

## Extending (add an operation)

1. Find/create the section module in `sections/` (set `path_prefix`).
2. Add a method that builds params/body and calls `self._get/_post/...` with
   the camelCase `operation=` name.
3. Add that operation's rate limit to `DEFAULT_RATES` in `rate_limit.py`
   (optional — there's a safe fallback).
4. For a new API, also register the section in `AmazonSPAPI.__init__`.
