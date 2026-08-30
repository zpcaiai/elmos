"""Exact catalog, dependency DAG, route, corpus, and lab contract tests."""

from __future__ import annotations

from collections import Counter, deque
import copy
import hashlib
import json
import warnings
import zipfile
from pathlib import Path

import pytest

from tooling import integrate_semantic_assurance_expansion_skills as integration


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = (
    REPOSITORY_ROOT
    / "skills/subskills/elmos-semantic-assurance-expansion-skills-v1.0.0.zip"
)
ARCHIVE_ROOT = "elmos-semantic-assurance-expansion-skills-v1.0.0"
EXPECTED_BATCH_COUNTS = {
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
EXTERNAL_DEPENDENCIES = frozenset(
    {
        "elmos-multi-source-repository-discovery",
        "elmos-embedded-sql-routine-migrator",
    }
)
ROUTE_UNREACHABLE_SKILLS = frozenset(
    {
        "elmos-adversarial-edge-case-corpus",
        "elmos-closure-capture-lambda-semantics",
        "elmos-public-fixture-license-provenance",
        "elmos-state-snapshot-equivalence",
    }
)


@pytest.fixture(scope="module")
def audit() -> integration.ArchiveAudit:
    return integration.validate_archive(ARCHIVE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _topological_count(graph: dict[str, tuple[str, ...]]) -> int:
    """Count nodes in a dependency-first topological traversal."""

    reverse: dict[str, list[str]] = {name: [] for name in graph}
    remaining = {
        name: sum(dependency in graph for dependency in dependencies)
        for name, dependencies in graph.items()
    }
    for name, dependencies in graph.items():
        for dependency in dependencies:
            if dependency in graph:
                reverse[dependency].append(name)
    queue = deque(name for name, count in remaining.items() if count == 0)
    visited = 0
    while queue:
        dependency = queue.popleft()
        visited += 1
        for dependent in reverse[dependency]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                queue.append(dependent)
    return visited


def _dependency_closure(
    graph: dict[str, tuple[str, ...]], seeds: set[str]
) -> set[str]:
    closure: set[str] = set()
    pending = list(seeds)
    while pending:
        name = pending.pop()
        if name in closure or name not in graph:
            continue
        closure.add(name)
        pending.extend(graph[name])
    return closure


def _cyclic_archive(destination: Path) -> Path:
    """Create a checksum-consistent 337-member ZIP with a real two-node cycle."""

    manifest_path = f"{ARCHIVE_ROOT}/manifest.json"
    file_manifest_path = (
        f"{ARCHIVE_ROOT}/dist-manifests/package-file-manifest.json"
    )
    with zipfile.ZipFile(ARCHIVE) as source:
        infos = source.infolist()
        payloads = {
            info.filename: (b"" if info.is_dir() else source.read(info))
            for info in infos
        }

    manifest = integration.strict_json_loads(
        payloads[manifest_path], label="manifest.json"
    )
    left = manifest["skills"][2]
    right = manifest["skills"][3]
    assert len(left["dependencies"]) == len(right["dependencies"]) == 1
    left_old_dependency = left["dependencies"][0]
    left["dependencies"] = [right["name"]]
    assert right["dependencies"] == [left["name"]]
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    payloads[manifest_path] = manifest_bytes

    changed_files = {"manifest.json": manifest_bytes}
    for skill, old_dependency, new_dependency in (
        (left, left_old_dependency, right["name"]),
    ):
        archive_path = f"{ARCHIVE_ROOT}/{skill['path']}"
        old = f'  - "{old_dependency}"'.encode()
        new = f'  - "{new_dependency}"'.encode()
        updated = payloads[archive_path].replace(old, new, 1)
        assert updated != payloads[archive_path]
        payloads[archive_path] = updated
        changed_files[skill["path"]] = updated

    file_manifest = integration.strict_json_loads(
        payloads[file_manifest_path], label="package-file-manifest.json"
    )
    records = {record["path"]: record for record in file_manifest["files"]}
    for relative, changed in changed_files.items():
        records[relative]["size"] = len(changed)
        records[relative]["sha256"] = _sha256(changed)
    payloads[file_manifest_path] = (
        json.dumps(file_manifest, indent=2) + "\n"
    ).encode()

    with zipfile.ZipFile(destination, "w") as target:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            for original in infos:
                target.writestr(copy.copy(original), payloads[original.filename])
    return destination


def test_manifest_has_exact_132_skills_batches_ids_outputs_and_states(
    audit: integration.ArchiveAudit,
) -> None:
    manifest = audit.manifest
    skills = manifest["skills"]
    assert len(skills) == 132
    assert Counter(skill["batch"] for skill in skills) == Counter(
        EXPECTED_BATCH_COUNTS
    )
    assert [skill["id"] for skill in skills] == [
        f"ELMOS-POLY-{number}" for number in range(169, 301)
    ]
    assert len({skill["name"] for skill in skills}) == 132
    assert {skill["risk"] for skill in skills} == {"critical"}
    assert {skill["readiness"] for skill in skills} == {"not-run"}

    outputs = [output for skill in skills for output in skill["outputs"]]
    assert len(outputs) == 396
    assert len(set(outputs)) == 396
    assert Counter(len(skill["outputs"]) for skill in skills) == Counter({3: 132})


def test_real_manifest_dependency_graph_has_229_edges_and_is_acyclic(
    audit: integration.ArchiveAudit,
) -> None:
    skills = audit.manifest["skills"]
    names = {skill["name"] for skill in skills}
    graph = {
        skill["name"]: tuple(skill["dependencies"]) for skill in skills
    }
    all_edges = [
        (name, dependency)
        for name, dependencies in graph.items()
        for dependency in dependencies
    ]
    internal = [edge for edge in all_edges if edge[1] in names]
    external = [edge for edge in all_edges if edge[1] not in names]

    assert len(all_edges) == 229
    assert len(internal) == 227
    assert len(external) == 2
    assert {dependency for _name, dependency in external} == EXTERNAL_DEPENDENCIES
    assert _topological_count(graph) == 132

    assert len(audit.internal_edges) == 227
    assert set(audit.internal_edges) == {
        (dependency, dependent) for dependent, dependency in internal
    }
    assert audit.external_dependencies == tuple(sorted(EXTERNAL_DEPENDENCIES))


def test_checksum_consistent_manifest_cycle_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attack = _cyclic_archive(tmp_path / "cyclic.zip")
    payload = attack.read_bytes()
    with zipfile.ZipFile(attack) as source:
        mutated_manifest_digest = _sha256(
            source.read(f"{ARCHIVE_ROOT}/manifest.json")
        )
    monkeypatch.setattr(
        integration,
        "EXPECTED_SOURCE_MANIFEST_SHA256",
        mutated_manifest_digest,
    )
    with pytest.raises(integration.IntegrationError, match="cycle|acyclic"):
        integration.validate_archive(
            attack,
            expected_digest=_sha256(payload),
            expected_bytes=len(payload),
            limits=integration.ArchiveLimits(
                expected_uncompressed_bytes=None,
                expected_compressed_member_bytes=None,
            ),
        )


def test_all_40_route_profiles_are_explicit_missing_blockers(
    audit: integration.ArchiveAudit,
) -> None:
    routes = audit.routes
    assert len(routes) == 40
    assert len({route["route"] for route in routes}) == 40
    assert {route["readiness"] for route in routes} == {"not-run"}
    assert {
        tuple(route["targetLevels"]) for route in routes
    } == {("E0", "E1", "E2", "E3", "E4", "E5")}

    with zipfile.ZipFile(ARCHIVE) as source:
        relative_files = {
            info.filename[len(f"{ARCHIVE_ROOT}/") :]
            for info in source.infolist()
            if not info.is_dir()
        }
    missing = {
        route["route"]: route["referenceProfile"]
        for route in routes
        if route["referenceProfile"] not in relative_files
    }
    assert len(missing) == 40
    assert missing == {
        route["route"]: f"route-profiles/{route['route']}.yaml" for route in routes
    }

    blockers = audit.blockers
    profile_blockers = [
        blocker
        for blocker in blockers
        if "route-profiles/" in json.dumps(blocker, sort_keys=True)
    ]
    assert len(profile_blockers) == 40


def test_empty_labs_and_corpora_remain_not_run_and_never_certify(
    audit: integration.ArchiveAudit,
) -> None:
    labs = audit.labs
    corpora = audit.corpora
    assert len(labs) == 9
    assert {lab["readiness"] for lab in labs} == {"not-run"}
    assert {tuple(lab["profiles"]) for lab in labs} == {()}

    assert len(corpora) == 40
    assert {route["status"] for route in corpora} == {"not-run"}
    assert {tuple(route["fixtures"]) for route in corpora} == {()}
    assert {
        (
            dimension,
            metric["numerator"],
            metric["denominator"],
        )
        for route in corpora
        for dimension, metric in route["coverage"].items()
    } == {
        ("syntax", 0, 1),
        ("semantic", 0, 1),
        ("regression", 0, 1),
    }

    serialized = json.dumps(
        {"routes": audit.routes, "labs": labs, "corpora": corpora},
        sort_keys=True,
    )
    assert "not-run" in serialized


def test_route_dependency_closure_exposes_four_unreferenced_skills(
    audit: integration.ArchiveAudit,
) -> None:
    graph = {
        skill["name"]: tuple(skill["dependencies"])
        for skill in audit.manifest["skills"]
    }
    direct = {
        skill
        for route in audit.routes
        for skill in route["requiredSemanticSkills"]
    }
    closure = _dependency_closure(graph, direct)
    assert len(direct) == 16
    assert len(closure) == 128
    assert set(graph) - closure == ROUTE_UNREACHABLE_SKILLS
