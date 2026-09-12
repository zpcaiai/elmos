"""Recipe, Pack and Extension Upgrade Engine (Batch 38 - Skill 1342).

Manages compatibility, dependency resolution, rolling/atomic upgrades,
and automated rollbacks for Recipes, Packs, and Extensions across editions.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    ArtifactPackageType,
    PackageArtifact,
    PackageDependency,
    PackageUpgradePlan,
    PackageUpgradeStatus,
    PackageUpgradeStrategy,
)


class RecipePackExtensionUpgradeEngine:
    """Industrial engine for managing Recipe, Pack, and Extension upgrades (B38)."""

    def __init__(self):
        self._packages: Dict[str, PackageArtifact] = {}
        self._plans: Dict[str, PackageUpgradePlan] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def register_package(self, package: PackageArtifact) -> str:
        """Register a new Recipe, Pack, or Extension artifact."""
        if not package.package_id:
            package.package_id = f"pkg-{uuid.uuid4().hex[:8]}"
        if not package.created_at:
            package.created_at = datetime.now(timezone.utc).isoformat()
        if not package.sha256:
            # Generate deterministic checksum from name, version, type
            raw = f"{package.name}:{package.version}:{package.package_type.value}".encode("utf-8")
            package.sha256 = hashlib.sha256(raw).hexdigest()

        self._packages[package.package_id] = package
        self._record_audit("register_package", package.package_id, {
            "name": package.name,
            "version": package.version,
            "type": package.package_type.value,
        })
        return package.package_id

    def get_package(self, package_id: str) -> Optional[PackageArtifact]:
        """Retrieve a package by its ID."""
        return self._packages.get(package_id)

    def find_package(self, name: str, version: str) -> Optional[PackageArtifact]:
        """Find a package by name and exact version."""
        for pkg in self._packages.values():
            if pkg.name == name and pkg.version == version:
                return pkg
        return None

    def check_dependencies(
        self,
        package_id: str,
        installed_packages: Dict[str, str],
    ) -> Dict[str, Any]:
        """Verify if installed packages satisfy the dependency constraints of the package."""
        pkg = self._get_package_or_raise(package_id)
        satisfied: List[str] = []
        missing: List[str] = []
        conflicts: List[str] = []

        for dep in pkg.dependencies:
            installed_ver = installed_packages.get(dep.name)
            if not installed_ver:
                if dep.mandatory:
                    missing.append(dep.name)
            else:
                # Basic constraint check: supports >= or exact
                if dep.version_constraint.startswith(">="):
                    min_ver = dep.version_constraint[2:].strip()
                    if installed_ver < min_ver:
                        conflicts.append(f"{dep.name} installed {installed_ver} < required {min_ver}")
                    else:
                        satisfied.append(dep.name)
                elif dep.version_constraint.startswith("=="):
                    req_ver = dep.version_constraint[2:].strip()
                    if installed_ver != req_ver:
                        conflicts.append(f"{dep.name} installed {installed_ver} != required {req_ver}")
                    else:
                        satisfied.append(dep.name)
                else:
                    satisfied.append(dep.name)

        compatible = (len(missing) == 0 and len(conflicts) == 0)
        return {
            "compatible": compatible,
            "satisfied": satisfied,
            "missing": missing,
            "conflicts": conflicts,
        }

    def create_upgrade_plan(self, plan: PackageUpgradePlan) -> str:
        """Create a new package upgrade plan."""
        if not plan.plan_id:
            plan.plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        plan.status = PackageUpgradeStatus.PENDING
        plan.applied_deployments = []
        plan.started_at = datetime.now(timezone.utc).isoformat()

        self._plans[plan.plan_id] = plan
        self._record_audit("create_upgrade_plan", plan.plan_id, {
            "package": plan.package_name,
            "from": plan.from_version,
            "to": plan.to_version,
            "targets": plan.target_deployments,
        })
        return plan.plan_id

    def execute_upgrade(self, plan_id: str, deployment_id: str) -> PackageUpgradePlan:
        """Execute upgrade step for a target deployment."""
        plan = self._get_plan_or_raise(plan_id)
        if plan.status in (PackageUpgradeStatus.FAILED, PackageUpgradeStatus.ROLLED_BACK):
            raise ValueError(f"Cannot execute upgrade on a {plan.status.value} plan")

        if deployment_id not in plan.target_deployments:
            raise ValueError(f"Deployment {deployment_id} is not part of plan {plan_id}")

        plan.status = PackageUpgradeStatus.IN_PROGRESS
        if deployment_id not in plan.applied_deployments:
            plan.applied_deployments.append(deployment_id)

        if len(plan.applied_deployments) == len(plan.target_deployments):
            plan.status = PackageUpgradeStatus.APPLIED
            plan.completed_at = datetime.now(timezone.utc).isoformat()

        self._record_audit("execute_upgrade_step", plan_id, {"deployment": deployment_id})
        return plan

    def rollback_upgrade(self, plan_id: str, deployment_id: str) -> PackageUpgradePlan:
        """Rollback upgrade for a specific deployment or the entire plan."""
        plan = self._get_plan_or_raise(plan_id)
        if deployment_id in plan.applied_deployments:
            plan.applied_deployments.remove(deployment_id)

        plan.status = PackageUpgradeStatus.ROLLED_BACK
        plan.completed_at = datetime.now(timezone.utc).isoformat()
        self._record_audit("rollback_upgrade", plan_id, {"deployment": deployment_id})
        return plan

    def fail_upgrade(self, plan_id: str, error_message: str) -> PackageUpgradePlan:
        """Mark upgrade as failed and optionally rollback."""
        plan = self._get_plan_or_raise(plan_id)
        plan.status = PackageUpgradeStatus.FAILED
        plan.error_message = error_message
        plan.completed_at = datetime.now(timezone.utc).isoformat()

        if plan.rollback_on_failure:
            plan.applied_deployments.clear()
            plan.status = PackageUpgradeStatus.ROLLED_BACK

        self._record_audit("fail_upgrade", plan_id, {"error": error_message, "auto_rollback": plan.rollback_on_failure})
        return plan

    def get_upgrade_plan(self, plan_id: str) -> Optional[PackageUpgradePlan]:
        """Retrieve an upgrade plan."""
        return self._plans.get(plan_id)

    def get_upgrade_summary(self) -> Dict[str, Any]:
        """Return aggregate summary of all upgrade activities."""
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}

        for p in self._plans.values():
            by_status[p.status.value] = by_status.get(p.status.value, 0) + 1
            by_type[p.package_type.value] = by_type.get(p.package_type.value, 0) + 1

        return {
            "total_packages_registered": len(self._packages),
            "total_plans": len(self._plans),
            "plans_by_status": by_status,
            "plans_by_type": by_type,
            "audit_events_count": len(self._audit_log),
        }

    def _get_package_or_raise(self, package_id: str) -> PackageArtifact:
        if package_id not in self._packages:
            raise ValueError(f"Package {package_id} not found")
        return self._packages[package_id]

    def _get_plan_or_raise(self, plan_id: str) -> PackageUpgradePlan:
        if plan_id not in self._plans:
            raise ValueError(f"Upgrade plan {plan_id} not found")
        return self._plans[plan_id]

    def _record_audit(self, action: str, target_id: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target_id": target_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })
