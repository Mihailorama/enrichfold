from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

import pytest

from enrichfold import (
    Claim,
    Entity,
    Evidence,
    KeenableProvider,
    ProviderSpec,
    ResearchEngine,
)


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        return json.dumps(
            {
                "results": [
                    {
                        "url": "https://example.com/about",
                        "description": "Acme builds software.",
                        "acquired_at": "2026-09-09T12:00:00Z",
                    }
                ]
            }
        ).encode()


def test_search_maps_keenable_results_to_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEENABLE_API_KEY", "keen_test")

    def map_results(
        entity: Entity, results: tuple[Mapping[str, Any], ...]
    ) -> list[Claim]:
        assert entity.identifiers == {"domain": "example.com"}
        result = results[0]
        return [
            Claim(
                field="summary",
                value=result["description"],
                kind="inferred",
                evidence=Evidence(
                    source_url=str(result["url"]),
                    observed_at=str(result["acquired_at"]),
                    confidence=0.8,
                    provider="keenable",
                ),
            )
        ]

    with patch("enrichfold.keenable.urlopen", return_value=Response()) as mocked_urlopen:
        provider = KeenableProvider(
            lambda entity: f'{entity.identifiers["domain"]} company',
            map_results,
            max_results=3,
        )
        result = ResearchEngine(
            [ProviderSpec("keenable", provider, reserved_units=1)]
        ).run(Entity.company(domain="example.com"), requested_fields=("summary",))

    request = mocked_urlopen.call_args.args[0]
    assert json.loads(request.data) == {"query": "example.com company", "max_results": 3}
    assert request.get_header("X-api-key") == "keen_test"
    assert result.attributes["summary"].value == "Acme builds software."
    assert result.attributes["summary"].source_url == "https://example.com/about"
    assert result.provider_runs[0].used_units == 1
    assert result.status == "needs_review"


def test_api_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="KEENABLE_API_KEY"):
        KeenableProvider("query", lambda entity, results: ())
