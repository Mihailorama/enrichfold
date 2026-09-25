"""Map web search results into evidence-backed research claims."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from enrichfold.models import Claim, Entity
from enrichfold.research import ProviderOutput
from enrichfold.search import SearchOptions, search


class WebSearchProvider:
    """Search configured engines; the caller maps sources to claims."""

    def __init__(
        self,
        query: str | Callable[[Entity], str],
        map_results: Callable[[Entity, tuple[Mapping[str, Any], ...]], Iterable[Claim]],
        *,
        engines: tuple[str, ...] | None = None,
        count: int = 10,
        usage_units: float = 0.0,
    ) -> None:
        if count < 1:
            raise ValueError("count must be positive")
        if usage_units < 0:
            raise ValueError("usage_units must be non-negative")
        self._query = query
        self._map_results = map_results
        self._engines = engines
        self._count = count
        self._usage_units = usage_units

    def research(self, entity: Entity) -> ProviderOutput:
        query = (self._query(entity) if callable(self._query) else self._query).strip()
        if not query:
            raise ValueError("search query must be non-empty")
        results = asyncio.run(
            search(query, SearchOptions(count=self._count, engines=self._engines))
        )
        acquired_at = datetime.now(timezone.utc).isoformat()
        sources = tuple(
            {
                "url": result.url,
                "title": result.title,
                "description": result.snippet,
                "engines": result.engines,
                "acquired_at": acquired_at,
            }
            for result in results
        )
        return ProviderOutput(
            claims=self._map_results(entity, sources),
            usage_units=self._usage_units,
            metadata={"query": query, "result_count": str(len(sources))},
        )
