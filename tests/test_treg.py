"""Treg's routed search and generic research boundary stay explicit."""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from enrichfold import (
    Claim,
    Entity,
    Evidence,
    ProviderSpec,
    ResearchEngine,
    TregProvider,
)
from enrichfold.search.engines import get_search_engine
from enrichfold.search.options import SearchOptions
from enrichfold.treg import TregClient, TregResponse


async def test_treg_search_routes_and_keeps_provenance(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://treg.to/call/treg.web.search",
        json={
            "output": {
                "results": [
                    {
                        "url": "https://example.com",
                        "title": "Example",
                        "snippet": "A site",
                    }
                ]
            }
        },
        headers={
            "X-Treg-Call-Id": "call-123",
            "X-Treg-Cost-Micro": "2500",
            "X-Treg-Served-By": "serper.web.search",
        },
    )
    hits = await get_search_engine("treg")(api_key="test-token").search(
        "example", SearchOptions(count=3)
    )
    request = httpx_mock.get_requests()[0]
    assert request.headers["X-Treg-Token"] == "test-token"
    assert request.headers["X-Treg-Route-Max-Cost"] == "1.0"
    assert json.loads(request.content) == {"q": "example", "limit": 3}
    assert [(hit.url, hit.engine, hit.raw["treg_served_by"]) for hit in hits] == [
        ("https://example.com", "treg", "serper.web.search")
    ]


async def test_treg_client_rejects_bad_endpoint_and_sanitizes_http_error(
    httpx_mock: HTTPXMock,
) -> None:
    client = TregClient("secret-token")
    with pytest.raises(ValueError, match="invalid Treg catalog endpoint"):
        await client.call("https://evil.example/path")
    httpx_mock.add_response(
        method="POST", url="https://treg.to/call/treg.people.search", status_code=402
    )
    with pytest.raises(RuntimeError, match="HTTP 402") as error:
        await client.call(
            "treg.people.search", request={"company_domain": "example.com"}
        )
    assert "secret-token" not in str(error.value)


async def test_catalog_get_and_pending(httpx_mock: HTTPXMock) -> None:
    client = TregClient("test-token", org="my-team")
    httpx_mock.add_response(
        method="GET",
        url="https://treg.to/call/provider.people.lookup?name=Ada",
        json={"name": "Ada"},
    )
    response = await client.call(
        "provider.people.lookup", method="GET", request={"name": "Ada"}, max_cost_usd=0
    )
    assert response.data == {"name": "Ada"}
    assert httpx_mock.get_requests()[0].headers["X-Treg-Org"] == "my-team"
    httpx_mock.add_response(
        method="POST",
        url="https://treg.to/call/treg.people.search",
        status_code=202,
        headers={"X-Treg-Call-Id": "pending-123"},
        json={"_treg": {"outcome": "pending"}},
    )
    with pytest.raises(RuntimeError, match="pending.*pending-123"):
        await client.call(
            "treg.people.search", request={"company_domain": "example.com"}
        )


def test_treg_provider_maps_people_to_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(
        self: TregClient, endpoint_id: str, **kwargs: object
    ) -> TregResponse:
        assert endpoint_id == "treg.people.search"
        assert kwargs["request"] == {"company_domain": "example.com", "limit": 2}
        return TregResponse(
            data={
                "output": {
                    "people": [
                        {"name": "Ada", "profile_url": "https://example.com/ada"}
                    ]
                }
            },
            call_id="call-456",
            cost_usd=0.002,
            served_by="exa.people.search",
        )

    monkeypatch.setattr(TregClient, "call", fake_call)

    def map_people(entity: Entity, data: object) -> list[Claim]:
        assert isinstance(data, dict)
        person = data["output"]["people"][0]
        return [
            Claim(
                field="person_name",
                value=person["name"],
                evidence=Evidence(
                    source_url=person["profile_url"],
                    observed_at="2026-09-26T00:00:00Z",
                    confidence=0.8,
                    provider="treg",
                ),
            )
        ]

    provider = TregProvider(
        "treg.people.search",
        lambda entity: {"company_domain": entity.identifiers["domain"], "limit": 2},
        map_people,
        token="test-token",
        usage_units=1,
    )
    result = provider.research(Entity.company(domain="example.com"))
    assert result.claims[0].value == "Ada"
    assert result.metadata == {
        "endpoint_id": "treg.people.search",
        "cost_usd": "0.002",
        "call_id": "call-456",
        "served_by": "exa.people.search",
    }
    run = ResearchEngine([ProviderSpec("treg", provider, reserved_units=1)]).run(
        Entity.company(domain="example.com"), requested_fields=("person_name",)
    )
    assert run.status == "completed"
    assert run.provider_runs[0].metadata["call_id"] == "call-456"
