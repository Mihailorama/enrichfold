"""Outscraper Google search: ``GET https://api.app.outscraper.com/google-search-v3``.

Reads ``OUTSCRAPER_API_KEY`` (``X-API-KEY`` header). Parameters copy ai-utils'
``get_content_outscraper``: ``query``, ``pagesPerQuery=1``, ``language=en``.
``opts.language`` replaces ``en`` and ``opts.country`` is sent as ``region``;
``outscraper_*`` extras override any parameter. The reply's ``data`` holds one
list of results per query; hits are cut to ``opts.count``. The snippet is
Outscraper's ``description``, else ``pre_snippet`` / ``snippet``, the fields
ai-utils reads.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit

_ENDPOINT = "https://api.app.outscraper.com/google-search-v3"


def _build_params(query: str, opts: SearchOptions) -> dict[str, Any]:
    params: dict[str, Any] = {
        "query": query,
        "pagesPerQuery": 1,
        "language": opts.language or "en",
    }
    if opts.country is not None:
        params["region"] = opts.country
    params.update(strip_extra_prefix(opts.extra, "outscraper_"))
    return params


def _items(data: dict[str, Any]) -> list[Any]:
    first = (data.get("data") or [[]])[0]
    # Documented shape: a list of results per query; some endpoints wrap them.
    return first.get("organic_results") or [] if isinstance(first, dict) else first


class OutscraperSearchEngine(SearchEngine):
    NAME = "outscraper"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("OUTSCRAPER_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.get(
                _ENDPOINT,
                params=_build_params(query, opts),
                headers={"X-API-KEY": self.api_key or ""},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchHit(
                url=item["link"],
                title=item.get("title") or "",
                snippet=item.get("description")
                or item.get("pre_snippet")
                or item.get("snippet")
                or "",
                raw=item,
            )
            for item in _items(data)
            if isinstance(item, dict) and item.get("link")
        ][: opts.count]


__all__ = ["OutscraperSearchEngine", "_build_params"]
