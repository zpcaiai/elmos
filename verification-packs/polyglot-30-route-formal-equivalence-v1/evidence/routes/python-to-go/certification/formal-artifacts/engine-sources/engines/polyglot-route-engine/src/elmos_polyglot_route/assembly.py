"""Assemble a batch report's PASSED units into one buildable target-language project.

The repository-scope pipeline (`repository.py` -> `discovery.py` -> `batch.py`)
proves each work unit in isolation: one function, one fixed-name emitted file
(`Migrated.java` / `Migrated.cs` / `migrated.py` / `migrated.ts`), one harness,
one exact-toolchain verification run. None of that is a project a human or a
CI pipeline could actually build, because every PASSED unit reuses the same
file name and, for Java/C#, the same class name -- combining two units
verbatim would collide on the first duplicate.

This module closes that gap for a single already-run batch report:

1. `assemble_project` places each PASSED unit's already-emitted source under a
   per-unit namespace so nothing collides, writes a real per-language build
   manifest, and records exactly which units were included and which were
   excluded (and why). It never re-derives or re-emits source -- it only
   relocates bytes the batch already produced, re-verifying each unit's
   recorded sha256 first (defense in depth against a tampered or stale batch
   output directory).
2. `verify_assembled_project` runs a real whole-project compile/build check
   against the assembled project using the same exact-toolchain contract the
   per-unit harness in `validation.py` already enforces, and folds the result
   back into the manifest on disk.

Both functions fail closed: a missing unit source, a sha256 mismatch, a path
that escapes its unit directory, or a failed compiler invocation raises
`RouteError` rather than producing a project that looks assembled but is not
actually attributable to proven work.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .assembly_deployment_guidance import render_assembly_deployment_guidance
from .models import Language, RouteError
from .toolchains import exact_toolchain
from .validation import safe_output

SCHEMA_VERSION = "1.0.0"
MANIFEST_NAME = "assembly-manifest.json"

_UNIT_ID_PATTERN = re.compile(r"^WU-[0-9]{5}$")

_BUILD_FILES: dict[Language, tuple[str, ...]] = {
    "java": ("pom.xml",),
    "csharp": ("polyglot-migrated-library.csproj",),
    "python": ("pyproject.toml",),
    "typescript": ("package.json", "tsconfig.json"),
}


def _safe_unit_id(unit_id: str) -> str:
    if not _UNIT_ID_PATTERN.fullmatch(unit_id):
        raise RouteError(f"ASSEMBLY_UNIT_ID_UNSAFE:{unit_id}")
    return unit_id


def _namespace(unit_id: str) -> str:
    # "WU-00001" -> "wu00001". Stable and filesystem/identifier-safe. Discovery
    # assigns each unit a unique sequential id (repository.py's plan_repository),
    # so namespaces derived from it are collision-free by construction.
    return unit_id.lower().replace("-", "")


def _read_verified_unit_source(batch_output: Path, unit: dict[str, Any]) -> str:
    """Read one PASSED unit's already-emitted file, re-verifying its recorded sha256.

    This is defense in depth, not the primary trust boundary: `run_batch`
    already proved the content by compiling and executing it. Re-hashing here
    only guards against the batch output directory having been altered or
    gone stale between the batch run and this assembly run.
    """
    unit_id = _safe_unit_id(str(unit.get("id", "")))
    target_path = str(unit.get("target_path", ""))
    if not target_path or "/" in target_path or "\\" in target_path:
        raise RouteError(f"ASSEMBLY_UNIT_TARGET_PATH_INVALID:{unit_id}")
    unit_directory = (batch_output / "units" / unit_id).resolve()
    source_file = (unit_directory / target_path).resolve()
    if (
        unit_directory.is_symlink()
        or source_file.is_symlink()
        or source_file.parent != unit_directory
        or not source_file.is_file()
    ):
        raise RouteError(f"ASSEMBLY_UNIT_SOURCE_MISSING:{unit_id}")
    content = source_file.read_text(encoding="utf-8")
    expected = unit.get("target_sha256")
    if expected:
        observed = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        if observed != expected:
            raise RouteError(f"ASSEMBLY_UNIT_CONTENT_DRIFTED:{unit_id}")
    return content


def _place_java(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/main/java/elmos/generated/{namespace}/Migrated.java"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"package elmos.generated.{namespace};\n\n{content}", encoding="utf-8")
    return relative


def _place_csharp(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/Units/{namespace}/Migrated.cs"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    pascal_namespace = namespace.capitalize()
    target.write_text(f"namespace Elmos.Generated.{pascal_namespace};\n\n{content}", encoding="utf-8")
    return relative


def _place_python(destination: Path, namespace: str, content: str) -> str:
    package_directory = destination / "src" / "elmos_generated"
    package_directory.mkdir(parents=True, exist_ok=True)
    init_file = package_directory / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")
    relative = f"src/elmos_generated/{namespace}.py"
    (destination / relative).write_text(content, encoding="utf-8")
    return relative


def _place_typescript(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/generated/{namespace}.ts"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative


_PLACERS = {
    "java": _place_java,
    "csharp": _place_csharp,
    "python": _place_python,
    "typescript": _place_typescript,
}


def _write_build_files(destination: Path, target_language: Language, included_unit_count: int) -> None:
    if target_language == "java":
        (destination / "pom.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
            "    <modelVersion>4.0.0</modelVersion>\n"
            "    <groupId>io.elmos.generated</groupId>\n"
            "    <artifactId>polyglot-migrated-library</artifactId>\n"
            "    <version>0.0.0-experimental</version>\n"
            "    <packaging>jar</packaging>\n"
            "    <properties>\n"
            "        <maven.compiler.release>21</maven.compiler.release>\n"
            "        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>\n"
            "    </properties>\n"
            "</project>\n",
            encoding="utf-8",
        )
    elif target_language == "csharp":
        (destination / "polyglot-migrated-library.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk">\n'
            "  <PropertyGroup>\n"
            "    <TargetFramework>net10.0</TargetFramework>\n"
            "    <ImplicitUsings>enable</ImplicitUsings>\n"
            "    <Nullable>enable</Nullable>\n"
            "    <AssemblyName>Elmos.Generated.PolyglotMigratedLibrary</AssemblyName>\n"
            "    <RootNamespace>Elmos.Generated</RootNamespace>\n"
            "    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>\n"
            "  </PropertyGroup>\n"
            "</Project>\n",
            encoding="utf-8",
        )
    elif target_language == "python":
        (destination / "pyproject.toml").write_text(
            "[project]\n"
            'name = "elmos-polyglot-migrated-library"\n'
            'version = "0.0.0"\n'
            'requires-python = ">=3.12"\n'
            "\n"
            "[build-system]\n"
            'requires = ["setuptools>=68"]\n'
            'build-backend = "setuptools.build_meta"\n'
            "\n"
            "[tool.setuptools.packages.find]\n"
            'where = ["src"]\n',
            encoding="utf-8",
        )
    else:
        (destination / "package.json").write_text(
            json.dumps(
                {
                    "name": "elmos-polyglot-migrated-library",
                    "version": "0.0.0-experimental",
                    "private": True,
                    "type": "module",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (destination / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2022",
                        "module": "NodeNext",
                        "moduleResolution": "NodeNext",
                        "strict": True,
                        "declaration": True,
                        "outDir": "dist",
                        "rootDir": "src",
                    },
                    "include": ["src/**/*.ts"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    del included_unit_count  # reserved for future per-count build tuning


def assemble_project(
    batch_report: dict[str, Any],
    batch_output: Path,
    destination: Path,
) -> dict[str, Any]:
    """Assemble a batch report's PASSED units into one buildable project skeleton.

    `destination` must not already exist (see `validation.safe_output`); this
    function only ever creates a fresh assembly, never merges into one.
    """
    if batch_report.get("kind") != "elmos.repository-batch-report":
        raise RouteError("ASSEMBLY_BATCH_REPORT_KIND_INVALID")
    target_language = batch_report.get("target_language")
    if target_language not in _PLACERS:
        raise RouteError("ASSEMBLY_UNSUPPORTED_TARGET_LANGUAGE")
    units = batch_report.get("units")
    if not isinstance(units, list) or not units:
        raise RouteError("ASSEMBLY_BATCH_REPORT_UNITS_REQUIRED")
    if batch_output.is_symlink() or not batch_output.is_dir():
        raise RouteError("ASSEMBLY_BATCH_OUTPUT_DIRECTORY_INVALID")

    destination = safe_output(destination)
    if destination.exists():
        raise RouteError("ASSEMBLY_DESTINATION_ALREADY_EXISTS")
    destination.mkdir(parents=True)

    placer = _PLACERS[target_language]
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for unit in units:
        unit_id = str(unit.get("id", ""))
        if unit_id in seen_ids:
            raise RouteError(f"ASSEMBLY_DUPLICATE_UNIT_ID:{unit_id}")
        seen_ids.add(unit_id)
        if unit.get("status") != "PASSED":
            excluded.append(
                {
                    "id": unit_id,
                    "status": unit.get("status"),
                    "reason": unit.get("reason", "Unit did not reach PASSED status in the batch run."),
                }
            )
            continue
        namespace = _namespace(_safe_unit_id(unit_id))
        content = _read_verified_unit_source(batch_output, unit)
        relative_path = placer(destination, namespace, content)
        included.append(
            {
                "id": unit_id,
                "namespace": namespace,
                "source_path": unit.get("source_path"),
                "function_name": unit.get("function_name"),
                "assembled_path": relative_path,
                "source_sha256": unit.get("target_sha256"),
            }
        )

    if not included:
        raise RouteError("ASSEMBLY_NO_PASSED_UNITS_TO_ASSEMBLE")

    _write_build_files(destination, target_language, len(included))

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-assembly-report",
        "status": "ASSEMBLED",
        "repository_ref": batch_report.get("repository_ref"),
        "snapshot_sha256": batch_report.get("snapshot_sha256"),
        "route_id": batch_report.get("route_id"),
        "source_language": batch_report.get("source_language"),
        "target_language": target_language,
        "batch_status": batch_report.get("status"),
        "build_files": list(_BUILD_FILES[target_language]),
        "included_unit_count": len(included),
        "excluded_unit_count": len(excluded),
        "included_units": included,
        "excluded_units": excluded,
        "build_verification_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Assembly only relocates already-emitted, already-verified per-unit source; "
            "it performs no additional translation.",
            "Each unit keeps its own namespace/module; units are never merged into a shared "
            "namespace, because cross-unit name collisions (e.g. two files defining a "
            "same-named function with different behavior) are not resolved at the semantic level.",
            "A batch_status of PARTIAL means the source repository was not fully migrated; "
            "this project covers only the included units listed above, not the whole repository.",
            "build_verification_status reflects a real whole-project compile/build invocation, "
            "not a re-run of per-unit behavior cases; those already passed during the batch run "
            "for every included unit, and assembly does not repeat them.",
            "build_verification_status is NOT_RUN until verify_assembled_project is executed.",
            "External verification and certification remain NOT_RUN / NOT_CERTIFIED.",
        ],
    }
    _write_manifest(destination, manifest)
    return manifest


def _write_manifest(destination: Path, manifest: dict[str, Any]) -> None:
    (destination / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run(command: list[str], cwd: Path, *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["NO_COLOR"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-4_000:]
        raise RouteError(f"ASSEMBLY_BUILD_VERIFICATION_FAILED:{command[0]}:{detail}")
    return completed


def verify_assembled_project(target_language: Language, destination: Path) -> dict[str, Any]:
    """Run a real whole-project compile/build check against an assembled project.

    Uses the same exact-toolchain contract as the per-unit harness in
    `validation.py`. This is what actually proves the assembled project is
    buildable as a whole, catching cross-unit issues (e.g. a shared build
    file rejecting one unit's construct) that per-unit validation cannot see.

    On success, `assembly-manifest.json` is rewritten with
    `build_verification_status: "PASSED"` and the command log. On failure,
    `RouteError` propagates and the manifest on disk is left untouched --
    it is not rewritten to a failure state, because "NOT_RUN" and "the last
    attempt failed" both correctly mean "do not treat this as buildable,"
    and leaving the file alone avoids ever writing a manifest that claims
    more than what actually happened.
    """
    destination = destination.expanduser().resolve()
    manifest_path = destination / MANIFEST_NAME
    if not manifest_path.is_file():
        raise RouteError("ASSEMBLY_MANIFEST_MISSING")
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("target_language") != target_language:
        raise RouteError("ASSEMBLY_MANIFEST_LANGUAGE_MISMATCH")

    toolchain = exact_toolchain(target_language)
    commands: list[dict[str, Any]] = []

    if target_language == "java":
        sources = sorted(str(path) for path in destination.glob("src/main/java/**/*.java"))
        if not sources:
            raise RouteError("ASSEMBLY_NO_JAVA_SOURCES_FOUND")
        build_directory = destination / "build" / "classes"
        build_directory.mkdir(parents=True, exist_ok=True)
        assert toolchain.auxiliary is not None
        command = [toolchain.auxiliary, "-d", str(build_directory), *sources]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "python":
        source_directory = destination / "src"
        command = [toolchain.executable, "-m", "compileall", "-q", str(source_directory)]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "csharp":
        command = [toolchain.executable, "build", "polyglot-migrated-library.csproj", "-c", "Release"]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    else:
        assert toolchain.auxiliary is not None
        command = [toolchain.auxiliary, "-p", "tsconfig.json"]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})

    manifest["build_verification_status"] = "PASSED"
    manifest["build_verification"] = {
        "toolchain_language": toolchain.language,
        "toolchain_version": toolchain.version,
        "commands": commands,
    }
    _write_manifest(destination, manifest)
    write_assembly_deployment_guidance(destination, target_language, int(manifest["included_unit_count"]))
    return manifest


def write_assembly_deployment_guidance(
    destination: Path,
    target_language: Language,
    included_unit_count: int,
) -> list[str]:
    """Write local-run + cloud-publishing guidance for a build-verified assembly.

    Deliberately only called from `verify_assembled_project` after a real
    build passes -- guidance for a project that has not been shown to build
    would document steps for an artifact that does not yet demonstrably exist.
    """
    files = render_assembly_deployment_guidance(target_language, included_unit_count)
    written: list[str] = []
    for relative_path, content in files.items():
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(relative_path)
    return written
