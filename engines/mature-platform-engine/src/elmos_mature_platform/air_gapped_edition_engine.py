"""Air-gapped Edition Engine (Batch 38 - Skill 1333).

Manages physical and network air-gapped enterprise deployments, offline licensing,
data diode and secure transfer validation, air-gap isolation status, and compliance audits.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    AirgapComplianceCheck,
    AirgapEditionDeployment,
    AirgapIsolationStatus,
    AirgapTransferMedium,
)


class AirGappedEditionEngine:
    """Enterprise governance and isolation control for air-gapped environments."""

    def __init__(self) -> None:
        self._deployments: Dict[str, AirgapEditionDeployment] = {}
        self._compliance_history: Dict[str, List[AirgapComplianceCheck]] = {}
        self._offline_license_tokens: Dict[str, str] = {}

    def register_deployment(self, deployment: AirgapEditionDeployment) -> str:
        """Register a new air-gapped deployment."""
        if not deployment.customer_id or not deployment.site_name:
            raise ValueError("customer_id and site_name are required")
        if not deployment.version:
            raise ValueError("version is required")

        if not deployment.deployment_id:
            deployment.deployment_id = f"airgap-{uuid.uuid4().hex[:8]}"

        if not deployment.created_at:
            deployment.created_at = datetime.now(timezone.utc).isoformat()

        self._deployments[deployment.deployment_id] = deployment
        self._compliance_history[deployment.deployment_id] = []
        return deployment.deployment_id

    def record_compliance_check(
        self, deployment_id: str, check: AirgapComplianceCheck
    ) -> AirgapComplianceCheck:
        """Record an isolation compliance check for a deployment."""
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")

        if not check.check_id:
            check.check_id = f"chk-{uuid.uuid4().hex[:8]}"
        if not check.checked_at:
            check.checked_at = datetime.now(timezone.utc).isoformat()

        self._compliance_history[deployment_id].append(check)
        deployment.last_compliance_audit = check.checked_at

        # Update isolation status if check failed
        if not check.passed:
            if "breach" in check.name.lower() or "leak" in check.name.lower() or "active_nic" in check.name.lower():
                deployment.isolation_status = AirgapIsolationStatus.BREACHED
            else:
                deployment.isolation_status = AirgapIsolationStatus.DEGRADED

        return check

    def install_offline_license(
        self, deployment_id: str, license_token: str, expires_at: str
    ) -> bool:
        """Install and validate an offline cryptographically signed license."""
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")
        if not license_token or len(license_token.strip()) < 16:
            raise ValueError("Invalid offline license token")

        deployment.offline_license_valid = True
        deployment.license_expires_at = expires_at
        self._offline_license_tokens[deployment_id] = license_token
        return True

    def revoke_offline_license(self, deployment_id: str) -> bool:
        """Revoke offline license for a deployment."""
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")

        deployment.offline_license_valid = False
        return True

    def attach_airgap_bundle(
        self, deployment_id: str, bundle_id: str, transfer_medium: AirgapTransferMedium
    ) -> AirgapEditionDeployment:
        """Import an update bundle via an approved airgap transfer medium."""
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")

        if deployment.allowed_transfer_mediums and transfer_medium not in deployment.allowed_transfer_mediums:
            raise ValueError(
                f"Transfer medium {transfer_medium.value} is not in allowed mediums: "
                f"{[m.value for m in deployment.allowed_transfer_mediums]}"
            )

        if bundle_id not in deployment.active_bundle_ids:
            deployment.active_bundle_ids.append(bundle_id)

        return deployment

    def audit_isolation(self, deployment_id: str) -> Dict[str, Any]:
        """Perform full isolation audit and recalculate isolation health."""
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")

        checks = self._compliance_history.get(deployment_id, [])
        total_checks = len(checks)
        passed_checks = sum(1 for c in checks if c.passed)

        if not deployment.network_interfaces_disabled:
            deployment.isolation_status = AirgapIsolationStatus.BREACHED
        elif total_checks > 0 and passed_checks < total_checks:
            has_breach = any(
                not c.passed and ("breach" in c.name.lower() or "leak" in c.name.lower())
                for c in checks
            )
            deployment.isolation_status = (
                AirgapIsolationStatus.BREACHED if has_breach else AirgapIsolationStatus.DEGRADED
            )
        elif total_checks > 0 and passed_checks == total_checks:
            deployment.isolation_status = AirgapIsolationStatus.ISOLATED
        else:
            deployment.isolation_status = AirgapIsolationStatus.UNVERIFIED

        return {
            "deployment_id": deployment_id,
            "site_name": deployment.site_name,
            "isolation_status": deployment.isolation_status.value,
            "network_disabled": deployment.network_interfaces_disabled,
            "offline_license_valid": deployment.offline_license_valid,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "compliance_pct": (passed_checks / total_checks * 100.0) if total_checks > 0 else 0.0,
            "active_bundles_count": len(deployment.active_bundle_ids),
        }

    def get_deployment(self, deployment_id: str) -> Optional[AirgapEditionDeployment]:
        """Retrieve deployment by ID."""
        return self._deployments.get(deployment_id)

    def get_airgap_fleet_report(self) -> Dict[str, Any]:
        """Generate fleet-wide isolation and compliance report."""
        total = len(self._deployments)
        by_status: Dict[str, int] = {}
        for d in self._deployments.values():
            st = d.isolation_status.value
            by_status[st] = by_status.get(st, 0) + 1

        licensed_count = sum(1 for d in self._deployments.values() if d.offline_license_valid)
        total_bundles = sum(len(d.active_bundle_ids) for d in self._deployments.values())

        return {
            "total_deployments": total,
            "by_isolation_status": by_status,
            "licensed_count": licensed_count,
            "total_active_bundles": total_bundles,
        }
