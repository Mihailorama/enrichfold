from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from enrichfold import (
    Claim,
    Entity,
    Evidence,
    ProviderSpec,
    ResearchEngine,
    ScrapefoldScrapeProvider,
    WebSearchProvider,
)
from enrichfold.search import SearchResult


def test_scrapefold_sources_keep_provenance(monkeypatch) -> None:
    async def search(query, opts):
        assert query == "example.com company"
        assert opts.engines == ("parallel", "tavily")
        return [
            SearchResult(
                url="https://example.com/about",
                title="About",
                snippet="Acme builds software.",
                engines=("parallel", "tavily"),
            )
        ]

    monkeypatch.setattr("enrichfold.search.provider.search", search)

    def map_results(entity, results):
        source = results[0]
        assert source["engines"] == ("parallel", "tavily")
        return [
            Claim(
                field="summary",
                value=source["description"],
                kind="inferred",
                evidence=Evidence(
                    source_url=source["url"],
                    observed_at=source["acquired_at"],
                    confidence=0.8,
                    provider="scrapefold",
                ),
            )
        ]

    provider = WebSearchProvider(
        lambda entity: f"{entity.identifiers['domain']} company",
        map_results,
        engines=("parallel", "tavily"),
        usage_units=2,
    )
    result = ResearchEngine(
        [ProviderSpec("scrapefold", provider, reserved_units=2)]
    ).run(Entity.company(domain="example.com"), requested_fields=("summary",))
    assert result.attributes["summary"].value == "Acme builds software."
    assert result.attributes["summary"].source_url == "https://example.com/about"
    assert result.provider_runs[0].used_units == 2


def test_scrapefold_scrape_can_supply_source_claim(monkeypatch) -> None:
    async def scrape(url, opts):
        assert url == "https://example.com/about"
        assert opts.engines == ("firecrawl",)
        return SimpleNamespace(
            url=url,
            text="Acme builds software.",
            markdown="Acme builds software.",
            html=None,
            json=None,
            engine="firecrawl",
        )

    fake = ModuleType("scrapefold")
    fake.scrape = scrape
    fake.ScrapeOptions = lambda **kwargs: SimpleNamespace(**kwargs)
    monkeypatch.setitem(sys.modules, "scrapefold", fake)

    def map_result(entity, source):
        assert source["engine"] == "firecrawl"
        return [
            Claim(
                field="summary",
                value=source["text"],
                kind="inferred",
                evidence=Evidence(
                    source_url=source["url"],
                    observed_at=source["acquired_at"],
                    confidence=0.8,
                    provider=source["engine"],
                ),
            )
        ]

    provider = ScrapefoldScrapeProvider(
        "https://example.com/about", map_result, engines=("firecrawl",), usage_units=1
    )
    result = ResearchEngine(
        [ProviderSpec("scrapefold", provider, reserved_units=1)]
    ).run(Entity.company(domain="example.com"), requested_fields=("summary",))
    assert result.attributes["summary"].source_url == "https://example.com/about"
