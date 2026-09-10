from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict
from elmos_mature_platform.types import (
    ServiceEntry,
    SliDefinition,
    SloTarget,
    SloMeasurement,
    ServiceTier
)

class ServiceCatalogSloEngine:
    """Engine for managing service catalog and SLOs."""

    def __init__(self):
        self._services: Dict[str, ServiceEntry] = {}
        self._slis: Dict[str, SliDefinition] = {}
        self._slos: Dict[str, SloTarget] = {}
        self._measurements: Dict[str, List[SloMeasurement]] = defaultdict(list)

    def register_service(self, service: ServiceEntry) -> str:
        """Register service in catalog"""
        if service.service_id in self._services:
            raise ValueError(f"Service {service.service_id} already exists")
        
        # Verify dependencies exist
        for dep in service.dependencies:
            if dep not in self._services:
                raise ValueError(f"Dependency {dep} does not exist in catalog")
        
        self._services[service.service_id] = service
        return service.service_id

    def update_service(self, service_id: str, **kwargs) -> ServiceEntry:
        """Update service details"""
        if service_id not in self._services:
            raise ValueError(f"Service {service_id} not found")
            
        service = self._services[service_id]
        
        # Verify dependencies if updated
        if "dependencies" in kwargs:
            for dep in kwargs["dependencies"]:
                if dep not in self._services:
                    raise ValueError(f"Dependency {dep} does not exist in catalog")
                    
        for k, v in kwargs.items():
            if hasattr(service, k):
                setattr(service, k, v)
                
        return service

    def decommission_service(self, service_id: str) -> bool:
        """Remove (fail if other services depend on it)"""
        if service_id not in self._services:
            raise ValueError(f"Service {service_id} not found")
            
        # Check for dependents
        dependents = []
        for s in self._services.values():
            if service_id in s.dependencies:
                dependents.append(s.service_id)
                
        if dependents:
            raise ValueError(f"Cannot decommission service {service_id}, it has dependents: {', '.join(dependents)}")
            
        # Remove related SLIs and SLOs
        slis_to_remove = [sli_id for sli_id, sli in self._slis.items() if sli.service_id == service_id]
        for sli_id in slis_to_remove:
            del self._slis[sli_id]
            
        slos_to_remove = [slo_id for slo_id, slo in self._slos.items() if slo.service_id == service_id]
        for slo_id in slos_to_remove:
            del self._slos[slo_id]
            if slo_id in self._measurements:
                del self._measurements[slo_id]
                
        del self._services[service_id]
        return True

    def define_sli(self, sli: SliDefinition) -> str:
        """Define SLI for a service"""
        if sli.service_id not in self._services:
            raise ValueError(f"Service {sli.service_id} not found")
            
        if sli.sli_id in self._slis:
            raise ValueError(f"SLI {sli.sli_id} already exists")
            
        self._slis[sli.sli_id] = sli
        return sli.sli_id

    def set_slo_target(self, slo: SloTarget) -> str:
        """Set SLO target for an SLI"""
        if slo.service_id not in self._services:
            raise ValueError(f"Service {slo.service_id} not found")
            
        if slo.sli_id not in self._slis:
            raise ValueError(f"SLI {slo.sli_id} not found")
            
        if slo.slo_id in self._slos:
            raise ValueError(f"SLO {slo.slo_id} already exists")
            
        self._slos[slo.slo_id] = slo
        return slo.slo_id

    def record_measurement(self, measurement: SloMeasurement) -> None:
        """Record measurement, compute measured_percentage and budget_remaining_pct"""
        if measurement.slo_id not in self._slos:
            raise ValueError(f"SLO {measurement.slo_id} not found")
            
        slo = self._slos[measurement.slo_id]
        
        if measurement.total_events == 0:
            measurement.measured_percentage = 100.0
        else:
            measurement.measured_percentage = (measurement.good_events / measurement.total_events) * 100
            
        target = slo.target_percentage
        
        if target >= 100.0:
            budget_remaining_pct = 0.0 if measurement.measured_percentage < 100.0 else 100.0
        else:
            budget_remaining_pct = ((measurement.measured_percentage - target) / (100 - target)) * 100
            
        # Clamp to [0, 100]
        measurement.budget_remaining_pct = max(0.0, min(100.0, budget_remaining_pct))
        
        self._measurements[measurement.slo_id].append(measurement)

    def get_service(self, service_id: str) -> ServiceEntry:
        """Get service details"""
        if service_id not in self._services:
            raise ValueError(f"Service {service_id} not found")
        return self._services[service_id]

    def get_service_slos(self, service_id: str) -> List[Dict]:
        """SLOs with current measurements for service"""
        if service_id not in self._services:
            raise ValueError(f"Service {service_id} not found")
            
        result = []
        for slo in self._slos.values():
            if slo.service_id == service_id:
                latest_measurement = None
                if slo.slo_id in self._measurements and self._measurements[slo.slo_id]:
                    # Sort by measured_at
                    measurements = sorted(self._measurements[slo.slo_id], key=lambda m: m.measured_at)
                    latest_measurement = measurements[-1]
                    
                result.append({
                    "slo": slo,
                    "sli": self._slis[slo.sli_id],
                    "latest_measurement": latest_measurement
                })
        return result

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Full service dependency graph"""
        graph = {}
        for service_id, service in self._services.items():
            graph[service_id] = list(service.dependencies)
        return graph

    def detect_circular_dependencies(self) -> List[List[str]]:
        """Find circular dependency chains"""
        graph = self.get_dependency_graph()
        cycles = []
        
        for start_node in graph:
            visited = set()
            path = []
            
            def dfs(current):
                if current in path:
                    # Found cycle
                    cycle_start_idx = path.index(current)
                    cycle = path[cycle_start_idx:] + [current]
                    
                    # Normalize cycle to avoid duplicates
                    # Rotate cycle so minimum element is first
                    min_idx = cycle[:-1].index(min(cycle[:-1]))
                    normalized = cycle[min_idx:-1] + cycle[:min_idx] + [cycle[min_idx]]
                    
                    if normalized not in cycles:
                        cycles.append(normalized)
                    return
                    
                if current in visited:
                    return
                    
                visited.add(current)
                path.append(current)
                
                for neighbor in graph.get(current, []):
                    dfs(neighbor)
                    
                path.pop()
                
            dfs(start_node)
            
        return cycles

    def get_tier_report(self) -> Dict:
        """Services grouped by tier with SLO status"""
        report = defaultdict(list)
        
        for service_id, service in self._services.items():
            tier = service.tier
            
            # Compute overall SLO status for service
            slos = self.get_service_slos(service_id)
            is_healthy = True
            
            for slo_data in slos:
                m = slo_data["latest_measurement"]
                if m and m.measured_percentage < slo_data["slo"].target_percentage:
                    is_healthy = False
                    break
                    
            report[tier.value].append({
                "service_id": service_id,
                "name": service.name,
                "is_healthy": is_healthy,
                "slo_count": len(slos)
            })
            
        return dict(report)

    def get_services_below_target(self) -> List[Dict]:
        """Services with measured_percentage below target"""
        below_target = []
        
        for service_id in self._services:
            slos = self.get_service_slos(service_id)
            for slo_data in slos:
                m = slo_data["latest_measurement"]
                if m and m.measured_percentage < slo_data["slo"].target_percentage:
                    below_target.append({
                        "service_id": service_id,
                        "slo_id": slo_data["slo"].slo_id,
                        "target_percentage": slo_data["slo"].target_percentage,
                        "measured_percentage": m.measured_percentage,
                        "budget_remaining_pct": m.budget_remaining_pct
                    })
                    
        return below_target

    def get_catalog_report(self) -> Dict:
        """Full catalog summary"""
        graph = self.get_dependency_graph()
        
        # Calculate inverse dependencies (who depends on this service)
        inverse_deps = defaultdict(list)
        for s_id, deps in graph.items():
            for d in deps:
                inverse_deps[d].append(s_id)
                
        return {
            "total_services": len(self._services),
            "total_slis": len(self._slis),
            "total_slos": len(self._slos),
            "services": {
                s_id: {
                    "tier": s.tier.value,
                    "owner": s.owner_team,
                    "dependency_count": len(graph.get(s_id, [])),
                    "dependent_count": len(inverse_deps.get(s_id, [])),
                    "slo_count": len([slo for slo in self._slos.values() if slo.service_id == s_id])
                }
                for s_id, s in self._services.items()
            }
        }
