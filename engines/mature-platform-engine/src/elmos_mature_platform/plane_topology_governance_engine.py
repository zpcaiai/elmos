import uuid
import datetime
from typing import Dict, List, Optional
from elmos_mature_platform.types import (
    PlaneFunction,
    PlaneIsolation,
    PlaneDefinition,
    PlaneGovernanceTopology as PlaneTopology,
    PlaneViolation
)

class PlaneTopologyGovernanceEngine:
    """Engine for Plane Topology Governance."""

    def __init__(self):
        self.planes: Dict[str, PlaneDefinition] = {}
        self.topologies: Dict[str, PlaneTopology] = {}

    def define_plane(self, plane: PlaneDefinition) -> str:
        """Define a plane and store it in memory."""
        self.planes[plane.plane_id] = plane
        return plane.plane_id

    def create_topology(self, topology: PlaneTopology) -> str:
        """Create a topology and store it."""
        self.topologies[topology.topology_id] = topology
        return topology.topology_id

    def add_plane_to_topology(self, topology_id: str, plane_id: str) -> None:
        """Add a plane to a topology."""
        if topology_id not in self.topologies:
            raise ValueError(f"Topology {topology_id} not found")
        if plane_id not in self.planes:
            raise ValueError(f"Plane {plane_id} not found")
        if plane_id not in self.topologies[topology_id].plane_ids:
            self.topologies[topology_id].plane_ids.append(plane_id)

    def validate_dependencies(self, topology_id: str) -> List[PlaneViolation]:
        """Check forbidden dependencies."""
        if topology_id not in self.topologies:
            raise ValueError(f"Topology {topology_id} not found")
        
        topology = self.topologies[topology_id]
        violations = []
        
        for p_id in topology.plane_ids:
            plane = self.planes.get(p_id)
            if not plane:
                continue
            for target in plane.allowed_dependencies:
                if target in plane.forbidden_dependencies:
                    violations.append(PlaneViolation(
                        violation_id=str(uuid.uuid4()),
                        source_plane=p_id,
                        target_plane=target,
                        rule="forbidden_dependency",
                        description=f"Plane {p_id} has forbidden dependency on {target}",
                        severity="high"
                    ))
                elif target not in self.planes:
                    violations.append(PlaneViolation(
                        violation_id=str(uuid.uuid4()),
                        source_plane=p_id,
                        target_plane=target,
                        rule="missing_dependency",
                        description=f"Plane {p_id} depends on unknown plane {target}",
                        severity="high"
                    ))
        return violations

    def detect_circular_dependencies(self, topology_id: str) -> List[PlaneViolation]:
        """Find circular dependencies."""
        if topology_id not in self.topologies:
            raise ValueError(f"Topology {topology_id} not found")
        
        topology = self.topologies[topology_id]
        violations = []
        
        graph = {}
        for p_id in topology.plane_ids:
            plane = self.planes.get(p_id)
            if plane:
                graph[p_id] = [dep for dep in plane.allowed_dependencies if dep in topology.plane_ids]
        
        visited = set()
        rec_stack = set()
        path = []

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    idx = path.index(neighbor)
                    cycle = path[idx:] + [neighbor]
                    violations.append(PlaneViolation(
                        violation_id=str(uuid.uuid4()),
                        source_plane=node,
                        target_plane=neighbor,
                        rule="circular_dependency",
                        description=f"Circular dependency detected: {' -> '.join(cycle)}",
                        severity="critical"
                    ))
                    return True
            
            rec_stack.remove(node)
            path.pop()
            return False
            
        for node in graph:
            if node not in visited:
                dfs(node)
                
        return violations

    def check_isolation_compliance(self, topology_id: str) -> List[PlaneViolation]:
        """Verify isolation rules."""
        if topology_id not in self.topologies:
            raise ValueError(f"Topology {topology_id} not found")
            
        topology = self.topologies[topology_id]
        violations = []
        
        for p_id in topology.plane_ids:
            plane = self.planes.get(p_id)
            if not plane:
                continue
            for target_id in plane.allowed_dependencies:
                target_plane = self.planes.get(target_id)
                if not target_plane:
                    continue
                
                # Rule: DEDICATED planes can only be called by planes of the same function
                if target_plane.isolation == PlaneIsolation.DEDICATED:
                    if plane.function != target_plane.function:
                        violations.append(PlaneViolation(
                            violation_id=str(uuid.uuid4()),
                            source_plane=p_id,
                            target_plane=target_id,
                            rule="isolation_violation",
                            description=f"Plane {p_id} ({plane.function.value}) cannot call DEDICATED plane {target_id} ({target_plane.function.value})",
                            severity="high"
                        ))
        return violations

    def check_mtls_compliance(self, topology_id: str) -> List[PlaneViolation]:
        """Check mTLS requirements."""
        if topology_id not in self.topologies:
            raise ValueError(f"Topology {topology_id} not found")
            
        topology = self.topologies[topology_id]
        violations = []
        
        for p_id in topology.plane_ids:
            plane = self.planes.get(p_id)
            if not plane:
                continue
            for target_id in plane.allowed_dependencies:
                target_plane = self.planes.get(target_id)
                if not target_plane:
                    continue
                
                # Rule: If target requires mTLS, source must also support/require it
                if target_plane.requires_mtls and not plane.requires_mtls:
                    violations.append(PlaneViolation(
                        violation_id=str(uuid.uuid4()),
                        source_plane=p_id,
                        target_plane=target_id,
                        rule="mtls_violation",
                        description=f"Plane {p_id} lacks mTLS but calls {target_id} which requires it",
                        severity="high"
                    ))
        return violations

    def evaluate_topology(self, topology_id: str) -> PlaneTopology:
        """Full evaluation, set compliant flag."""
        if topology_id not in self.topologies:
            raise ValueError(f"Topology {topology_id} not found")
            
        topology = self.topologies[topology_id]
        all_violations = []
        
        all_violations.extend(self.validate_dependencies(topology_id))
        all_violations.extend(self.detect_circular_dependencies(topology_id))
        all_violations.extend(self.check_isolation_compliance(topology_id))
        all_violations.extend(self.check_mtls_compliance(topology_id))
        
        topology.violations = [v.violation_id for v in all_violations]
        topology.compliant = len(all_violations) == 0
        topology.evaluated_at = datetime.datetime.now().isoformat()
        
        # Store violations somewhere if needed? Not strictly required by schema unless we store them globally,
        # but returning the topology is enough as its `violations` field just has IDs.
        # Actually wait, `violations` list in topology has string IDs, but where are the violation objects stored?
        # Let's attach them to an engine attribute for compliance report.
        if not hasattr(self, 'violations_store'):
            self.violations_store = {}
        for v in all_violations:
            self.violations_store[v.violation_id] = v
            
        return topology

    def get_plane_graph(self, topology_id: str) -> Dict:
        """Dependency graph."""
        if topology_id not in self.topologies:
            raise ValueError(f"Topology {topology_id} not found")
            
        topology = self.topologies[topology_id]
        graph = {}
        for p_id in topology.plane_ids:
            plane = self.planes.get(p_id)
            if plane:
                graph[p_id] = {
                    "dependencies": [dep for dep in plane.allowed_dependencies if dep in topology.plane_ids],
                    "function": plane.function.value,
                    "isolation": plane.isolation.value
                }
        return {"topology_id": topology_id, "nodes": graph}

    def get_compliance_report(self, topology_id: str) -> Dict:
        """Summary: planes, violations, compliance."""
        if topology_id not in self.topologies:
            raise ValueError(f"Topology {topology_id} not found")
            
        topology = self.topologies[topology_id]
        
        # Make sure we have a store, even if empty
        if not hasattr(self, 'violations_store'):
            self.violations_store = {}
            
        violation_details = [
            {
                "violation_id": v_id,
                "rule": self.violations_store[v_id].rule if v_id in self.violations_store else "unknown",
                "description": self.violations_store[v_id].description if v_id in self.violations_store else "",
                "severity": self.violations_store[v_id].severity if v_id in self.violations_store else ""
            }
            for v_id in topology.violations
        ]
        
        return {
            "topology_id": topology_id,
            "name": topology.name,
            "compliant": topology.compliant,
            "evaluated_at": topology.evaluated_at,
            "plane_count": len(topology.plane_ids),
            "violation_count": len(topology.violations),
            "violations": violation_details
        }
