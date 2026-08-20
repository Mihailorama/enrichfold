"""Provider-neutral, provenance-first entity enrichment."""

from .identity import (
    DEFAULT_FREE_EMAIL_DOMAINS,
    DEFAULT_GENERIC_COMPANY_NAMES,
    CompanyIdentity,
    SiteIdentity,
    canonical_website_domain,
    company_email_domain,
    company_name_matches_domain,
    derive_company_identity,
    is_free_email_domain,
    is_generic_company_name,
)
from .models import (
    Claim,
    EnrichmentResult,
    Entity,
    Evidence,
    FieldResolution,
    ReconciliationResult,
    ResolvedAttribute,
)
from .pipeline import DiscoveryProvider, EnrichmentPipeline, reconcile_claims

__all__ = [
    "Claim",
    "CompanyIdentity",
    "DEFAULT_FREE_EMAIL_DOMAINS",
    "DEFAULT_GENERIC_COMPANY_NAMES",
    "DiscoveryProvider",
    "EnrichmentPipeline",
    "EnrichmentResult",
    "Entity",
    "Evidence",
    "FieldResolution",
    "ReconciliationResult",
    "ResolvedAttribute",
    "SiteIdentity",
    "canonical_website_domain",
    "company_email_domain",
    "company_name_matches_domain",
    "derive_company_identity",
    "is_free_email_domain",
    "is_generic_company_name",
    "reconcile_claims",
]
