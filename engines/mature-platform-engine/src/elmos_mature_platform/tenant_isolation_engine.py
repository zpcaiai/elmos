import uuid
from typing import Dict, List, Optional
from elmos_mature_platform.physical.kubernetes_api import KubernetesControlPlaneDriver
from elmos_mature_platform.types import (
    RegionId,
    TenantDescriptor,
    TenantIsolationLevel,
    TenantResourceUsage,
    TenantWorkspaceBinding,
    IsolationEnforcementResult
)

class TenantIsolationEngine:
    """Engine for managing multi-tenant isolation, quotas, and security boundaries."""

    def __init__(self, kubernetes_driver: Optional[KubernetesControlPlaneDriver] = None) -> None:
        self.tenants: Dict[str, TenantDescriptor] = {}
        self.usage: Dict[str, TenantResourceUsage] = {}
        self.cross_tenant_violations = 0
        self.residency_violations = 0
        self.access_attempts = 0
        self._k8s = kubernetes_driver or KubernetesControlPlaneDriver.from_env()
        self._physical_receipts: List[Dict] = []

    def provision_tenant(self, descriptor: TenantDescriptor) -> TenantWorkspaceBinding:
        """Provisions a new tenant and returns its hardened workspace binding."""
        self.tenants[descriptor.tenant_id] = descriptor
        self.usage[descriptor.tenant_id] = TenantResourceUsage(tenant_id=descriptor.tenant_id)
        
        workspace_id = f"ws-{uuid.uuid4().hex[:8]}"
        bundle = self._k8s.apply_tenant_isolation(
            tenant_id=descriptor.tenant_id,
            cpu_cores=descriptor.cpu_cores_limit,
            memory_gb=descriptor.memory_gb_limit,
        )
        self._physical_receipts.append(bundle.to_dict())
        return TenantWorkspaceBinding(
            workspace_id=workspace_id,
            tenant_id=descriptor.tenant_id,
            cgroup_path=f"/sys/fs/cgroup/elmos/tenant-{descriptor.tenant_id}",
            network_namespace=f"netns-{descriptor.tenant_id}",
            fs_mounts={"/data": f"/mnt/storage/{descriptor.tenant_id}"},
            container_security_profile="no-new-privileges",
            read_only_rootfs=True
        )

    def verify_tenant_boundary(self, token_tenant_id: str, target_resource_tenant_id: str, resource: str) -> IsolationEnforcementResult:
        """Verifies fail-closed cross-tenant access, raising PermissionError on violation."""
        self.access_attempts += 1
        
        tenant = self.tenants.get(token_tenant_id)
        if not tenant:
            raise PermissionError(f"Tenant {token_tenant_id} not found.")
            
        if tenant.status != "ACTIVE":
            raise PermissionError(f"Tenant {token_tenant_id} is {tenant.status}. Access denied.")
            
        if token_tenant_id != target_resource_tenant_id:
            self.cross_tenant_violations += 1
            raise PermissionError(f"Cross-tenant access violation: {token_tenant_id} attempted to access {target_resource_tenant_id}'s resource {resource}")
            
        return IsolationEnforcementResult(
            allowed=True,
            tenant_id=token_tenant_id,
            resource_target=resource,
            boundary_type="COMPUTE",
            audit_message="Access allowed"
        )

    def check_quota(self, tenant_id: str, resource_type: str, requested_amount: float) -> bool:
        """Enforces quotas for CPU, memory, storage, or rate limits."""
        tenant = self.tenants.get(tenant_id)
        if not tenant or tenant.status != "ACTIVE":
            return False
            
        usage = self.usage.get(tenant_id)
        if not usage:
            return False
            
        if resource_type == "cpu":
            return (usage.allocated_cpu_cores + requested_amount) <= tenant.cpu_cores_limit
        elif resource_type == "memory":
            return (usage.allocated_memory_gb + requested_amount) <= tenant.memory_gb_limit
        elif resource_type == "storage":
            return (usage.current_storage_bytes + requested_amount) <= (tenant.storage_gb_limit * 1024 * 1024 * 1024)
        elif resource_type == "rate":
            return requested_amount <= tenant.rate_limit_rps
        return False

    def record_usage(self, tenant_id: str, cpu: float, memory: float, storage: int, egress: int) -> None:
        """Tracks ongoing resource usage for a tenant."""
        if tenant_id not in self.usage:
            self.usage[tenant_id] = TenantResourceUsage(tenant_id=tenant_id)
            
        self.usage[tenant_id].allocated_cpu_cores += cpu
        self.usage[tenant_id].allocated_memory_gb += memory
        self.usage[tenant_id].current_storage_bytes += storage
        self.usage[tenant_id].period_egress_bytes += egress
        self.usage[tenant_id].active_runners += 1

    def get_usage(self, tenant_id: str) -> TenantResourceUsage:
        """Returns current resource usage for a tenant."""
        return self.usage.get(tenant_id, TenantResourceUsage(tenant_id=tenant_id))

    def verify_data_residency(self, tenant_id: str, target_region: RegionId) -> bool:
        """Performs fail-closed data residency check."""
        tenant = self.tenants.get(tenant_id)
        if not tenant or tenant.status != "ACTIVE":
            self.residency_violations += 1
            return False
            
        if tenant.residency_region != target_region:
            self.residency_violations += 1
            return False
            
        return True

    def verify_container_hardening(self, workspace: TenantWorkspaceBinding) -> Dict[str, bool]:
        """Checks read-only rootfs, cgroup, and namespace isolation settings."""
        return {
            "read_only_rootfs": workspace.read_only_rootfs is True,
            "cgroup_isolated": workspace.cgroup_path.startswith("/sys/fs/cgroup/"),
            "network_isolated": bool(workspace.network_namespace),
            "no_new_privileges": workspace.container_security_profile == "no-new-privileges"
        }

    def resolve_encryption_context(self, tenant_id: str) -> Dict[str, str]:
        """Generates tenant-specific KMS Additional Authenticated Data (AAD) binding."""
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        return {
            "tenant_id": tenant.tenant_id,
            "kms_key_arn": tenant.kms_key_arn,
            "isolation_level": tenant.isolation_level.value
        }

    def suspend_tenant(self, tenant_id: str) -> None:
        """Suspends a tenant, rejecting all new requests."""
        tenant = self.tenants.get(tenant_id)
        if tenant:
            tenant.status = "SUSPENDED"

    def list_tenants(self, status: Optional[str] = None) -> List[TenantDescriptor]:
        """Lists all tenants, optionally filtered by status."""
        if status:
            return [t for t in self.tenants.values() if t.status == status]
        return list(self.tenants.values())

    def get_tenant_isolation_report(self) -> Dict:
        """Returns cross-tenant access attempts, violations, and usage summaries."""
        return {
            "cross_tenant_violations": self.cross_tenant_violations,
            "residency_violations": self.residency_violations,
            "access_attempts": self.access_attempts,
            "active_tenants": len([t for t in self.tenants.values() if t.status == "ACTIVE"]),
            "suspended_tenants": len([t for t in self.tenants.values() if t.status == "SUSPENDED"])
        }
