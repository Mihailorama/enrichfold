"""Live parity check: enrichfold engines against a saved ai-utils output.

Run the same query through ai-utils and through enrichfold at about the same
time (SERPs drift), then compare the URLs each returns.

1. Capture ai-utils output, from the ai-utils checkout with its env loaded::

       python - <<'EOF'
       import asyncio, json
       from services import enrich_service as e, url_to_text_service as u
       q = "Acme Corp headquarters city"
       fns = {"jina": e.perform_jinaai_search, "serpapi_yandex": e.perform_yandex_search,
              "perplexity": e.perform_perplexity_search, "gemini": e.perform_gemini_search,
              "openai": e.perform_openai_search, "openrouter": e.perform_openrouter_search,
              "outscraper": u.get_content_outscraper}
       async def main():
           out = {"query": q}
           for name, fn in fns.items():
               try:
                   out[name] = await fn(q)
               except SearchEngineError as exc:
                   out[name] = {"error": str(exc)}
           json.dump(out, open("ai_utils_output.json", "w"), ensure_ascii=False, default=str)
       asyncio.run(main())
       EOF

   (``get_content_outscraper`` takes a URL in ai-utils; pass a URL as ``q`` to
   compare it.)

2. With the vendor keys in env, run::

       python scripts/parity_ai_utils.py ai_utils_output.json \\
           --perplexity-model sonar-pro --gemini-model gemini-3.8-flash \\
           --openai-model gpt-5.2 --openrouter-model google/gemini-3.8-flash

Engines without a key, a model, or a saved ai-utils output are skipped. A SERP
engine passes when it returns at least ``--min-overlap`` of ai-utils' URLs
(default 0.8). Answer engines are generated text, so they pass on a non-empty
answer and the URL overlap is reported, not enforced. Exit code 1 if any engine
fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from enrichfold.search import (
    GeminiAnswerEngine,
    OpenAIAnswerEngine,
    OpenRouterAnswerEngine,
    PerplexityAnswerEngine,
    SearchEngineError,
    SearchOptions,
    get_search_engine,
)

SERP_ENGINES = ("jina", "serpapi_yandex", "serpapi_google", "scrapingdog", "outscraper")
ANSWER_ENGINES = {
    "perplexity": PerplexityAnswerEngine,
    "gemini": GeminiAnswerEngine,
    "openai": OpenAIAnswerEngine,
    "openrouter": OpenRouterAnswerEngine,
}
_URL = re.compile(r"https?://[^\s\"'<>()\[\]{}|\\^`]+")


def urls_in(value: Any) -> list[str]:
    """The result URLs in ai-utils' output, in order.

    SerpAPI dict -> ``organic_results`` links; Jina markdown -> ``URL Source:``
    lines; Outscraper text -> ``URL:`` lines; Scrapingdog ``str(list)`` ->
    ``'link'`` values; anything else (answer text) -> every URL in it.
    """
    if isinstance(value, dict) and "organic_results" in value:
        found = [r.get("link", "") for r in value["organic_results"]]
    else:
        text = (
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        )
        for pattern in (r"URL Source: (\S+)", r"^URL: (\S+)", r"'link': '([^']+)'"):
            found = re.findall(pattern, text, flags=re.MULTILINE)
            if found:
                break
        else:
            found = _URL.findall(text)
    return list(dict.fromkeys(_norm(u) for u in found if u))


def _norm(url: str) -> str:
    return url.rstrip(".,;:").removesuffix("?utm_source=openai").rstrip("/")


def overlap(ours: list[str], theirs: list[str]) -> float:
    """Share of ai-utils' URLs that enrichfold also returned."""
    if not theirs:
        return 1.0
    return len({_norm(u) for u in ours} & set(theirs)) / len(theirs)


async def run(args: argparse.Namespace) -> int:
    saved = json.loads(Path(args.saved).read_text(encoding="utf-8"))
    query = args.query or saved["query"]
    failed = 0
    for name in SERP_ENGINES:
        engine = get_search_engine(name)()
        if name not in saved or not engine.is_available():
            print(f"{name}: skipped (no saved output or no key)")
            continue
        try:
            hits = await engine.search(query, SearchOptions(count=args.count))
        except SearchEngineError as exc:
            print(f"{name}: FAIL {exc}")
            failed += 1
            continue
        theirs = urls_in(saved[name])
        score = overlap([h.url for h in hits], theirs)
        ok = score >= args.min_overlap
        failed += not ok
        print(
            f"{name}: {'ok' if ok else 'FAIL'} overlap={score:.2f} "
            f"ours={len(hits)} ai-utils={len(theirs)}"
        )
    for name, cls in ANSWER_ENGINES.items():
        model = getattr(args, f"{name}_model")
        if name not in saved or not model:
            print(f"{name}: skipped (no saved output or no --{name}-model)")
            continue
        engine = cls(model)
        if not engine.api_key:
            print(f"{name}: skipped (no key)")
            continue
        try:
            result = await engine.answer(query)
        except SearchEngineError as exc:
            print(f"{name}: FAIL {exc}")
            failed += 1
            continue
        score = overlap([c.url for c in result.citations], urls_in(saved[name]))
        print(
            f"{name}: ok chars={len(result.text)} citations={len(result.citations)} "
            f"ai-utils-url-overlap={score:.2f} (reported only)"
        )
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("saved", help="JSON from step 1: {query, <engine>: output}")
    parser.add_argument("--query", help="override the saved query")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--min-overlap", type=float, default=0.8)
    for name in ANSWER_ENGINES:
        parser.add_argument(f"--{name}-model")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
