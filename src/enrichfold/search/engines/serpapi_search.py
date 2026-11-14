"""Google and Yandex through SerpAPI: ``GET https://serpapi.com/search``.

Reads ``SERPAPI_API_KEY`` (or ai-utils' ``SERAPI_API_KEY``).

``serpapi_yandex`` copies ai-utils' ``perform_yandex_search`` parameters:
``engine=yandex``, ``text``, ``yandex_domain=yandex.ru``, ``lr=1``, ``lang=ru``,
``no_cache=true``. ``opts.language`` replaces ``lang``; Yandex has no page-size
parameter, so hits are cut to ``opts.count``.

``serpapi_google`` (not used by ai-utils) sends ``engine=google``, ``q``,
``num`` and, when set, ``gl`` / ``hl``.

Both take ``serpapi_*`` extras, which override the defaults above. A SerpAPI
``error`` in the reply raises, except "hasn't returned any results", which is
an empty result.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

import httpx

from enrichfold.search.engines.base import SearchEngine, check_response
from enrichfold.search.options import SearchOptions, strip_extra_prefix
from enrichfold.search.types import SearchHit

_ENDPOINT = "https://serpapi.com/search"


class _SerpApiEngine(SearchEngine):
    REQUIRES_API_KEY = True
    ESTIMATED_COST_USD = 0.01
    ENGINE: ClassVar[str] = ""

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(
            api_key or os.getenv("SERPAPI_API_KEY") or os.getenv("SERAPI_API_KEY")
        )

    def _params(self, query: str, opts: SearchOptions) -> dict[str, Any]:
        raise NotImplementedError

    def build_params(self, query: str, opts: SearchOptions) -> dict[str, Any]:
        params = {"engine": self.ENGINE, **self._params(query, opts), "output": "json"}
        params.update(strip_extra_prefix(opts.extra, "serpapi_"))
        return params

    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        params = {**self.build_params(query, opts), "api_key": self.api_key or ""}
        async with httpx.AsyncClient(timeout=float(opts.timeout_s)) as client:
            response = await client.get(_ENDPOINT, params=params)
        check_response(response)
        data = response.json()
        error = data.get("error")
        if error:
            if "hasn't returned any results" in str(error):
                return []
            raise RuntimeError(f"SerpAPI error: {str(error)[:200]}")
        return [
            SearchHit(
                url=item["link"],
                title=item.get("title") or "",
                snippet=item.get("snippet") or "",
                raw=item,
            )
            for item in data.get("organic_results") or []
            if isinstance(item, dict) and item.get("link")
        ][: opts.count]


class SerpApiYandexSearchEngine(_SerpApiEngine):
    NAME = "serpapi_yandex"
    ENGINE = "yandex"

    def _params(self, query: str, opts: SearchOptions) -> dict[str, Any]:
        return {
            "text": query,
            "yandex_domain": "yandex.ru",
            "lr": "1",
            "lang": opts.language or "ru",
            "no_cache": "true",
        }


class SerpApiGoogleSearchEngine(_SerpApiEngine):
    NAME = "serpapi_google"
    ENGINE = "google"

    def _params(self, query: str, opts: SearchOptions) -> dict[str, Any]:
        params: dict[str, Any] = {"q": query, "num": opts.count}
        if opts.country is not None:
            params["gl"] = opts.country
        if opts.language is not None:
            params["hl"] = opts.language
        return params


__all__ = ["SerpApiGoogleSearchEngine", "SerpApiYandexSearchEngine"]
