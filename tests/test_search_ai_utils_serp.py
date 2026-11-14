"""SERP engines ported from ai-utils: Jina, SerpAPI Google/Yandex, Scrapingdog,
Outscraper. All HTTP is mocked with payloads shaped like the vendors' documented
replies; request parameters are the ones ai-utils sends."""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from enrichfold.search.engines import get_search_engine
from enrichfold.search.engines.base import SearchEngineError
from enrichfold.search.options import SearchOptions


def _params(httpx_mock: HTTPXMock) -> dict[str, str]:
    return dict(httpx_mock.get_requests()[0].url.params)


async def test_jina_sends_ai_utils_body_and_maps_json(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://s.jina.ai/search",
        json={
            "code": 200,
            "status": 20000,
            "data": [
                {
                    "title": "Acme",
                    "url": "https://acme.test/",
                    "description": "Acme makes anvils",
                    "content": "# Acme\nfull page markdown",
                    "links": {"About": "https://acme.test/about"},
                },
                {"title": "second", "url": "https://two.test/", "description": ""},
            ],
        },
    )

    hits = await get_search_engine("jina")(api_key="jina_k").search(
        'Acme "anvils"', SearchOptions(count=1)
    )

    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "Bearer jina_k"
    assert request.headers["accept"] == "application/json"
    assert json.loads(request.content) == {
        "q": "Acme anvils",
        "withGeneratedAlt": True,
        "withLinksSummary": True,
        "withImagesSummary": True,
    }
    assert [(h.url, h.title, h.snippet, h.engine) for h in hits] == [
        ("https://acme.test/", "Acme", "Acme makes anvils", "jina")
    ]
    assert hits[0].raw["content"].startswith("# Acme")


def test_jina_reads_ai_utils_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    monkeypatch.setenv("JINAAI_API_KEY", "legacy")
    assert get_search_engine("jina")().api_key == "legacy"


_SERPAPI_ORGANIC = {
    "search_metadata": {"status": "Success"},
    "organic_results": [
        {"position": 1, "title": "Яндекс", "link": "https://ya.test/", "snippet": "s1"},
        {"position": 2, "title": "no link"},
        {"position": 3, "title": "Two", "link": "https://two.test/", "snippet": "s2"},
    ],
}


async def test_serpapi_yandex_uses_ai_utils_params(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", json=_SERPAPI_ORGANIC)

    hits = await get_search_engine("serpapi_yandex")(api_key="serp_k").search("q")

    assert _params(httpx_mock) == {
        "engine": "yandex",
        "text": "q",
        "yandex_domain": "yandex.ru",
        "lr": "1",
        "lang": "ru",
        "no_cache": "true",
        "output": "json",
        "api_key": "serp_k",
    }
    assert httpx_mock.get_requests()[0].url.path == "/search"
    assert [(h.url, h.rank, h.engine) for h in hits] == [
        ("https://ya.test/", 0, "serpapi_yandex"),
        ("https://two.test/", 1, "serpapi_yandex"),
    ]


async def test_serpapi_google_params_and_extras(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", json=_SERPAPI_ORGANIC)
    opts = SearchOptions(
        count=5, country="de", language="en", extra={"serpapi_location": "Berlin"}
    )

    hits = await get_search_engine("serpapi_google")(api_key="serp_k").search("q", opts)

    assert _params(httpx_mock) == {
        "engine": "google",
        "q": "q",
        "num": "5",
        "gl": "de",
        "hl": "en",
        "location": "Berlin",
        "output": "json",
        "api_key": "serp_k",
    }
    assert len(hits) == 2


async def test_serpapi_error_raises_but_no_results_is_empty(
    httpx_mock: HTTPXMock,
) -> None:
    engine = get_search_engine("serpapi_google")(api_key="serp_k")
    httpx_mock.add_response(
        method="GET",
        json={"error": "Google hasn't returned any results for this query."},
    )
    assert await engine.search("q") == []

    httpx_mock.add_response(
        method="GET", status_code=401, json={"error": "Invalid API key."}
    )
    with pytest.raises(SearchEngineError, match="Invalid API key"):
        await engine.search("q")


def test_serpapi_reads_ai_utils_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.setenv("SERAPI_API_KEY", "legacy")
    assert get_search_engine("serpapi_yandex")().api_key == "legacy"


async def test_scrapingdog_uses_ai_utils_params(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        json={
            "organic_results": [
                {
                    "title": "Acme",
                    "displayed_link": "acme.test",
                    "snippet": "anvils",
                    "link": "https://acme.test/",
                    "rank": 1,
                }
            ]
        },
    )

    hits = await get_search_engine("scrapingdog")(api_key="dog_k").search(
        "q", SearchOptions(count=20)
    )

    request = httpx_mock.get_requests()[0]
    assert f"{request.url.host}{request.url.path}" == "api.scrapingdog.com/google"
    assert _params(httpx_mock) == {
        "query": "q",
        "results": "20",
        "page": "0",
        "country": "us",
        "api_key": "dog_k",
    }
    assert [(h.url, h.title, h.snippet) for h in hits] == [
        ("https://acme.test/", "Acme", "anvils")
    ]


async def test_outscraper_uses_ai_utils_params_and_maps_v3(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="GET",
        json={
            "id": "req-1",
            "status": "Success",
            "data": [
                [
                    {
                        "query": "q",
                        "position": 1,
                        "title": "Acme",
                        "link": "https://acme.test/",
                        "description": "Acme makes anvils",
                    },
                    {
                        "position": 2,
                        "title": "B",
                        "link": "https://b.test/",
                        "snippet": "b",
                    },
                ]
            ],
        },
    )

    hits = await get_search_engine("outscraper")(api_key="out_k").search("q")

    request = httpx_mock.get_requests()[0]
    assert request.url.path == "/google-search-v3"
    assert request.headers["x-api-key"] == "out_k"
    assert _params(httpx_mock) == {
        "query": "q",
        "pagesPerQuery": "1",
        "language": "en",
        "async": "false",
    }
    assert [(h.url, h.snippet, h.rank) for h in hits] == [
        ("https://acme.test/", "Acme makes anvils", 0),
        ("https://b.test/", "b", 1),
    ]


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, {"id": "req-1", "status": "Pending"}),
        (202, {"id": "req-1", "status": "Pending"}),
        (200, {"error": True, "errorMessage": "Not enough credits"}),
    ],
)
async def test_outscraper_pending_or_error_reply_raises(
    httpx_mock: HTTPXMock, status: int, body: dict
) -> None:
    httpx_mock.add_response(method="GET", status_code=status, json=body)
    with pytest.raises(SearchEngineError) as exc_info:
        await get_search_engine("outscraper")(api_key="k").search("q")
    assert exc_info.value.engine == "outscraper"


@pytest.mark.parametrize(
    "name", ["jina", "serpapi_google", "serpapi_yandex", "scrapingdog", "outscraper"]
)
def test_registered_and_keyed(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    for env in (
        "JINA_API_KEY",
        "JINAAI_API_KEY",
        "SERPAPI_API_KEY",
        "SERAPI_API_KEY",
        "SCRAPINGDOG_API_KEY",
        "OUTSCRAPER_API_KEY",
    ):
        monkeypatch.delenv(env, raising=False)
    cls = get_search_engine(name)
    assert not cls().is_available()
    assert cls(api_key="k").is_available()


_SECRET = "sk-secret-123"


@pytest.mark.parametrize(
    "name", ["jina", "serpapi_google", "serpapi_yandex", "scrapingdog", "outscraper"]
)
@pytest.mark.parametrize(
    ("status", "kwargs"),
    [
        (401, {"json": {"message": "Invalid API key"}}),
        (429, {"text": "Too Many Requests"}),
        (502, {"text": "<html>Bad Gateway</html>"}),
    ],
)
async def test_http_errors_keep_status_and_never_leak_key(
    httpx_mock: HTTPXMock,
    caplog: pytest.LogCaptureFixture,
    name: str,
    status: int,
    kwargs: dict,
) -> None:
    httpx_mock.add_response(status_code=status, **kwargs)

    with caplog.at_level("DEBUG"), pytest.raises(SearchEngineError) as exc_info:
        await get_search_engine(name)(api_key=_SECRET).search("q")

    message = str(exc_info.value)
    assert exc_info.value.engine == name
    assert str(status) in message
    assert _SECRET not in message
    assert _SECRET not in caplog.text
