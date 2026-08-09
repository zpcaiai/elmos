#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIRECTORY))
sys.path.insert(
    0,
    str(DEFAULT_REPOSITORY_ROOT / "engines" / "polyglot-route-engine" / "src"),
)

from route_sets import (  # noqa: E402
    CORE_LANGUAGES,
    CORE_ROUTE_KEYS,
    EVIDENCED_ROUTE_KEYS,
    EXACT_ROUTE_SETS,
    SPECIALIZED_LANGUAGES,
    SPECIALIZED_ROUTE_KEYS,
    split_route_key,
)

from elmos_polyglot_route.emitter import _SWIFT_HELPERS  # noqa: E402
from elmos_polyglot_route.engine import migrate, migrate_module  # noqa: E402
from elmos_polyglot_route.models import Language, RouteError, SemanticIR  # noqa: E402
from elmos_polyglot_route.native import analyze  # noqa: E402

B16_LANGUAGES: tuple[Language, ...] = CORE_LANGUAGES  # type: ignore[assignment]
SPECIALIZED_INPUT_DOMAIN = "canonical-finite-no-error-input-domain"
SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC = "BLOCKED_NOT_EQUIVALENTLY_MODELED"

VERSIONS = {
    "java": ["Java 21.0.11", "JDK Compiler Tree API"],
    "python": ["Python 3.12.12", "CPython AST"],
    "csharp": ["C# 14", ".NET SDK 10.0.301", "Roslyn 5.6.0"],
    "typescript": ["TypeScript 5.9.2", "Node.js 26.0.0"],
    "go": ["Go 1.25.0", "go/parser AST"],
    "rust": ["Rust 1.89.0", "syn 2.0.119"],
    "cpp": [
        "C++20",
        "Apple clang version 21.0.0 (clang-2100.1.1.101)",
        "arm64-apple-darwin25.6.0",
    ],
    "objc": [
        "Objective-C",
        "Apple clang version 21.0.0 (clang-2100.1.1.101)",
        "arm64-apple-darwin25.6.0",
        "Foundation",
    ],
    "swift": [
        "Apple Swift 6.3.3 (swiftlang-6.3.3.1.3 clang-2100.1.1.101)",
        "arm64-apple-macosx26.0",
        "SwiftSyntax 600.0.1",
    ],
}
ENGINE_PATHS = {
    "java": "engines/polyglot-route-engine/native/java/Analyzer.java",
    "python": "engines/polyglot-route-engine/src/elmos_polyglot_route/python_analyzer.py",
    "csharp": "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli",
    "typescript": "engines/frontend-client-engine/src/polyglot.ts",
    "go": "engines/polyglot-route-engine/native/go/analyzer.go",
    "rust": "engines/polyglot-route-engine/native/rust/src/main.rs",
    "cpp": "engines/polyglot-route-engine/src/elmos_polyglot_route/clang_analyzer.py",
    "objc": "engines/polyglot-route-engine/src/elmos_polyglot_route/clang_analyzer.py",
    "swift": "engines/polyglot-route-engine/native/swift/Sources/ElmosSwiftAnalyzer/main.swift",
}
SHORT_VERSIONS = {
    "java": "21.0.11",
    "python": "3.12.12",
    "csharp": "10.0.301",
    "typescript": "5.9.2 / Node 26.0.0",
    "go": "1.25.0",
    "rust": "1.89.0",
    "cpp": "C++20 / Apple clang 21.0.0 / arm64-apple-darwin25.6.0",
    "objc": "Objective-C / Apple clang 21.0.0 / arm64-apple-darwin25.6.0",
    "swift": "Swift 6.3.3 / arm64-apple-macosx26.0",
}
EXTENSIONS = {
    "java": "java",
    "python": "py",
    "csharp": "cs",
    "typescript": "ts",
    "go": "go",
    "rust": "rs",
    "cpp": "cpp",
    "objc": "m",
    "swift": "swift",
}
CORPORA = {
    "development": ("", "Pricing", "pricing", "calculate", "behavior-cases.json"),
    "holdout": ("holdout", "Clamp", "clamp", "clamp", "holdout/cases.json"),
    "real-repository": (
        "representative",
        "Difference",
        "difference",
        "difference",
        "representative/cases.json",
    ),
}
SPECIALIZED_CORPUS_PROFILES: dict[str, dict[str, Any]] = {
    "development": {
        "class_name": "Pricing",
        "module_name": "pricing",
        "function_name": "calculate",
        "type_coverage": ["integer"],
        "cases": [
            {"args": [100, 20], "expected": 120},
            {"args": [-1, 5], "expected": 0},
            {"args": [7, -2], "expected": 5},
        ],
    },
    "holdout": {
        "class_name": "EchoNumber",
        "module_name": "echo_number",
        "function_name": "echoNumber",
        "type_coverage": ["number"],
        "cases": [
            {"args": [-0.0], "expected": -0.0},
            {"args": [0.0], "expected": 0.0},
            {"args": [1.7976931348623157e308], "expected": 1.7976931348623157e308},
            {"args": [-1.7976931348623157e308], "expected": -1.7976931348623157e308},
            {"args": [2.2250738585072014e-308], "expected": 2.2250738585072014e-308},
        ],
    },
    "real-repository": {
        "class_name": "Decision",
        "module_name": "decision",
        "function_name": "decision",
        "type_coverage": ["boolean"],
        "cases": [
            {"args": [True, True, False], "expected": True},
            {"args": [True, False, False], "expected": False},
            {"args": [False, False, True], "expected": True},
            {"args": [False, False, False], "expected": False},
        ],
    },
}


def specialized_corpus_source(language: Language, corpus: str) -> str:
    """Return exact source text for the three independent specialized type corpora."""

    if corpus == "development":
        return {
            "java": (
                "public final class Pricing {\n"
                "    public static long calculate(long subtotal, long tax) {\n"
                "        if (subtotal < 0) { return 0; }\n"
                "        return subtotal + tax;\n"
                "    }\n"
                "}\n"
            ),
            "cpp": (
                "#include <cstdint>\n"
                "std::int64_t calculate(std::int64_t subtotal, std::int64_t tax) {\n"
                "    if (subtotal < 0) { return 0; }\n"
                "    return subtotal + tax;\n"
                "}\n"
            ),
            "objc": (
                "#import <Foundation/Foundation.h>\n"
                "long long calculate(long long subtotal, long long tax) {\n"
                "    if (subtotal < 0) { return 0; }\n"
                "    return subtotal + tax;\n"
                "}\n"
            ),
            "swift": (
                "func calculate(_ subtotal: Int64, _ tax: Int64) -> Int64 {\n"
                "    if subtotal < 0 { return 0 }\n"
                "    return subtotal + tax\n"
                "}\n"
            ),
        }[language]
    if corpus == "holdout":
        return {
            "java": (
                "public final class EchoNumber {\n"
                "    public static double echoNumber(double value) { return value; }\n"
                "}\n"
            ),
            "cpp": "double echoNumber(double value) { return value; }\n",
            "objc": ("#import <Foundation/Foundation.h>\ndouble echoNumber(double value) { return value; }\n"),
            "swift": "func echoNumber(_ value: Double) -> Double { return value }\n",
        }[language]
    if corpus == "real-repository":
        return {
            "java": (
                "public final class Decision {\n"
                "    public static boolean decision(boolean left, boolean right, boolean fallback) {\n"
                "        if ((left && right) || fallback) { return true; }\n"
                "        return false;\n"
                "    }\n"
                "}\n"
            ),
            "cpp": (
                "bool decision(bool left, bool right, bool fallback) {\n"
                "    if ((left && right) || fallback) { return true; }\n"
                "    return false;\n"
                "}\n"
            ),
            "objc": (
                "#import <Foundation/Foundation.h>\n"
                "BOOL decision(BOOL left, BOOL right, BOOL fallback) {\n"
                "    if ((left && right) || fallback) { return YES; }\n"
                "    return NO;\n"
                "}\n"
            ),
            "swift": (
                "func decision(_ left: Bool, _ right: Bool, _ fallback: Bool) -> Bool {\n"
                "    if (left && right) || fallback { return true }\n"
                "    return false\n"
                "}\n"
            ),
        }[language]
    raise RuntimeError(f"SPECIALIZED_CORPUS_UNDECLARED:{corpus}")


MODULE_FIXTURE_FILES: dict[Language, str] = {
    "java": "EquivalenceModule.java",
    "cpp": "equivalence_module.cpp",
    "objc": "equivalence_module.m",
    "swift": "equivalence_module.swift",
}
ARTIFACT_CORPORA = frozenset({*CORPORA, "module"})
ARTIFACT_ALLOWED_SUFFIXES = {
    ".cs",
    ".csproj",
    ".cpp",
    ".go",
    ".java",
    ".js",
    ".json",
    ".lock",
    ".log",
    ".md",
    ".m",
    ".py",
    ".rs",
    ".smt2",
    ".toml",
    ".ts",
    ".swift",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
EXCLUDED_REBUILDABLE_DIRECTORIES = {
    ".build",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".swiftpm",
    "__pycache__",
    "artifacts",
    "bin",
    "checkouts",
    "dist",
    "obj",
    "target",
}
EXCLUDED_REBUILDABLE_SUFFIXES = {
    ".a",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".o",
    ".pdb",
    ".pyc",
    ".pyo",
    ".rlib",
    ".rmeta",
    ".so",
}
EXCLUDED_REBUILDABLE_PATTERNS = [
    "bin/**",
    "obj/**",
    "target/**",
    "dist/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    "*.class",
    "*.pyc",
    "*.pyo",
    "*.o",
    "*.a",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.exe",
    "*.pdb",
    "*.rlib",
    "*.rmeta",
    "route_harness",
    "other extensionless/native binaries",
]


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_ref(evidence_root: Path, path: Path) -> dict[str, str | int]:
    resolved_root = evidence_root.resolve()
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError(f"ARTIFACT_OUTSIDE_EVIDENCE_ROOT:{resolved}") from exc
    if not resolved.is_file():
        raise RuntimeError(f"ARTIFACT_NOT_FILE:{resolved}")
    return {
        "path": relative.as_posix(),
        "sha256": sha256_file(resolved),
        "bytes": resolved.stat().st_size,
    }


def formal_artifact_id(route: Path, path: Path) -> str:
    relative = path.resolve(strict=True).relative_to(route.resolve()).as_posix()
    return "artifact-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()


def formal_artifact_ref(route: Path, path: Path, role: str) -> dict[str, str | int]:
    return {
        "artifact_id": formal_artifact_id(route, path),
        "role": role,
        **artifact_ref(route, path),
    }


def persist_artifact_directory(
    repo: Path,
    route: Path,
    corpus: str,
    generated: Path,
) -> dict[str, str | int]:
    """Copy one successful generated run into its fixed, managed evidence path.

    The destination is additive/overwrite-only: files produced at the same
    fixed relative path are refreshed, while unrelated or stale files are never
    recursively deleted. The manifest is therefore the authority for the exact
    files belonging to the current run.
    """

    if corpus not in ARTIFACT_CORPORA:
        raise RuntimeError(f"UNKNOWN_CORPUS:{corpus}")
    generated = generated.resolve(strict=True)
    if not generated.is_dir():
        raise RuntimeError(f"GENERATED_ARTIFACT_ROOT_INVALID:{generated}")
    destination = route / "certification" / "artifacts" / corpus
    destination.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, str | int]] = []
    excluded_files: list[str] = []
    for source in sorted(generated.rglob("*"), key=lambda path: path.as_posix()):
        relative = source.relative_to(generated)
        target = destination / relative
        if source.is_symlink():
            raise RuntimeError(f"GENERATED_ARTIFACT_SYMLINK_REJECTED:{relative.as_posix()}")
        if any(part in EXCLUDED_REBUILDABLE_DIRECTORIES for part in relative.parts):
            if source.is_file():
                excluded_files.append(relative.as_posix())
            continue
        if source.is_dir():
            continue
        if not source.is_file():
            raise RuntimeError(f"GENERATED_ARTIFACT_SPECIAL_FILE_REJECTED:{relative.as_posix()}")
        if (
            source.suffix.lower() in EXCLUDED_REBUILDABLE_SUFFIXES
            or source.suffix.lower() not in ARTIFACT_ALLOWED_SUFFIXES
        ):
            excluded_files.append(relative.as_posix())
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        observed = sha256_file(target)
        expected = sha256_file(source)
        if observed != expected or target.stat().st_size != source.stat().st_size:
            raise RuntimeError(f"GENERATED_ARTIFACT_COPY_MISMATCH:{relative.as_posix()}")
        files.append(
            {
                "path": relative.as_posix(),
                "sha256": observed,
                "bytes": target.stat().st_size,
            }
        )
    if not files:
        raise RuntimeError(f"GENERATED_ARTIFACT_ROOT_EMPTY:{corpus}")
    manifest_path = destination / "artifact-manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": 1,
            "route_key": route.name,
            "corpus": corpus,
            "artifact_root": destination.relative_to(repo).as_posix(),
            "file_count": len(files),
            "total_bytes": sum(int(item["bytes"]) for item in files),
            "files": files,
            "allowed_suffixes": sorted(ARTIFACT_ALLOWED_SUFFIXES),
            "excluded_rebuildable_patterns": EXCLUDED_REBUILDABLE_PATTERNS,
            "excluded_files": excluded_files,
            "note": "Only files listed here belong to this generated run; unlisted files are not evidence.",
        },
    )
    return artifact_ref(route, manifest_path)


def _corpus_artifact(route: Path, corpus: str, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise RuntimeError(f"{label}_PATH_INVALID:{relative}")
    candidate = route / "certification" / "artifacts" / corpus / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(route.resolve())
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise RuntimeError(f"{label}_PATH_INVALID:{relative}") from exc
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise RuntimeError(f"{label}_FILE_INVALID:{relative}")
    return resolved


def _normalized_functions(path: Path, label: str) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{label}_IR_ROOT_INVALID")
    try:
        semantic_ir = SemanticIR.from_mapping(value)
    except RouteError as exc:
        raise RuntimeError(f"{label}_IR_INVALID:{exc}") from exc
    if semantic_ir.diagnostics or not semantic_ir.functions:
        raise RuntimeError(f"{label}_IR_NOT_EXACT")
    return [function.semantic_mapping() for function in semantic_ir.functions]


def _validated_corpus_manifest_files(route: Path, corpus: str) -> list[Path]:
    manifest_path = route / "certification" / "artifacts" / corpus / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("corpus") != corpus:
        raise RuntimeError(f"FORMAL_ARTIFACT_MANIFEST_INVALID:{corpus}")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError(f"FORMAL_ARTIFACT_MANIFEST_EMPTY:{corpus}")
    result = [manifest_path]
    root = manifest_path.parent
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise RuntimeError(f"FORMAL_ARTIFACT_MANIFEST_ENTRY_INVALID:{corpus}:{index}")
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise RuntimeError(f"FORMAL_ARTIFACT_MANIFEST_PATH_INVALID:{corpus}:{index}")
        candidate = (root / relative).resolve(strict=True)
        try:
            candidate.relative_to(root.resolve())
        except ValueError as exc:
            raise RuntimeError(f"FORMAL_ARTIFACT_MANIFEST_PATH_ESCAPE:{corpus}:{relative}") from exc
        if (
            not candidate.is_file()
            or sha256_file(candidate) != entry.get("sha256")
            or candidate.stat().st_size != entry.get("bytes")
        ):
            raise RuntimeError(f"FORMAL_ARTIFACT_MANIFEST_TAMPERED:{corpus}:{relative}")
        result.append(candidate)
    return result


def _capture_engine_sources(repo: Path, route: Path) -> tuple[Path, list[Path]]:
    """Persist the analyzer, emitter, proof, schema, and gate bytes used.

    A dependency lockfile alone does not bind the implementation that produced
    evidence. Route-local copies keep replay independent from a mutable
    checkout and make code drift visible to the strict digest validator.
    """

    engine = repo / "engines" / "polyglot-route-engine"
    engine_module_root = engine / "src" / "elmos_polyglot_route"
    sources = [
        engine_module_root / name
        for name in (
            "__init__.py",
            "canonical.py",
            "clang_analyzer.py",
            "emitter.py",
            "engine.py",
            "equivalence.py",
            "models.py",
            "native.py",
            "python_analyzer.py",
            "toolchains.py",
            "types.py",
            "validation.py",
        )
    ]
    for native_root in (
        engine / "native" / "csharp",
        engine / "native" / "go",
        engine / "native" / "java",
        engine / "native" / "rust",
        engine / "native" / "swift",
        engine / "native" / "typescript",
    ):
        sources.extend(
            path
            for path in native_root.rglob("*")
            if path.is_file()
            and not any(part in EXCLUDED_REBUILDABLE_DIRECTORIES for part in path.relative_to(native_root).parts)
            and (
                path.name == "Package.resolved"
                or path.suffix.lower()
                in {
                    ".cs",
                    ".csproj",
                    ".go",
                    ".java",
                    ".lock",
                    ".mjs",
                    ".rs",
                    ".swift",
                    ".toml",
                }
            )
        )
    sources.extend(
        [
            engine / "pyproject.toml",
            engine / "uv.lock",
            repo / "schemas" / "batch29" / "formal-equivalence-evidence.schema.json",
            repo / "schemas" / "batch29" / "module-case-manifest.schema.json",
            repo / "schemas" / "batch29" / "module-equivalence-evidence.schema.json",
            repo / "schemas" / "batch29" / "route-certification.schema.json",
            repo / "scripts" / "batch29" / "run_polyglot_routes.py",
            repo / "scripts" / "batch29" / "route_sets.py",
            repo / "scripts" / "batch29" / "run_route_gate.py",
            repo / "scripts" / "batch29" / "validate_route.py",
            repo / "scripts" / "operations" / "validate_translation_route_matrix.py",
        ]
    )
    capture_parent = route / "certification" / "formal-artifacts"
    capture_parent.mkdir(parents=True, exist_ok=True)
    capture_root = capture_parent / "engine-sources"
    backup_root = capture_parent / ".engine-sources.previous"
    if backup_root.exists() and not capture_root.exists():
        backup_root.rename(capture_root)
    elif backup_root.exists():
        shutil.rmtree(backup_root)
    staging_parent = Path(tempfile.mkdtemp(prefix=".engine-sources-staging-", dir=capture_parent))
    staging_root = staging_parent / "engine-sources"
    captured: list[Path] = []
    entries: list[dict[str, Any]] = []
    try:
        for source in sorted(set(sources), key=lambda path: path.relative_to(repo).as_posix()):
            if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
                raise RuntimeError(f"FORMAL_ENGINE_SOURCE_INVALID:{source}")
            relative = source.relative_to(repo)
            staged = staging_root / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged)
            if sha256_file(staged) != sha256_file(source) or staged.stat().st_size != source.stat().st_size:
                raise RuntimeError(f"FORMAL_ENGINE_SOURCE_COPY_MISMATCH:{relative.as_posix()}")
            final_destination = capture_root / relative
            entries.append(
                {
                    "repository_path": relative.as_posix(),
                    "captured_path": final_destination.relative_to(route).as_posix(),
                    "sha256": sha256_file(staged),
                    "bytes": staged.stat().st_size,
                }
            )
        if capture_root.exists():
            capture_root.rename(backup_root)
        try:
            staging_root.rename(capture_root)
        except Exception:
            if backup_root.exists() and not capture_root.exists():
                backup_root.rename(capture_root)
            raise
        if backup_root.exists():
            shutil.rmtree(backup_root)
    finally:
        if staging_parent.exists():
            shutil.rmtree(staging_parent)
    captured = [route / str(item["captured_path"]) for item in entries]
    manifest = route / "certification" / "formal-artifacts" / "engine-source-manifest.json"
    write_json(
        manifest,
        {
            "schema_version": 1,
            "kind": "polyglot-route-engine-source-bundle",
            "file_count": len(entries),
            "files": entries,
        },
    )
    return manifest, captured


def build_formal_equivalence_evidence(
    repo: Path,
    route: Path,
    source: Language,
    target: Language,
    reports: dict[str, dict[str, Any]],
) -> dict[str, str | int]:
    """Compose strict, byte-bound route evidence from three successful runs.

    The per-artifact theorem compares the two normalized L0 denotations.  The
    route-level claim remains ``PROVED_UNDER_ASSUMPTIONS`` because compiler
    frontend/analyzer and emitter soundness are recorded assumptions rather
    than independently checked proof certificates.
    """

    route_key = f"{source}-to-{target}"
    formal_root = route / "certification" / "formal-artifacts"
    formal_root.mkdir(parents=True, exist_ok=True)
    normalized_runs: list[dict[str, Any]] = []
    target_artifacts: list[dict[str, Any]] = []
    chunks: list[dict[str, str]] = []
    counterexamples: list[dict[str, str]] = []
    total_cases = 0
    passed_cases = 0
    canonical_oracle_passed = True
    source_runtime_passed = True
    target_runtime_passed = True
    obligations: list[dict[str, Any]] = []
    assumptions: set[str] = set()
    solver_name: str | None = None
    solver_version: str | None = None
    solver_timeout_ms: int | None = None
    solver_random_seed: int | None = None
    proof_bundle_runs: list[dict[str, Any]] = []
    referenced_paths: list[Path] = []
    artifact_roles: dict[Path, str] = {}
    chunk_artifact_ids: list[str] = []
    behavior_artifact_ids: list[str] = []
    solver_result_artifact_ids: list[str] = []

    def bind(path: Path, role: str) -> None:
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(route.resolve())
        except ValueError as exc:
            raise RuntimeError(f"FORMAL_ARTIFACT_OUTSIDE_ROUTE:{resolved}") from exc
        referenced_paths.append(resolved)
        previous = artifact_roles.get(resolved)
        if previous is None or previous == "corpus-artifact":
            artifact_roles[resolved] = role
        elif role != "corpus-artifact" and previous != role:
            raise RuntimeError(f"FORMAL_ARTIFACT_ROLE_CONFLICT:{resolved}:{previous}:{role}")

    for corpus in CORPORA:
        report = reports.get(corpus)
        if not isinstance(report, dict) or report.get("status") != "PASSED":
            raise RuntimeError(f"FORMAL_CORPUS_REPORT_NOT_PASSED:{route_key}:{corpus}")
        for persisted_path in _validated_corpus_manifest_files(route, corpus):
            bind(persisted_path, "corpus-artifact")
        semantic = report.get("semantic_equivalence")
        chunk = report.get("chunk_equivalence")
        behavior = report.get("behavior_equivalence")
        formal = report.get("formal_composition")
        layered = report.get("layered_equivalence")
        if not all(isinstance(item, dict) for item in (semantic, chunk, behavior, formal, layered)):
            raise RuntimeError(f"FORMAL_LAYER_MISSING:{route_key}:{corpus}")
        if (
            semantic.get("status") != "PASSED"
            or semantic.get("difference_count") != 0
            or chunk.get("status") != "PASSED"
            or chunk.get("coverage") != 1.0
            or behavior.get("status") != "PASSED"
            or formal.get("status") != "PROVED_UNDER_ASSUMPTIONS"
            or formal.get("property_status") != "PROVED"
            or layered.get("status") != "PASSED"
        ):
            raise RuntimeError(f"FORMAL_LAYER_NONPASSING:{route_key}:{corpus}")

        source_ir = _corpus_artifact(route, corpus, semantic.get("source_ir_path"), "SOURCE_IR")
        target_ir = _corpus_artifact(route, corpus, semantic.get("target_ir_path"), "TARGET_IR")
        source_functions = _normalized_functions(source_ir, "SOURCE")
        target_functions = _normalized_functions(target_ir, "TARGET")
        if source_functions != target_functions:
            raise RuntimeError(f"FORMAL_NORMALIZED_IR_MISMATCH:{route_key}:{corpus}")
        normalized_runs.append({"corpus": corpus, "functions": source_functions})
        bind(source_ir, "source-ir")
        bind(target_ir, "target-ir")

        target_path = _corpus_artifact(route, corpus, report.get("target", {}).get("path"), "TARGET")
        target_artifacts.append(
            {
                "corpus": corpus,
                "path": target_path.relative_to(route).as_posix(),
                "sha256": sha256_file(target_path),
                "bytes": target_path.stat().st_size,
            }
        )
        bind(target_path, "target-artifact")

        chunk_path = _corpus_artifact(route, corpus, chunk.get("artifact_path"), "CHUNK")
        chunk_value = json.loads(chunk_path.read_text(encoding="utf-8"))
        if not isinstance(chunk_value, dict):
            raise RuntimeError(f"FORMAL_CHUNK_ROOT_INVALID:{route_key}:{corpus}")
        mappings = chunk_value.get("mappings")
        if not isinstance(mappings, list) or not mappings:
            raise RuntimeError(f"FORMAL_CHUNKS_EMPTY:{route_key}:{corpus}")
        for mapping in mappings:
            if not isinstance(mapping, dict) or mapping.get("status") != "EXACT":
                raise RuntimeError(f"FORMAL_CHUNK_NONEXACT:{route_key}:{corpus}")
            semantic_path = mapping.get("semantic_path")
            semantic_hash = mapping.get("semantic_hash")
            source_chunk_id = mapping.get("source_chunk_id")
            target_chunk_id = mapping.get("target_chunk_id")
            if not all(
                isinstance(item, str) and item
                for item in (
                    semantic_path,
                    semantic_hash,
                    source_chunk_id,
                    target_chunk_id,
                )
            ):
                raise RuntimeError(f"FORMAL_CHUNK_ID_INVALID:{route_key}:{corpus}")
            chunks.append(
                {
                    "chunk_id": f"{corpus}:{source_chunk_id}",
                    "source_ref": f"{formal_artifact_id(route, source_ir)}#{semantic_path}",
                    "target_ref": f"{formal_artifact_id(route, target_ir)}#{semantic_path}",
                    "semantic_hash": semantic_hash,
                    "status": "MATCHED",
                }
            )
        bind(chunk_path, "chunk-map")
        chunk_artifact_ids.append(formal_artifact_id(route, chunk_path))

        behavior_path = _corpus_artifact(route, corpus, behavior.get("artifact_path"), "BEHAVIOR")
        behavior_value = json.loads(behavior_path.read_text(encoding="utf-8"))
        if not isinstance(behavior_value, dict):
            raise RuntimeError(f"FORMAL_BEHAVIOR_ROOT_INVALID:{route_key}:{corpus}")
        case_count = behavior_value.get("case_count")
        pass_count = behavior_value.get("pass_count")
        if (
            not isinstance(case_count, int)
            or isinstance(case_count, bool)
            or case_count <= 0
            or pass_count != case_count
        ):
            raise RuntimeError(f"FORMAL_BEHAVIOR_COUNT_INVALID:{route_key}:{corpus}")
        total_cases += case_count
        passed_cases += pass_count
        canonical_oracle_passed = canonical_oracle_passed and behavior_value.get("oracle_conflict_count") == 0
        source_runtime_passed = source_runtime_passed and behavior_value.get("source_runtime_passed") is True
        target_runtime_passed = target_runtime_passed and behavior_value.get("target_runtime_passed") is True
        for item in behavior_value.get("counterexamples", []):
            if not isinstance(item, dict):
                raise RuntimeError(f"FORMAL_BEHAVIOR_COUNTEREXAMPLE_INVALID:{route_key}:{corpus}")
            counterexamples.append(
                {
                    "case_id": f"{corpus}:{item.get('case_id')}",
                    "reason": "source/canonical/target behavior divergence",
                    "evidence_ref": behavior_path.relative_to(route).as_posix(),
                }
            )
        bind(behavior_path, "behavior-result")
        behavior_artifact_ids.append(formal_artifact_id(route, behavior_path))

        formal_path = _corpus_artifact(route, corpus, formal.get("artifact_path"), "FORMAL")
        formal_value = json.loads(formal_path.read_text(encoding="utf-8"))
        if not isinstance(formal_value, dict):
            raise RuntimeError(f"FORMAL_PROOF_ROOT_INVALID:{route_key}:{corpus}")
        solver = formal_value.get("solver")
        if not isinstance(solver, dict):
            raise RuntimeError(f"FORMAL_SOLVER_INVALID:{route_key}:{corpus}")
        observed_solver = solver.get("name")
        observed_version = solver.get("version")
        if not isinstance(observed_solver, str) or not isinstance(observed_version, str):
            raise RuntimeError(f"FORMAL_SOLVER_IDENTITY_INVALID:{route_key}:{corpus}")
        solver_name = solver_name or observed_solver
        solver_version = solver_version or observed_version
        if solver_name != observed_solver or solver_version != observed_version:
            raise RuntimeError(f"FORMAL_SOLVER_DRIFT:{route_key}:{corpus}")
        timeout = solver.get("timeout_ms")
        random_seed = solver.get("random_seed")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise RuntimeError(f"FORMAL_SOLVER_TIMEOUT_INVALID:{route_key}:{corpus}")
        if not isinstance(random_seed, int) or isinstance(random_seed, bool):
            raise RuntimeError(f"FORMAL_SOLVER_SEED_INVALID:{route_key}:{corpus}")
        solver_timeout_ms = solver_timeout_ms or timeout
        solver_random_seed = solver_random_seed if solver_random_seed is not None else random_seed
        if solver_timeout_ms != timeout or solver_random_seed != random_seed:
            raise RuntimeError(f"FORMAL_SOLVER_OPTIONS_DRIFT:{route_key}:{corpus}")
        corpus_assumptions = formal_value.get("assumptions")
        if (
            not isinstance(corpus_assumptions, list)
            or not corpus_assumptions
            or any(not isinstance(item, str) or not item for item in corpus_assumptions)
        ):
            raise RuntimeError(f"FORMAL_ASSUMPTIONS_REQUIRED:{route_key}:{corpus}")
        assumptions.update(corpus_assumptions)
        smt2_path = _corpus_artifact(route, corpus, "formal-equivalence.smt2", "FORMAL_SMT2")
        proof_result_path = _corpus_artifact(route, corpus, "formal-proof-result.json", "FORMAL_RESULT")
        formal_input_path = _corpus_artifact(route, corpus, "formal-input.json", "FORMAL_INPUT")
        obligations.append(
            {
                "obligation_id": f"{route_key}:{corpus}:L0-DENOTATIONAL-EQUIVALENCE",
                "status": "PROVED_UNDER_ASSUMPTIONS",
                "scope": f"{corpus}:typed-pure-function-v1",
                "formal_input_artifact_id": formal_artifact_id(route, formal_input_path),
                "solver_input_artifact_id": formal_artifact_id(route, smt2_path),
                "input_digest": sha256_file(smt2_path),
                "solver_result_artifact_id": formal_artifact_id(route, proof_result_path),
                "assumptions": sorted(set(corpus_assumptions)),
                "detail": "Z3 returned UNSAT for source/target divergence with same-input constraints.",
            }
        )
        proof_bundle_runs.append(
            {
                "corpus": corpus,
                "formal_input": artifact_ref(route, formal_input_path),
                "smt2": artifact_ref(route, smt2_path),
                "result": artifact_ref(route, proof_result_path),
                "composition": artifact_ref(route, formal_path),
                "status": formal_value.get("status"),
                "property_status": formal_value.get("property_status"),
            }
        )
        bind(formal_path, "formal-composition")
        bind(formal_input_path, "formal-input")
        bind(smt2_path, "solver-input")
        bind(proof_result_path, "solver-result")
        solver_result_artifact_ids.append(formal_artifact_id(route, proof_result_path))

    normalized_bundle = {
        "schema_version": 1,
        "semantic_profile": "typed-pure-function-v1",
        "route_key": route_key,
        "corpora": normalized_runs,
    }
    source_bundle = formal_root / "source-semantic-ir.normalized.json"
    target_bundle = formal_root / "target-semantic-ir.normalized.json"
    write_json(source_bundle, normalized_bundle)
    write_json(target_bundle, normalized_bundle)
    if source_bundle.read_bytes() != target_bundle.read_bytes():
        raise RuntimeError(f"FORMAL_NORMALIZED_BUNDLE_DRIFT:{route_key}")

    target_bundle_path = formal_root / "target-artifact-bundle.json"
    write_json(
        target_bundle_path,
        {
            "schema_version": 1,
            "route_key": route_key,
            "semantic_profile": "typed-pure-function-v1",
            "target_artifacts": target_artifacts,
        },
    )
    proof_bundle_path = formal_root / "proof-input-bundle.json"
    write_json(
        proof_bundle_path,
        {
            "schema_version": 1,
            "route_key": route_key,
            "property_id": "L0-DENOTATIONAL-EQUIVALENCE",
            "same_input_required": True,
            "runs": proof_bundle_runs,
        },
    )
    engine_source_manifest, captured_engine_sources = _capture_engine_sources(repo, route)
    environment_path = formal_root / "environment.json"
    write_json(
        environment_path,
        {
            "schema_version": 1,
            "route_key": route_key,
            "authority": "local-engineering-validation",
            "platform": platform.platform(),
            "python": sys.version,
            "source_toolchain": VERSIONS[source],
            "target_toolchain": VERSIONS[target],
            "solver": {"name": solver_name, "version": solver_version},
            "route_engine_lock": {
                "path": "engines/polyglot-route-engine/uv.lock",
                "sha256": sha256_file(repo / "engines" / "polyglot-route-engine" / "uv.lock"),
            },
            "engine_source_manifest": {
                "path": engine_source_manifest.relative_to(route).as_posix(),
                "sha256": sha256_file(engine_source_manifest),
                "bytes": engine_source_manifest.stat().st_size,
            },
            "independent_verification": "NOT_RUN",
            "external_certification": "NOT_RUN",
        },
    )

    bind(source_bundle, "source-ir")
    bind(target_bundle, "target-ir")
    bind(target_bundle_path, "target-artifact")
    bind(proof_bundle_path, "proof-input-bundle")
    bind(environment_path, "environment")
    bind(engine_source_manifest, "engine-source-manifest")
    for captured_engine_source in captured_engine_sources:
        bind(captured_engine_source, "engine-source")
    unique_paths = sorted(set(referenced_paths), key=lambda item: item.relative_to(route).as_posix())
    artifact_refs = [formal_artifact_ref(route, item, artifact_roles[item]) for item in unique_paths]
    source_ir_digest = sha256_file(source_bundle)
    target_ir_digest = sha256_file(target_bundle)
    proof_input_digest = sha256_file(proof_bundle_path)
    target_artifact_id = formal_artifact_id(route, target_bundle_path)
    environment_artifact_id = formal_artifact_id(route, environment_path)
    source_ir_artifact_id = formal_artifact_id(route, source_bundle)
    target_ir_artifact_id = formal_artifact_id(route, target_bundle)
    evidence = {
        "schema_version": 2,
        "route_key": route_key,
        "route_manifest_sha256": sha256_file(route / "route.json"),
        "semantic_profile": "typed-pure-function-v1",
        "semantic_profile_sha256": sha256_file(route / "lowering" / "profile.json"),
        "artifact_sha256": sha256_file(target_bundle_path),
        "artifact_id": target_artifact_id,
        "environment_sha256": sha256_file(environment_path),
        "environment_artifact_id": environment_artifact_id,
        "artifact_refs": artifact_refs,
        "semantic_ir": {
            "status": "PASSED",
            "source_ir_artifact_id": source_ir_artifact_id,
            "source_ir_sha256": source_ir_digest,
            "target_ir_artifact_id": target_ir_artifact_id,
            "target_relift_ir_sha256": target_ir_digest,
            "unknown_or_dropped_nodes": 0,
            "differences": [],
        },
        "semantic_chunks": {
            "status": "PASSED",
            "total": len(chunks),
            "matched": len(chunks),
            "unmatched": 0,
            "ambiguous": 0,
            "coverage": 1.0,
            "evidence_artifact_ids": chunk_artifact_ids,
            "chunks": chunks,
        },
        "behavior_equivalence": {
            "status": "PASSED",
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "counterexamples": counterexamples,
            "evidence_artifact_ids": behavior_artifact_ids,
            "source_runtime_artifact_ids": behavior_artifact_ids,
            "target_runtime_artifact_ids": behavior_artifact_ids,
            "canonical_oracle_passed": canonical_oracle_passed,
            "source_runtime_passed": source_runtime_passed,
            "target_runtime_passed": target_runtime_passed,
        },
        "formal_proof": {
            "status": "PROVED_UNDER_ASSUMPTIONS",
            "solver": solver_name,
            "solver_version": solver_version,
            "solver_options": {
                "timeout_ms": solver_timeout_ms,
                "random_seed": solver_random_seed,
            },
            "input_artifact_id": formal_artifact_id(route, proof_bundle_path),
            "input_digest": proof_input_digest,
            "result_artifact_ids": solver_result_artifact_ids,
            "assumptions": sorted(assumptions),
            "obligations": obligations,
            "replay": {
                "command": [
                    "uv",
                    "--directory",
                    "../../engines/polyglot-route-engine",
                    "run",
                    "--locked",
                    "python",
                    "../../scripts/batch29/run_polyglot_routes.py",
                    "--repo-root",
                    "../..",
                    "--route",
                    route_key,
                ],
                "cwd": ".",
                "expected_result_artifact_id": solver_result_artifact_ids[0],
                "expected_result_sha256": next(
                    reference["sha256"]
                    for reference in artifact_refs
                    if reference["artifact_id"] == solver_result_artifact_ids[0]
                ),
                "expected_exit_code": 0,
            },
        },
    }
    formal_path = route / "certification" / "formal-equivalence.json"
    write_json(formal_path, evidence)
    return artifact_ref(route, formal_path)


def write_module_not_run_evidence(route: Path, source: Language, target: Language, reason: str) -> dict[str, str | int]:
    """Persist an honest module placeholder until real three-function evidence exists."""

    path = route / "certification" / "module-equivalence.json"
    write_json(
        path,
        {
            "schema_version": "1.0.0",
            "kind": "typed-pure-module-equivalence",
            "profile": "typed-pure-module-v1",
            "status": "NOT_RUN",
            "local_verification_status": "NOT_RUN",
            "route": {
                "route_key": f"{source}-to-{target}",
                "source_language": source,
                "target_language": target,
            },
            "module_input_sha256": None,
            "module_contract": {
                "source_symbols": [],
                "target_symbols": [],
                "manifest_symbols": [],
                "exact_symbol_set": False,
                "exact_signature_set": False,
                "independence": {"status": "NOT_RUN"},
            },
            "functions": [],
            "composition": {
                "rule": "per-function-denotation-plus-module-composition",
                "input_domain": SPECIALIZED_INPUT_DOMAIN,
                "out_of_domain_arithmetic_behavior": SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC,
                "function_count": 0,
                "passed_function_count": 0,
                "status": "NOT_RUN",
                "proof_strength": "NONE",
                "original_source_bytes_theorem": False,
                "source_compiler_runtime_soundness": "NOT_RUN",
                "target_compiler_runtime_soundness": "NOT_RUN",
            },
            "artifact_refs": [],
            "certification_status": "NOT_CERTIFIED",
            "external_verification_status": "NOT_RUN",
            "limitations": [reason],
        },
    )
    return artifact_ref(route, path)


SPECIALIZED_NEGATIVE_CASES = {
    "java": ("java-int-width", "java-string-raw-reference-equality"),
    "cpp": ("cpp-long-width", "cpp-unsigned-domain"),
    "objc": ("objc-nsinteger-width", "objc-nsstring-pointer-identity"),
    "swift": ("swift-int-requires-int64", "swift-helper-tamper"),
}

SPECIALIZED_NEGATIVE_SOURCES: dict[str, tuple[Language, str, str, str, tuple[str, ...]]] = {
    "java-int-width": (
        "java",
        "JavaIntWidth.java",
        "width",
        "public final class JavaIntWidth {\n    public static int width(int value) { return value; }\n}\n",
        ("JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int",),
    ),
    "java-string-raw-reference-equality": (
        "java",
        "JavaStringIdentity.java",
        "same",
        "public final class JavaStringIdentity {\n"
        "    public static boolean same(String left, String right) { return left == right; }\n"
        "}\n",
        ("JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET",),
    ),
    "cpp-long-width": (
        "cpp",
        "cpp_long_width.cpp",
        "width",
        "long width(long value) { return value; }\n",
        ("CPP_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:long",),
    ),
    "cpp-unsigned-domain": (
        "cpp",
        "cpp_unsigned_domain.cpp",
        "unsigned_value",
        "unsigned long long unsigned_value(unsigned long long value) { return value; }\n",
        ("CPP_UNSUPPORTED_TYPE:unsigned long long", "CPP_UNSIGNED"),
    ),
    "objc-nsinteger-width": (
        "objc",
        "objc_nsinteger_width.m",
        "width",
        "typedef long NSInteger;\nNSInteger width(NSInteger value) { return value; }\n",
        ("OBJC_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:NSInteger",),
    ),
    "objc-nsstring-pointer-identity": (
        "objc",
        "objc_nsstring_pointer_identity.m",
        "same",
        "typedef signed char BOOL;\n"
        "@interface NSString\n"
        "- (BOOL)isEqualToString:(NSString *)other;\n"
        "@end\n"
        "BOOL same(NSString *left, NSString *right) { return left == right; }\n",
        ("OBJC_STRING_POINTER_COMPARISON_OUTSIDE_CERTIFIED_SUBSET",),
    ),
    "swift-int-requires-int64": (
        "swift",
        "swift_int_width.swift",
        "width",
        "func width(_ value: Int) -> Int { return value }\n",
        ("SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int",),
    ),
}


def write_not_run_route_scaffold(route: Path, source: Language, target: Language) -> None:
    """Create a complete, non-passing route record before native execution."""

    route_key = f"{source}-to-{target}"
    run_refs: list[str] = []
    for corpus, filename in (
        ("development", "local-development-evidence.json"),
        ("holdout", "local-holdout-evidence.json"),
        ("real-repository", "local-representative-evidence.json"),
    ):
        relative = f"certification/{filename}"
        run_refs.append(relative)
        write_json(
            route / relative,
            {
                "schema_version": 1,
                "route": route_key,
                "corpus": corpus,
                "status": "NOT_RUN",
                "behavior_pass_rate": 0.0,
                "critical_unknown_semantics": 1,
                "source_map_coverage": 0.0,
                "independent_verifier": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
        )
    negative_ids = sorted(
        {
            *SPECIALIZED_NEGATIVE_CASES.get(source, ()),
            *SPECIALIZED_NEGATIVE_CASES.get(target, ()),
            "specialized-non-finite-case-unsupported",
            "specialized-number-arithmetic-unsupported",
            "specialized-overflow-outside-no-error-domain",
            "specialized-string-semantics-unsupported",
            "undeclared-directed-route-fails-closed",
            "missing-symbol-fails-closed",
        }
    )
    negative_relative = "certification/local-negative-evidence.json"
    write_json(
        route / negative_relative,
        {
            "schema_version": 1,
            "route": route_key,
            "status": "NOT_RUN",
            "expected_result": "BLOCKED",
            "test_integrity": "PRESERVED",
            "cases": [
                {
                    "case_id": case_id,
                    "status": "NOT_RUN",
                    "expected_result": "BLOCKED",
                    "observed_reason": None,
                }
                for case_id in negative_ids
            ],
            "independent_verifier": "NOT_RUN",
            "external_certification": "NOT_RUN",
        },
    )
    module_ref = write_module_not_run_evidence(
        route,
        source,
        target,
        "Native three-function module verification has not run.",
    )
    evidence = {
        "schema_version": 1,
        "route_key": route_key,
        "route_version": "1.0.0",
        "route_maturity": "LIMITED",
        "execution_status": "NOT_RUN",
        "metrics": {
            "build_green_rate": 0.0,
            "first_build_pass_rate": 0.0,
            "p0_behavior_pass_rate": 0.0,
            "source_map_coverage": 0.0,
            "manual_hours": 0,
            "cost_per_verified_workload": 0,
        },
        "critical_unknown_semantics": 1,
        "critical_behavior_regressions": 0,
        "test_integrity_violations": 0,
        "runs": run_refs,
        "negative_runs": [negative_relative],
        "module_execution_status": "NOT_RUN",
        "module_equivalence": module_ref,
        "notes": [
            "No local route or module behavior is claimed before native execution.",
            "Independent, external, customer, and production evidence remain NOT_RUN.",
        ],
    }
    write_json(route / "certification" / "evidence.json", evidence)
    certification = {
        "schema_version": 1,
        "route_key": route_key,
        "route_version": "1.0.0",
        "status": "limited",
        "certification_decision": "NOT_CERTIFIED",
        "declared_scope": "typed-pure-function-v1+typed-pure-module-v1",
        "issued_at": datetime.now(UTC).isoformat(),
        "next_review_at": "2026-11-09T00:00:00+00:00",
        "metrics": evidence["metrics"],
        "evidence_refs": [*run_refs, negative_relative, str(module_ref["path"])],
        "gate_results": {
            "local_execution": "NOT_RUN",
            "module_execution": "NOT_RUN",
            "external_execution": "NOT_RUN",
            "independent_verification": "NOT_RUN",
        },
        "module_equivalence": module_ref,
    }
    write_json(route / "certification" / "certification.json", certification)


def parse_route_key(value: str) -> tuple[Language, Language]:
    try:
        source, target = split_route_key(value)
    except ValueError:
        choices = ", ".join(EVIDENCED_ROUTE_KEYS)
        raise argparse.ArgumentTypeError(f"route must be one exact declared directed key: {choices}") from None
    return source, target  # type: ignore[return-value]


def source_path(fixtures: Path, corpus: str, language: Language) -> tuple[Path, str, Path]:
    directory, class_name, module_name, function_name, cases_name = CORPORA[corpus]
    source_name = class_name if language in {"java", "csharp"} else module_name
    source = fixtures / directory / language / f"{source_name}.{EXTENSIONS[language]}"
    cases = fixtures / cases_name
    return source, function_name, cases


def configure_route(repo: Path, source: Language, target: Language) -> Path:
    route_key = f"{source}-to-{target}"
    if route_key not in EVIDENCED_ROUTE_KEYS:
        raise RuntimeError(f"UNDECLARED_DIRECTED_ROUTE:{route_key}")
    specialized = route_key in SPECIALIZED_ROUTE_KEYS
    route = repo / "routes" / route_key
    if not route.is_dir():
        raise RuntimeError(f"MISSING_ROUTE:{route_key}")
    route_manifest = {
        "schema_version": 1,
        "route_key": route_key,
        "version": "1.0.0",
        "status": "limited",
        "owner": "ELMOS Migration Platform",
        "maintenance_owner": "ELMOS Polyglot Route Maintainers",
        "review_date": "2026-10-26",
        "source": {
            "language": source,
            "versions": VERSIONS[source],
            "engine_path": ENGINE_PATHS[source],
        },
        "target": {
            "language": target,
            "versions": VERSIONS[target],
            "engine_path": "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py",
        },
        "profiles": {
            "semantic_profile": "typed-pure-function-v1",
            "module_profile": "typed-pure-module-v1" if specialized else "NOT_APPLICABLE",
            "target_profile": f"{target}-native-compiler",
            "input_domain": (SPECIALIZED_INPUT_DOMAIN if specialized else "legacy-profile-defined-domain"),
        },
        "framework_profiles": [],
        "paths": {
            "support_matrix": "support-matrix.json",
            "corpus": "corpus",
            "certification": "certification",
        },
        "gates": {
            "real_target_compiler": True,
            "source_map_required": True,
            "holdout_required": True,
            "representative_repository_required": True,
            "critical_unknowns_allowed": 0,
            "critical_behavior_regressions_allowed": 0,
            "module_equivalence_required": specialized,
            "minimum_module_functions": 3,
            "concrete_spans_required": specialized,
            "canonical_finite_no_error_input_domain_required": specialized,
            "specialized_string_semantics_allowed": False if specialized else True,
        },
    }
    support = {
        "schema_version": 1,
        "route_key": route_key,
        "capabilities": [
            {
                "id": "typed-pure-function-v1",
                "status": "conditional" if specialized else "supported",
                "strategy": "compiler-backed-semantic-ir",
                "reason": (
                    "Conditionally supported only for integer, finite-number, and boolean functions "
                    "inside the canonical finite no-error input domain; string semantics and arithmetic-error "
                    "outcomes are blocked. Native analysis, target compilation, separate typed corpora, "
                    "and behavior replay must each pass before local execution may be raised; "
                    "independent/external verification remain NOT_RUN."
                    if specialized
                    else "Supported only inside typed-pure-function-v1 after native analysis, target "
                    "compilation, separate holdout, and representative behavior replay. Independent "
                    "and external certification remain NOT_RUN."
                ),
                "evidence_refs": [
                    "certification/local-development-evidence.json",
                    "certification/local-holdout-evidence.json",
                    "certification/local-representative-evidence.json",
                ],
            },
            {
                "id": "primitive-types",
                "status": "conditional" if specialized else "supported",
                "strategy": "exact-type-mapping",
                "reason": (
                    "Integer, finite IEEE-754 binary64 number, and boolean are mapped explicitly only "
                    "inside the canonical finite no-error input domain. String is not in the specialized profile."
                    if specialized
                    else "Integer, number, boolean, and string are mapped explicitly in the bounded profile."
                ),
                "evidence_refs": ["mappings/types.json"],
            },
            *(
                [
                    {
                        "id": "canonical-finite-no-error-input-domain",
                        "status": "supported",
                        "strategy": "explicit-domain-precondition",
                        "reason": "All three local type corpora and formal obligations are scoped to inputs "
                        "for which source and target arithmetic error flags are both zero.",
                        "evidence_refs": [
                            "lowering/profile.json",
                            "certification/local-development-evidence.json",
                            "certification/local-holdout-evidence.json",
                            "certification/local-representative-evidence.json",
                        ],
                    },
                    {
                        "id": "string-semantics",
                        "status": "blocked",
                        "strategy": "dedicated-string-contract-required",
                        "reason": "Unicode normalization, code-unit encoding, and equality contracts differ; "
                        "the specialized exact routes reject string before artifact production.",
                        "evidence_refs": ["certification/local-negative-evidence.json"],
                    },
                    {
                        "id": "arithmetic-error-domain",
                        "status": "blocked",
                        "strategy": "separate-error-semantics-profile-required",
                        "reason": "Java wrap, C++ undefined behavior, and Swift traps are not claimed equivalent; "
                        "out-of-domain arithmetic-error inputs remain BLOCKED/NOT_SUPPORTED.",
                        "evidence_refs": [],
                    },
                    {
                        "id": "finite-number-transport-comparison",
                        "status": "conditional",
                        "strategy": "fp64-bit-exact-native-replay",
                        "reason": "Finite binary64 parameters may be transported, returned, branched on, "
                        "and compared; the holdout contract requires negative zero and finite boundary values.",
                        "evidence_refs": ["certification/local-holdout-evidence.json"],
                    },
                    {
                        "id": "number-arithmetic",
                        "status": "blocked",
                        "strategy": "dedicated-fp-arithmetic-contract-required",
                        "reason": "Number +, -, *, /, and % remain outside the exact-eight profile because "
                        "finite inputs can produce infinities/NaNs and rounding/payload behavior is unproved.",
                        "evidence_refs": [],
                    },
                ]
                if specialized
                else []
            ),
            {
                "id": "if-return-control-flow",
                "status": "supported",
                "strategy": "typed-structured-lowering",
                "reason": "If and return statements are lowered from compiler-backed syntax trees.",
                "evidence_refs": ["lowering/profile.json"],
            },
            {
                "id": "framework-database-async-concurrency",
                "status": "blocked",
                "strategy": "separate-exact-pack",
                "reason": "Requires exact Batch 30/31 packs and independent runtime evidence; "
                "it is not hidden in this route.",
                "evidence_refs": [],
            },
            {
                "id": "typed-pure-module-v1",
                "status": "conditional" if specialized else "blocked",
                "strategy": "per-function-proof-plus-module-composition",
                "reason": (
                    "Requires at least three independently observed functions, exact symbol/signature "
                    "closure, semantic chunks, behavior replay, and module composition evidence."
                    if specialized
                    else "This legacy route has not requested the separate module profile."
                ),
                "evidence_refs": [],
            },
        ],
    }
    write_json(route / "route.json", route_manifest)
    write_json(route / "support-matrix.json", support)
    write_json(
        route / "lowering" / "profile.json",
        {
            "schema_version": 1,
            "profile": "typed-pure-function-v1",
            "statements": ["if", "return"],
            "expressions": ["name", "literal", "binary"],
            "operators": [
                "+",
                "-",
                "*",
                "/",
                "%",
                "<",
                "<=",
                ">",
                ">=",
                "==",
                "!=",
                "&&",
                "||",
            ],
            "operator_domains": (
                {
                    "integer_arithmetic": {
                        "operators": ["+", "-", "*", "/", "%"],
                        "status": "conditional-safe-domain",
                    },
                    "finite_number_transport_comparison": {
                        "operators": ["<", "<=", ">", ">=", "==", "!="],
                        "status": "conditional",
                    },
                    "number_arithmetic": {
                        "operators": [],
                        "blocked_operators": ["+", "-", "*", "/", "%"],
                        "status": "BLOCKED",
                    },
                    "boolean_logic": {
                        "operators": ["==", "!=", "&&", "||"],
                        "status": "conditional",
                    },
                }
                if specialized
                else {"status": "legacy-profile-defined"}
            ),
            "input_domain": (SPECIALIZED_INPUT_DOMAIN if specialized else "legacy-profile-defined-domain"),
            "out_of_domain_arithmetic_behavior": (
                SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC if specialized else "profile-specific"
            ),
            "concrete_spans_required": specialized,
            "string_semantics": "BLOCKED" if specialized else "PROFILE_DEFINED",
            "fail_closed": True,
        },
    )
    write_json(
        route / "mappings" / "types.json",
        {
            "schema_version": 1,
            "source": source,
            "target": target,
            "types": (["integer", "number", "boolean"] if specialized else ["integer", "number", "boolean", "string"]),
            "type_evidence_corpora": (
                {
                    "integer": "corpus/development",
                    "number": "corpus/holdout",
                    "boolean": "corpus/real-repository",
                }
                if specialized
                else {}
            ),
            "input_domain": (SPECIALIZED_INPUT_DOMAIN if specialized else "legacy-profile-defined-domain"),
            "string_semantics": "BLOCK" if specialized else "PROFILE_DEFINED",
            "out_of_domain_arithmetic_behavior": (
                SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC if specialized else "profile-specific"
            ),
            "unknown_type_policy": "BLOCK",
            "money_policy": "OUT_OF_SCOPE_REQUIRES_DECIMAL_PACK",
        },
    )
    write_json(
        route / "compat-runtime" / "manifest.json",
        {
            "schema_version": 1,
            "route_key": route_key,
            "components": [],
            "budget": {
                "max_components": 0,
                "max_wrapped_callable_ratio": 0.0,
                "prohibited_domains": [
                    "authentication",
                    "authorization",
                    "transaction-core",
                    "money-calculation",
                ],
            },
        },
    )
    certification_root = route / "certification"
    certification_root.mkdir(parents=True, exist_ok=True)
    (certification_root / "gap-inventory.md").write_text(
        f"# {route_key} remaining obligations\n\n"
        "- Execute three physically separate function corpora with the pinned native toolchains.\n"
        "- Execute the typed-pure-module-v1 campaign over at least three functions.\n"
        "- Preserve every unsupported width, identity, ownership, exception, and effect semantic as blocked.\n"
        + (
            "- Keep string semantics and every arithmetic-error-domain input blocked; local zero-unknown "
            "claims apply only inside canonical-finite-no-error-input-domain.\n"
            if specialized
            else ""
        )
        + "- Obtain independent verification and external/customer evidence; both are currently NOT_RUN.\n",
        encoding="utf-8",
    )
    (certification_root / "customer-support-profile.md").write_text(
        f"# {route_key} customer support profile\n\n"
        "Status: `limited / NOT_CERTIFIED`.\n\n"
        "Only the exact typed-pure-function-v1 and evidenced typed-pure-module-v1 subsets may be used. "
        + (
            "The specialized routes are conditional on canonical-finite-no-error-input-domain; only integer, "
            "finite-number, and boolean semantics are locally evidenced. String and arithmetic-error "
            "outcomes remain BLOCKED/NOT_SUPPORTED. "
            if specialized
            else ""
        )
        + "Pointers, ownership, heap state, dynamic dispatch, exceptions outside the canonical arithmetic "
        "contract, concurrency, I/O, frameworks, and undeclared routes remain unsupported.\n",
        encoding="utf-8",
    )
    write_json(
        certification_root / "economics.json",
        {
            "schema_version": 1,
            "route_key": route_key,
            "status": "NOT_RUN",
            "currency": "USD",
            "cost_per_verified_workload": None,
            "manual_hours": None,
            "maintenance_owner": "ELMOS Polyglot Route Maintainers",
            "limitations": ["No customer or production economics evidence has run."],
        },
    )
    return route


def populate_corpus(route: Path, fixtures: Path, source: Language) -> None:
    specialized = route.name in SPECIALIZED_ROUTE_KEYS
    for corpus in CORPORA:
        destination = route / "corpus" / corpus
        destination.mkdir(parents=True, exist_ok=True)
        if specialized:
            profile = SPECIALIZED_CORPUS_PROFILES[corpus]
            source_name = str(profile["class_name"]) if source == "java" else str(profile["module_name"])
            source_file = destination / f"{source_name}.{EXTENSIONS[source]}"
            source_file.write_text(specialized_corpus_source(source, corpus), encoding="utf-8")
            cases_path = destination / "cases.json"
            cases_path.write_text(
                json.dumps(profile["cases"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            function_name = str(profile["function_name"])
            type_coverage = list(profile["type_coverage"])
        else:
            fixture_source, function_name, cases = source_path(fixtures, corpus, source)
            source_file = destination / fixture_source.name
            shutil.copy2(fixture_source, source_file)
            cases_path = destination / "cases.json"
            shutil.copy2(cases, cases_path)
            type_coverage = ["legacy-profile-defined"]
        write_json(
            destination / "manifest.json",
            {
                "schema_version": 1,
                "corpus": corpus,
                "source_language": source,
                "source_file": source_file.name,
                "cases_file": "cases.json",
                "function_name": function_name,
                "type_coverage": type_coverage,
                "input_domain": (SPECIALIZED_INPUT_DOMAIN if specialized else "legacy-profile-defined-domain"),
                "rule_authoring_input": corpus == "development",
                "independent": corpus != "development",
                "evidence_class": (
                    "development-fixture"
                    if corpus == "development"
                    else "independent-holdout"
                    if corpus == "holdout"
                    else "representative-bounded-fixture"
                ),
                "customer_repository": False,
            },
        )


def populate_module_corpus(route: Path, fixtures: Path, source: Language) -> None:
    """Copy the exact, explicitly mapped module fixture into one route pack."""

    filename = MODULE_FIXTURE_FILES.get(source)
    if filename is None:
        raise RuntimeError(f"MODULE_FIXTURE_LANGUAGE_UNDECLARED:{source}")
    fixture_root = fixtures / "module"
    source_file = fixture_root / source / filename
    cases_file = fixture_root / "cases.json"
    if not source_file.is_file() or not cases_file.is_file():
        raise RuntimeError(f"MODULE_FIXTURE_MISSING:{source}")
    destination = route / "corpus" / "module"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, destination / filename)
    shutil.copy2(cases_file, destination / "cases.json")
    write_json(
        destination / "manifest.json",
        {
            "schema_version": 1,
            "corpus": "module",
            "profile": "typed-pure-module-v1",
            "input_domain": SPECIALIZED_INPUT_DOMAIN,
            "type_coverage_required": ["integer", "number", "boolean"],
            "source_language": source,
            "source_file": filename,
            "cases_file": "cases.json",
            "minimum_function_count": 3,
            "independent_functions": True,
            "call_graph": [],
            "rule_authoring_input": False,
            "independent": True,
            "evidence_class": "independent-module-composition-fixture",
            "customer_repository": False,
        },
    )


def execute_module_route(
    repo: Path,
    route: Path,
    fixtures: Path,
    source: Language,
    target: Language,
) -> tuple[dict[str, str | int], dict[str, str | int]]:
    """Run and persist the real three-function module verification campaign."""

    populate_module_corpus(route, fixtures, source)
    module_root = route / "corpus" / "module"
    module_manifest = json.loads((module_root / "manifest.json").read_text(encoding="utf-8"))
    source_file = module_root / str(module_manifest["source_file"])
    cases_file = module_root / str(module_manifest["cases_file"])
    with tempfile.TemporaryDirectory(prefix=f"elmos-module-{source}-to-{target}-") as temporary:
        generated = Path(temporary) / "module"
        report = migrate_module(
            source_file,
            source,
            target,
            cases_file,
            generated,
        )
        if (
            report.get("status") != "PASSED"
            or report.get("local_verification_status") != "PASSED"
            or report.get("certification_status") != "NOT_CERTIFIED"
            or report.get("external_verification_status") != "NOT_RUN"
        ):
            raise RuntimeError(f"MODULE_EQUIVALENCE_NON_PASSING:{route.name}")
        write_json(generated / "typed-pure-module-equivalence.json", report)
        manifest_ref = persist_artifact_directory(repo, route, "module", generated)

    artifact_prefix = "certification/artifacts/module/"
    route_report = json.loads(json.dumps(report))
    for reference in route_report["artifact_refs"]:
        reference["path"] = artifact_prefix + str(reference["path"])
    for function in route_report["functions"]:
        formal = function["layers"]["formal"]
        for field in (
            "formal_input_path",
            "solver_input_path",
            "formal_result_path",
        ):
            formal[field] = artifact_prefix + str(formal[field])
    report_path = route / "certification" / "module-equivalence.json"
    write_json(report_path, route_report)
    return artifact_ref(route, report_path), manifest_ref


def execute_route(repo: Path, fixtures: Path, source: Language, target: Language) -> None:
    route = configure_route(repo, source, target)
    populate_corpus(route, fixtures, source)
    reports: dict[str, dict[str, Any]] = {}
    artifact_manifests: dict[str, dict[str, str | int]] = {}
    with tempfile.TemporaryDirectory(prefix=f"elmos-{source}-to-{target}-") as temporary:
        root = Path(temporary)
        for corpus in CORPORA:
            corpus_root = route / "corpus" / corpus
            corpus_manifest = json.loads((corpus_root / "manifest.json").read_text(encoding="utf-8"))
            source_file = corpus_root / str(corpus_manifest["source_file"])
            function_name = str(corpus_manifest["function_name"])
            cases = corpus_root / str(corpus_manifest["cases_file"])
            generated = root / corpus
            report = migrate(source_file, source, target, function_name, cases, generated)
            report["corpus"] = corpus
            report["executor"] = "local-toolchain"
            report["independent_verifier"] = "NOT_RUN"
            report["authorization"] = "local-engineering-validation"
            report["route_maturity"] = "LIMITED"
            report["certification_status"] = "NOT_CERTIFIED"
            inputs = generated / "inputs"
            inputs.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, inputs / source_file.name)
            shutil.copy2(cases, inputs / "cases.json")
            write_json(generated / "route-evidence.json", report)
            manifest_ref = persist_artifact_directory(repo, route, corpus, generated)
            artifact_manifests[corpus] = manifest_ref
            report["artifact_root"] = f"certification/artifacts/{corpus}"
            report["artifact_manifest"] = manifest_ref
            reports[corpus] = report
            evidence_name = {
                "development": "local-development-evidence.json",
                "holdout": "local-holdout-evidence.json",
                "real-repository": "local-representative-evidence.json",
            }[corpus]
            write_json(route / "certification" / evidence_name, report)
    negative_ref = execute_negative(route, fixtures, source, target)
    evidence = {
        "schema_version": 1,
        "route_key": f"{source}-to-{target}",
        "route_version": "1.0.0",
        "route_maturity": "LIMITED",
        "execution_status": "PASSED_LOCAL",
        "metrics": {
            "build_green_rate": 1.0,
            "first_build_pass_rate": 1.0,
            "p0_behavior_pass_rate": 1.0,
            "source_map_coverage": 1.0,
            "manual_hours": 0,
            "cost_per_verified_workload": 0,
        },
        "critical_unknown_semantics": 0,
        "critical_behavior_regressions": 0,
        "test_integrity_violations": 0,
        "runs": [
            "certification/local-development-evidence.json",
            "certification/local-holdout-evidence.json",
            "certification/local-representative-evidence.json",
        ],
        "negative_runs": [negative_ref],
        "artifact_refs": list(artifact_manifests.values()),
        "artifact_manifests": artifact_manifests,
        "notes": [
            "The exact typed-pure-function-v1 profile passed native source analysis, "
            "native target compilation, and behavior replay.",
            "Each corpus output directory is persisted under certification/artifacts and bound "
            "by a path, SHA-256, and byte-count manifest.",
            "The physically separate holdout and representative bounded fixture were not used to author route rules.",
            "Independent verifier, customer repository, framework, database, production, "
            "and external certification evidence remain NOT_RUN.",
        ],
    }
    if f"{source}-to-{target}" in SPECIALIZED_ROUTE_KEYS:
        evidence["input_domain"] = SPECIALIZED_INPUT_DOMAIN
        evidence["out_of_domain_arithmetic_behavior"] = SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
        evidence["evidenced_type_coverage"] = ["integer", "number", "boolean"]
        evidence["notes"].append(
            "critical_unknown_semantics=0 is scoped only to canonical-finite-no-error-input-domain; "
            "string semantics and arithmetic-error-domain behavior remain blocked."
        )
    write_json(route / "certification" / "evidence.json", evidence)
    certification = {
        "schema_version": 1,
        "route_key": f"{source}-to-{target}",
        "route_version": "1.0.0",
        "status": "limited",
        "certification_decision": "NOT_CERTIFIED",
        "declared_scope": "typed-pure-function-v1",
        "issued_at": datetime.now(UTC).isoformat(),
        "next_review_at": "2026-10-26T00:00:00+00:00",
        "metrics": evidence["metrics"],
        "evidence_refs": evidence["runs"],
        "gate_results": {
            "local_execution": "PASSED",
            "external_execution": "NOT_RUN",
            "independent_verification": "NOT_RUN",
        },
    }
    write_json(route / "certification" / "certification.json", certification)
    formal_ref = build_formal_equivalence_evidence(
        repo,
        route,
        source,
        target,
        reports,
    )
    certification["evidence_format"] = 2
    certification["formal_equivalence"] = formal_ref
    certification["evidence_refs"] = [
        *certification["evidence_refs"],
        str(formal_ref["path"]),
    ]
    if f"{source}-to-{target}" in SPECIALIZED_ROUTE_KEYS:
        module_ref, module_manifest_ref = execute_module_route(
            repo,
            route,
            fixtures,
            source,
            target,
        )
        certification["module_equivalence"] = module_ref
        certification["declared_scope"] = "typed-pure-function-v1+typed-pure-module-v1"
        certification["gate_results"]["module_execution"] = "PASSED"
        certification["evidence_refs"].extend([str(module_ref["path"]), str(module_manifest_ref["path"])])
        evidence["module_equivalence"] = module_ref
        evidence["module_execution_status"] = "PASSED_LOCAL"
        evidence["module_artifact_manifest"] = module_manifest_ref
        evidence["artifact_refs"].append(module_manifest_ref)
        evidence["notes"].append(
            "The typed-pure-module-v1 run composed at least three independently observed functions "
            "covering integer, finite-number, and boolean semantics with exact symbol/signature "
            "closure and byte-bound per-function proof artifacts."
        )
    write_json(route / "certification" / "certification.json", certification)
    evidence["formal_equivalence"] = formal_ref
    write_json(route / "certification" / "evidence.json", evidence)


def write_route_gate_documents(route: Path, source: Language, target: Language) -> None:
    specialized = f"{source}-to-{target}" in SPECIALIZED_ROUTE_KEYS
    module_line = (
        "- Five-function typed-pure module composition (integer/finite-number/boolean): `PASSED`\n"
        if specialized
        else ""
    )
    declared_profile = (
        "`typed-pure-function-v1` plus `typed-pure-module-v1`" if specialized else "`typed-pure-function-v1`"
    )
    (route / "certification" / "gate-report.md").write_text(
        f"# {source}-to-{target} route gate\n\n"
        "- Local bounded profile: `PASSED`\n"
        "- Route status: `limited`\n"
        "- Native source analyzer: `PASSED`\n"
        "- Native target compiler/runtime: `PASSED`\n"
        "- Development, holdout, and representative behavior: `PASSED`\n"
        f"{module_line}"
        + (
            "- Input domain: `canonical-finite-no-error-input-domain`\n"
            "- String semantics and number arithmetic: `BLOCKED`\n"
            if specialized
            else ""
        )
        + "- Independent verifier: `NOT_RUN`\n"
        "- External/customer certification: `NOT_RUN`\n\n"
        f"The route is supported only for {declared_profile}. "
        + (
            "Local zero-unknown claims apply only to integer, finite-number transport/comparison, "
            "and boolean semantics inside the canonical finite no-error input domain. "
            if specialized
            else ""
        )
        + "Repository orchestration "
        "may process many eligible work units, but unsupported units keep the repository result "
        "`PARTIAL`; unsupported semantics and undeclared directed routes fail closed.\n",
        encoding="utf-8",
    )
    (route / "README.md").write_text(
        f"# {source} to {target}\n\n"
        f"Compiler-backed directed route for {declared_profile}. "
        + (
            "The specialized profile covers integer, finite-number transport/comparison, and boolean; "
            "string, number arithmetic, and out-of-domain arithmetic outcomes are blocked. "
            if specialized
            else ""
        )
        + "The reverse direction is a separate route. Native parsing, target compilation, "
        "and three local behavior corpora pass, so the bounded route is `limited`. "
        "Whole-repository orchestration never broadens the semantic profile; independent "
        "and external certification remain `NOT_RUN`.\n",
        encoding="utf-8",
    )


def execute_specialized_negative(route: Path, fixtures: Path, source: Language, target: Language) -> str:
    route_key = f"{source}-to-{target}"
    expected_case_ids = sorted(
        {
            *SPECIALIZED_NEGATIVE_CASES[source],
            *SPECIALIZED_NEGATIVE_CASES[target],
            "specialized-non-finite-case-unsupported",
            "specialized-number-arithmetic-unsupported",
            "specialized-overflow-outside-no-error-domain",
            "specialized-string-semantics-unsupported",
            "undeclared-directed-route-fails-closed",
            "missing-symbol-fails-closed",
        }
    )
    negative_root = route / "corpus" / "negative"
    negative_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for case_id in expected_case_ids:
        if case_id == "specialized-number-arithmetic-unsupported":
            number_sources = {
                "java": (
                    "NumberArithmetic.java",
                    "public final class NumberArithmetic {\n"
                    "    public static double addNumber(double left, double right) { "
                    "return left + right; }\n"
                    "}\n",
                ),
                "cpp": (
                    "number_arithmetic.cpp",
                    "double addNumber(double left, double right) { return left + right; }\n",
                ),
                "objc": (
                    "number_arithmetic.m",
                    "#import <Foundation/Foundation.h>\n"
                    "double addNumber(double left, double right) { return left + right; }\n",
                ),
                "swift": (
                    "number_arithmetic.swift",
                    "func addNumber(_ left: Double, _ right: Double) -> Double { return left + right }\n",
                ),
            }
            filename, content = number_sources[source]
            number_source = negative_root / filename
            number_source.write_text(content, encoding="utf-8")
            number_cases = negative_root / "number_arithmetic_cases.json"
            number_cases.write_text(
                json.dumps(
                    [{"args": [1.25, 2.5], "expected": 3.75}],
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            with tempfile.TemporaryDirectory(prefix=f"elmos-specialized-number-arithmetic-{route_key}-") as temporary:
                output = Path(temporary) / "must-not-exist"
                try:
                    migrate(
                        number_source,
                        source,
                        target,
                        "addNumber",
                        number_cases,
                        output,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError("SPECIALIZED_NUMBER_ARITHMETIC_UNEXPECTEDLY_PASSED")
                if output.exists():
                    raise RuntimeError("SPECIALIZED_NUMBER_ARITHMETIC_CREATED_ARTIFACTS")
            expected_fragments = (f"SPECIALIZED_NUMBER_ARITHMETIC_UNSUPPORTED:{route_key}:addNumber",)
            input_refs = [
                artifact_ref(route, number_source),
                artifact_ref(route, number_cases),
            ]
        elif case_id == "specialized-non-finite-case-unsupported":
            holdout_manifest = json.loads((route / "corpus" / "holdout" / "manifest.json").read_text(encoding="utf-8"))
            non_finite_source = route / "corpus" / "holdout" / str(holdout_manifest["source_file"])
            non_finite_cases = negative_root / "non_finite_number_cases.json"
            non_finite_cases.write_text('[{"args":[1e400],"expected":0.0}]\n', encoding="utf-8")
            function_name = str(holdout_manifest["function_name"])
            with tempfile.TemporaryDirectory(prefix=f"elmos-specialized-non-finite-{route_key}-") as temporary:
                output = Path(temporary) / "must-not-exist"
                try:
                    migrate(
                        non_finite_source,
                        source,
                        target,
                        function_name,
                        non_finite_cases,
                        output,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError("SPECIALIZED_NON_FINITE_UNEXPECTEDLY_PASSED")
                if output.exists():
                    raise RuntimeError("SPECIALIZED_NON_FINITE_CREATED_ARTIFACTS")
            expected_fragments = (f"SPECIALIZED_CASE_NON_FINITE_NUMBER_UNSUPPORTED:{route_key}:{function_name}:0",)
            input_refs = [
                artifact_ref(route, non_finite_source),
                artifact_ref(route, non_finite_cases),
            ]
        elif case_id == "specialized-overflow-outside-no-error-domain":
            development_manifest = json.loads(
                (route / "corpus" / "development" / "manifest.json").read_text(encoding="utf-8")
            )
            overflow_source = route / "corpus" / "development" / str(development_manifest["source_file"])
            overflow_cases = negative_root / "canonical_overflow_cases.json"
            overflow_cases.write_text(
                json.dumps(
                    [
                        {
                            "args": [9223372036854775807, 1],
                            "expected": -9223372036854775808,
                        }
                    ],
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            function_name = str(development_manifest["function_name"])
            with tempfile.TemporaryDirectory(prefix=f"elmos-specialized-overflow-{route_key}-") as temporary:
                output = Path(temporary) / "must-not-exist"
                try:
                    migrate(
                        overflow_source,
                        source,
                        target,
                        function_name,
                        overflow_cases,
                        output,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError("SPECIALIZED_OVERFLOW_UNEXPECTEDLY_PASSED")
                if output.exists():
                    raise RuntimeError("SPECIALIZED_OVERFLOW_CREATED_ARTIFACTS")
            expected_fragments = (
                f"SPECIALIZED_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN:{route_key}:{function_name}:0:IntegerOverflow",
            )
            input_refs = [
                artifact_ref(route, overflow_source),
                artifact_ref(route, overflow_cases),
            ]
        elif case_id == "specialized-string-semantics-unsupported":
            string_sources = {
                "java": (
                    "CanonicalStringEquality.java",
                    "public final class CanonicalStringEquality {\n"
                    "    public static boolean same(String left, String right) { "
                    "return true; }\n"
                    "}\n",
                ),
                "cpp": (
                    "canonical_string_equality.cpp",
                    "#include <string>\n"
                    "bool same(const std::string &left, const std::string &right) { "
                    "return left == right; }\n",
                ),
                "objc": (
                    "canonical_string_equality.m",
                    "#import <Foundation/Foundation.h>\n"
                    "BOOL same(NSString *left, NSString *right) { "
                    "return [left isEqualToString:right]; }\n",
                ),
                "swift": (
                    "canonical_string_equality.swift",
                    "func same(_ left: String, _ right: String) -> Bool { return left == right }\n",
                ),
            }
            filename, content = string_sources[source]
            string_source = negative_root / filename
            string_source.write_text(content, encoding="utf-8")
            string_cases = negative_root / "canonical_string_cases.json"
            string_cases.write_text(
                json.dumps(
                    [
                        {"args": ["same", "same"], "expected": True},
                        {"args": ["left", "right"], "expected": False},
                        {"args": ["é", "é"], "expected": False},
                    ],
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            with tempfile.TemporaryDirectory(prefix=f"elmos-specialized-string-{route_key}-") as temporary:
                output = Path(temporary) / "must-not-exist"
                try:
                    migrate(
                        string_source,
                        source,
                        target,
                        "same",
                        string_cases,
                        output,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError("SPECIALIZED_STRING_UNEXPECTEDLY_PASSED")
                if output.exists():
                    raise RuntimeError("SPECIALIZED_STRING_CREATED_ARTIFACTS")
            expected_fragments = (f"SPECIALIZED_STRING_SEMANTICS_UNSUPPORTED:{route_key}",)
            input_refs = [
                artifact_ref(route, string_source),
                artifact_ref(route, string_cases),
            ]
        elif case_id == "missing-symbol-fails-closed":
            development_manifest = json.loads(
                (route / "corpus" / "development" / "manifest.json").read_text(encoding="utf-8")
            )
            missing_source = route / "corpus" / "development" / str(development_manifest["source_file"])
            missing_cases = route / "corpus" / "development" / "cases.json"
            with tempfile.TemporaryDirectory(prefix=f"elmos-missing-symbol-{route_key}-") as temporary:
                try:
                    migrate(
                        missing_source,
                        source,
                        target,
                        "__elmos_missing_function__",
                        missing_cases,
                        Path(temporary) / "output",
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError("MISSING_SYMBOL_UNEXPECTEDLY_PASSED")
            expected_fragments = ("FUNCTION_NOT_FOUND", "NO_SUPPORTED_FUNCTIONS")
            input_refs = [
                artifact_ref(route, missing_source),
                artifact_ref(route, missing_cases),
            ]
        elif case_id == "undeclared-directed-route-fails-closed":
            module_source = fixtures / "module" / "java" / MODULE_FIXTURE_FILES["java"]
            module_cases = fixtures / "module" / "cases.json"
            undeclared_source = negative_root / "undeclared_java_to_swift.java"
            undeclared_cases = negative_root / "undeclared_java_to_swift_cases.json"
            shutil.copy2(module_source, undeclared_source)
            shutil.copy2(module_cases, undeclared_cases)
            with tempfile.TemporaryDirectory(prefix=f"elmos-undeclared-{route_key}-") as temporary:
                output = Path(temporary) / "must-not-exist"
                try:
                    migrate_module(
                        undeclared_source,
                        "java",
                        "swift",
                        undeclared_cases,
                        output,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError("UNDECLARED_DIRECTED_ROUTE_UNEXPECTEDLY_PASSED")
                if output.exists():
                    raise RuntimeError("UNDECLARED_DIRECTED_ROUTE_CREATED_ARTIFACTS")
            expected_fragments = ("UNSUPPORTED_DIRECTED_ROUTE:java-to-swift",)
            input_refs = [
                artifact_ref(route, undeclared_source),
                artifact_ref(route, undeclared_cases),
            ]
        elif case_id == "swift-helper-tamper":
            expected_helper = _SWIFT_HELPERS["non_zero_double"]
            tampered_helper = expected_helper.replace("    return value\n", "    return -value\n", 1)
            if tampered_helper == expected_helper:
                raise RuntimeError("SWIFT_HELPER_TAMPER_FIXTURE_NOT_MUTATED")
            source_path = negative_root / "swift_helper_tamper.swift"
            source_path.write_text(
                tampered_helper + "\nfunc quotient(_ left: Double, _ right: Double) -> Double { "
                "return left / elmosNonZero(right) }\n",
                encoding="utf-8",
            )
            try:
                analyze(source_path, "swift", "quotient", emitted_target=True)
            except RouteError as exc:
                reason = str(exc)
            else:
                raise RuntimeError("SWIFT_HELPER_TAMPER_UNEXPECTEDLY_PASSED")
            expected_fragments = ("EMITTED_HELPER_SOURCE_MISMATCH:swift",)
            input_refs = [artifact_ref(route, source_path)]
        else:
            specification = SPECIALIZED_NEGATIVE_SOURCES.get(case_id)
            if specification is None:
                raise RuntimeError(f"SPECIALIZED_NEGATIVE_CASE_UNDECLARED:{case_id}")
            language, filename, function_name, content, expected_fragments = specification
            source_path = negative_root / filename
            source_path.write_text(content, encoding="utf-8")
            try:
                analyze(source_path, language, function_name)
            except RouteError as exc:
                reason = str(exc)
            else:
                raise RuntimeError(f"SPECIALIZED_NEGATIVE_UNEXPECTEDLY_PASSED:{case_id}")
            input_refs = [artifact_ref(route, source_path)]
        matched_reason_code = next((fragment for fragment in expected_fragments if fragment in reason), None)
        if matched_reason_code is None:
            raise RuntimeError(f"SPECIALIZED_NEGATIVE_WRONG_FAILURE:{case_id}:{reason}")
        results.append(
            {
                "case_id": case_id,
                "status": "PASSED",
                "expected_result": "BLOCKED",
                "observed_reason": matched_reason_code,
                "input_refs": input_refs,
                "native_analysis": "EXECUTED",
                "target_execution": "NOT_REACHED_BY_DESIGN",
            }
        )
    write_json(
        negative_root / "manifest.json",
        {
            "schema_version": 1,
            "route_key": route_key,
            "case_ids": expected_case_ids,
            "independent": True,
            "rule_authoring_input": False,
            "expected_result": "BLOCKED",
        },
    )
    relative = "certification/local-negative-evidence.json"
    write_json(
        route / relative,
        {
            "schema_version": 1,
            "route": route_key,
            "status": "PASSED",
            "expected_result": "BLOCKED",
            "test_integrity": "PRESERVED",
            "cases": results,
            "independent_verifier": "NOT_RUN",
            "external_certification": "NOT_RUN",
        },
    )
    write_route_gate_documents(route, source, target)
    return relative


def execute_negative(route: Path, fixtures: Path, source: Language, target: Language) -> str:
    if f"{source}-to-{target}" in SPECIALIZED_ROUTE_KEYS:
        return execute_specialized_negative(route, fixtures, source, target)
    source_file, _, cases = source_path(fixtures, "development", source)
    with tempfile.TemporaryDirectory(prefix=f"elmos-negative-{source}-to-{target}-") as temporary:
        try:
            migrate(
                source_file,
                source,
                target,
                "__elmos_missing_function__",
                cases,
                Path(temporary) / "output",
            )
        except RouteError as exc:
            reason = str(exc)
        else:
            raise RuntimeError(f"NEGATIVE_CASE_UNEXPECTEDLY_PASSED:{source}-to-{target}")
    if not any(code in reason for code in ("FUNCTION_NOT_FOUND", "NO_SUPPORTED_FUNCTIONS")):
        raise RuntimeError(f"NEGATIVE_CASE_WRONG_FAILURE:{source}-to-{target}:{reason}")
    relative = "certification/local-negative-evidence.json"
    write_json(
        route / relative,
        {
            "schema_version": 1,
            "status": "PASSED",
            "route": f"{source}-to-{target}",
            "case": "missing-function-fails-closed",
            "expected_result": "BLOCKED",
            "observed_reason": reason,
            "source_native_analyzer": "EXECUTED",
            "target_execution": "NOT_REACHED_BY_DESIGN",
            "test_integrity": "PRESERVED",
            "independent_verifier": "NOT_RUN",
            "external_certification": "NOT_RUN",
        },
    )
    write_route_gate_documents(route, source, target)
    return relative


def current_engine_source_binding(repo: Path, route_root: Path) -> tuple[bool, str]:
    """Return whether persisted local evidence still binds the live engine bytes."""

    manifest_path = route_root / "certification" / "formal-artifacts" / "engine-source-manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return False, "ENGINE_SOURCE_MANIFEST_MISSING"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False, "ENGINE_SOURCE_MANIFEST_INVALID"
    files = manifest.get("files")
    if not isinstance(files, list) or not files or manifest.get("file_count") != len(files):
        return False, "ENGINE_SOURCE_MANIFEST_INVALID"

    repo_root = repo.resolve()
    route_resolved = route_root.resolve()
    for record in files:
        if not isinstance(record, dict):
            return False, "ENGINE_SOURCE_MANIFEST_INVALID"
        repository_path = record.get("repository_path")
        captured_path = record.get("captured_path")
        expected_sha256 = record.get("sha256")
        expected_bytes = record.get("bytes")
        if (
            not isinstance(repository_path, str)
            or not repository_path
            or not isinstance(captured_path, str)
            or not captured_path
            or not isinstance(expected_sha256, str)
            or not expected_sha256.startswith("sha256:")
            or not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes < 0
        ):
            return False, "ENGINE_SOURCE_MANIFEST_INVALID"
        candidates = (
            (repo_root, repo_root / repository_path),
            (route_resolved, route_resolved / captured_path),
        )
        for allowed_root, candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(allowed_root)
            except (OSError, RuntimeError, ValueError):
                return False, "ENGINE_SOURCE_ARTIFACT_INVALID"
            if candidate.is_symlink() or not resolved.is_file():
                return False, "ENGINE_SOURCE_ARTIFACT_INVALID"
            try:
                payload = resolved.read_bytes()
            except OSError:
                return False, "ENGINE_SOURCE_ARTIFACT_INVALID"
            if len(payload) != expected_bytes:
                return False, "ENGINE_SOURCE_EVIDENCE_STALE"
            actual_sha256 = f"sha256:{hashlib.sha256(payload).hexdigest()}"
            if actual_sha256 != expected_sha256:
                return False, "ENGINE_SOURCE_EVIDENCE_STALE"
    return True, "ENGINE_SOURCE_EVIDENCE_CURRENT"


def write_inventory(repo: Path) -> None:
    routes: list[dict[str, Any]] = []
    for route_key in EVIDENCED_ROUTE_KEYS:
        source_value, target_value = split_route_key(route_key)
        route_root = repo / "routes" / route_key
        manifest = json.loads((route_root / "route.json").read_text(encoding="utf-8"))
        evidence = json.loads((route_root / "certification" / "evidence.json").read_text(encoding="utf-8"))
        specialized = route_key in SPECIALIZED_ROUTE_KEYS
        function_passed = evidence.get("execution_status") == "PASSED_LOCAL"
        module_passed = evidence.get("module_execution_status") == "PASSED_LOCAL" if specialized else True
        source_binding_current, source_binding_reason = current_engine_source_binding(repo, route_root)
        if function_passed and module_passed and source_binding_current:
            local_status = "PASSED_LOCAL"
        elif evidence.get("execution_status") == "FAILED" or evidence.get("module_execution_status") == "FAILED":
            local_status = "FAILED"
        else:
            local_status = "NOT_RUN"
        local_execution_reason = (
            "LOCAL_EXECUTION_FAILED"
            if local_status == "FAILED"
            else source_binding_reason
            if function_passed and module_passed
            else "LOCAL_EXECUTION_NOT_RUN"
        )
        routes.append(
            {
                "route_key": route_key,
                "route_set": ("cpp-objc-swift-java-exact-8" if specialized else "legacy-complete-30"),
                "source": source_value,
                "source_version": SHORT_VERSIONS[source_value],
                "target": target_value,
                "target_version": SHORT_VERSIONS[target_value],
                "status": manifest.get("status"),
                "local_execution_status": local_status,
                "local_execution_reason": local_execution_reason,
                "module_execution_status": (
                    (evidence.get("module_execution_status", "NOT_RUN") if source_binding_current else "NOT_RUN")
                    if specialized
                    else "NOT_APPLICABLE"
                ),
                "repository_execution_status": "NOT_RUN",
                "repository_profile": None,
                "repository_evidence_ref": None,
                "repository_evidence_sha256": None,
                "repository_evidence_bytes": None,
                "independent_verification_status": "NOT_RUN",
                "external_certification_status": "NOT_RUN",
            }
        )
    local_statuses = {entry["local_execution_status"] for entry in routes}
    aggregate_local = (
        "FAILED" if "FAILED" in local_statuses else "PASSED_LOCAL" if local_statuses == {"PASSED_LOCAL"} else "NOT_RUN"
    )
    status_counts = {
        status: sum(1 for entry in routes if entry["status"] == status)
        for status in ("research", "experimental", "limited", "blocked", "certified")
    }
    write_json(
        repo / "routes" / "inventory.json",
        {
            "schema_version": "1.3.0",
            "route_policy": {
                "mode": "explicit-route-sets",
                "cartesian_expansion": "FORBIDDEN",
                "complete_route_set": "legacy-complete-30",
                "specialized_route_set": "cpp-objc-swift-java-exact-8",
            },
            "route_sets": {
                "legacy-complete-30": {
                    "policy": "complete-directed-permutation",
                    "languages": list(CORE_LANGUAGES),
                    "route_count": len(CORE_ROUTE_KEYS),
                    "route_keys": list(CORE_ROUTE_KEYS),
                },
                "cpp-objc-swift-java-exact-8": {
                    "policy": "exact-explicit-set",
                    "languages": ["cpp", "objc", "swift", "java"],
                    "route_count": len(SPECIALIZED_ROUTE_KEYS),
                    "route_keys": list(SPECIALIZED_ROUTE_KEYS),
                    "module_profile": "typed-pure-module-v1",
                },
            },
            "route_count": len(routes),
            "research_route_count": status_counts["research"],
            "experimental_route_count": status_counts["experimental"],
            "limited_route_count": status_counts["limited"],
            "blocked_route_count": status_counts["blocked"],
            "certified_route_count": status_counts["certified"],
            "local_execution_evidence": aggregate_local,
            "independent_verification_evidence": "NOT_RUN",
            "external_certification_evidence": "NOT_RUN",
            "semantic_profile": "typed-pure-function-v1",
            "module_profile": "typed-pure-module-v1",
            "console_exposed_languages": list(CORE_LANGUAGES),
            "languages": {
                language: {
                    "version": SHORT_VERSIONS[language],
                    "engine_path": ENGINE_PATHS[language],
                }
                for language in (*CORE_LANGUAGES, *SPECIALIZED_LANGUAGES)
            },
            "routes": routes,
        },
    )


def run_route_checks(repo: Path, route: Path) -> int:
    for script in ("validate_route.py", "run_route_gate.py"):
        completed = subprocess.run(
            [sys.executable, str(repo / "scripts" / "batch29" / script), str(route)],
            cwd=repo,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inventory-only", action="store_true")
    mode.add_argument("--negative-only", action="store_true")
    mode.add_argument(
        "--route-set",
        choices=sorted(EXACT_ROUTE_SETS),
        help="execute one immutable declared route set without inferring other pairs",
    )
    mode.add_argument(
        "--prepare-route-set",
        choices=sorted(EXACT_ROUTE_SETS),
        help="prepare complete NOT_RUN route scaffolds without claiming native execution",
    )
    mode.add_argument(
        "--route",
        type=parse_route_key,
        metavar="SOURCE-TO-TARGET",
        help="replay exactly one declared directed route, then run its validator and gate",
    )
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    if args.inventory_only:
        write_inventory(repo)
        print("PASS: exact limited route inventory updated")
        return 0
    fixtures = repo / "engines" / "polyglot-route-engine" / "fixtures"
    if args.prepare_route_set is not None:
        for route_key in EXACT_ROUTE_SETS[args.prepare_route_set]:
            source_value, target_value = split_route_key(route_key)
            source = cast(Language, source_value)
            target = cast(Language, target_value)
            route = configure_route(repo, source, target)
            populate_corpus(route, fixtures, source)
            if route_key in SPECIALIZED_ROUTE_KEYS:
                populate_module_corpus(route, fixtures, source)
            write_not_run_route_scaffold(route, source, target)
        print(f"PASS: prepared exact route set {args.prepare_route_set} as NOT_RUN / NOT_CERTIFIED")
        return 0
    if args.negative_only:
        for route_key in EVIDENCED_ROUTE_KEYS:
            source, target = split_route_key(route_key)
            route = repo / "routes" / route_key
            reference = execute_negative(route, fixtures, source, target)  # type: ignore[arg-type]
            evidence_path = route / "certification" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["negative_runs"] = [reference]
            write_json(evidence_path, evidence)
        print(f"PASS: {len(EVIDENCED_ROUTE_KEYS)} declared route negatives failed closed")
        return 0
    selected = (
        [args.route]
        if args.route is not None
        else [
            split_route_key(route_key)
            for route_key in (EXACT_ROUTE_SETS[args.route_set] if args.route_set is not None else CORE_ROUTE_KEYS)
        ]
    )
    for source, target in selected:
        execute_route(repo, fixtures, source, target)  # type: ignore[arg-type]
        route = repo / "routes" / f"{source}-to-{target}"
        check_result = run_route_checks(repo, route)
        if check_result != 0:
            return check_result
    if args.route is not None:
        source, target = args.route
        print(
            f"PASS: exact route {source}-to-{target} replayed with persisted limited local evidence; "
            "decision remains NOT_CERTIFIED"
        )
        return 0
    write_inventory(repo)
    selected_name = args.route_set or "legacy-complete-30"
    print(f"PASS: exact route set {selected_name} completed with conservative local evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
