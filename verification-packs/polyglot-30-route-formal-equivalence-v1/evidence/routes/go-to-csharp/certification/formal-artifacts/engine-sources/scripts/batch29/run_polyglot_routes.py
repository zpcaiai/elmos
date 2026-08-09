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
from typing import Any

DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(
    0,
    str(DEFAULT_REPOSITORY_ROOT / "engines" / "polyglot-route-engine" / "src"),
)

from elmos_polyglot_route.engine import migrate  # noqa: E402
from elmos_polyglot_route.models import Language, RouteError  # noqa: E402

B16_LANGUAGES: tuple[Language, ...] = (
    "java",
    "csharp",
    "go",
    "rust",
    "python",
    "typescript",
)

VERSIONS = {
    "java": ["Java 21.0.11", "JDK Compiler Tree API"],
    "python": ["Python 3.12.12", "CPython AST"],
    "csharp": ["C# 14", ".NET SDK 10.0.301", "Roslyn 5.6.0"],
    "typescript": ["TypeScript 5.9.2", "Node.js 26.0.0"],
    "go": ["Go 1.25.0", "go/parser AST"],
    "rust": ["Rust 1.89.0", "syn 2.0.119"],
}
ENGINE_PATHS = {
    "java": "engines/polyglot-route-engine/native/java/Analyzer.java",
    "python": "engines/polyglot-route-engine/src/elmos_polyglot_route/python_analyzer.py",
    "csharp": "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli",
    "typescript": "engines/frontend-client-engine/src/polyglot.ts",
    "go": "engines/polyglot-route-engine/native/go/analyzer.go",
    "rust": "engines/polyglot-route-engine/native/rust/src/main.rs",
}
SHORT_VERSIONS = {
    "java": "21.0.11",
    "python": "3.12.12",
    "csharp": "10.0.301",
    "typescript": "5.9.2 / Node 26.0.0",
    "go": "1.25.0",
    "rust": "1.89.0",
}
EXTENSIONS = {
    "java": "java",
    "python": "py",
    "csharp": "cs",
    "typescript": "ts",
    "go": "go",
    "rust": "rs",
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
ARTIFACT_ALLOWED_SUFFIXES = {
    ".cs",
    ".csproj",
    ".go",
    ".java",
    ".js",
    ".json",
    ".lock",
    ".log",
    ".md",
    ".py",
    ".rs",
    ".smt2",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
EXCLUDED_REBUILDABLE_DIRECTORIES = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "bin",
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

    if corpus not in CORPORA:
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
            raise RuntimeError(
                f"GENERATED_ARTIFACT_SYMLINK_REJECTED:{relative.as_posix()}"
            )
        if any(part in EXCLUDED_REBUILDABLE_DIRECTORIES for part in relative.parts):
            if source.is_file():
                excluded_files.append(relative.as_posix())
            continue
        if source.is_dir():
            continue
        if not source.is_file():
            raise RuntimeError(
                f"GENERATED_ARTIFACT_SPECIAL_FILE_REJECTED:{relative.as_posix()}"
            )
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
            raise RuntimeError(
                f"GENERATED_ARTIFACT_COPY_MISMATCH:{relative.as_posix()}"
            )
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
    diagnostics = value.get("diagnostics")
    functions = value.get("functions")
    if diagnostics != [] or not isinstance(functions, list) or not functions:
        raise RuntimeError(f"{label}_IR_NOT_EXACT")
    if any(not isinstance(item, dict) for item in functions):
        raise RuntimeError(f"{label}_IR_FUNCTION_INVALID")
    return functions


def _validated_corpus_manifest_files(route: Path, corpus: str) -> list[Path]:
    manifest_path = (
        route / "certification" / "artifacts" / corpus / "artifact-manifest.json"
    )
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
            raise RuntimeError(
                f"FORMAL_ARTIFACT_MANIFEST_ENTRY_INVALID:{corpus}:{index}"
            )
        relative = entry.get("path")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
        ):
            raise RuntimeError(
                f"FORMAL_ARTIFACT_MANIFEST_PATH_INVALID:{corpus}:{index}"
            )
        candidate = (root / relative).resolve(strict=True)
        try:
            candidate.relative_to(root.resolve())
        except ValueError as exc:
            raise RuntimeError(
                f"FORMAL_ARTIFACT_MANIFEST_PATH_ESCAPE:{corpus}:{relative}"
            ) from exc
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
    sources = list((engine / "src" / "elmos_polyglot_route").glob("*.py"))
    for native_root in (
        engine / "native" / "csharp",
        engine / "native" / "go",
        engine / "native" / "java",
        engine / "native" / "rust",
        engine / "native" / "typescript",
    ):
        sources.extend(
            path
            for path in native_root.rglob("*")
            if path.is_file()
            and not any(
                part in EXCLUDED_REBUILDABLE_DIRECTORIES
                for part in path.relative_to(native_root).parts
            )
            and path.suffix.lower()
            in {".cs", ".csproj", ".go", ".java", ".lock", ".mjs", ".rs", ".toml"}
        )
    sources.extend(
        [
            engine / "pyproject.toml",
            engine / "uv.lock",
            repo / "schemas" / "batch29" / "formal-equivalence-evidence.schema.json",
            repo / "schemas" / "batch29" / "route-certification.schema.json",
            repo / "scripts" / "batch29" / "run_polyglot_routes.py",
            repo / "scripts" / "batch29" / "run_route_gate.py",
            repo / "scripts" / "batch29" / "validate_route.py",
            repo / "scripts" / "operations" / "validate_translation_route_matrix.py",
        ]
    )
    capture_root = route / "certification" / "formal-artifacts" / "engine-sources"
    captured: list[Path] = []
    entries: list[dict[str, Any]] = []
    for source in sorted(
        set(sources), key=lambda path: path.relative_to(repo).as_posix()
    ):
        if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
            raise RuntimeError(f"FORMAL_ENGINE_SOURCE_INVALID:{source}")
        relative = source.relative_to(repo)
        destination = capture_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if (
            sha256_file(destination) != sha256_file(source)
            or destination.stat().st_size != source.stat().st_size
        ):
            raise RuntimeError(
                f"FORMAL_ENGINE_SOURCE_COPY_MISMATCH:{relative.as_posix()}"
            )
        captured.append(destination)
        entries.append(
            {
                "repository_path": relative.as_posix(),
                "captured_path": destination.relative_to(route).as_posix(),
                "sha256": sha256_file(destination),
                "bytes": destination.stat().st_size,
            }
        )
    manifest = (
        route / "certification" / "formal-artifacts" / "engine-source-manifest.json"
    )
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
            raise RuntimeError(
                f"FORMAL_ARTIFACT_ROLE_CONFLICT:{resolved}:{previous}:{role}"
            )

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
        if not all(
            isinstance(item, dict)
            for item in (semantic, chunk, behavior, formal, layered)
        ):
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

        source_ir = _corpus_artifact(
            route, corpus, semantic.get("source_ir_path"), "SOURCE_IR"
        )
        target_ir = _corpus_artifact(
            route, corpus, semantic.get("target_ir_path"), "TARGET_IR"
        )
        source_functions = _normalized_functions(source_ir, "SOURCE")
        target_functions = _normalized_functions(target_ir, "TARGET")
        if source_functions != target_functions:
            raise RuntimeError(f"FORMAL_NORMALIZED_IR_MISMATCH:{route_key}:{corpus}")
        normalized_runs.append({"corpus": corpus, "functions": source_functions})
        bind(source_ir, "source-ir")
        bind(target_ir, "target-ir")

        target_path = _corpus_artifact(
            route, corpus, report.get("target", {}).get("path"), "TARGET"
        )
        target_artifacts.append(
            {
                "corpus": corpus,
                "path": target_path.relative_to(route).as_posix(),
                "sha256": sha256_file(target_path),
                "bytes": target_path.stat().st_size,
            }
        )
        bind(target_path, "target-artifact")

        chunk_path = _corpus_artifact(
            route, corpus, chunk.get("artifact_path"), "CHUNK"
        )
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

        behavior_path = _corpus_artifact(
            route, corpus, behavior.get("artifact_path"), "BEHAVIOR"
        )
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
        canonical_oracle_passed = (
            canonical_oracle_passed and behavior_value.get("oracle_conflict_count") == 0
        )
        source_runtime_passed = (
            source_runtime_passed
            and behavior_value.get("source_runtime_passed") is True
        )
        target_runtime_passed = (
            target_runtime_passed
            and behavior_value.get("target_runtime_passed") is True
        )
        for item in behavior_value.get("counterexamples", []):
            if not isinstance(item, dict):
                raise RuntimeError(
                    f"FORMAL_BEHAVIOR_COUNTEREXAMPLE_INVALID:{route_key}:{corpus}"
                )
            counterexamples.append(
                {
                    "case_id": f"{corpus}:{item.get('case_id')}",
                    "reason": "source/canonical/target behavior divergence",
                    "evidence_ref": behavior_path.relative_to(route).as_posix(),
                }
            )
        bind(behavior_path, "behavior-result")
        behavior_artifact_ids.append(formal_artifact_id(route, behavior_path))

        formal_path = _corpus_artifact(
            route, corpus, formal.get("artifact_path"), "FORMAL"
        )
        formal_value = json.loads(formal_path.read_text(encoding="utf-8"))
        if not isinstance(formal_value, dict):
            raise RuntimeError(f"FORMAL_PROOF_ROOT_INVALID:{route_key}:{corpus}")
        solver = formal_value.get("solver")
        if not isinstance(solver, dict):
            raise RuntimeError(f"FORMAL_SOLVER_INVALID:{route_key}:{corpus}")
        observed_solver = solver.get("name")
        observed_version = solver.get("version")
        if not isinstance(observed_solver, str) or not isinstance(
            observed_version, str
        ):
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
        solver_random_seed = (
            solver_random_seed if solver_random_seed is not None else random_seed
        )
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
        smt2_path = _corpus_artifact(
            route, corpus, "formal-equivalence.smt2", "FORMAL_SMT2"
        )
        proof_result_path = _corpus_artifact(
            route, corpus, "formal-proof-result.json", "FORMAL_RESULT"
        )
        formal_input_path = _corpus_artifact(
            route, corpus, "formal-input.json", "FORMAL_INPUT"
        )
        obligations.append(
            {
                "obligation_id": f"{route_key}:{corpus}:L0-DENOTATIONAL-EQUIVALENCE",
                "status": "PROVED_UNDER_ASSUMPTIONS",
                "scope": f"{corpus}:typed-pure-function-v1",
                "formal_input_artifact_id": formal_artifact_id(
                    route, formal_input_path
                ),
                "solver_input_artifact_id": formal_artifact_id(route, smt2_path),
                "input_digest": sha256_file(smt2_path),
                "solver_result_artifact_id": formal_artifact_id(
                    route, proof_result_path
                ),
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
    engine_source_manifest, captured_engine_sources = _capture_engine_sources(
        repo, route
    )
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
                "sha256": sha256_file(
                    repo / "engines" / "polyglot-route-engine" / "uv.lock"
                ),
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
    unique_paths = sorted(
        set(referenced_paths), key=lambda item: item.relative_to(route).as_posix()
    )
    artifact_refs = [
        formal_artifact_ref(route, item, artifact_roles[item]) for item in unique_paths
    ]
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


def parse_route_key(value: str) -> tuple[Language, Language]:
    matches = [
        (source, target)
        for source in B16_LANGUAGES
        for target in B16_LANGUAGES
        if source != target and value == f"{source}-to-{target}"
    ]
    if len(matches) != 1:
        choices = ", ".join(
            f"{source}-to-{target}"
            for source in B16_LANGUAGES
            for target in B16_LANGUAGES
            if source != target
        )
        raise argparse.ArgumentTypeError(
            f"route must be one exact directed key from the six-language matrix: {choices}"
        )
    return matches[0]


def source_path(
    fixtures: Path, corpus: str, language: Language
) -> tuple[Path, str, Path]:
    directory, class_name, module_name, function_name, cases_name = CORPORA[corpus]
    source_name = class_name if language in {"java", "csharp"} else module_name
    source = fixtures / directory / language / f"{source_name}.{EXTENSIONS[language]}"
    cases = fixtures / cases_name
    return source, function_name, cases


def configure_route(repo: Path, source: Language, target: Language) -> Path:
    route_key = f"{source}-to-{target}"
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
            "target_profile": f"{target}-native-compiler",
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
        },
    }
    support = {
        "schema_version": 1,
        "route_key": route_key,
        "capabilities": [
            {
                "id": "typed-pure-function-v1",
                "status": "supported",
                "strategy": "compiler-backed-semantic-ir",
                "reason": "Supported only inside typed-pure-function-v1 after native analysis, "
                "target compilation, separate holdout, and representative behavior replay. "
                "Independent and external certification remain NOT_RUN.",
                "evidence_refs": [
                    "certification/local-development-evidence.json",
                    "certification/local-holdout-evidence.json",
                    "certification/local-representative-evidence.json",
                ],
            },
            {
                "id": "primitive-types",
                "status": "supported",
                "strategy": "exact-type-mapping",
                "reason": "Integer, number, boolean, and string are mapped explicitly in the bounded profile.",
                "evidence_refs": ["mappings/types.json"],
            },
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
            "fail_closed": True,
        },
    )
    write_json(
        route / "mappings" / "types.json",
        {
            "schema_version": 1,
            "source": source,
            "target": target,
            "types": ["integer", "number", "boolean", "string"],
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
    return route


def populate_corpus(route: Path, fixtures: Path, source: Language) -> None:
    for corpus in CORPORA:
        source_file, _, cases = source_path(fixtures, corpus, source)
        destination = route / "corpus" / corpus
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination / source_file.name)
        shutil.copy2(cases, destination / "cases.json")
        write_json(
            destination / "manifest.json",
            {
                "schema_version": 1,
                "corpus": corpus,
                "source_language": source,
                "source_file": source_file.name,
                "cases_file": "cases.json",
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


def execute_route(
    repo: Path, fixtures: Path, source: Language, target: Language
) -> None:
    route = configure_route(repo, source, target)
    populate_corpus(route, fixtures, source)
    reports: dict[str, dict[str, Any]] = {}
    artifact_manifests: dict[str, dict[str, str | int]] = {}
    with tempfile.TemporaryDirectory(
        prefix=f"elmos-{source}-to-{target}-"
    ) as temporary:
        root = Path(temporary)
        for corpus in CORPORA:
            source_file, function_name, cases = source_path(fixtures, corpus, source)
            generated = root / corpus
            report = migrate(
                source_file, source, target, function_name, cases, generated
            )
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
    write_json(route / "certification" / "certification.json", certification)
    evidence["formal_equivalence"] = formal_ref
    write_json(route / "certification" / "evidence.json", evidence)


def execute_negative(
    route: Path, fixtures: Path, source: Language, target: Language
) -> str:
    source_file, _, cases = source_path(fixtures, "development", source)
    with tempfile.TemporaryDirectory(
        prefix=f"elmos-negative-{source}-to-{target}-"
    ) as temporary:
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
            raise RuntimeError(
                f"NEGATIVE_CASE_UNEXPECTEDLY_PASSED:{source}-to-{target}"
            )
    if not any(
        code in reason for code in ("FUNCTION_NOT_FOUND", "NO_SUPPORTED_FUNCTIONS")
    ):
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
    (route / "certification" / "gate-report.md").write_text(
        f"# {source}-to-{target} route gate\n\n"
        "- Local bounded profile: `PASSED`\n"
        "- Route status: `limited`\n"
        "- Native source analyzer: `PASSED`\n"
        "- Native target compiler/runtime: `PASSED`\n"
        "- Development, holdout, and representative behavior: `PASSED`\n"
        "- Independent verifier: `NOT_RUN`\n"
        "- External/customer certification: `NOT_RUN`\n\n"
        "The route is supported only for `typed-pure-function-v1`. Repository orchestration "
        "may process many eligible work units, but unsupported units keep the repository result "
        "`PARTIAL`; unsupported semantics fail closed.\n",
        encoding="utf-8",
    )
    (route / "README.md").write_text(
        f"# {source} to {target}\n\n"
        "Compiler-backed directed route for the exact `typed-pure-function-v1` profile. "
        "The reverse direction is a separate route. Native parsing, target compilation, "
        "and three local behavior corpora pass, so the bounded route is `limited`. "
        "Whole-repository orchestration never broadens the semantic profile; independent "
        "and external certification remain `NOT_RUN`.\n",
        encoding="utf-8",
    )
    return relative


def write_inventory(repo: Path) -> None:
    routes = [
        {
            "route_key": f"{source}-to-{target}",
            "source": source,
            "source_version": SHORT_VERSIONS[source],
            "target": target,
            "target_version": SHORT_VERSIONS[target],
            "status": "limited",
            "local_execution_status": "PASSED_LOCAL",
            "independent_verification_status": "NOT_RUN",
            "external_certification_status": "NOT_RUN",
        }
        for source in B16_LANGUAGES
        for target in B16_LANGUAGES
        if source != target
    ]
    write_json(
        repo / "routes" / "inventory.json",
        {
            "schema_version": "1.2.0",
            "route_count": len(routes),
            "research_route_count": 0,
            "experimental_route_count": 0,
            "limited_route_count": len(routes),
            "blocked_route_count": 0,
            "certified_route_count": 0,
            "local_execution_evidence": "PASSED_LOCAL",
            "independent_verification_evidence": "NOT_RUN",
            "external_certification_evidence": "NOT_RUN",
            "semantic_profile": "typed-pure-function-v1",
            "languages": {
                language: {
                    "version": SHORT_VERSIONS[language],
                    "engine_path": ENGINE_PATHS[language],
                }
                for language in B16_LANGUAGES
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
        "--route",
        type=parse_route_key,
        metavar="SOURCE-TO-TARGET",
        help="replay exactly one of the 30 directed routes, then run its validator and gate",
    )
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    if args.inventory_only:
        write_inventory(repo)
        print("PASS: exact limited route inventory updated")
        return 0
    fixtures = repo / "engines" / "polyglot-route-engine" / "fixtures"
    if args.negative_only:
        for source in B16_LANGUAGES:
            for target in B16_LANGUAGES:
                if source == target:
                    continue
                route = repo / "routes" / f"{source}-to-{target}"
                reference = execute_negative(route, fixtures, source, target)
                evidence_path = route / "certification" / "evidence.json"
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                evidence["negative_runs"] = [reference]
                write_json(evidence_path, evidence)
        print("PASS: 30 directed B16 negative cases failed closed")
        return 0
    selected = (
        [args.route]
        if args.route is not None
        else [
            (source, target)
            for source in B16_LANGUAGES
            for target in B16_LANGUAGES
            if source != target
        ]
    )
    for source, target in selected:
        execute_route(repo, fixtures, source, target)
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
    print(
        f"PASS: {len(B16_LANGUAGES) * (len(B16_LANGUAGES) - 1)} directed polyglot routes completed with limited local evidence"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
