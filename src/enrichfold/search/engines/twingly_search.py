"""Twingly News Search: ``POST https://data.twingly.net/news/b/search/v1/search``.

Reads ``TWINGLY_API_KEY`` and sends it as ``Authorization: apikey <key>``. The
JSON body puts the query in ``all``, ``opts.count`` in ``size`` and
``opts.country`` in ``locations``. Other documented body fields (``none``,
``timestamp``, ``topics``, ``entities``, ...) go through ``twingly_*`` extras,
e.g. ``{"twingly_timestamp": {"since": "2026-11-20T00:00:00Z"}}``. Each hit's
``raw`` keeps the whole document: full ``text``, ``published_at``,
``crawled_at``, ``language_code``, ``location_code``, ``site_name`` and
``topics_and_entities``. A trial key allows 100 requests in total.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from enrichfold.search.engines.base import SearchEngine, check_response
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit

_ENDPOINT = "https://data.twingly.net/news/b/search/v1/search"
_SNIPPET_CHARS = 300


def _build_body(query: str, opts: SearchOptions) -> dict[str, Any]:
    body: dict[str, Any] = {"all": [query], "size": opts.count}
    if opts.country:
        body["locations"] = [opts.country.lower()]
    body.update(strip_extra_prefix(opts.extra, "twingly_"))
    return body


class TwinglySearchEngine(SearchEngine):
    NAME = "twingly"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key or os.getenv("TWINGLY_API_KEY"))

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        headers = {"Authorization": f"apikey {self.api_key or ''}"}
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.post(
                _ENDPOINT, json=_build_body(query, opts), headers=headers
            )
            check_response(response)
            data = response.json()
        return [
            SearchHit(
                url=doc["url"],
                title=doc.get("title") or "",
                snippet=doc.get("summary") or (doc.get("text") or "")[:_SNIPPET_CHARS],
                raw=doc,
            )
            for doc in data.get("documents") or []
            if isinstance(doc, dict) and doc.get("url")
        ][: opts.count]


__all__ = ["TwinglySearchEngine", "_build_body"]
