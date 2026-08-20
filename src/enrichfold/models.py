"""Data contracts for provenance-first enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


EntityKind = Literal["person", "company"]


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
    """Attributes observed by one provider at a source URL."""

    source_url: str
    observed_at: str
    confidence: float
    attributes: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.source_url.startswith(("https://", "http://")):
            raise ValueError("evidence requires an http(s) source_url")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class ResolvedAttribute:
    """One chosen attribute and the evidence that supports it."""

    value: Any
    source_url: str
    observed_at: str
    confidence: float


@dataclass(frozen=True)
class EnrichmentResult:
    """Resolved attributes plus requested fields for which no evidence exists."""

    entity: Entity
    attributes: Mapping[str, ResolvedAttribute]
    missing: tuple[str, ...]
