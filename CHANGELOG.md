# Changelog

## 0.7.0 — 2026-09-26

- Add `TregClient` for JSON catalog calls with token/org authentication, a
  per-call spending ceiling, and actual cost/call/provider metadata.
- Add `TregProvider` for People search, company enrichment, email lookup,
  and other catalog sources. Applications explicitly map responses to claims.
- Add `treg` web search via `treg.web.search`; Scrapefold uses this same API.
- Report pending async calls without automatically resubmitting paid tasks.
- Preserve provider metadata in research runs, including Treg call receipts.

## 0.6.0 — 2026-09-25

- Add optional multi-engine web search with Exa, Parallel, You.com, Tavily,
  Linkup, Seltz, TinyFish, Nimble, Browserbase, Serper, and DuckDuckGo.
- Add `WebSearchProvider` to map search sources to provenance-bearing claims.
- Add optional `ScrapefoldScrapeProvider` for page-backed research. Scrapefold
  now delegates its public `search()` API to Enrichfold.
- Include the previously unreleased `GroundingValidator` and `find_citations`
  additions described below.

### Grounding changes prepared as 0.5.0 (not published separately)

- Add `GroundingValidator`, an optional `EvidenceValidator` adapter that grounds
  a provider-asserted claim value (and its evidence attribute values) against
  the text of its own `source_url`, fetched through a caller-supplied
  `fetch(url) -> str` callable. Enrichfold's core still makes no network calls
  and gains no HTTP client.
- Add `find_citations`, a stdlib-only two-pass exact-then-normalized substring
  matcher returning coverage; a port of Scrapefold's citation algorithm vendored
  into the adapter so enrichfold keeps no dependency on Scrapefold.
- Verdicts preserve provenance: `accepted` when the value is grounded,
  `rejected` when absent, and `needs_review` on partial coverage, an
  ungroundable value, or a fetch failure (fetch errors never propagate).

## 0.4.0 — 2026-09-09

- Add `KeenableProvider`, a synchronous Keenable web-search adapter for
  `ResearchEngine` that reads `KEENABLE_API_KEY` or an explicit key.
- Keep claim extraction caller-owned so search snippets cannot silently become
  accepted enrichment facts.
- Add end-to-end provider coverage and live validation against the Keenable API.

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
