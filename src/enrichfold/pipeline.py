"""Provider orchestration and deterministic conflict resolution."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from typing import Protocol

from .models import EnrichmentResult, Entity, Evidence, ResolvedAttribute


class DiscoveryProvider(Protocol):
    """A caller-owned adapter that returns externally observed evidence."""

    def discover(self, entity: Entity) -> Iterable[Evidence]: ...


Provider = DiscoveryProvider | Callable[[Entity], Iterable[Evidence]]


class EnrichmentPipeline:
    """Combine provider evidence without making network calls itself."""

    def __init__(self, providers: Sequence[Provider]) -> None:
        self._providers = tuple(providers)

    def enrich(self, entity: Entity, *, requested_fields: Iterable[str] = ()) -> EnrichmentResult:
        candidates: dict[str, list[Evidence]] = {}
        for provider in self._providers:
            discovered = provider.discover(entity) if hasattr(provider, "discover") else provider(entity)
            for evidence in discovered:
                for attribute in evidence.attributes:
                    candidates.setdefault(attribute, []).append(evidence)

        resolved: dict[str, ResolvedAttribute] = {}
        for attribute, evidence_items in candidates.items():
            best = min(evidence_items, key=lambda item: self._rank(item, attribute))
            resolved[attribute] = ResolvedAttribute(
                value=best.attributes[attribute],
                source_url=best.source_url,
                observed_at=best.observed_at,
                confidence=best.confidence,
            )

        requested = tuple(dict.fromkeys(field.strip() for field in requested_fields if field.strip()))
        missing = tuple(field for field in requested if field not in resolved)
        return EnrichmentResult(entity=entity, attributes=resolved, missing=missing)

    @staticmethod
    def _rank(evidence: Evidence, attribute: str) -> tuple[float, str, str]:
        value = json.dumps(evidence.attributes[attribute], sort_keys=True, default=str)
        return (-evidence.confidence, evidence.source_url, value)
