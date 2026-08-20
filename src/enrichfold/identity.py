"""Offline company identity checks that fail closed when evidence is weak."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Collection, Literal
from urllib.parse import urlsplit


DEFAULT_FREE_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "icloud.com",
        "proton.me",
        "protonmail.com",
        "yahoo.com",
    }
)
DEFAULT_GENERIC_COMPANY_NAMES = frozenset({"company", "unknown", "unknown company"})
_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])$",
    re.IGNORECASE,
)

IdentityStatus = Literal["verified", "needs_review"]


@dataclass(frozen=True)
class SiteIdentity:
    """A caller-verified identity read from a supplied website."""

    name: str
    domain: str


@dataclass(frozen=True)
class CompanyIdentity:
    """An identity decision that is safe to gate before enrichment or actions."""

    status: IdentityStatus
    name: str | None
    canonical_domain: str | None
    website: str | None
    slug: str | None
    reason: str

    @property
    def requires_review(self) -> bool:
        return self.status == "needs_review"


def company_email_domain(email: str) -> str | None:
    local, separator, domain = email.strip().lower().rpartition("@")
    if not separator or not local or not _DOMAIN_RE.fullmatch(domain):
        return None
    return domain


def canonical_website_domain(website: str | None) -> str | None:
    if not website or not website.strip():
        return None
    value = website.strip()
    parsed = urlsplit(value if re.match(r"^https?://", value, re.IGNORECASE) else f"https://{value}")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    hostname = parsed.hostname.lower().removeprefix("www.")
    return hostname if _DOMAIN_RE.fullmatch(hostname) else None


def is_free_email_domain(domain: str, *, free_email_domains: Collection[str] = DEFAULT_FREE_EMAIL_DOMAINS) -> bool:
    return domain.lower() in {item.lower() for item in free_email_domains}


def is_generic_company_name(name: str | None, *, generic_names: Collection[str] = DEFAULT_GENERIC_COMPANY_NAMES) -> bool:
    normalized = re.sub(r"\s+", " ", (name or "").strip().casefold())
    return not normalized or normalized in {item.strip().casefold() for item in generic_names}


def slugify(value: str) -> str:
    """Locale-safe readable slug; applications may replace it for their own URLs."""

    return "-".join(part for part in re.split(r"[^\w]+", value.casefold(), flags=re.UNICODE) if part)


def _domains_match(left: str, right: str) -> bool:
    return left == right or left.endswith(f".{right}") or right.endswith(f".{left}")


def company_name_matches_domain(name: str, domain: str) -> bool:
    """Match only the registrable-looking first label; never substring-match."""

    labels = domain.lower().removeprefix("www.").split(".")
    if len(labels) != 2:
        return False
    normalized_name = re.sub(r"[^a-z0-9]", "", name.lower())
    return bool(normalized_name) and normalized_name == labels[0].replace("-", "")


def _identity(
    *,
    status: IdentityStatus,
    name: str | None,
    domain: str | None,
    slug: str | None,
    reason: str,
) -> CompanyIdentity:
    return CompanyIdentity(
        status=status,
        name=name,
        canonical_domain=domain,
        website=f"https://{domain}" if domain else None,
        slug=slug,
        reason=reason,
    )


def derive_company_identity(
    *,
    email: str,
    company_name: str | None,
    website: str | None,
    verified_site_identity: SiteIdentity | None = None,
    free_email_domains: Collection[str] = DEFAULT_FREE_EMAIL_DOMAINS,
    generic_names: Collection[str] = DEFAULT_GENERIC_COMPANY_NAMES,
) -> CompanyIdentity:
    """Derive an identity without network access and require review by default.

    A corporate domain is only verified when it exactly matches the company
    name, or when a caller supplies independently verified same-domain site
    metadata. Free mailboxes and conflicts never become automatically verified.
    """

    name = None if is_generic_company_name(company_name, generic_names=generic_names) else company_name.strip()
    slug = slugify(name) if name else None
    email_domain = company_email_domain(email)
    website_domain = canonical_website_domain(website)

    if not name:
        return _identity(
            status="needs_review",
            name=None,
            domain=website_domain or email_domain,
            slug=None,
            reason="missing_company_name",
        )
    if not email_domain:
        return _identity(
            status="needs_review",
            name=name,
            domain=website_domain,
            slug=slug,
            reason="invalid_email",
        )
    if website and not website_domain:
        return _identity(
            status="needs_review",
            name=name,
            domain=None,
            slug=slug,
            reason="invalid_website",
        )
    if website_domain and not is_free_email_domain(email_domain, free_email_domains=free_email_domains) and not _domains_match(email_domain, website_domain):
        return _identity(
            status="needs_review",
            name=name,
            domain=website_domain,
            slug=slug,
            reason="domain_conflict",
        )
    if website_domain and is_free_email_domain(email_domain, free_email_domains=free_email_domains):
        return _identity(
            status="needs_review",
            name=name,
            domain=website_domain,
            slug=slug,
            reason="free_email_with_unverified_website",
        )
    if (
        website_domain
        and verified_site_identity
        and verified_site_identity.name.strip() == name
        and _domains_match(website_domain, verified_site_identity.domain.lower().removeprefix("www."))
    ):
        return _identity(
            status="verified",
            name=name,
            domain=website_domain,
            slug=slug,
            reason="corporate_email_domain_site_metadata",
        )
    if website_domain and company_name_matches_domain(name, website_domain):
        return _identity(
            status="verified",
            name=name,
            domain=website_domain,
            slug=slug,
            reason="matching_email_and_website",
        )
    if website_domain:
        return _identity(
            status="needs_review",
            name=name,
            domain=website_domain,
            slug=slug,
            reason="corporate_email_domain_unverified",
        )
    if is_free_email_domain(email_domain, free_email_domains=free_email_domains):
        return _identity(
            status="needs_review",
            name=name,
            domain=None,
            slug=slug,
            reason="free_email_without_website",
        )
    if company_name_matches_domain(name, email_domain):
        return _identity(
            status="verified",
            name=name,
            domain=email_domain,
            slug=slug,
            reason="corporate_email_domain",
        )
    return _identity(
        status="needs_review",
        name=name,
        domain=email_domain,
        slug=slug,
        reason="corporate_email_domain_unverified",
    )
