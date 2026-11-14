"""Base interface for every search engine.

Each engine subclasses ``SearchEngine``, declares its name, whether it needs an
API key, and an estimated per-call cost, then implements the async ``_search``
method. The public ``search`` wrapper handles timing, uniform error wrapping,
and stamping ``rank`` + ``engine`` onto each returned hit.

Adding a new search engine
--------------------------
1. Create ``src/enrichfold/search/engines/<name>.py`` with a class
   ``class XSearchEngine(SearchEngine):``.
2. Set ``NAME``, ``REQUIRES_API_KEY``, ``ESTIMATED_COST_USD``.
3. Implement ``async def _search(self, query, opts) -> list[SearchHit]``.
4. Register it in ``search/engines/__init__.py``.
5. Add tests under ``tests/test_search_<name>.py``.
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Any, ClassVar

from enrichfold.search.options import SearchOptions
from enrichfold.search.types import SearchHit

logger = logging.getLogger(__name__)

_KEY_IN_URL = re.compile(r"(api_key=)[^&\s\"']+")


class _RedactApiKey(logging.Filter):
    """httpx logs every request URL at INFO; SerpAPI and Scrapingdog take the key
    in the query string, so mask it there."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "api_key=" in message:
            record.msg, record.args = _KEY_IN_URL.sub(r"\1***", message), ()
        return True


if not any(isinstance(f, _RedactApiKey) for f in logging.getLogger("httpx").filters):
    logging.getLogger("httpx").addFilter(_RedactApiKey())


@dataclass(frozen=True)
class SearchEngineError(Exception):
    """Raised when a search engine fails. Wraps the original exception."""

    engine: str
    message: str

    def __str__(self) -> str:
        return f"[{self.engine}] {self.message}"


def check_response(response: Any) -> None:
    """Raise on an HTTP error with the status and the start of the body.

    Never ``httpx.Response.raise_for_status()``: its message carries the full
    request URL, which holds the API key for query-string-keyed vendors.
    """
    if response.is_error:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")


class SearchEngine(ABC):
    """Abstract base for every search engine."""

    NAME: ClassVar[str] = ""
    REQUIRES_API_KEY: ClassVar[bool] = True
    ESTIMATED_COST_USD: ClassVar[float] = 0.0

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def search(
        self, query: str, opts: SearchOptions | None = None
    ) -> list[SearchHit]:
        """Public entry. Handles timing, error wrapping, and rank/engine stamping."""
        opts = opts or SearchOptions()
        started = time.monotonic()
        try:
            hits = await self._search(query, opts)
        except SearchEngineError:
            raise
        except Exception as exc:
            logger.warning("%s search failed for %r: %s", self.NAME, query, exc)
            raise SearchEngineError(self.NAME, str(exc)) from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.debug(
            "engine=%s query=%r hits=%d elapsed_ms=%d",
            self.NAME,
            query,
            len(hits),
            elapsed_ms,
        )
        return [
            replace(hit, rank=position, engine=self.NAME)
            for position, hit in enumerate(hits)
        ]

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------
    @abstractmethod
    async def _search(self, query: str, opts: SearchOptions) -> list[SearchHit]:
        """Engine-specific search. ``rank`` / ``engine`` are stamped by the wrapper."""

    def is_available(self) -> bool:
        """Whether this engine can run right now (API key present when required)."""
        return not self.REQUIRES_API_KEY or bool(self.api_key)


__all__ = ["SearchEngine", "SearchEngineError", "check_response"]
