"""Optional Scrapefold page-fetch adapter for provenance-aware research."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from .models import Claim, Entity
from .research import ProviderOutput

_Query = str | Callable[[Entity], str]


class ScrapefoldScrapeProvider:
    """Fetch an entity URL through Scrapefold; the caller maps content to claims."""

    def __init__(
        self,
        url: _Query,
        map_result: Callable[[Entity, Mapping[str, Any]], Iterable[Claim]],
        *,
        engines: tuple[str, ...] | None = None,
        usage_units: float = 0.0,
    ) -> None:
        if usage_units < 0:
            raise ValueError("usage_units must be non-negative")
        self._url = url
        self._map_result = map_result
        self._engines = engines
        self._usage_units = usage_units

    def research(self, entity: Entity) -> ProviderOutput:
        from scrapefold import ScrapeOptions, scrape

        url = (self._url(entity) if callable(self._url) else self._url).strip()
        if not url:
            raise ValueError("Scrapefold URL must be non-empty")
        result = asyncio.run(scrape(url, ScrapeOptions(engines=self._engines)))
        source = {
            "url": result.url,
            "text": result.text,
            "markdown": result.markdown,
            "html": result.html,
            "json": result.json,
            "engine": result.engine,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }
        return ProviderOutput(
            claims=self._map_result(entity, source),
            usage_units=self._usage_units,
            metadata={"url": result.url, "engine": result.engine},
        )


__all__ = ["ScrapefoldScrapeProvider"]
