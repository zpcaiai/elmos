"""Mature Product Evidence Pack Engine (Batch 45 - Skill 1459).

Packages, cryptographically binds, seals, and attests all certification evidence
(test outcomes, SLSA attestations, SRE telemetry, security scans, audit receipts)
into a tamper-evident Merkle-tree rooted evidence bundle.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    ComprehensiveEvidencePack,
    EvidenceArtifactEntry,
    EvidenceBundleStatus,
)


class MatureProductEvidencePackEngine:
    """Industrial engine for sealing and attesting mature release evidence bundles (B45)."""

    def __init__(self):
        self._packs: Dict[str, ComprehensiveEvidencePack] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def create_evidence_pack(
        self,
        product_name: str,
        version: str,
    ) -> ComprehensiveEvidencePack:
        """Create a new draft evidence pack."""
        pack_id = f"evp-{uuid.uuid4().hex[:8]}"
        pack = ComprehensiveEvidencePack(
            pack_id=pack_id,
            product_name=product_name,
            version=version,
            status=EvidenceBundleStatus.DRAFT,
            merkle_root_sha256="",
            total_artifacts=0,
            artifacts=[],
            release_gate_passed=False,
            sealed_at="",
            certified_by="",
        )
        self._packs[pack_id] = pack
        self._record_audit("evidence_pack_created", pack_id, {"product": product_name, "version": version})
        return pack

    def get_pack(self, pack_id: str) -> Optional[ComprehensiveEvidencePack]:
        """Retrieve an evidence pack."""
        return self._packs.get(pack_id)

    def add_artifact_entry(
        self,
        pack_id: str,
        category: str,
        content_bytes: bytes,
        attestation_signer: str = "automated-pipeline",
    ) -> EvidenceArtifactEntry:
        """Add a verified artifact entry into the evidence pack."""
        pack = self._get_pack_or_raise(pack_id)
        if pack.status == EvidenceBundleStatus.SEALED:
            raise ValueError("Cannot add artifacts to an already SEALED evidence pack")

        sha256 = hashlib.sha256(content_bytes).hexdigest()
        entry_id = f"art-{uuid.uuid4().hex[:6]}"

        entry = EvidenceArtifactEntry(
            entry_id=entry_id,
            category=category,
            artifact_sha256=sha256,
            size_bytes=len(content_bytes),
            attestation_signer=attestation_signer,
            verified=True,
        )

        pack.artifacts.append(entry)
        pack.total_artifacts = len(pack.artifacts)
        self._record_audit("artifact_added", pack_id, {"entry_id": entry_id, "category": category, "sha256": sha256})
        return entry

    def compute_merkle_root(self, pack_id: str) -> str:
        """Compute Merkle tree root hash across all artifact SHA-256 digests in pack."""
        pack = self._get_pack_or_raise(pack_id)
        if not pack.artifacts:
            return hashlib.sha256(b"empty_pack").hexdigest()

        # Sort hashes for canonical deterministic tree
        hashes = sorted([a.artifact_sha256 for a in pack.artifacts])

        while len(hashes) > 1:
            next_level: List[str] = []
            for i in range(0, len(hashes), 2):
                if i + 1 < len(hashes):
                    combined = (hashes[i] + hashes[i + 1]).encode("utf-8")
                else:
                    combined = (hashes[i] + hashes[i]).encode("utf-8")
                next_level.append(hashlib.sha256(combined).hexdigest())
            hashes = next_level

        pack.merkle_root_sha256 = hashes[0]
        return hashes[0]

    def seal_evidence_pack(
        self,
        pack_id: str,
        certifier: str,
        release_gate_passed: bool = True,
    ) -> ComprehensiveEvidencePack:
        """Seal evidence pack cryptographically, locking it from further mutations."""
        pack = self._get_pack_or_raise(pack_id)
        if not pack.artifacts:
            raise ValueError("Cannot seal evidence pack with zero artifacts")

        merkle_root = self.compute_merkle_root(pack_id)
        pack.status = EvidenceBundleStatus.SEALED
        pack.release_gate_passed = release_gate_passed
        pack.sealed_at = datetime.now(timezone.utc).isoformat()
        pack.certified_by = certifier

        self._record_audit("evidence_pack_sealed", pack_id, {
            "merkle_root": merkle_root,
            "certifier": certifier,
            "gate_passed": release_gate_passed,
        })
        return pack

    def verify_pack_integrity(self, pack_id: str, expected_merkle_root: str) -> bool:
        """Verify that current pack artifacts match the sealed Merkle root."""
        pack = self._get_pack_or_raise(pack_id)
        current_root = self.compute_merkle_root(pack_id)
        valid = (current_root == expected_merkle_root)
        if not valid:
            pack.status = EvidenceBundleStatus.TAMPERED
        return valid

    def get_evidence_pack_report(self, pack_id: str) -> Dict[str, Any]:
        """Produce structured evidence verification report."""
        pack = self._get_pack_or_raise(pack_id)
        categories: Dict[str, int] = {}
        total_size = sum(a.size_bytes for a in pack.artifacts)

        for a in pack.artifacts:
            categories[a.category] = categories.get(a.category, 0) + 1

        return {
            "pack_id": pack.pack_id,
            "product_name": pack.product_name,
            "version": pack.version,
            "status": pack.status.value,
            "merkle_root_sha256": pack.merkle_root_sha256,
            "release_gate_passed": pack.release_gate_passed,
            "sealed_at": pack.sealed_at,
            "certified_by": pack.certified_by,
            "total_artifacts": pack.total_artifacts,
            "total_size_bytes": total_size,
            "category_breakdown": categories,
        }

    def _get_pack_or_raise(self, pack_id: str) -> ComprehensiveEvidencePack:
        if pack_id not in self._packs:
            raise ValueError(f"Evidence pack {pack_id} not found")
        return self._packs[pack_id]

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
