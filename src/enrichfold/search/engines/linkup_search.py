"""Linkup Search API: ``POST /v1/search`` in source-result mode."""

from __future__ import annotations

import os

import httpx

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit


class LinkupSearchEngine(SearchEngine):
    NAME = "linkup"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("LINKUP_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        body = {"q": query, "depth": "standard", "outputType": "searchResults"}
        body.update(strip_extra_prefix(opts.extra, "linkup_"))
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.post(
                "https://api.linkup.so/v1/search",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key or ''}"},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchHit(
                url=item["url"],
                title=item.get("name") or "",
                snippet=item.get("content") or "",
                raw=item,
            )
            for item in (data.get("results") or [])[: opts.count]
            if isinstance(item, dict) and item.get("url")
        ]
