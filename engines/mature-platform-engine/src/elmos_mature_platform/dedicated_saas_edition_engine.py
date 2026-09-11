"""Dedicated SaaS Edition Engine (Batch 38 - Skill 1329).

Manages single-tenant and dedicated cluster enterprise SaaS instances,
custom domains, BYOK encryption, VPC peering, and tenant isolation audits.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    DedicatedSaasAuditRecord,
    DedicatedSaasConfig,
    DedicatedSaasIsolationLevel,
    DedicatedSaasStatus,
)


class DedicatedSaasEditionEngine:
    """Provisioning and isolation management for Dedicated SaaS environments."""

    def __init__(self) -> None:
        self._editions: Dict[str, DedicatedSaasConfig] = {}
        self._audits: Dict[str, List[DedicatedSaasAuditRecord]] = {}

    def provision_dedicated_saas(self, config: DedicatedSaasConfig) -> str:
        """Register and provision a new Dedicated SaaS customer deployment."""
        if not config.edition_id:
            config.edition_id = f"ded-{uuid.uuid4().hex[:8]}"
        if not config.customer_id or not config.custom_domain:
            raise ValueError("customer_id and custom_domain are required")

        if not config.created_at:
            config.created_at = datetime.now(timezone.utc).isoformat()

        config.status = DedicatedSaasStatus.PROVISIONING
        self._editions[config.edition_id] = config
        self._audits[config.edition_id] = []
        return config.edition_id

    def activate_edition(self, edition_id: str) -> DedicatedSaasConfig:
        """Mark a provisioned edition as ACTIVE."""
        edition = self._editions.get(edition_id)
        if not edition:
            raise ValueError(f"Edition not found: {edition_id}")

        edition.status = DedicatedSaasStatus.ACTIVE
        return edition

    def configure_byok(self, edition_id: str, key_arn: str) -> DedicatedSaasConfig:
        """Configure customer-managed encryption key (BYOK)."""
        edition = self._editions.get(edition_id)
        if not edition:
            raise ValueError(f"Edition not found: {edition_id}")
        if not key_arn:
            raise ValueError("key_arn cannot be empty")

        edition.byok_key_arn = key_arn
        return edition

    def configure_vpc_peering(self, edition_id: str, peering_id: str) -> DedicatedSaasConfig:
        """Link a customer VPC peering connection."""
        edition = self._editions.get(edition_id)
        if not edition:
            raise ValueError(f"Edition not found: {edition_id}")
        if not peering_id:
            raise ValueError("peering_id cannot be empty")

        edition.vpc_peering_id = peering_id
        return edition

    def suspend_edition(self, edition_id: str, reason: str = "") -> DedicatedSaasConfig:
        """Suspend an active deployment."""
        edition = self._editions.get(edition_id)
        if not edition:
            raise ValueError(f"Edition not found: {edition_id}")

        edition.status = DedicatedSaasStatus.SUSPENDED
        return edition

    def record_isolation_audit(
        self, edition_id: str, audit: DedicatedSaasAuditRecord
    ) -> DedicatedSaasAuditRecord:
        """Record an isolation verification audit result."""
        if edition_id not in self._editions:
            raise ValueError(f"Edition not found: {edition_id}")

        if not audit.audit_id:
            audit.audit_id = f"audit-{uuid.uuid4().hex[:8]}"
        if not audit.checked_at:
            audit.checked_at = datetime.now(timezone.utc).isoformat()

        audit.edition_id = edition_id
        self._audits[edition_id].append(audit)
        return audit

    def verify_isolation_health(self, edition_id: str) -> Dict[str, Any]:
        """Evaluate overall isolation and security health for an edition."""
        edition = self._editions.get(edition_id)
        if not edition:
            raise ValueError(f"Edition not found: {edition_id}")

        audits = self._audits.get(edition_id, [])
        total_audits = len(audits)
        passed_audits = sum(1 for a in audits if a.passed)
        has_byok = bool(edition.byok_key_arn)
        has_vpc = bool(edition.vpc_peering_id)

        healthy = (total_audits == 0 or passed_audits == total_audits) and (
            edition.status == DedicatedSaasStatus.ACTIVE
        )

        return {
            "edition_id": edition_id,
            "status": edition.status.value,
            "isolation_level": edition.isolation_level.value,
            "is_healthy": healthy,
            "byok_configured": has_byok,
            "vpc_peered": has_vpc,
            "total_audits": total_audits,
            "passed_audits": passed_audits,
        }

    def get_edition_by_customer(self, customer_id: str) -> Optional[DedicatedSaasConfig]:
        """Look up a dedicated SaaS edition by customer ID."""
        return next((e for e in self._editions.values() if e.customer_id == customer_id), None)

    def get_dedicated_saas_fleet_report(self) -> Dict[str, Any]:
        """Return fleet summary statistics for all dedicated SaaS deployments."""
        total = len(self._editions)
        active = sum(1 for e in self._editions.values() if e.status == DedicatedSaasStatus.ACTIVE)
        byok_count = sum(1 for e in self._editions.values() if bool(e.byok_key_arn))
        vpc_count = sum(1 for e in self._editions.values() if bool(e.vpc_peering_id))

        isolation_counts: Dict[str, int] = {}
        for e in self._editions.values():
            lvl = e.isolation_level.value
            isolation_counts[lvl] = isolation_counts.get(lvl, 0) + 1

        return {
            "total_deployments": total,
            "active_deployments": active,
            "byok_enabled_count": byok_count,
            "vpc_peered_count": vpc_count,
            "isolation_distribution": isolation_counts,
        }
