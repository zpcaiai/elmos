"""Runner Update Supply Chain Engine (Batch 40 - Skill 1385).

Governs private and hosted runner binary release packages, cryptographic signing,
Cosign attestations, staged fleet rollouts, node version compliance, and
emergency release revocations across runner channels (Canary, Stable, LTS).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    RunnerChannel,
    RunnerNodeFleetStatus,
    RunnerReleasePackage,
    RunnerUpdateStatus,
)


class RunnerUpdateSupplyChainEngine:
    """Industrial engine for runner binary supply chain security and updates (B40)."""

    def __init__(self):
        self._releases: Dict[str, RunnerReleasePackage] = {}
        self._nodes: Dict[str, RunnerNodeFleetStatus] = {}

    def create_release_package(
        self,
        version: str,
        channel: RunnerChannel,
        binary_digest_sha256: str,
        minimum_agent_version: str = "1.0.0",
    ) -> RunnerReleasePackage:
        """Register a new candidate runner release package in DRAFT state."""
        if not binary_digest_sha256 or len(binary_digest_sha256) != 64:
            raise ValueError("binary_digest_sha256 must be a valid 64-char hexadecimal SHA-256 string")

        for r in self._releases.values():
            if r.version == version and r.channel == channel:
                raise ValueError(f"Release version '{version}' already exists for channel '{channel.value}'")

        release_id = f"rel-{channel.value[:3]}-{uuid.uuid4().hex[:6]}"
        pkg = RunnerReleasePackage(
            release_id=release_id,
            version=version,
            channel=channel,
            binary_digest_sha256=binary_digest_sha256,
            signature="",
            cosign_attestation_ref="",
            status=RunnerUpdateStatus.DRAFT,
            released_at=datetime.now(timezone.utc).isoformat(),
            minimum_agent_version=minimum_agent_version,
            revocation_reason="",
        )
        self._releases[release_id] = pkg
        return pkg

    def sign_release(
        self,
        release_id: str,
        signing_key: str = "elmos-runner-signing-key",
        cosign_ref: str = "",
    ) -> RunnerReleasePackage:
        """Sign release package with cryptographic signature and Cosign provenance ref."""
        pkg = self._releases.get(release_id)
        if not pkg:
            raise ValueError(f"Release '{release_id}' not found")
        if pkg.status != RunnerUpdateStatus.DRAFT:
            raise ValueError(f"Cannot sign release in status '{pkg.status.value}'")

        payload = f"{pkg.release_id}:{pkg.version}:{pkg.channel.value}:{pkg.binary_digest_sha256}"
        sig = hmac.new(signing_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

        pkg.signature = sig
        pkg.cosign_attestation_ref = cosign_ref or f"rekor://attestations/{pkg.binary_digest_sha256[:16]}"
        pkg.status = RunnerUpdateStatus.SIGNED
        return pkg

    def stage_release(self, release_id: str) -> RunnerReleasePackage:
        """Stage signed release for canary testing and integration."""
        pkg = self._releases.get(release_id)
        if not pkg:
            raise ValueError(f"Release '{release_id}' not found")
        if pkg.status != RunnerUpdateStatus.SIGNED:
            raise ValueError(f"Only SIGNED releases can be staged, current status is '{pkg.status.value}'")

        pkg.status = RunnerUpdateStatus.STAGED
        return pkg

    def deploy_release(self, release_id: str) -> RunnerReleasePackage:
        """Promote staged release to general availability for node fleet upgrades."""
        pkg = self._releases.get(release_id)
        if not pkg:
            raise ValueError(f"Release '{release_id}' not found")
        if pkg.status != RunnerUpdateStatus.STAGED:
            raise ValueError(f"Only STAGED releases can be deployed, current status is '{pkg.status.value}'")

        pkg.status = RunnerUpdateStatus.DEPLOYED
        return pkg

    def revoke_release(
        self,
        release_id: str,
        revocation_reason: str,
    ) -> RunnerReleasePackage:
        """Emergency revoke a release due to security defect or CVE."""
        pkg = self._releases.get(release_id)
        if not pkg:
            raise ValueError(f"Release '{release_id}' not found")
        if not revocation_reason.strip():
            raise ValueError("Revocation reason cannot be empty")

        pkg.status = RunnerUpdateStatus.REVOKED
        pkg.revocation_reason = revocation_reason
        return pkg

    def register_fleet_node(
        self,
        node_id: str,
        current_version: str,
    ) -> RunnerNodeFleetStatus:
        """Register or update runner fleet node status."""
        node = RunnerNodeFleetStatus(
            node_id=node_id,
            current_version=current_version,
            target_version=current_version,
            update_in_progress=False,
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
            update_failed=False,
        )
        self._nodes[node_id] = node
        return node

    def trigger_node_update(
        self,
        node_id: str,
        release_id: str,
    ) -> RunnerNodeFleetStatus:
        """Dispatch targeted binary upgrade to a fleet node with release validation."""
        node = self._nodes.get(node_id)
        if not node:
            raise ValueError(f"Node '{node_id}' not found")

        pkg = self._releases.get(release_id)
        if not pkg:
            raise ValueError(f"Release '{release_id}' not found")

        if pkg.status != RunnerUpdateStatus.DEPLOYED:
            raise ValueError(f"Cannot update node to release with status '{pkg.status.value}' (must be DEPLOYED)")

        node.target_version = pkg.version
        node.update_in_progress = True
        node.update_failed = False
        return node

    def complete_node_update(
        self,
        node_id: str,
        success: bool,
    ) -> RunnerNodeFleetStatus:
        """Record outcome of runner node update operation."""
        node = self._nodes.get(node_id)
        if not node:
            raise ValueError(f"Node '{node_id}' not found")

        node.update_in_progress = False
        if success:
            node.current_version = node.target_version
            node.update_failed = False
        else:
            node.update_failed = True
            node.target_version = node.current_version

        node.last_heartbeat = datetime.now(timezone.utc).isoformat()
        return node

    def get_fleet_rollout_progress(self, target_version: str) -> Dict[str, Any]:
        """Calculate percentage of nodes upgraded to target version."""
        if not self._nodes:
            return {
                "target_version": target_version,
                "total_nodes": 0,
                "upgraded_nodes": 0,
                "in_progress_nodes": 0,
                "failed_nodes": 0,
                "rollout_percentage": 0.0,
            }

        total = len(self._nodes)
        upgraded = sum(1 for n in self._nodes.values() if n.current_version == target_version)
        in_progress = sum(1 for n in self._nodes.values() if n.update_in_progress)
        failed = sum(1 for n in self._nodes.values() if n.update_failed)
        pct = round((upgraded / total) * 100.0, 2)

        return {
            "target_version": target_version,
            "total_nodes": total,
            "upgraded_nodes": upgraded,
            "in_progress_nodes": in_progress,
            "failed_nodes": failed,
            "rollout_percentage": pct,
        }

    def get_release(self, release_id: str) -> Optional[RunnerReleasePackage]:
        """Retrieve release by ID."""
        return self._releases.get(release_id)

    def list_releases(
        self,
        channel: Optional[RunnerChannel] = None,
        status: Optional[RunnerUpdateStatus] = None,
    ) -> List[RunnerReleasePackage]:
        """List releases, optionally filtered by channel or status."""
        results = list(self._releases.values())
        if channel:
            results = [r for r in results if r.channel == channel]
        if status:
            results = [r for r in results if r.status == status]
        return results
