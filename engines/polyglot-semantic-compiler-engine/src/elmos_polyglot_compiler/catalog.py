"""Digest-bound compiled catalog for all 300 exact source Skill identities."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .contracts import ContractError, canonical_json
from .models import RouteCell, RouteCertificationPlan, SkillDefinition


EXPECTED_ARCHIVE_SHA256 = "7bce369fdeb9b3f86753c353e2d72bb53bb9e91e7368abc7c24a26c132d1db17"
EXPECTED_BATCH_COUNTS = {
    "A": 16,
    "B": 16,
    "C": 16,
    "D": 16,
    "E": 20,
    "F": 22,
    "G": 24,
    "H": 22,
    "I": 16,
    "J": 16,
    "K": 14,
    "L": 16,
    "M": 18,
    "N": 16,
    "O": 14,
    "P": 12,
    "Q": 14,
    "R": 12,
}


class CatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompiledCatalog:
    raw: Mapping[str, Any]
    skills: tuple[SkillDefinition, ...]
    skills_by_name: Mapping[str, SkillDefinition]
    routes: tuple[RouteCell, ...]
    routes_by_id: Mapping[str, RouteCell]
    reference_routes: tuple[RouteCertificationPlan, ...]
    reference_routes_by_id: Mapping[str, RouteCertificationPlan]
    digest: str

    def dependency_closure(self, requested: Sequence[str]) -> tuple[SkillDefinition, ...]:
        if not requested:
            raise CatalogError("at least one Skill is required")
        selected: set[str] = set()
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in selected:
                return
            if name in visiting:
                raise CatalogError("compiled Skill dependency graph contains a cycle")
            definition = self.skills_by_name.get(name)
            if definition is None:
                raise CatalogError(f"unknown Skill in dependency request: {name}")
            visiting.add(name)
            for dependency in definition.dependencies:
                visit(dependency)
            visiting.remove(name)
            selected.add(name)

        for name in requested:
            if not isinstance(name, str):
                raise CatalogError("Skill names must be strings")
            visit(name)
        return tuple(item for item in self.skills if item.name in selected)


def _read_resource() -> tuple[dict[str, Any], str]:
    resource_root = Path(__file__).resolve().parent / "resources"
    catalog_path = resource_root / "compiled-catalog.json"
    digest_path = resource_root / "compiled-catalog.sha256"
    for path in (catalog_path, digest_path):
        if path.is_symlink() or not path.is_file():
            raise CatalogError(f"compiled catalog resource is unavailable: {path.name}")
    value = catalog_path.read_bytes()
    if len(value) > 8 * 1024 * 1024:
        raise CatalogError("compiled catalog exceeds the bounded runtime limit")
    expected = digest_path.read_text(encoding="ascii").strip()
    observed = hashlib.sha256(value).hexdigest()
    if expected != observed:
        raise CatalogError("compiled catalog digest mismatch")
    try:
        document = json.loads(value)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError("compiled catalog is not valid JSON") from exc
    if not isinstance(document, dict):
        raise CatalogError("compiled catalog root must be an object")
    if canonical_json(document) + b"\n" != value:
        raise CatalogError("compiled catalog is not canonical repository output")
    return document, "sha256:" + observed


def _validate_skill_dag(skills: tuple[SkillDefinition, ...]) -> None:
    names = {item.name for item in skills}
    indegree = {item.name: len(item.dependencies) for item in skills}
    downstream: dict[str, list[str]] = {name: [] for name in names}
    edge_count = 0
    for item in skills:
        if item.name in item.dependencies:
            raise CatalogError(f"Skill has a self dependency: {item.name}")
        for dependency in item.dependencies:
            if dependency not in names:
                raise CatalogError(f"Skill dependency is missing: {item.name}->{dependency}")
            downstream[dependency].append(item.name)
            edge_count += 1
    if edge_count != 537:
        raise CatalogError(f"compiled Skill dependency edge count differs: {edge_count}")
    ready = deque(sorted(name for name, value in indegree.items() if value == 0))
    visited = 0
    while ready:
        name = ready.popleft()
        visited += 1
        for dependent in sorted(downstream[name]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
    if visited != 300:
        raise CatalogError("compiled Skill dependency graph contains a cycle")


def _parse_catalog(document: Mapping[str, Any], digest: str) -> CompiledCatalog:
    package = document.get("package")
    source = document.get("source")
    counts = document.get("counts")
    if not isinstance(package, Mapping) or package.get("version") != "3.0.0":
        raise CatalogError("compiled catalog package identity differs")
    if not isinstance(source, Mapping) or source.get("archive_sha256") != EXPECTED_ARCHIVE_SHA256:
        raise CatalogError("compiled catalog source digest differs")
    if not isinstance(counts, Mapping):
        raise CatalogError("compiled catalog counts are missing")
    expected_counts = {
        "skills": 300,
        "dependency_edges": 537,
        "technologies": 28,
        "repository_surfaces": 8,
        "route_cells": 784,
        "reference_routes": 40,
    }
    if any(counts.get(key) != value for key, value in expected_counts.items()):
        raise CatalogError("compiled catalog cardinalities differ")

    raw_skills = document.get("skills")
    if not isinstance(raw_skills, list) or len(raw_skills) != 300:
        raise CatalogError("compiled catalog must contain exactly 300 Skills")
    try:
        skills = tuple(SkillDefinition.from_mapping(item) for item in raw_skills)
    except (KeyError, TypeError, ValueError, ContractError) as exc:
        raise CatalogError("compiled Skill row is invalid") from exc
    if tuple(item.ordinal for item in skills) != tuple(range(1, 301)):
        raise CatalogError("compiled Skill ordinals must be contiguous")
    if tuple(item.source_id for item in skills) != tuple(
        f"ELMOS-POLY-{index:03d}" for index in range(1, 301)
    ):
        raise CatalogError("compiled Skill source IDs differ")
    if len({item.name for item in skills}) != 300:
        raise CatalogError("compiled Skill names must be unique")
    if Counter(item.batch.value for item in skills) != Counter(EXPECTED_BATCH_COUNTS):
        raise CatalogError("compiled Skill batch counts differ")
    _validate_skill_dag(skills)
    skills_by_name = MappingProxyType({item.name: item for item in skills})

    raw_routes = document.get("routes")
    if not isinstance(raw_routes, list) or len(raw_routes) != 784:
        raise CatalogError("compiled catalog must contain exactly 784 route cells")
    routes: list[RouteCell] = []
    route_pairs: set[tuple[str, str]] = set()
    for row in raw_routes:
        if not isinstance(row, Mapping):
            raise CatalogError("compiled route row must be an object")
        source_language = str(row.get("source"))
        target_language = str(row.get("target"))
        pair = (source_language, target_language)
        if pair in route_pairs or row.get("readiness") != "not-run":
            raise CatalogError("compiled route matrix contains a duplicate or promoted route")
        route_pairs.add(pair)
        routes.append(
            RouteCell(
                route_id=str(row.get("route_id", f"{source_language}-to-{target_language}")),
                source_language=source_language,
                target_language=target_language,
                route_class=str(row.get("route_class")),
                default_mode=str(row.get("default_mode")),
                minimum_gate=str(row.get("minimum_gate")),
                readiness="not-run",
                reference_profile=(
                    str(row["reference_profile"])
                    if row.get("reference_profile") is not None
                    else None
                ),
            )
        )
    if len({item[0] for item in route_pairs}) != 28 or len({item[1] for item in route_pairs}) != 28:
        raise CatalogError("compiled route matrix is not a complete 28 by 28 grid")
    route_tuple = tuple(routes)
    routes_by_id = MappingProxyType({item.route_id: item for item in route_tuple})
    if len(routes_by_id) != 784:
        raise CatalogError("compiled route IDs must be unique")

    raw_reference = document.get("reference_routes")
    if not isinstance(raw_reference, list) or len(raw_reference) != 40:
        raise CatalogError("compiled catalog must contain exactly 40 reference routes")
    reference_routes: list[RouteCertificationPlan] = []
    for row in raw_reference:
        if not isinstance(row, Mapping) or row.get("readiness") != "not-run":
            raise CatalogError("compiled reference route is invalid or promoted")
        required_skills = tuple(str(item) for item in row.get("required_skills", ()))
        if any(item not in skills_by_name for item in required_skills):
            raise CatalogError("reference route requires an unknown Skill")
        route_id = str(row.get("route_id"))
        reference_routes.append(
            RouteCertificationPlan(
                plan_id=f"plan:{route_id}",
                route_id=route_id,
                source_language=str(row.get("source")),
                target_language=str(row.get("target")),
                required_skills=required_skills,
                required_labs=tuple(str(item) for item in row.get("required_labs", ())),
                target_levels=tuple(str(item) for item in row.get("target_levels", ())),
                status="not-run",
            )
        )
    reference_tuple = tuple(reference_routes)
    reference_by_id = MappingProxyType({item.route_id: item for item in reference_tuple})
    if len(reference_by_id) != 40:
        raise CatalogError("compiled reference route IDs must be unique")

    issues = document.get("source_issues")
    if not isinstance(issues, list) or not any(
        isinstance(item, Mapping) and item.get("id") == "SOURCE-SCHEMA-BATCH-ENUM-A-I"
        for item in issues
    ):
        raise CatalogError("compiled catalog lost the known source schema defect")

    return CompiledCatalog(
        raw=MappingProxyType(dict(document)),
        skills=skills,
        skills_by_name=skills_by_name,
        routes=route_tuple,
        routes_by_id=routes_by_id,
        reference_routes=reference_tuple,
        reference_routes_by_id=reference_by_id,
        digest=digest,
    )


def load_catalog() -> CompiledCatalog:
    document, digest = _read_resource()
    return _parse_catalog(document, digest)
