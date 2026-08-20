"""Provider orchestration and review-safe deterministic reconciliation."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Protocol

from .models import (
    Claim,
    EnrichmentResult,
    Entity,
    Evidence,
    FieldResolution,
    ReconciliationResult,
    ResolvedAttribute,
    canonical_value,
)


class DiscoveryProvider(Protocol):
    """A caller-owned adapter that returns externally observed evidence."""

    def discover(self, entity: Entity) -> Iterable[Evidence]: ...


Provider = DiscoveryProvider | Callable[[Entity], Iterable[Evidence]]


def _rank(claim: Claim) -> tuple[int, float, str, str]:
    """Rank observed evidence before inference, then use reproducible tie-breaks."""

    return (
        0 if claim.kind == "observed" else 1,
        -claim.evidence.confidence,
        claim.evidence.source_url,
        canonical_value(claim.value),
    )


def reconcile_claims(claims: Iterable[Claim]) -> ReconciliationResult:
    """Resolve claims deterministically while failing closed on disagreement.

    Multiple claims for the same canonical value reinforce one another. Distinct
    values are retained as alternatives and make the field ``needs_review``;
    an inferred winning value also requires review. This lets an application
    choose its own approval workflow without losing provenance.
    """

    by_field: dict[str, list[Claim]] = {}
    for claim in claims:
        by_field.setdefault(claim.field.strip(), []).append(claim)

    fields: dict[str, FieldResolution] = {}
    for name, field_claims in by_field.items():
        by_value: dict[str, list[Claim]] = {}
        for claim in field_claims:
            by_value.setdefault(canonical_value(claim.value), []).append(claim)

        representatives = [min(group, key=_rank) for group in by_value.values()]
        chosen = min(representatives, key=_rank)
        alternatives = tuple(
            claim
            for claim in sorted(representatives, key=_rank)
            if canonical_value(claim.value) != canonical_value(chosen.value)
        )
        status = "needs_review" if alternatives or chosen.kind == "inferred" else "accepted"
        fields[name] = FieldResolution(
            value=chosen.value,
            evidence=chosen.evidence,
            kind=chosen.kind,
            status=status,
            alternatives=alternatives,
        )
    return ReconciliationResult(fields=fields)


class EnrichmentPipeline:
    """Combine provider evidence without making network calls itself."""

    def __init__(self, providers: Sequence[Provider]) -> None:
        self._providers = tuple(providers)

    def enrich(self, entity: Entity, *, requested_fields: Iterable[str] = ()) -> EnrichmentResult:
        claims: list[Claim] = []
        for provider in self._providers:
            discovered = provider.discover(entity) if hasattr(provider, "discover") else provider(entity)
            for evidence in discovered:
                claims.extend(
                    Claim(field=attribute, value=value, evidence=evidence)
                    for attribute, value in evidence.attributes.items()
                )

        reconciled = reconcile_claims(claims)
        resolved = {
            attribute: ResolvedAttribute(
                value=resolution.value,
                source_url=resolution.evidence.source_url,
                observed_at=resolution.evidence.observed_at,
                confidence=resolution.evidence.confidence,
            )
            for attribute, resolution in reconciled.fields.items()
        }
        requested = tuple(dict.fromkeys(field.strip() for field in requested_fields if field.strip()))
        missing = tuple(field for field in requested if field not in resolved)
        return EnrichmentResult(
            entity=entity,
            attributes=resolved,
            missing=missing,
            review_fields=reconciled.review_fields,
        )
