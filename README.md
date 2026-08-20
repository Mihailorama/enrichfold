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

## Evidence, conflicts, and review gates

`enrichfold` keeps provider I/O outside the library. Its core turns supplied
evidence into deterministic decisions while retaining disagreements for a human
approval flow. A conflicting value is never silently accepted:

```python
from enrichfold import Claim, Evidence, reconcile_claims

result = reconcile_claims([
    Claim(
        field="industry",
        value="software",
        evidence=Evidence(
            source_url="https://acme.example/about",
            observed_at="2026-08-20T12:00:00Z",
            confidence=0.91,
        ),
    ),
    Claim(
        field="industry",
        value="retail",
        evidence=Evidence(
            source_url="https://directory.example/acme",
            observed_at="2026-08-20T12:00:00Z",
            confidence=0.88,
        ),
    ),
])

industry = result.fields["industry"]
assert industry.value == "software"          # stable suggested value
assert industry.status == "needs_review"     # do not automate an action
assert result.requires_review is True
```

`Claim(kind="inferred", ...)` also requires review even with no competing
claim. This distinction makes it possible to keep model-produced hypotheses
without presenting them as observed facts.

## Company identity gate

Before a caller enriches or acts on a company, use the offline identity gate.
It is deliberately conservative: free mailboxes, invalid sites, domain
conflicts, and corporate domains that do not exactly match the name receive a
review status. Applications can pass separately verified site metadata when
they have it.

```python
from enrichfold import derive_company_identity

identity = derive_company_identity(
    email="hello@acme.example",
    company_name="Acme",
    website="https://www.acme.example/about",
)

assert identity.status == "verified"
assert identity.canonical_domain == "acme.example"
```

## Design boundaries

- No network calls, scraping, credential handling, contact exporting, or outreach.
- No inferred facts: a field is returned only when a provider supplies evidence.
- Conflicts have a deterministic suggested value but are marked `needs_review`.
- Inferred claims are always marked `needs_review`.
- Company identity is verified only through an exact name/domain match or
  caller-supplied, independently verified same-domain site metadata.
- Bring your own providers for search engines, public data APIs, browser tools, or
  internal approved sources.

The package intentionally does not decide whether a review is approved or run
an action after one; persistence, permissions, UI, and provider adapters stay
with the host application.

## Installation

```bash
pip install enrichfold
```

## Development

```bash
uv run --with pytest pytest -q
python -m build
```

## License

MIT.
