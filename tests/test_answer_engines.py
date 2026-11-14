"""Answer engines: recorded replies shaped like each vendor's documented response
and the requests ai-utils sends. No network: the call is injected, except one
test of the default httpx transport."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from enrichfold.search import (
    AnswerResult,
    Citation,
    GeminiAnswerEngine,
    OpenAIAnswerEngine,
    OpenRouterAnswerEngine,
    PerplexityAnswerEngine,
)
from enrichfold.search.answer import GEMINI_PROMPT, OPENAI_SYSTEM_PROMPT
from enrichfold.search.engines.base import SearchEngineError


class Recorder:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((url, body))
        return self.reply


async def test_perplexity_request_and_citations() -> None:
    call = Recorder(
        {
            "model": "sonar-pro",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": " Acme was founded in 1990 [1]. ",
                    }
                }
            ],
            "citations": ["https://acme.test/about", "https://news.test/a"],
            "search_results": [
                {
                    "title": "About Acme",
                    "url": "https://acme.test/about",
                    "date": "2026-01-02",
                    "snippet": "Founded 1990",
                },
                {"title": "News", "url": "https://news.test/a", "snippet": ""},
                {"title": "dup", "url": "https://acme.test/about"},
            ],
        }
    )

    result = await PerplexityAnswerEngine("sonar-pro", call=call).answer("Acme founded")

    url, body = call.calls[0]
    assert url == "https://api.perplexity.ai/chat/completions"
    assert body == {
        "model": "sonar-pro",
        "messages": [{"role": "user", "content": "Acme founded"}],
        "max_tokens": 8000,
        "temperature": 0.05,
    }
    assert result.text == "Acme was founded in 1990 [1]."
    assert result.citations == (
        Citation("https://acme.test/about", "About Acme", "Founded 1990"),
        Citation("https://news.test/a", "News", ""),
    )
    assert (result.engine, result.model) == ("perplexity", "sonar-pro")


async def test_perplexity_falls_back_to_bare_citations() -> None:
    call = Recorder(
        {"choices": [{"message": {"content": "x"}}], "citations": ["https://a.test/"]}
    )
    result = await PerplexityAnswerEngine("sonar", call=call).answer("q")
    assert result.citations == (Citation("https://a.test/"),)


async def test_openrouter_appends_online_and_reads_annotations() -> None:
    call = Recorder(
        {
            "choices": [
                {
                    "message": {
                        "content": "Acme makes anvils.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url_citation": {
                                    "url": "https://acme.test/",
                                    "title": "Acme",
                                    "content": "We make anvils",
                                    "start_index": 0,
                                    "end_index": 18,
                                },
                            }
                        ],
                    }
                }
            ]
        }
    )

    engine = OpenRouterAnswerEngine("google/gemini-3.8-flash", call=call)
    result = await engine.answer("Acme")

    url, body = call.calls[0]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert body["model"] == "google/gemini-3.8-flash:online"
    assert (body["max_tokens"], body["temperature"]) == (4000, 0.0)
    prompt = body["messages"][0]["content"]
    assert prompt.startswith(
        "Please provide comprehensive information about the following:"
    )
    assert "\nAcme\n\n" in prompt
    assert result.citations == (
        Citation("https://acme.test/", "Acme", "We make anvils"),
    )
    assert OpenRouterAnswerEngine("x/y:online", call=call).model == "x/y:online"


async def test_openai_responses_web_search() -> None:
    call = Recorder(
        {
            "id": "resp_1",
            "object": "response",
            "output": [
                {"type": "web_search_call", "id": "ws_1", "status": "completed"},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Acme makes anvils (acme.test).",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "start_index": 18,
                                    "end_index": 29,
                                    "url": "https://acme.test/?utm_source=openai",
                                    "title": "Acme",
                                }
                            ],
                        }
                    ],
                },
            ],
        }
    )

    result = await OpenAIAnswerEngine("gpt-5.2", call=call).answer("Acme")

    url, body = call.calls[0]
    assert url == "https://api.openai.com/v1/responses"
    assert body == {
        "model": "gpt-5.2",
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": OPENAI_SYSTEM_PROMPT}],
            },
            {"role": "user", "content": [{"type": "input_text", "text": "Acme"}]},
        ],
        "tools": [{"type": "web_search"}],
        "temperature": 0.1,
        "max_output_tokens": 10000,
    }
    assert result.text == "Acme makes anvils (acme.test)."
    assert result.citations == (
        Citation("https://acme.test/?utm_source=openai", "Acme"),
    )


async def test_gemini_grounding() -> None:
    call = Recorder(
        {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": "thinking", "thought": True},
                            {"text": "Acme "},
                            {"text": "makes anvils."},
                        ],
                    },
                    "groundingMetadata": {
                        "webSearchQueries": ["Acme"],
                        "groundingChunks": [
                            {
                                "web": {
                                    "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
                                    "title": "acme.test",
                                }
                            }
                        ],
                        "groundingSupports": [
                            {
                                "segment": {
                                    "startIndex": 0,
                                    "endIndex": 18,
                                    "text": "Acme makes anvils.",
                                },
                                "groundingChunkIndices": [0],
                            }
                        ],
                    },
                }
            ]
        }
    )

    result = await GeminiAnswerEngine("gemini-3.8-flash", call=call).answer("Acme")

    url, body = call.calls[0]
    assert url.endswith("/v1beta/models/gemini-3.8-flash:generateContent")
    assert body["contents"][0]["parts"][0]["text"] == GEMINI_PROMPT.replace(
        "{query}", "Acme"
    )
    assert body["tools"] == [{"googleSearch": {}}]
    assert body["generationConfig"] == {
        "responseMimeType": "text/plain",
        "temperature": 0.1,
    }
    assert result == AnswerResult(
        "Acme makes anvils.",
        (
            Citation(
                "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
                "acme.test",
            ),
        ),
        "gemini",
        "gemini-3.8-flash",
        call.reply,
    )


async def test_empty_answer_and_call_errors_raise() -> None:
    empty = Recorder({"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(SearchEngineError, match="returned no content"):
        await PerplexityAnswerEngine("sonar-pro", call=empty).answer("q")

    async def failing(url: str, body: dict[str, Any]) -> dict[str, Any]:
        raise TimeoutError("slow")

    with pytest.raises(SearchEngineError) as exc_info:
        await OpenAIAnswerEngine("gpt-5.2", call=failing).answer("q")
    assert exc_info.value.engine == "openai"


@pytest.mark.parametrize(
    "cls",
    [
        PerplexityAnswerEngine,
        GeminiAnswerEngine,
        OpenAIAnswerEngine,
        OpenRouterAnswerEngine,
    ],
)
def test_model_is_required(cls: type) -> None:
    with pytest.raises(ValueError, match="model is required"):
        cls("")


async def test_default_transport_sends_key_from_env(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g_k")
    httpx_mock.add_response(
        method="POST",
        url="https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
        json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
    )

    result = await GeminiAnswerEngine("gemini-3.8-flash").answer("q")

    request = httpx_mock.get_requests()[0]
    assert request.headers["x-goog-api-key"] == "g_k"
    assert json.loads(request.content)["tools"] == [{"googleSearch": {}}]
    assert result.text == "ok"


async def test_default_transport_error_keeps_vendor_body(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.perplexity.ai/chat/completions",
        status_code=429,
        json={"error": {"message": "rate limit exceeded"}},
    )

    with pytest.raises(SearchEngineError) as exc_info:
        await PerplexityAnswerEngine("sonar-pro", api_key="pplx-secret").answer("q")

    message = str(exc_info.value)
    assert "429" in message and "rate limit exceeded" in message
    assert "pplx-secret" not in message


@pytest.mark.parametrize(
    "cls",
    [
        PerplexityAnswerEngine,
        GeminiAnswerEngine,
        OpenAIAnswerEngine,
        OpenRouterAnswerEngine,
    ],
)
def test_is_available_needs_a_key(cls: type, monkeypatch: pytest.MonkeyPatch) -> None:
    for env in cls.KEY_ENV:
        monkeypatch.delenv(env, raising=False)
    assert cls("m").is_available() is False
    assert cls("m", api_key="k").is_available() is True
