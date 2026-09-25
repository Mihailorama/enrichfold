"""TinyFish Search API: ranked results from ``GET api.search.tinyfish.ai``."""

from __future__ import annotations

import os

import httpx

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit


class TinyFishSearchEngine(SearchEngine):
    NAME = "tinyfish"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("TINYFISH_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        params = {"query": query}
        if opts.country:
            params["location"] = opts.country
        if opts.language:
            params["language"] = opts.language
        params.update(strip_extra_prefix(opts.extra, "tinyfish_"))
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.get(
                "https://api.search.tinyfish.ai",
                params=params,
                headers={"X-API-Key": self.api_key or ""},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchHit(
                url=item["url"],
                title=item.get("title") or "",
                snippet=item.get("snippet") or "",
                raw=item,
            )
            for item in (data.get("results") or [])[: opts.count]
            if isinstance(item, dict) and item.get("url")
        ]
