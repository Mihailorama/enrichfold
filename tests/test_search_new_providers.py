"""Offline HTTP contracts for Enrichfold search providers."""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from enrichfold.search.engines import get_search_engine
from enrichfold.search.options import SearchOptions


@pytest.mark.parametrize(
    ("name", "method", "url", "payload", "expected_snippet"),
    [
        (
            "browserbase",
            "POST",
            "https://api.browserbase.com/v1/search",
            {"results": [{"url": "https://a.test", "title": "A"}]},
            "",
        ),
        (
            "parallel",
            "POST",
            "https://api.parallel.ai/v1/search",
            {
                "results": [
                    {
                        "url": "https://a.test",
                        "title": "A",
                        "excerpts": ["Parallel excerpt"],
                    }
                ]
            },
            "Parallel excerpt",
        ),
        (
            "you",
            "POST",
            "https://ydc-index.io/v1/search",
            {
                "results": {
                    "web": [
                        {
                            "url": "https://a.test",
                            "title": "A",
                            "description": "You excerpt",
                        }
                    ]
                }
            },
            "You excerpt",
        ),
        (
            "tavily",
            "POST",
            "https://api.tavily.com/search",
            {
                "results": [
                    {"url": "https://a.test", "title": "A", "content": "Tavily excerpt"}
                ]
            },
            "Tavily excerpt",
        ),
        (
            "linkup",
            "POST",
            "https://api.linkup.so/v1/search",
            {
                "results": [
                    {"url": "https://a.test", "name": "A", "content": "Linkup excerpt"}
                ]
            },
            "Linkup excerpt",
        ),
        (
            "seltz",
            "POST",
            "https://api.seltz.ai/v1/search",
            {"documents": [{"url": "https://a.test", "content": "Seltz excerpt"}]},
            "Seltz excerpt",
        ),
        (
            "tinyfish",
            "GET",
            "https://api.search.tinyfish.ai?query=test",
            {
                "results": [
                    {
                        "url": "https://a.test",
                        "title": "A",
                        "snippet": "TinyFish excerpt",
                    }
                ]
            },
            "TinyFish excerpt",
        ),
        (
            "nimble",
            "POST",
            "https://sdk.nimbleway.com/v2/search",
            {
                "results": [
                    {
                        "url": "https://a.test",
                        "title": "A",
                        "description": "Nimble excerpt",
                    }
                ]
            },
            "Nimble excerpt",
        ),
    ],
)
async def test_search_adapter(
    httpx_mock: HTTPXMock,
    name: str,
    method: str,
    url: str,
    payload: dict,
    expected_snippet: str,
) -> None:
    httpx_mock.add_response(method=method, url=url, json=payload)
    hits = await get_search_engine(name)(api_key="test-key").search(
        "test", SearchOptions(count=1)
    )
    assert [(hit.url, hit.snippet, hit.engine, hit.rank) for hit in hits] == [
        ("https://a.test", expected_snippet, name, 0)
    ]
    request = httpx_mock.get_requests()[0]
    if name == "parallel":
        assert json.loads(request.content)["objective"] == "test"
    if name == "linkup":
        assert json.loads(request.content)["outputType"] == "searchResults"
    if name == "browserbase":
        assert json.loads(request.content)["numResults"] == 1
