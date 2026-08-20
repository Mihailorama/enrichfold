"""Immutable, provenance-first data contracts for enrichment."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping


EntityKind = Literal["person", "company"]
ClaimKind = Literal["observed", "inferred"]
ReviewStatus = Literal["accepted", "needs_review"]


@dataclass(frozen=True)
class Entity:
    """A person or company identified by one or more non-empty identifiers."""

    kind: EntityKind
    identifiers: Mapping[str, str]

    def __post_init__(self) -> None:
        normalized = {
            key.strip(): value.strip()
            for key, value in self.identifiers.items()
            if key.strip() and value.strip()
        }
        if not normalized:
            raise ValueError("an entity requires at least one non-empty identifier")
        object.__setattr__(self, "identifiers", normalized)

    @classmethod
    def person(cls, **identifiers: str) -> Entity:
        return cls(kind="person", identifiers=identifiers)

    @classmethod
    def company(cls, **identifiers: str) -> Entity:
        return cls(kind="company", identifiers=identifiers)


@dataclass(frozen=True)
class Evidence:
    """A provider-observed source. The library never fetches it itself."""

    source_url: str
    observed_at: str
    confidence: float
    attributes: Mapping[str, Any] = field(default_factory=dict)
    source_title: str | None = None
    source_date: str | None = None
    provider: str | None = None

    def __post_init__(self) -> None:
        if not self.source_url.startswith(("https://", "http://")):
            raise ValueError("evidence requires an http(s) source_url")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class Claim:
    """One value asserted for a field, with an immutable evidence reference.

    ``inferred`` claims are intentionally never silently auto-approved by the
    reconciliation API; callers must record their review decision.
    """

    field: str
    value: Any
    evidence: Evidence
    kind: ClaimKind = "observed"

    def __post_init__(self) -> None:
        if not self.field.strip():
            raise ValueError("a claim requires a non-empty field")


@dataclass(frozen=True)
class ResolvedAttribute:
    """One chosen attribute and the evidence that supports it."""

    value: Any
    source_url: str
    observed_at: str
    confidence: float


@dataclass(frozen=True)
class FieldResolution:
    """A deterministic choice plus alternatives that require human review."""

    value: Any
    evidence: Evidence
    kind: ClaimKind
    status: ReviewStatus
    alternatives: tuple[Claim, ...] = ()


@dataclass(frozen=True)
class ReconciliationResult:
    """Field-level decisions from one or more independently supplied claims."""

    fields: Mapping[str, FieldResolution]

    @property
    def review_fields(self) -> tuple[str, ...]:
        return tuple(name for name, value in self.fields.items() if value.status == "needs_review")

    @property
    def requires_review(self) -> bool:
        return bool(self.review_fields)


@dataclass(frozen=True)
class EnrichmentResult:
    """Resolved attributes plus requested fields for which no evidence exists."""

    entity: Entity
    attributes: Mapping[str, ResolvedAttribute]
    missing: tuple[str, ...]
    review_fields: tuple[str, ...] = ()


def canonical_value(value: Any) -> str:
    """Stable value identity for deterministic grouping and conflict detection."""

    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
