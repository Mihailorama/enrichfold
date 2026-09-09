"""Keenable web-search adapter for :class:`ResearchEngine`."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .models import Claim, Entity
from .research import ProviderOutput

_Query = str | Callable[[Entity], str]
_Mapper = Callable[[Entity, tuple[Mapping[str, Any], ...]], Iterable[Claim]]


class KeenableProvider:
    """Run one Keenable search and let the caller turn its sources into claims."""

    def __init__(
        self,
        query: _Query,
        map_results: _Mapper,
        *,
        api_key: str | None = None,
        max_results: int = 10,
        timeout: float = 30.0,
        base_url: str = "https://api.keenable.ai",
    ) -> None:
        key = (api_key or os.getenv("KEENABLE_API_KEY", "")).strip()
        if not key:
            raise ValueError("KeenableProvider requires api_key or KEENABLE_API_KEY")
        if not 1 <= max_results <= 50:
            raise ValueError("max_results must be between 1 and 50")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._query = query
        self._map_results = map_results
        self._api_key = key
        self._max_results = max_results
        self._timeout = timeout
        self._url = f"{base_url.rstrip('/')}/v1/search"

    def research(self, entity: Entity) -> ProviderOutput:
        query = (self._query(entity) if callable(self._query) else self._query).strip()
        if not query:
            raise ValueError("Keenable query must be non-empty")
        request = Request(
            self._url,
            data=json.dumps({"query": query, "max_results": self._max_results}).encode(),
            headers={"Content-Type": "application/json", "X-API-Key": self._api_key},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                data = json.load(response)
        except HTTPError as error:
            try:
                payload = json.loads(error.read())
                detail = payload.get("message") or payload.get("error")
            except (AttributeError, json.JSONDecodeError):
                detail = None
            raise RuntimeError(f"Keenable HTTP {error.code}: {detail or error.reason}") from None

        results = data.get("results") if isinstance(data, Mapping) else None
        if not isinstance(results, list) or any(not isinstance(result, Mapping) for result in results):
            raise ValueError("invalid Keenable response: results must be a list of objects")
        mapped_results = tuple(results)
        return ProviderOutput(
            claims=self._map_results(entity, mapped_results),
            usage_units=1,
            metadata={"query": query, "result_count": str(len(mapped_results))},
        )


__all__ = ["KeenableProvider"]
