"""Customer Audit Evidence Engine (Batch 40 - Skill 1390).

Automates the compilation, Merkle-root sealing, cryptographic attestation,
and integrity verification of customer compliance audit evidence packages
(SOC2, ISO27001, HIPAA, PCI-DSS, etc.).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    AuditEvidenceType,
    ComplianceFramework,
    CustomerAuditArtifact,
    CustomerAuditEvidencePackage,
)


class CustomerAuditEvidenceEngine:
    """Industrial engine for assembling and verifying customer audit evidence packages (B40)."""

    def __init__(self, default_expiry_hours: int = 72):
        self.default_expiry_hours = default_expiry_hours
        self._packages: Dict[str, CustomerAuditEvidencePackage] = {}
        self._signatures: Dict[str, str] = {}  # package_id -> signature_hex

    def initiate_package(
        self,
        customer_id: str,
        framework: ComplianceFramework,
        expiry_hours: Optional[int] = None,
    ) -> CustomerAuditEvidencePackage:
        """Create a new empty evidence package in 'preparing' state."""
        hours = expiry_hours if expiry_hours is not None else self.default_expiry_hours
        package_id = f"pkg-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(hours=hours)

        package = CustomerAuditEvidencePackage(
            package_id=package_id,
            customer_id=customer_id,
            framework=framework,
            artifacts=[],
            status="preparing",
            merkle_root="",
            download_expiry=expiry.isoformat(),
            generated_at=now.isoformat(),
        )
        self._packages[package_id] = package
        return package

    def add_artifact(
        self,
        package_id: str,
        evidence_type: AuditEvidenceType,
        title: str,
        content_bytes: bytes,
    ) -> CustomerAuditArtifact:
        """Compute SHA-256 digest and size of raw evidence bytes, then attach artifact to package."""
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Package '{package_id}' not found")
        if package.status == "sealed":
            raise ValueError(f"Cannot add artifact to sealed package '{package_id}'")

        checksum = hashlib.sha256(content_bytes).hexdigest()
        artifact_id = f"art-{evidence_type.value[:4]}-{uuid.uuid4().hex[:6]}"
        artifact = CustomerAuditArtifact(
            artifact_id=artifact_id,
            evidence_type=evidence_type,
            title=title,
            checksum_sha256=checksum,
            collected_at=datetime.now(timezone.utc).isoformat(),
            file_size_bytes=len(content_bytes),
        )
        package.artifacts.append(artifact)
        return artifact

    def add_precomputed_artifact(
        self,
        package_id: str,
        artifact: CustomerAuditArtifact,
    ) -> CustomerAuditArtifact:
        """Attach an existing verified artifact with precomputed checksum."""
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Package '{package_id}' not found")
        if package.status == "sealed":
            raise ValueError(f"Cannot add artifact to sealed package '{package_id}'")
        if not artifact.checksum_sha256:
            raise ValueError("Artifact must have a non-empty checksum_sha256")

        package.artifacts.append(artifact)
        return artifact

    def compute_merkle_root(self, package_id: str) -> str:
        """Compute a deterministic Merkle root from the SHA-256 hashes of all artifacts."""
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Package '{package_id}' not found")

        if not package.artifacts:
            # Hash of empty string for empty set
            return hashlib.sha256(b"").hexdigest()

        # Sort leaf hashes deterministically
        hashes = sorted([art.checksum_sha256.lower() for art in package.artifacts])

        # Iteratively pair and hash until single root remains
        current_layer = [bytes.fromhex(h) for h in hashes]
        while len(current_layer) > 1:
            next_layer = []
            for i in range(0, len(current_layer), 2):
                left = current_layer[i]
                right = current_layer[i + 1] if (i + 1 < len(current_layer)) else left
                combined = hashlib.sha256(left + right).digest()
                next_layer.append(combined)
            current_layer = next_layer

        return current_layer[0].hex()

    def seal_and_sign(
        self,
        package_id: str,
        notary_key: str = "elmos-audit-notary-secret",
    ) -> CustomerAuditEvidencePackage:
        """Calculate Merkle root, seal package against modifications, and generate HMAC signature."""
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Package '{package_id}' not found")
        if not package.artifacts:
            raise ValueError("Cannot seal an empty evidence package")

        merkle_root = self.compute_merkle_root(package_id)
        package.merkle_root = merkle_root
        package.status = "sealed"

        # Generate HMAC-SHA256 signature
        payload = f"{package.package_id}:{package.customer_id}:{package.framework.value}:{merkle_root}"
        sig = hmac.new(notary_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        self._signatures[package_id] = sig

        return package

    def verify_package_integrity(
        self,
        package_id: str,
        notary_key: str = "elmos-audit-notary-secret",
    ) -> Dict[str, Any]:
        """Verify that current artifacts match the sealed Merkle root and cryptographic signature."""
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Package '{package_id}' not found")

        if package.status != "sealed":
            return {
                "package_id": package_id,
                "verified": False,
                "reason": f"Package status is '{package.status}', must be 'sealed'",
                "merkle_match": False,
                "signature_valid": False,
            }

        recomputed_root = self.compute_merkle_root(package_id)
        merkle_match = (recomputed_root == package.merkle_root)

        stored_sig = self._signatures.get(package_id)
        payload = f"{package.package_id}:{package.customer_id}:{package.framework.value}:{package.merkle_root}"
        expected_sig = hmac.new(notary_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        signature_valid = (stored_sig == expected_sig)

        verified = merkle_match and signature_valid
        return {
            "package_id": package_id,
            "verified": verified,
            "merkle_match": merkle_match,
            "signature_valid": signature_valid,
            "expected_merkle_root": package.merkle_root,
            "recomputed_merkle_root": recomputed_root,
            "artifact_count": len(package.artifacts),
        }

    def check_download_validity(self, package_id: str) -> bool:
        """Check if package is sealed and within its download expiry window."""
        package = self._packages.get(package_id)
        if not package or package.status != "sealed":
            return False

        try:
            exp_time = datetime.fromisoformat(package.download_expiry)
            now = datetime.now(timezone.utc)
            return now <= exp_time
        except Exception:
            return False

    def get_package_report(self, package_id: str) -> Dict[str, Any]:
        """Generate summary report of artifacts by evidence type and total volume."""
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Package '{package_id}' not found")

        by_type: Dict[str, int] = {}
        for t in AuditEvidenceType:
            by_type[t.value] = 0

        total_bytes = 0
        for art in package.artifacts:
            by_type[art.evidence_type.value] = by_type.get(art.evidence_type.value, 0) + 1
            total_bytes += art.file_size_bytes

        return {
            "package_id": package.package_id,
            "customer_id": package.customer_id,
            "framework": package.framework.value,
            "status": package.status,
            "artifact_count": len(package.artifacts),
            "total_size_bytes": total_bytes,
            "merkle_root": package.merkle_root,
            "is_valid_for_download": self.check_download_validity(package_id),
            "by_evidence_type": by_type,
        }

    def get_package(self, package_id: str) -> Optional[CustomerAuditEvidencePackage]:
        """Retrieve package by ID."""
        return self._packages.get(package_id)

    def list_packages(self, customer_id: Optional[str] = None) -> List[CustomerAuditEvidencePackage]:
        """List packages, optionally filtered by customer ID."""
        if customer_id:
            return [p for p in self._packages.values() if p.customer_id == customer_id]
        return list(self._packages.values())
