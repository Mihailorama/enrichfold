"""Nimble v2 Search API: sourced web results."""

from __future__ import annotations

import os

import httpx

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit


class NimbleSearchEngine(SearchEngine):
    NAME = "nimble"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("NIMBLE_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        body = {"query": query, "max_results": opts.count}
        if opts.country:
            body["country"] = opts.country
        if opts.language:
            body["locale"] = opts.language
        body.update(strip_extra_prefix(opts.extra, "nimble_"))
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.post(
                "https://sdk.nimbleway.com/v2/search",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key or ''}"},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchHit(
                url=item["url"],
                title=item.get("title") or "",
                snippet=item.get("description") or item.get("content") or "",
                raw=item,
            )
            for item in data.get("results") or []
            if isinstance(item, dict) and item.get("url")
        ]
