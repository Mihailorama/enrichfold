"""Grounding validator: check a claim's value against its source page text.

An optional, network-touching :class:`~enrichfold.research.EvidenceValidator`.
Like :class:`~enrichfold.keenable.KeenableProvider`, it is a standalone adapter:
enrichfold's core (``models``, ``pipeline``, ``research``, ``identity``) never
imports it and gains no HTTP client. The adapter does I/O only through a
caller-supplied ``fetch(url) -> str`` callable, so "core never fetches" stays
true. The host wires the fetcher in, for example a Scrapefold-backed
``lambda url: scrapefold.scrape_sync(url).text``.

The validator adds no claims. It only returns an
:class:`~enrichfold.research.EvidenceVerdict`, honoring the ``EvidenceValidator``
contract that a validator "must not perform hidden enrichment".

The citation matcher (:func:`find_citations`) is a stdlib-only port of
Scrapefold's two-pass exact-then-normalized substring match. It is vendored
here rather than imported so enrichfold keeps no dependency on Scrapefold and
stays offline-testable.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .models import Claim
from .research import EvidenceVerdict

Fetcher = Callable[[str], str]

_WHITESPACE = re.compile(r"\s+")
_CREDENTIALS_IN_URL = re.compile(r"(https?://)[^/@\s]+@")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(token|api[_-]?key|authorization)\s*[=:]\s*[^\s,;]+"
)


def _normalize(text: str) -> str:
    """Case-fold and collapse runs of whitespace to a single space."""

    return _WHITESPACE.sub(" ", text.casefold()).strip()


def _as_text(value: object) -> str:
    """Render a claim/attribute value as the string to look for in the source."""

    return value.strip() if isinstance(value, str) else str(value)


def _safe_reason(error: BaseException) -> str:
    """Bounded error text with URL credentials and secret assignments redacted."""

    message = _CREDENTIALS_IN_URL.sub(r"\1[redacted]@", str(error))
    message = _SECRET_ASSIGNMENT.sub(r"\1=[redacted]", message)
    return message[:200] or type(error).__name__


@dataclass(frozen=True)
class CitationCoverage:
    """How well a set of target strings is grounded in a source text.

    ``coverage`` is ``matched / total`` in ``[0, 1]``. ``matched`` and
    ``unmatched`` keep the exact targets, in first-seen order, so a verdict
    reason can name what was and was not found.
    """

    coverage: float
    matched: tuple[str, ...]
    unmatched: tuple[str, ...]


def find_citations(text: str, targets: Iterable[str]) -> CitationCoverage:
    """Two-pass exact-then-normalized substring match, returning coverage.

    Pass 1 looks for each target verbatim in ``text``. A target that misses is
    retried in pass 2 against a case- and whitespace-normalized copy of both
    sides. A target found by either pass counts as matched. Blank targets are
    ignored and duplicates are collapsed so they do not inflate the total.

    This mirrors Scrapefold's ``find_citations`` algorithm but is kept here as
    stdlib-only code to avoid a hard enrichfold -> scrapefold dependency.
    """

    candidates = tuple(dict.fromkeys(t.strip() for t in targets if t and t.strip()))
    if not candidates:
        return CitationCoverage(0.0, (), ())
    normalized_text = _normalize(text)
    matched: list[str] = []
    unmatched: list[str] = []
    for target in candidates:
        if target in text or _normalize(target) in normalized_text:
            matched.append(target)
        else:
            unmatched.append(target)
    return CitationCoverage(len(matched) / len(candidates), tuple(matched), tuple(unmatched))


class GroundingValidator:
    """Ground a provider claim against the text of its own ``source_url``.

    ``validate`` fetches ``claim.evidence.source_url`` through the injected
    ``fetch`` callable and checks that the claim's asserted value - and, by
    default, any ``evidence.attributes`` values - actually appear on that page.

    Verdicts:

    - ``accepted`` when coverage reaches ``min_accept_coverage`` (all values by
      default).
    - ``rejected`` when no value is found.
    - ``needs_review`` when only some values are found, when the value cannot be
      grounded, or when the fetch fails - never an uncaught exception.
    """

    def __init__(
        self,
        fetch: Fetcher,
        *,
        min_accept_coverage: float = 1.0,
        include_attributes: bool = True,
    ) -> None:
        if not callable(fetch):
            raise TypeError("GroundingValidator requires a callable fetch(url) -> str")
        if not 0.0 < min_accept_coverage <= 1.0:
            raise ValueError("min_accept_coverage must be within (0, 1]")
        self._fetch = fetch
        self._min_accept_coverage = min_accept_coverage
        self._include_attributes = include_attributes

    def validate(self, claim: Claim) -> EvidenceVerdict:
        targets = self._targets(claim)
        if not targets:
            return EvidenceVerdict("needs_review", "claim has no groundable value")
        try:
            text = self._fetch(claim.evidence.source_url)
        except Exception as error:  # noqa: BLE001 - a fetch failure is a normal outcome, never propagated.
            return EvidenceVerdict("needs_review", f"could not fetch source: {_safe_reason(error)}")
        if not isinstance(text, str):
            return EvidenceVerdict("needs_review", "fetch returned no text for source")
        return self._verdict(find_citations(text, targets))

    def _targets(self, claim: Claim) -> tuple[str, ...]:
        values = [_as_text(claim.value)]
        if self._include_attributes:
            values.extend(_as_text(value) for value in claim.evidence.attributes.values())
        return tuple(value for value in values if value)

    def _verdict(self, coverage: CitationCoverage) -> EvidenceVerdict:
        total = len(coverage.matched) + len(coverage.unmatched)
        found = len(coverage.matched)
        if coverage.coverage >= self._min_accept_coverage:
            return EvidenceVerdict("accepted", f"grounded {found}/{total} value(s) in source")
        if coverage.coverage == 0.0:
            return EvidenceVerdict("rejected", f"no asserted value found in source (0/{total})")
        unmatched = ", ".join(coverage.unmatched)
        return EvidenceVerdict(
            "needs_review",
            f"grounded {found}/{total} value(s) in source; unmatched: {unmatched}",
        )


__all__ = ["CitationCoverage", "Fetcher", "GroundingValidator", "find_citations"]
