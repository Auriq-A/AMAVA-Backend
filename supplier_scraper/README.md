# supplier_scraper

Scrapes wholesaler / supplier / distributor sites via **Bright Data**, then uses
**Gemini** to extract structured products from *any* layout (no per-site
selectors to maintain). Async-first, same OOP style as `sp_api_amazon`.

> Status: foundation built and import/flow-verified offline. **Not yet run
> against live Bright Data / Gemini** — needs your credentials + a smoke test.

## How it works

```
                         ┌─────────────────────────────┐
 supplier URL ─▶ pick ─▶ │ Scraping Browser (gated)     │ ─▶ HTML ─▶ Gemini ─▶ Product[]
            transport    │ Web Unlocker     (public)    │
                         └─────────────────────────────┘
```

- **Transport is chosen per supplier:** login required → Scraping Browser
  (Playwright over CDP: login, JS, click-pagination). Public → Web Unlocker
  (stateless, cheaper).
- **Extraction is layout-agnostic:** the page HTML is cleaned and handed to
  Gemini, which returns a JSON array of products. Sites can change without
  breaking the scraper.

## Cost controls (important)

Scraping Browser bills **per GB**. By default we **abort image/media/font/CSS**
requests (`ScraperConfig.block_resources`) — typically a **5–10× bandwidth cut**.
HTML sent to Gemini is also capped (`max_html_chars`) to bound token cost.
For public sites, Web Unlocker (per-request) is usually cheaper still.

## Install

```bash
pip install -r supplier_scraper/requirements.txt
# No `playwright install` needed — the browser is remote (Bright Data).
```

## Configure

See [.env.example](.env.example). Minimum:
- **Scraping Browser:** `BRIGHTDATA_BROWSER_AUTH`
  (`brd-customer-<id>-zone-<zone>:<password>` from the dashboard)
- **Web Unlocker:** `BRIGHTDATA_API_TOKEN` + `BRIGHTDATA_UNLOCKER_ZONE`
- **Gemini:** `GOOGLE_API_KEY` (already used by the ADK agent)
- **Per-supplier login:** e.g. `AVASAM_EMAIL` / `AVASAM_PASSWORD`

## Usage

```python
from supplier_scraper import SupplierScraper, PaginationConfig

scraper = SupplierScraper()  # reads env; no network until you scrape

# Ad-hoc public catalog (Web Unlocker), 3 pages via ?page=N:
result = await scraper.scrape(
    "https://supplier.com/catalog",
    max_pages=3,
    pagination=PaginationConfig(strategy="query", page_param="page", max_pages=3),
)

# Registered, login-gated supplier (Scraping Browser):
result = await scraper.scrape_supplier("avasam", max_pages=5)

for p in result.products:
    print(p.sku, p.title, p.price, p.currency)
print(result.count, "products from", result.pages_scraped, "pages via", result.transport_used)

# Non-async caller:
result = scraper.scrape_supplier_sync("888lots")
```

Each run returns a `ScrapeResult` (`.products`, `.count`, `.pages_scraped`,
`.transport_used`, `.errors`, `.to_dict()`). Each `Product` has `title, sku,
price, currency, moq, in_stock, brand, upc, ean, product_url, image_url,
category, extra`.

## Registering a supplier

Edit [suppliers.py](suppliers.py) (the AVASAM/888lots/Frontier entries are
TEMPLATES — fill in real selectors), or register at runtime:

```python
from supplier_scraper import register, SupplierProfile, LoginConfig, PaginationConfig

register(SupplierProfile(
    name="acme",
    base_url="https://acme-wholesale.com",
    requires_login=True,
    transport="browser",
    login=LoginConfig(
        url="https://acme-wholesale.com/login",
        username_selector="#email", password_selector="#password",
        submit_selector="button[type=submit]",
        username_env="ACME_USER", password_env="ACME_PASS",
    ),
    pagination=PaginationConfig(strategy="next_button", next_selector="a.next", max_pages=10),
    extraction_hint="Prices are per case; MOQ shown as 'Min Qty'.",
))
```

## Layout

```
supplier_scraper/
  __init__.py        SupplierScraper facade + exports
  config.py          BrightDataConfig, ScraperConfig (+ .from_env)
  models.py          Product, ScrapeResult, SupplierProfile, Login/Pagination
  exceptions.py      ScraperError hierarchy
  suppliers.py       supplier registry (templates to fill in)
  scraper.py         orchestrator: transport routing, pagination, extraction
  transports/        base, scraping_browser (Playwright/CDP), web_unlocker (httpx)
  extraction/        base, html_clean (regex reducer), llm (GeminiExtractor)
```

## Not yet / next

- Fill real login & pagination selectors per supplier.
- Live smoke test once Bright Data creds are set.
- Optional: hybrid selector+LLM extractor; persist results to the DB / hand to
  the ADK agent as a tool.
