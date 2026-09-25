"""Browserbase Search API: ranked URLs and titles."""

from __future__ import annotations

import os

import httpx

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit


class BrowserbaseSearchEngine(SearchEngine):
    NAME = "browserbase"

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("BROWSERBASE_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        body = {"query": query, "numResults": min(max(opts.count, 1), 25)}
        body.update(strip_extra_prefix(opts.extra, "browserbase_"))
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.post(
                "https://api.browserbase.com/v1/search",
                json=body,
                headers={"X-BB-API-Key": self.api_key or ""},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchHit(url=item["url"], title=item.get("title") or "", raw=item)
            for item in data.get("results") or []
            if isinstance(item, dict) and item.get("url")
        ]
