# Changelog

## 0.3.0 — 2026-08-20

- Add `ResearchEngine`: concurrent, provider-neutral research orchestration
  with deterministic claim reconciliation.
- Add pre-spend generic unit budgets. Providers are skipped before they start
  when their reservation would exceed the configured limit.
- Add optional evidence-validation hooks that retain provenance while routing
  weak sources to review or rejecting them from resolution.
- Surface explicit `completed`, `partial`, `needs_review`, and `failed` run
  states along with provider outcomes and missing requested fields.

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
