"""Tests for KeenableSearchEngine. All HTTP is mocked; no live Keenable calls."""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from enrichfold.search.engines import get_search_engine
from enrichfold.search.engines.base import SearchEngineError
from enrichfold.search.options import SearchOptions

_KEYED = "https://api.keenable.ai/v1/search"
_PUBLIC = "https://api.keenable.ai/v1/search/public"
_PAYLOAD = {
    "query": "q",
    "mode": "pro",
    "results": [
        {
            "title": "A",
            "url": "https://a.test/x",
            "description": "",
            "snippet": "Keenable excerpt",
            "published_at": "2026-10-30T00:00:00Z",
            "acquired_at": "2026-11-03T08:57:22Z",
        },
        {"title": "no url"},
    ],
}


async def test_keyed_search_maps_hits_and_forwards_filters(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_KEYED, json=_PAYLOAD)
    opts = SearchOptions(
        count=99,
        extra={"keenable_site": "a.test", "keenable_published_after": "7d"},
    )

    hits = await get_search_engine("keenable")(api_key="keen_test").search("q", opts)

    request = httpx_mock.get_requests()[0]
    assert request.headers["x-api-key"] == "keen_test"
    assert json.loads(request.content) == {
        "query": "q",
        "max_results": 50,
        "site": "a.test",
        "published_after": "7d",
    }
    assert [(h.url, h.title, h.snippet, h.engine, h.rank) for h in hits] == [
        ("https://a.test/x", "A", "Keenable excerpt", "keenable", 0)
    ]
    assert hits[0].raw["published_at"] == "2026-10-30T00:00:00Z"
    assert hits[0].raw["acquired_at"] == "2026-11-03T08:57:22Z"


async def test_keyless_uses_public_endpoint(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)
    httpx_mock.add_response(method="POST", url=_PUBLIC, json=_PAYLOAD)
    engine = get_search_engine("keenable")()

    hits = await engine.search("q", SearchOptions(count=3))

    request = httpx_mock.get_requests()[0]
    assert "x-api-key" not in request.headers
    assert request.headers["x-keenable-title"] == "enrichfold"
    assert json.loads(request.content)["max_results"] == 3
    assert len(hits) == 1
    assert not engine.is_available()  # keyless only when selected explicitly


async def test_http_error_raises_search_engine_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_KEYED, status_code=402, json={})

    with pytest.raises(SearchEngineError) as exc_info:
        await get_search_engine("keenable")(api_key="keen_test").search("q")

    assert exc_info.value.engine == "keenable"
