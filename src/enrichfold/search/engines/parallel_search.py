"""Parallel Search API: ``POST /v1/search`` with sourced excerpts."""

from __future__ import annotations

import os

import httpx

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit


class ParallelSearchEngine(SearchEngine):
    NAME = "parallel"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("PARALLEL_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        body = {"objective": query, "search_queries": [query], "mode": "fast"}
        body.update(strip_extra_prefix(opts.extra, "parallel_"))
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.post(
                "https://api.parallel.ai/v1/search",
                json=body,
                headers={"x-api-key": self.api_key or ""},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchHit(
                url=item["url"],
                title=item.get("title") or "",
                snippet="\n".join(item.get("excerpts") or []),
                raw=item,
            )
            for item in (data.get("results") or [])[: opts.count]
            if isinstance(item, dict) and item.get("url")
        ]
