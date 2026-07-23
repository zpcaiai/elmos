#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


NODE_TYPES = {
    "capability", "skill", "tool", "runtime", "artifact", "test",
    "evidence", "policy", "route", "domain",
}
DEPENDENCY_RELATIONS = {"depends", "requires", "requires_tool", "route_includes"}
EDGE_RELATIONS = DEPENDENCY_RELATIONS | {"produces", "verifies", "governed_by"}
SHA256_REF = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_graph(graph: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["graph must be an object"]
    if graph.get("schema_version") != "elmos.capability-graph.v1":
        errors.append("invalid schema_version")
    snapshot_id = graph.get("snapshot_id")
    if not isinstance(snapshot_id, str) or SHA256_REF.fullmatch(snapshot_id) is None:
        errors.append("invalid snapshot_id")
    generated_at = graph.get("generated_at")
    try:
        if not isinstance(generated_at, str):
            raise ValueError
        parsed_timestamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if "T" not in generated_at or parsed_timestamp.tzinfo is None:
            raise ValueError
    except ValueError:
        errors.append("invalid generated_at")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return errors + ["nodes and edges must be arrays"]

    identifiers: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"node {index} must be an object")
            continue
        identifier = node.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"node {index} has invalid id")
            continue
        if identifier in identifiers:
            errors.append(f"duplicate node id: {identifier}")
        identifiers.add(identifier)
        if node.get("type") not in NODE_TYPES:
            errors.append(f"node {identifier} has invalid type")
        if not isinstance(node.get("name"), str) or not node["name"]:
            errors.append(f"node {identifier} has invalid name")
        if not isinstance(node.get("version"), str) or not node["version"]:
            errors.append(f"node {identifier} has invalid version")
        provenance = node.get("provenance")
        if not isinstance(provenance, dict) or not provenance:
            errors.append(f"node {identifier} has missing provenance")
        else:
            if not isinstance(provenance.get("source"), str) or not provenance["source"]:
                errors.append(f"node {identifier} has invalid provenance source")
            source_digest = provenance.get("source_digest")
            if not isinstance(source_digest, str) or SHA256_REF.fullmatch(source_digest) is None:
                errors.append(f"node {identifier} has invalid provenance digest")

    adjacency = {identifier: [] for identifier in identifiers}
    edge_keys: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edge {index} must be an object")
            continue
        source, target, relation = edge.get("from"), edge.get("to"), edge.get("relation")
        if not isinstance(source, str) or not isinstance(target, str):
            errors.append(f"edge {index} has invalid endpoints")
            continue
        if source not in identifiers or target not in identifiers:
            errors.append(f"edge {index} is dangling")
            continue
        if source == target:
            errors.append(f"edge {index} is self-referential")
        if relation not in EDGE_RELATIONS:
            errors.append(f"edge {index} has invalid relation")
            continue
        key = (source, target, relation)
        if key in edge_keys:
            errors.append(f"duplicate edge: {source}->{target}:{relation}")
        edge_keys.add(key)
        confidence = edge.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            errors.append(f"edge {index} has invalid confidence")
        blocking = edge.get("blocking")
        if not isinstance(blocking, bool):
            errors.append(f"edge {index} has invalid blocking flag")
        elif blocking and relation in DEPENDENCY_RELATIONS:
            adjacency[source].append(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> bool:
        if identifier in visiting:
            return True
        if identifier in visited:
            return False
        visiting.add(identifier)
        if any(visit(dependency) for dependency in adjacency[identifier]):
            return True
        visiting.remove(identifier)
        visited.add(identifier)
        return False

    if any(visit(identifier) for identifier in sorted(identifiers)):
        errors.append("blocking dependency cycle")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("graph")
    args = parser.parse_args()
    try:
        graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid graph document: {exc}", file=sys.stderr)
        return 2
    errors = validate_graph(graph)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("PASS: capability graph identity, references, provenance, and blocking DAG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
