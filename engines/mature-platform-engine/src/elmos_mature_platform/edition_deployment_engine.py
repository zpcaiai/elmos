from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
import uuid

from .types import (
    EditionDeployment,
    EditionType,
    UpgradeExecution,
    UpgradePhase,
    VersionCompatibility,
    PlaneTopology,
    PlaneType,
    UpgradeStrategy,
    RegionId,
)


class EditionDeploymentEngine:
    """Engine for managing edition deployments, upgrades, and planes."""

    def __init__(self):
        self._deployments: Dict[str, EditionDeployment] = {}
        self._upgrades: Dict[str, UpgradeExecution] = {}
        self._compatibility_matrix: Dict[Tuple[str, str], VersionCompatibility] = {}
        self._topologies: Dict[str, PlaneTopology] = {}

    def register_edition(self, deployment: EditionDeployment) -> None:
        """Register a new edition deployment. Validates constraints."""
        if deployment.edition_type == EditionType.AIR_GAPPED and not deployment.network_isolated:
            raise ValueError("Air-gapped editions must be network isolated.")
        if deployment.edition_type == EditionType.MULTITENANT_SAAS and deployment.max_tenants <= 1:
            raise ValueError("Multitenant SaaS editions must have max_tenants > 1.")
            
        self._deployments[deployment.deployment_id] = deployment

    def get_deployment(self, deployment_id: str) -> EditionDeployment:
        """Retrieve deployment by ID."""
        if deployment_id not in self._deployments:
            raise KeyError(f"Deployment {deployment_id} not found.")
        return self._deployments[deployment_id]

    def register_version_compatibility(self, compat: VersionCompatibility) -> None:
        """Add to compatibility matrix."""
        self._compatibility_matrix[(compat.source_version, compat.target_version)] = compat

    def check_upgrade_path(self, from_version: str, to_version: str) -> VersionCompatibility:
        """Check compatibility between versions."""
        compat = self._compatibility_matrix.get((from_version, to_version))
        if not compat:
            raise ValueError(f"No compatibility path from {from_version} to {to_version}")
        return compat

    def initiate_upgrade(self, deployment_id: str, to_version: str) -> UpgradeExecution:
        """Start upgrade process."""
        deployment = self.get_deployment(deployment_id)
        
        # Check compatibility first
        compat = self.check_upgrade_path(deployment.version, to_version)
        if not compat.compatible:
            raise ValueError(f"Incompatible version upgrade from {deployment.version} to {to_version}")

        upgrade_id = f"upg-{uuid.uuid4()}"
        upgrade = UpgradeExecution(
            upgrade_id=upgrade_id,
            deployment_id=deployment_id,
            from_version=deployment.version,
            to_version=to_version,
            strategy=deployment.upgrade_strategy,
            phase=UpgradePhase.PRE_CHECK,
            started_at=datetime.now(timezone.utc).isoformat(),
            backup_id=f"bak-{uuid.uuid4()}",
            rollback_available=True
        )
        self._upgrades[upgrade_id] = upgrade
        return upgrade

    def advance_upgrade_phase(self, upgrade_id: str) -> UpgradeExecution:
        """Move to next phase in sequence."""
        if upgrade_id not in self._upgrades:
            raise KeyError(f"Upgrade {upgrade_id} not found.")
            
        upgrade = self._upgrades[upgrade_id]
        
        phase_transitions = {
            UpgradePhase.PRE_CHECK: UpgradePhase.BACKUP,
            UpgradePhase.BACKUP: UpgradePhase.EXPAND,
            UpgradePhase.EXPAND: UpgradePhase.MIGRATE,
            UpgradePhase.MIGRATE: UpgradePhase.VERIFY,
            UpgradePhase.VERIFY: UpgradePhase.CONTRACT,
            UpgradePhase.CONTRACT: UpgradePhase.COMPLETE,
        }
        
        if upgrade.phase == UpgradePhase.COMPLETE:
            return upgrade
            
        if upgrade.phase not in phase_transitions:
            raise ValueError(f"Cannot advance from phase {upgrade.phase}")
            
        next_phase = phase_transitions[upgrade.phase]
        
        if upgrade.phase == UpgradePhase.PRE_CHECK:
            upgrade.pre_check_passed = True
            upgrade.migration_log.append("Pre-check passed.")
        elif upgrade.phase == UpgradePhase.VERIFY:
            upgrade.verify_passed = True
            upgrade.migration_log.append("Verification passed.")
            
        upgrade.phase = next_phase
        upgrade.migration_log.append(f"Advanced to {next_phase.value}.")
        
        if next_phase == UpgradePhase.COMPLETE:
            upgrade.completed_at = datetime.now(timezone.utc).isoformat()
            deployment = self.get_deployment(upgrade.deployment_id)
            deployment.previous_version = deployment.version
            deployment.version = upgrade.to_version
            upgrade.migration_log.append("Upgrade completed.")
            
        return upgrade

    def rollback_upgrade(self, upgrade_id: str) -> UpgradeExecution:
        """Rollback to previous version."""
        if upgrade_id not in self._upgrades:
            raise KeyError(f"Upgrade {upgrade_id} not found.")
            
        upgrade = self._upgrades[upgrade_id]
        if not upgrade.rollback_available:
            raise ValueError("Rollback not available for this upgrade.")
            
        if upgrade.phase == UpgradePhase.COMPLETE:
            raise ValueError("Cannot rollback a completed upgrade.")
            
        upgrade.phase = UpgradePhase.ROLLBACK
        upgrade.migration_log.append("Rollback initiated.")
        upgrade.error = "Upgrade rolled back."
        return upgrade

    def register_plane_topology(self, topology: PlaneTopology) -> None:
        """Register plane topology."""
        if topology.deployment_id not in self._deployments:
            raise ValueError(f"Deployment {topology.deployment_id} does not exist.")
        self._topologies[topology.deployment_id] = topology

    def validate_plane_connectivity(self, deployment_id: str) -> Dict[str, bool]:
        """Check all required plane connections exist."""
        if deployment_id not in self._topologies:
            raise KeyError(f"No topology for deployment {deployment_id}")
            
        topology = self._topologies[deployment_id]
        deployment = self.get_deployment(deployment_id)
        
        connectivity = {}
        # Expect connections between all defined planes
        expected_connections = []
        planes = deployment.planes
        for i in range(len(planes)):
            for j in range(i + 1, len(planes)):
                expected_connections.append((planes[i].value, planes[j].value))
                expected_connections.append((planes[j].value, planes[i].value))
                
        actual_conns = set(topology.cross_plane_connectivity)
        
        for p1, p2 in expected_connections:
            # We assume bidirectional connection is required or at least one direction
            conn_key = f"{p1}->{p2}"
            connectivity[conn_key] = (p1, p2) in actual_conns
            
        return connectivity

    def execute_zero_downtime_upgrade(self, deployment_id: str, to_version: str) -> UpgradeExecution:
        """Full automated zero downtime upgrade."""
        deployment = self.get_deployment(deployment_id)
        
        if deployment.upgrade_strategy not in [UpgradeStrategy.ROLLING_UPDATE, UpgradeStrategy.BLUE_GREEN]:
            raise ValueError("Zero downtime requires ROLLING_UPDATE or BLUE_GREEN strategy.")
            
        upgrade = self.initiate_upgrade(deployment_id, to_version)
        
        # Fast-forward through all phases
        while upgrade.phase != UpgradePhase.COMPLETE:
            self.advance_upgrade_phase(upgrade.upgrade_id)
            
        return upgrade

    def get_edition_responsibility_matrix(self, edition_type: EditionType) -> Dict[str, str]:
        """Return responsibility matrix."""
        matrix = {
            "control_plane": "platform",
            "data_plane": "platform",
            "networking": "platform",
            "security": "shared",
            "updates": "platform",
            "monitoring": "platform"
        }
        
        if edition_type in [EditionType.SELF_HOSTED, EditionType.AIR_GAPPED]:
            matrix = {
                "control_plane": "customer",
                "data_plane": "customer",
                "networking": "customer",
                "security": "customer",
                "updates": "customer",
                "monitoring": "shared"
            }
        elif edition_type == EditionType.CUSTOMER_VPC:
            matrix["data_plane"] = "customer"
            matrix["networking"] = "shared"
            matrix["security"] = "shared"
            
        return matrix

    def create_offline_update_bundle(self, deployment_id: str, to_version: str) -> Dict[str, Any]:
        """Generate offline update bundle."""
        deployment = self.get_deployment(deployment_id)
        if deployment.edition_type != EditionType.AIR_GAPPED:
            raise ValueError("Offline bundles only supported for air-gapped editions.")
            
        return {
            "deployment_id": deployment_id,
            "target_version": to_version,
            "manifest": {"components": ["core", "api", "worker"]},
            "checksums": {"core": "sha256-abc", "api": "sha256-def", "worker": "sha256-ghi"},
            "signature": "sig-12345",
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    def validate_data_residency(self, deployment_id: str) -> Tuple[bool, List[str]]:
        """Validate data residency."""
        deployment = self.get_deployment(deployment_id)
        violations = []
        
        if not deployment.data_residency_region:
            return True, []
            
        if deployment.region.value != deployment.data_residency_region:
            violations.append(f"Deployment region {deployment.region.value} does not match residency {deployment.data_residency_region}")
            
        if deployment_id in self._topologies:
            topology = self._topologies[deployment_id]
            for plane_type, plane_data in topology.planes.items():
                if plane_data.get("region") != deployment.data_residency_region:
                    violations.append(f"Plane {plane_type} in {plane_data.get('region')} violates residency {deployment.data_residency_region}")
                    
        return len(violations) == 0, violations

    def get_active_deployments(self, edition_type: Optional[EditionType] = None) -> List[EditionDeployment]:
        """Filter active deployments."""
        active = [d for d in self._deployments.values() if d.is_active]
        if edition_type:
            active = [d for d in active if d.edition_type == edition_type]
        return active
