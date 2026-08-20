"""Provider-neutral research orchestration with provenance and review gates.

The engine deliberately owns no HTTP client, credentials, persistence, or task
queue.  Callers provide provider adapters; this module makes their outcomes
deterministic, budget-bounded before work starts, and safe to route to review.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

from .models import Claim, Entity, ResolvedAttribute
from .pipeline import reconcile_claims

ProviderRunStatus = Literal["succeeded", "failed", "skipped_budget"]
ResearchStatus = Literal["completed", "partial", "needs_review", "failed"]
EvidenceVerdictStatus = Literal["accepted", "needs_review", "rejected"]


@dataclass(frozen=True)
class ProviderOutput:
    """A provider-owned result containing only claims it can substantiate."""

    claims: tuple[Claim, ...] | Iterable[Claim]
    usage_units: float = 0.0
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        claims = tuple(self.claims)
        if any(not isinstance(claim, Claim) for claim in claims):
            raise TypeError("provider output claims must be Claim instances")
        if self.usage_units < 0:
            raise ValueError("provider usage_units must be non-negative")
        object.__setattr__(self, "claims", claims)
        object.__setattr__(self, "metadata", dict(self.metadata))


class ResearchProvider(Protocol):
    """Caller-owned adapter. It may do I/O; Enrichfold itself never does."""

    def research(self, entity: Entity) -> ProviderOutput: ...


ProviderCallable = Callable[[Entity], ProviderOutput]
ProviderRunner = ResearchProvider | ProviderCallable


@dataclass(frozen=True)
class ProviderSpec:
    """One independently executable provider with an upfront unit reservation."""

    name: str
    runner: ProviderRunner
    reserved_units: float = 0.0

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("provider name must be non-empty")
        if self.reserved_units < 0:
            raise ValueError("provider reserved_units must be non-negative")
        object.__setattr__(self, "name", name)


@dataclass(frozen=True)
class ResearchBudget:
    """Generic units avoid encoding provider pricing or credentials in the core."""

    max_units: float | None = None
    reserved_units: float = 0.0
    used_units: float = 0.0

    def __post_init__(self) -> None:
        if self.max_units is not None and self.max_units < 0:
            raise ValueError("budget max_units must be non-negative")
        if self.reserved_units < 0 or self.used_units < 0:
            raise ValueError("budget units must be non-negative")
        if self.max_units is not None and self.reserved_units > self.max_units:
            raise ValueError("budget reserved_units cannot exceed max_units")

    @property
    def remaining_units(self) -> float | None:
        return None if self.max_units is None else self.max_units - self.reserved_units


@dataclass(frozen=True)
class EvidenceVerdict:
    """A caller-supplied decision about a source without hiding its provenance."""

    status: EvidenceVerdictStatus
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("an evidence verdict requires a reason")


class EvidenceValidator(Protocol):
    """Optional source-policy hook; it must not perform hidden enrichment."""

    def validate(self, claim: Claim) -> EvidenceVerdict: ...


@dataclass(frozen=True)
class EvidenceAssessment:
    claim: Claim
    provider: str
    verdict: EvidenceVerdict


@dataclass(frozen=True)
class ProviderRun:
    provider: str
    status: ProviderRunStatus
    reserved_units: float
    used_units: float = 0.0
    claims: tuple[Claim, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class ResearchResult:
    """Research result whose consumer can distinguish coverage from approval."""

    entity: Entity
    status: ResearchStatus
    attributes: Mapping[str, ResolvedAttribute]
    missing: tuple[str, ...]
    review_fields: tuple[str, ...]
    provider_runs: tuple[ProviderRun, ...]
    evidence_assessments: tuple[EvidenceAssessment, ...]
    budget: ResearchBudget

    @property
    def requires_review(self) -> bool:
        return bool(self.review_fields)

    @property
    def is_partial(self) -> bool:
        return any(run.status != "succeeded" for run in self.provider_runs)


def _accepted(_: Claim) -> EvidenceVerdict:
    return EvidenceVerdict("accepted", "no validator configured")


def _run_provider(spec: ProviderSpec, entity: Entity) -> ProviderOutput:
    result = spec.runner.research(entity) if hasattr(spec.runner, "research") else spec.runner(entity)
    if not isinstance(result, ProviderOutput):
        raise TypeError("research providers must return ProviderOutput")
    if result.usage_units > spec.reserved_units:
        raise ValueError("provider usage_units exceeded its reserved_units")
    return result


def _safe_error(error: BaseException) -> str:
    """Keep a useful, bounded error without leaking URL credentials or tokens."""

    message = str(error)
    message = re.sub(r"(https?://)[^/@\s]+@", r"\1[redacted]@", message)
    message = re.sub(r"(?i)(token|api[_-]?key|authorization)\s*[=:]\s*[^\s,;]+", r"\1=[redacted]", message)
    return message[:500] or type(error).__name__


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


class ResearchEngine:
    """Execute independent providers concurrently and reconcile their claims.

    A provider's ``reserved_units`` are reserved *before* it starts.  This
    prevents a later provider from being launched once the caller's configured
    budget is exhausted.  Providers must report no more than they reserved.
    """

    def __init__(
        self,
        providers: Iterable[ProviderSpec],
        *,
        budget: ResearchBudget | None = None,
        evidence_validator: EvidenceValidator | None = None,
        max_workers: int | None = None,
    ) -> None:
        specs = tuple(providers)
        names = [spec.name for spec in specs]
        if len(names) != len(set(names)):
            raise ValueError("provider names must be unique")
        if max_workers is not None and max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self._providers = specs
        self._budget = budget or ResearchBudget()
        self._validator = evidence_validator
        self._max_workers = max_workers

    def run(self, entity: Entity, *, requested_fields: Iterable[str] = ()) -> ResearchResult:
        requested = _dedupe(requested_fields)
        reserved_units = 0.0
        scheduled: list[ProviderSpec] = []
        runs: dict[str, ProviderRun] = {}
        for spec in self._providers:
            next_reserved = reserved_units + spec.reserved_units
            if self._budget.max_units is not None and next_reserved > self._budget.max_units:
                runs[spec.name] = ProviderRun(
                    provider=spec.name,
                    status="skipped_budget",
                    reserved_units=0.0,
                )
                continue
            reserved_units = next_reserved
            scheduled.append(spec)

        futures: dict[str, Future[ProviderOutput]] = {}
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for spec in scheduled:
                futures[spec.name] = executor.submit(_run_provider, spec, entity)
            for spec in scheduled:
                try:
                    output = futures[spec.name].result()
                except Exception as error:  # noqa: BLE001 - a provider failure is a normal run outcome.
                    runs[spec.name] = ProviderRun(
                        provider=spec.name,
                        status="failed",
                        reserved_units=spec.reserved_units,
                        error=_safe_error(error),
                    )
                else:
                    runs[spec.name] = ProviderRun(
                        provider=spec.name,
                        status="succeeded",
                        reserved_units=spec.reserved_units,
                        used_units=output.usage_units,
                        claims=cast(tuple[Claim, ...], output.claims),
                    )

        ordered_runs = tuple(runs[spec.name] for spec in self._providers)
        assessments: list[EvidenceAssessment] = []
        accepted_claims: list[Claim] = []
        validator = self._validator.validate if self._validator else _accepted
        for run in ordered_runs:
            if run.status != "succeeded":
                continue
            for claim in run.claims:
                verdict = validator(claim)
                if not isinstance(verdict, EvidenceVerdict):
                    raise TypeError("evidence validators must return EvidenceVerdict")
                assessments.append(EvidenceAssessment(claim=claim, provider=run.provider, verdict=verdict))
                if verdict.status != "rejected":
                    accepted_claims.append(claim)

        reconciled = reconcile_claims(accepted_claims)
        attributes = {
            field: ResolvedAttribute(
                value=resolution.value,
                source_url=resolution.evidence.source_url,
                observed_at=resolution.evidence.observed_at,
                confidence=resolution.evidence.confidence,
            )
            for field, resolution in reconciled.fields.items()
        }
        missing = tuple(field for field in requested if field not in attributes)
        validator_review_fields = (
            assessment.claim.field
            for assessment in assessments
            if assessment.verdict.status == "needs_review"
        )
        review_fields = _dedupe((*reconciled.review_fields, *validator_review_fields, *missing))
        successful_runs = [run for run in ordered_runs if run.status == "succeeded"]
        has_partial_coverage = any(run.status != "succeeded" for run in ordered_runs)
        if not successful_runs:
            status: ResearchStatus = "failed"
        elif review_fields:
            status = "needs_review"
        elif has_partial_coverage:
            status = "partial"
        else:
            status = "completed"
        used_units = sum(run.used_units for run in ordered_runs)
        result_budget = ResearchBudget(
            max_units=self._budget.max_units,
            reserved_units=reserved_units,
            used_units=used_units,
        )
        return ResearchResult(
            entity=entity,
            status=status,
            attributes=attributes,
            missing=missing,
            review_fields=review_fields,
            provider_runs=ordered_runs,
            evidence_assessments=tuple(assessments),
            budget=result_budget,
        )
