"""Seltz REST Search API: ``POST /v1/search``."""

from __future__ import annotations

import os

import httpx

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit


class SeltzSearchEngine(SearchEngine):
    NAME = "seltz"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("SELTZ_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        body = {"query": query, "max_results": opts.count}
        body.update(strip_extra_prefix(opts.extra, "seltz_"))
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.post(
                "https://api.seltz.ai/v1/search",
                json=body,
                headers={"x-api-key": self.api_key or ""},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchHit(url=item["url"], snippet=item.get("content") or "", raw=item)
            for item in data.get("documents") or []
            if isinstance(item, dict) and item.get("url")
        ]
