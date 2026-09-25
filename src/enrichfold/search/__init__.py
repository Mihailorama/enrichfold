"""Multi-engine web search with Reciprocal Rank Fusion.

``search(query)`` fans out to several SERP engines concurrently and merges their
ranked lists with RRF, producing deduped results with explainable per-engine
score breakdowns. Scrapefold delegates its compatibility ``search()`` API here;
query in, ranked results out.
"""

from __future__ import annotations

from enrichfold.search.api import search
from enrichfold.search.engines import get_search_engine, list_search_engine_names
from enrichfold.search.engines.base import SearchEngine, SearchEngineError
from enrichfold.search.fusion import fuse, reciprocal_rank_fusion
from enrichfold.search.options import SearchOptions
from enrichfold.search.types import SearchHit, SearchResult

__all__ = [
    "SearchEngine",
    "SearchEngineError",
    "SearchHit",
    "SearchOptions",
    "SearchResult",
    "fuse",
    "get_search_engine",
    "list_search_engine_names",
    "reciprocal_rank_fusion",
    "search",
]
