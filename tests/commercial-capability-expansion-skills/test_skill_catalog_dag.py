"""Exact catalog and honest source/repository dependency-graph tests."""

from __future__ import annotations

from collections import Counter, defaultdict, deque

import pytest

from tooling import integrate_commercial_capability_expansion_skills as importer


@pytest.fixture(scope="module")
def package():
    return importer.validate_package(
        importer.read_pinned_archive(importer.resolve_archive())
    )


def test_manifest_has_85_exact_names_and_eight_exact_kernel_counts(package):
    skills = package.source_skills
    assert tuple(skill["id"] for skill in skills) == importer.EXPECTED_SKILL_NAMES
    assert len(skills) == 85
    by_kernel: dict[str, list[str]] = defaultdict(list)
    for skill in skills:
        by_kernel[skill["kernel"]].append(skill["id"])
    assert {
        kernel: tuple(names) for kernel, names in by_kernel.items()
    } == importer.EXPECTED_SKILLS_BY_KERNEL
    assert Counter(skill["priority"] for skill in skills) == Counter(
        {"P0": 68, "P1": 17}
    )


def test_source_manifest_explicitly_has_no_dependency_or_dag_semantics(package):
    manifest = package.manifest
    assert not set(manifest).intersection(importer.SOURCE_DEPENDENCY_FIELDS)
    for skill in manifest["skills"]:
        assert not set(skill).intersection(importer.SOURCE_DEPENDENCY_FIELDS)
    catalog = importer._build_catalog(
        package, importer._build_wrapper_trees(package)
    )
    source_graph = catalog["source_graph"]
    assert source_graph["origin"] == "SOURCE_MANIFEST_INVENTORY_ONLY"
    assert source_graph["node_count"] == 85
    assert source_graph["edge_count"] == 0
    assert source_graph["edges"] == []
    assert source_graph["source_dependency_gap"] is True
    assert source_graph["source_owned_dag_claimed"] is False


def test_repository_owned_lifecycle_graph_is_acyclic_and_fully_labeled(package):
    graph = package.repository_graph
    assert graph["origin"] == "REPOSITORY_OWNED_NORMALIZATION"
    assert graph["source_dependency_gap"] is True
    assert graph["source_owned_dag_claimed"] is False
    assert graph["node_count"] == 85
    assert set(graph["nodes"]) == set(importer.EXPECTED_SKILL_NAMES)
    assert graph["edge_count"] == len(graph["edges"])
    assert graph["acyclic"] is True
    assert len(graph["topological_order"]) == 85
    assert set(graph["topological_order"]) == set(graph["nodes"])
    assert all(
        edge["origin"] == "REPOSITORY_OWNED_NORMALIZATION"
        and edge["reason"]
        for edge in graph["edges"]
    )

    indegree = {node: 0 for node in graph["nodes"]}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in graph["edges"]:
        indegree[edge["to"]] += 1
        outgoing[edge["from"]].append(edge["to"])
    queue = deque(node for node in graph["nodes"] if indegree[node] == 0)
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for target in outgoing[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    assert visited == 85


def test_repository_graph_encodes_only_documented_anchor_lifecycle(package):
    graph = package.repository_graph
    edges = {(edge["from"], edge["to"]) for edge in graph["edges"]}
    required_path = [
        "policy-as-code-kernel",
        "universal-agent-skill-runtime",
        "repository-semantic-code-graph",
        "change-risk-classifier",
        "multi-engine-rewrite-router",
        "hermetic-build-environment",
        "differential-runtime-verification",
        "evidence-gate-orchestrator",
        "slsa-in-toto-provenance",
        "otel-agent-execution-tracing",
        "trajectory-dataset-versioning",
    ]
    assert all(pair in edges for pair in zip(required_path, required_path[1:]))
    assert (
        "fine-grained-authorization-engine",
        "universal-agent-skill-runtime",
    ) in edges
    assert (
        "prompt-injection-tool-boundary",
        "universal-agent-skill-runtime",
    ) in edges
    for producer in (
        "continuous-fuzz-certification",
        "contract-compatibility-verification",
        "static-dataflow-assurance",
    ):
        assert ("hermetic-build-environment", producer) in edges
        assert (producer, "evidence-gate-orchestrator") in edges


def test_non_anchor_skills_have_only_their_kernel_normalization_anchor(package):
    dependencies = package.repository_graph["dependencies_by_skill"]
    for skill in package.source_skills:
        if skill["id"] in importer.LIFECYCLE_ANCHORS:
            continue
        assert dependencies[skill["id"]] == [
            importer.KERNEL_PRIMARY_ANCHOR[skill["kernel"]]
        ]


def test_compiled_contract_dependencies_match_repository_graph_not_source(package):
    trees = importer._build_wrapper_trees(package)
    for skill in package.source_skills:
        contract = importer.load_json(
            trees[skill["id"]]["compiled-contract.json"].content,
            skill["id"],
        )
        assert contract["skill"]["dependencies"] == package.repository_graph[
            "dependencies_by_skill"
        ][skill["id"]]
        assert (
            contract["skill"]["dependency_origin"]
            == "REPOSITORY_OWNED_NORMALIZATION"
        )
        assert contract["skill"]["source_dependency_gap"] is True
        assert contract["source"]["source_dependency_declarations_present"] is False


def test_master_is_guidance_only_and_generated_contracts_hide_private_registry(package):
    trees = importer._build_wrapper_trees(package)
    master = importer.load_json(
        trees[importer.MASTER_SKILL_NAME]["compiled-contract.json"].content,
        "master compiled contract",
    )
    assert master["runtime"]["binding_mode"] == "GUIDANCE_ONLY_NOT_EXECUTABLE"
    assert master["runtime"]["entrypoint"] is None
    assert master["status"]["implementation"] == "GUIDANCE_ONLY_NOT_EXECUTABLE"

    for tree in trees.values():
        generated = b"\n".join(payload.content for payload in tree.values())
        assert b"EXACT_SKILL_HANDLERS" not in generated
        assert b"_exact_registry" not in generated
        assert b'"registry_key"' not in generated
