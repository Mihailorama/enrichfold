"""Treg's routed web search, backed by its provider catalog."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from enrichfold.search.engines.base import SearchEngine
from enrichfold.search.options import SearchOptions
from enrichfold.search.types import SearchHit
from enrichfold.treg import TregClient


class TregSearchEngine(SearchEngine):
    NAME = "treg"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("TREG_TOKEN"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        response = await TregClient(self.api_key).call(
            "treg.web.search",
            request={"q": query, "limit": opts.count},
            max_cost_usd=float(opts.extra.get("treg_max_cost_usd", 1.0)),
            timeout_s=float(opts.timeout_s),
        )
        data = response.data
        output = data.get("output") if isinstance(data, Mapping) else None
        results = output.get("results") if isinstance(output, Mapping) else None
        if not isinstance(results, list):
            raise TypeError(
                "invalid Treg web.search response: output.results must be a list"
            )
        hits: list[SearchHit] = []
        for item in results[: opts.count]:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("link")
            if not isinstance(url, str) or not url:
                continue
            raw: dict[str, Any] = dict(item)
            if response.served_by:
                raw["treg_served_by"] = response.served_by
            if response.call_id:
                raw["treg_call_id"] = response.call_id
            hits.append(
                SearchHit(
                    url=url,
                    title=str(item.get("title") or item.get("name") or ""),
                    snippet=str(
                        item.get("snippet")
                        or item.get("description")
                        or item.get("content")
                        or ""
                    ),
                    raw=raw,
                )
            )
        return hits


__all__ = ["TregSearchEngine"]
