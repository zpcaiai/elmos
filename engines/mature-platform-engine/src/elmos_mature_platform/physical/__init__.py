"""Physical middleware drivers for the mature platform (B38-B45 / SRE)."""

from elmos_mature_platform.physical.bundle import PhysicalBundle
from elmos_mature_platform.physical.cloud_vendor import CloudVendorControlPlaneDriver
from elmos_mature_platform.physical.kubernetes_api import KubernetesControlPlaneDriver
from elmos_mature_platform.physical.loopback import IndustrialLoopback
from elmos_mature_platform.physical.protocol import PhysicalCallResult
from elmos_mature_platform.physical.sigstore_cosign import SigstoreCosignDriver
from elmos_mature_platform.physical.toxiproxy import ToxiproxyDriver
from elmos_mature_platform.physical.vault_transit import VaultTransitDriver

__all__ = [
    "CloudVendorControlPlaneDriver",
    "IndustrialLoopback",
    "KubernetesControlPlaneDriver",
    "PhysicalBundle",
    "PhysicalCallResult",
    "SigstoreCosignDriver",
    "ToxiproxyDriver",
    "VaultTransitDriver",
]
