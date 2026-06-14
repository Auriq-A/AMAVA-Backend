"""Gemini-based product extraction.

Sends cleaned page HTML to Gemini and asks for a strict JSON array of products.
Because it works from intent ("find the products and their fields") rather than
hard-coded selectors, the same code adapts to any supplier layout - which is
what keeps the scraper from feeling brittle/"cheap" when a site changes.

Uses the google-genai SDK, which reads GOOGLE_API_KEY (or the Vertex env vars)
from the environment - the same credentials the project's ADK agent uses.
"""
from __future__ import annotations

import json

from ..exceptions import ExtractionError, ScraperConfigError
from ..models import Product
from .base import Extractor
from .html_clean import clean_html

# Fields we ask the model to populate (mirrors Product). Kept here so the prompt
# and the dataclass stay in sync.
_FIELDS = [
    "title", "sku", "price", "currency", "moq", "in_stock",
    "brand", "upc", "ean", "product_url", "image_url", "category",
]

_SYSTEM = (
    "You extract product data from an e-commerce / wholesale supplier web page. "
    "Return ONLY a JSON array (no prose, no markdown fences). Each element is an "
    "object with these keys: " + ", ".join(_FIELDS) + ". "
    "Use null for anything not present. price must be a number (no currency "
    "symbol); put the currency code in 'currency'. moq is an integer (minimum "
    "order quantity) or null. in_stock is true/false/null. If the page is a "
    "catalog/list, return every product on it. If it's a single product page, "
    "return a one-element array. Do not invent values."
)

# Extra fields only meaningful on a single product's detail page.
_DETAIL_ONLY_FIELDS = [
    "description", "images", "specifications", "rating", "stock_quantity",
]
_DETAIL_FIELDS = _FIELDS + _DETAIL_ONLY_FIELDS

_DETAIL_SYSTEM = (
    "You extract full product details from a SINGLE product's detail page on "
    "an e-commerce / wholesale supplier site. Return ONLY a JSON object (no "
    "prose, no markdown fences) with these keys: " + ", ".join(_DETAIL_FIELDS) + ". "
    "Use null for anything not present. price must be a number (no currency "
    "symbol); put the currency code in 'currency'. moq and stock_quantity are "
    "integers or null. in_stock is true/false/null. images is an array of "
    "absolute image URLs for the product gallery (resolve relative URLs "
    "against the page URL), most representative first - omit thumbnails, "
    "icons and logos. specifications is an object mapping spec name -> spec "
    "value (both strings), taken from any spec table, attribute list, or "
    "bullet points (e.g. weight, dimensions, color, material, model number, "
    "pack size). description is the full product description as plain text "
    "(strip HTML tags), trimmed to the essential content. rating is the "
    "average review score as a number from 0 to 5, or null if there are no "
    "reviews. Do not invent values - if a field isn't on the page, use "
    "null (or an empty array/object for images/specifications)."
)


class GeminiExtractor(Extractor):
    def __init__(self, model: str = "gemini-2.5-flash-lite",
                 *, max_html_chars: int = 400_000) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise ScraperConfigError(
                "google-genai is not installed. Run: pip install google-genai"
            ) from exc
        self._genai = genai
        # Client() picks up GOOGLE_API_KEY / Vertex config from the environment.
        self._client = genai.Client()
        self._model = model
        self._max_html_chars = max_html_chars

    async def extract(
        self,
        html: str,
        *,
        page_url: str | None = None,
        hint: str = "",
    ) -> list[Product]:
        from google.genai import types

        cleaned = clean_html(html, max_chars=self._max_html_chars)
        prompt_parts = [_SYSTEM]
        if hint:
            prompt_parts.append(f"Site-specific notes: {hint}")
        if page_url:
            prompt_parts.append(
                f"Page URL (resolve relative product/image links against it): {page_url}"
            )
        prompt_parts.append("PAGE HTML:\n" + cleaned)
        prompt = "\n\n".join(prompt_parts)

        try:
            resp = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(f"Gemini extraction call failed: {exc}") from exc

        return self._parse(resp.text or "")

    async def extract_detail(
        self,
        html: str,
        *,
        page_url: str | None = None,
        hint: str = "",
    ) -> Product | None:
        from google.genai import types

        cleaned = clean_html(html, max_chars=self._max_html_chars)
        prompt_parts = [_DETAIL_SYSTEM]
        if hint:
            prompt_parts.append(f"Site-specific notes: {hint}")
        if page_url:
            prompt_parts.append(
                f"Page URL (resolve relative image/link URLs against it): {page_url}"
            )
        prompt_parts.append("PAGE HTML:\n" + cleaned)
        prompt = "\n\n".join(prompt_parts)

        try:
            resp = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(f"Gemini detail extraction call failed: {exc}") from exc

        return self._parse_detail(resp.text or "")

    # -- parsing ----------------------------------------------------------
    @staticmethod
    def _parse(text: str) -> list[Product]:
        raw = _loads_lenient(text)
        if raw is None:
            raise ExtractionError("Extractor returned no parseable JSON.")
        if isinstance(raw, dict):
            # Model occasionally wraps the array, e.g. {"products": [...]}.
            for key in ("products", "items", "data", "results"):
                if isinstance(raw.get(key), list):
                    raw = raw[key]
                    break
            else:
                raw = [raw]
        if not isinstance(raw, list):
            raise ExtractionError("Extractor JSON was not a list of products.")

        products: list[Product] = []
        allowed = set(_FIELDS)
        for item in raw:
            if not isinstance(item, dict):
                continue
            known = {k: item.get(k) for k in allowed}
            extra = {k: v for k, v in item.items() if k not in allowed}
            known["price"] = _to_float(known.get("price"))
            known["moq"] = _to_int(known.get("moq"))
            products.append(Product(extra=extra, **known))
        return products

    @staticmethod
    def _parse_detail(text: str) -> Product | None:
        raw = _loads_lenient(text)
        if raw is None:
            raise ExtractionError("Detail extractor returned no parseable JSON.")
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ExtractionError("Detail extractor JSON was not an object.")

        allowed = set(_DETAIL_FIELDS)
        known = {k: raw.get(k) for k in allowed}
        extra = {k: v for k, v in raw.items() if k not in allowed}
        known["price"] = _to_float(known.get("price"))
        known["moq"] = _to_int(known.get("moq"))
        known["stock_quantity"] = _to_int(known.get("stock_quantity"))
        known["rating"] = _to_float(known.get("rating"))

        images = known.get("images")
        known["images"] = (
            [u for u in images if isinstance(u, str) and u]
            if isinstance(images, list) else []
        )

        specs = known.get("specifications")
        known["specifications"] = (
            {str(k): str(v) for k, v in specs.items()}
            if isinstance(specs, dict) else {}
        )

        return Product(extra=extra, **known)


def _loads_lenient(text: str):
    text = text.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` fences if the model added them.
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the largest [...] or {...} span.
        for open_c, close_c in (("[", "]"), ("{", "}")):
            start, end = text.find(open_c), text.rfind(close_c)
            if 0 <= start < end:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
    return None


def _to_float(value):
    if value is None or isinstance(value, (int, float)):
        return float(value) if value is not None else None
    try:
        cleaned = "".join(c for c in str(value) if c.isdigit() or c in ".-")
        return float(cleaned) if cleaned not in ("", "-", ".") else None
    except (TypeError, ValueError):
        return None


def _to_int(value):
    f = _to_float(value)
    return int(f) if f is not None else None
