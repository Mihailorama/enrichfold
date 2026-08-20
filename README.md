# Enrichfold

Provider-neutral, provenance-first entity enrichment for people and companies.

`enrichfold` is an offline-first core, not a scraping product: applications supply
their own discovery providers and credentials. Every accepted attribute retains its
source URL, observation time, and confidence, so downstream systems can decide
whether a result is suitable for an automated action or requires review.

```python
from enrichfold import Entity, EnrichmentPipeline, Evidence

class CompanyProvider:
    def discover(self, entity):
        return [Evidence(
            source_url="https://example.com/team",
            observed_at="2026-08-20T12:00:00Z",
            confidence=0.94,
            attributes={"industry": "software", "company_size": "51-200"},
        )]

company = Entity.company(domain="example.com")
result = EnrichmentPipeline([CompanyProvider()]).enrich(company)
print(result.attributes["industry"].value)  # software
```

## Design boundaries

- No network calls, scraping, credential handling, contact exporting, or outreach.
- No inferred facts: a field is returned only when a provider supplies evidence.
- Conflicts resolve deterministically by confidence, source URL, then canonical value.
- Bring your own providers for search engines, public data APIs, browser tools, or
  internal approved sources.

## Installation

```bash
pip install enrichfold
```

## License

MIT.
