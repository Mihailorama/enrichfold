"""The parity script's URL extraction for each ai-utils output format."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).parents[1] / "scripts" / "parity_ai_utils.py"
_spec = importlib.util.spec_from_file_location("parity_ai_utils", _PATH)
assert _spec and _spec.loader
parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parity)


def test_urls_in_each_ai_utils_format() -> None:
    serpapi = {
        "search_metadata": {"json_endpoint": "https://serpapi.com/x.json"},
        "organic_results": [{"link": "https://a.test/"}, {"link": "https://b.test"}],
    }
    jina = (
        "[1] Title: A\n[1] URL Source: https://a.test/\n[1] Description: d\n"
        "[1] Content: see https://img.test/x.png\n"
    )
    outscraper = "# A\nURL: https://a.test/\nabout https://other.test\n\n# B\nURL: https://b.test"
    scrapingdog = str([{"title": "A", "link": "https://a.test/"}])
    answer = "Acme (https://a.test/), see https://b.test/page."

    assert parity.urls_in(serpapi) == ["https://a.test", "https://b.test"]
    assert parity.urls_in(jina) == ["https://a.test"]
    assert parity.urls_in(outscraper) == ["https://a.test", "https://b.test"]
    assert parity.urls_in(scrapingdog) == ["https://a.test"]
    assert parity.urls_in(answer) == ["https://a.test", "https://b.test/page"]
    assert (
        parity.overlap(["https://a.test/"], ["https://a.test", "https://b.test"]) == 0.5
    )
