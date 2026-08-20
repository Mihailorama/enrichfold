from __future__ import annotations

from enrichfold import (
    Claim,
    Entity,
    Evidence,
    EvidenceVerdict,
    ProviderOutput,
    ProviderSpec,
    ResearchBudget,
    ResearchEngine,
)


def claim(field: str, value: object, *, source: str, confidence: float = 0.9) -> Claim:
    return Claim(
        field=field,
        value=value,
        evidence=Evidence(
            source_url=source,
            observed_at="2026-08-20T12:00:00Z",
            confidence=confidence,
        ),
    )


def test_reserves_budget_before_starting_each_provider() -> None:
    called: list[str] = []

    def official(_: Entity) -> ProviderOutput:
        called.append("official")
        return ProviderOutput(
            claims=(claim("industry", "software", source="https://acme.example/about"),),
            usage_units=2,
        )

    def directory(_: Entity) -> ProviderOutput:
        called.append("directory")
        return ProviderOutput(claims=(), usage_units=2)

    result = ResearchEngine(
        [
            ProviderSpec("official", official, reserved_units=2),
            ProviderSpec("directory", directory, reserved_units=2),
        ],
        budget=ResearchBudget(max_units=3),
    ).run(Entity.company(domain="acme.example"), requested_fields=("industry",))

    assert called == ["official"]
    assert result.status == "partial"
    assert result.budget.reserved_units == 2
    assert result.budget.used_units == 2
    assert result.provider_runs[1].status == "skipped_budget"


def test_conflicting_provider_results_require_review_deterministically() -> None:
    result = ResearchEngine(
        [
            ProviderSpec(
                "official",
                lambda _: ProviderOutput(
                    claims=(claim("industry", "software", source="https://acme.example/about"),)
                ),
            ),
            ProviderSpec(
                "directory",
                lambda _: ProviderOutput(
                    claims=(claim("industry", "retail", source="https://directory.example/acme"),)
                ),
            ),
        ]
    ).run(Entity.company(domain="acme.example"), requested_fields=("industry",))

    assert result.status == "needs_review"
    assert result.requires_review is True
    assert result.attributes["industry"].value == "software"
    assert result.review_fields == ("industry",)


def test_validator_can_gate_otherwise_observed_evidence_without_discarding_provenance() -> None:
    class SourcePolicy:
        def validate(self, claim: Claim) -> EvidenceVerdict:
            assert claim.evidence.source_url == "https://directory.example/acme"
            return EvidenceVerdict("needs_review", "directory is not an authoritative source")

    result = ResearchEngine(
        [
            ProviderSpec(
                "directory",
                lambda _: ProviderOutput(
                    claims=(claim("industry", "software", source="https://directory.example/acme"),)
                ),
            )
        ],
        evidence_validator=SourcePolicy(),
    ).run(Entity.company(domain="acme.example"), requested_fields=("industry",))

    assert result.status == "needs_review"
    assert result.attributes["industry"].value == "software"
    assert result.evidence_assessments[0].verdict.status == "needs_review"
    assert result.evidence_assessments[0].claim.evidence.source_url == "https://directory.example/acme"


def test_provider_failure_yields_partial_result_and_keeps_successful_evidence() -> None:
    def unavailable(_: Entity) -> ProviderOutput:
        raise RuntimeError("provider timeout")

    result = ResearchEngine(
        [
            ProviderSpec("unavailable", unavailable),
            ProviderSpec(
                "official",
                lambda _: ProviderOutput(
                    claims=(claim("industry", "software", source="https://acme.example/about"),)
                ),
            ),
        ]
    ).run(Entity.company(domain="acme.example"), requested_fields=("industry",))

    assert result.status == "partial"
    assert result.attributes["industry"].source_url == "https://acme.example/about"
    assert result.provider_runs[0].status == "failed"
    assert result.provider_runs[0].error == "provider timeout"


def test_missing_required_field_never_reports_completed() -> None:
    result = ResearchEngine(
        [ProviderSpec("official", lambda _: ProviderOutput(claims=()))]
    ).run(Entity.company(domain="acme.example"), requested_fields=("industry",))

    assert result.status == "needs_review"
    assert result.missing == ("industry",)
    assert result.review_fields == ("industry",)
