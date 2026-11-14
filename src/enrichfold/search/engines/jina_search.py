"""Jina search: ``POST https://s.jina.ai/search``.

Reads ``JINA_API_KEY`` (or ai-utils' ``JINAAI_API_KEY``). The body copies
ai-utils' ``perform_jinaai_search``: ``q`` with double quotes removed, plus
``withGeneratedAlt``, ``withLinksSummary`` and ``withImagesSummary``. ai-utils
reads the default markdown reply; this engine adds ``Accept: application/json``
to get the same results as structured items, so each hit's ``raw`` keeps
Jina's ``content``, ``links`` and ``images``. Extra body fields go through
``jina_*`` extras. Jina returns its own page size; hits are cut to
``opts.count``.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from enrichfold.search.engines.base import SearchEngine, check_response
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit

_ENDPOINT = "https://s.jina.ai/search"


def _build_body(query: str, opts: SearchOptions) -> dict[str, Any]:
    body: dict[str, Any] = {
        "q": query.replace('"', ""),
        "withGeneratedAlt": True,
        "withLinksSummary": True,
        "withImagesSummary": True,
    }
    body.update(strip_extra_prefix(opts.extra, "jina_"))
    return body


class JinaSearchEngine(SearchEngine):
    NAME = "jina"
    REQUIRES_API_KEY = True

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(
            api_key or os.getenv("JINA_API_KEY") or os.getenv("JINAAI_API_KEY")
        )

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.post(
                _ENDPOINT, json=_build_body(query, opts), headers=headers
            )
            check_response(response)
            data = response.json()
        return [
            SearchHit(
                url=item["url"],
                title=item.get("title") or "",
                snippet=item.get("description") or "",
                raw=item,
            )
            for item in data.get("data") or []
            if isinstance(item, dict) and item.get("url")
        ][: opts.count]


__all__ = ["JinaSearchEngine", "_build_body"]
