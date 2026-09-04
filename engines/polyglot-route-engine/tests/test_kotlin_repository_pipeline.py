"""Kotlin whole-repository inventory, conversion, assembly, and JVM closure."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import cast

import pytest

from elmos_polyglot_route import assembly as assembly_module
from elmos_polyglot_route.discovery import Verdict, discover_repository
from elmos_polyglot_route.models import REPOSITORY_SURFACE_LANGUAGES, RouteError
from elmos_polyglot_route.pipeline import run_repository_pipeline
from elmos_polyglot_route.project_graph import build_project_graph
from elmos_polyglot_route.repository import plan_repository
from elmos_polyglot_route.source_analyzer import inventory_module
from elmos_polyglot_route.toolchains import ExactToolchain, exact_toolchain, sanitized_subprocess_env
from elmos_polyglot_route.validation import _kotlin_jvm_bin


def _write_cases(cases: Path, values: list[list[dict[str, object]]]) -> None:
    cases.mkdir()
    for index, value in enumerate(values, start=1):
        (cases / f"WU-{index:05d}.json").write_text(
            json.dumps(value, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _run_exact_kotlin(
    command: list[str],
    cwd: Path,
    scratch: Path,
    toolchain: ExactToolchain,
) -> subprocess.CompletedProcess[str]:
    home = scratch / "home"
    temporary = scratch / "tmp"
    home.mkdir(parents=True)
    temporary.mkdir()
    assert toolchain.auxiliary is not None
    environment = sanitized_subprocess_env(
        home=home,
        temp_dir=temporary,
        executable_dirs=(
            _kotlin_jvm_bin(toolchain.profile),
            Path(toolchain.executable).resolve().parent,
            Path(toolchain.auxiliary).resolve().parent,
        ),
    )
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )


def _assert_process_passed(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0, f"stdout={completed.stdout[-2_000:]!r}\nstderr={completed.stderr[-2_000:]!r}"


def test_kotlin_repository_inventory_uses_kt_and_keeps_kts_fail_closed(
    tmp_path: Path,
) -> None:
    assert "kotlin" in REPOSITORY_SURFACE_LANGUAGES
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "pure.kt").write_text(
        "fun add(left: Long, right: Long): Long {\n    return left + right\n}\n",
        encoding="utf-8",
    )
    (repository / "task.kts").write_text('println("side effect")\n', encoding="utf-8")
    (repository / "build.gradle.kts").write_text(
        'plugins { kotlin("jvm") version "2.2.20" }\n',
        encoding="utf-8",
    )

    plan = plan_repository(repository, "local:kotlin-inventory", "kotlin", "python")
    assert plan["file_count"] == 1
    assert plan["source_file_count"] == 1
    assert plan["language_counts"]["kotlin"] == 1
    assert [unit["source_path"] for unit in plan["work_units"]] == ["pure.kt"]

    discovery = discover_repository(plan, repository)
    assert discovery["ready_count"] == 1
    assert discovery["module_inventory_count"] == 1
    assert discovery["module_inventory_status_counts"] == {
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 1,
    }
    inventory = discovery["module_inventories"][0]
    assert inventory["analyzer"] == "kotlin-compiler PSI"
    assert inventory["analyzer_version"] == "2.2.20"
    assert inventory["subjects"][0]["qualified_name"] == "add"
    public_inventory = inventory_module(repository / "pure.kt", "kotlin")
    assert public_inventory["source_language"] == "kotlin"
    assert public_inventory["enumeration_status"] == inventory["enumeration_status"]
    assert public_inventory["analyzer"] == inventory["analyzer"]
    assert public_inventory["analyzer_version"] == inventory["analyzer_version"]
    assert (
        public_inventory["subjects"][0]["qualified_name"]
        == inventory["subjects"][0]["qualified_name"]
    )

    graph = build_project_graph(repository, "local:kotlin-inventory", discovery)
    assert graph["repository_complete"] is False
    diagnostics = cast(list[dict[str, object]], graph["diagnostic_obligations"])
    diagnostic_codes = {str(diagnostic["code"]) for diagnostic in diagnostics}
    assert "FILE_CLASSIFICATION_UNKNOWN" in diagnostic_codes
    assert "BUILD_DESCRIPTOR_MIGRATION_NOT_RUN" in diagnostic_codes

    scripts_only = tmp_path / "scripts-only"
    scripts_only.mkdir()
    (scripts_only / "task.kts").write_text('println("not a module")\n', encoding="utf-8")
    with pytest.raises(RouteError, match=r"^NO_SOURCE_FILES:kotlin$"):
        plan_repository(scripts_only, "local:kotlin-scripts-only", "kotlin", "python")


def test_kotlin_module_obligation_blocks_repository_completion(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "mixed.kt").write_text(
        "val externalState: Long = 1L\n\nfun add(left: Long, right: Long): Long {\n    return left + right\n}\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    _write_cases(cases, [[{"args": [2, 3], "expected": 5}]])

    plan = plan_repository(repository, "local:kotlin-obligation", "kotlin", "python")
    discovery = discover_repository(plan, repository)
    assert [item["verdict"] for item in discovery["results"]] == [
        Verdict.READY,
        Verdict.UNSUPPORTED,
    ]
    assert discovery["results"][1]["blocker_code"] == ("NATIVE_MODULE_DECLARATION_CONVERSION_UNCOVERED")

    report = run_repository_pipeline(
        repository,
        "local:kotlin-obligation",
        "kotlin",
        "python",
        cases,
        tmp_path / "output",
    )
    assert report["status"] == "PARTIAL"
    assert report["repository_complete"] is False
    assert report["repository_execution_status"] == "LIMITED"
    assert report["certification_status"] == "NOT_CERTIFIED"
    assert report["status_counts"] == {
        "PASSED": 1,
        "SKIPPED_NOT_READY": 1,
    }


def test_kotlin_source_repository_runs_two_files_and_closes_to_python(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Add.kt").write_text(
        "fun add(left: Long, right: Long): Long {\n    return left + right\n}\n",
        encoding="utf-8",
    )
    (repository / "Multiply.kt").write_text(
        "fun multiply(left: Long, right: Long): Long {\n    return left * right\n}\n",
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

    # Establish a real original multi-file Kotlin/JVM baseline independently
    # from the route's per-function validation harnesses.
    toolchain = exact_toolchain("kotlin")
    runner = repository / "RepositoryRunner.kt"
    runner.write_text(
        "fun main() {\n"
        "    check(add(2L, 3L) == 5L)\n"
        "    check(multiply(3L, 4L) == 12L)\n"
        '    println("KOTLIN_SOURCE_MULTI_FILE_OK")\n'
        "}\n",
        encoding="utf-8",
    )
    source_classes = tmp_path / "source-classes"
    source_classes.mkdir()
    compiled = _run_exact_kotlin(
        [
            toolchain.executable,
            "-Werror",
            "-jvm-target",
            "21",
            "-d",
            str(source_classes),
            str(repository / "Add.kt"),
            str(repository / "Multiply.kt"),
            str(runner),
        ],
        repository,
        tmp_path / "source-compile-scratch",
        toolchain,
    )
    _assert_process_passed(compiled)
    assert toolchain.auxiliary is not None
    executed = _run_exact_kotlin(
        [toolchain.auxiliary, "-classpath", str(source_classes), "RepositoryRunnerKt"],
        repository,
        tmp_path / "source-runtime-scratch",
        toolchain,
    )
    _assert_process_passed(executed)
    assert executed.stdout.strip() == "KOTLIN_SOURCE_MULTI_FILE_OK"

    # The baseline runner is evidence-only and not part of the migration input
    # inventory; remove it before the content-addressed repository scan.
    runner.unlink()
    report = run_repository_pipeline(
        repository,
        "local:kotlin-two-file-source",
        "kotlin",
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


def test_kotlin_target_repository_assembles_compiles_and_runs_two_files(
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
        "local:kotlin-two-file-target",
        "python",
        "kotlin",
        cases,
        output,
    )
    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["work_unit_count"] == 2
    assert report["included_unit_count"] == 2
    assert report["build_verification"]["status"] == "PASSED"
    assert report["build_verification"]["toolchain"]["language"] == "kotlin"
    assert report["build_verification"]["toolchain"]["version"] == ("kotlinc-jvm 2.2.20 (JRE 21.0.11)")
    assert report["certification_status"] == "NOT_CERTIFIED"

    assembled = output / "assembled"
    manifest = json.loads((assembled / "assembly-manifest.json").read_text(encoding="utf-8"))
    assert manifest["build_files"] == ["kotlinc.args"]
    assert manifest["build_verification_status"] == "PASSED"
    assert manifest["included_unit_count"] == 2
    kotlin_identity = manifest["build_verification"]["kotlin_exact_toolchain"]
    assert kotlin_identity["version"] == "kotlinc-jvm 2.2.20 (JRE 21.0.11)"
    assert any(
        value.startswith("kotlin-compiler-jar-sha256=")
        for value in kotlin_identity["profile"]
    )
    assert any(
        value.startswith("kotlin-jvm-release-sha256=")
        for value in kotlin_identity["profile"]
    )
    assert manifest["build_verification"][
        "kotlin_exact_toolchain_sha256"
    ].startswith("sha256:")
    tampered_manifest = json.loads(json.dumps(manifest))
    tampered_manifest["build_verification"]["kotlin_exact_toolchain"][
        "profile"
    ][0] += "-tampered"
    with pytest.raises(
        RouteError,
        match="^ASSEMBLY_KOTLIN_BUILD_TOOLCHAIN_IDENTITY_DRIFT$",
    ):
        assembly_module._validate_assembly_manifest(
            tampered_manifest,
            "kotlin",
            assembled,
            require_build_passed=True,
        )
    argument_lines = (assembled / "kotlinc.args").read_text(encoding="utf-8").splitlines()
    assert argument_lines[:9] == [
        "-Werror",
        "-language-version",
        "2.2",
        "-api-version",
        "2.2",
        "-jvm-target",
        "21",
        "-d",
        "build/classes",
    ]
    assert argument_lines[9:] == sorted(str(unit["assembled_path"]) for unit in manifest["included_units"])

    runner = tmp_path / "TargetRunner.kt"
    calls = []
    expected_by_source = {"add.py": ("2L, 3L", "5L"), "multiply.py": ("3L, 4L", "12L")}
    for unit in manifest["included_units"]:
        arguments, expected = expected_by_source[str(unit["source_path"])]
        calls.append(
            f"    check(elmos.generated.{unit['namespace']}.{unit['target_function_name']}({arguments}) == {expected})"
        )
    runner.write_text(
        "fun main() {\n" + "\n".join(calls) + '\n    println("KOTLIN_TARGET_MULTI_FILE_OK")\n}\n',
        encoding="utf-8",
    )

    toolchain = exact_toolchain("kotlin")
    runner_classes = tmp_path / "runner-classes"
    runner_classes.mkdir()
    compiled = _run_exact_kotlin(
        [
            toolchain.executable,
            "-Werror",
            "-jvm-target",
            "21",
            "-classpath",
            str(assembled / "build" / "classes"),
            "-d",
            str(runner_classes),
            str(runner),
        ],
        tmp_path,
        tmp_path / "target-runner-compile-scratch",
        toolchain,
    )
    _assert_process_passed(compiled)
    assert toolchain.auxiliary is not None
    classpath = os.pathsep.join([str(assembled / "build" / "classes"), str(runner_classes)])
    executed = _run_exact_kotlin(
        [toolchain.auxiliary, "-classpath", classpath, "TargetRunnerKt"],
        tmp_path,
        tmp_path / "target-runtime-scratch",
        toolchain,
    )
    _assert_process_passed(executed)
    assert executed.stdout.strip() == "KOTLIN_TARGET_MULTI_FILE_OK"
