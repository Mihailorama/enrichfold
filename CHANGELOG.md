# Changelog

## 0.2.0 - 2026-08-20

- Added provenance-bearing `Claim` contracts and deterministic claim
  reconciliation.
- Made contradictory values and inferred claims explicit `needs_review` gates.
- Added offline, fail-closed company identity resolution for corporate email
  domains and supplied websites.
- Preserved the 0.1 provider protocol and the simple `EnrichmentPipeline` API;
  pipeline results now expose `review_fields` when provider values disagree.

## 0.1.0 - 2026-08-20

- Initial provider-neutral, provenance-first enrichment core.
