"""Twingly News Search engine. HTTP is mocked with a reply shaped like the live
response captured on 2026-11-27 (field names real, values made up)."""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from enrichfold.search.engines import get_search_engine
from enrichfold.search.engines.base import SearchEngineError
from enrichfold.search.options import SearchOptions

_URL = "https://data.twingly.net/news/b/search/v1/search"

_REPLY = {
    "number_of_documents": 3,
    "number_of_documents_estimated_total": 58181,
    "documents": [
        {
            "article_id": 1,
            "url": "https://news.test/a",
            "title": "Acme raises prices",
            "text": "Acme said on Monday " + "x" * 400,
            "summary": "",
            "published_at": "2026-11-27T19:36:09Z",
            "crawled_at": "2026-11-27T19:50:07Z",
            "language_code": "en",
            "location_code": "us",
            "site_name": "news.test",
            "topics_and_entities": {"topics": [], "organization_entities": []},
        },
        {"article_id": 2, "title": "no url"},
        {
            "article_id": 3,
            "url": "https://news.test/b",
            "title": "Second",
            "summary": "Short summary",
        },
    ],
}


async def test_twingly_sends_documented_body_and_maps_documents(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(method="POST", url=_URL, json=_REPLY)

    hits = await get_search_engine("twingly")(api_key="tw_k").search(
        "Acme",
        SearchOptions(
            count=2,
            country="US",
            extra={"twingly_timestamp": {"since": "2026-11-20T00:00:00Z"}},
        ),
    )

    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "apikey tw_k"
    assert json.loads(request.content) == {
        "all": ["Acme"],
        "size": 2,
        "locations": ["us"],
        "timestamp": {"since": "2026-11-20T00:00:00Z"},
    }
    assert [(h.url, h.title, h.engine, h.rank) for h in hits] == [
        ("https://news.test/a", "Acme raises prices", "twingly", 0),
        ("https://news.test/b", "Second", "twingly", 1),
    ]
    assert hits[0].snippet.startswith("Acme said") and len(hits[0].snippet) == 300
    assert hits[1].snippet == "Short summary"
    assert hits[0].raw["published_at"] == "2026-11-27T19:36:09Z"


async def test_twingly_invalid_key_raises_without_key(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_URL,
        status_code=401,
        json={"status": 401, "code": 40101, "error": "Invalid API key"},
    )
    with pytest.raises(SearchEngineError) as err:
        await get_search_engine("twingly")(api_key="secret_k").search("q")
    assert "HTTP 401" in str(err.value) and "secret_k" not in str(err.value)


def test_twingly_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWINGLY_API_KEY", "env_k")
    engine = get_search_engine("twingly")()
    assert engine.api_key == "env_k" and engine.is_available()
