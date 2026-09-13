from typing import List, Dict, Optional
from elmos_mature_platform.types import (
    ControlPlaneComponent,
    PlaneHealthState,
    PortablePlaneType,
    DeploymentTopology,
    TopologyValidation,
    PlaneGovernanceRule
)

class PortableControlPlaneEngine:
    """Engine for managing portable control plane components and topologies."""

    def __init__(self):
        self._components: Dict[str, ControlPlaneComponent] = {}
        self._governance_rules: Dict[PortablePlaneType, PlaneGovernanceRule] = {}

    def register_component(self, component: ControlPlaneComponent) -> None:
        """Register a control plane component."""
        self._components[component.component_id] = component

    def update_health(self, component_id: str, health: PlaneHealthState) -> None:
        """Update component health."""
        if component_id not in self._components:
            raise ValueError(f"Component {component_id} not found")
        self._components[component_id].health = health

    def get_component(self, component_id: str) -> ControlPlaneComponent:
        """Get component details."""
        if component_id not in self._components:
            raise ValueError(f"Component {component_id} not found")
        return self._components[component_id]

    def list_components(self, plane_type: Optional[PortablePlaneType] = None) -> List[ControlPlaneComponent]:
        """List components, optionally filter by plane type."""
        comps = list(self._components.values())
        if plane_type:
            return [c for c in comps if c.plane_type == plane_type]
        return comps

    def validate_topology(self, topology: DeploymentTopology) -> TopologyValidation:
        """Validate all required components exist and are healthy."""
        comps_in_topo = [c for c in self._components.values() if c.topology == topology]
        
        warnings = []
        missing_components = []
        valid = True
        
        # Check governance rules
        planes_present = {}
        for c in comps_in_topo:
            planes_present.setdefault(c.plane_type, []).append(c)
            
        for p_type, rule in self._governance_rules.items():
            if rule.allowed_topologies and topology.value not in rule.allowed_topologies:
                # Topo not allowed
                pass
                
            comps = planes_present.get(p_type, [])
            if len(comps) < rule.min_instances:
                missing_components.append(f"Missing instances for {p_type.value}: expected {rule.min_instances}, got {len(comps)}")
                valid = False
            if len(comps) > rule.max_instances:
                warnings.append(f"Too many instances for {p_type.value}: max {rule.max_instances}, got {len(comps)}")

        # Check health and airgapped constraint
        regions = set()
        for c in comps_in_topo:
            if c.region:
                regions.add(c.region)
            if c.health in (PlaneHealthState.STOPPED, PlaneHealthState.UNREACHABLE):
                warnings.append(f"Component {c.component_id} is {c.health.value}")
                valid = False
                
        if topology == DeploymentTopology.AIR_GAPPED and len(regions) > 1:
            warnings.append("Air-gapped topology requires all components in same region")
            valid = False

        total_cpu = sum(c.resource_cpu_millicores for c in comps_in_topo)
        total_mem = sum(c.resource_memory_mb for c in comps_in_topo)

        return TopologyValidation(
            topology=topology,
            valid=valid,
            missing_components=missing_components,
            warnings=warnings,
            resource_total_cpu=total_cpu,
            resource_total_memory=total_mem
        )

    def add_governance_rule(self, rule: PlaneGovernanceRule) -> None:
        """Add governance rule for a plane type."""
        self._governance_rules[rule.plane_type] = rule

    def check_governance(self, component_id: str) -> Dict:
        """Check if component complies with governance rules."""
        if component_id not in self._components:
            raise ValueError(f"Component {component_id} not found")
            
        comp = self._components[component_id]
        rule = self._governance_rules.get(comp.plane_type)
        if not rule:
            return {"compliant": True, "reasons": []}
            
        compliant = True
        reasons = []
        
        if rule.allowed_topologies and comp.topology.value not in rule.allowed_topologies:
            compliant = False
            reasons.append(f"Topology {comp.topology.value} not allowed by rule")
            
        if rule.requires_encryption and not comp.endpoint_url.startswith("https://"):
            compliant = False
            reasons.append("Endpoint URL must be https:// when encryption is required")
            
        return {"compliant": compliant, "reasons": reasons}

    def get_topology_resource_summary(self, topology: DeploymentTopology) -> Dict:
        """Total CPU/memory for a topology."""
        comps = [c for c in self._components.values() if c.topology == topology]
        return {
            "total_cpu_millicores": sum(c.resource_cpu_millicores for c in comps),
            "total_memory_mb": sum(c.resource_memory_mb for c in comps),
            "component_count": len(comps)
        }

    def detect_dependency_issues(self) -> List[Dict]:
        """Find circular deps, missing deps, unhealthy deps."""
        issues = []
        # build graph
        adj = {c.component_id: c.dependencies for c in self._components.values()}
        
        # missing / unhealthy deps
        for c in self._components.values():
            for dep in c.dependencies:
                if dep not in self._components:
                    issues.append({"type": "missing_dependency", "component": c.component_id, "dependency": dep})
                else:
                    dep_comp = self._components[dep]
                    if dep_comp.health != PlaneHealthState.RUNNING:
                        issues.append({"type": "unhealthy_dependency", "component": c.component_id, "dependency": dep, "health": dep_comp.health.value})
                        
        # Detect circular dependencies using DFS
        visited = set()
        path = set()
        
        def dfs(node):
            if node in path:
                return [node]
            if node in visited:
                return None
            visited.add(node)
            path.add(node)
            
            for neighbor in adj.get(node, []):
                cycle = dfs(neighbor)
                if cycle:
                    return cycle + [node]
                    
            path.remove(node)
            return None

        for node in adj:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    cycle.reverse()
                    issues.append({"type": "circular_dependency", "cycle": cycle})
                    break # report one cycle to avoid clutter
                    
        return issues

    def promote_topology(self, from_topology: DeploymentTopology, to_topology: DeploymentTopology) -> Dict:
        """Plan migration from one topology to another."""
        issues = self.detect_dependency_issues()
        if issues:
            return {"success": False, "reason": "Dependency issues detected", "issues": issues}
            
        from_comps = [c for c in self._components.values() if c.topology == from_topology]
        if not from_comps:
            return {"success": False, "reason": "No components found in source topology"}
            
        # check if healthy
        for c in from_comps:
            if c.health != PlaneHealthState.RUNNING:
                return {"success": False, "reason": f"Component {c.component_id} is not RUNNING"}
                
        # Plan migration
        return {
            "success": True,
            "migrated_components_count": len(from_comps),
            "from_topology": from_topology.value,
            "to_topology": to_topology.value,
            "estimated_cpu_diff": 0,
            "estimated_memory_diff": 0
        }

    def get_plane_health_report(self) -> Dict:
        """Health report across all planes."""
        report = {}
        for p_type in PortablePlaneType:
            comps = [c for c in self._components.values() if c.plane_type == p_type]
            if not comps:
                continue
                
            state = "healthy"
            unreachable = any(c.health == PlaneHealthState.UNREACHABLE for c in comps)
            degraded = any(c.health in (PlaneHealthState.DEGRADED, PlaneHealthState.STOPPED) for c in comps)
            
            if unreachable:
                state = "degraded"
            elif degraded:
                state = "degraded"
                
            report[p_type.value] = {
                "overall_state": state,
                "components": len(comps),
                "unreachable": sum(1 for c in comps if c.health == PlaneHealthState.UNREACHABLE),
                "running": sum(1 for c in comps if c.health == PlaneHealthState.RUNNING)
            }
            
        return report
