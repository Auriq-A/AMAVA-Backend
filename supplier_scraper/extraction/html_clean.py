"""Lightweight HTML reduction before sending a page to the LLM.

Goal: cut tokens (=cost) without losing product data. We drop scripts, styles,
SVGs, comments and collapse whitespace using stdlib regex only (no bs4/lxml
dependency). It doesn't need to be perfect - the LLM tolerates messy HTML; we
just remove the obvious noise and truncate very large pages.
"""
from __future__ import annotations

import re

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
