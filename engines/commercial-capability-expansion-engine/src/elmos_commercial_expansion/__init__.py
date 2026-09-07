"""Read-only public surface for Commercial Capability Expansion.

Execution contracts, registries, mutable stores and handler requests are not
re-exported.  Trusted hosts integrate the explicit runtime submodule; ordinary
package callers receive catalog/status and read-only integrity inspection.
"""

from .service import (
    CommercialCapabilityExpansionService,
    get_commercial_status,
    list_capability_kernels,
)
from .store import ReadonlyControlPlaneStore

__version__ = "2.0.0"

__all__ = [
    "CommercialCapabilityExpansionService",
    "ReadonlyControlPlaneStore",
    "get_commercial_status",
    "list_capability_kernels",
]
