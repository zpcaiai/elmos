"""Migration Entity Relations Engine (Batch 41 - Skill 1395).

Maintains a graph of migration entities (Projects, Modules, Rules, Patches,
and Evidences), tracing bidirectional lineage, provenance, and verification closure.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import uuid

from .types import (
    EntityLineageTrace,
    EntityRelationType,
    MigrationEntity,
    MigrationEntityType,
    MigrationRelationEdge,
)


class MigrationEntityRelationsEngine:
    """Manages relationships and lineage across migration artifacts and rules."""

    def __init__(self) -> None:
        self._entities: Dict[str, MigrationEntity] = {}
        self._edges: Dict[str, MigrationRelationEdge] = {}
        self._outgoing: Dict[str, List[str]] = {}
        self._incoming: Dict[str, List[str]] = {}

    def register_entity(self, entity: MigrationEntity) -> str:
        """Register a migration entity."""
        if not entity.entity_id:
            entity.entity_id = f"ent-{uuid.uuid4().hex[:8]}"
        if not entity.name:
            raise ValueError("Entity name is required")
        if not entity.created_at:
            entity.created_at = datetime.now(timezone.utc).isoformat()

        self._entities[entity.entity_id] = entity
        self._outgoing.setdefault(entity.entity_id, [])
        self._incoming.setdefault(entity.entity_id, [])
        return entity.entity_id

    def connect_entities(
        self,
        source_id: str,
        target_id: str,
        relation: EntityRelationType,
        confidence: float = 1.0,
        note: str = "",
    ) -> str:
        """Create a directed relation between two migration entities."""
        if source_id not in self._entities:
            raise ValueError(f"Source entity not found: {source_id}")
        if target_id not in self._entities:
            raise ValueError(f"Target entity not found: {target_id}")

        edge_id = f"edge-{uuid.uuid4().hex[:8]}"
        edge = MigrationRelationEdge(
            edge_id=edge_id,
            source_entity_id=source_id,
            target_entity_id=target_id,
            relation_type=relation,
            confidence=confidence,
            established_at=datetime.now(timezone.utc).isoformat(),
            provenance_note=note,
        )
        self._edges[edge_id] = edge
        self._outgoing[source_id].append(edge_id)
        self._incoming[target_id].append(edge_id)
        return edge_id

    def get_entity(self, entity_id: str) -> Optional[MigrationEntity]:
        """Retrieve an entity by identifier."""
        return self._entities.get(entity_id)

    def trace_patch_provenance(self, patch_id: str) -> EntityLineageTrace:
        """Trace backward lineage from a patch to its origin project."""
        if patch_id not in self._entities:
            raise ValueError(f"Patch entity not found: {patch_id}")

        trace = EntityLineageTrace(
            trace_id=f"trace-{uuid.uuid4().hex[:8]}",
            root_entity_id=patch_id,
            lineage_path=[patch_id],
        )

        # Check if patch is verified
        verifications = self.find_verifications_for_patch(patch_id)
        trace.has_unverified_patch = (len(verifications) == 0)

        # BFS traverse incoming connections
        queue = deque([patch_id])
        visited: Set[str] = {patch_id}
        reached_project = False

        while queue:
            curr_id = queue.popleft()
            curr_ent = self._entities.get(curr_id)
            if curr_ent and curr_ent.entity_type == MigrationEntityType.PROJECT:
                reached_project = True

            for edge_id in self._incoming.get(curr_id, []):
                edge = self._edges[edge_id]
                src = edge.source_entity_id
                if src not in visited:
                    visited.add(src)
                    queue.append(src)
                    trace.lineage_path.append(src)

        trace.complete = reached_project
        return trace

    def find_verifications_for_patch(self, patch_id: str) -> List[MigrationEntity]:
        """Return all verification evidence entities linked to a patch."""
        if patch_id not in self._entities:
            raise ValueError(f"Patch entity not found: {patch_id}")

        verifications = []
        for edge_id in self._outgoing.get(patch_id, []):
            edge = self._edges[edge_id]
            if edge.relation_type == EntityRelationType.VERIFIED_BY:
                target = self._entities.get(edge.target_entity_id)
                if target:
                    verifications.append(target)
        return verifications

    def find_affected_patches_by_rule(self, rule_id: str) -> List[MigrationEntity]:
        """Return all patches produced by a specific transformation rule."""
        if rule_id not in self._entities:
            raise ValueError(f"Rule entity not found: {rule_id}")

        patches = []
        for edge_id in self._outgoing.get(rule_id, []):
            edge = self._edges[edge_id]
            if edge.relation_type == EntityRelationType.PRODUCED_PATCH:
                target = self._entities.get(edge.target_entity_id)
                if target and target.entity_type == MigrationEntityType.GENERATED_PATCH:
                    patches.append(target)
        return patches

    def invalidate_rule_and_descendants(self, rule_id: str, reason: str) -> List[str]:
        """Mark a rule and its derived patches as invalidated."""
        rule = self.get_entity(rule_id)
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        affected_ids = [rule_id]
        patches = self.find_affected_patches_by_rule(rule_id)
        for p in patches:
            affected_ids.append(p.entity_id)
            self.connect_entities(
                source_id=rule_id,
                target_id=p.entity_id,
                relation=EntityRelationType.INVALIDATED_BY,
                note=f"Rule invalidated: {reason}",
            )
        return affected_ids

    def detect_orphan_entities(self) -> List[MigrationEntity]:
        """Return entities that have zero incoming and outgoing edges."""
        orphans = []
        for ent_id, ent in self._entities.items():
            in_count = len(self._incoming.get(ent_id, []))
            out_count = len(self._outgoing.get(ent_id, []))
            if in_count == 0 and out_count == 0:
                orphans.append(ent)
        return orphans

    def get_entity_graph_density(self) -> Dict[str, Any]:
        """Compute density, breakdown, and topological stats of the entity graph."""
        total_entities = len(self._entities)
        total_edges = len(self._edges)

        type_counts: Dict[str, int] = {}
        for ent in self._entities.values():
            type_counts[ent.entity_type.value] = type_counts.get(ent.entity_type.value, 0) + 1

        relation_counts: Dict[str, int] = {}
        for edge in self._edges.values():
            relation_counts[edge.relation_type.value] = (
                relation_counts.get(edge.relation_type.value, 0) + 1
            )

        avg_degree = (2.0 * total_edges / total_entities) if total_entities > 0 else 0.0

        return {
            "total_entities": total_entities,
            "total_edges": total_edges,
            "average_degree": round(avg_degree, 2),
            "entity_types": type_counts,
            "relation_types": relation_counts,
        }

    def verify_closed_provenance(self, project_id: str) -> bool:
        """Verify that all patches stemming from this project have associated verification evidence."""
        if project_id not in self._entities:
            raise ValueError(f"Project entity not found: {project_id}")

        # Find all reachable patches from project
        queue = deque([project_id])
        visited: Set[str] = {project_id}
        project_patches: List[str] = []

        while queue:
            curr = queue.popleft()
            for edge_id in self._outgoing.get(curr, []):
                edge = self._edges[edge_id]
                target_id = edge.target_entity_id
                target_ent = self._entities.get(target_id)
                if target_ent and target_ent.entity_type == MigrationEntityType.GENERATED_PATCH:
                    if target_id not in project_patches:
                        project_patches.append(target_id)
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append(target_id)

        if not project_patches:
            return True

        for patch_id in project_patches:
            verifications = self.find_verifications_for_patch(patch_id)
            if not verifications:
                return False

        return True
