from typing import List, Optional, Dict
import hashlib
from datetime import datetime
from .types import (
    AirgapBundle,
    BundleComponent,
    BundleStatus,
    BundleVerification,
    BundleComponentType
)

class AirgapBundleEngine:
    def __init__(self):
        self._bundles: Dict[str, AirgapBundle] = {}
        self._revoked_bundles: Dict[str, str] = {}  # bundle_id -> reason

    def create_bundle(self, bundle: AirgapBundle) -> str:
        """Create a new airgap bundle."""
        if bundle.bundle_id in self._bundles:
            raise ValueError(f"Bundle {bundle.bundle_id} already exists")
        
        bundle.status = BundleStatus.BUILDING
        bundle.created_at = datetime.utcnow().isoformat()
        self._bundles[bundle.bundle_id] = bundle
        return bundle.bundle_id

    def add_component(self, bundle_id: str, component: BundleComponent) -> None:
        """Add a component to an existing bundle in BUILDING status."""
        if bundle_id not in self._bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
        
        bundle = self._bundles[bundle_id]
        if bundle.status != BundleStatus.BUILDING:
            raise ValueError(f"Cannot add component to bundle in {bundle.status} status")
            
        bundle.components.append(component)

    def finalize_bundle(self, bundle_id: str) -> AirgapBundle:
        """Calculate total size, manifest digest, transition to READY."""
        if bundle_id not in self._bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self._bundles[bundle_id]
        if bundle.status != BundleStatus.BUILDING:
            raise ValueError(f"Cannot finalize bundle in {bundle.status} status")

        total_size = 0
        checksums = []
        
        for comp in bundle.components:
            if not comp.checksum_sha256:
                raise ValueError(f"Component {comp.component_id} missing checksum")
            total_size += comp.size_bytes
            checksums.append(comp.checksum_sha256)
            
        bundle.total_size_bytes = total_size
        
        # Sort checksums for deterministic digest
        checksums.sort()
        manifest_str = "".join(checksums)
        bundle.manifest_digest = hashlib.sha256(manifest_str.encode()).hexdigest()
        
        bundle.status = BundleStatus.READY
        return bundle

    def sign_bundle(self, bundle_id: str, signing_key_id: str) -> AirgapBundle:
        """Sign bundle, transition to SIGNED."""
        if bundle_id not in self._bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self._bundles[bundle_id]
        if bundle.status != BundleStatus.READY:
            raise ValueError(f"Cannot sign bundle in {bundle.status} status. Must be READY.")
            
        bundle.signing_key_id = signing_key_id
        bundle.signed_at = datetime.utcnow().isoformat()
        bundle.status = BundleStatus.SIGNED
        return bundle

    def verify_bundle(self, bundle_id: str) -> BundleVerification:
        """Verify components, checksums, signature, and expiration."""
        if bundle_id not in self._bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self._bundles[bundle_id]
        
        errors = []
        all_components_present = True
        all_checksums_valid = True
        signature_valid = bool(bundle.signing_key_id and bundle.status in (BundleStatus.SIGNED, BundleStatus.DEPLOYED))
        not_expired = True
        
        if not bundle.components:
            all_components_present = False
            errors.append("No components found in bundle")
            
        for comp in bundle.components:
            if not comp.checksum_sha256:
                all_checksums_valid = False
                errors.append(f"Component {comp.component_id} missing checksum")
        
        if bundle.status == BundleStatus.BUILDING:
            all_checksums_valid = False
            errors.append("Bundle is still BUILDING, manifest not finalized")
        else:
            # Recompute manifest digest
            checksums = sorted([c.checksum_sha256 for c in bundle.components if c.checksum_sha256])
            manifest_str = "".join(checksums)
            expected_digest = hashlib.sha256(manifest_str.encode()).hexdigest()
            if bundle.manifest_digest != expected_digest:
                all_checksums_valid = False
                errors.append("Manifest digest mismatch")

        if bundle.expiry_date:
            try:
                expiry = datetime.fromisoformat(bundle.expiry_date)
                if datetime.utcnow() > expiry:
                    not_expired = False
                    errors.append("Bundle has expired")
            except ValueError:
                pass
                
        if bundle.status == BundleStatus.REVOKED:
            errors.append(f"Bundle is revoked: {self._revoked_bundles.get(bundle_id, 'Unknown reason')}")
            signature_valid = False

        overall_valid = all_components_present and all_checksums_valid and signature_valid and not_expired and bundle.status != BundleStatus.REVOKED

        return BundleVerification(
            bundle_id=bundle_id,
            all_components_present=all_components_present,
            all_checksums_valid=all_checksums_valid,
            signature_valid=signature_valid,
            not_expired=not_expired,
            overall_valid=overall_valid,
            errors=errors
        )

    def deploy_bundle(self, bundle_id: str) -> AirgapBundle:
        """Mark as deployed. Must be SIGNED and verified first."""
        if bundle_id not in self._bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self._bundles[bundle_id]
        
        if bundle.status in (BundleStatus.REVOKED, BundleStatus.EXPIRED):
            raise ValueError(f"Cannot deploy {bundle.status} bundle")
            
        if bundle.status != BundleStatus.SIGNED:
            raise ValueError(f"Cannot deploy bundle in {bundle.status} status. Must be SIGNED.")
            
        verification = self.verify_bundle(bundle_id)
        if not verification.overall_valid:
            raise ValueError(f"Cannot deploy invalid bundle: {', '.join(verification.errors)}")
            
        bundle.status = BundleStatus.DEPLOYED
        bundle.deployed_at = datetime.utcnow().isoformat()
        return bundle

    def revoke_bundle(self, bundle_id: str, reason: str) -> None:
        """Revoke a bundle."""
        if bundle_id not in self._bundles:
            raise ValueError(f"Bundle {bundle_id} not found")
            
        bundle = self._bundles[bundle_id]
        if bundle.status == BundleStatus.DEPLOYED:
            raise ValueError("Cannot revoke a deployed bundle")
            
        bundle.status = BundleStatus.REVOKED
        self._revoked_bundles[bundle_id] = reason

    def check_upgrade_path(self, from_version: str, to_version: str) -> bool:
        """Check if an upgrade path exists from 'from_version' to 'to_version'."""
        for bundle in self._bundles.values():
            if bundle.upgrade_from_version == from_version and bundle.target_version == to_version:
                return True
        return False

    def list_bundles(self, status: Optional[BundleStatus] = None) -> List[AirgapBundle]:
        """List bundles optionally filtered by status."""
        if status:
            return [b for b in self._bundles.values() if b.status == status]
        return list(self._bundles.values())

    def get_bundle_report(self) -> Dict:
        """Summary: bundles by status, total size, signed count."""
        report = {
            "total_bundles": len(self._bundles),
            "by_status": {status.value: 0 for status in BundleStatus},
            "total_size_bytes": sum(b.total_size_bytes for b in self._bundles.values()),
            "signed_count": sum(1 for b in self._bundles.values() if b.signing_key_id)
        }
        for bundle in self._bundles.values():
            report["by_status"][bundle.status.value] += 1
        return report

    def expire_bundles(self, current_date: str) -> List[str]:
        """Mark expired bundles, return their IDs."""
        expired_ids = []
        try:
            current = datetime.fromisoformat(current_date)
        except ValueError:
            raise ValueError("Invalid current_date format")
            
        for bundle in self._bundles.values():
            if bundle.status in (BundleStatus.DEPLOYED, BundleStatus.REVOKED):
                continue
                
            if bundle.expiry_date:
                try:
                    expiry = datetime.fromisoformat(bundle.expiry_date)
                    if current > expiry:
                        bundle.status = BundleStatus.EXPIRED
                        expired_ids.append(bundle.bundle_id)
                except ValueError:
                    pass
                    
        return expired_ids
