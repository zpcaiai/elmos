"""Factory for the physical middleware bundle used by B38-B45 engines."""

from __future__ import annotations

from dataclasses import dataclass

from elmos_mature_platform.physical.cloud_vendor import CloudVendorControlPlaneDriver
from elmos_mature_platform.physical.kubernetes_api import KubernetesControlPlaneDriver
from elmos_mature_platform.physical.sigstore_cosign import SigstoreCosignDriver
from elmos_mature_platform.physical.toxiproxy import ToxiproxyDriver
from elmos_mature_platform.physical.vault_transit import VaultTransitDriver


@dataclass
class PhysicalBundle:
    sigstore: SigstoreCosignDriver
    kubernetes: KubernetesControlPlaneDriver
    vault: VaultTransitDriver
    toxiproxy: ToxiproxyDriver
    cloud: CloudVendorControlPlaneDriver

    @classmethod
    def from_env(cls) -> "PhysicalBundle":
        return cls(
            sigstore=SigstoreCosignDriver.from_env(),
            kubernetes=KubernetesControlPlaneDriver.from_env(),
            vault=VaultTransitDriver.from_env(),
            toxiproxy=ToxiproxyDriver.from_env(),
            cloud=CloudVendorControlPlaneDriver.from_env(),
        )

    @classmethod
    def for_loopback(cls, base_url: str) -> "PhysicalBundle":
        root = base_url.rstrip("/")
        return cls(
            sigstore=SigstoreCosignDriver(rekor_url=root, fulcio_url=root),
            kubernetes=KubernetesControlPlaneDriver(api_url=root),
            vault=VaultTransitDriver(vault_addr=root, vault_token="elmos-root"),
            toxiproxy=ToxiproxyDriver(base_url=root),
            cloud=CloudVendorControlPlaneDriver(
                aws_endpoint=root,
                gcp_endpoint=root,
                azure_endpoint=root,
            ),
        )
