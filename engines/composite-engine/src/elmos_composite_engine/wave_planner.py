"""Migration wave planner for complex multi-system modernization landscapes."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set

from .models import DependencyEdge, MigrationWave, SystemNode
from .topology import DependencyGraphAnalyzer


class MigrationWavePlanner:
    """Plans ordered migration waves ensuring dependencies and circular units are respected."""

    def plan_waves(self, nodes: List[SystemNode], edges: List[DependencyEdge]) -> List[MigrationWave]:
        analyzer = DependencyGraphAnalyzer(nodes, edges)
        sccs = analyzer.find_strongly_connected_components()

        # Map each node in an SCC to its canonical SCC group ID
        scc_map: Dict[str, str] = {}
        scc_groups: Dict[str, List[str]] = {}
        for idx, scc in enumerate(sccs):
            group_id = f"scc-group-{idx}"
            scc_groups[group_id] = scc
            for node_id in scc:
                scc_map[node_id] = group_id

        # Determine all units (individual nodes or SCC groups)
        units: Dict[str, List[str]] = {}
        for n in nodes:
            if n.nodeId in scc_map:
                group_id = scc_map[n.nodeId]
                units[group_id] = scc_groups[group_id]
            else:
                units[n.nodeId] = [n.nodeId]

        # Build unit-level dependencies
        unit_deps: Dict[str, Set[str]] = defaultdict(set)
        for edge in edges:
            if edge.validity != "ACTIVE":
                continue
            src_unit = scc_map.get(edge.sourceNodeId, edge.sourceNodeId)
            tgt_unit = scc_map.get(edge.targetNodeId, edge.targetNodeId)
            if src_unit != tgt_unit:
                # src calls target, so target must migrate before or with src
                unit_deps[src_unit].add(tgt_unit)

        # Compute waves (Kahn's level assignment)
        assigned: Set[str] = set()
        waves: List[MigrationWave] = []
        wave_idx = 1

        remaining_units = set(units.keys())
        while remaining_units:
            # Find units whose target dependencies are all assigned
            ready_units = {
                u for u in remaining_units
                if unit_deps[u].issubset(assigned)
            }
            if not ready_units:
                # Cycle or unresolvable: bundle remaining into final wave
                ready_units = remaining_units

            wave_nodes = []
            for u in sorted(ready_units):
                wave_nodes.extend(units[u])

            prereqs = list(range(1, wave_idx))
            waves.append(MigrationWave(
                waveNumber=wave_idx,
                name=f"Migration Wave {wave_idx}",
                nodes=sorted(list(set(wave_nodes))),
                prerequisiteWaves=prereqs,
                estimatedRisk="LOW" if wave_idx == 1 else "MEDIUM"
            ))

            assigned.update(ready_units)
            remaining_units.difference_update(ready_units)
            wave_idx += 1

        return waves
