"""Multitenant SaaS Edition Engine (Batch 38 - Skill 1327).

Manages multitenant SaaS cluster provisioning, tenant isolation modes (pooled,
siloed, hybrid), tier-based quotas, storage limits, custom domain routing,
and cluster admission control.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    SaasClusterResourceQuota,
    SaasTenantConfig,
    SaasTenantTier,
    TenantIsolationMode,
)


class MultitenantSaasEditionEngine:
    """Industrial engine for Multitenant SaaS edition governance and quotas (B38)."""

    TIER_DEFAULTS = {
        SaasTenantTier.FREE: {
            "storage_quota_gb": 5.0,
            "rps_limit": 20,
            "isolation_mode": TenantIsolationMode.POOLED,
            "features": ["basic_transform", "standard_reports"],
            "allow_custom_domain": False,
        },
        SaasTenantTier.STANDARD: {
            "storage_quota_gb": 50.0,
            "rps_limit": 100,
            "isolation_mode": TenantIsolationMode.POOLED,
            "features": ["basic_transform", "standard_reports", "api_access", "webhooks"],
            "allow_custom_domain": False,
        },
        SaasTenantTier.PREMIUM: {
            "storage_quota_gb": 250.0,
            "rps_limit": 500,
            "isolation_mode": TenantIsolationMode.HYBRID,
            "features": ["basic_transform", "standard_reports", "api_access", "webhooks", "custom_rules", "priority_queue"],
            "allow_custom_domain": True,
        },
        SaasTenantTier.ENTERPRISE: {
            "storage_quota_gb": 1000.0,
            "rps_limit": 2000,
            "isolation_mode": TenantIsolationMode.SILOED,
            "features": ["basic_transform", "standard_reports", "api_access", "webhooks", "custom_rules", "priority_queue", "dedicated_vpc", "byok_kms", "custom_domain"],
            "allow_custom_domain": True,
        },
    }

    def __init__(self):
        self._clusters: Dict[str, SaasClusterResourceQuota] = {}
        self._tenants: Dict[str, SaasTenantConfig] = {}
        self._tenant_cluster_map: Dict[str, str] = {}  # tenant_id -> cluster_id
        self._tenant_storage_usage: Dict[str, float] = {}  # tenant_id -> current_gb

    def create_cluster(
        self,
        cluster_id: str,
        max_tenants: int = 500,
        total_storage_gb: float = 10000.0,
    ) -> SaasClusterResourceQuota:
        """Register a new SaaS cluster quota boundary."""
        if cluster_id in self._clusters:
            raise ValueError(f"Cluster '{cluster_id}' already exists")

        quota = SaasClusterResourceQuota(
            cluster_id=cluster_id,
            max_tenants=max_tenants,
            allocated_storage_gb=0.0,
            total_storage_gb=total_storage_gb,
            active_tenant_count=0,
        )
        self._clusters[cluster_id] = quota
        return quota

    def provision_tenant(
        self,
        cluster_id: str,
        name: str,
        tier: SaasTenantTier = SaasTenantTier.STANDARD,
        isolation_mode: Optional[TenantIsolationMode] = None,
        custom_domain: str = "",
    ) -> SaasTenantConfig:
        """Provision a new tenant in the designated SaaS cluster with admission control."""
        cluster = self._clusters.get(cluster_id)
        if not cluster:
            raise ValueError(f"Cluster '{cluster_id}' not found")

        if cluster.active_tenant_count >= cluster.max_tenants:
            raise ValueError(f"Cluster '{cluster_id}' has reached maximum tenant capacity ({cluster.max_tenants})")

        tier_cfg = self.TIER_DEFAULTS[tier]
        quota_gb = tier_cfg["storage_quota_gb"]

        if cluster.allocated_storage_gb + quota_gb > cluster.total_storage_gb:
            raise ValueError(
                f"Cluster '{cluster_id}' storage exhausted: requested {quota_gb} GB, remaining {cluster.total_storage_gb - cluster.allocated_storage_gb} GB"
            )

        if custom_domain and not tier_cfg["allow_custom_domain"]:
            raise ValueError(f"Tier '{tier.value}' does not support custom domain configurations")

        mode = isolation_mode or tier_cfg["isolation_mode"]
        tenant_id = f"tnt-{uuid.uuid4().hex[:8]}"

        tenant = SaasTenantConfig(
            tenant_id=tenant_id,
            name=name,
            tier=tier,
            isolation_mode=mode,
            storage_quota_gb=quota_gb,
            rps_limit=tier_cfg["rps_limit"],
            enabled_features=list(tier_cfg["features"]),
            custom_domain=custom_domain,
            is_suspended=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        self._tenants[tenant_id] = tenant
        self._tenant_cluster_map[tenant_id] = cluster_id
        self._tenant_storage_usage[tenant_id] = 0.0

        cluster.active_tenant_count += 1
        cluster.allocated_storage_gb += quota_gb

        return tenant

    def upgrade_tier(
        self,
        tenant_id: str,
        new_tier: SaasTenantTier,
    ) -> SaasTenantConfig:
        """Upgrade or modify tenant tier and adjust cluster quota reservations."""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        cluster_id = self._tenant_cluster_map[tenant_id]
        cluster = self._clusters[cluster_id]

        old_quota = tenant.storage_quota_gb
        new_tier_cfg = self.TIER_DEFAULTS[new_tier]
        new_quota = new_tier_cfg["storage_quota_gb"]
        quota_delta = new_quota - old_quota

        if quota_delta > 0 and (cluster.allocated_storage_gb + quota_delta > cluster.total_storage_gb):
            raise ValueError(f"Cluster storage cannot accommodate upgrade (+{quota_delta} GB)")

        cluster.allocated_storage_gb += quota_delta
        tenant.tier = new_tier
        tenant.storage_quota_gb = new_quota
        tenant.rps_limit = new_tier_cfg["rps_limit"]
        tenant.isolation_mode = new_tier_cfg["isolation_mode"]
        tenant.enabled_features = list(new_tier_cfg["features"])

        return tenant

    def suspend_tenant(self, tenant_id: str, reason: str = "") -> SaasTenantConfig:
        """Suspend tenant operations."""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        tenant.is_suspended = True
        return tenant

    def reactivate_tenant(self, tenant_id: str) -> SaasTenantConfig:
        """Reactivate suspended tenant."""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        tenant.is_suspended = False
        return tenant

    def update_storage_usage(self, tenant_id: str, used_gb: float) -> float:
        """Record current storage consumption for a tenant and check quota breach."""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found")
        if used_gb < 0.0:
            raise ValueError("Used storage cannot be negative")

        self._tenant_storage_usage[tenant_id] = used_gb
        if used_gb > tenant.storage_quota_gb:
            # Mark suspended on over-quota breach
            tenant.is_suspended = True

        return used_gb

    def get_tenant(self, tenant_id: str) -> Optional[SaasTenantConfig]:
        """Retrieve tenant configuration."""
        return self._tenants.get(tenant_id)

    def get_cluster_quota(self, cluster_id: str) -> Optional[SaasClusterResourceQuota]:
        """Retrieve cluster resource quota."""
        return self._clusters.get(cluster_id)

    def get_cluster_utilization(self, cluster_id: str) -> Dict[str, Any]:
        """Compute cluster utilization metrics across all tenants."""
        cluster = self._clusters.get(cluster_id)
        if not cluster:
            raise ValueError(f"Cluster '{cluster_id}' not found")

        tenants_in_cluster = [
            t for t_id, t in self._tenants.items() if self._tenant_cluster_map.get(t_id) == cluster_id
        ]

        tier_dist: Dict[str, int] = {}
        for t in SaasTenantTier:
            tier_dist[t.value] = 0

        actual_used_gb = 0.0
        suspended_count = 0
        for t in tenants_in_cluster:
            tier_dist[t.tier.value] += 1
            actual_used_gb += self._tenant_storage_usage.get(t.tenant_id, 0.0)
            if t.is_suspended:
                suspended_count += 1

        storage_pct = round((cluster.allocated_storage_gb / cluster.total_storage_gb) * 100.0, 2) if cluster.total_storage_gb > 0 else 0.0

        return {
            "cluster_id": cluster.cluster_id,
            "max_tenants": cluster.max_tenants,
            "active_tenant_count": cluster.active_tenant_count,
            "suspended_tenant_count": suspended_count,
            "total_storage_gb": cluster.total_storage_gb,
            "allocated_storage_gb": cluster.allocated_storage_gb,
            "actual_used_storage_gb": round(actual_used_gb, 2),
            "storage_allocation_pct": storage_pct,
            "tier_distribution": tier_dist,
        }

    def list_tenants(
        self,
        cluster_id: Optional[str] = None,
        tier: Optional[SaasTenantTier] = None,
    ) -> List[SaasTenantConfig]:
        """List tenants, optionally filtered by cluster ID or tier."""
        results = list(self._tenants.values())
        if cluster_id:
            results = [t for t in results if self._tenant_cluster_map.get(t.tenant_id) == cluster_id]
        if tier:
            results = [t for t in results if t.tier == tier]
        return results
