from enrichfold import Entity, EnrichmentPipeline, Evidence


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
