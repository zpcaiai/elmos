"""Typed architecture graphs, deterministic exports, diffs, and impact cones."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

from .repository import RepositoryEvidenceGraph
from .semantic import SemanticBundle


class ArchitectureNodeKind(str, Enum):
    MODULE = "module"
    SERVICE = "service"
    DATABASE = "database"
    MESSAGE = "message"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class ArchitectureNode:
    id: str
    kind: ArchitectureNodeKind
    name: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    authoritative: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "name": self.name,
            "attributes": dict(self.attributes),
            "evidence_refs": list(self.evidence_refs),
            "authoritative": self.authoritative,
        }


@dataclass(frozen=True, slots=True)
class ArchitectureEdge:
    source: str
    target: str
    relationship: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    authoritative: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "attributes": dict(self.attributes),
            "evidence_refs": list(self.evidence_refs),
            "authoritative": self.authoritative,
        }


@dataclass(frozen=True, slots=True)
class ArchitectureGraph:
    graph_digest: str
    snapshot_id: str
    nodes: tuple[ArchitectureNode, ...]
    edges: tuple[ArchitectureEdge, ...]

    @classmethod
    def create(
        cls,
        snapshot_id: str,
        nodes: Iterable[ArchitectureNode],
        edges: Iterable[ArchitectureEdge],
    ) -> "ArchitectureGraph":
        node_items = tuple(sorted(nodes, key=lambda item: item.id))
        if len({item.id for item in node_items}) != len(node_items):
            raise ValueError("architecture node ids must be unique")
        node_ids = {item.id for item in node_items}
        edge_items = tuple(
            sorted(
                edges,
                key=lambda item: (
                    item.source,
                    item.target,
                    item.relationship,
                    _digest(dict(item.attributes)),
                ),
            )
        )
        for edge in edge_items:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(
                    f"architecture edge references an unknown node: {edge.source} -> {edge.target}"
                )
        body = {
            "snapshot_id": snapshot_id,
            "nodes": [item.to_dict() for item in node_items],
            "edges": [item.to_dict() for item in edge_items],
        }
        return cls(_digest(body), snapshot_id, node_items, edge_items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_version": "elmos.ai/v3",
            "kind": "ArchitectureGraph",
            "graph_digest": self.graph_digest,
            "snapshot_id": self.snapshot_id,
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, indent=indent)

    def to_calm(self) -> dict[str, Any]:
        """Export a deterministic CALM-shaped architecture document.

        This is a bounded structural export, not a CALM certification claim.
        Evidence and authority flags remain attached as metadata.
        """

        return {
            "$schema": "https://calm.finos.org/release/1.0/meta/calm.json",
            "unique-id": f"urn:elmos:architecture:{self.graph_digest}",
            "name": "ELMOS repository architecture",
            "description": f"Source-bound architecture projection for {self.snapshot_id}",
            "nodes": [
                {
                    "unique-id": node.id,
                    "node-type": node.kind.value,
                    "name": node.name,
                    "description": str(node.attributes.get("description", node.name)),
                    "metadata": [
                        {"key": "authoritative", "value": node.authoritative},
                        {"key": "evidence_refs", "value": list(node.evidence_refs)},
                        {"key": "attributes", "value": dict(node.attributes)},
                    ],
                }
                for node in self.nodes
            ],
            "relationships": [
                {
                    "unique-id": f"rel:{_digest(edge.to_dict())}",
                    "relationship-type": edge.relationship,
                    "source": {"node": edge.source},
                    "destination": {"node": edge.target},
                    "metadata": [
                        {"key": "authoritative", "value": edge.authoritative},
                        {"key": "evidence_refs", "value": list(edge.evidence_refs)},
                        {"key": "attributes", "value": dict(edge.attributes)},
                    ],
                }
                for edge in self.edges
            ],
        }

    def graph_rows(self) -> tuple[dict[str, Any], ...]:
        node_by_id = {node.id: node for node in self.nodes}
        rows: list[dict[str, Any]] = []
        for node in self.nodes:
            rows.append(
                {
                    "row_type": "node",
                    "id": node.id,
                    "kind": node.kind.value,
                    "name": node.name,
                    "source": None,
                    "target": None,
                    "relationship": None,
                    "authoritative": node.authoritative,
                    "evidence_refs": list(node.evidence_refs),
                }
            )
        for edge in self.edges:
            rows.append(
                {
                    "row_type": "edge",
                    "id": f"edge:{_digest(edge.to_dict())}",
                    "kind": None,
                    "name": None,
                    "source": edge.source,
                    "source_name": node_by_id[edge.source].name,
                    "target": edge.target,
                    "target_name": node_by_id[edge.target].name,
                    "relationship": edge.relationship,
                    "authoritative": edge.authoritative,
                    "evidence_refs": list(edge.evidence_refs),
                }
            )
        return tuple(rows)

    def impact(
        self,
        node_ids: Iterable[str],
        *,
        direction: str = "both",
        max_depth: int = 32,
    ) -> tuple[str, ...]:
        if direction not in {"upstream", "downstream", "both"}:
            raise ValueError("direction must be upstream, downstream, or both")
        if max_depth < 0:
            raise ValueError("max_depth cannot be negative")
        known = {node.id for node in self.nodes}
        seeds = set(node_ids)
        unknown = seeds - known
        if unknown:
            raise KeyError(f"unknown architecture nodes: {sorted(unknown)}")
        outgoing: dict[str, set[str]] = {}
        incoming: dict[str, set[str]] = {}
        for edge in self.edges:
            outgoing.setdefault(edge.source, set()).add(edge.target)
            incoming.setdefault(edge.target, set()).add(edge.source)
        visited = set(seeds)
        frontier = set(seeds)
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for item in frontier:
                if direction in {"downstream", "both"}:
                    next_frontier.update(outgoing.get(item, ()))
                if direction in {"upstream", "both"}:
                    next_frontier.update(incoming.get(item, ()))
            next_frontier -= visited
            if not next_frontier:
                break
            visited.update(next_frontier)
            frontier = next_frontier
        return tuple(sorted(visited))


@dataclass(frozen=True, slots=True)
class ArchitectureDiff:
    before_digest: str
    after_digest: str
    added_nodes: tuple[ArchitectureNode, ...]
    removed_nodes: tuple[ArchitectureNode, ...]
    changed_nodes: tuple[tuple[ArchitectureNode, ArchitectureNode], ...]
    added_edges: tuple[ArchitectureEdge, ...]
    removed_edges: tuple[ArchitectureEdge, ...]
    impacted_before: tuple[str, ...]
    impacted_after: tuple[str, ...]

    @classmethod
    def compare(
        cls, before: ArchitectureGraph, after: ArchitectureGraph
    ) -> "ArchitectureDiff":
        before_nodes = {node.id: node for node in before.nodes}
        after_nodes = {node.id: node for node in after.nodes}
        added_ids = sorted(set(after_nodes) - set(before_nodes))
        removed_ids = sorted(set(before_nodes) - set(after_nodes))
        common = sorted(set(before_nodes) & set(after_nodes))
        changed = tuple(
            (before_nodes[node_id], after_nodes[node_id])
            for node_id in common
            if before_nodes[node_id].to_dict() != after_nodes[node_id].to_dict()
        )
        before_edge_map = {_edge_key(edge): edge for edge in before.edges}
        after_edge_map = {_edge_key(edge): edge for edge in after.edges}
        changed_before = set(removed_ids) | {left.id for left, _ in changed}
        changed_after = set(added_ids) | {right.id for _, right in changed}
        for key in set(before_edge_map) ^ set(after_edge_map):
            edge = before_edge_map.get(key) or after_edge_map[key]
            changed_before.update(
                node_id
                for node_id in (edge.source, edge.target)
                if node_id in before_nodes
            )
            changed_after.update(
                node_id
                for node_id in (edge.source, edge.target)
                if node_id in after_nodes
            )
        return cls(
            before.graph_digest,
            after.graph_digest,
            tuple(after_nodes[item] for item in added_ids),
            tuple(before_nodes[item] for item in removed_ids),
            changed,
            tuple(after_edge_map[key] for key in sorted(set(after_edge_map) - set(before_edge_map))),
            tuple(before_edge_map[key] for key in sorted(set(before_edge_map) - set(after_edge_map))),
            before.impact(changed_before) if changed_before else (),
            after.impact(changed_after) if changed_after else (),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "added_nodes": [item.to_dict() for item in self.added_nodes],
            "removed_nodes": [item.to_dict() for item in self.removed_nodes],
            "changed_nodes": [
                {"before": before.to_dict(), "after": after.to_dict()}
                for before, after in self.changed_nodes
            ],
            "added_edges": [item.to_dict() for item in self.added_edges],
            "removed_edges": [item.to_dict() for item in self.removed_edges],
            "impacted_before": list(self.impacted_before),
            "impacted_after": list(self.impacted_after),
        }


class ArchitectureExtractor:
    """Project typed architecture facts from repository and semantic evidence.

    Inferred service/database classification is explicitly non-authoritative.
    External compiler adapters may add authoritative nodes using
    :class:`ArchitectureGraph.create`.
    """

    _SERVICE_MANIFESTS = {
        "Cargo.toml",
        "build.gradle",
        "build.gradle.kts",
        "go.mod",
        "package.json",
        "pom.xml",
        "pyproject.toml",
    }

    def extract(
        self,
        repository: RepositoryEvidenceGraph,
        semantic: SemanticBundle,
    ) -> ArchitectureGraph:
        nodes: dict[str, ArchitectureNode] = {}
        edges: dict[tuple[str, str, str, str], ArchitectureEdge] = {}
        for graph_node in repository.nodes:
            if graph_node.kind != "module":
                continue
            node_id = f"arch:module:{graph_node.name}"
            nodes[node_id] = ArchitectureNode(
                node_id,
                ArchitectureNodeKind.MODULE,
                graph_node.name,
                {"repository_node": graph_node.id},
                graph_node.evidence_refs,
                True,
            )
        for item in repository.files:
            pure = PurePosixPath(item.path)
            parent = "." if pure.parent.as_posix() == "." else pure.parent.as_posix()
            module_id = f"arch:module:{parent}"
            if pure.name in self._SERVICE_MANIFESTS:
                service_id = f"arch:service:{parent}"
                nodes[service_id] = ArchitectureNode(
                    service_id,
                    ArchitectureNodeKind.SERVICE,
                    parent,
                    {"manifest": item.path, "inference": "build-manifest"},
                    (item.evidence_id,),
                    False,
                )
                edges[_raw_edge_key(module_id, service_id, "defines")] = ArchitectureEdge(
                    module_id,
                    service_id,
                    "defines",
                    {"inference": "build-manifest"},
                    (item.evidence_id,),
                    False,
                )
            if item.language == "sql":
                database_id = f"arch:database:{item.path}"
                nodes[database_id] = ArchitectureNode(
                    database_id,
                    ArchitectureNodeKind.DATABASE,
                    item.path,
                    {"inference": "sql-source", "dialect": "unknown"},
                    (item.evidence_id,),
                    False,
                )
                edges[_raw_edge_key(module_id, database_id, "contains-data-contract")] = ArchitectureEdge(
                    module_id,
                    database_id,
                    "contains-data-contract",
                    {},
                    (item.evidence_id,),
                    False,
                )

        file_module: dict[str, str] = {}
        for item in repository.files:
            parent = PurePosixPath(item.path).parent.as_posix()
            file_module[item.path] = f"arch:module:{'.' if parent == '.' else parent}"
        for shard in semantic.shards:
            source_module = file_module.get(shard.path, "arch:module:.")
            for dependency in shard.invalidation_dependencies:
                target_path = dependency.rsplit(":", 1)[0]
                target_module = file_module.get(target_path)
                if target_module and target_module != source_module:
                    key = _raw_edge_key(source_module, target_module, "depends-on")
                    edges[key] = ArchitectureEdge(
                        source_module,
                        target_module,
                        "depends-on",
                        {"source_shard": shard.shard_digest},
                        tuple(sorted({ref for node in shard.nodes for ref in node.evidence_refs})),
                        shard.authoritative,
                    )
            for edge in shard.edges:
                if not edge.target.startswith("external:"):
                    continue
                external_id = f"arch:{edge.target}"
                nodes.setdefault(
                    external_id,
                    ArchitectureNode(
                        external_id,
                        ArchitectureNodeKind.EXTERNAL,
                        edge.target.removeprefix("external:"),
                        {"inference": "compiler-import"},
                        edge.evidence_refs,
                        edge.authoritative,
                    ),
                )
                key = _raw_edge_key(source_module, external_id, "uses")
                edges[key] = ArchitectureEdge(
                    source_module,
                    external_id,
                    "uses",
                    {"semantic_edge": edge.kind},
                    edge.evidence_refs,
                    edge.authoritative,
                )
        return ArchitectureGraph.create(repository.snapshot_id, nodes.values(), edges.values())


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _edge_key(edge: ArchitectureEdge) -> str:
    return _digest(edge.to_dict())


def _raw_edge_key(source: str, target: str, relationship: str) -> tuple[str, str, str, str]:
    return (source, target, relationship, "")


__all__ = [
    "ArchitectureDiff",
    "ArchitectureEdge",
    "ArchitectureExtractor",
    "ArchitectureGraph",
    "ArchitectureNode",
    "ArchitectureNodeKind",
]
