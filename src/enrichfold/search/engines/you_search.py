"""You.com Search API: ``POST /v1/search`` (web and news results)."""

from __future__ import annotations

import os

import httpx

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit


class YouSearchEngine(SearchEngine):
    NAME = "you"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("YOU_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        body = {"query": query, "count": opts.count}
        body.update(strip_extra_prefix(opts.extra, "you_"))
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.post(
                "https://ydc-index.io/v1/search",
                json=body,
                headers={"X-API-Key": self.api_key or ""},
            )
            response.raise_for_status()
            data = response.json()
        results = data.get("results") or {}
        web = results.get("web") or [] if isinstance(results, dict) else []
        return [
            SearchHit(
                url=item["url"],
                title=item.get("title") or "",
                snippet=item.get("description") or "",
                raw=item,
            )
            for item in web[: opts.count]
            if isinstance(item, dict) and item.get("url")
        ]
