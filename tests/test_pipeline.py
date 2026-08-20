from enrichfold import (
    Claim,
    Entity,
    EnrichmentPipeline,
    Evidence,
    derive_company_identity,
    reconcile_claims,
)


class CompanyProvider:
    def discover(self, entity: Entity) -> list[Evidence]:
        assert entity.identifiers == {"domain": "example.com"}
        return [
            Evidence(
                source_url="https://example.com/team",
                observed_at="2026-08-20T12:00:00Z",
                confidence=0.94,
                attributes={"industry": "software", "company_size": "51-200"},
            )
        ]


def test_enriches_a_company_with_provenance() -> None:
    result = EnrichmentPipeline([CompanyProvider()]).enrich(Entity.company(domain="example.com"))

    assert result.attributes["industry"].value == "software"
    assert result.attributes["industry"].source_url == "https://example.com/team"
    assert result.attributes["industry"].confidence == 0.94
    assert result.missing == ()


def test_uses_stronger_evidence_for_a_conflicting_value() -> None:
    weak = Evidence(
        source_url="https://directory.example/acme",
        observed_at="2026-08-20T12:00:00Z",
        confidence=0.30,
        attributes={"industry": "retail"},
    )
    strong = Evidence(
        source_url="https://acme.example/about",
        observed_at="2026-08-20T12:00:00Z",
        confidence=0.90,
        attributes={"industry": "software"},
    )

    result = EnrichmentPipeline([lambda entity: [weak, strong]]).enrich(Entity.company(domain="acme.example"))

    assert result.attributes["industry"].value == "software"
    assert result.attributes["industry"].source_url == "https://acme.example/about"


def test_identity_requires_review_for_an_unverified_corporate_domain() -> None:
    identity = derive_company_identity(
        email="partnerships@parent-company.example",
        company_name="Acme Labs",
        website=None,
    )

    assert identity.status == "needs_review"
    assert identity.canonical_domain == "parent-company.example"
    assert identity.reason == "corporate_email_domain_unverified"


def test_identity_accepts_matching_corporate_domain_and_site() -> None:
    identity = derive_company_identity(
        email="hello@acme.example",
        company_name="Acme",
        website="https://www.acme.example/about",
    )

    assert identity.status == "verified"
    assert identity.canonical_domain == "acme.example"
    assert identity.website == "https://acme.example"
    assert identity.reason == "matching_email_and_website"


def test_identity_does_not_trust_a_free_mailbox_with_a_supplied_site() -> None:
    identity = derive_company_identity(
        email="person@gmail.com",
        company_name="Acme",
        website="https://acme.example",
    )

    assert identity.status == "needs_review"
    assert identity.reason == "free_email_with_unverified_website"


def test_identity_detects_a_corporate_domain_conflict() -> None:
    identity = derive_company_identity(
        email="hello@acme.example",
        company_name="Acme",
        website="https://unrelated.example",
    )

    assert identity.status == "needs_review"
    assert identity.reason == "domain_conflict"


def test_reconciliation_marks_differing_observations_for_review() -> None:
    result = reconcile_claims(
        [
            Claim(
                field="industry",
                value="software",
                evidence=Evidence(
                    source_url="https://acme.example/about",
                    observed_at="2026-08-20T12:00:00Z",
                    confidence=0.91,
                    attributes={},
                ),
            ),
            Claim(
                field="industry",
                value="retail",
                evidence=Evidence(
                    source_url="https://directory.example/acme",
                    observed_at="2026-08-20T12:00:00Z",
                    confidence=0.88,
                    attributes={},
                ),
            ),
        ]
    )

    resolution = result.fields["industry"]
    assert resolution.status == "needs_review"
    assert resolution.value == "software"
    assert len(resolution.alternatives) == 1


def test_reconciliation_requires_review_for_an_inferred_claim() -> None:
    result = reconcile_claims(
        [
            Claim(
                field="market",
                value="Europe",
                kind="inferred",
                evidence=Evidence(
                    source_url="https://acme.example/press",
                    observed_at="2026-08-20T12:00:00Z",
                    confidence=0.99,
                    attributes={},
                ),
            )
        ]
    )

    assert result.requires_review is True
    assert result.review_fields == ("market",)
    assert result.fields["market"].status == "needs_review"


def test_pipeline_exposes_conflicts_without_dropping_deterministic_value() -> None:
    first = Evidence(
        source_url="https://acme.example/about",
        observed_at="2026-08-20T12:00:00Z",
        confidence=0.91,
        attributes={"industry": "software"},
    )
    second = Evidence(
        source_url="https://directory.example/acme",
        observed_at="2026-08-20T12:00:00Z",
        confidence=0.88,
        attributes={"industry": "retail"},
    )

    result = EnrichmentPipeline([lambda entity: [first, second]]).enrich(Entity.company(domain="acme.example"))

    assert result.attributes["industry"].value == "software"
    assert result.review_fields == ("industry",)
