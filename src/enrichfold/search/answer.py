"""Answer engines: a web-grounded LLM answer with its citations.

Each engine builds the vendor request the way ai-utils' ``enrich_service``
does (same prompts, sampling and token limits), sends it through a ``call``,
and maps the reply to an ``AnswerResult``:

- ``PerplexityAnswerEngine``: Perplexity sonar chat completions; citations
  from ``search_results`` (else the bare ``citations`` URLs).
- ``GeminiAnswerEngine``: Gemini ``generateContent`` with Google Search
  grounding; citations from ``groundingMetadata.groundingChunks``. Their URLs
  are Google's grounding redirect links and their titles are domains.
- ``OpenAIAnswerEngine``: OpenAI Responses API with the ``web_search`` tool;
  citations from the ``url_citation`` annotations.
- ``OpenRouterAnswerEngine``: an OpenRouter ``:online`` model (OpenRouter's
  web plugin); citations from the message's ``url_citation`` annotations.

The model is a required argument; nothing is defaulted. ``call(url, body)``
sends the JSON body and returns the vendor's JSON reply. The caller can inject
it to own keys, transport, retries and model fallbacks; without one the engine
POSTs with ``httpx`` and a key from the constructor or the environment.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from enrichfold.search.engines.base import SearchEngineError, check_response

Call = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Citation:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass(frozen=True)
class AnswerResult:
    text: str
    citations: tuple[Citation, ...] = ()
    engine: str = ""
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


# Prompts copied from ai-utils services/enrich_service.py, whitespace included.
GEMINI_PROMPT = (
    "Please research and provide comprehensive information about: {query}\n"
    "\n"
    "        Provide an in-depth research report covering:\n"
    "        1. Key facts and figures\n"
    "        2. Main organizations, people, or entities involved\n"
    "        3. Recent developments or news\n"
    "        4. Historical context if relevant\n"
    "        \n"
    "        Include all relevant details you can find.\n"
    "        Be specific, thorough, and cite your sources of information where possible.\n"
    "        If you're uncertain about any information, please indicate that clearly.\n"
    "        \n"
    '        At the end of your response, include a "Sources" section listing websites, articles, or resources that provided this information.'
)

OPENROUTER_PROMPT = (
    "Please provide comprehensive information about the following:\n"
    "        \n"
    "{query}\n"
    "\n"
    "Conduct a thorough search and provide detailed information, including:\n"
    "1. Facts, figures, and relevant data\n"
    "2. Key people, organizations, or entities involved\n"
    "3. Recent developments or news\n"
    "4. Historical context if relevant\n"
    "5. Any links, URLs, or sources of information when available\n"
    "\n"
    "Provide as much specific, detailed information as possible to answer the query comprehensively.\n"
    "Be precise and include all relevant facts, figures, dates, and sources when available."
)

OPENAI_SYSTEM_PROMPT = (
    "You are a senior research analyst with direct access to the OpenAI Web Search tool. "
    "Run live searches, aggregate the most authoritative facts, cite URLs inline, and "
    "summarize findings in clear prose."
)


def _dedupe(citations: list[Citation]) -> tuple[Citation, ...]:
    seen: dict[str, Citation] = {}
    for citation in citations:
        if citation.url and citation.url not in seen:
            seen[citation.url] = citation
    return tuple(seen.values())


class AnswerEngine:
    NAME: ClassVar[str] = ""
    KEY_ENV: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        model: str,
        *,
        call: Call | None = None,
        api_key: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        if not model:
            raise ValueError(f"{self.NAME}: model is required")
        self.model = model
        self.call = call
        self.api_key = api_key or next(
            (os.environ[k] for k in self.KEY_ENV if os.getenv(k)), None
        )
        self.timeout_s = timeout_s

    def is_available(self) -> bool:
        """Whether a key is present (a caller-injected ``call`` may not need one)."""
        return bool(self.api_key)

    def request(self, query: str) -> tuple[str, dict[str, Any]]:
        """The vendor URL and JSON body for ``query``."""
        raise NotImplementedError

    def parse(self, raw: dict[str, Any]) -> tuple[str, list[Citation]]:
        raise NotImplementedError

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key or ''}"}

    async def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(url, json=body, headers=self.headers())
        check_response(response)
        return response.json()

    async def answer(self, query: str) -> AnswerResult:
        url, body = self.request(query)
        try:
            raw = await (self.call or self._post)(url, body)
            text, citations = self.parse(raw)
        except Exception as exc:
            raise SearchEngineError(self.NAME, str(exc)) from exc
        text = text.strip()
        if not text:
            raise SearchEngineError(self.NAME, f"{self.model} returned no content")
        return AnswerResult(text, _dedupe(citations), self.NAME, self.model, raw)


def _chat_message(raw: dict[str, Any]) -> dict[str, Any]:
    return ((raw.get("choices") or [{}])[0] or {}).get("message") or {}


class PerplexityAnswerEngine(AnswerEngine):
    """Perplexity sonar, e.g. ``model="sonar-pro"`` (ai-utils' first choice)."""

    NAME = "perplexity"
    KEY_ENV = ("PERPLEXITY_API_KEY", "PERPLEXITYAI_API_KEY")

    def request(self, query: str) -> tuple[str, dict[str, Any]]:
        return "https://api.perplexity.ai/chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": query}],
            "max_tokens": 8000,
            "temperature": 0.05,
        }

    def parse(self, raw: dict[str, Any]) -> tuple[str, list[Citation]]:
        results = raw.get("search_results") or []
        citations = (
            [
                Citation(
                    r.get("url") or "", r.get("title") or "", r.get("snippet") or ""
                )
                for r in results
            ]
            if results
            else [Citation(url) for url in raw.get("citations") or []]
        )
        return _chat_message(raw).get("content") or "", citations


class OpenRouterAnswerEngine(AnswerEngine):
    """An OpenRouter model with web search; ``:online`` is appended when missing."""

    NAME = "openrouter"
    KEY_ENV = ("OPENROUTER_API_KEY",)

    def __init__(self, model: str, **kwargs: Any) -> None:
        if model and not model.endswith(":online"):
            model += ":online"
        super().__init__(model, **kwargs)

    def request(self, query: str) -> tuple[str, dict[str, Any]]:
        return "https://openrouter.ai/api/v1/chat/completions", {
            "model": self.model,
            "messages": [
                {"role": "user", "content": OPENROUTER_PROMPT.replace("{query}", query)}
            ],
            "max_tokens": 4000,
            "temperature": 0.0,
        }

    def parse(self, raw: dict[str, Any]) -> tuple[str, list[Citation]]:
        message = _chat_message(raw)
        citations = [
            Citation(c.get("url") or "", c.get("title") or "", c.get("content") or "")
            for a in message.get("annotations") or []
            if a.get("type") == "url_citation" and (c := a.get("url_citation") or {})
        ]
        return message.get("content") or "", citations


class OpenAIAnswerEngine(AnswerEngine):
    """OpenAI Responses API with the ``web_search`` tool."""

    NAME = "openai"
    KEY_ENV = ("OPENAI_API_KEY",)

    def request(self, query: str) -> tuple[str, dict[str, Any]]:
        return "https://api.openai.com/v1/responses", {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": OPENAI_SYSTEM_PROMPT}],
                },
                {"role": "user", "content": [{"type": "input_text", "text": query}]},
            ],
            "tools": [{"type": "web_search"}],
            "temperature": 0.1,
            "max_output_tokens": 10000,
        }

    def parse(self, raw: dict[str, Any]) -> tuple[str, list[Citation]]:
        parts = [
            content
            for block in raw.get("output") or []
            if block.get("type") == "message"
            for content in block.get("content") or []
            if isinstance(content, dict) and content.get("type") == "output_text"
        ]
        # The SDK's response.output_text, which ai-utils reads, joins these with "".
        text = raw.get("output_text") or "".join(p.get("text") or "" for p in parts)
        citations = [
            Citation(a.get("url") or "", a.get("title") or "")
            for p in parts
            for a in p.get("annotations") or []
            if a.get("type") == "url_citation"
        ]
        return text, citations


class GeminiAnswerEngine(AnswerEngine):
    """Gemini with Google Search grounding, e.g. ``model="gemini-3.8-flash"``."""

    NAME = "gemini"
    KEY_ENV = ("GEMINI_API_KEY", "GOOGLE_API_KEY")

    def headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key or ""}

    def request(self, query: str) -> tuple[str, dict[str, Any]]:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        return url, {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": GEMINI_PROMPT.replace("{query}", query)}],
                }
            ],
            "tools": [{"googleSearch": {}}],
            "generationConfig": {"responseMimeType": "text/plain", "temperature": 0.1},
        }

    def parse(self, raw: dict[str, Any]) -> tuple[str, list[Citation]]:
        candidate = (raw.get("candidates") or [{}])[0] or {}
        text = "".join(
            part.get("text") or ""
            for part in (candidate.get("content") or {}).get("parts") or []
            if not part.get("thought")
        )
        chunks = (candidate.get("groundingMetadata") or {}).get("groundingChunks") or []
        citations = [
            Citation(web.get("uri") or "", web.get("title") or "")
            for chunk in chunks
            if (web := chunk.get("web") or {})
        ]
        return text, citations


__all__ = [
    "AnswerEngine",
    "AnswerResult",
    "Call",
    "Citation",
    "GeminiAnswerEngine",
    "OpenAIAnswerEngine",
    "OpenRouterAnswerEngine",
    "PerplexityAnswerEngine",
]
