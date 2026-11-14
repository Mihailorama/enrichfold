"""Scrapingdog Google SERP: ``GET https://api.scrapingdog.com/google``.

Reads ``SCRAPINGDOG_API_KEY``. Parameters copy ai-utils' former
``perform_google_scrapingdog_search`` (removed there 2026-11-12):
``query``, ``results``, ``page=0``, ``country=us``. ``results`` is
``opts.count`` (ai-utils sent 20) and ``opts.country`` replaces ``us``.
``scrapingdog_*`` extras override any parameter.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from enrichfold.search.engines.base import SearchEngine, check_response
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit

_ENDPOINT = "https://api.scrapingdog.com/google"


def _build_params(query: str, opts: SearchOptions) -> dict[str, Any]:
    params: dict[str, Any] = {
        "query": query,
        "results": opts.count,
        "page": 0,
        "country": opts.country or "us",
    }
    params.update(strip_extra_prefix(opts.extra, "scrapingdog_"))
    return params


class ScrapingdogSearchEngine(SearchEngine):
    NAME = "scrapingdog"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("SCRAPINGDOG_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        params = {**_build_params(query, opts), "api_key": self.api_key or ""}
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.get(_ENDPOINT, params=params)
            check_response(response)
            data = response.json()
        return [
            SearchHit(
                url=item["link"],
                title=item.get("title") or "",
                snippet=item.get("snippet") or "",
                raw=item,
            )
            for item in data.get("organic_results") or []
            if isinstance(item, dict) and item.get("link")
        ]


__all__ = ["ScrapingdogSearchEngine", "_build_params"]
