"""Functional coverage for the complete local repository route matrix.

This suite deliberately exercises repository execution rather than route-pack
certification.  Every ordered pair receives a fresh three-file source
repository, independent behavior cases for each work unit, and a fresh output
directory.  A local pass must therefore cover source execution, translation,
target execution, assembly, and the whole-target-project build without
upgrading the route's external or certification status.
"""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from decimal import Decimal
from itertools import product
from pathlib import Path, PurePosixPath
from typing import Any, cast

import pytest

from elmos_polyglot_route.models import SUPPORTED_LANGUAGES, Language
from elmos_polyglot_route.pipeline import (
    ARTIFACT_MANIFEST_NAME,
    ARTIFACT_NAME,
    REPORT_NAME,
    run_repository_pipeline,
)

DIRECTED_LANGUAGE_PAIRS: tuple[tuple[Language, Language], ...] = tuple(
    (source, target)
    for source, target in product(SUPPORTED_LANGUAGES, repeat=2)
    if source != target
)
MEDIUM_LANGUAGE_RING: tuple[tuple[Language, Language], ...] = tuple(
    (source, SUPPORTED_LANGUAGES[(index + 1) % len(SUPPORTED_LANGUAGES)])
    for index, source in enumerate(SUPPORTED_LANGUAGES)
)

_SMALL_MAXIMUM_BYTES = 8 * 1024 * 1024
_MEDIUM_MAXIMUM_BYTES = 64 * 1024 * 1024
_FILE_MAXIMUM_BYTES = 2 * 1024 * 1024
_MEDIUM_COMMENT_BYTES_PER_FILE = 1_700_000
_ASSEMBLY_AUXILIARY_INPUTS: dict[Language, tuple[str, ...]] = {
    "python": ("src/elmos_generated/__init__.py",),
}

_BEHAVIOR_CASES: tuple[list[dict[str, object]], ...] = (
    [
        {"args": [2, 3], "expected": 5},
        {"args": [-4, 1], "expected": -3},
    ],
    [
        {"args": [3, 4], "expected": 12},
        {"args": [-2, 5], "expected": -10},
    ],
    [
        {"args": [9, 4], "expected": 5},
        {"args": [-2, -3], "expected": 1},
    ],
)
_MEDIUM_BEHAVIOR_CASES: dict[str, list[dict[str, object]]] = {
    "add": _BEHAVIOR_CASES[0],
    "maximum": [
        {"args": [2, 3], "expected": 3},
        {"args": [-4, -1], "expected": -1},
    ],
    "minimum": [
        {"args": [2, 3], "expected": 2},
        {"args": [-4, -1], "expected": -4},
    ],
    "multiply": _BEHAVIOR_CASES[1],
    "subtract": _BEHAVIOR_CASES[2],
}

_SOURCE_FILES: dict[Language, tuple[tuple[str, str], ...]] = {
    "java": (
        (
            "Add.java",
            "public final class Add {\n"
            "    public static long add(long left, long right) { return left + right; }\n"
            "}\n",
        ),
        (
            "Multiply.java",
            "public final class Multiply {\n"
            "    public static long multiply(long left, long right) { return left * right; }\n"
            "}\n",
        ),
        (
            "Subtract.java",
            "public final class Subtract {\n"
            "    public static long subtract(long left, long right) { return left - right; }\n"
            "}\n",
        ),
    ),
    "python": (
        ("add.py", "def add(left: int, right: int) -> int:\n    return left + right\n"),
        (
            "multiply.py",
            "def multiply(left: int, right: int) -> int:\n    return left * right\n",
        ),
        (
            "subtract.py",
            "def subtract(left: int, right: int) -> int:\n    return left - right\n",
        ),
    ),
    "csharp": (
        (
            "Add.cs",
            "public static class Add\n"
            "{\n"
            "    public static long add(long left, long right) { return left + right; }\n"
            "}\n",
        ),
        (
            "Multiply.cs",
            "public static class Multiply\n"
            "{\n"
            "    public static long multiply(long left, long right) { return left * right; }\n"
            "}\n",
        ),
        (
            "Subtract.cs",
            "public static class Subtract\n"
            "{\n"
            "    public static long subtract(long left, long right) { return left - right; }\n"
            "}\n",
        ),
    ),
    "typescript": (
        (
            "add.ts",
            "export function add(left: number, right: number): number {\n"
            "  return left + right;\n"
            "}\n",
        ),
        (
            "multiply.ts",
            "export function multiply(left: number, right: number): number {\n"
            "  return left * right;\n"
            "}\n",
        ),
        (
            "subtract.ts",
            "export function subtract(left: number, right: number): number {\n"
            "  return left - right;\n"
            "}\n",
        ),
    ),
    "go": (
        (
            "add.go",
            "package sample\n\nfunc add(left int64, right int64) int64 {\n"
            "\treturn left + right\n"
            "}\n",
        ),
        (
            "multiply.go",
            "package sample\n\nfunc multiply(left int64, right int64) int64 {\n"
            "\treturn left * right\n"
            "}\n",
        ),
        (
            "subtract.go",
            "package sample\n\nfunc subtract(left int64, right int64) int64 {\n"
            "\treturn left - right\n"
            "}\n",
        ),
    ),
    "rust": (
        ("add.rs", "fn add(left: i64, right: i64) -> i64 {\n    return left + right;\n}\n"),
        (
            "multiply.rs",
            "fn multiply(left: i64, right: i64) -> i64 {\n    return left * right;\n}\n",
        ),
        (
            "subtract.rs",
            "fn subtract(left: i64, right: i64) -> i64 {\n    return left - right;\n}\n",
        ),
    ),
    "cpp": (
        (
            "add.cpp",
            "#include <cstdint>\n\n"
            "std::int64_t add(std::int64_t left, std::int64_t right) { return left + right; }\n",
        ),
        (
            "multiply.cpp",
            "#include <cstdint>\n\n"
            "std::int64_t multiply(std::int64_t left, std::int64_t right) { return left * right; }\n",
        ),
        (
            "subtract.cpp",
            "#include <cstdint>\n\n"
            "std::int64_t subtract(std::int64_t left, std::int64_t right) { return left - right; }\n",
        ),
    ),
    "objc": (
        ("add.m", "long long add(long long left, long long right) { return left + right; }\n"),
        (
            "multiply.m",
            "long long multiply(long long left, long long right) { return left * right; }\n",
        ),
        (
            "subtract.m",
            "long long subtract(long long left, long long right) { return left - right; }\n",
        ),
    ),
    "swift": (
        (
            "add.swift",
            "func add(_ left: Int64, _ right: Int64) -> Int64 {\n"
            "    return left + right\n"
            "}\n",
        ),
        (
            "multiply.swift",
            "func multiply(_ left: Int64, _ right: Int64) -> Int64 {\n"
            "    return left * right\n"
            "}\n",
        ),
        (
            "subtract.swift",
            "func subtract(_ left: Int64, _ right: Int64) -> Int64 {\n"
            "    return left - right\n"
            "}\n",
        ),
    ),
}

_MEDIUM_EXTRA_SOURCE_FILES: dict[Language, tuple[tuple[str, str], ...]] = {
    "java": (
        (
            "Maximum.java",
            "public final class Maximum {\n"
            "    public static long maximum(long left, long right) {\n"
            "        if (left > right) { return left; }\n"
            "        return right;\n"
            "    }\n"
            "}\n",
        ),
        (
            "Minimum.java",
            "public final class Minimum {\n"
            "    public static long minimum(long left, long right) {\n"
            "        if (left < right) { return left; }\n"
            "        return right;\n"
            "    }\n"
            "}\n",
        ),
    ),
    "python": (
        (
            "maximum.py",
            "def maximum(left: int, right: int) -> int:\n"
            "    if left > right:\n"
            "        return left\n"
            "    return right\n",
        ),
        (
            "minimum.py",
            "def minimum(left: int, right: int) -> int:\n"
            "    if left < right:\n"
            "        return left\n"
            "    return right\n",
        ),
    ),
    "csharp": (
        (
            "Maximum.cs",
            "public static class Maximum\n"
            "{\n"
            "    public static long maximum(long left, long right)\n"
            "    {\n"
            "        if (left > right) { return left; }\n"
            "        return right;\n"
            "    }\n"
            "}\n",
        ),
        (
            "Minimum.cs",
            "public static class Minimum\n"
            "{\n"
            "    public static long minimum(long left, long right)\n"
            "    {\n"
            "        if (left < right) { return left; }\n"
            "        return right;\n"
            "    }\n"
            "}\n",
        ),
    ),
    "typescript": (
        (
            "maximum.ts",
            "export function maximum(left: number, right: number): number {\n"
            "  if (left > right) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
        (
            "minimum.ts",
            "export function minimum(left: number, right: number): number {\n"
            "  if (left < right) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
    ),
    "go": (
        (
            "maximum.go",
            "package sample\n\nfunc maximum(left int64, right int64) int64 {\n"
            "\tif left > right { return left }\n"
            "\treturn right\n"
            "}\n",
        ),
        (
            "minimum.go",
            "package sample\n\nfunc minimum(left int64, right int64) int64 {\n"
            "\tif left < right { return left }\n"
            "\treturn right\n"
            "}\n",
        ),
    ),
    "rust": (
        (
            "maximum.rs",
            "fn maximum(left: i64, right: i64) -> i64 {\n"
            "    if left > right { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
        (
            "minimum.rs",
            "fn minimum(left: i64, right: i64) -> i64 {\n"
            "    if left < right { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
    ),
    "cpp": (
        (
            "maximum.cpp",
            "#include <cstdint>\n\n"
            "std::int64_t maximum(std::int64_t left, std::int64_t right) {\n"
            "    if (left > right) { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
        (
            "minimum.cpp",
            "#include <cstdint>\n\n"
            "std::int64_t minimum(std::int64_t left, std::int64_t right) {\n"
            "    if (left < right) { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
    ),
    "objc": (
        (
            "maximum.m",
            "long long maximum(long long left, long long right) {\n"
            "    if (left > right) { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
        (
            "minimum.m",
            "long long minimum(long long left, long long right) {\n"
            "    if (left < right) { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
    ),
    "swift": (
        (
            "maximum.swift",
            "func maximum(_ left: Int64, _ right: Int64) -> Int64 {\n"
            "    if left > right { return left }\n"
            "    return right\n"
            "}\n",
        ),
        (
            "minimum.swift",
            "func minimum(_ left: Int64, _ right: Int64) -> Int64 {\n"
            "    if left < right { return left }\n"
            "    return right\n"
            "}\n",
        ),
    ),
}


def _write_repository_and_cases(root: Path, source_language: Language) -> tuple[Path, Path]:
    repository = root / "repository"
    cases = root / "cases"
    repository.mkdir()
    cases.mkdir()

    source_files = _SOURCE_FILES[source_language]
    assert len(source_files) == 3
    assert [name for name, _ in source_files] == sorted(name for name, _ in source_files)
    for index, ((name, content), behavior_cases) in enumerate(
        zip(source_files, _BEHAVIOR_CASES, strict=True),
        start=1,
    ):
        (repository / name).write_text(content, encoding="utf-8")
        (cases / f"WU-{index:05d}.json").write_text(
            json.dumps(behavior_cases, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return repository, cases


def _medium_comment_filler(language: Language) -> str:
    prefix = "# " if language == "python" else "// "
    line = prefix + ("x" * 92) + "\n"
    repetitions = (_MEDIUM_COMMENT_BYTES_PER_FILE + len(line) - 1) // len(line)
    filler = line * repetitions
    assert len(filler.encode("utf-8")) >= _MEDIUM_COMMENT_BYTES_PER_FILE
    return filler


def _write_medium_repository_and_cases(
    root: Path,
    source_language: Language,
) -> tuple[Path, Path]:
    repository = root / "repository"
    cases = root / "cases"
    repository.mkdir()
    cases.mkdir()

    source_files = sorted((*_SOURCE_FILES[source_language], *_MEDIUM_EXTRA_SOURCE_FILES[source_language]))
    assert len(source_files) == 5
    filler = _medium_comment_filler(source_language)
    for index, (name, content) in enumerate(source_files, start=1):
        source = filler + content
        source_bytes = source.encode("utf-8")
        assert len(source_bytes) < _FILE_MAXIMUM_BYTES
        function_name = Path(name).stem.lower()
        behavior_cases = _MEDIUM_BEHAVIOR_CASES[function_name]
        (repository / name).write_bytes(source_bytes)
        (cases / f"WU-{index:05d}.json").write_text(
            json.dumps(behavior_cases, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return repository, cases


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _prefixed_sha256(content: bytes) -> str:
    return "sha256:" + _sha256(content)


def _relative_regular_file(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    assert relative
    assert not pure.is_absolute()
    assert ".." not in pure.parts
    assert "\\" not in relative
    assert pure.as_posix() == relative
    path = root.joinpath(*pure.parts)
    assert not path.is_symlink()
    assert path.is_file()
    return path


def _canonical_json_value(value: object) -> tuple[str, object]:
    if value is None:
        return ("null", None)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, int):
        return ("number", Decimal(value).normalize())
    if isinstance(value, float):
        assert math.isfinite(value)
        return ("number", Decimal(str(value)).normalize())
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return ("array", tuple(_canonical_json_value(item) for item in value))
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        return (
            "object",
            tuple(sorted((key, _canonical_json_value(item)) for key, item in value.items())),
        )
    raise AssertionError(f"non-JSON observation value: {type(value).__name__}")


def _semantic_observation_set(
    observations: object,
) -> set[tuple[int, str, tuple[str, object]]]:
    assert isinstance(observations, list)
    normalized: set[tuple[int, str, tuple[str, object]]] = set()
    for observation in observations:
        assert isinstance(observation, dict)
        case_id = observation.get("case_id")
        status = observation.get("status")
        assert isinstance(case_id, int)
        assert isinstance(status, str)
        normalized.add(
            (
                case_id,
                status,
                _canonical_json_value(observation.get("value")),
            )
        )
    assert len(normalized) == len(observations)
    return normalized


def _assert_batch_evidence_closure(
    output: Path,
    cases: Path,
    source_language: Language,
    target_language: Language,
    expected_unit_count: int,
) -> dict[str, Any]:
    batch_root = output / "batch"
    batch = cast(
        dict[str, Any],
        json.loads((batch_root / "batch-report.json").read_text(encoding="utf-8")),
    )
    assert batch["kind"] == "elmos.repository-batch-report"
    assert batch["status"] == "COMPLETE"
    assert batch["route_id"] == f"{source_language}-to-{target_language}"
    assert batch["source_language"] == source_language
    assert batch["target_language"] == target_language
    assert batch["work_unit_count"] == expected_unit_count
    assert batch["status_counts"] == {"PASSED": expected_unit_count}
    units = batch["units"]
    assert isinstance(units, list)
    expected_ids = {f"WU-{index:05d}" for index in range(1, expected_unit_count + 1)}
    assert {unit["id"] for unit in units} == expected_ids

    for unit in units:
        unit_id = unit["id"]
        assert unit["status"] == "PASSED"
        assert unit["evidence_path"] == f"units/{unit_id}/route-evidence.json"
        evidence_path = _relative_regular_file(batch_root, unit["evidence_path"])
        evidence_bytes = evidence_path.read_bytes()
        assert unit["evidence_sha256"] == _prefixed_sha256(evidence_bytes)
        evidence = json.loads(evidence_bytes)

        target_path = _relative_regular_file(batch_root / "units" / unit_id, unit["target_path"])
        target_bytes = target_path.read_bytes()
        assert unit["target_sha256"] == _prefixed_sha256(target_bytes)
        assert evidence["target"]["path"] == unit["target_path"]
        assert evidence["target"]["sha256"] == unit["target_sha256"]
        assert evidence["source"]["path"] == unit["source_path"]
        assert evidence["source"]["language"] == source_language
        assert evidence["target"]["language"] == target_language
        assert evidence["route"] == f"{source_language}-to-{target_language}"
        assert evidence["status"] == "PASSED_LOCAL_UNCERTIFIED"

        case_payload = json.loads((cases / f"{unit_id}.json").read_text(encoding="utf-8"))
        assert isinstance(case_payload, list)
        case_count = len(case_payload)
        assert case_count > 0
        assert unit["behavior_case_count"] == case_count
        assert evidence["behavior_case_count"] == case_count
        source_validation = evidence["source_validation"]
        target_validation = evidence["validation"]
        assert source_validation["status"] == "PASSED"
        assert target_validation["status"] == "PASSED"
        assert source_validation["case_count"] == case_count
        assert target_validation["case_count"] == case_count

        source_observations = _semantic_observation_set(source_validation["observations"])
        target_observations = _semantic_observation_set(target_validation["observations"])
        expected_observations = {
            (
                index,
                "RETURNED",
                _canonical_json_value(case["expected"]),
            )
            for index, case in enumerate(case_payload)
        }
        assert source_observations == target_observations == expected_observations
        assert evidence["external_certification_status"] == "NOT_RUN"
        assert evidence["certification_status"] == "EXPERIMENTAL"
    return batch


def _assert_assembly_closure(
    output: Path,
    batch: dict[str, Any],
    source_language: Language,
    target_language: Language,
    expected_unit_count: int,
) -> dict[str, Any]:
    assembled = output / "assembled"
    manifest = cast(
        dict[str, Any],
        json.loads((assembled / "assembly-manifest.json").read_text(encoding="utf-8")),
    )
    assert manifest["kind"] == "elmos.repository-assembly-report"
    assert manifest["status"] == "ASSEMBLED"
    assert manifest["route_id"] == f"{source_language}-to-{target_language}"
    assert manifest["source_language"] == source_language
    assert manifest["target_language"] == target_language
    assert manifest["batch_status"] == "COMPLETE"
    assert manifest["included_unit_count"] == expected_unit_count
    assert manifest["excluded_unit_count"] == 0
    assert manifest["excluded_units"] == []
    assert manifest["build_verification_status"] == "PASSED"
    assert manifest["build_verification"]["toolchain_language"] == target_language
    assert manifest["build_verification"]["toolchain_version"]
    assert manifest["build_verification"]["commands"]
    assert manifest["external_verification_status"] == "NOT_RUN"
    assert manifest["certification_status"] == "NOT_CERTIFIED"

    batch_units = {unit["id"]: unit for unit in batch["units"]}
    included_units = manifest["included_units"]
    assert {unit["id"] for unit in included_units} == set(batch_units)
    assembled_paths: set[str] = set()
    for included in included_units:
        unit = batch_units[included["id"]]
        assembled_path = included["assembled_path"]
        assert assembled_path not in assembled_paths
        assembled_paths.add(assembled_path)
        assert included["source_path"] == unit["source_path"]
        assert included["function_name"] == unit["function_name"]
        assert included["source_sha256"] == unit["checkpoint_identity"]["source_sha256"]
        assert included["target_sha256"] == unit["target_sha256"]

    expected_build_inputs = {
        *assembled_paths,
        *manifest["build_files"],
        *_ASSEMBLY_AUXILIARY_INPUTS.get(target_language, ()),
    }
    build_inputs = manifest["build_inputs"]
    assert manifest["build_input_count"] == len(build_inputs) == len(expected_build_inputs)
    assert [build_input["path"] for build_input in build_inputs] == sorted(expected_build_inputs)
    observed_build_inputs: dict[str, tuple[int, str]] = {}
    for build_input in build_inputs:
        relative = build_input["path"]
        assert relative not in observed_build_inputs
        content = _relative_regular_file(assembled, relative).read_bytes()
        binding = (len(content), _prefixed_sha256(content))
        assert build_input["bytes"] == binding[0]
        assert build_input["sha256"] == binding[1]
        observed_build_inputs[relative] = binding
    assert set(observed_build_inputs) == expected_build_inputs
    for included in included_units:
        assert observed_build_inputs[included["assembled_path"]] == (
            included["assembled_bytes"],
            included["assembled_sha256"],
        )
    return manifest


def _assert_artifact_closure(
    output: Path,
    report: dict[str, Any],
    assembly_manifest: dict[str, Any],
) -> None:
    manifest_path = output / ARTIFACT_MANIFEST_NAME
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["kind"] == "elmos.repository-migration-artifact-manifest"
    assert manifest["status"] == report["status"]
    assert manifest["route_id"] == report["route_id"]
    assert manifest["repository_complete"] == report["repository_complete"]
    assert manifest["repository_execution_status"] == report["repository_execution_status"]
    assert manifest["external_verification_status"] == "NOT_RUN"
    assert manifest["certification_status"] == "NOT_CERTIFIED"

    declared: dict[str, tuple[int, str]] = {}
    for entry in manifest["files"]:
        relative = entry["path"]
        assert relative not in declared
        content = _relative_regular_file(output, relative).read_bytes()
        binding = (len(content), _sha256(content))
        assert entry["bytes"] == binding[0]
        assert entry["sha256"] == binding[1]
        declared[relative] = binding
    controls = {
        ARTIFACT_NAME,
        f"{ARTIFACT_NAME}.tmp",
        ARTIFACT_MANIFEST_NAME,
        REPORT_NAME,
    }
    observed_paths = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.relative_to(output).as_posix() not in controls
    }
    assert set(declared) == observed_paths

    archive_path = output / ARTIFACT_NAME
    archive_bytes = archive_path.read_bytes()
    assert report["artifact"] == {
        "path": ARTIFACT_NAME,
        "bytes": len(archive_bytes),
        "sha256": _sha256(archive_bytes),
    }
    archive_bindings = {
        **declared,
        ARTIFACT_MANIFEST_NAME: (len(manifest_bytes), _sha256(manifest_bytes)),
    }
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        assert len(infos) == len({info.filename for info in infos})
        assert not any(info.is_dir() for info in infos)
        assert {info.filename for info in infos} == set(archive_bindings)
        for info in infos:
            content = archive.read(info)
            expected_bytes, expected_sha256 = archive_bindings[info.filename]
            assert info.file_size == expected_bytes == len(content)
            assert _sha256(content) == expected_sha256
        assert archive.read(ARTIFACT_MANIFEST_NAME) == manifest_bytes

        assembly_relative = "assembled/assembly-manifest.json"
        embedded_assembly_bytes = archive.read(assembly_relative)
        assert json.loads(embedded_assembly_bytes) == assembly_manifest
        assert archive_bindings[assembly_relative] == (
            len(embedded_assembly_bytes),
            _sha256(embedded_assembly_bytes),
        )
        for build_input in assembly_manifest["build_inputs"]:
            relative = f"assembled/{build_input['path']}"
            content = archive.read(relative)
            assert archive_bindings[relative] == (len(content), _sha256(content))
            assert build_input["bytes"] == len(content)
            assert build_input["sha256"] == _prefixed_sha256(content)


def test_directed_language_pair_matrix_contains_every_ordered_pair_once() -> None:
    assert len(SUPPORTED_LANGUAGES) == 9
    assert len(DIRECTED_LANGUAGE_PAIRS) == 72
    assert len(set(DIRECTED_LANGUAGE_PAIRS)) == 72
    assert set(DIRECTED_LANGUAGE_PAIRS) == {
        (source, target)
        for source in SUPPORTED_LANGUAGES
        for target in SUPPORTED_LANGUAGES
        if source != target
    }


def test_medium_language_ring_covers_every_source_and_target_once() -> None:
    assert len(MEDIUM_LANGUAGE_RING) == 9
    assert len(set(MEDIUM_LANGUAGE_RING)) == 9
    assert all(source != target for source, target in MEDIUM_LANGUAGE_RING)
    assert {source for source, _ in MEDIUM_LANGUAGE_RING} == set(SUPPORTED_LANGUAGES)
    assert {target for _, target in MEDIUM_LANGUAGE_RING} == set(SUPPORTED_LANGUAGES)


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    DIRECTED_LANGUAGE_PAIRS,
    ids=lambda language: language,
)
def test_repository_pipeline_converts_three_file_repository_for_every_directed_pair(
    tmp_path: Path,
    source_language: Language,
    target_language: Language,
) -> None:
    repository, cases = _write_repository_and_cases(tmp_path, source_language)
    output = tmp_path / "output"

    report = run_repository_pipeline(
        repository,
        f"local:functional-matrix/{source_language}-to-{target_language}",
        source_language,
        target_language,
        cases,
        output,
    )
    plan = json.loads((output / "repository-route-plan.json").read_text(encoding="utf-8"))

    assert plan["repository_scale"] == "small"
    assert plan["file_count"] == 3
    assert plan["source_file_count"] == 3
    assert 0 < plan["source_bytes"] <= _SMALL_MAXIMUM_BYTES
    assert len(plan["work_units"]) == 3
    assert all(0 < unit["source_bytes"] < _FILE_MAXIMUM_BYTES for unit in plan["work_units"])
    assert report["route_id"] == f"{source_language}-to-{target_language}"
    assert report["repository_scale"] == "small"
    assert report["work_unit_count"] == 3
    assert report["ready_count"] == 3
    assert report["unit_batch_status"] == "COMPLETE"
    assert report["status_counts"] == {"PASSED": 3}
    assert report["included_unit_count"] == 3
    assert report["build_verification"]["status"] == "PASSED"
    assert report["project_graph"]["repository_complete"] is True
    assert report["project_graph"]["completeness_status"] == "COMPLETE"
    assert report["project_graph"]["obligation_count"] == 0
    assert report["conversion_coverage"]["inventory_status"] == "PASSED"
    assert report["conversion_coverage"]["status"] == "PASSED"
    assert report["conversion_coverage"]["complete"] is True
    assert report["conversion_coverage"]["subject_count"] == 3
    assert report["conversion_coverage"]["status_counts"] == {
        "BLOCKED": 0,
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 3,
        "UNKNOWN": 0,
    }
    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["repository_execution_status"] == "PASSED_LOCAL"
    assert report["local_execution_evidence"] == "PASSED"
    assert report["independent_verification_status"] == "NOT_RUN"
    assert report["certification_status"] == "NOT_CERTIFIED"
    batch = _assert_batch_evidence_closure(output, cases, source_language, target_language, 3)
    assembly = _assert_assembly_closure(output, batch, source_language, target_language, 3)
    _assert_artifact_closure(output, report, assembly)


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    DIRECTED_LANGUAGE_PAIRS,
    ids=lambda language: language,
)
def test_repository_pipeline_converts_medium_repository_for_every_directed_pair(
    tmp_path: Path,
    source_language: Language,
    target_language: Language,
) -> None:
    repository, cases = _write_medium_repository_and_cases(tmp_path, source_language)
    output = tmp_path / "output"

    report = run_repository_pipeline(
        repository,
        f"local:medium-functional-matrix/{source_language}-to-{target_language}",
        source_language,
        target_language,
        cases,
        output,
    )
    plan = json.loads((output / "repository-route-plan.json").read_text(encoding="utf-8"))

    assert plan["repository_scale"] == "medium"
    assert plan["file_count"] == 5
    assert plan["source_file_count"] == 5
    assert _SMALL_MAXIMUM_BYTES < plan["source_bytes"] <= _MEDIUM_MAXIMUM_BYTES
    assert len(plan["work_units"]) == 5
    assert all(0 < unit["source_bytes"] < _FILE_MAXIMUM_BYTES for unit in plan["work_units"])
    assert report["route_id"] == f"{source_language}-to-{target_language}"
    assert report["repository_scale"] == "medium"
    assert report["work_unit_count"] == 5
    assert report["ready_count"] == 5
    assert report["unit_batch_status"] == "COMPLETE"
    assert report["status_counts"] == {"PASSED": 5}
    assert report["included_unit_count"] == 5
    assert report["build_verification"]["status"] == "PASSED"
    assert report["project_graph"]["repository_complete"] is True
    assert report["project_graph"]["completeness_status"] == "COMPLETE"
    assert report["project_graph"]["obligation_count"] == 0
    assert report["conversion_coverage"]["inventory_status"] == "PASSED"
    assert report["conversion_coverage"]["status"] == "PASSED"
    assert report["conversion_coverage"]["complete"] is True
    assert report["conversion_coverage"]["subject_count"] == 5
    assert report["conversion_coverage"]["status_counts"] == {
        "BLOCKED": 0,
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 5,
        "UNKNOWN": 0,
    }
    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["repository_execution_status"] == "PASSED_LOCAL"
    assert report["local_execution_evidence"] == "PASSED"
    assert report["independent_verification_status"] == "NOT_RUN"
    assert report["certification_status"] == "NOT_CERTIFIED"
    batch = _assert_batch_evidence_closure(output, cases, source_language, target_language, 5)
    assembly = _assert_assembly_closure(output, batch, source_language, target_language, 5)
    _assert_artifact_closure(output, report, assembly)
