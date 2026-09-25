"""Search engine registry.

Engines are imported lazily so that a missing key or extra never breaks import
of ``enrichfold``. ``get_search_engine(name)`` returns a class on demand.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from enrichfold.search.engines.base import SearchEngine

# Lazy registry: name -> import-and-return-class function.
_REGISTRY: dict[str, Callable[[], type[SearchEngine]]] = {
    "browserbase": lambda: (
        __import__(
            "enrichfold.search.engines.browserbase_search",
            fromlist=["BrowserbaseSearchEngine"],
        ).BrowserbaseSearchEngine
    ),
    "serper": lambda: (
        __import__(
            "enrichfold.search.engines.serper_search", fromlist=["SerperSearchEngine"]
        ).SerperSearchEngine
    ),
    "exa": lambda: (
        __import__(
            "enrichfold.search.engines.exa_search", fromlist=["ExaSearchEngine"]
        ).ExaSearchEngine
    ),
    "parallel": lambda: (
        __import__(
            "enrichfold.search.engines.parallel_search",
            fromlist=["ParallelSearchEngine"],
        ).ParallelSearchEngine
    ),
    "you": lambda: (
        __import__(
            "enrichfold.search.engines.you_search", fromlist=["YouSearchEngine"]
        ).YouSearchEngine
    ),
    "tavily": lambda: (
        __import__(
            "enrichfold.search.engines.tavily_search", fromlist=["TavilySearchEngine"]
        ).TavilySearchEngine
    ),
    "linkup": lambda: (
        __import__(
            "enrichfold.search.engines.linkup_search", fromlist=["LinkupSearchEngine"]
        ).LinkupSearchEngine
    ),
    "seltz": lambda: (
        __import__(
            "enrichfold.search.engines.seltz_search", fromlist=["SeltzSearchEngine"]
        ).SeltzSearchEngine
    ),
    "tinyfish": lambda: (
        __import__(
            "enrichfold.search.engines.tinyfish_search",
            fromlist=["TinyFishSearchEngine"],
        ).TinyFishSearchEngine
    ),
    "nimble": lambda: (
        __import__(
            "enrichfold.search.engines.nimble_search", fromlist=["NimbleSearchEngine"]
        ).NimbleSearchEngine
    ),
    "duckduckgo": lambda: (
        __import__(
            "enrichfold.search.engines.duckduckgo", fromlist=["DuckDuckGoSearchEngine"]
        ).DuckDuckGoSearchEngine
    ),
}

# User-facing aliases resolved at registry lookup.
SEARCH_ENGINE_ALIASES: dict[str, str] = {}


def register(name: str, loader: Callable[[], type[SearchEngine]]) -> None:
    _REGISTRY[name] = loader


def register_alias(alias: str, canonical: str) -> None:
    """Register ``alias`` as a user-facing name for canonical engine ``canonical``."""
    SEARCH_ENGINE_ALIASES[alias] = canonical


def resolve_alias(name: str) -> str:
    """Return the canonical engine name for ``name``, or ``name`` if no alias."""
    return SEARCH_ENGINE_ALIASES.get(name, name)


def get_search_engine(name: str) -> type[SearchEngine]:
    """Return the search engine class for ``name`` (alias-resolved). Raises KeyError."""
    canonical = resolve_alias(name)
    try:
        loader = _REGISTRY[canonical]
    except KeyError as exc:
        raise KeyError(
            f"unknown search engine: {name!r} (resolved to {canonical!r}). "
            f"known: {sorted(_REGISTRY)}"
        ) from exc
    return loader()


def list_search_engine_names() -> list[str]:
    return sorted(_REGISTRY)


# "ddg" resolves to the keyless DuckDuckGo default.
register_alias("ddg", "duckduckgo")


__all__ = [
    "SEARCH_ENGINE_ALIASES",
    "get_search_engine",
    "list_search_engine_names",
    "register",
    "register_alias",
    "resolve_alias",
]
