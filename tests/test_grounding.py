from __future__ import annotations

import pytest

from enrichfold import (
    CitationCoverage,
    Claim,
    Entity,
    Evidence,
    GroundingValidator,
    ProviderOutput,
    ProviderSpec,
    ResearchEngine,
    find_citations,
)


def claim(
    field: str,
    value: object,
    *,
    source: str = "https://acme.example/about",
    attributes: dict[str, object] | None = None,
) -> Claim:
    return Claim(
        field=field,
        value=value,
        evidence=Evidence(
            source_url=source,
            observed_at="2026-08-20T12:00:00Z",
            confidence=0.9,
            attributes=attributes or {},
        ),
    )


# --- find_citations: the ported two-pass matcher -------------------------------


def test_find_citations_matches_exact_substring() -> None:
    coverage = find_citations("Acme builds software for teams.", ["software"])
    assert coverage == CitationCoverage(1.0, ("software",), ())


def test_find_citations_falls_back_to_case_and_whitespace_normalization() -> None:
    coverage = find_citations("ACME  Robotics\nInc", ["acme robotics inc"])
    assert coverage.coverage == 1.0
    assert coverage.matched == ("acme robotics inc",)


def test_find_citations_reports_partial_coverage() -> None:
    coverage = find_citations("Acme builds software.", ["software", "51-200"])
    assert coverage.coverage == pytest.approx(0.5)
    assert coverage.matched == ("software",)
    assert coverage.unmatched == ("51-200",)


def test_find_citations_reports_zero_when_absent() -> None:
    coverage = find_citations("nothing relevant here", ["software"])
    assert coverage.coverage == 0.0
    assert coverage.unmatched == ("software",)


def test_find_citations_ignores_empty_targets() -> None:
    coverage = find_citations("Acme builds software.", ["", "  ", "software"])
    assert coverage.matched == ("software",)
    assert coverage.coverage == 1.0


def test_find_citations_dedupes_repeated_targets() -> None:
    coverage = find_citations("Acme builds software.", ["software", "software"])
    assert coverage.matched == ("software",)
    assert coverage.coverage == 1.0


# --- GroundingValidator --------------------------------------------------------


def test_requires_a_callable_fetch() -> None:
    with pytest.raises(TypeError, match="callable"):
        GroundingValidator(object())  # type: ignore[arg-type]


def test_accepts_when_value_is_found_in_source() -> None:
    validator = GroundingValidator(lambda url: "Acme builds software for teams.")
    verdict = validator.validate(claim("industry", "software"))
    assert verdict.status == "accepted"
    assert "1/1" in verdict.reason


def test_grounds_attribute_values_and_reviews_when_partial() -> None:
    validator = GroundingValidator(
        lambda url: "Acme builds software for teams."
    )
    verdict = validator.validate(
        claim("industry", "software", attributes={"company_size": "51-200"})
    )
    assert verdict.status == "needs_review"
    assert "51-200" in verdict.reason


def test_rejects_when_no_value_is_found() -> None:
    validator = GroundingValidator(lambda url: "An unrelated page about cats.")
    verdict = validator.validate(claim("industry", "software"))
    assert verdict.status == "rejected"


def test_fetch_failure_is_review_not_an_exception_and_redacts_secrets() -> None:
    def fetch(url: str) -> str:
        raise RuntimeError("boom token=supersecret authorization=Bearer abc")

    validator = GroundingValidator(fetch)
    verdict = validator.validate(claim("industry", "software"))
    assert verdict.status == "needs_review"
    assert "could not fetch source" in verdict.reason
    assert "supersecret" not in verdict.reason
    assert "Bearer abc" not in verdict.reason


def test_non_string_fetch_result_is_review() -> None:
    validator = GroundingValidator(lambda url: None)  # type: ignore[arg-type,return-value]
    verdict = validator.validate(claim("industry", "software"))
    assert verdict.status == "needs_review"


def test_empty_groundable_value_is_review() -> None:
    validator = GroundingValidator(lambda url: "anything")
    verdict = validator.validate(claim("industry", ""))
    assert verdict.status == "needs_review"
    assert "groundable" in verdict.reason


def test_min_accept_coverage_allows_partial_acceptance() -> None:
    validator = GroundingValidator(
        lambda url: "Acme builds software.", min_accept_coverage=0.5
    )
    verdict = validator.validate(
        claim("industry", "software", attributes={"company_size": "51-200"})
    )
    assert verdict.status == "accepted"


def test_min_accept_coverage_is_bounded() -> None:
    with pytest.raises(ValueError, match="min_accept_coverage"):
        GroundingValidator(lambda url: "", min_accept_coverage=0.0)


def test_fetches_the_claim_source_url() -> None:
    seen: list[str] = []

    def fetch(url: str) -> str:
        seen.append(url)
        return "Acme builds software."

    GroundingValidator(fetch).validate(
        claim("industry", "software", source="https://acme.example/about")
    )
    assert seen == ["https://acme.example/about"]


# --- integration with ResearchEngine ------------------------------------------


def test_engine_routes_ungrounded_field_to_review_preserving_provenance() -> None:
    page = "Acme builds software for teams."

    def provider(_: Entity) -> ProviderOutput:
        return ProviderOutput(
            claims=(
                claim("industry", "software", source="https://acme.example/about"),
                claim("headcount", "9000", source="https://acme.example/about"),
            )
        )

    result = ResearchEngine(
        [ProviderSpec("official", provider, reserved_units=1)],
        evidence_validator=GroundingValidator(lambda url: page),
    ).run(Entity.company(domain="acme.example"), requested_fields=("industry", "headcount"))

    assert result.status == "needs_review"
    # Grounded field is accepted and resolved.
    assert result.attributes["industry"].value == "software"
    # Ungrounded value is rejected out of resolution but its field is still reported.
    assert "headcount" not in result.attributes
    assert "headcount" in result.review_fields

    # Provenance is preserved verbatim in the assessments, including the verdict.
    by_field = {a.claim.field: a for a in result.evidence_assessments}
    assert by_field["industry"].verdict.status == "accepted"
    assert by_field["headcount"].verdict.status == "rejected"
    assert by_field["headcount"].claim.value == "9000"
    assert by_field["headcount"].claim.evidence.source_url == "https://acme.example/about"
    assert by_field["industry"].provider == "official"


def test_engine_review_verdict_routes_field_to_review() -> None:
    def provider(_: Entity) -> ProviderOutput:
        return ProviderOutput(
            claims=(
                claim(
                    "industry",
                    "software",
                    attributes={"company_size": "51-200"},
                ),
            )
        )

    result = ResearchEngine(
        [ProviderSpec("official", provider, reserved_units=1)],
        evidence_validator=GroundingValidator(lambda url: "Acme builds software."),
    ).run(Entity.company(domain="acme.example"), requested_fields=("industry",))

    assert result.status == "needs_review"
    assert "industry" in result.review_fields
    # A needs_review verdict does not discard the claim from resolution.
    assert result.attributes["industry"].value == "software"
