"""Lightweight HTML reduction before sending a page to the LLM.

Goal: cut tokens (=cost) without losing product data. We drop scripts, styles,
SVGs, comments and collapse whitespace using stdlib regex only (no bs4/lxml
dependency). It doesn't need to be perfect - the LLM tolerates messy HTML; we
just remove the obvious noise and truncate very large pages.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

_PATTERNS = [
    re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<noscript\b[^>]*>.*?</noscript>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<head\b[^>]*>.*?</head>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<!--.*?-->", re.DOTALL),
]
_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")

_HREF_RE = re.compile(r'href=["\']([^"\'#\s][^"\']*)["\']', re.IGNORECASE)

# Top-level path segments that are never product pages.
_NAV_SEGMENTS = frozenset({
    "search", "filter", "sort", "cart", "checkout", "account", "login",
    "logout", "register", "signup", "wishlist", "compare", "contact",
    "about", "help", "faq", "blog", "news", "press", "careers", "policy",
    "terms", "privacy", "sitemap", "cookie", "accessibility",
})

# Static-asset / framework paths that look same-domain but are never products.
_ASSET_PATHS = ("/_next/", "/static/", "/assets/", "/api/", "/_nuxt/", "/cdn-cgi/")
_ASSET_EXT_RE = re.compile(
    r"\.(?:css|js|mjs|json|xml|map|png|jpe?g|gif|svg|ico|webp|avif|"
    r"woff2?|ttf|eot|pdf|zip|mp4|webm|txt)(?:$|\?)",
    re.IGNORECASE,
)


def extract_product_links(html: str, page_url: str | None = None) -> list[str]:
    """Extract candidate product-page URLs from raw HTML.

    Parses every <a href> before cleaning, resolves relative links against
    ``page_url``, and filters to same-domain URLs that look like product
    pages. The list is passed to the Gemini extractor so it can match each
    product to its real URL rather than guessing.
    """
    base_domain = urlparse(page_url).netloc if page_url else ""
    seen: set[str] = set()
    links: list[str] = []

    for href in _HREF_RE.findall(html):
        if href.startswith(("javascript:", "mailto:", "tel:", "data:")):
            continue
        url = urljoin(page_url, href) if page_url else href
        if not url.startswith("http"):
            continue
        parsed = urlparse(url)
        # Stay on the same domain.
        if base_domain and parsed.netloc != base_domain:
            continue
        path_lower = parsed.path.lower()
        # Skip static assets / framework chunks (CSS, JS, images, _next, api...).
        if _ASSET_EXT_RE.search(path_lower) or any(a in path_lower for a in _ASSET_PATHS):
            continue
        # Skip obvious navigation paths.
        first_segment = path_lower.strip("/").split("/")[0] if path_lower.strip("/") else ""
        if first_segment in _NAV_SEGMENTS:
            continue
        if any(p in path_lower for p in ("/cart/", "/account/", "/login", "/logout")):
            continue
        # Deduplicate on scheme+domain+path (ignore query string noise).
        key = parsed.scheme + parsed.netloc + parsed.path
        if key in seen:
            continue
        seen.add(key)
        links.append(url)

    return links[:300]


def clean_html(html: str, *, max_chars: int | None = None) -> str:
    """Return a reduced version of ``html`` suitable for LLM extraction."""
    cleaned = html
    for pattern in _PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned)
    cleaned = _BLANK_LINES.sub("\n", cleaned)
    cleaned = cleaned.strip()
    if max_chars is not None and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]
    return cleaned
