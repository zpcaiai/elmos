"""Flutter/Dart whole-repository discovery, execution, and bundle closure."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from elmos_polyglot_route.assembly import verify_archived_assembly_closure
from elmos_polyglot_route.discovery import Verdict, discover_repository
from elmos_polyglot_route.models import REPOSITORY_SURFACE_LANGUAGES, RouteError
from elmos_polyglot_route.pipeline import run_repository_pipeline
from elmos_polyglot_route.repository import plan_repository


def _write_cases(cases: Path, values: list[list[dict[str, object]]]) -> None:
    cases.mkdir()
    for index, value in enumerate(values, start=1):
        (cases / f"WU-{index:05d}.json").write_text(
            json.dumps(value, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def test_flutter_repository_inventory_discovers_only_typed_pure_dart(
    tmp_path: Path,
) -> None:
    assert "flutter" in REPOSITORY_SURFACE_LANGUAGES
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "pure.dart").write_text(
        "int add(int left, int right) {\n  return left + right;\n}\n",
        encoding="utf-8",
    )
    (repository / "widget.dart").write_text(
        "import 'package:flutter/widgets.dart';\n\n"
        "class RouteScreen extends StatelessWidget {\n"
        "  const RouteScreen({super.key});\n"
        "  @override\n"
        "  Widget build(BuildContext context) => const SizedBox.shrink();\n"
        "}\n",
        encoding="utf-8",
    )
    (repository / "async.dart").write_text(
        "Future<int> delayed(int value) async {\n  return value;\n}\n",
        encoding="utf-8",
    )
    (repository / "effect.dart").write_text(
        "int printAndReturn(int value) {\n  print(value);\n  return value;\n}\n",
        encoding="utf-8",
    )

    plan = plan_repository(repository, "local:flutter-discovery", "flutter", "python")
    assert plan["file_count"] == 4
    assert plan["source_file_count"] == 4
    assert plan["language_counts"]["flutter"] == 4
    assert sum(plan["language_counts"].values()) == 4

    discovery = discover_repository(plan, repository)
    assert discovery["ready_count"] == 1
    assert discovery["module_inventory_count"] == 4
    assert discovery["module_inventory_status_counts"] == {
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 4,
    }
    ready = [result for result in discovery["results"] if result["verdict"] == Verdict.READY]
    assert [(result["source_path"], result["function_name"]) for result in ready] == [
        ("pure.dart", "add")
    ]
    rejected = [
        result
        for result in discovery["results"]
        if result["source_path"] in {"widget.dart", "async.dart", "effect.dart"}
    ]
    assert rejected
    assert {result["source_path"] for result in rejected} == {
        "async.dart",
        "effect.dart",
        "widget.dart",
    }
    assert all(result["verdict"] == Verdict.UNSUPPORTED for result in rejected)
    assert all(
        result["blocker_code"] == "NATIVE_MODULE_DECLARATION_CONVERSION_UNCOVERED"
        for result in rejected
    )


def test_flutter_source_repository_runs_two_files_and_closes_to_python(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "add.dart").write_text(
        "int add(int left, int right) {\n  return left + right;\n}\n",
        encoding="utf-8",
    )
    (repository / "multiply.dart").write_text(
        "int multiply(int left, int right) {\n  return left * right;\n}\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    _write_cases(
        cases,
        [
            [{"args": [2, 3], "expected": 5}, {"args": [-4, 1], "expected": -3}],
            [{"args": [3, 4], "expected": 12}, {"args": [-2, 5], "expected": -10}],
        ],
    )

    report = run_repository_pipeline(
        repository,
        "local:flutter-two-file-source",
        "flutter",
        "python",
        cases,
        tmp_path / "output",
    )

    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["repository_execution_status"] == "PASSED_LOCAL"
    assert report["work_unit_count"] == 2
    assert report["included_unit_count"] == 2
    assert report["build_verification"]["status"] == "PASSED"
    assert report["build_verification"]["toolchain"]["language"] == "python"
    assert report["certification_status"] == "NOT_CERTIFIED"


def test_flutter_target_repository_analyzes_compiles_and_runs_pure_dart_kernel(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "add.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left + right\n",
        encoding="utf-8",
    )
    (repository / "multiply.py").write_text(
        "def multiply(left: int, right: int) -> int:\n    return left * right\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    _write_cases(
        cases,
        [
            [{"args": [2, 3], "expected": 5}, {"args": [-4, 1], "expected": -3}],
            [{"args": [3, 4], "expected": 12}, {"args": [-2, 5], "expected": -10}],
        ],
    )
    output = tmp_path / "output"

    report = run_repository_pipeline(
        repository,
        "local:flutter-two-file-target",
        "python",
        "flutter",
        cases,
        output,
    )

    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["repository_execution_status"] == "PASSED_LOCAL"
    assert report["work_unit_count"] == 2
    assert report["included_unit_count"] == 2
    assert report["build_verification"]["status"] == "PASSED"
    assert report["build_verification"]["toolchain"]["language"] == "flutter"
    assert report["build_verification"]["toolchain"]["version"] == (
        "Flutter 3.44.1 / Dart 3.12.1"
    )
    assert report["certification_status"] == "NOT_CERTIFIED"

    assembled = output / "assembled"
    manifest = json.loads(
        (assembled / "assembly-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["build_files"] == [
        "pubspec.yaml",
        "analysis_options.yaml",
        ".dart_tool/package_config.json",
    ]
    assert manifest["build_verification_status"] == "PASSED"
    assert manifest["included_unit_count"] == 2
    build_receipt = manifest["build_verification"][
        "flutter_build_toolchain_receipt"
    ]
    assert build_receipt["kind"] == "elmos.flutter-dart-build-toolchain-receipt"
    assert set(build_receipt["trees"]) == {"dart_sdk"}
    build_commands = [
        record["command"] for record in manifest["build_verification"]["commands"]
    ]
    for command in build_commands:
        assert command[0].endswith("/dart")
        assert not any("flutter_tools.snapshot" in part for part in command)
    assert build_commands[2][1:] == [
        "--packages=.dart_tool/package_config.json",
        "build/elmos_repository.dill",
    ]
    assert (assembled / "lib" / "main.dart").is_file()
    assert len(list(assembled.glob("lib/generated/*/migrated.dart"))) == 2
    pubspec = (assembled / "pubspec.yaml").read_text(encoding="utf-8")
    assert "dependencies: {}" in pubspec
    assert "sdk: flutter" not in pubspec
    package_config = json.loads(
        (assembled / ".dart_tool" / "package_config.json").read_text(encoding="utf-8")
    )
    assert package_config == {
        "configVersion": 2,
        "packages": [
            {
                "name": "elmos_polyglot_migrated_flutter",
                "rootUri": "../",
                "packageUri": "lib/",
                "languageVersion": "3.12",
            }
        ],
    }
    assert "include:" not in (
        assembled / "analysis_options.yaml"
    ).read_text(encoding="utf-8")
    kernel = assembled / "build" / "elmos_repository.dill"
    assert kernel.is_file() and kernel.stat().st_size > 0
    compiled = manifest["build_verification"]["flutter_compiled_artifact"]
    assert compiled["path"] == "build/elmos_repository.dill"
    assert compiled["bytes"] == kernel.stat().st_size
    assert compiled["sha256"].startswith("sha256:")

    archived_artifact = "assembled/build/elmos_repository.dill"
    with ZipFile(output / report["artifact"]["path"]) as archive:
        names = archive.namelist()
        manifest_bytes = archive.read("assembled/assembly-manifest.json")
        with pytest.raises(
            RouteError,
            match="ASSEMBLY_ARCHIVE_FLUTTER_COMPILED_ARTIFACT_MISSING",
        ):
            verify_archived_assembly_closure(
                manifest_bytes,
                "flutter",
                [name for name in names if name != archived_artifact],
                archive.read,
            )

        def tampered_read(name: str) -> bytes:
            if name == archived_artifact:
                return b"tampered-kernel"
            return archive.read(name)

        with pytest.raises(
            RouteError,
            match="ASSEMBLY_ARCHIVE_FLUTTER_COMPILED_ARTIFACT_DRIFTED",
        ):
            verify_archived_assembly_closure(
                manifest_bytes,
                "flutter",
                names,
                tampered_read,
            )
