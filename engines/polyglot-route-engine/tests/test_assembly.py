"""Tests for `assembly.py`: turning a batch report's PASSED units into one project.

Most tests here construct a batch report and batch output directory by hand,
deliberately bypassing `run_batch`/`migrate`, so they exercise assembly's own
placement, namespacing and fail-closed logic without requiring any of the four
exact language toolchains to be installed. `test_end_to_end_...` is the
exception: it drives the real `plan_repository -> discover_repository ->
run_batch -> assemble_project -> verify_assembled_project` pipeline, mirroring
`test_repository_pipeline.py`'s conventions, and therefore does require the
real Python and TypeScript toolchains pinned by `toolchains.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route import assembly
from elmos_polyglot_route.assembly import (
    MANIFEST_NAME,
    assemble_project,
    verify_assembled_project,
    write_assembly_deployment_guidance,
)
from elmos_polyglot_route.batch import run_batch
from elmos_polyglot_route.discovery import Verdict, discover_repository
from elmos_polyglot_route.identifier_hygiene import (
    identifier_plan_bytes,
    plan_identifiers,
    repository_work_unit_namespace,
    target_function_view,
)
from elmos_polyglot_route.models import Language, RouteError, SemanticIR
from elmos_polyglot_route.repository import plan_repository


def _digest(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _fake_cmake_tree_identity(prefix: Path) -> tuple[int, int, str]:
    resource_root = prefix / "share" / "cmake"
    paths = [
        prefix / "bin" / "cmake",
        resource_root,
        *sorted(resource_root.rglob("*"), key=lambda path: path.relative_to(prefix).as_posix()),
    ]
    records: list[dict[str, int | str]] = []
    total_file_bytes = 0
    for path in paths:
        metadata = path.lstat()
        relative = path.relative_to(prefix).as_posix()
        if stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
            content = b""
            digest = ""
        else:
            kind = "file"
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            total_file_bytes += len(content)
        records.append(
            {
                "path": relative,
                "kind": kind,
                "mode": stat.S_IMODE(metadata.st_mode),
                "uid": metadata.st_uid,
                "gid": metadata.st_gid,
                "bytes": len(content),
                "sha256": digest,
            }
        )
    canonical = json.dumps(
        records,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return len(records), total_file_bytes, hashlib.sha256(canonical).hexdigest()


@pytest.fixture
def fake_cmake_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[Path, Path]]:
    assembly._clear_cmake_runtime()
    prefix = (tmp_path / "Cellar" / "cmake" / "4.4.0").resolve()
    executable = prefix / "bin" / "cmake"
    resource_file = prefix / "share" / "cmake" / "Modules" / "Fake.cmake"
    executable.parent.mkdir(parents=True)
    resource_file.parent.mkdir(parents=True)
    executable.write_text(
        '#!/bin/sh\nif [ "$1" = "--version" ]; then\n  printf \'cmake version 4.4.0\\n\'\nfi\n',
        encoding="utf-8",
    )
    executable.chmod(0o555)
    resource_file.write_text("set(FAKE_CMAKE_RESOURCE TRUE)\n", encoding="utf-8")
    resource_file.chmod(0o444)
    entry_count, total_file_bytes, tree_sha256 = _fake_cmake_tree_identity(prefix)
    executable_bytes = executable.read_bytes()

    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_PREFIX", prefix)
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_EXECUTABLE", executable)
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_RESOURCE_ROOT", prefix / "share" / "cmake")
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_SOURCE_UID", os.getuid())
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_SOURCE_GID", os.getgid())
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_BYTES", len(executable_bytes))
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_SHA256", hashlib.sha256(executable_bytes).hexdigest())
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_TREE_ENTRY_COUNT", entry_count)
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_TREE_FILE_BYTES", total_file_bytes)
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_TREE_SHA256", tree_sha256)
    snapshot = assembly._read_cmake_source_snapshot(retain_contents=False)
    runtime_manifest = assembly._cmake_runtime_manifest(snapshot)
    monkeypatch.setattr(assembly, "_EXPECTED_CMAKE_RUNTIME_MANIFEST_BYTES", len(runtime_manifest))
    monkeypatch.setattr(
        assembly,
        "_EXPECTED_CMAKE_RUNTIME_MANIFEST_SHA256",
        hashlib.sha256(runtime_manifest).hexdigest(),
    )
    try:
        yield prefix, resource_file
    finally:
        assembly._clear_cmake_runtime()


_FIXTURE_SNAPSHOT = "a" * 64


def _target_language(target_path: str) -> Language:
    filename = Path(target_path).name
    if filename == "Migrated.java":
        return "java"
    suffixes: dict[str, Language] = {
        ".py": "python",
        ".cs": "csharp",
        ".ts": "typescript",
        ".mjs": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".m": "objc",
        ".swift": "swift",
    }
    return suffixes[Path(filename).suffix]


def _fixture_source_language(target_language: Language) -> Language:
    return "java" if target_language == "python" else "python"


def _unit_materials(
    unit_id: str,
    target_path: str,
    content: str,
    function_name: str,
) -> tuple[str, bytes, str, bytes, str, str]:
    target_language = _target_language(target_path)
    source_language = _fixture_source_language(target_language)
    source_path = f"src/{unit_id}.src"
    source_sha256 = hashlib.sha256(f"fixture-source:{unit_id}".encode()).hexdigest()
    source_ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": source_language,
            "source_file": Path(source_path).name,
            "analyzer": "strict-assembly-fixture-analyzer",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": function_name,
                    "parameters": [{"name": "value", "type": "integer"}],
                    "return_type": "integer",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {"kind": "name", "value": "value"},
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )
    namespace = repository_work_unit_namespace(
        repository_snapshot_sha256="sha256:" + _FIXTURE_SNAPSHOT,
        work_unit_id=unit_id,
        source_logical_path=source_path,
        source_sha256="sha256:" + source_sha256,
    )
    plan = plan_identifiers(source_ir, target_language, unit_namespace=namespace)
    target_function = target_function_view(source_ir, source_ir.functions[0], plan)
    observation = {
        "case_id": 0,
        "status": "RETURNED",
        "value": 1,
        "encoding": "json",
        "raw": '{"case_id":0,"value":1}',
    }
    behavior = {
        "schema_version": "1.0.0",
        "kind": "elmos.behavior-equivalence",
        "status": "PASSED",
        "case_count": 1,
        "pass_count": 1,
        "source_runtime_pass_count": 1,
        "target_runtime_pass_count": 1,
        "source_runtime_passed": True,
        "target_runtime_passed": True,
        "oracle_conflict_count": 0,
        "counterexample_count": 0,
        "results": [
            {
                "case_id": 0,
                "arguments_sha256": "sha256:" + hashlib.sha256(b"[1]").hexdigest(),
                "canonical": {"status": "RETURNED", "value": 1, "error": None},
                "source_native": observation,
                "target_native": observation,
                "independent_expected": 1,
                "status": "PASSED",
            }
        ],
        "counterexamples": [],
    }
    behavior_bytes = (json.dumps(behavior, indent=2, sort_keys=True) + "\n").encode()
    payload = {
        "schema_version": "1.0.0",
        "status": "PASSED_LOCAL_UNCERTIFIED",
        "repository_execution_mode": True,
        "behavior_case_count": 1,
        "behavior_pass_rate": 1.0,
        "source": {
            "path": Path(source_path).name,
            "sha256": "sha256:" + source_sha256,
            "language": source_language,
            "function_name": function_name,
        },
        "target": {
            "path": target_path,
            "sha256": _digest(content),
            "language": target_language,
            "function_name": target_function.name,
        },
        "identifier_hygiene": {
            "status": "PASSED",
            "plan_path": "identifier-plan.json",
            "plan_sha256": plan.digest,
            "source_function_name": function_name,
            "target_function_name": target_function.name,
            "unit_namespace": plan.unit_namespace.to_mapping(),
            "unit_namespace_sha256": plan.unit_namespace.digest,
        },
        "source_validation": {"status": "PASSED", "case_count": 1, "observations": [observation]},
        "validation": {"status": "PASSED", "case_count": 1, "observations": [observation]},
        "behavior_equivalence": {
            "status": "PASSED",
            "case_count": 1,
            "pass_count": 1,
            "source_runtime_passed": True,
            "target_runtime_passed": True,
            "oracle_conflict_count": 0,
            "artifact_path": "behavior-equivalence.json",
            "artifact_sha256": "sha256:" + hashlib.sha256(behavior_bytes).hexdigest(),
        },
    }
    evidence_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    source_ir_text = json.dumps(source_ir.to_mapping(), indent=2, sort_keys=True) + "\n"
    return (
        evidence_text,
        identifier_plan_bytes(plan),
        source_ir_text,
        behavior_bytes,
        target_function.name,
        source_sha256,
    )


def _write_unit(
    batch_output: Path,
    unit_id: str,
    target_path: str,
    content: str,
    *,
    function_name: str = "calculate",
) -> None:
    evidence_text, plan_bytes, source_ir_text, behavior_bytes, _target_function, _source_sha256 = _unit_materials(
        unit_id,
        target_path,
        content,
        function_name,
    )
    directory = batch_output / "units" / unit_id
    directory.mkdir(parents=True)
    (directory / target_path).write_text(content, encoding="utf-8")
    (directory / "route-evidence.json").write_text(evidence_text, encoding="utf-8")
    (directory / "identifier-plan.json").write_bytes(plan_bytes)
    (directory / "source-semantic-ir.json").write_text(source_ir_text, encoding="utf-8")
    (directory / "behavior-equivalence.json").write_bytes(behavior_bytes)


def _passed_unit(unit_id: str, target_path: str, content: str, *, function_name: str = "calculate") -> dict[str, Any]:
    evidence_text, _plan_bytes, _source_ir_text, _behavior_bytes, target_function, source_sha256 = _unit_materials(
        unit_id,
        target_path,
        content,
        function_name,
    )
    plan = json.loads(_plan_bytes)
    return {
        "id": unit_id,
        "source_path": f"src/{unit_id}.src",
        "status": "PASSED",
        "function_name": function_name,
        "target_function_name": target_function,
        "identifier_plan_path": "identifier-plan.json",
        "identifier_plan_sha256": "sha256:" + hashlib.sha256(_plan_bytes).hexdigest(),
        "target_path": target_path,
        "target_sha256": _digest(content),
        "evidence_path": f"units/{unit_id}/route-evidence.json",
        "evidence_sha256": _digest(evidence_text),
        "behavior_case_count": 1,
        "checkpoint_identity": {
            "snapshot_sha256": _FIXTURE_SNAPSHOT,
            "source_path": f"src/{unit_id}.src",
            "source_sha256": source_sha256,
            "function_name": function_name,
            "verdict": "READY",
            "identifier_unit_namespace": plan["unit_namespace"],
            "identifier_unit_namespace_sha256": plan["unit_namespace_sha256"],
        },
        "identifier_unit_namespace": plan["unit_namespace"],
        "identifier_unit_namespace_sha256": plan["unit_namespace_sha256"],
    }


def _batch_report(target_language: str, units: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = {
        status: sum(1 for unit in units if unit.get("status") == status)
        for status in ("PASSED", "FAILED", "SKIPPED_NOT_READY", "SKIPPED_NO_CASES")
        if any(unit.get("status") == status for unit in units)
    }
    attempted_count = status_counts.get("PASSED", 0) + status_counts.get("FAILED", 0)
    complete = status_counts == {"PASSED": len(units)}
    source_language: Language = "java" if target_language == "python" else "python"
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.repository-batch-report",
        "status": "COMPLETE" if complete else "PARTIAL",
        "repository_ref": "local:customer-repository",
        "snapshot_sha256": _FIXTURE_SNAPSHOT,
        "route_id": f"{source_language}-to-{target_language}",
        "source_language": source_language,
        "target_language": target_language,
        "work_unit_count": len(units),
        "selected_count": len(units),
        "attempted_count": attempted_count,
        "unattempted_count": len(units) - attempted_count,
        "status_counts": status_counts,
        "units": units,
    }


PYTHON_UNIT_A = "def calculate(a: int, b: int) -> int:\n    return a + b\n"
PYTHON_UNIT_B = "def calculate(a: int, b: int) -> int:\n    return a - b\n"
JAVA_UNIT = (
    "public final class Migrated {\n    public static long add(long a, long b) {\n        return (a + b);\n    }\n}\n"
)
CSHARP_UNIT = (
    "public static class Migrated\n"
    "{\n"
    "    public static long Calculate(long value) => value;\n"
    "}\n"
)

ADDITIONAL_TARGET_UNITS = {
    "javascript": (
        "migrated.mjs",
        "export function calculate(a, b) { return a + b; }\n",
    ),
    "go": ("migrated.go", "package main\n\nfunc calculate(a int64, b int64) int64 { return a + b }\n"),
    "rust": ("migrated.rs", "fn calculate(a: i64, b: i64) -> i64 { a + b }\n"),
    "cpp": (
        "migrated.cpp",
        "#include <cstdint>\n\nstd::int64_t calculate(std::int64_t a, std::int64_t b) { return a + b; }\n",
    ),
    "objc": (
        "migrated.m",
        "#import <Foundation/Foundation.h>\n\nlong long calculate(long long a, long long b) { return a + b; }\n",
    ),
    "swift": ("migrated.swift", "func calculate(_ a: Int, _ b: Int) -> Int { a + b }\n"),
}


def test_assemble_places_python_units_under_collision_free_modules(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    _write_unit(batch_output, "WU-00002", "migrated.py", PYTHON_UNIT_B)
    report = _batch_report(
        "python",
        [
            _passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A),
            _passed_unit("WU-00002", "migrated.py", PYTHON_UNIT_B),
        ],
    )

    destination = tmp_path / "assembled"
    manifest = assemble_project(report, batch_output, destination)

    assert manifest["kind"] == "elmos.repository-assembly-report"
    assert manifest["included_unit_count"] == 2
    assert manifest["excluded_unit_count"] == 0
    assert manifest["build_verification_status"] == "NOT_RUN"

    first = destination / "src" / "elmos_generated" / "wu00001.py"
    second = destination / "src" / "elmos_generated" / "wu00002.py"
    assert first.read_text(encoding="utf-8") == PYTHON_UNIT_A
    assert second.read_text(encoding="utf-8") == PYTHON_UNIT_B
    # Same function name in both units never collides because each keeps its own module.
    assert first.read_text().count("def calculate") == 1
    assert second.read_text().count("def calculate") == 1
    assert (destination / "src" / "elmos_generated" / "__init__.py").is_file()
    assert (destination / "pyproject.toml").is_file()
    assert (destination / MANIFEST_NAME).is_file()


def test_assemble_wraps_each_java_unit_in_its_own_package(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "Migrated.java", JAVA_UNIT, function_name="add")
    report = _batch_report("java", [_passed_unit("WU-00001", "Migrated.java", JAVA_UNIT, function_name="add")])

    destination = tmp_path / "assembled"
    manifest = assemble_project(report, batch_output, destination)

    placed = destination / "src" / "main" / "java" / "elmos" / "generated" / "wu00001" / "Migrated.java"
    content = placed.read_text(encoding="utf-8")
    assert content.startswith("package elmos.generated.wu00001;\n\n")
    assert "public final class Migrated" in content
    assert manifest["included_units"][0]["assembled_path"] == "src/main/java/elmos/generated/wu00001/Migrated.java"
    assert (destination / "pom.xml").is_file()


def test_csharp_build_compiles_only_assembled_sources_not_evidence_copies(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    units = []
    for index in (1, 2):
        unit_id = f"WU-{index:05d}"
        _write_unit(batch_output, unit_id, "Migrated.cs", CSHARP_UNIT)
        units.append(_passed_unit(unit_id, "Migrated.cs", CSHARP_UNIT))

    destination = tmp_path / "assembled"
    assemble_project(_batch_report("csharp", units), batch_output, destination)

    project = (destination / "polyglot-migrated-library.csproj").read_text(encoding="utf-8")
    assert "<EnableDefaultCompileItems>false</EnableDefaultCompileItems>" in project
    assert '<Compile Include="src/**/*.cs" />' in project
    assert len(list((destination / "evidence").glob("*/Migrated.cs"))) == 2
    assert verify_assembled_project("csharp", destination)["build_verification_status"] == "PASSED"


@pytest.mark.parametrize(
    ("target_language", "expected_path", "build_files"),
    [
        ("javascript", "src/generated/wu00001.mjs", {"package.json"}),
        ("go", "units/wu00001/migrated.go", {"go.mod"}),
        ("rust", "src/wu00001.rs", {"Cargo.toml", "src/lib.rs"}),
        ("cpp", "src/wu00001/migrated.cpp", {"CMakeLists.txt"}),
        ("objc", "src/wu00001/migrated.m", {"CMakeLists.txt"}),
        ("swift", "Sources/Wu00001/migrated.swift", {"Package.swift"}),
    ],
)
def test_assemble_supports_every_additional_target_project_shape(
    tmp_path: Path,
    target_language: str,
    expected_path: str,
    build_files: set[str],
) -> None:
    target_path, content = ADDITIONAL_TARGET_UNITS[target_language]
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", target_path, content)
    report = _batch_report(
        target_language,
        [_passed_unit("WU-00001", target_path, content)],
    )

    destination = tmp_path / "assembled"
    manifest = assemble_project(report, batch_output, destination)

    assert manifest["included_units"][0]["assembled_path"] == expected_path
    assert (destination / expected_path).is_file()
    assert set(manifest["build_files"]) == build_files
    assert all((destination / relative).is_file() for relative in build_files)
    if target_language == "go":
        assert (destination / expected_path).read_text(encoding="utf-8").startswith("package wu00001\n")
    if target_language == "rust":
        assert (destination / "src" / "lib.rs").read_text(encoding="utf-8") == "pub mod wu00001;\n"
    if target_language in {"cpp", "objc"}:
        cmake = (destination / "CMakeLists.txt").read_text(encoding="utf-8")
        assert "add_library(elmos_migrated SHARED" in cmake
        assert expected_path in cmake


@pytest.mark.parametrize("target_language", ["cpp", "objc"])
def test_native_assembly_links_all_units_in_one_target_to_expose_symbol_collisions(
    tmp_path: Path,
    target_language: Language,
) -> None:
    target_path, content = ADDITIONAL_TARGET_UNITS[target_language]
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", target_path, content)
    _write_unit(batch_output, "WU-00002", target_path, content)
    destination = tmp_path / "assembled"

    assemble_project(
        _batch_report(
            target_language,
            [
                _passed_unit("WU-00001", target_path, content),
                _passed_unit("WU-00002", target_path, content),
            ],
        ),
        batch_output,
        destination,
    )

    cmake = (destination / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "add_library(elmos_migrated SHARED" in cmake
    assert "src/wu00001/migrated" in cmake
    assert "src/wu00002/migrated" in cmake

    with pytest.raises(RouteError, match="ASSEMBLY_BUILD_VERIFICATION_FAILED"):
        verify_assembled_project(target_language, destination)


@pytest.mark.parametrize("target_language", ["javascript", "go", "rust", "cpp", "objc", "swift"])
def test_verify_assembled_project_builds_every_additional_target(
    tmp_path: Path,
    target_language: Language,
) -> None:
    target_path, content = ADDITIONAL_TARGET_UNITS[target_language]
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", target_path, content)
    destination = tmp_path / "assembled"
    assemble_project(
        _batch_report(
            target_language,
            [_passed_unit("WU-00001", target_path, content)],
        ),
        batch_output,
        destination,
    )

    verified = verify_assembled_project(target_language, destination)

    assert verified["build_verification_status"] == "PASSED"
    assert verified["build_verification"]["commands"]
    assert (destination / "docs" / "LOCAL_RUN.md").is_file()
    if target_language == "javascript":
        local_guidance = (destination / "docs" / "LOCAL_RUN.md").read_text(encoding="utf-8")
        deployment = json.loads((destination / "deploy" / "deployment-options.json").read_text(encoding="utf-8"))
        assert "-exec node --check {} \\;" in local_guidance
        assert deployment["local"]["build_commands"] == [
            "find src/generated -name '*.mjs' -type f -exec node --check {} \\;"
        ]


def test_javascript_assembly_checks_every_included_module(tmp_path: Path) -> None:
    valid = "export function first(a, b) { return a + b; }\n"
    invalid = "export function second( {\n"
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.mjs", valid, function_name="first")
    _write_unit(batch_output, "WU-00002", "migrated.mjs", invalid, function_name="second")
    destination = tmp_path / "assembled"
    assemble_project(
        _batch_report(
            "javascript",
            [
                _passed_unit("WU-00001", "migrated.mjs", valid, function_name="first"),
                _passed_unit("WU-00002", "migrated.mjs", invalid, function_name="second"),
            ],
        ),
        batch_output,
        destination,
    )

    with pytest.raises(RouteError, match="ASSEMBLY_BUILD_VERIFICATION_FAILED"):
        verify_assembled_project("javascript", destination)

    manifest = json.loads((destination / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["build_verification_status"] == "NOT_RUN"


def test_assembly_process_uses_a_private_environment_without_ambient_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hostile = {
        "JAVA_TOOL_OPTIONS": "-javaagent:/tmp/hostile.jar",
        "NODE_OPTIONS": "--require=/tmp/hostile.cjs",
        "PYTHONPATH": str(tmp_path / "hostile-python"),
        "RUSTFLAGS": "-Clinker=/tmp/hostile-linker",
        "CMAKE_TOOLCHAIN_FILE": str(tmp_path / "hostile.cmake"),
    }
    for key, value in hostile.items():
        monkeypatch.setenv(key, value)

    observed: dict[str, str] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        observed.update(environment)
        assert not set(hostile).intersection(environment)
        for key in ("HOME", "TMPDIR", "XDG_CACHE_HOME"):
            path = Path(environment[key])
            assert path.is_dir()
            assert stat.S_IMODE(path.stat().st_mode) == 0o700
        assert environment["PATH"].split(":") == ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("elmos_polyglot_route.assembly.subprocess.run", fake_run)
    result = assembly._run(["/usr/bin/true"], tmp_path)

    assert result.returncode == 0
    assert observed
    assert not Path(observed["HOME"]).exists()
    assert not Path(observed["TMPDIR"]).exists()


def test_assembly_process_failure_preserves_bounded_sanitized_dual_streams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_value = "stdout-secret"
    stderr_value = "stderr-secret"
    stdout = (
        "STDOUT-HEAD-"
        + ("A" * 3_000)
        + f"\ncompiler error at {tmp_path}/source.cs TOKEN={stdout_value}\nCS0101"
    )
    stderr = (
        "STDERR-HEAD-"
        + ("B" * 3_000)
        + f"\n/private/runtime/welcome PASSWORD={stderr_value}\nfirst-run warning"
    )

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del kwargs
        return subprocess.CompletedProcess(command, 23, stdout, stderr)

    monkeypatch.setattr("elmos_polyglot_route.assembly.subprocess.run", fake_run)

    with pytest.raises(RouteError) as captured:
        assembly._run(["/private/toolchains/secret-tool"], tmp_path)

    message = str(captured.value)
    assert "ASSEMBLY_BUILD_VERIFICATION_FAILED:secret-tool:returncode=23" in message
    assert 'stdout="' in message
    assert 'stderr="' in message
    assert "CS0101" in message
    assert "first-run warning" in message
    assert stdout_value not in message
    assert stderr_value not in message
    assert str(tmp_path) not in message
    assert "/private/" not in message
    assert "STDOUT-HEAD" not in message
    assert "STDERR-HEAD" not in message


def test_cmake_selection_ignores_an_ambient_path_precedence_attack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_cmake_source: tuple[Path, Path],
) -> None:
    hostile_bin = tmp_path / "hostile-bin"
    hostile_bin.mkdir()
    hostile_cmake = hostile_bin / "cmake"
    hostile_cmake.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
    hostile_cmake.chmod(0o700)
    monkeypatch.setenv("PATH", f"{hostile_bin}:/usr/bin:/bin")

    selected = assembly._exact_cmake(tmp_path)

    assert selected.executable == selected.prefix / "bin" / "cmake"
    assert selected.executable.is_relative_to(selected.cache_root)
    assert selected.executable.resolve() != hostile_cmake.resolve()
    assert selected.executable.resolve() != (fake_cmake_source[0] / "bin" / "cmake").resolve()
    assert stat.S_IMODE(selected.prefix.stat().st_mode) == 0o700
    assert stat.S_IMODE(selected.executable.stat().st_mode) == 0o500


def test_cmake_snapshot_fails_closed_if_source_changes_after_private_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_cmake_source: tuple[Path, Path],
) -> None:
    _, resource_file = fake_cmake_source
    original = assembly._read_cmake_source_snapshot
    calls = 0

    def change_after_first_snapshot(*, retain_contents: bool) -> assembly._CMakeSourceSnapshot:
        nonlocal calls
        snapshot = original(retain_contents=retain_contents)
        calls += 1
        if calls == 1:
            resource_file.chmod(0o644)
            resource_file.write_text("set(FAKE_CMAKE_RESOURCE DRIFTED)\n", encoding="utf-8")
            resource_file.chmod(0o444)
        return snapshot

    monkeypatch.setattr(assembly, "_read_cmake_source_snapshot", change_after_first_snapshot)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_CMAKE_SOURCE_CHANGED_AFTER_COPY"):
        assembly._exact_cmake(tmp_path)


def test_cmake_execution_detects_private_manifest_toctou(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_cmake_source: tuple[Path, Path],
) -> None:
    del fake_cmake_source
    runtime = assembly._exact_cmake(tmp_path)
    manifest = runtime.prefix / assembly._CMAKE_RUNTIME_MANIFEST

    def tampering_run(command: list[str], cwd: Path, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del cwd, kwargs
        manifest.chmod(0o600)
        manifest.write_bytes(runtime.manifest_bytes + b"tampered\n")
        manifest.chmod(0o400)
        return subprocess.CompletedProcess(command, 0, assembly._EXPECTED_CMAKE_VERSION + "\n", "")

    monkeypatch.setattr(assembly, "_run", tampering_run)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_CMAKE_BUNDLE_MANIFEST_DRIFTED"):
        assembly._run_cmake(runtime, ["--version"], tmp_path)


def test_assembly_manifest_rejects_a_forged_cmake_runtime_binding(tmp_path: Path) -> None:
    target_path, content = ADDITIONAL_TARGET_UNITS["cpp"]
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", target_path, content)
    destination = tmp_path / "assembled"
    manifest = assemble_project(
        _batch_report("cpp", [_passed_unit("WU-00001", target_path, content)]),
        batch_output,
        destination,
    )
    manifest["build_verification_status"] = "PASSED"
    manifest["build_verification"] = {
        "toolchain_language": "cpp",
        "toolchain_version": "Apple clang version 17.0.0",
        "commands": [{"command": ["cmake", "--build", "build"], "stdout": "", "stderr": ""}],
        "cmake_runtime": {
            "kind": "private-content-addressed-cmake-runtime-v1",
            "version": assembly._EXPECTED_CMAKE_VERSION,
            "source_prefix": str(assembly._EXPECTED_CMAKE_PREFIX),
            "source_identity_sha256": assembly._EXPECTED_CMAKE_TREE_SHA256,
            "source_entry_count": assembly._EXPECTED_CMAKE_TREE_ENTRY_COUNT,
            "source_total_file_bytes": assembly._EXPECTED_CMAKE_TREE_FILE_BYTES,
            "bundle_manifest_bytes": assembly._EXPECTED_CMAKE_RUNTIME_MANIFEST_BYTES,
            "bundle_manifest_sha256": "1" * 64,
        },
    }
    assembly._write_manifest(destination, manifest)

    with pytest.raises(RouteError, match="ASSEMBLY_CMAKE_RUNTIME_BINDING_INVALID"):
        assembly.verify_assembly_closure("cpp", destination)


def test_assemble_excludes_non_passed_units_but_records_them(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    report = _batch_report(
        "python",
        [
            _passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A),
            {"id": "WU-00002", "status": "FAILED", "reason": "TARGET_VALIDATION_FAILED:javac:boom"},
            {"id": "WU-00003", "status": "SKIPPED_NO_CASES", "reason": "No behavior-case corpus."},
        ],
    )

    manifest = assemble_project(report, batch_output, tmp_path / "assembled")

    assert manifest["included_unit_count"] == 1
    assert manifest["excluded_unit_count"] == 2
    excluded_ids = {unit["id"] for unit in manifest["excluded_units"]}
    assert excluded_ids == {"WU-00002", "WU-00003"}


def test_assemble_rejects_content_that_drifted_from_the_recorded_hash(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    unit = _passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A)
    unit["target_sha256"] = _digest("something else entirely")
    report = _batch_report("python", [unit])

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_CONTENT_DRIFTED"):
        assemble_project(report, batch_output, tmp_path / "assembled")


def test_assemble_requires_target_and_behavior_evidence_digests(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    missing_target = _passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A)
    missing_target.pop("target_sha256")
    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_TARGET_DIGEST_REQUIRED"):
        assemble_project(
            _batch_report("python", [missing_target]),
            batch_output,
            tmp_path / "missing-target-digest",
        )

    missing_evidence = _passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A)
    missing_evidence.pop("evidence_sha256")
    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_EVIDENCE_DIGEST_REQUIRED"):
        assemble_project(
            _batch_report("python", [missing_evidence]),
            batch_output,
            tmp_path / "missing-evidence-digest",
        )


def test_assemble_rejects_self_reported_batch_counter_drift(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    report = _batch_report("python", [_passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A)])
    report["work_unit_count"] = 99

    with pytest.raises(RouteError, match="ASSEMBLY_BATCH_STATUS_COUNTS_INVALID"):
        assemble_project(report, batch_output, tmp_path / "assembled")


def test_assemble_rejects_symlinked_unit_directory(tmp_path: Path) -> None:
    external = tmp_path / "external"
    _write_unit(external, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    batch_output = tmp_path / "batch"
    (batch_output / "units").mkdir(parents=True)
    (batch_output / "units" / "WU-00001").symlink_to(
        external / "units" / "WU-00001",
        target_is_directory=True,
    )
    report = _batch_report(
        "python",
        [_passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A)],
    )

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_SOURCE_MISSING"):
        assemble_project(report, batch_output, tmp_path / "assembled")


def test_assemble_rejects_symlinked_unit_source_file(tmp_path: Path) -> None:
    external = tmp_path / "external.py"
    external.write_text(PYTHON_UNIT_A, encoding="utf-8")
    batch_output = tmp_path / "batch"
    unit = batch_output / "units" / "WU-00001"
    unit.mkdir(parents=True)
    (unit / "migrated.py").symlink_to(external)
    report = _batch_report(
        "python",
        [_passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A)],
    )

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_SOURCE_MISSING"):
        assemble_project(report, batch_output, tmp_path / "assembled")


def test_assemble_rejects_a_batch_report_with_no_passed_units(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    batch_output.mkdir()
    report = _batch_report("python", [{"id": "WU-00001", "status": "SKIPPED_NOT_READY", "reason": "UNSUPPORTED"}])

    with pytest.raises(RouteError, match="ASSEMBLY_NO_PASSED_UNITS_TO_ASSEMBLE"):
        assemble_project(report, batch_output, tmp_path / "assembled")


def test_assemble_rejects_a_target_path_that_is_not_a_bare_filename(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    unit = _passed_unit("WU-00001", "../migrated.py", PYTHON_UNIT_A)
    report = _batch_report("python", [unit])

    with pytest.raises(RouteError, match="ASSEMBLY_UNIT_TARGET_PATH_INVALID"):
        assemble_project(report, batch_output, tmp_path / "assembled")


def test_assemble_refuses_to_overwrite_an_existing_destination(tmp_path: Path) -> None:
    batch_output = tmp_path / "batch"
    _write_unit(batch_output, "WU-00001", "migrated.py", PYTHON_UNIT_A)
    report = _batch_report("python", [_passed_unit("WU-00001", "migrated.py", PYTHON_UNIT_A)])
    destination = tmp_path / "assembled"
    destination.mkdir()

    with pytest.raises(RouteError, match="ASSEMBLY_DESTINATION_ALREADY_EXISTS"):
        assemble_project(report, batch_output, destination)


def test_verify_assembled_project_requires_a_manifest(tmp_path: Path) -> None:
    destination = tmp_path / "assembled"
    destination.mkdir()
    with pytest.raises(RouteError, match="ASSEMBLY_MANIFEST_MISSING"):
        verify_assembled_project("python", destination)


def test_end_to_end_pipeline_assembles_and_build_verifies_a_python_project(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repository"
    (repository / "src").mkdir(parents=True)
    (repository / "src" / "pricing.py").write_text(
        "def calculate(subtotal: float, tax: float) -> float:\n"
        "    if tax < 0:\n"
        "        return subtotal\n"
        "    return subtotal + tax\n",
        encoding="utf-8",
    )
    (repository / "src" / "shipping.py").write_text(
        "def calculate(weight: float, rate: float) -> float:\n    return weight * rate\n",
        encoding="utf-8",
    )

    plan = plan_repository(repository, "local:customer-repository", "python", "typescript")
    discovery = discover_repository(plan, repository)
    ready_units = [result for result in discovery["results"] if result["verdict"] == Verdict.READY]
    assert len(ready_units) == 2

    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / f"{ready_units[0]['id']}.json").write_text(
        json.dumps([{"args": [100.0, 5.0], "expected": 105.0}, {"args": [100.0, -1.0], "expected": 100.0}]),
        encoding="utf-8",
    )
    (cases / f"{ready_units[1]['id']}.json").write_text(
        json.dumps([{"args": [2.0, 3.0], "expected": 6.0}]),
        encoding="utf-8",
    )

    batch_report = run_batch(discovery, repository, cases, tmp_path / "batch")
    assert batch_report["status_counts"]["PASSED"] == 2

    destination = tmp_path / "assembled"
    manifest = assemble_project(batch_report, tmp_path / "batch", destination)
    assert manifest["included_unit_count"] == 2
    assert manifest["build_verification_status"] == "NOT_RUN"
    assert not (destination / "docs" / "LOCAL_RUN.md").exists()

    verified = verify_assembled_project("typescript", destination)
    assert verified["build_verification_status"] == "PASSED"
    assert (destination / "dist").is_dir()
    assert (destination / "docs" / "LOCAL_RUN.md").is_file()
    assert (destination / "docs" / "CLOUD_PUBLISHING.md").is_file()
    assert (destination / "deploy" / "deployment-options.json").is_file()

    on_disk_manifest = json.loads((destination / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert on_disk_manifest["build_verification_status"] == "PASSED"


def test_write_assembly_deployment_guidance_is_reusable_independent_of_verify(tmp_path: Path) -> None:
    destination = tmp_path / "assembled"
    destination.mkdir()
    written = write_assembly_deployment_guidance(destination, "csharp", 3)
    assert set(written) == {
        "docs/LOCAL_RUN.md",
        "docs/CLOUD_PUBLISHING.md",
        "deploy/deployment-options.json",
    }
    for relative_path in written:
        assert (destination / relative_path).is_file()
