from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .canonical import canonical_json_bytes, sha256_digest


@dataclass(frozen=True)
class EnvironmentInputs:
    base_image_digest: str
    setup_script_digest: str
    maintenance_script_digest: str
    lockfile_digests: tuple[str, ...]
    toolchain_digests: tuple[str, ...]
    platform: Mapping[str, str]
    approved_environment: Mapping[str, str]
    secret_reference_versions: Mapping[str, str]
    schema_version: str = "1.2.0"

    def key(self) -> str:
        return sha256_digest(
            canonical_json_bytes(
                {
                    "schema_version": self.schema_version,
                    "base_image_digest": self.base_image_digest,
                    "setup_script_digest": self.setup_script_digest,
                    "maintenance_script_digest": self.maintenance_script_digest,
                    "lockfile_digests": sorted(self.lockfile_digests),
                    "toolchain_digests": sorted(self.toolchain_digests),
                    "platform": dict(self.platform),
                    "approved_environment": dict(self.approved_environment),
                    "secret_reference_versions": dict(self.secret_reference_versions),
                }
            )
        )


@dataclass(frozen=True)
class RestoreDecision:
    restore: bool
    reason: str
    estimated_net_saved_ms: float


def choose_restore(
    *,
    restore_ms: float,
    verify_ms: float,
    rebuild_ms: float,
    snapshot_status: str = "AVAILABLE",
) -> RestoreDecision:
    if snapshot_status != "AVAILABLE":
        return RestoreDecision(False, f"SNAPSHOT_{snapshot_status}", 0.0)
    net = rebuild_ms - restore_ms - verify_ms
    if net <= 0:
        return RestoreDecision(False, "RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE", net)
    return RestoreDecision(True, "RESTORE_NET_POSITIVE", net)
