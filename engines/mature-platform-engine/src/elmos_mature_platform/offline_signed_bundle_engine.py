import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from elmos_mature_platform.types import (
    OfflineBundle,
    BundleArtifact,
    OfflineBundleStatus as BundleStatus
)

class OfflineSignedBundleEngine:
    """Engine for creating, managing, signing and distributing offline signed bundles."""
    
    def __init__(self):
        self.bundles: Dict[str, OfflineBundle] = {}
        self.artifacts: Dict[str, BundleArtifact] = {}

    def create_bundle(self, bundle: OfflineBundle) -> str:
        """Create a new offline bundle in DRAFT state."""
        bundle.status = BundleStatus.DRAFT
        if not bundle.created_at:
            bundle.created_at = datetime.now(timezone.utc).isoformat()
        self.bundles[bundle.bundle_id] = bundle
        return bundle.bundle_id

    def add_artifact(self, bundle_id: str, artifact: BundleArtifact) -> OfflineBundle:
        """Add an artifact to the bundle. Bundle must be in DRAFT status."""
        if bundle_id not in self.bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
        
        bundle = self.bundles[bundle_id]
        if bundle.status != BundleStatus.DRAFT:
            raise ValueError(f"Cannot add artifact to bundle in {bundle.status} status")
            
        self.artifacts[artifact.artifact_id] = artifact
        bundle.artifacts.append(artifact.artifact_id)
        bundle.total_size_bytes += artifact.size_bytes
        return bundle

    def set_install_order(self, bundle_id: str, artifact_ids: List[str]) -> OfflineBundle:
        """Set the install order. All artifact_ids must be in the bundle."""
        if bundle_id not in self.bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self.bundles[bundle_id]
        for aid in artifact_ids:
            if aid not in bundle.artifacts:
                raise ValueError(f"Artifact {aid} not in bundle {bundle_id}")
                
        bundle.install_order = artifact_ids
        return bundle

    def build_bundle(self, bundle_id: str) -> OfflineBundle:
        """Move bundle to BUILDING status, verify at least 1 artifact, compute total size."""
        if bundle_id not in self.bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self.bundles[bundle_id]
        if bundle.status != BundleStatus.DRAFT:
            raise ValueError(f"Cannot build bundle from {bundle.status} status")
            
        if not bundle.artifacts:
            raise ValueError("Bundle must have at least 1 artifact to build")
            
        total_size = sum(self.artifacts[aid].size_bytes for aid in bundle.artifacts)
        bundle.total_size_bytes = total_size
        bundle.status = BundleStatus.BUILDING
        return bundle

    def sign_bundle(self, bundle_id: str, signer: str, expiry_days: int = 90) -> OfflineBundle:
        """Sign the bundle. Must be in BUILDING status. Moves to SIGNED."""
        if bundle_id not in self.bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self.bundles[bundle_id]
        if bundle.status != BundleStatus.BUILDING:
            raise ValueError(f"Cannot sign bundle from {bundle.status} status")
            
        now = datetime.now(timezone.utc)
        bundle.signed_at = now.isoformat()
        bundle.expiry_date = (now + timedelta(days=expiry_days)).isoformat()
        bundle.signer_identity = signer
        
        sig_data = f"{bundle_id}:{signer}:{bundle.signed_at}".encode('utf-8')
        bundle.bundle_signature = hashlib.sha256(sig_data).hexdigest()
        bundle.status = BundleStatus.SIGNED
        return bundle

    def verify_bundle_signature(self, bundle_id: str) -> Dict:
        """Verify the bundle signature, expiry, and artifact digests."""
        if bundle_id not in self.bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self.bundles[bundle_id]
        if bundle.status not in (BundleStatus.SIGNED, BundleStatus.DISTRIBUTING, BundleStatus.INSTALLED):
            return {"valid": False, "reason": f"Bundle in invalid status for verification: {bundle.status}"}
            
        if not bundle.bundle_signature:
            return {"valid": False, "reason": "No bundle signature found"}
            
        sig_data = f"{bundle_id}:{bundle.signer_identity}:{bundle.signed_at}".encode('utf-8')
        expected_sig = hashlib.sha256(sig_data).hexdigest()
        if expected_sig != bundle.bundle_signature:
            return {"valid": False, "reason": "Signature mismatch"}
            
        if bundle.expiry_date:
            expiry = datetime.fromisoformat(bundle.expiry_date)
            if datetime.now(timezone.utc) > expiry:
                return {"valid": False, "reason": "Bundle expired"}
                
        for aid in bundle.artifacts:
            art = self.artifacts[aid]
            if not art.sha256_digest:
                return {"valid": False, "reason": f"Artifact {aid} missing digest"}
                
        return {"valid": True, "reason": "Signature and artifacts valid"}

    def distribute_bundle(self, bundle_id: str, target_env: str) -> OfflineBundle:
        """Move to DISTRIBUTING, add target environment. Requires SIGNED status."""
        if bundle_id not in self.bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self.bundles[bundle_id]
        if bundle.status not in (BundleStatus.SIGNED, BundleStatus.DISTRIBUTING):
            raise ValueError(f"Cannot distribute bundle from {bundle.status} status")
            
        if target_env not in bundle.target_environments:
            bundle.target_environments.append(target_env)
            
        bundle.status = BundleStatus.DISTRIBUTING
        return bundle

    def install_bundle(self, bundle_id: str, env: str) -> Dict:
        """Install bundle. Must be DISTRIBUTING or SIGNED, verify signature. Returns install_order."""
        if bundle_id not in self.bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self.bundles[bundle_id]
        if bundle.status == BundleStatus.REVOKED:
            raise ValueError("Cannot install revoked bundle")
            
        if bundle.status not in (BundleStatus.SIGNED, BundleStatus.DISTRIBUTING):
            raise ValueError(f"Cannot install bundle from {bundle.status} status")
            
        verification = self.verify_bundle_signature(bundle_id)
        if not verification["valid"]:
            raise ValueError(f"Bundle verification failed: {verification['reason']}")
            
        if not bundle.install_order:
            raise ValueError("No install order defined")
            
        bundle.status = BundleStatus.INSTALLED
        return {
            "status": "installed",
            "environment": env,
            "install_order": bundle.install_order
        }

    def revoke_bundle(self, bundle_id: str, reason: str) -> OfflineBundle:
        """Revoke a bundle."""
        if bundle_id not in self.bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self.bundles[bundle_id]
        bundle.status = BundleStatus.REVOKED
        return bundle

    def get_bundle_manifest(self, bundle_id: str) -> Dict:
        """Get full bundle manifest."""
        if bundle_id not in self.bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self.bundles[bundle_id]
        return {
            "bundle": {
                "bundle_id": bundle.bundle_id,
                "name": bundle.name,
                "target_version": bundle.target_version,
                "status": bundle.status.value,
                "created_at": bundle.created_at,
                "signed_at": bundle.signed_at,
                "expiry_date": bundle.expiry_date,
                "signer_identity": bundle.signer_identity,
                "bundle_signature": bundle.bundle_signature,
                "total_size_bytes": bundle.total_size_bytes
            },
            "artifacts": [
                {
                    "artifact_id": a,
                    "type": self.artifacts[a].artifact_type.value,
                    "sha256_digest": self.artifacts[a].sha256_digest,
                    "size_bytes": self.artifacts[a].size_bytes
                } for a in bundle.artifacts
            ],
            "install_order": bundle.install_order
        }

    def get_bundle_report(self) -> Dict:
        """Get summary of bundles."""
        status_counts = {}
        total_size = 0
        signed_count = 0
        unsigned_count = 0
        
        for bundle in self.bundles.values():
            status_counts[bundle.status.value] = status_counts.get(bundle.status.value, 0) + 1
            total_size += bundle.total_size_bytes
            if bundle.status in (BundleStatus.SIGNED, BundleStatus.DISTRIBUTING, BundleStatus.INSTALLED, BundleStatus.REVOKED):
                signed_count += 1
            else:
                unsigned_count += 1
                
        return {
            "total_bundles": len(self.bundles),
            "status_counts": status_counts,
            "total_size_bytes": total_size,
            "signed_bundles": signed_count,
            "unsigned_bundles": unsigned_count
        }
