"""Treg catalog calls and an explicit research adapter for JSON endpoints."""

from __future__ import annotations

import asyncio
import math
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .models import Claim, Entity
from .research import ProviderOutput

_ENDPOINT_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]*\Z")
_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class TregResponse:
    data: Any
    call_id: str | None
    cost_usd: float
    served_by: str | None


class TregClient:
    """Call a catalog endpoint with a Treg token; return its unmodified JSON."""

    def __init__(self, token: str | None = None, *, org: str | None = None) -> None:
        self.token = (token or os.getenv("TREG_TOKEN", "")).strip()
        if not self.token:
            raise ValueError("Treg requires token or TREG_TOKEN")
        self.org = org or os.getenv("TREG_ORG")

    async def call(
        self,
        endpoint_id: str,
        *,
        method: str = "POST",
        request: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        max_cost_usd: float | None = 1.0,
        timeout_s: float = 30.0,
    ) -> TregResponse:
        """Send one catalog call. ``request`` becomes query params for GET, JSON otherwise."""
        if not _ENDPOINT_ID.fullmatch(endpoint_id):
            raise ValueError("invalid Treg catalog endpoint id")
        method = method.upper()
        if method not in _METHODS:
            raise ValueError("unsupported Treg method")
        if max_cost_usd is not None and (
            not math.isfinite(max_cost_usd) or max_cost_usd < 0
        ):
            raise ValueError("max_cost_usd must be finite and non-negative")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be positive")

        import httpx  # optional search dependency; core imports stay stdlib-only

        headers = {"X-Treg-Token": self.token}
        if self.org:
            headers["X-Treg-Org"] = self.org
        if max_cost_usd is not None:
            headers["X-Treg-Route-Max-Cost"] = str(max_cost_usd)
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.request(
                method,
                f"https://treg.to/call/{endpoint_id}",
                headers=headers,
                params={**(request or {}), **(params or {})}
                if method == "GET"
                else params,
                json=request if method != "GET" else None,
            )
        if response.is_error:
            raise RuntimeError(
                f"Treg {endpoint_id} returned HTTP {response.status_code}"
            )
        if response.status_code == 202:
            call_id = response.headers.get("X-Treg-Call-Id", "unknown")
            raise RuntimeError(
                f"Treg task is pending (call_id={call_id}); poll it instead of resubmitting"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError(f"Treg {endpoint_id} returned non-JSON data") from exc
        cost_micro = response.headers.get("X-Treg-Cost-Micro", "0")
        try:
            cost_usd = int(cost_micro) / 1_000_000
        except ValueError as exc:
            raise ValueError("invalid Treg cost header") from exc
        return TregResponse(
            data=data,
            call_id=response.headers.get("X-Treg-Call-Id"),
            cost_usd=cost_usd,
            served_by=response.headers.get("X-Treg-Served-By"),
        )


class TregProvider:
    """Use any JSON catalog endpoint in ResearchEngine with caller-owned claims."""

    def __init__(
        self,
        endpoint_id: str,
        request: Mapping[str, Any] | Callable[[Entity], Mapping[str, Any]],
        map_response: Callable[[Entity, Any], Iterable[Claim]],
        *,
        method: str = "POST",
        params: Mapping[str, Any] | Callable[[Entity], Mapping[str, Any]] | None = None,
        token: str | None = None,
        org: str | None = None,
        max_cost_usd: float = 1.0,
        timeout_s: float = 90.0,
        usage_units: float = 0.0,
    ) -> None:
        if usage_units < 0:
            raise ValueError("usage_units must be non-negative")
        self._client = TregClient(token, org=org)
        self._endpoint_id = endpoint_id
        self._request = request
        self._map_response = map_response
        self._method = method
        self._params = params
        self._max_cost_usd = max_cost_usd
        self._timeout_s = timeout_s
        self._usage_units = usage_units

    def research(self, entity: Entity) -> ProviderOutput:
        request = self._request(entity) if callable(self._request) else self._request
        response = asyncio.run(
            self._client.call(
                self._endpoint_id,
                method=self._method,
                request=request,
                params=self._params(entity) if callable(self._params) else self._params,
                max_cost_usd=self._max_cost_usd,
                timeout_s=self._timeout_s,
            )
        )
        metadata = {
            "endpoint_id": self._endpoint_id,
            "cost_usd": str(response.cost_usd),
        }
        if response.call_id:
            metadata["call_id"] = response.call_id
        if response.served_by:
            metadata["served_by"] = response.served_by
        return ProviderOutput(
            claims=self._map_response(entity, response.data),
            usage_units=self._usage_units,
            metadata=metadata,
        )


__all__ = ["TregClient", "TregProvider", "TregResponse"]
