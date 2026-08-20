"""Provider-neutral, provenance-first entity enrichment."""

from .models import EnrichmentResult, Entity, Evidence, ResolvedAttribute
from .pipeline import DiscoveryProvider, EnrichmentPipeline

__all__ = [
    "DiscoveryProvider",
    "EnrichmentPipeline",
    "EnrichmentResult",
    "Entity",
    "Evidence",
    "ResolvedAttribute",
]
