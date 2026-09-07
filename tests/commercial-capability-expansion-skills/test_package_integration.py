"""End-to-end bindings for the production-safe package importer."""

from __future__ import annotations

from importlib import import_module
from inspect import signature
import json
from pathlib import Path
import sys

import pytest

from tooling import integrate_commercial_capability_expansion_skills as importer


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/commercial-capability-expansion-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

CommercialCapabilityExpansionService = import_module(
    "elmos_commercial_expansion"
).CommercialCapabilityExpansionService
CommercialCapabilityRuntime = import_module(
    "elmos_commercial_expansion.runtime"
).CommercialCapabilityRuntime


SOURCE_ROOT = ROOT / importer.SOURCE_RELATIVE
CATALOG_PATH = ROOT / importer.CATALOG_RELATIVE
RECEIPT_PATH = ROOT / importer.RECEIPT_RELATIVE
WORKSPACE_ROOT = ROOT / importer.WORKSPACE_SKILLS_RELATIVE
RUNTIME_ROOT = ROOT / importer.RUNTIME_SKILLS_RELATIVE


@pytest.fixture(scope="module")
def compiled():
    archive = importer.resolve_archive()
    snapshot = importer.read_pinned_archive(archive)
    package = importer.validate_package(snapshot)
    projection = importer.compile_projection(
        package,
        archive_path=archive,
        source_path=SOURCE_ROOT,
        catalog_path=CATALOG_PATH,
        receipt_path=RECEIPT_PATH,
        workspace_root=WORKSPACE_ROOT,
        runtime_root=RUNTIME_ROOT,
    )
    return archive, package, projection


def test_archive_identity_and_complete_prevalidation(compiled):
    archive, package, _ = compiled
    assert archive.is_file()
    assert package.snapshot.archive_sha256 == importer.EXPECTED_ARCHIVE_SHA256
    assert package.snapshot.archive_bytes == importer.EXPECTED_ARCHIVE_BYTES
    assert package.snapshot.member_count == importer.EXPECTED_MEMBER_COUNT == 105
    assert (
        package.snapshot.uncompressed_bytes
        == importer.EXPECTED_UNCOMPRESSED_BYTES
        == 294_029
    )
    assert len(package.source_skills) == importer.EXPECTED_SKILL_COUNT == 85


def test_immutable_extraction_is_exact_archive_byte_projection(compiled):
    _, package, _ = compiled
    importer._assert_tree_bytes(
        SOURCE_ROOT, package.snapshot.files, "test immutable extraction"
    )
    assert importer._tree_digest(
        importer._read_regular_tree(SOURCE_ROOT, [package.snapshot.files])
    ) == importer._tree_digest(package.snapshot.files)


def test_repository_compiled_catalog_is_exact(compiled):
    _, _, projection = compiled
    assert CATALOG_PATH.read_bytes() == projection.catalog_bytes
    catalog = json.loads(projection.catalog_bytes)
    assert catalog["origin"] == "REPOSITORY_OWNED_COMPILED"
    assert catalog["skill_count"] == 85
    assert catalog["kernel_counts"] == importer.EXPECTED_KERNEL_COUNTS
    assert catalog["source_graph"]["node_count"] == 85
    assert catalog["source_graph"]["edge_count"] == 0
    assert catalog["source_graph"]["source_dependency_gap"] is True
    assert catalog["source_graph"]["source_owned_dag_claimed"] is False


def test_master_and_85_wrappers_are_repository_owned_and_dual_root_exact(compiled):
    _, package, projection = compiled
    assert len(projection.wrapper_trees) == 86
    source_by_name = {skill["id"]: skill["path"] for skill in package.source_skills}
    for name, expected_tree in projection.wrapper_trees.items():
        assert set(expected_tree) == {
            "SKILL.md",
            "compiled-contract.json",
            "agents/openai.yaml",
        }
        importer._assert_tree_bytes(
            WORKSPACE_ROOT / name, expected_tree, f"workspace {name}"
        )
        importer._assert_tree_bytes(
            RUNTIME_ROOT / name, expected_tree, f"runtime {name}"
        )
        assert (WORKSPACE_ROOT / name / "SKILL.md").read_bytes() == (
            RUNTIME_ROOT / name / "SKILL.md"
        ).read_bytes()
        source_member = (
            "SKILL.md" if name == importer.MASTER_SKILL_NAME else source_by_name[name]
        )
        assert expected_tree["SKILL.md"].content != package.snapshot.files[
            source_member
        ].content


def test_every_compiled_contract_has_exact_runtime_and_fail_closed_state(compiled):
    _, _, projection = compiled
    for name, tree in projection.wrapper_trees.items():
        contract = json.loads(tree["compiled-contract.json"].content)
        runtime = contract["runtime"]
        assert contract["source"]["source_content_executed"] is False
        assert contract["source"]["source_instructions_installed"] is False
        assert contract["skill"]["source_dependency_gap"] is True
        assert contract["status"]["external_runtime_evidence"] == "NOT_RUN"
        assert contract["status"]["certification"] == "NOT_CERTIFIED"
        if name == importer.MASTER_SKILL_NAME:
            assert runtime["module"] is None
            assert runtime["service"] is None
            assert runtime["entrypoint"] is None
            assert runtime["preparation_module"] is None
            assert runtime["preparation_entrypoint"] is None
            assert runtime["input_contract_catalog_entrypoint"] is None
            assert runtime["input_contract_policy"] is None
            assert runtime["authentication_required"] is None
            assert runtime["scope_fields"] == []
            assert runtime["preparation_fields"] == []
            assert runtime["execute_fields"] == []
            assert runtime["binding_mode"] == "GUIDANCE_ONLY_NOT_EXECUTABLE"
            assert runtime["orchestrates_exact_skill_count"] == 85
            assert contract["status"]["implementation"] == (
                "GUIDANCE_ONLY_NOT_EXECUTABLE"
            )
        else:
            assert runtime["module"] == "elmos_commercial_expansion"
            assert runtime["service"] == "CommercialCapabilityExpansionService"
            assert runtime["entrypoint"] == (
                "CommercialCapabilityExpansionService.execute"
            )
            assert runtime["preparation_module"] == (
                "elmos_commercial_expansion.runtime"
            )
            assert runtime["preparation_entrypoint"] == (
                "CommercialCapabilityRuntime.prepare_invocation"
            )
            assert runtime["input_contract_catalog_entrypoint"] == (
                "list_capability_kernels"
            )
            assert runtime["input_contract_policy"] == (
                "EXACT_REQUIRED_OPTIONAL_FAIL_CLOSED"
            )
            assert runtime["authentication_required"] is True
            assert runtime["scope_fields"] == [
                "tenant_id",
                "project_id",
                "actor_id",
                "revision",
                "environment_id",
            ]
            assert runtime["preparation_fields"] == [
                "scope",
                "skill_id",
                "action",
                "inputs",
                "idempotency_key",
                "ttl",
            ]
            assert runtime["execute_fields"] == [
                "invocation",
                "inputs",
                "decision",
                "lease",
                "authority_proof",
            ]
            assert runtime["binding_mode"] == "AUTHENTICATED_EXACT_EXECUTION"
            assert contract["status"]["implementation"] == (
                "RUNTIME_BOUND_NOT_EXECUTED"
            )


def test_generated_wrappers_use_only_public_execution_surface(compiled):
    _, _, projection = compiled
    assert callable(CommercialCapabilityExpansionService.execute)
    assert callable(CommercialCapabilityRuntime.prepare_invocation)
    assert list(signature(CommercialCapabilityRuntime.prepare_invocation).parameters) == [
        "self",
        "scope",
        "skill_id",
        "action",
        "inputs",
        "idempotency_key",
        "ttl",
    ]
    assert list(signature(CommercialCapabilityExpansionService.execute).parameters) == [
        "self",
        "invocation",
        "inputs",
        "decision",
        "lease",
        "authority_proof",
    ]
    for tree in projection.wrapper_trees.values():
        generated = b"\n".join(payload.content for payload in tree.values())
        assert b"list_capability_kernels" in generated
        assert b"EXACT_SKILL_HANDLERS" not in generated
        assert b"_exact_registry" not in generated
        assert b'"registry_key"' not in generated


def test_exact_previous_repository_projection_has_one_fail_closed_upgrade_path(
    compiled, tmp_path
):
    _, package, projection = compiled
    name = "cost-latency-quality-optimizer"
    expected = projection.wrapper_trees[name]
    previous = importer._previous_managed_wrapper_tree(expected)
    destination = tmp_path / name
    for relative, payload in previous.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload.content)
    assert importer._classify_wrapper_destination(
        destination,
        expected,
        importer._legacy_wrapper_tree(package, name),
    ) == "MIGRATE_REPOSITORY_V2_INPUT_CONTRACT_DISCOVERY"

    (destination / "SKILL.md").write_bytes(previous["SKILL.md"].content + b"tamper")
    with pytest.raises(importer.IntegrationError, match="drift|foreign"):
        importer._classify_wrapper_destination(
            destination,
            expected,
            importer._legacy_wrapper_tree(package, name),
        )


def test_receipt_binds_archive_extraction_catalog_and_wrapper_tree(compiled):
    _, package, projection = compiled
    receipt = json.loads(RECEIPT_PATH.read_bytes())
    assert receipt == projection.receipt
    assert receipt["source_archive"]["sha256"] == importer.EXPECTED_ARCHIVE_SHA256
    assert receipt["immutable_extraction"]["tree_sha256"] == importer._tree_digest(
        package.snapshot.files
    )
    assert receipt["compiled_catalog"]["sha256"] == importer.sha256_bytes(
        projection.catalog_bytes
    )
    assert receipt["installed_wrappers"]["tree_sha256"] == importer._tree_digest(
        importer._aggregate_wrapper_payloads(projection.wrapper_trees)
    )
    assert receipt["evidence"]["external_runtime"] == "NOT_RUN"
    assert receipt["evidence"]["independent_verification"] == "NOT_RUN"
    assert receipt["evidence"]["certification"] == "NOT_CERTIFIED"
    assert receipt["security"]["source_executables_treated_as_inert_data"] is True


def test_check_mode_replays_every_binding_without_writes(compiled):
    _, package, projection = compiled
    watched = [
        CATALOG_PATH,
        RECEIPT_PATH,
        SOURCE_ROOT / "manifest.json",
        WORKSPACE_ROOT / importer.MASTER_SKILL_NAME / "SKILL.md",
        RUNTIME_ROOT / importer.EXPECTED_SKILL_NAMES[-1] / "compiled-contract.json",
    ]
    before = {
        path: (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
        for path in watched
    }
    assert importer.main(["--check"]) == 0
    after = {
        path: (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
        for path in watched
    }
    assert after == before
    importer.check_projection(
        package,
        projection,
        trusted_root=ROOT,
        source_path=SOURCE_ROOT,
        catalog_path=CATALOG_PATH,
        receipt_path=RECEIPT_PATH,
        workspace_root=WORKSPACE_ROOT,
        runtime_root=RUNTIME_ROOT,
    )
