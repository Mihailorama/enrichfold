"""Keenable web search: ``POST https://api.keenable.ai/v1/search``.

Reads ``KEENABLE_API_KEY``. Without a key it calls the keyless
``/v1/search/public`` twin (per-IP rate limits, no credits), which needs an
``X-Keenable-Title`` header. Because keyless traffic is rate-limited per IP,
``is_available()`` stays ``False`` without a key, so Keenable joins the default
fan-out only when keyed; select it explicitly to use the keyless tier.

Filters go through ``opts.extra`` with the ``keenable_`` prefix and are sent
as-is, e.g. ``keenable_site``, ``keenable_exclude_domains``,
``keenable_published_after`` / ``keenable_published_before``,
``keenable_acquired_after`` / ``keenable_acquired_before``, ``keenable_mode``,
``keenable_snippet_max_length``. Dates accept ``YYYY-MM-DD``, ISO 8601, or a
relative delta such as ``7d``. Each hit keeps the full result in ``raw``,
including ``published_at`` and ``acquired_at`` when Keenable knows them.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit

_BASE_URL = "https://api.keenable.ai"
_APP_TITLE = "enrichfold"


def _build_body(query: str, opts: SearchOptions) -> dict[str, Any]:
    body: dict[str, Any] = {"query": query, "max_results": max(1, min(opts.count, 50))}
    body.update(strip_extra_prefix(opts.extra, "keenable_"))
    return body


class KeenableSearchEngine(SearchEngine):
    NAME = "keenable"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("KEENABLE_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        if self.api_key:
            path, headers = "/v1/search", {"X-API-Key": self.api_key}
        else:
            path, headers = "/v1/search/public", {"X-Keenable-Title": _APP_TITLE}
        async with httpx.AsyncClient(
            timeout=float(opts.timeout_s), base_url=_BASE_URL
        ) as client:
            response = await client.post(
                path, json=_build_body(query, opts), headers=headers
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchHit(
                url=item["url"],
                title=item.get("title") or "",
                snippet=item.get("snippet") or item.get("description") or "",
                raw=item,
            )
            for item in data.get("results") or []
            if isinstance(item, dict) and item.get("url")
        ]


__all__ = ["KeenableSearchEngine", "_build_body"]
