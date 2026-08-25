from __future__ import annotations

import importlib.util
import io
import json
import shutil
import stat
import sys
import zipfile
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = REPOSITORY_ROOT / "tooling/integrate_multimodal_intake_skills.py"
SPEC = importlib.util.spec_from_file_location(
    "integrate_multimodal_intake_skills", IMPORTER_PATH
)
assert SPEC is not None and SPEC.loader is not None
importer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = importer
SPEC.loader.exec_module(importer)


def _real_archive() -> Path:
    return REPOSITORY_ROOT / importer.ARCHIVE_RELATIVE_PATH


def _real_schema_members() -> dict[str, bytes]:
    with zipfile.ZipFile(_real_archive(), "r") as archive:
        return {
            name: archive.read(
                f"{importer.ARCHIVE_ROOT}/schemas/{name}"
            )
            for name in importer.EXPECTED_SCHEMA_NAMES
        }


class _CentralDirectoryFixture:
    def __init__(self, infos: list[zipfile.ZipInfo]) -> None:
        self._infos = infos

    def infolist(self) -> list[zipfile.ZipInfo]:
        return list(self._infos)


def _regular_zip_info(
    relative: str,
    *,
    mode: int = 0o644,
    file_size: int = 0,
    compress_size: int = 0,
    flag_bits: int = 0,
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(f"{importer.ARCHIVE_ROOT}/{relative}")
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.compress_type = zipfile.ZIP_STORED
    info.file_size = file_size
    info.compress_size = compress_size
    info.flag_bits = flag_bits
    info.CRC = 0
    return info


def _synthetic_runtime(snapshot: importer.PackageSnapshot) -> str:
    imports_by_module: dict[str, list[str]] = {}
    for operation, module in importer.EXPECTED_OPERATION_IMPORTS.items():
        imports_by_module.setdefault(module, []).append(operation)
    operation_imports = "\n".join(
        f"from .{module} import {', '.join(sorted(operations))}"
        for module, operations in sorted(imports_by_module.items())
    )
    function_blocks: list[str] = []
    for skill in snapshot.skills:
        dispatcher, operation = importer.EXPECTED_HANDLER_CALLS[skill.ordinal - 1]
        arguments = (
            f'"{skill.name}", request'
            if operation is None
            else f'"{skill.name}", {operation}, request'
        )
        function_blocks.append(
            f"def {skill.handler_id}(request):\n    return {dispatcher}({arguments})"
        )
    functions = "\n\n".join(function_blocks)
    registry = "\n".join(
        f'    "{skill.name}": _entry({skill.ordinal}, "{skill.name}", '
        f'"{importer.EXPECTED_HANDLER_PHASES[skill.ordinal - 1]}", {skill.handler_id}),' 
        for skill in snapshot.skills
    )
    return f'''"""Synthetic static registry used only by importer integration tests."""

from dataclasses import dataclass

{operation_imports}


class SkillHandler:
    pass


@dataclass(frozen=True)
class HandlerBinding:
    ordinal: int
    skill: str
    handler_id: str
    phase: str
    handler: SkillHandler


def _entry(ordinal, skill, phase, handler):
    return HandlerBinding(ordinal, skill, getattr(handler, "__name__"), phase, handler)


def _run_bridge(skill, request):
    return request


def _run_domain(skill, operation, request):
    return request


def _run_domain_or_bridge(skill, operation, request):
    return request

{functions}

SKILL_REGISTRY = {{
{registry}
}}
'''


def _prepare_repository(tmp_path: Path) -> tuple[Path, importer.PackageSnapshot]:
    snapshot = importer.validate_archive(_real_archive())
    archive = tmp_path / importer.ARCHIVE_RELATIVE_PATH
    archive.parent.mkdir(parents=True)
    shutil.copyfile(_real_archive(), archive)

    matrix = tmp_path / importer.MATRIX_RELATIVE_PATH
    matrix.parent.mkdir(parents=True)
    shutil.copyfile(REPOSITORY_ROOT / importer.MATRIX_RELATIVE_PATH, matrix)

    engine_root = tmp_path / importer.ENGINE_ROOT_RELATIVE_PATH
    for relative in (*importer.ENGINE_IMPLEMENTATION_FILES, *importer.ENGINE_TEST_FILES):
        runtime_file = engine_root / relative
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_text("synthetic runtime fixture\n", encoding="utf-8")
    markers_by_file: dict[str, list[str]] = {}
    for marker_map in (
        importer.HUMAN_REVIEW_RUNTIME_CONTRACT_MARKERS,
        importer.GOVERNANCE_DELETION_RUNTIME_CONTRACT_MARKERS,
        importer.SKILL26_OPERATION_REGISTRY_MARKERS,
        importer.PROJECT_PACKAGE_LIFECYCLE_MARKERS,
        importer.ACCEPTANCE_EVALUATION_RUNTIME_CONTRACT_MARKERS,
        importer.CONTENT_PROJECTION_RUNTIME_CONTRACT_MARKERS,
        importer.TELEMETRY_LIFECYCLE_RUNTIME_CONTRACT_MARKERS,
        importer.DOWNSTREAM_AGENT_RUNTIME_CONTRACT_MARKERS,
        importer.PROCESSING_JOB_CANCELLATION_RUNTIME_CONTRACT_MARKERS,
        importer.CORE_OUTBOX_DELIVERY_RECEIPT_RUNTIME_CONTRACT_MARKERS,
        importer.OPERATION_INPUT_SCHEMA_RUNTIME_CONTRACT_MARKERS,
        importer.SDK_COMPILATION_TOOL_RUNTIME_CONTRACT_MARKERS,
    ):
        for relative, markers in marker_map.items():
            markers_by_file.setdefault(relative, []).extend(markers)
    for relative, markers in markers_by_file.items():
        runtime_file = engine_root / relative
        runtime_file.write_text(
            "synthetic runtime fixture\n"
            + "\n".join(dict.fromkeys(markers))
            + "\n",
            encoding="utf-8",
        )
    for source_relative, packaged_relative in importer.PACKAGED_MIGRATION_PAIRS:
        (engine_root / packaged_relative).write_bytes(
            (engine_root / source_relative).read_bytes()
        )
    for source_relative, packaged_relative in importer.PACKAGED_RUNTIME_FILE_PAIRS:
        source_payload = (
            REPOSITORY_ROOT
            / importer.ENGINE_ROOT_RELATIVE_PATH
            / source_relative
        ).read_bytes()
        (engine_root / source_relative).write_bytes(source_payload)
        (engine_root / packaged_relative).write_bytes(source_payload)
    operation_registry = engine_root / "src/elmos_multimodal_intake/operation_registry.py"
    operation_registry.write_bytes(
        (REPOSITORY_ROOT / importer.OPERATION_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    for relative in (*importer.SURFACE_IMPLEMENTATION_FILES, *importer.REPOSITORY_TEST_FILES):
        runtime_file = tmp_path / relative
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_text("synthetic surface fixture\n", encoding="utf-8")
    engine = tmp_path / importer.ENGINE_RELATIVE_PATH
    engine.write_text(_synthetic_runtime(snapshot), encoding="utf-8")
    return archive, snapshot


def test_pinned_archive_contract_inventory_is_exact() -> None:
    snapshot = importer.validate_archive(_real_archive())

    assert snapshot.archive_sha256 == importer.ARCHIVE_SHA256
    assert _real_archive().stat().st_size == importer.EXPECTED_ARCHIVE_BYTES == 664_179
    assert snapshot.entry_count == 346
    assert snapshot.uncompressed_bytes == 1_117_974
    assert snapshot.internal_checksum_count == 345
    assert len(snapshot.skills) == 50
    assert sum(len(skill.acceptance_ids) for skill in snapshot.skills) == 240
    assert sum(len(skill.deliverables) for skill in snapshot.skills) == 170
    assert snapshot.global_gate_ids == tuple(f"G-{value:02d}" for value in range(1, 9))
    assert snapshot.dependency_sccs == tuple(sorted(importer.EXPECTED_CYCLIC_SCCS))


def test_constrained_contract_parser_supports_only_yaml_folded_continuations() -> None:
    contract = b"""schema_version: 1.0.0
ordinal: 1
name: elmos-example
title: Example
objective: first segment
  second segment
dependencies:
- dependency first
  dependency second
inputs: []
outputs: []
responsibilities: []
deliverables: []
acceptance: []
data_entities: []
events: []
metrics: []
failure_modes: []
cross_cutting_invariants: []
"""

    parsed = importer._parse_contract(contract, "folded-contract.yaml")

    assert parsed["objective"] == "first segment second segment"
    assert parsed["dependencies"] == ["dependency first dependency second"]

    with pytest.raises(importer.IntegrationError, match="unsupported YAML structure"):
        importer._parse_contract(
            contract.replace(b"  second segment", b"    ambiguous indentation"),
            "ambiguous-contract.yaml",
        )


def test_static_metadata_parsers_reject_duplicate_keys_and_non_finite_json() -> None:
    with pytest.raises(importer.IntegrationError, match="duplicate frontmatter key"):
        importer._parse_frontmatter(
            b"---\nname: elmos-example\nname: elmos-shadow\ndescription: example\n---\n",
            "SKILL.md",
        )
    with pytest.raises(importer.IntegrationError, match="duplicate JSON key"):
        importer._strict_json_bytes(b'{"name":"first","name":"second"}', "manifest.json")
    with pytest.raises(importer.IntegrationError, match="non-finite JSON"):
        importer._strict_json_bytes(b'{"value":NaN}', "manifest.json")
    with pytest.raises(importer.IntegrationError, match="invalid JSON Unicode"):
        importer._strict_json_bytes(b'{"value":"\\ud800"}', "manifest.json")
    deeply_nested = ("[" * 70 + "0" + "]" * 70).encode("ascii")
    with pytest.raises(importer.IntegrationError, match="too complex"):
        importer._strict_json_bytes(deeply_nested, "manifest.json")


def test_package_schema_inventory_and_local_reference_closure_are_exact() -> None:
    identifiers = importer._validate_package_schemas(_real_schema_members())

    assert len(identifiers) == importer.EXPECTED_SCHEMA_COUNT == 9
    assert len(set(identifiers)) == len(identifiers)
    assert identifiers == tuple(
        f"https://elmos.local/schemas/{name}"
        for name in importer.EXPECTED_SCHEMA_NAMES
    )


def test_package_schema_inventory_rejects_missing_and_extra_files() -> None:
    schemas = _real_schema_members()
    schemas.pop(importer.EXPECTED_SCHEMA_NAMES[0])
    schemas["undeclared.schema.json"] = b"{}"

    with pytest.raises(importer.IntegrationError, match="Schema inventory drift"):
        importer._validate_package_schemas(schemas)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"$schema": "https://json-schema.org/draft/2019-09/schema"}, "identity"),
        ({"$id": "https://elmos.local/schemas/shadow.schema.json"}, "identity"),
        ({"$ref": "https://example.invalid/external.schema.json"}, "non-local"),
        ({"$ref": "#/$defs/not-present"}, "unresolved local"),
        ({"$ref": "#/$defs/~2invalid"}, "invalid JSON Pointer escape"),
    ],
)
def test_package_schemas_reject_identity_and_reference_drift(
    mutation: dict[str, str],
    error: str,
) -> None:
    schemas = _real_schema_members()
    name = "archive-inspection.schema.json"
    document = json.loads(schemas[name])
    document.update(mutation)
    schemas[name] = json.dumps(document, separators=(",", ":")).encode("utf-8")

    with pytest.raises(importer.IntegrationError, match=error):
        importer._validate_package_schemas(schemas)


def test_package_schemas_reject_duplicate_json_keys() -> None:
    schemas = _real_schema_members()
    name = "archive-inspection.schema.json"
    schemas[name] = b'{"$schema":"first","$schema":"second"}'

    with pytest.raises(importer.IntegrationError, match="duplicate JSON key"):
        importer._validate_package_schemas(schemas)


def test_checked_in_implementation_matrix_matches_contracts() -> None:
    snapshot = importer.validate_archive(_real_archive())
    importer._validate_matrix(REPOSITORY_ROOT, snapshot)


def test_write_then_check_is_idempotent_and_never_certifies(tmp_path: Path) -> None:
    archive, snapshot = _prepare_repository(tmp_path)

    written = importer.write_integration(tmp_path, archive)
    checked = importer.check_integration(tmp_path, archive)

    assert written.archive_sha256 == checked.archive_sha256 == snapshot.archive_sha256
    compiled = importer._load_json(
        tmp_path / importer.COMPILED_MANIFEST_RELATIVE_PATH, "compiled manifest"
    )
    installed = importer._load_json(
        tmp_path / importer.INSTALLED_MANIFEST_RELATIVE_PATH, "installed manifest"
    )
    for manifest in (compiled, installed):
        assert manifest["external_evidence_status"] == "NOT_RUN"
        assert manifest["certification_status"] == "NOT_CERTIFIED"
    assert compiled["engine"]["handler_count"] == 50
    assert len(compiled["skills"]) == 50
    assert compiled["runtime"]["root"] == "."
    assert compiled["compiler"] == {
        "path": importer.IMPORTER_RELATIVE_PATH.as_posix(),
        "sha256": importer._running_importer_sha256(),
    }
    assert compiled["operation_registry"] == {
        "path": importer.OPERATION_REGISTRY_RELATIVE_PATH.as_posix(),
        "source_sha256": importer._digest_file(
            tmp_path / importer.OPERATION_REGISTRY_RELATIVE_PATH
        ),
        "schema_version": importer.EXPECTED_OPERATION_REGISTRY_SCHEMA,
        "skill_count": importer.EXPECTED_SKILL_COUNT,
        "skills": sorted(skill.name for skill in snapshot.skills),
        "operation_count": importer.EXPECTED_OPERATION_COUNT,
        "document_sha256": importer.EXPECTED_OPERATION_REGISTRY_DIGEST,
        "static_ast_validated": True,
    }
    implementation_paths = {
        item["path"] for item in compiled["runtime"]["implementation"]["files"]
    }
    test_paths = {item["path"] for item in compiled["runtime"]["tests"]["files"]}
    assert set(importer.SURFACE_IMPLEMENTATION_FILES).issubset(implementation_paths)
    assert set(importer.REPOSITORY_TEST_FILES).issubset(test_paths)
    assert [item["phase"] for item in compiled["skills"]] == list(
        importer.EXPECTED_HANDLER_PHASES
    )
    installed_skill = (
        tmp_path
        / importer.INSTALL_ROOTS[0]
        / snapshot.skills[0].name
    )
    compiled_contract = importer._load_json(
        installed_skill / "compiled-contract.json",
        "compiled Skill contract",
    )
    assert compiled_contract["provenance"]["archive_scripts_executed"] is False
    assert (
        compiled_contract["provenance"]["compiler_sha256"]
        == compiled["compiler"]["sha256"]
    )
    assert compiled_contract["provenance"]["mirrors_verified_byte_identical"] == [
        "skills",
        ".agents/skills",
        ".claude/skills",
    ]
    assert compiled_contract["external_evidence_status"] == "NOT_RUN"
    assert compiled_contract["certification_status"] == "NOT_CERTIFIED"
    assert "allow_implicit_invocation: true" in (
        installed_skill / "agents/openai.yaml"
    ).read_text(encoding="utf-8")
    assert "Runtime phase: `secure-intake`" in (
        installed_skill / "SKILL.md"
    ).read_text(encoding="utf-8")


def test_check_is_read_only_for_the_complete_managed_distribution(tmp_path: Path) -> None:
    archive, snapshot = _prepare_repository(tmp_path)
    importer.write_integration(tmp_path, archive)
    managed_paths = [
        tmp_path / importer.SOURCE_RELATIVE_PATH,
        tmp_path / importer.COMPILED_MANIFEST_RELATIVE_PATH,
        tmp_path / importer.INSTALLED_MANIFEST_RELATIVE_PATH,
        *(
            tmp_path / root / skill.name
            for root in importer.INSTALL_ROOTS
            for skill in snapshot.skills
        ),
    ]
    before = {
        path.relative_to(tmp_path).as_posix(): importer._path_fingerprint(path)
        for path in managed_paths
    }
    root_entries_before = sorted(path.name for path in tmp_path.iterdir())

    importer.check_integration(tmp_path, archive)

    after = {
        path.relative_to(tmp_path).as_posix(): importer._path_fingerprint(path)
        for path in managed_paths
    }
    assert after == before
    assert sorted(path.name for path in tmp_path.iterdir()) == root_entries_before


def test_check_rejects_installed_skill_drift(tmp_path: Path) -> None:
    archive, snapshot = _prepare_repository(tmp_path)
    importer.write_integration(tmp_path, archive)
    drifted = (
        tmp_path
        / importer.INSTALL_ROOTS[0]
        / snapshot.skills[0].name
        / "SKILL.md"
    )
    drifted.write_text(drifted.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="drift"):
        importer.check_integration(tmp_path, archive)


def test_write_never_overwrites_generated_skill_or_manifest_drift(tmp_path: Path) -> None:
    archive, snapshot = _prepare_repository(tmp_path)
    importer.write_integration(tmp_path, archive)
    interface = (
        tmp_path
        / importer.INSTALL_ROOTS[0]
        / snapshot.skills[0].name
        / "agents/openai.yaml"
    )
    interface.write_text(interface.read_text(encoding="utf-8") + "# user edit\n", encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="drifted installed Skill"):
        importer.write_integration(tmp_path, archive)
    assert interface.read_text(encoding="utf-8").endswith("# user edit\n")

    interface.write_bytes(
        importer._expected_skill_payloads(
            snapshot,
            importer._runtime_snapshot(tmp_path),
            importer._running_importer_sha256(),
        )[snapshot.skills[0].name]["agents/openai.yaml"].data
    )
    compiled = tmp_path / importer.COMPILED_MANIFEST_RELATIVE_PATH
    compiled.write_text(compiled.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(importer.IntegrationError, match="drifted generated manifests"):
        importer.write_integration(tmp_path, archive)


def test_current_manifests_never_heal_legacy_shaped_installed_drift(
    tmp_path: Path,
) -> None:
    archive, snapshot = _prepare_repository(tmp_path)
    importer.write_integration(tmp_path, archive)
    skill = snapshot.skills[0]
    destination = tmp_path / importer.INSTALL_ROOTS[0] / skill.name
    shutil.rmtree(destination)
    importer._write_payload_tree(
        destination,
        importer._legacy_skill_payloads(skill),
    )
    legacy_fingerprint = importer._path_fingerprint(destination)

    with pytest.raises(importer.IntegrationError) as raised:
        importer.write_integration(tmp_path, archive)

    assert raised.value.code == "MULTIMODAL_MANAGED_DRIFT"
    assert importer._path_fingerprint(destination) == legacy_fingerprint


def test_write_atomically_upgrades_an_exact_prior_managed_generation(tmp_path: Path) -> None:
    archive, snapshot = _prepare_repository(tmp_path)
    importer.write_integration(tmp_path, archive)
    prior_installed = (
        tmp_path / importer.INSTALL_ROOTS[0] / snapshot.skills[0].name / "SKILL.md"
    ).read_bytes()
    runtime_test = tmp_path / "apps/web-console/app/lib/server/multimodalIntakeRunner.verify.mjs"
    runtime_test.write_text(
        runtime_test.read_text(encoding="utf-8") + "legitimate runtime revision\n",
        encoding="utf-8",
    )

    importer.write_integration(tmp_path, archive)
    importer.check_integration(tmp_path, archive)

    upgraded_installed = (
        tmp_path / importer.INSTALL_ROOTS[0] / snapshot.skills[0].name / "SKILL.md"
    ).read_bytes()
    assert upgraded_installed != prior_installed
    installed_manifest = importer._load_json(
        tmp_path / importer.INSTALLED_MANIFEST_RELATIVE_PATH,
        "installed manifest",
    )
    assert installed_manifest["runtime"]["tests_sha256"] == importer._runtime_snapshot(
        tmp_path
    ).tests_sha256


def test_managed_upgrade_accepts_the_recognized_pre_verify_test_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _snapshot = _prepare_repository(tmp_path)
    current_repository_tests = importer.REPOSITORY_TEST_FILES
    current_exact_files = importer.OWNED_SURFACE_EXACT_FILES
    verify_relative = Path(
        "apps/web-console/app/lib/server/multimodalIntakeRunner.verify.mjs"
    )
    verify_path = tmp_path / verify_relative
    verify_payload = verify_path.read_bytes()
    verify_path.unlink()
    monkeypatch.setattr(
        importer,
        "REPOSITORY_TEST_FILES",
        importer.LEGACY_REPOSITORY_TEST_FILES_V1,
    )
    monkeypatch.setattr(
        importer,
        "OWNED_SURFACE_EXACT_FILES",
        tuple(path for path in current_exact_files if path != verify_relative),
    )
    importer.write_integration(tmp_path, archive)
    monkeypatch.setattr(importer, "REPOSITORY_TEST_FILES", current_repository_tests)
    monkeypatch.setattr(importer, "OWNED_SURFACE_EXACT_FILES", current_exact_files)
    verify_path.write_bytes(verify_payload)

    importer.write_integration(tmp_path, archive)
    importer.check_integration(tmp_path, archive)

    compiled = importer._load_json(
        tmp_path / importer.COMPILED_MANIFEST_RELATIVE_PATH,
        "compiled manifest",
    )
    test_paths = {item["path"] for item in compiled["runtime"]["tests"]["files"]}
    assert "apps/web-console/app/lib/server/multimodalIntakeRunner.verify.mjs" in test_paths


def test_managed_upgrade_accepts_the_recognized_pre_outbox_integrity_test_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _snapshot = _prepare_repository(tmp_path)
    current_engine_tests = importer.ENGINE_TEST_FILES
    test_relative = Path("tests/test_core_outbox_delivery_integrity.py")
    test_path = tmp_path / importer.ENGINE_ROOT_RELATIVE_PATH / test_relative
    test_payload = test_path.read_bytes()
    test_path.unlink()
    monkeypatch.setattr(
        importer,
        "ENGINE_TEST_FILES",
        importer.LEGACY_ENGINE_TEST_FILES_V1,
    )
    importer.write_integration(tmp_path, archive)
    monkeypatch.setattr(importer, "ENGINE_TEST_FILES", current_engine_tests)
    test_path.write_bytes(test_payload)

    importer.write_integration(tmp_path, archive)
    importer.check_integration(tmp_path, archive)

    compiled = importer._load_json(
        tmp_path / importer.COMPILED_MANIFEST_RELATIVE_PATH,
        "compiled manifest",
    )
    test_paths = {item["path"] for item in compiled["runtime"]["tests"]["files"]}
    assert (
        "engines/multimodal-intake-engine/tests/"
        "test_core_outbox_delivery_integrity.py"
    ) in test_paths


def test_managed_upgrade_refuses_one_root_user_drift(tmp_path: Path) -> None:
    archive, snapshot = _prepare_repository(tmp_path)
    importer.write_integration(tmp_path, archive)
    runtime_test = tmp_path / "apps/web-console/app/lib/server/multimodalIntakeRunner.verify.mjs"
    runtime_test.write_text(
        runtime_test.read_text(encoding="utf-8") + "legitimate runtime revision\n",
        encoding="utf-8",
    )
    drifted = (
        tmp_path / importer.INSTALL_ROOTS[1] / snapshot.skills[0].name / "SKILL.md"
    )
    drifted.write_text(
        drifted.read_text(encoding="utf-8") + "user-owned edit\n",
        encoding="utf-8",
    )
    compiled = tmp_path / importer.COMPILED_MANIFEST_RELATIVE_PATH
    installed = tmp_path / importer.INSTALLED_MANIFEST_RELATIVE_PATH
    manifests_before = (compiled.read_bytes(), installed.read_bytes())

    with pytest.raises(importer.IntegrationError, match="managed Skills|drifted"):
        importer.write_integration(tmp_path, archive)

    assert drifted.read_text(encoding="utf-8").endswith("user-owned edit\n")
    assert (compiled.read_bytes(), installed.read_bytes()) == manifests_before


def test_managed_upgrade_requires_manifest_digest_binding(tmp_path: Path) -> None:
    archive, _snapshot = _prepare_repository(tmp_path)
    importer.write_integration(tmp_path, archive)
    runtime_test = tmp_path / "apps/web-console/app/lib/server/multimodalIntakeRunner.verify.mjs"
    runtime_test.write_text(
        runtime_test.read_text(encoding="utf-8") + "legitimate runtime revision\n",
        encoding="utf-8",
    )
    installed_path = tmp_path / importer.INSTALLED_MANIFEST_RELATIVE_PATH
    installed = importer._load_json(installed_path, "installed manifest")
    installed["compiled_manifest_sha256"] = "0" * 64
    installed_path.write_text(
        json.dumps(installed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(importer.IntegrationError, match="drifted generated manifests"):
        importer.write_integration(tmp_path, archive)

    assert importer._load_json(installed_path, "installed manifest")[
        "compiled_manifest_sha256"
    ] == "0" * 64


def test_write_refuses_existing_user_skill_without_partial_install(tmp_path: Path) -> None:
    archive, snapshot = _prepare_repository(tmp_path)
    conflict = tmp_path / importer.INSTALL_ROOTS[0] / snapshot.skills[-1].name
    conflict.mkdir(parents=True)
    user_file = conflict / "SKILL.md"
    user_file.write_text("user-owned\n", encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="refusing to overwrite"):
        importer.write_integration(tmp_path, archive)

    assert user_file.read_text(encoding="utf-8") == "user-owned\n"
    assert not (tmp_path / importer.INSTALL_ROOTS[0] / snapshot.skills[0].name).exists()
    assert not (tmp_path / importer.INSTALL_ROOTS[1] / snapshot.skills[0].name).exists()


@pytest.mark.parametrize(
    "member_name",
    [
        f"{importer.ARCHIVE_ROOT}/../escape.txt",
        f"{importer.ARCHIVE_ROOT}/safe\\escape.txt",
        f"{importer.ARCHIVE_ROOT}/nested/C:/escape.txt",
        f"{importer.ARCHIVE_ROOT}/nested/NUL.txt",
        "/absolute.txt",
    ],
)
def test_central_directory_rejects_unsafe_paths(member_name: str) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(member_name, b"unsafe")
    with zipfile.ZipFile(io.BytesIO(payload.getvalue()), "r") as archive:
        with pytest.raises(importer.IntegrationError):
            importer._validate_central_directory(
                archive,
                expected_entries=None,
                expected_uncompressed_bytes=None,
            )


def test_central_directory_rejects_symlinks() -> None:
    payload = io.BytesIO()
    info = zipfile.ZipInfo(f"{importer.ARCHIVE_ROOT}/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(info, b"../../outside")
    with zipfile.ZipFile(io.BytesIO(payload.getvalue()), "r") as archive:
        with pytest.raises(importer.IntegrationError, match="link or special"):
            importer._validate_central_directory(
                archive,
                expected_entries=None,
                expected_uncompressed_bytes=None,
            )


@pytest.mark.parametrize("flag_bits", [0x1, 0x40, 0x41])
def test_central_directory_rejects_encrypted_members(flag_bits: int) -> None:
    archive = _CentralDirectoryFixture(
        [_regular_zip_info("encrypted.txt", flag_bits=flag_bits)]
    )

    with pytest.raises(importer.IntegrationError) as raised:
        importer._validate_central_directory(
            archive,  # type: ignore[arg-type]
            expected_entries=None,
            expected_uncompressed_bytes=None,
        )

    assert raised.value.code == "MULTIMODAL_ARCHIVE_MEMBER_UNSAFE"


@pytest.mark.parametrize(
    "second_name",
    ["case.TXT", "\uff43\uff41\uff53\uff45.txt"],
)
def test_central_directory_rejects_case_and_unicode_compatibility_collisions(
    second_name: str,
) -> None:
    archive = _CentralDirectoryFixture(
        [
            _regular_zip_info("case.txt"),
            _regular_zip_info(second_name),
        ]
    )

    with pytest.raises(importer.IntegrationError, match="collision") as raised:
        importer._validate_central_directory(
            archive,  # type: ignore[arg-type]
            expected_entries=None,
            expected_uncompressed_bytes=None,
        )

    assert raised.value.code == "MULTIMODAL_ARCHIVE_MEMBER_UNSAFE"


def test_central_directory_rejects_member_count_ratio_and_special_mode() -> None:
    too_many = _CentralDirectoryFixture(
        [
            _regular_zip_info(f"member-{index:04d}.txt")
            for index in range(importer.MAX_ARCHIVE_ENTRIES + 1)
        ]
    )
    with pytest.raises(importer.IntegrationError, match="member count"):
        importer._validate_central_directory(
            too_many,  # type: ignore[arg-type]
            expected_entries=None,
            expected_uncompressed_bytes=None,
        )

    unsafe_ratio = _CentralDirectoryFixture(
        [_regular_zip_info("ratio.txt", file_size=101, compress_size=1)]
    )
    with pytest.raises(importer.IntegrationError, match="compression ratio"):
        importer._validate_central_directory(
            unsafe_ratio,  # type: ignore[arg-type]
            expected_entries=None,
            expected_uncompressed_bytes=None,
        )

    special = _regular_zip_info("fifo", mode=0o644)
    special.external_attr = (stat.S_IFIFO | 0o644) << 16
    with pytest.raises(importer.IntegrationError, match="link or special"):
        importer._validate_central_directory(
            _CentralDirectoryFixture([special]),  # type: ignore[arg-type]
            expected_entries=None,
            expected_uncompressed_bytes=None,
        )


def test_archive_member_read_rejects_crc_mismatch_with_stable_code() -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(_regular_zip_info("payload.txt"), b"payload")
    with zipfile.ZipFile(io.BytesIO(payload.getvalue()), "r") as archive:
        info = archive.getinfo(f"{importer.ARCHIVE_ROOT}/payload.txt")
        info.CRC ^= 1
        with pytest.raises(importer.IntegrationError) as raised:
            importer._member_digest(archive, info)

    assert raised.value.code == "MULTIMODAL_ARCHIVE_INTEGRITY_INVALID"


def test_archive_member_name_rejects_invalid_unicode_and_path_bounds() -> None:
    with pytest.raises(importer.IntegrationError) as invalid_unicode:
        importer._safe_archive_name(f"{importer.ARCHIVE_ROOT}/\ud800")
    assert invalid_unicode.value.code == "MULTIMODAL_ARCHIVE_MEMBER_UNSAFE"

    overlong_component = "a" * (importer.MAX_ARCHIVE_COMPONENT_BYTES + 1)
    with pytest.raises(importer.IntegrationError, match="component exceeds"):
        importer._safe_archive_name(
            f"{importer.ARCHIVE_ROOT}/{overlong_component}"
        )


def test_pinned_archive_reader_rejects_symlink_and_wrong_compressed_size(tmp_path: Path) -> None:
    linked = tmp_path / "linked.zip"
    linked.symlink_to(_real_archive())
    with pytest.raises(importer.IntegrationError, match="opened safely"):
        importer.validate_archive(linked)

    truncated = tmp_path / "truncated.zip"
    truncated.write_bytes(b"not the pinned archive")
    with pytest.raises(importer.IntegrationError, match="compressed-byte mismatch"):
        importer.validate_archive(truncated)


def test_cli_reports_stable_archive_identity_error_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    truncated = tmp_path / "truncated.zip"
    truncated.write_bytes(b"not the pinned archive")

    result = importer.main(
        [
            "--check",
            "--repo-root",
            str(tmp_path),
            "--archive",
            str(truncated),
        ]
    )

    assert result == 1
    assert capsys.readouterr().err.startswith(
        "ERROR[MULTIMODAL_ARCHIVE_IDENTITY_INVALID]:"
    )


def test_runtime_inventory_rejects_bytecode_even_when_source_exists(tmp_path: Path) -> None:
    _archive, _snapshot = _prepare_repository(tmp_path)
    bytecode = (
        tmp_path
        / importer.ENGINE_ROOT_RELATIVE_PATH
        / "src/elmos_multimodal_intake/__pycache__/skill_runtime.cpython-312.pyc"
    )
    bytecode.parent.mkdir(parents=True)
    bytecode.write_bytes(b"untrusted bytecode")

    with pytest.raises(importer.IntegrationError, match="runtime file inventory drift"):
        importer._runtime_snapshot(tmp_path)


def test_owned_surface_inventory_rejects_an_undeclared_file(tmp_path: Path) -> None:
    _archive, _snapshot = _prepare_repository(tmp_path)
    undeclared = (
        tmp_path
        / "apps/web-console/app/api/multimodal-intake/v1/shadow/route.ts"
    )
    undeclared.parent.mkdir(parents=True)
    undeclared.write_text("export const shadow = true;\n", encoding="utf-8")

    with pytest.raises(
        importer.IntegrationError,
        match="owned multimodal surface inventory drift",
    ):
        importer._runtime_snapshot(tmp_path)


@pytest.mark.parametrize(
    ("migration_name", "current_version", "drifted_version"),
    [
        ("023_processing_job_cancellation.sql", 23, 22),
        ("024_core_outbox_delivery_receipts.sql", 24, 23),
    ],
)
def test_runtime_inventory_binds_latest_migrations(
    tmp_path: Path,
    migration_name: str,
    current_version: int,
    drifted_version: int,
) -> None:
    _archive, _snapshot = _prepare_repository(tmp_path)
    root_migration = (
        tmp_path
        / importer.ENGINE_ROOT_RELATIVE_PATH
        / "migrations"
        / migration_name
    )
    root_migration.write_text(
        root_migration.read_text(encoding="utf-8").replace(
            f"PRAGMA user_version = {current_version}",
            f"PRAGMA user_version = {drifted_version}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(importer.IntegrationError, match="packaged migration drift"):
        importer._runtime_snapshot(tmp_path)


def test_runtime_inventory_binds_packaged_operation_input_schema(
    tmp_path: Path,
) -> None:
    _archive, _snapshot = _prepare_repository(tmp_path)
    _source_relative, packaged_relative = importer.PACKAGED_RUNTIME_FILE_PAIRS[0]
    packaged_schema = (
        tmp_path / importer.ENGINE_ROOT_RELATIVE_PATH / packaged_relative
    )
    packaged_schema.write_bytes(packaged_schema.read_bytes() + b"\n")

    with pytest.raises(importer.IntegrationError, match="packaged runtime file drift"):
        importer._runtime_snapshot(tmp_path)


def test_runtime_inventory_rejects_an_extra_openapi_external_schema_reference(
    tmp_path: Path,
) -> None:
    _archive, _snapshot = _prepare_repository(tmp_path)
    openapi = (
        tmp_path
        / importer.ENGINE_ROOT_RELATIVE_PATH
        / "openapi/multimodal-intake-v1.openapi.yaml"
    )
    source = openapi.read_text(encoding="utf-8")
    exact_reference = (
        f'- {{ $ref: "{importer.OPENAPI_OPERATION_INPUT_SCHEMA_REFERENCE}" }}'
    )
    openapi.write_text(
        source.replace(
            exact_reference,
            exact_reference + '\n- { $ref: "https://example.invalid/schema.json" }',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        importer.IntegrationError,
        match="external reference inventory drifted",
    ):
        importer._runtime_snapshot(tmp_path)


def test_runtime_inventory_rejects_human_review_contract_drift(tmp_path: Path) -> None:
    _archive, _snapshot = _prepare_repository(tmp_path)
    relative = "src/elmos_multimodal_intake/human_review.py"
    path = tmp_path / importer.ENGINE_ROOT_RELATIVE_PATH / relative
    marker = importer.HUMAN_REVIEW_RUNTIME_CONTRACT_MARKERS[relative][0]
    path.write_text(path.read_text(encoding="utf-8").replace(marker, ""), encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="human-review runtime contract drift"):
        importer._runtime_snapshot(tmp_path)


def test_runtime_inventory_rejects_sdk_compiler_contract_drift(tmp_path: Path) -> None:
    _archive, _snapshot = _prepare_repository(tmp_path)
    relative = "tools/verify_sdks.py"
    path = tmp_path / importer.ENGINE_ROOT_RELATIVE_PATH / relative
    marker = importer.SDK_COMPILATION_TOOL_RUNTIME_CONTRACT_MARKERS[relative][5]
    path.write_text(
        path.read_text(encoding="utf-8").replace(marker, ""),
        encoding="utf-8",
    )

    with pytest.raises(importer.IntegrationError, match="sdk-compilation-tool.*drift"):
        importer._runtime_snapshot(tmp_path)


def _standalone_file_transaction(
    tmp_path: Path,
) -> tuple[
    Path,
    importer._ManagedTarget,
    dict[str, str],
    Path,
    dict[str, object],
]:
    destination = tmp_path / "managed.txt"
    destination.write_bytes(b"original")
    destination.chmod(0o644)
    target = importer._ManagedTarget(
        destination=destination,
        kind="file",
        payload=importer.FilePayload(b"replacement"),
        replace=True,
        original_fingerprint=importer._path_fingerprint(destination),
        label="standalone managed file",
    )
    allowed_targets = {"managed.txt": "file"}
    transaction_root, journal = importer._initialize_transaction(
        tmp_path,
        [target],
        allowed_targets,
    )
    staged = transaction_root / "staged/000"
    importer._write_payload_file(staged, target.payload)
    importer._fsync_directory(staged.parent)
    assert importer._path_fingerprint(staged) == journal["targets"][0][
        "staged_fingerprint"
    ]
    return destination, target, allowed_targets, transaction_root, journal


def test_repository_writer_lock_rejects_concurrent_writer(tmp_path: Path) -> None:
    with importer._writer_lock(tmp_path):
        with pytest.raises(importer.IntegrationError, match="writer is active"):
            with importer._writer_lock(tmp_path):
                pytest.fail("a second repository writer acquired the same lock")


def test_check_fails_closed_and_does_not_modify_stale_transaction(tmp_path: Path) -> None:
    archive, _snapshot = _prepare_repository(tmp_path)
    transaction_root = tmp_path / f"{importer.TRANSACTION_PREFIX}manual01"
    transaction_root.mkdir(mode=0o700)
    marker = transaction_root / "preserve-me"
    marker.write_bytes(b"incomplete transaction")
    before = marker.read_bytes()

    with pytest.raises(importer.IntegrationError, match="requires --write recovery"):
        importer.check_integration(tmp_path, archive)

    assert marker.read_bytes() == before


def test_write_recovers_stale_allowed_publish_before_installing(tmp_path: Path) -> None:
    archive, snapshot = _prepare_repository(tmp_path)
    (
        _runtime,
        _engine_sha256,
        _importer_sha256,
        _operation_registry,
        _source_payloads,
        skill_payloads,
        _compiled_payload,
        _installed_payload,
    ) = importer._prepare_expectations(tmp_path, snapshot)
    skill = snapshot.skills[0]
    destination = importer._resolve_below(
        tmp_path,
        importer.INSTALL_ROOTS[0] / skill.name,
    )
    target = importer._ManagedTarget(
        destination=destination,
        kind="tree",
        payload=skill_payloads[skill.name],
        replace=False,
        original_fingerprint=None,
        label="stale installed Skill",
    )
    allowed = importer._allowed_managed_targets(snapshot)
    transaction_root, journal = importer._initialize_transaction(
        tmp_path,
        [target],
        allowed,
    )
    staged = transaction_root / "staged/000"
    importer._write_payload_tree(staged, target.payload)
    importer._fsync_tree_directories(staged)
    importer._fsync_directory(staged.parent)
    created: set[str] = set()
    importer._ensure_parent_directories(
        destination,
        tmp_path,
        set(journal["created_parents"]),
        created,
    )
    importer._advance_target_state(transaction_root, journal, 0, "BACKED_UP")
    importer._durable_replace(staged, destination)

    importer.write_integration(tmp_path, archive)
    importer.check_integration(tmp_path, archive)

    assert not transaction_root.exists()
    importer._assert_tree_matches(
        destination,
        skill_payloads[skill.name],
        "recovered installed Skill",
    )


@pytest.mark.parametrize(
    "crash_point",
    ["after_backup", "after_publish", "after_publish_journal", "during_recovery"],
)
def test_stale_transaction_recovers_physical_step_ahead_of_journal(
    tmp_path: Path,
    crash_point: str,
) -> None:
    destination, _target, allowed, transaction_root, journal = (
        _standalone_file_transaction(tmp_path)
    )
    staged = transaction_root / "staged/000"
    backup = transaction_root / "backups/000"
    importer._durable_replace(destination, backup)
    if crash_point != "after_backup":
        importer._advance_target_state(transaction_root, journal, 0, "BACKED_UP")
        importer._durable_replace(staged, destination)
    if crash_point in {"after_publish_journal", "during_recovery"}:
        importer._advance_target_state(transaction_root, journal, 0, "PUBLISHED")
    if crash_point == "during_recovery":
        importer._mark_recovery_started(transaction_root, journal)

    importer._recover_stale_transactions(
        tmp_path,
        archive_sha256=importer.ARCHIVE_SHA256,
        allowed_targets=allowed,
    )

    assert destination.read_bytes() == b"original"
    assert not transaction_root.exists()


def test_verified_stale_transaction_is_finalized_not_rolled_back(tmp_path: Path) -> None:
    destination, _target, allowed, transaction_root, journal = (
        _standalone_file_transaction(tmp_path)
    )
    staged = transaction_root / "staged/000"
    backup = transaction_root / "backups/000"
    assert journal["targets"][0]["state"] == "INTENT"
    importer._durable_replace(destination, backup)
    importer._advance_target_state(transaction_root, journal, 0, "BACKED_UP")
    persisted = json.loads(
        (transaction_root / importer.TRANSACTION_JOURNAL_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert persisted["targets"][0]["state"] == "BACKED_UP"
    importer._durable_replace(staged, destination)
    importer._advance_target_state(transaction_root, journal, 0, "PUBLISHED")
    persisted = json.loads(
        (transaction_root / importer.TRANSACTION_JOURNAL_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert persisted["targets"][0]["state"] == "PUBLISHED"
    importer._mark_transaction_verified(transaction_root, journal)

    persisted = json.loads(
        (transaction_root / importer.TRANSACTION_JOURNAL_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert persisted["targets"][0]["state"] == "VERIFIED"
    importer._recover_stale_transactions(
        tmp_path,
        archive_sha256=importer.ARCHIVE_SHA256,
        allowed_targets=allowed,
    )

    assert destination.read_bytes() == b"replacement"
    assert not transaction_root.exists()


def test_recovery_refuses_third_party_destination_change_and_preserves_backup(
    tmp_path: Path,
) -> None:
    destination, _target, allowed, transaction_root, journal = (
        _standalone_file_transaction(tmp_path)
    )
    staged = transaction_root / "staged/000"
    backup = transaction_root / "backups/000"
    importer._durable_replace(destination, backup)
    importer._advance_target_state(transaction_root, journal, 0, "BACKED_UP")
    importer._durable_replace(staged, destination)
    importer._advance_target_state(transaction_root, journal, 0, "PUBLISHED")
    destination.write_bytes(b"third-party change")

    with pytest.raises(importer.IntegrationError, match="artifacts preserved|changed"):
        importer._recover_stale_transactions(
            tmp_path,
            archive_sha256=importer.ARCHIVE_SHA256,
            allowed_targets=allowed,
        )

    assert transaction_root.exists()
    assert backup.read_bytes() == b"original"
    assert destination.read_bytes() == b"third-party change"


def test_recovery_rejects_non_allowlisted_journal_target(tmp_path: Path) -> None:
    destination, _target, allowed, transaction_root, journal = (
        _standalone_file_transaction(tmp_path)
    )
    journal["targets"][0]["destination"] = "../outside.txt"
    importer._write_journal_atomic(transaction_root, journal)

    with pytest.raises(importer.IntegrationError, match="artifacts preserved|allowlisted"):
        importer._recover_stale_transactions(
            tmp_path,
            archive_sha256=importer.ARCHIVE_SHA256,
            allowed_targets=allowed,
        )

    assert transaction_root.exists()
    assert destination.read_bytes() == b"original"


def test_transaction_cleanup_never_ignores_removal_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _destination, _target, _allowed, transaction_root, _journal = (
        _standalone_file_transaction(tmp_path)
    )

    def refuse_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        assert kwargs.get("ignore_errors") is not True
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(importer.shutil, "rmtree", refuse_cleanup)
    with pytest.raises(OSError, match="injected cleanup failure"):
        importer._cleanup_transaction(tmp_path, transaction_root)
    assert transaction_root.exists()


def test_incomplete_rollback_preserves_original_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "managed.txt"
    destination.write_bytes(b"original")
    target = importer._ManagedTarget(
        destination=destination,
        kind="file",
        payload=importer.FilePayload(b"replacement"),
        replace=True,
        original_fingerprint=importer._path_fingerprint(destination),
        label="managed test file",
    )
    real_replace = importer.os.replace

    def fail_publish_and_restore(source: Path | str, target_path: Path | str) -> None:
        source_path = Path(source)
        destination_path = Path(target_path)
        if destination_path == destination and source_path.parent.name in {"staged", "backups"}:
            raise OSError("injected replace failure")
        real_replace(source, target_path)

    monkeypatch.setattr(importer.os, "replace", fail_publish_and_restore)
    with pytest.raises(importer.IntegrationError, match="recovery artifacts preserved"):
        importer._apply_transaction(tmp_path, [target], lambda: None, None)

    transactions = list(tmp_path.glob(".multimodal-intake-transaction-*"))
    assert len(transactions) == 1
    assert (transactions[0] / "backups/000").read_bytes() == b"original"


def test_managed_path_resolution_rejects_symlink_ancestor(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)

    with pytest.raises(importer.IntegrationError, match="traverses a symlink"):
        importer._resolve_below(tmp_path, Path("alias/managed.json"))


def test_engine_registry_is_read_statically_without_import(tmp_path: Path) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    marker = tmp_path / "must-not-exist"
    engine.write_text(
        _synthetic_runtime(snapshot)
        + f'\nif __name__ != "never":\n    open({str(marker)!r}, "w").close()\n',
        encoding="utf-8",
    )

    digest, registry = importer._parse_engine_registry(engine, snapshot.skills)

    assert len(digest) == 64
    assert len(registry) == 50
    assert not marker.exists()


def test_real_engine_registry_matches_pinned_contracts() -> None:
    snapshot = importer.validate_archive(_real_archive())

    digest, registry = importer._parse_engine_registry(
        REPOSITORY_ROOT / importer.ENGINE_RELATIVE_PATH,
        snapshot.skills,
    )

    assert len(digest) == 64
    assert registry == {skill.name: skill.handler_id for skill in snapshot.skills}


def test_operation_registry_is_parsed_statically_and_covers_every_skill() -> None:
    snapshot = importer.validate_archive(_real_archive())

    registry = importer._parse_operation_registry(
        REPOSITORY_ROOT / importer.OPERATION_REGISTRY_RELATIVE_PATH,
        [skill.name for skill in snapshot.skills],
    )

    assert registry.schema_version == importer.EXPECTED_OPERATION_REGISTRY_SCHEMA
    assert registry.operation_count == importer.EXPECTED_OPERATION_COUNT == 147
    assert registry.skill_names == tuple(sorted(skill.name for skill in snapshot.skills))
    assert registry.document_sha256 == importer.EXPECTED_OPERATION_REGISTRY_DIGEST
    importer._validate_operation_input_schema(
        REPOSITORY_ROOT
        / importer.ENGINE_ROOT_RELATIVE_PATH
        / "openapi/operation-input-contracts.schema.json",
        registry,
    )


def test_operation_input_schema_rejects_one_field_contract_drift(
    tmp_path: Path,
) -> None:
    snapshot = importer.validate_archive(_real_archive())
    registry = importer._parse_operation_registry(
        REPOSITORY_ROOT / importer.OPERATION_REGISTRY_RELATIVE_PATH,
        [skill.name for skill in snapshot.skills],
    )
    source = (
        REPOSITORY_ROOT
        / importer.ENGINE_ROOT_RELATIVE_PATH
        / "openapi/operation-input-contracts.schema.json"
    )
    document = json.loads(source.read_bytes())
    document["allOf"][0]["then"]["properties"]["input"]["properties"][
        "undeclared_field"
    ] = {}
    drifted = tmp_path / "operation-input-contracts.schema.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="does not exactly match"):
        importer._validate_operation_input_schema(drifted, registry)


def test_operation_registry_rejects_operation_contract_digest_drift(
    tmp_path: Path,
) -> None:
    snapshot = importer.validate_archive(_real_archive())
    source = (
        REPOSITORY_ROOT / importer.OPERATION_REGISTRY_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    registry_path = tmp_path / "operation_registry.py"
    registry_path.write_text(
        source.replace('"bootstrap_project"', '"bootstrap_project_drift"', 1),
        encoding="utf-8",
    )

    with pytest.raises(importer.IntegrationError, match="document digest drift"):
        importer._parse_operation_registry(
            registry_path,
            [skill.name for skill in snapshot.skills],
        )


def test_operation_registry_rejects_skill_coverage_drift(tmp_path: Path) -> None:
    snapshot = importer.validate_archive(_real_archive())
    source = (
        REPOSITORY_ROOT / importer.OPERATION_REGISTRY_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    registry_path = tmp_path / "operation_registry.py"
    registry_path.write_text(
        source.replace(
            '"elmos-multimodal-input-orchestrator"',
            '"elmos-undeclared-shadow-skill"',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(importer.IntegrationError, match="Skill coverage drift"):
        importer._parse_operation_registry(
            registry_path,
            [skill.name for skill in snapshot.skills],
        )


def test_operation_registry_rejects_invalid_single_arity(tmp_path: Path) -> None:
    snapshot = importer.validate_archive(_real_archive())
    source = (
        REPOSITORY_ROOT / importer.OPERATION_REGISTRY_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    registry_path = tmp_path / "operation_registry.py"
    registry_path.write_text(
        source.replace(
            '*_single("elmos-unified-multimodal-content-ir", "normalize", '
            '"blocks relations source_schema_version document_id")',
            '*_single("elmos-unified-multimodal-content-ir", "normalize")',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(importer.IntegrationError, match="static _spec/_single"):
        importer._parse_operation_registry(
            registry_path,
            [skill.name for skill in snapshot.skills],
        )


def test_engine_registry_rejects_missing_handler(tmp_path: Path) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    engine.write_text(
        _synthetic_runtime(snapshot).replace(
            (
                f'    "{snapshot.skills[0].name}": _entry({snapshot.skills[0].ordinal}, '
                f'"{snapshot.skills[0].name}", "{importer.EXPECTED_HANDLER_PHASES[0]}", '
                f'{snapshot.skills[0].handler_id}),\n'
            ),
            "",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(importer.IntegrationError, match="SKILL_REGISTRY drift"):
        importer._parse_engine_registry(engine, snapshot.skills)


def test_engine_registry_rejects_non_entry_bindings(tmp_path: Path) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    source = _synthetic_runtime(snapshot)
    source = source.replace(
        (
            f'    "{snapshot.skills[0].name}": _entry({snapshot.skills[0].ordinal}, '
            f'"{snapshot.skills[0].name}", "{importer.EXPECTED_HANDLER_PHASES[0]}", '
            f'{snapshot.skills[0].handler_id}),'
        ),
        (
            f'    "{snapshot.skills[0].name}": HandlerBinding('
            f'handler_id="{snapshot.skills[0].handler_id}", '
            f'handler={snapshot.skills[0].handler_id}),'
        ),
        1,
    )
    engine.write_text(source, encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="exact static _entry"):
        importer._parse_engine_registry(engine, snapshot.skills)


def test_engine_registry_rejects_duplicate_callable_binding(tmp_path: Path) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    source = _synthetic_runtime(snapshot).replace(
        (
            f'    "{snapshot.skills[1].name}": _entry({snapshot.skills[1].ordinal}, '
            f'"{snapshot.skills[1].name}", "{importer.EXPECTED_HANDLER_PHASES[1]}", '
            f'{snapshot.skills[1].handler_id}),'
        ),
        (
            f'    "{snapshot.skills[1].name}": _entry({snapshot.skills[1].ordinal}, '
            f'"{snapshot.skills[1].name}", "{importer.EXPECTED_HANDLER_PHASES[1]}", '
            f'{snapshot.skills[0].handler_id}),'
        ),
        1,
    )
    engine.write_text(source, encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="drift|unique"):
        importer._parse_engine_registry(engine, snapshot.skills)


@pytest.mark.parametrize(
    "replacement",
    [
        "_entry()",
        "_entry(True, 'wrong', 'content', execute_multimodal_input_orchestrator)",
        "module._entry(1, 'elmos-multimodal-input-orchestrator', 'secure-intake', execute_multimodal_input_orchestrator)",
        "_entry(ordinal=1, skill='elmos-multimodal-input-orchestrator', phase='secure-intake', handler=execute_multimodal_input_orchestrator)",
    ],
)
def test_engine_registry_rejects_malformed_entry_calls(tmp_path: Path, replacement: str) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    expected = (
        f'_entry(1, "{snapshot.skills[0].name}", "{importer.EXPECTED_HANDLER_PHASES[0]}", '
        f'{snapshot.skills[0].handler_id})'
    )
    engine.write_text(_synthetic_runtime(snapshot).replace(expected, replacement, 1), encoding="utf-8")

    with pytest.raises(importer.IntegrationError):
        importer._parse_engine_registry(engine, snapshot.skills)


def test_engine_registry_rejects_wrong_but_known_phase(tmp_path: Path) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    expected = (
        f'_entry(1, "{snapshot.skills[0].name}", "{importer.EXPECTED_HANDLER_PHASES[0]}", '
        f'{snapshot.skills[0].handler_id})'
    )
    replacement = (
        f'_entry(1, "{snapshot.skills[0].name}", "content", '
        f'{snapshot.skills[0].handler_id})'
    )
    engine.write_text(_synthetic_runtime(snapshot).replace(expected, replacement, 1), encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="phase|identity"):
        importer._parse_engine_registry(engine, snapshot.skills)


def test_engine_registry_rejects_entry_helper_body_drift(tmp_path: Path) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    source = _synthetic_runtime(snapshot).replace(
        'getattr(handler, "__name__")',
        "handler.__name__",
        1,
    )
    engine.write_text(source, encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="_entry helper implementation drift"):
        importer._parse_engine_registry(engine, snapshot.skills)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("@dataclass(frozen=True)", "@dataclass"),
        ("    handler_id: str", "    callable_id: str"),
        ("    handler: SkillHandler", "    handler: object"),
    ],
)
def test_engine_registry_rejects_handler_binding_drift(
    tmp_path: Path,
    old: str,
    new: str,
) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    engine.write_text(_synthetic_runtime(snapshot).replace(old, new, 1), encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="HandlerBinding"):
        importer._parse_engine_registry(engine, snapshot.skills)


@pytest.mark.parametrize(
    "statement_template",
    [
        "_entry = lambda *args: None",
        "HandlerBinding = object",
        "getattr = lambda value, name: name",
        "len = lambda value: 50",
        "<HANDLER> = lambda request: request",
        "class <HANDLER>:\n    pass",
        "from builtins import id as <HANDLER>",
        "if True:\n    SKILL_REGISTRY = {}",
    ],
)
def test_engine_registry_rejects_protected_name_rebinding(
    tmp_path: Path,
    statement_template: str,
) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    statement = statement_template.replace("<HANDLER>", snapshot.skills[0].handler_id)
    engine.write_text(_synthetic_runtime(snapshot) + "\n" + statement + "\n", encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="protected runtime name"):
        importer._parse_engine_registry(engine, snapshot.skills)


def test_engine_registry_rejects_star_import_shadowing(tmp_path: Path) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    engine.write_text(
        _synthetic_runtime(snapshot) + "\nfrom arbitrary_runtime import *\n",
        encoding="utf-8",
    )

    with pytest.raises(importer.IntegrationError, match="star import"):
        importer._parse_engine_registry(engine, snapshot.skills)


@pytest.mark.parametrize(
    "statement_template",
    [
        "SKILL_REGISTRY |= {}",
        "del SKILL_REGISTRY[\"<SKILL>\"]",
        "SKILL_REGISTRY[\"extra\"] = None",
        "SKILL_REGISTRY.__setitem__(\"extra\", None)",
        "registry_alias = SKILL_REGISTRY\nregistry_alias.clear()",
        "globals()[\"SKILL_REGISTRY\"] = {}",
    ],
)
def test_engine_registry_rejects_registry_mutation_or_alias(
    tmp_path: Path,
    statement_template: str,
) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    statement = statement_template.replace("<SKILL>", snapshot.skills[0].name)
    engine.write_text(_synthetic_runtime(snapshot) + "\n" + statement + "\n", encoding="utf-8")

    with pytest.raises(importer.IntegrationError):
        importer._parse_engine_registry(engine, snapshot.skills)


@pytest.mark.parametrize(
    "replacement_template",
    [
        "async def <HANDLER>(request):",
        "def <HANDLER>():",
        "def <HANDLER>(request, extra):",
    ],
)
def test_engine_registry_rejects_async_or_bad_handler_signature(
    tmp_path: Path,
    replacement_template: str,
) -> None:
    snapshot = importer.validate_archive(_real_archive())
    engine = tmp_path / "skill_runtime.py"
    handler = snapshot.skills[0].handler_id
    source = _synthetic_runtime(snapshot).replace(
        f"def {handler}(request):",
        replacement_template.replace("<HANDLER>", handler),
        1,
    )
    engine.write_text(source, encoding="utf-8")

    with pytest.raises(importer.IntegrationError, match="synchronous request callable"):
        importer._parse_engine_registry(engine, snapshot.skills)
