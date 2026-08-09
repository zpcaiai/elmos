#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib
import json
import math
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ENGINE_RUNTIME_MODULES = {
    "elmos_polyglot_route.equivalence": "elmos_polyglot_route/equivalence.py",
    "elmos_polyglot_route.models": "elmos_polyglot_route/models.py",
    "elmos_polyglot_route.engine": "elmos_polyglot_route/engine.py",
    "elmos_polyglot_route.emitter": "elmos_polyglot_route/emitter.py",
    "elmos_polyglot_route.types": "elmos_polyglot_route/types.py",
    "elmos_polyglot_route.canonical": "elmos_polyglot_route/canonical.py",
    "elmos_polyglot_route.native": "elmos_polyglot_route/native.py",
    "elmos_polyglot_route.clang_analyzer": "elmos_polyglot_route/clang_analyzer.py",
    "elmos_polyglot_route.python_analyzer": "elmos_polyglot_route/python_analyzer.py",
    "elmos_polyglot_route.toolchains": "elmos_polyglot_route/toolchains.py",
    "elmos_polyglot_route.validation": "elmos_polyglot_route/validation.py",
}
PINNED_Z3_VERSION = "4.16.0"

SPECIALIZED_NEGATIVE_CASES = {
    "java": frozenset(
        {"java-int-width", "java-string-raw-reference-equality"}
    ),
    "cpp": frozenset({"cpp-long-width", "cpp-unsigned-domain"}),
    "objc": frozenset(
        {"objc-nsinteger-width", "objc-nsstring-pointer-identity"}
    ),
    "swift": frozenset({"swift-int-requires-int64", "swift-helper-tamper"}),
}
SPECIALIZED_COMMON_NEGATIVE_CASES = frozenset(
    {
        "specialized-string-semantics-unsupported",
        "specialized-number-arithmetic-unsupported",
        "specialized-non-finite-case-unsupported",
        "specialized-overflow-outside-no-error-domain",
        "undeclared-directed-route-fails-closed",
        "missing-symbol-fails-closed",
    }
)
SPECIALIZED_NEGATIVE_ANALYZE_SPECS = {
    "java-int-width": ("java", "width", False),
    "java-string-raw-reference-equality": ("java", "same", False),
    "cpp-long-width": ("cpp", "width", False),
    "cpp-unsigned-domain": ("cpp", "unsigned_value", False),
    "objc-nsinteger-width": ("objc", "width", False),
    "objc-nsstring-pointer-identity": ("objc", "same", False),
    "swift-int-requires-int64": ("swift", "width", False),
    "swift-helper-tamper": ("swift", "quotient", True),
}
SPECIALIZED_NEGATIVE_INPUT_ROLES = {
    **{
        case_id: ("source",)
        for case_id in SPECIALIZED_NEGATIVE_ANALYZE_SPECS
    },
    "specialized-string-semantics-unsupported": ("source", "cases"),
    "specialized-number-arithmetic-unsupported": ("source", "cases"),
    "specialized-non-finite-case-unsupported": ("source", "cases"),
    "specialized-overflow-outside-no-error-domain": ("source", "cases"),
    "missing-symbol-fails-closed": ("source", "cases"),
    "undeclared-directed-route-fails-closed": (
        "source-module",
        "case-manifest",
    ),
}
SPECIALIZED_NEGATIVE_STATIC_REASONS = {
    "java-int-width": frozenset(
        {"JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int"}
    ),
    "java-string-raw-reference-equality": frozenset(
        {"JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET"}
    ),
    "cpp-long-width": frozenset(
        {"CPP_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:long"}
    ),
    "cpp-unsigned-domain": frozenset(
        {"CPP_UNSUPPORTED_TYPE:unsigned long long"}
    ),
    "objc-nsinteger-width": frozenset(
        {"OBJC_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:NSInteger"}
    ),
    "objc-nsstring-pointer-identity": frozenset(
        {"OBJC_STRING_POINTER_COMPARISON_OUTSIDE_CERTIFIED_SUBSET"}
    ),
    "swift-int-requires-int64": frozenset(
        {"SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int"}
    ),
    "swift-helper-tamper": frozenset(
        {"EMITTED_HELPER_SOURCE_MISMATCH:swift:non_zero_double:elmosNonZero"}
    ),
    "undeclared-directed-route-fails-closed": frozenset(
        {"SOURCE_AND_TARGET_MUST_DIFFER"}
    ),
}
SPECIALIZED_NEGATIVE_SOURCE_FILES = {
    "java-int-width": "JavaIntWidth.java",
    "java-string-raw-reference-equality": "JavaStringIdentity.java",
    "cpp-long-width": "cpp_long_width.cpp",
    "cpp-unsigned-domain": "cpp_unsigned_domain.cpp",
    "objc-nsinteger-width": "objc_nsinteger_width.m",
    "objc-nsstring-pointer-identity": "objc_nsstring_pointer_identity.m",
    "swift-int-requires-int64": "swift_int_width.swift",
    "swift-helper-tamper": "swift_helper_tamper.swift",
}
SPECIALIZED_NUMBER_ARITHMETIC_SOURCE_FILES = {
    "java": "NumberArithmetic.java",
    "cpp": "number_arithmetic.cpp",
    "objc": "number_arithmetic.m",
    "swift": "number_arithmetic.swift",
}
SPECIALIZED_STRING_SOURCE_FILES = {
    "java": "CanonicalStringEquality.java",
    "cpp": "canonical_string_equality.cpp",
    "objc": "canonical_string_equality.m",
    "swift": "canonical_string_equality.swift",
}

REQUIRED_ROUTE = [
    "schema_version",
    "route_key",
    "version",
    "status",
    "owner",
    "source",
    "target",
    "paths",
    "gates",
]
REQUIRED_DIRS = [
    "lowering",
    "mappings",
    "compat-runtime",
    "corpus/development",
    "corpus/holdout",
    "corpus/real-repository",
    "certification",
]
ALLOWED_ROUTE_STATUS = {
    "research",
    "experimental",
    "limited",
    "certified",
    "deprecated",
    "blocked",
}
ALLOWED_CAP_STATUS = {
    "certified",
    "supported",
    "conditional",
    "experimental",
    "detected-only",
    "blocked",
}
LAYER_STATUSES = {"PASSED", "FAILED", "UNKNOWN", "NOT_RUN"}
PROOF_STATUSES = {
    "PROVED",
    "PROVED_UNDER_ASSUMPTIONS",
    "AXIOM",
    "BOUNDED",
    "UNKNOWN",
    "TIMEOUT",
    "NOT_RUN",
    "COUNTEREXAMPLE",
}
CHUNK_STATUSES = {"MATCHED", "UNMATCHED", "AMBIGUOUS", "FAILED"}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

FORMAL_REQUIRED_KEYS = {
    "schema_version",
    "route_key",
    "route_manifest_sha256",
    "semantic_profile",
    "semantic_profile_sha256",
    "artifact_sha256",
    "artifact_id",
    "environment_sha256",
    "environment_artifact_id",
    "artifact_refs",
    "semantic_ir",
    "semantic_chunks",
    "behavior_equivalence",
    "formal_proof",
}
SEMANTIC_IR_KEYS = {
    "status",
    "source_ir_artifact_id",
    "source_ir_sha256",
    "target_ir_artifact_id",
    "target_relift_ir_sha256",
    "unknown_or_dropped_nodes",
    "differences",
}
SEMANTIC_CHUNK_KEYS = {
    "status",
    "total",
    "matched",
    "unmatched",
    "ambiguous",
    "coverage",
    "evidence_artifact_ids",
    "chunks",
}
CHUNK_KEYS = {"chunk_id", "source_ref", "target_ref", "semantic_hash", "status"}
BEHAVIOR_KEYS = {
    "status",
    "total_cases",
    "passed_cases",
    "counterexamples",
    "evidence_artifact_ids",
    "source_runtime_artifact_ids",
    "target_runtime_artifact_ids",
    "canonical_oracle_passed",
    "source_runtime_passed",
    "target_runtime_passed",
}
COUNTEREXAMPLE_REQUIRED_KEYS = {"case_id", "reason"}
COUNTEREXAMPLE_ALLOWED_KEYS = COUNTEREXAMPLE_REQUIRED_KEYS | {"evidence_ref"}
FORMAL_PROOF_KEYS = {
    "status",
    "solver",
    "solver_version",
    "solver_options",
    "input_artifact_id",
    "input_digest",
    "result_artifact_ids",
    "assumptions",
    "obligations",
    "replay",
}
OBLIGATION_REQUIRED_KEYS = {
    "obligation_id",
    "status",
    "scope",
    "formal_input_artifact_id",
    "solver_input_artifact_id",
    "input_digest",
    "solver_result_artifact_id",
    "assumptions",
}
OBLIGATION_ALLOWED_KEYS = OBLIGATION_REQUIRED_KEYS | {"detail"}
REPLAY_KEYS = {
    "command",
    "cwd",
    "expected_result_artifact_id",
    "expected_result_sha256",
    "expected_exit_code",
}
ARTIFACT_REF_KEYS = {"artifact_id", "role", "path", "sha256", "bytes"}
ARTIFACT_ROLES = {
    "source-ir",
    "target-ir",
    "target-artifact",
    "environment",
    "chunk-map",
    "behavior-result",
    "formal-input",
    "solver-input",
    "solver-result",
    "proof-input-bundle",
    "formal-composition",
    "engine-source",
    "engine-source-manifest",
    "corpus-artifact",
    "replay-tool",
    "replay-schema",
    "swift-analyzer-build-receipt",
}
ARTIFACT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{7,95}$")
FORMAL_INPUT_REQUIRED_KEYS = {
    "schema_version",
    "kind",
    "route",
    "claim_scope",
    "source_artifact",
    "target_artifact",
    "source_normalized_ir",
    "target_relift_normalized_ir",
    "implementation_identity",
    "analyzer_identity",
    "emitter_identity",
    "solver",
    "environment",
    "environment_assumptions",
    "unsupported_semantics",
}
MODULE_FUNCTION_LAYER_KEYS = {"semantic", "chunk", "behavior", "formal"}
MODULE_PASSING_PROOF_STATUSES = {"PROVED", "PROVED_UNDER_ASSUMPTIONS"}
MODULE_ARTIFACT_ROLES = {
    "source-module-semantic-ir",
    "target-module-semantic-ir",
    "source-module-observations",
    "target-module-observations",
    "emitted-target-module-artifact",
    "module-formal-input",
    "formal-function-input",
    "formal-function-smt2",
    "formal-function-result",
    "source-module-validation",
    "target-module-validation",
    "original-source-module-artifact",
    "module-case-manifest",
    "source-module-inventory",
    "target-module-inventory",
    "whole-file-module-closure",
    "swift-analyzer-build-receipt",
}
MODULE_INVENTORY_BASE_KEYS = {
    "schema_version",
    "kind",
    "profile",
    "source_language",
    "source_file",
    "analyzer",
    "analyzer_version",
    "enumeration_status",
    "subjects",
    "diagnostics",
    "source_artifact_sha256",
    "source_artifact_bytes",
    "directives",
}
SWIFT_ANALYZER_RECEIPT_PATH = (
    "certification/formal-artifacts/swift-analyzer-build-receipt.json"
)
SWIFT_ANALYZER_MIRROR_SEEDS = frozenset(
    {
        "verified-package-source-mirror",
        "verified-user-git-cache",
        "network-exact-revision",
    }
)
SWIFT_ANALYZER_RECEIPT_KEYS = {
    "schema_version",
    "kind",
    "source_inputs",
    "dependency",
    "toolchain",
    "build",
    "binary",
}
MODULE_INVENTORY_SUBJECT_KEYS = {
    "name",
    "qualified_name",
    "declaration_kind",
    "analyzable",
    "source_span",
    "signature",
    "occurrence",
}
WHOLE_FILE_CLOSURE_KEYS = {
    "schema_version",
    "kind",
    "profile",
    "route",
    "status",
    "source_inventory_sha256",
    "source_inventory_bytes",
    "target_inventory_sha256",
    "target_inventory_bytes",
    "manifest_symbols",
    "source_profile_symbols",
    "target_profile_symbols",
    "target_helper_symbols",
    "verified_generated_helpers",
    "verified_language_prelude",
    "verified_language_wrapper",
    "blocked_declarations",
    "source_user_call_graph",
    "target_call_graph_policy",
    "target_call_graph",
    "target_builtin_normalizations",
}
SPECIALIZED_INPUT_DOMAIN = "canonical-finite-no-error-input-domain"
SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC = "BLOCKED_NOT_EQUIVALENTLY_MODELED"
FORMAL_FUNCTION_INPUT_KEYS = {
    "schema_version",
    "kind",
    "profile",
    "route",
    "input_domain",
    "module_input_sha256",
    "symbol",
    "signature",
    "source_function",
    "source_function_sha256",
    "target_function",
    "target_function_sha256",
    "case_manifest_sha256",
}
FORMAL_FUNCTION_RESULT_KEYS = {
    "schema_version",
    "kind",
    "profile",
    "symbol",
    "status",
    "property_status",
    "proof_strength",
    "solver",
    "version",
    "options",
    "assumptions",
    "countermodel",
    "formal_input_digest",
    "solver_input_digest",
    "formal_input",
    "solver_input",
    "replay_contract",
    "claim_scope",
    "reason",
    "external_soundness_boundary",
    "independent_encodings",
    "certification_status",
}


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
        )
    except Exception as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _private_snapshot(
    root: Path,
    *,
    role: str,
    logical_name: str,
    content: bytes,
) -> Path:
    """Write one immutable-by-convention input below a private replay root."""

    destination_root = root / role
    destination_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    destination = destination_root / logical_name
    if destination.name != logical_name or not logical_name:
        raise ValueError(f"unsafe snapshot logical name: {logical_name!r}")
    destination.write_bytes(content)
    destination.chmod(0o400)
    return destination


def _validate_snapshot_stability(
    *,
    label: str,
    origin: Path,
    snapshot: Path,
    expected_bytes: bytes,
    expected_digest: str,
    failures: list[str],
) -> None:
    """Fail closed if either the private snapshot or bound origin drifted."""

    try:
        snapshot_bytes = snapshot.read_bytes()
        origin_bytes = origin.read_bytes()
    except OSError as exc:
        failures.append(f"{label} snapshot/origin stability check failed: {exc}")
        return
    if snapshot_bytes != expected_bytes or sha256_bytes(snapshot_bytes) != expected_digest:
        failures.append(f"{label} private snapshot changed during replay")
    if origin_bytes != expected_bytes or sha256_bytes(origin_bytes) != expected_digest:
        failures.append(f"{label} bound origin changed during replay")


def canonical_json_sha256(value: object) -> str:
    encoded = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return sha256_bytes(encoded)


def _runtime_layout() -> tuple[Path, Path, Path] | None:
    """Resolve the only accepted locked engine/venv/solver layout.

    ``Path.resolve`` is intentionally not used for ``sys.executable`` because
    a venv interpreter may itself be a symlink to a system Python.  The
    lexical executable location is the trust anchor supplied by ``uv
    --directory engines/polyglot-route-engine run --locked``.
    """

    executable = Path(os.path.abspath(sys.executable))
    if executable.parent.name != "bin":
        return None
    venv_root = executable.parent.parent
    if not (venv_root / "pyvenv.cfg").is_file():
        return None
    declared_environment = os.environ.get("UV_PROJECT_ENVIRONMENT")
    if declared_environment:
        try:
            if Path(declared_environment).resolve(strict=True) != venv_root.resolve(
                strict=True
            ):
                return None
        except OSError:
            return None
    validator_path = Path(__file__).resolve(strict=True)
    engine_projects = (
        validator_path.parents[2] / "engines" / "polyglot-route-engine",
        validator_path.parents[3]
        / "formal-artifacts"
        / "engine-sources"
        / "engines"
        / "polyglot-route-engine",
    )
    engine_project = next(
        (
            candidate
            for candidate in engine_projects
            if (candidate / "pyproject.toml").is_file()
            and (candidate / "uv.lock").is_file()
        ),
        None,
    )
    if engine_project is None:
        return None
    source_root = engine_project / "src"
    if not all((source_root / relative).is_file() for relative in ENGINE_RUNTIME_MODULES.values()):
        return None
    return source_root.resolve(), venv_root.resolve(), (executable.parent / "z3").resolve()


def _clean_proof_environment() -> dict[str, str]:
    layout = _runtime_layout()
    if layout is None:
        return {}
    _, _, z3_cli = layout
    environment = os.environ.copy()
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "PYTHONUSERBASE",
    ):
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PATH"] = str(z3_cli.parent) + os.pathsep + os.defpath
    return environment


def _runtime_provenance(
    failures: list[str], label: str
) -> dict[str, Any] | None:
    """Bind proof imports and both Z3 entry points to the locked uv runtime."""

    layout = _runtime_layout()
    if layout is None:
        failures.append(
            f"{label} proof runtime is not the locked polyglot-route-engine uv environment"
        )
        return None
    source_root, venv_root, expected_cli = layout
    lock_path = source_root.parent / "uv.lock"
    if not lock_path.is_file():
        failures.append(f"{label} locked route-engine uv.lock is missing")
        return None
    modules: dict[str, dict[str, str]] = {}
    for module_name, relative in ENGINE_RUNTIME_MODULES.items():
        try:
            module = importlib.import_module(module_name)
            origin_value = getattr(module, "__file__", None)
            if not isinstance(origin_value, str):
                raise ValueError("module has no file origin")
            origin = Path(origin_value).resolve(strict=True)
            expected = (source_root / relative).resolve(strict=True)
            origin.relative_to(source_root)
            if origin != expected:
                raise ValueError(f"origin {origin} != {expected}")
            observed_digest = sha256_file(origin)
            expected_digest = sha256_file(expected)
            if observed_digest != expected_digest:
                raise ValueError("origin digest differs from locked live source")
        except Exception as exc:
            failures.append(f"{label} engine module origin rejected for {module_name}: {exc}")
            return None
        modules[module_name] = {
            "path": str(origin),
            "sha256": observed_digest,
        }

    try:
        z3_module = importlib.import_module("z3")
        z3_origin_value = getattr(z3_module, "__file__", None)
        if not isinstance(z3_origin_value, str):
            raise ValueError("z3 module has no file origin")
        z3_origin = Path(z3_origin_value).resolve(strict=True)
        z3_origin.relative_to(venv_root)
        z3_version = str(z3_module.get_version_string())
        if z3_version != PINNED_Z3_VERSION:
            raise ValueError(f"unexpected z3 Python version {z3_version}")
    except Exception as exc:
        failures.append(f"{label} z3 Python origin rejected: {exc}")
        return None

    resolved_cli = shutil.which("z3")
    try:
        if resolved_cli is None:
            raise ValueError("z3 is absent from PATH")
        cli_path = Path(resolved_cli).resolve(strict=True)
        if cli_path != expected_cli or not expected_cli.is_file():
            raise ValueError(f"PATH resolves {cli_path}, expected {expected_cli}")
        cli_version_run = subprocess.run(
            [str(expected_cli), "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=_clean_proof_environment(),
        )
        expected_version_line = f"Z3 version {PINNED_Z3_VERSION} - 64 bit"
        if cli_version_run.returncode != 0 or cli_version_run.stdout.strip() != expected_version_line:
            raise ValueError("z3 CLI version output is not exact")
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        failures.append(f"{label} z3 CLI origin rejected: {exc}")
        return None

    return {
        "engine_modules": modules,
        "z3_python": {
            "path": str(z3_origin),
            "sha256": sha256_file(z3_origin),
            "version": z3_version,
        },
        "z3_cli": {
            "path": str(expected_cli),
            "sha256": sha256_file(expected_cli),
            "version": PINNED_Z3_VERSION,
        },
        "route_engine_lock": {
            "path": str(lock_path.resolve()),
            "sha256": sha256_file(lock_path),
        },
    }


def semantic_value(value: object) -> object:
    """Remove concrete locations while preserving the typed semantic subtree."""

    if isinstance(value, dict):
        return {
            key: semantic_value(item)
            for key, item in value.items()
            if key != "source_span"
        }
    if isinstance(value, list):
        return [semantic_value(item) for item in value]
    return value


def _engine_proof_api(
    failures: list[str], label: str
) -> tuple[Any, Any, Any] | None:
    """Load the pinned encoder/oracle used for independent evidence replay.

    All supported entry points run this validator in the route-engine's locked
    ``uv`` environment.  Failing to load that exact API is therefore a closed
    gate, never a reason to trust persisted solver or oracle output.
    """

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.equivalence import (  # type: ignore[import-not-found]
            behavior_equivalence,
            formal_equivalence,
        )
        from elmos_polyglot_route.models import Function  # type: ignore[import-not-found]
    except Exception as exc:
        failures.append(f"{label} cannot load pinned proof/oracle API: {exc}")
        return None
    return Function, formal_equivalence, behavior_equivalence


def _engine_domain_api(
    failures: list[str], label: str
) -> tuple[Any, Any, Any] | None:
    """Load the engine's exact-eight domain guards only after origin binding."""

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.engine import (  # type: ignore[import-not-found]
            _enforce_specialized_case_domain,
            _enforce_specialized_semantic_domain,
        )
        from elmos_polyglot_route.models import SemanticIR  # type: ignore[import-not-found]
    except Exception as exc:
        failures.append(f"{label} cannot load pinned specialized-domain API: {exc}")
        return None
    return (
        SemanticIR,
        _enforce_specialized_semantic_domain,
        _enforce_specialized_case_domain,
    )


def _engine_negative_replay_api(
    failures: list[str], label: str
) -> tuple[Any, Any, Any, Any] | None:
    """Load only the origin-bound entry points used to replay negative cases."""

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.engine import (  # type: ignore[import-not-found]
            migrate,
            migrate_module,
        )
        from elmos_polyglot_route.models import (  # type: ignore[import-not-found]
            RouteError,
        )
        from elmos_polyglot_route.native import (  # type: ignore[import-not-found]
            analyze,
        )
    except Exception as exc:
        failures.append(f"{label} cannot load pinned negative replay API: {exc}")
        return None
    return migrate, migrate_module, analyze, RouteError


def _engine_module_closure_api(
    failures: list[str], label: str
) -> tuple[Any, Any, Any, Any, Any, Any, Any, Any] | None:
    """Load the exact module inventory/emission closure implementation."""

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.emitter import emit  # type: ignore[import-not-found]
        from elmos_polyglot_route.engine import (  # type: ignore[import-not-found]
            _build_whole_file_closure,
            _combine_function_irs,
        )
        from elmos_polyglot_route.models import (  # type: ignore[import-not-found]
            SemanticIR,
        )
        from elmos_polyglot_route.native import (  # type: ignore[import-not-found]
            analyze,
            inventory_module,
        )
        from elmos_polyglot_route.validation import (  # type: ignore[import-not-found]
            validate,
            validate_source,
        )
    except Exception as exc:
        failures.append(f"{label} cannot load pinned module closure API: {exc}")
        return None
    return (
        SemanticIR,
        emit,
        analyze,
        inventory_module,
        _combine_function_irs,
        _build_whole_file_closure,
        validate_source,
        validate,
    )


def _engine_swift_analyzer_api(
    failures: list[str], label: str
) -> tuple[Any, Any, Any] | None:
    """Load the receipt builder and its live binary handle from bound sources."""

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.native import (  # type: ignore[import-not-found]
            _swift_analyzer,
            swift_analyzer_build_receipt,
        )
        from elmos_polyglot_route.toolchains import (  # type: ignore[import-not-found]
            exact_toolchain,
        )
    except Exception as exc:
        failures.append(f"{label} cannot load pinned Swift analyzer receipt API: {exc}")
        return None
    return _swift_analyzer, swift_analyzer_build_receipt, exact_toolchain


def _receipt_payload_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def _swift_receipt_stable_projection(receipt: dict[str, Any]) -> dict[str, Any]:
    """Return only fields the locked contract says are cross-build stable."""

    projected = json.loads(
        json.dumps(receipt, ensure_ascii=False, allow_nan=False),
        parse_constant=_reject_json_constant,
    )
    projected.pop("binary", None)
    dependency = projected.get("dependency")
    mirror = dependency.get("mirror") if isinstance(dependency, dict) else None
    if isinstance(mirror, dict):
        mirror.pop("seed", None)
    return projected


def _module_inventory_stable_projection(
    inventory: dict[str, Any],
) -> dict[str, Any]:
    """Normalize only the explicitly non-reproducible Swift build fields."""

    projected = json.loads(
        json.dumps(inventory, ensure_ascii=False, allow_nan=False),
        parse_constant=_reject_json_constant,
    )
    receipt = projected.get("analyzer_build_receipt")
    if isinstance(receipt, dict):
        projected["analyzer_build_receipt"] = _swift_receipt_stable_projection(
            receipt
        )
    return projected


def _canonical_json_bytes_for_binding(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _whole_file_closure_stable_projection(
    closure: dict[str, Any],
    *,
    source_inventory: dict[str, Any],
    target_inventory: dict[str, Any],
) -> dict[str, Any]:
    projected = json.loads(
        json.dumps(closure, ensure_ascii=False, allow_nan=False),
        parse_constant=_reject_json_constant,
    )
    for side, inventory in (
        ("source", source_inventory),
        ("target", target_inventory),
    ):
        stable_inventory = _module_inventory_stable_projection(inventory)
        stable_bytes = _canonical_json_bytes_for_binding(stable_inventory)
        projected[f"{side}_inventory_sha256"] = sha256_bytes(stable_bytes)
        projected[f"{side}_inventory_bytes"] = len(stable_bytes)
    return projected


def _validate_swift_analyzer_receipt_document(
    receipt: object,
    *,
    label: str,
    failures: list[str],
    live_binary: Path | None = None,
) -> dict[str, Any] | None:
    """Validate one persisted or freshly rebuilt Swift analyzer receipt.

    Persisted binary bytes intentionally are not present in route evidence, so
    their digest is a receipt boundary rather than an independent executable
    replay.  A freshly rebuilt receipt is additionally checked against its live
    private binary below.  Compiler/runtime soundness remains ``NOT_RUN``.
    """

    if not isinstance(receipt, dict):
        failures.append(f"{label} must be an object")
        return None
    if set(receipt) != SWIFT_ANALYZER_RECEIPT_KEYS:
        failures.append(f"{label} top-level keys are not exact")
    if (
        receipt.get("schema_version") != "1.0.0"
        or receipt.get("kind") != "elmos.swift-analyzer-build-receipt"
    ):
        failures.append(f"{label} identity is invalid")

    source_inputs = receipt.get("source_inputs")
    if not isinstance(source_inputs, dict) or set(source_inputs) != {
        "sha256",
        "files",
    }:
        failures.append(f"{label}.source_inputs keys are not exact")
        source_inputs = {}
    _require_digest(
        failures,
        source_inputs.get("sha256"),
        f"{label}.source_inputs.sha256",
    )
    files = source_inputs.get("files")
    if not isinstance(files, list) or len(files) < 3:
        failures.append(f"{label}.source_inputs.files is incomplete")
        files = []
    observed_paths: list[str] = []
    for index, item in enumerate(files):
        item_label = f"{label}.source_inputs.files[{index}]"
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}:
            failures.append(f"{item_label} keys are not exact")
            continue
        relative = item.get("path")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in Path(relative).parts)
        ):
            failures.append(f"{item_label}.path is invalid")
        else:
            observed_paths.append(relative)
        _require_digest(failures, item.get("sha256"), f"{item_label}.sha256")
        if not _is_int(item.get("bytes"), minimum=1):
            failures.append(f"{item_label}.bytes is invalid")
    if observed_paths != list(dict.fromkeys(observed_paths)):
        failures.append(f"{label}.source_inputs.files paths are duplicated")
    if source_inputs.get("sha256") != _receipt_payload_sha256({"files": files}):
        failures.append(f"{label}.source_inputs aggregate digest mismatch")

    layout = _runtime_layout()
    if layout is None:
        failures.append(f"{label} cannot resolve locked Swift analyzer sources")
    else:
        source_root, _, _ = layout
        package = source_root.parent / "native" / "swift"
        expected_sources = [
            package / "Package.swift",
            package / "Package.resolved",
            *sorted(
                (package / "Sources").rglob("*.swift"),
                key=lambda path: path.relative_to(package).as_posix(),
            ),
        ]
        expected_paths = [path.relative_to(package).as_posix() for path in expected_sources]
        if observed_paths != expected_paths:
            failures.append(f"{label}.source_inputs file set differs from locked engine sources")
        records_by_path = {
            item.get("path"): item for item in files if isinstance(item, dict)
        }
        for source in expected_sources:
            relative = source.relative_to(package).as_posix()
            record = records_by_path.get(relative)
            try:
                if source.is_symlink() or not source.is_file():
                    raise ValueError("not a regular locked source")
                content = source.read_bytes()
            except (OSError, ValueError) as exc:
                failures.append(f"{label}.source_inputs locked source invalid: {relative}: {exc}")
                continue
            if not isinstance(record, dict) or (
                record.get("sha256") != sha256_bytes(content)
                or record.get("bytes") != len(content)
            ):
                failures.append(f"{label}.source_inputs source binding mismatch: {relative}")

    dependency = receipt.get("dependency")
    dependency_keys = {
        "identity",
        "version",
        "revision",
        "sha256",
        "file_count",
        "bytes",
        "mirror",
    }
    if not isinstance(dependency, dict) or set(dependency) != dependency_keys:
        failures.append(f"{label}.dependency keys are not exact")
        dependency = {}
    if any(
        not isinstance(dependency.get(field), str) or not dependency.get(field)
        for field in ("identity", "version", "revision")
    ):
        failures.append(f"{label}.dependency identity is invalid")
    _require_digest(failures, dependency.get("sha256"), f"{label}.dependency.sha256")
    for field in ("file_count", "bytes"):
        if not _is_int(dependency.get(field), minimum=1):
            failures.append(f"{label}.dependency.{field} is invalid")
    mirror = dependency.get("mirror")
    if not isinstance(mirror, dict) or set(mirror) != {
        "seed",
        "git",
        "sha256",
        "file_count",
        "bytes",
    }:
        failures.append(f"{label}.dependency.mirror keys are not exact")
        mirror = {}
    if mirror.get("seed") not in SWIFT_ANALYZER_MIRROR_SEEDS:
        failures.append(f"{label}.dependency.mirror.seed is invalid")
    for field in ("sha256", "file_count", "bytes"):
        if mirror.get(field) != dependency.get(field):
            failures.append(f"{label}.dependency.mirror.{field} differs from dependency tree")
    git = mirror.get("git")
    if not isinstance(git, dict) or set(git) != {"path", "sha256", "version"}:
        failures.append(f"{label}.dependency.mirror.git keys are not exact")
        git = {}
    if any(not isinstance(git.get(field), str) or not git.get(field) for field in ("path", "version")):
        failures.append(f"{label}.dependency.mirror.git identity is invalid")
    _require_digest(failures, git.get("sha256"), f"{label}.dependency.mirror.git.sha256")
    git_path = Path(str(git.get("path", "")))
    try:
        if not git_path.is_absolute() or not git_path.is_file():
            raise ValueError("git path is not an absolute regular file")
        if sha256_file(git_path) != git.get("sha256"):
            raise ValueError("git digest differs")
    except (OSError, ValueError) as exc:
        failures.append(f"{label}.dependency.mirror.git provenance invalid: {exc}")

    toolchain = receipt.get("toolchain")
    if not isinstance(toolchain, dict) or set(toolchain) != {
        "swiftc",
        "swiftc_sha256",
        "swift_driver",
        "swift_driver_sha256",
        "version",
        "profile",
    }:
        failures.append(f"{label}.toolchain keys are not exact")
        toolchain = {}
    for path_field, digest_field in (
        ("swiftc", "swiftc_sha256"),
        ("swift_driver", "swift_driver_sha256"),
    ):
        _require_digest(failures, toolchain.get(digest_field), f"{label}.toolchain.{digest_field}")
        tool_path = Path(str(toolchain.get(path_field, "")))
        try:
            if not tool_path.is_absolute() or not tool_path.is_file():
                raise ValueError(f"{path_field} is not an absolute regular file")
            if sha256_file(tool_path) != toolchain.get(digest_field):
                raise ValueError(f"{path_field} digest differs")
        except (OSError, ValueError) as exc:
            failures.append(f"{label}.toolchain.{path_field} provenance invalid: {exc}")
    if not isinstance(toolchain.get("version"), str) or not toolchain.get("version"):
        failures.append(f"{label}.toolchain.version is invalid")
    profile = toolchain.get("profile")
    if (
        not isinstance(profile, list)
        or not profile
        or any(not isinstance(item, str) or not item for item in profile)
    ):
        failures.append(f"{label}.toolchain.profile is invalid")

    expected_argv = [
        "<swift-driver>",
        "build",
        "--package-path",
        "<source-snapshot>",
        "--cache-path",
        "<isolated-cache>",
        "--config-path",
        "<isolated-config>",
        "--security-path",
        "<isolated-security>",
        "--scratch-path",
        "<isolated-build>",
        "--manifest-cache",
        "none",
        "--disable-automatic-resolution",
        "-c",
        "release",
    ]
    build = receipt.get("build")
    if not isinstance(build, dict) or set(build) != {
        "configuration",
        "automatic_resolution",
        "manifest_cache",
        "environment_policy",
        "argv",
    }:
        failures.append(f"{label}.build keys are not exact")
        build = {}
    if build != {
        "configuration": "release",
        "automatic_resolution": False,
        "manifest_cache": "none",
        "environment_policy": "minimal-empty-home-v1",
        "argv": expected_argv,
    }:
        failures.append(f"{label}.build policy is invalid")

    binary = receipt.get("binary")
    if not isinstance(binary, dict) or set(binary) != {"name", "sha256", "bytes", "mode"}:
        failures.append(f"{label}.binary keys are not exact")
        binary = {}
    if binary.get("name") != "ElmosSwiftAnalyzer":
        failures.append(f"{label}.binary.name is invalid")
    _require_digest(failures, binary.get("sha256"), f"{label}.binary.sha256")
    if not _is_int(binary.get("bytes"), minimum=1) or int(binary.get("bytes", 0)) > 100_000_000:
        failures.append(f"{label}.binary.bytes is invalid")
    mode_value = binary.get("mode")
    try:
        parsed_mode = int(mode_value, 8) if isinstance(mode_value, str) else -1
    except ValueError:
        parsed_mode = -1
    if (
        not isinstance(mode_value, str)
        or not re.fullmatch(r"[0-7]{4}", mode_value)
        or parsed_mode & 0o111 == 0
        or parsed_mode & 0o022 != 0
    ):
        failures.append(f"{label}.binary.mode is unsafe")

    if live_binary is not None:
        try:
            if live_binary.is_symlink():
                raise ValueError("binary is a symlink")
            resolved_binary = live_binary.resolve(strict=True)
            metadata = resolved_binary.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
                raise ValueError("binary is not an owner-controlled regular file")
            if (
                resolved_binary.name != binary.get("name")
                or metadata.st_size != binary.get("bytes")
                or f"{stat.S_IMODE(metadata.st_mode):04o}" != binary.get("mode")
                or sha256_file(resolved_binary) != binary.get("sha256")
            ):
                raise ValueError("binary bytes/mode/digest differ from receipt")
            private_root = next(
                (
                    parent
                    for parent in resolved_binary.parents
                    if parent.name.startswith("elmos-swift-analyzer-")
                ),
                None,
            )
            if private_root is None:
                raise ValueError("binary is not inside a private analyzer build root")
            relative_binary = resolved_binary.relative_to(private_root)
            root_metadata = private_root.lstat()
            if (
                relative_binary.parts[0] != "build"
                or not stat.S_ISDIR(root_metadata.st_mode)
                or root_metadata.st_uid != os.getuid()
                or stat.S_IMODE(root_metadata.st_mode) != 0o700
            ):
                raise ValueError("binary escaped the owner-only isolated build tree")
            if layout is not None and resolved_binary.is_relative_to(layout[0].parent):
                raise ValueError("repository build cache was used as analyzer binary")
        except (OSError, ValueError) as exc:
            failures.append(f"{label}.binary live provenance invalid: {exc}")

    return receipt


def _validate_swift_receipt_binding(
    *,
    source_language: object,
    target_language: object,
    records: list[tuple[dict[str, Any], Path, str]],
    label: str,
    failures: list[str],
) -> dict[str, Any] | None:
    """Require one shared receipt for Swift routes and independently rebuild it."""

    swift_required = "swift" in {source_language, target_language}
    if not swift_required:
        if records:
            failures.append(f"{label} is forbidden on a non-Swift route")
        return None
    if len(records) != 1:
        failures.append(f"{label} must be bound exactly once on a Swift route")
        return None
    record = records[0]
    if record[0].get("path") != SWIFT_ANALYZER_RECEIPT_PATH:
        failures.append(f"{label} path is not the canonical route receipt path")
    try:
        persisted = load(record[1])
    except Exception as exc:
        failures.append(f"{label} is invalid JSON: {exc}")
        return None
    persisted = _validate_swift_analyzer_receipt_document(
        persisted,
        label=label,
        failures=failures,
    )
    api = _engine_swift_analyzer_api(failures, label)
    if persisted is None or api is None:
        return persisted
    swift_analyzer, public_receipt, exact_toolchain = api
    try:
        binary_path, fresh = swift_analyzer(exact_toolchain("swift"))
        public = public_receipt()
    except Exception as exc:
        failures.append(f"{label} independent scratch rebuild failed: {exc}")
        return persisted
    if public != fresh:
        failures.append(f"{label} public/private receipt API results differ")
    validated_fresh = _validate_swift_analyzer_receipt_document(
        fresh,
        label=f"{label} fresh",
        failures=failures,
        live_binary=Path(binary_path),
    )
    if validated_fresh is not None and (
        _swift_receipt_stable_projection(persisted)
        != _swift_receipt_stable_projection(validated_fresh)
    ):
        failures.append(f"{label} stable projection differs from independent scratch rebuild")
    return persisted


def _validate_swift_analyzer_version_binding(
    *,
    semantic_document: object,
    receipt: dict[str, Any] | None,
    label: str,
    failures: list[str],
) -> bool:
    if not isinstance(semantic_document, dict) or semantic_document.get(
        "source_language"
    ) != "swift":
        return False
    if receipt is None:
        failures.append(f"{label} has no bound Swift analyzer build receipt")
        return True
    source_inputs = receipt.get("source_inputs")
    toolchain = receipt.get("toolchain")
    dependency = receipt.get("dependency")
    if not all(isinstance(item, dict) for item in (source_inputs, toolchain, dependency)):
        failures.append(f"{label} Swift analyzer receipt projection is invalid")
        return True
    expected_suffix = (
        f";source-inputs={source_inputs.get('sha256')};"
        f"swift-driver={toolchain.get('swift_driver_sha256')};"
        f"swift-syntax-tree={dependency.get('sha256')}"
    )
    analyzer_version = semantic_document.get("analyzer_version")
    if not isinstance(analyzer_version, str) or not analyzer_version.endswith(
        expected_suffix
    ):
        failures.append(f"{label} analyzer_version is detached from the Swift receipt")
    return True


def _load_json_array(path: Path) -> list[Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
    )
    if not isinstance(value, list):
        raise ValueError(f"{path}: JSON root must be an array")
    return value


def _fresh_formal_equivalence(
    *,
    source_function: dict[str, Any],
    target_function: dict[str, Any],
    source_language: object,
    target_language: object,
    input_digest: str,
    formal_input_reference: dict[str, str],
    input_domain: str,
    label: str,
    failures: list[str],
) -> tuple[dict[str, Any], str] | None:
    """Regenerate a proof in a fresh Z3 process.

    Z3's pretty-printer uses context-local expression identities.  Replaying in
    a new process makes the byte comparison independent of validations already
    performed in this process and matches the generator's fresh-process
    contract.
    """

    parent_provenance = _runtime_provenance(failures, label)
    if parent_provenance is None:
        return None
    layout = _runtime_layout()
    if layout is None:  # already reported by _runtime_provenance
        return None
    source_root, _, _ = layout
    payload = {
        "source_function": source_function,
        "target_function": target_function,
        "source_language": source_language,
        "target_language": target_language,
        "input_digest": input_digest,
        "formal_input_reference": formal_input_reference,
        "input_domain": input_domain,
        "module_files": ENGINE_RUNTIME_MODULES,
        "lock_path": parent_provenance["route_engine_lock"]["path"],
    }
    program = """
import base64
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from elmos_polyglot_route.equivalence import formal_equivalence
from elmos_polyglot_route.models import Function
p = json.load(sys.stdin)
modules = {}
for module_name in p["module_files"]:
    module = importlib.import_module(module_name)
    origin = Path(module.__file__).resolve(strict=True)
    modules[module_name] = {
        "path": str(origin),
        "sha256": "sha256:" + hashlib.sha256(origin.read_bytes()).hexdigest(),
    }
z3_module = importlib.import_module("z3")
z3_origin = Path(z3_module.__file__).resolve(strict=True)
z3_cli = Path(shutil.which("z3") or "").resolve(strict=True)
z3_version_run = subprocess.run(
    [str(z3_cli), "-version"], capture_output=True, text=True, check=False, timeout=10
)
provenance = {
    "engine_modules": modules,
    "z3_python": {
        "path": str(z3_origin),
        "sha256": "sha256:" + hashlib.sha256(z3_origin.read_bytes()).hexdigest(),
        "version": str(z3_module.get_version_string()),
    },
    "z3_cli": {
        "path": str(z3_cli),
        "sha256": "sha256:" + hashlib.sha256(z3_cli.read_bytes()).hexdigest(),
        "version": str(z3_module.get_version_string()),
        "version_output": z3_version_run.stdout.strip(),
        "returncode": z3_version_run.returncode,
    },
    "route_engine_lock": {
        "path": str(Path(p["lock_path"]).resolve(strict=True)),
        "sha256": "sha256:" + hashlib.sha256(Path(p["lock_path"]).read_bytes()).hexdigest(),
    },
}
result, smt = formal_equivalence(
    Function.from_mapping(p["source_function"]),
    Function.from_mapping(p["target_function"]),
    p["source_language"],
    p["target_language"],
    p["input_digest"],
    formal_input_reference=p["formal_input_reference"],
    input_domain=p["input_domain"],
)
print(json.dumps({"result": result, "smt_base64": base64.b64encode(smt.encode("utf-8")).decode("ascii"), "provenance": provenance}, sort_keys=True, separators=(",", ":"), allow_nan=False))
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", program],
            input=json.dumps(payload, ensure_ascii=False, allow_nan=False),
            capture_output=True,
            text=True,
            check=False,
            timeout=40,
            # ``PYTHONPATH`` is intentionally scrubbed.  Execute from the
            # digest-checked source root itself so ``sys.path[0]`` can load
            # only the pinned ``elmos_polyglot_route`` package.
            cwd=source_root,
            env=_clean_proof_environment(),
        )
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        failures.append(f"{label} fresh formal re-encoding failed: {exc}")
        return None
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip().splitlines()[-1:] or ["unknown error"]
        failures.append(
            f"{label} fresh formal re-encoding exited nonzero: {diagnostic[0]}"
        )
        return None
    try:
        response = json.loads(
            completed.stdout, parse_constant=_reject_json_constant
        )
        result = response["result"]
        smt = base64.b64decode(response["smt_base64"], validate=True).decode("utf-8")
        child_provenance = response["provenance"]
    except Exception as exc:
        failures.append(f"{label} fresh formal re-encoding output is invalid: {exc}")
        return None
    if not isinstance(result, dict):
        failures.append(f"{label} fresh formal result is not an object")
        return None
    if not isinstance(child_provenance, dict):
        failures.append(f"{label} fresh proof runtime provenance is not an object")
        return None
    child_cli = child_provenance.get("z3_cli")
    if isinstance(child_cli, dict):
        child_cli = {
            key: child_cli.get(key) for key in ("path", "sha256", "version")
        }
    normalized_child = {
        **child_provenance,
        "z3_cli": child_cli,
    }
    if normalized_child != parent_provenance:
        failures.append(f"{label} fresh proof runtime provenance differs from parent")
        return None
    raw_child_cli = child_provenance.get("z3_cli")
    expected_version_line = f"Z3 version {PINNED_Z3_VERSION} - 64 bit"
    if (
        not isinstance(raw_child_cli, dict)
        or raw_child_cli.get("returncode") != 0
        or raw_child_cli.get("version_output") != expected_version_line
    ):
        failures.append(f"{label} fresh z3 CLI version replay is invalid")
        return None
    return result, smt


def _function_chunk_nodes(
    function: object,
) -> tuple[dict[str, dict[str, Any]], dict[str, str | None], dict[str, list[str]]]:
    """Enumerate exactly the syntax nodes emitted by ``semantic_chunks``."""

    if not isinstance(function, dict):
        raise ValueError("function must be an object")
    nodes: dict[str, dict[str, Any]] = {}
    parents: dict[str, str | None] = {}
    children: dict[str, list[str]] = {}

    def add(path: str, value: object, parent: str | None) -> dict[str, Any]:
        if not isinstance(value, dict) or path in nodes:
            raise ValueError(f"invalid/duplicate semantic node: {path}")
        nodes[path] = value
        parents[path] = parent
        if parent is not None:
            children.setdefault(parent, []).append(path)
        children.setdefault(path, [])
        return value

    def expression(value: object, path: str, parent: str) -> None:
        node = add(path, value, parent)
        if node.get("kind") == "binary":
            expression(node.get("left"), f"{path}/left", path)
            expression(node.get("right"), f"{path}/right", path)

    def statements(value: object, base: str, parent: str) -> None:
        if not isinstance(value, list):
            raise ValueError(f"statement list is invalid: {base}")
        for index, raw_statement in enumerate(value):
            path = f"{base}/{index}"
            statement = add(path, raw_statement, parent)
            if statement.get("expression") is not None:
                expression(statement.get("expression"), f"{path}/expression", path)
            if statement.get("condition") is not None:
                expression(statement.get("condition"), f"{path}/condition", path)
            statements(statement.get("then", []), f"{path}/then", path)
            statements(statement.get("else", []), f"{path}/else", path)

    root = "/functions/0"
    add(root, function, None)
    parameters = function.get("parameters")
    if not isinstance(parameters, list):
        raise ValueError("function parameters must be an array")
    for index, parameter in enumerate(parameters):
        add(f"{root}/parameters/{index}", parameter, root)
    statements(function.get("body"), f"{root}/body", root)
    return nodes, parents, children


def _expected_semantic_layer(
    source_function: object, target_function: object
) -> dict[str, Any]:
    source_view = {"functions": [semantic_value(source_function)]}
    target_view = {"functions": [semantic_value(target_function)]}
    differences: list[dict[str, Any]] = []
    if source_view != target_view:
        differences.append(
            {
                "path": "/functions",
                "source_sha256": canonical_json_sha256(source_view),
                "target_sha256": canonical_json_sha256(target_view),
            }
        )
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.semantic-equivalence",
        "status": "PASSED" if not differences else "FAILED",
        "source_view_sha256": canonical_json_sha256(source_view),
        "target_view_sha256": canonical_json_sha256(target_view),
        "difference_count": len(differences),
        "differences": differences,
    }


def _validate_nonvacuous_smt(
    *,
    smt_text: str,
    persisted_path: Path,
    label: str,
    failures: list[str],
) -> None:
    """Replay assumptions-only SAT and assumptions+divergence UNSAT."""

    provenance = _runtime_provenance(failures, label)
    if provenance is None:
        return
    try:
        import z3  # type: ignore[import-not-found]

        assertions = list(z3.parse_smt2_string(smt_text))
        if not assertions:
            raise ValueError("SMT contains no assertions")
        assumptions_solver = z3.Solver()
        assumptions_solver.set(timeout=30000, random_seed=0)
        assumptions_solver.add(*assertions[:-1])
        assumption_verdict = assumptions_solver.check()
        divergence_solver = z3.Solver()
        divergence_solver.set(timeout=30000, random_seed=0)
        divergence_solver.add(*assertions)
        divergence_verdict = divergence_solver.check()
    except Exception as exc:
        failures.append(f"{label} independent SMT replay failed: {exc}")
        return
    if assumption_verdict != z3.sat:
        failures.append(f"{label} assumptions-only domain is not SAT")
    if divergence_verdict != z3.unsat:
        failures.append(f"{label} divergence is not UNSAT")
    try:
        replay = subprocess.run(
            [provenance["z3_cli"]["path"], "-smt2", persisted_path.name],
            cwd=persisted_path.parent,
            check=False,
            capture_output=True,
            text=True,
            timeout=35,
            env=_clean_proof_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        failures.append(f"{label} z3 CLI replay failed: {exc}")
    else:
        if replay.returncode != 0 or replay.stdout.strip() != "unsat":
            failures.append(f"{label} z3 CLI replay did not reproduce exact UNSAT")


def _smt_assertions_equivalent(
    persisted: str,
    regenerated: str,
    *,
    label: str,
    failures: list[str],
) -> bool:
    """Compare ordered Z3 ASTs, ignoring unstable local let numbering."""

    if _runtime_provenance(failures, label) is None:
        return False
    try:
        import z3  # type: ignore[import-not-found]

        persisted_assertions = list(z3.parse_smt2_string(persisted))
        regenerated_assertions = list(z3.parse_smt2_string(regenerated))
    except Exception as exc:
        failures.append(f"{label} cannot parse persisted/regenerated SMT: {exc}")
        return False
    if len(persisted_assertions) != len(regenerated_assertions):
        failures.append(f"{label} SMT assertion count differs from re-encoding")
        return False
    if any(
        not z3.eq(persisted_item, regenerated_item)
        for persisted_item, regenerated_item in zip(
            persisted_assertions, regenerated_assertions, strict=True
        )
    ):
        failures.append(f"{label} SMT assertions differ from independent re-encoding")
        return False
    return True


def _validate_concrete_chunk_document(
    document: object,
    *,
    label: str,
    failures: list[str],
    source_record: tuple[dict[str, Any], Path, str] | None,
    target_record: tuple[dict[str, Any], Path, str] | None,
    source_function: object | None = None,
    target_function: object | None = None,
) -> None:
    """Recompute the exact UTF-8 span contract from bound source/target bytes."""

    if not isinstance(document, dict):
        failures.append(f"{label} must be an object")
        return
    if document.get("concrete_spans_required") is not True:
        failures.append(f"{label}.concrete_spans_required must be true")
    if document.get("span_scheme") != "relative-file-utf8-byte-range-end-exclusive-v1":
        failures.append(f"{label}.span_scheme is invalid")
    if document.get("kind") != "elmos.chunk-equivalence":
        failures.append(f"{label}.kind is invalid")
    if document.get("status") != "PASSED":
        failures.append(f"{label}.status must be PASSED")
    if document.get("path_scheme") != "rfc6901-json-pointer-v1":
        failures.append(f"{label}.path_scheme is invalid")
    if document.get("hash_scheme") != "sha256-canonical-semantic-subtree-v1":
        failures.append(f"{label}.hash_scheme is invalid")
    for field in (
        "missing_source_span_count",
        "missing_target_span_count",
        "mismatch_count",
        "unexpected_target_chunk_count",
    ):
        if document.get(field) != 0:
            failures.append(f"{label}.{field} must be zero")
    span_validation = document.get("span_validation")
    if not isinstance(span_validation, dict):
        failures.append(f"{label}.span_validation must be an object")
        return
    if span_validation.get("status") != "PASSED":
        failures.append(f"{label}.span_validation.status must be PASSED")
    mappings = document.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        failures.append(f"{label}.mappings must be non-empty")
        return
    if document.get("required_source_chunk_count") != len(mappings):
        failures.append(f"{label}.required_source_chunk_count drift")
    if document.get("mapped_source_chunk_count") != len(mappings):
        failures.append(f"{label}.mapped_source_chunk_count drift")
    if document.get("coverage") != 1.0:
        failures.append(f"{label}.coverage must be 1.0")
    if document.get("unexpected_target_paths") != []:
        failures.append(f"{label}.unexpected_target_paths must be empty")

    semantic_nodes: dict[str, dict[str, dict[str, Any]]] = {}
    semantic_parents: dict[str, dict[str, str | None]] = {}
    semantic_children: dict[str, dict[str, list[str]]] = {}
    for side, function in (("source", source_function), ("target", target_function)):
        if function is None:
            failures.append(f"{label} has no bound {side} semantic function")
            continue
        try:
            nodes, parents, children = _function_chunk_nodes(function)
        except Exception as exc:
            failures.append(f"{label} {side} semantic function is invalid: {exc}")
            continue
        semantic_nodes[side] = nodes
        semantic_parents[side] = parents
        semantic_children[side] = children
    declared_paths: list[str] = []
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            failures.append(f"{label}.mappings[{index}] must be an object")
            continue
        if mapping.get("status") != "EXACT":
            failures.append(f"{label}.mappings[{index}].status must be EXACT")
        semantic_path = mapping.get("semantic_path")
        if not isinstance(semantic_path, str) or not semantic_path.startswith("/"):
            failures.append(f"{label}.mappings[{index}].semantic_path is invalid")
            continue
        declared_paths.append(semantic_path)
    if len(declared_paths) != len(mappings):
        failures.append(f"{label}.mappings contain invalid/non-path entries")
    if len(declared_paths) != len(set(declared_paths)):
        failures.append(f"{label}.mappings contain duplicate semantic paths")
    for side, nodes in semantic_nodes.items():
        if set(declared_paths) != set(nodes):
            failures.append(f"{label} {side} semantic path set is not complete/exact")

    for side, record in (("source", source_record), ("target", target_record)):
        metadata = span_validation.get(side)
        if not isinstance(metadata, dict):
            failures.append(f"{label}.span_validation.{side} must be an object")
            continue
        if metadata.get("status") != "PASSED":
            failures.append(f"{label}.span_validation.{side}.status must be PASSED")
        if record is None:
            failures.append(f"{label} has no byte-bound {side} artifact")
            continue
        _, artifact_path, artifact_digest = record
        artifact_bytes = artifact_path.read_bytes()
        if metadata.get("artifact_sha256") != artifact_digest:
            failures.append(f"{label}.span_validation.{side} digest drift")
        if metadata.get("artifact_byte_count") != len(artifact_bytes):
            failures.append(f"{label}.span_validation.{side} byte count drift")
        if metadata.get("logical_file") != artifact_path.name:
            failures.append(f"{label}.span_validation.{side} logical file drift")
        if metadata.get("node_count") != len(mappings):
            failures.append(f"{label}.span_validation.{side} node count drift")
        nodes = semantic_nodes.get(side, {})
        spans_by_path: dict[str, dict[str, Any]] = {}
        for index, mapping in enumerate(mappings):
            if not isinstance(mapping, dict):
                failures.append(f"{label}.mappings[{index}] must be an object")
                continue
            span = mapping.get(f"{side}_span")
            if not isinstance(span, dict) or set(span) != {
                "file",
                "start_byte",
                "end_byte",
            }:
                failures.append(f"{label}.mappings[{index}].{side}_span is not exact")
                continue
            semantic_path = mapping.get("semantic_path")
            node = nodes.get(semantic_path) if isinstance(semantic_path, str) else None
            if node is None:
                failures.append(
                    f"{label}.mappings[{index}] has unknown {side} semantic path"
                )
            elif span != node.get("source_span"):
                failures.append(
                    f"{label}.mappings[{index}].{side}_span does not bind semantic IR"
                )
            if isinstance(semantic_path, str):
                spans_by_path[semantic_path] = span
            start = span.get("start_byte")
            end = span.get("end_byte")
            if span.get("file") != artifact_path.name:
                failures.append(
                    f"{label}.mappings[{index}].{side}_span logical file drift"
                )
            if (
                not _is_int(start, minimum=0)
                or not _is_int(end, minimum=1)
                or int(start) >= int(end)
                or int(end) > len(artifact_bytes)
            ):
                failures.append(
                    f"{label}.mappings[{index}].{side}_span is outside UTF-8 byte bounds"
                )
            pointer = mapping.get(f"{side}_artifact_pointer")
            if pointer != f"{artifact_digest}#{semantic_path}":
                failures.append(
                    f"{label}.mappings[{index}].{side}_artifact_pointer drift"
                )
            if mapping.get(f"{side}_semantic_pointer") != semantic_path:
                failures.append(
                    f"{label}.mappings[{index}].{side}_semantic_pointer drift"
                )
            if node is not None:
                observed_semantic_hash = canonical_json_sha256(semantic_value(node))
                if mapping.get("semantic_hash") != observed_semantic_hash:
                    failures.append(
                        f"{label}.mappings[{index}] {side} semantic_hash drift"
                    )
                expected_chunk_id = sha256_bytes(
                    f"{artifact_digest}\0{semantic_path}\0{observed_semantic_hash}".encode(
                        "utf-8"
                    )
                )
                if mapping.get(f"{side}_chunk_id") != expected_chunk_id:
                    failures.append(
                        f"{label}.mappings[{index}].{side}_chunk_id drift"
                    )

        parents = semantic_parents.get(side, {})
        children = semantic_children.get(side, {})
        for path, parent in parents.items():
            if parent is None or path not in spans_by_path or parent not in spans_by_path:
                continue
            child_span = spans_by_path[path]
            parent_span = spans_by_path[parent]
            if (
                child_span.get("start_byte", -1) < parent_span.get("start_byte", 0)
                or child_span.get("end_byte", 0) > parent_span.get("end_byte", -1)
            ):
                failures.append(f"{label} {side} parent span does not cover {path}")
        for parent, child_paths in children.items():
            ranged = [
                (
                    spans_by_path[path].get("start_byte"),
                    spans_by_path[path].get("end_byte"),
                    path,
                )
                for path in child_paths
                if path in spans_by_path
            ]
            if any(not _is_int(start) or not _is_int(end, minimum=1) for start, end, _ in ranged):
                continue
            ranged.sort()
            for previous, current in zip(ranged, ranged[1:], strict=False):
                if previous[1] > current[0]:
                    failures.append(
                        f"{label} {side} sibling spans overlap: {previous[2]} / {current[2]}"
                    )


def _validate_module_behavior_layer(
    *,
    symbol: str,
    source_function: object,
    layer: object,
    cases: object,
    source_validation: object,
    target_validation: object,
    source_observations: object,
    target_observations: object,
    failures: list[str],
) -> None:
    """Verify reported behavior rows against manifest cases and persisted observations."""

    label = f"module function {symbol} behavior"
    if not isinstance(layer, dict) or not isinstance(cases, list) or not cases:
        failures.append(f"{label} or its cases are invalid")
        return
    case_count = len(cases)
    expected_counts = {
        "case_count": case_count,
        "pass_count": case_count,
        "source_runtime_pass_count": case_count,
        "target_runtime_pass_count": case_count,
        "counterexample_count": 0,
        "oracle_conflict_count": 0,
    }
    for field, expected in expected_counts.items():
        if layer.get(field) != expected:
            failures.append(f"{label}.{field} must equal {expected}")
    if layer.get("status") != "PASSED":
        failures.append(f"{label}.status must be PASSED")
    for field in ("source_runtime_passed", "target_runtime_passed"):
        if layer.get(field) is not True:
            failures.append(f"{label}.{field} must be true")
    if layer.get("counterexamples") != []:
        failures.append(f"{label}.counterexamples must be empty")
    if not isinstance(source_validation, dict) or not isinstance(target_validation, dict):
        failures.append(f"{label} validation records are missing")
        return
    for side, validation, observations in (
        ("source", source_validation, source_observations),
        ("target", target_validation, target_observations),
    ):
        if validation.get("status") != "PASSED":
            failures.append(f"{label} {side} validation did not pass")
        if validation.get("case_count") != case_count:
            failures.append(f"{label} {side} validation case count drift")
        if not isinstance(observations, list) or len(observations) != case_count:
            failures.append(f"{label} {side} persisted observations are incomplete")
        elif validation.get("observations") != observations:
            failures.append(f"{label} {side} validation/observation artifact drift")
    results = layer.get("results")
    if not isinstance(results, list) or len(results) != case_count:
        failures.append(f"{label}.results count drift")
        return
    by_case_id = {
        item.get("case_id"): item for item in results if isinstance(item, dict)
    }
    if set(by_case_id) != set(range(case_count)) or len(by_case_id) != len(results):
        failures.append(f"{label}.results case ids are not exact")
        return
    if not isinstance(source_observations, list) or not isinstance(
        target_observations, list
    ):
        return
    for case_id, case in enumerate(cases):
        if not isinstance(case, dict):
            failures.append(f"{label} case {case_id} is invalid")
            continue
        result = by_case_id[case_id]
        expected = case.get("expected")
        if result.get("status") != "PASSED":
            failures.append(f"{label} case {case_id} did not pass")
        if result.get("independent_expected") != expected:
            failures.append(f"{label} case {case_id} expected value drift")
        canonical = result.get("canonical")
        if not isinstance(canonical, dict) or canonical.get("status") != "RETURNED":
            failures.append(f"{label} case {case_id} canonical result is invalid")
        elif canonical.get("error") is not None or canonical.get("value") != expected:
            failures.append(f"{label} case {case_id} canonical value drift")
        if result.get("source_native") != source_observations[case_id]:
            failures.append(f"{label} case {case_id} source observation drift")
        if result.get("target_native") != target_observations[case_id]:
            failures.append(f"{label} case {case_id} target observation drift")
        if (
            isinstance(result.get("source_native"), dict)
            and isinstance(result.get("target_native"), dict)
            and result["source_native"].get("raw") != result["target_native"].get("raw")
        ):
            failures.append(f"{label} case {case_id} raw native encodings differ")

    api = _engine_proof_api(failures, label)
    if api is None or not isinstance(source_function, dict):
        return
    Function, _, behavior_equivalence = api
    try:
        function = Function.from_mapping(source_function)
        regenerated = behavior_equivalence(
            function,
            cases,
            source_observations,
            target_observations,
        )
    except Exception as exc:
        failures.append(f"{label} independent canonical replay failed: {exc}")
        return
    if layer != regenerated:
        failures.append(f"{label} differs from independent canonical replay")

    return_type = function.return_type
    for side, observations in (
        ("source", source_observations),
        ("target", target_observations),
    ):
        for case_id, observation in enumerate(observations):
            observation_label = f"{label} {side} observation {case_id}"
            if not isinstance(observation, dict) or set(observation) != {
                "case_id",
                "encoding",
                "raw",
                "status",
                "value",
            }:
                failures.append(f"{observation_label} keys are not exact")
                continue
            value = observation.get("value")
            if observation.get("case_id") != case_id:
                failures.append(f"{observation_label} case_id drift")
            if observation.get("status") != "RETURNED":
                failures.append(f"{observation_label} status must be RETURNED")
            if return_type == "integer":
                valid = (
                    observation.get("encoding") == "i64-dec"
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                    and -(2**63) <= value <= 2**63 - 1
                    and observation.get("raw") == str(value)
                )
            elif return_type == "number":
                valid = (
                    observation.get("encoding") == "fp64-hex"
                    and isinstance(value, int | float)
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    and observation.get("raw")
                    == struct.pack(">d", float(value)).hex()
                )
            elif return_type == "boolean":
                valid = (
                    observation.get("encoding") == "bool"
                    and isinstance(value, bool)
                    and observation.get("raw") == ("true" if value else "false")
                )
            else:
                valid = False
            if not valid:
                failures.append(f"{observation_label} typed raw encoding drift")


def _validate_module_formal_closure(
    *,
    symbol: str,
    signature: object,
    source_function: object,
    target_function: object,
    semantic_layer: object,
    case_manifest_sha256: object,
    formal: object,
    module_input_sha256: object,
    route_scope: dict[str, Any],
    artifacts_by_path: dict[str, tuple[dict[str, Any], Path, str]],
    failures: list[str],
) -> None:
    """Rebind and replay one function's input/SMT/result proof closure."""

    label = f"module function {symbol} formal"
    if not isinstance(formal, dict):
        failures.append(f"{label} layer is invalid")
        return
    records: dict[str, tuple[dict[str, Any], Path, str]] = {}
    for field, role in (
        ("formal_input_path", "formal-function-input"),
        ("solver_input_path", "formal-function-smt2"),
        ("formal_result_path", "formal-function-result"),
    ):
        relative = formal.get(field)
        record = artifacts_by_path.get(relative) if isinstance(relative, str) else None
        if record is None or record[0].get("role") != role:
            failures.append(f"{label}.{field} is not bound to role {role}")
            continue
        digest_field = field.replace("_path", "_sha256")
        if formal.get(digest_field) != record[2]:
            failures.append(f"{label}.{digest_field} drift")
        records[role] = record
    if set(records) != {
        "formal-function-input",
        "formal-function-smt2",
        "formal-function-result",
    }:
        return
    input_record = records["formal-function-input"]
    solver_record = records["formal-function-smt2"]
    result_record = records["formal-function-result"]
    try:
        formal_input = load(input_record[1])
        formal_result = load(result_record[1])
    except Exception as exc:
        failures.append(f"{label} closure JSON is invalid: {exc}")
        return
    if set(formal_input) != FORMAL_FUNCTION_INPUT_KEYS:
        failures.append(f"{label} input keys are not exact")
    if set(formal_result) != FORMAL_FUNCTION_RESULT_KEYS:
        failures.append(f"{label} result keys are not exact")
    expected_route = {
        "route_key": route_scope.get("route_key"),
        "source_language": route_scope.get("source_language"),
        "target_language": route_scope.get("target_language"),
    }
    if formal_input.get("route") != expected_route:
        failures.append(f"{label} input route drift")
    for field, expected in (
        ("schema_version", "1.0.0"),
        ("kind", "typed-pure-module-function-formal-input"),
        ("profile", "typed-pure-module-v1"),
        ("input_domain", SPECIALIZED_INPUT_DOMAIN),
        ("module_input_sha256", module_input_sha256),
        ("symbol", symbol),
        ("signature", signature),
        ("case_manifest_sha256", case_manifest_sha256),
    ):
        if formal_input.get(field) != expected:
            failures.append(f"{label} input {field} drift")
    for side in ("source", "target"):
        function_value = formal_input.get(f"{side}_function")
        if canonical_json_sha256(function_value) != formal_input.get(
            f"{side}_function_sha256"
        ):
            failures.append(f"{label} {side} function digest drift")
    expected_source_function = semantic_value(source_function)
    expected_target_function = semantic_value(target_function)
    if formal_input.get("source_function") != expected_source_function:
        failures.append(f"{label} source function is detached from source module IR")
    if formal_input.get("target_function") != expected_target_function:
        failures.append(f"{label} target function is detached from target module IR")
    expected_semantic = _expected_semantic_layer(source_function, target_function)
    if semantic_layer != expected_semantic:
        failures.append(f"{label} semantic layer differs from bound module IR")
    for key, expected in (
        ("schema_version", "1.0.0"),
        ("kind", "typed-pure-module-function-formal-result"),
        ("profile", "typed-pure-module-v1"),
        ("symbol", symbol),
        ("status", "PROVED_UNDER_ASSUMPTIONS"),
        ("property_status", "PROVED"),
        ("proof_strength", "THEOREM_UNDER_ASSUMPTIONS"),
        ("solver", "z3"),
        ("version", "4.16.0"),
        ("countermodel", None),
        ("formal_input_digest", input_record[2]),
        ("solver_input_digest", solver_record[2]),
        ("certification_status", "NOT_CERTIFIED"),
    ):
        if formal_result.get(key) != expected:
            failures.append(f"{label} result {key} drift")
    for key in FORMAL_FUNCTION_RESULT_KEYS:
        if formal.get(key) != formal_result.get(key):
            failures.append(f"{label} report/result {key} drift")
    assumptions = formal_result.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions or any(
        not isinstance(item, str) or not item for item in assumptions
    ):
        failures.append(f"{label} assumptions must be non-empty")
    claim_scope = formal_result.get("claim_scope")
    if (
        not isinstance(claim_scope, dict)
        or claim_scope.get("input_domain") != SPECIALIZED_INPUT_DOMAIN
    ):
        failures.append(f"{label} claim input domain drift")
    if formal_result.get("external_soundness_boundary") != {
        "analyzer_and_emitter_soundness": "ASSUMPTION",
        "source_compiler_runtime_soundness": "NOT_RUN",
        "target_compiler_runtime_soundness": "NOT_RUN",
    }:
        failures.append(f"{label} external soundness boundary is overstated")
    expected_input_ref = {"path": input_record[1].name, "sha256": input_record[2]}
    expected_solver_ref = {"path": solver_record[1].name, "sha256": solver_record[2]}
    if formal_result.get("formal_input") != expected_input_ref:
        failures.append(f"{label} result formal_input ref drift")
    if formal_result.get("solver_input") != expected_solver_ref:
        failures.append(f"{label} result solver_input ref drift")
    expected_replay = {
        "kind": "z3-cli-check-sat",
        "argv": ["z3", "-smt2", solver_record[1].name],
        "working_directory": ".",
        "expected_exit_code": 0,
        "expected_stdout": "unsat",
    }
    if formal_result.get("replay_contract") != expected_replay:
        failures.append(f"{label} replay contract drift")
    options = formal_result.get("options")
    if options != {
        "timeout_ms": 30000,
        "random_seed": 0,
        "theories": ["QF_BV", "FP", "Seq", "Bool", "Int"],
    }:
        failures.append(f"{label} solver options drift")
    solver_text = solver_record[1].read_text(encoding="utf-8")
    required_headers = (
        f"; formal_input_digest: {input_record[2]}",
        f"; formal-input-sha256: {input_record[2]}",
        f"; formal-input-path: {input_record[1].name}",
        f"; input-domain: {SPECIALIZED_INPUT_DOMAIN}",
    )
    if any(header not in solver_text.splitlines()[:16] for header in required_headers):
        failures.append(f"{label} SMT input header is not bound to formal input/domain")
    regenerated_closure = _fresh_formal_equivalence(
        source_function=expected_source_function,
        target_function=expected_target_function,
        source_language=route_scope.get("source_language"),
        target_language=route_scope.get("target_language"),
        input_digest=input_record[2],
        formal_input_reference=expected_input_ref,
        input_domain=SPECIALIZED_INPUT_DOMAIN,
        label=label,
        failures=failures,
    )
    if regenerated_closure is None:
        return
    regenerated, regenerated_smt = regenerated_closure
    _smt_assertions_equivalent(
        solver_text,
        regenerated_smt,
        label=label,
        failures=failures,
    )
    regenerated_solver = regenerated.get("solver")
    if not isinstance(regenerated_solver, dict):
        failures.append(f"{label} regenerated solver identity is invalid")
        return
    expected_result = {
        "schema_version": "1.0.0",
        "kind": "typed-pure-module-function-formal-result",
        "profile": "typed-pure-module-v1",
        "symbol": symbol,
        "status": regenerated.get("status"),
        "property_status": regenerated.get("property_status"),
        "proof_strength": regenerated.get("proof_strength"),
        "solver": regenerated_solver.get("name"),
        "version": regenerated_solver.get("version"),
        "options": {
            "timeout_ms": regenerated_solver.get("timeout_ms"),
            "random_seed": regenerated_solver.get("random_seed"),
            "theories": regenerated_solver.get("theories"),
        },
        "assumptions": regenerated.get("assumptions"),
        "countermodel": regenerated.get("countermodel"),
        "formal_input_digest": input_record[2],
        "solver_input_digest": solver_record[2],
        "formal_input": expected_input_ref,
        "solver_input": expected_solver_ref,
        "replay_contract": expected_replay,
        "claim_scope": regenerated.get("claim_scope"),
        "reason": regenerated.get("reason"),
        "external_soundness_boundary": regenerated.get(
            "external_soundness_boundary"
        ),
        "independent_encodings": regenerated.get("independent_encodings"),
        "certification_status": regenerated.get("certification_status"),
    }
    if formal_result != expected_result:
        failures.append(f"{label} result differs from independent re-encoding")
    if regenerated.get("status") != "PROVED_UNDER_ASSUMPTIONS" or regenerated.get(
        "property_status"
    ) != "PROVED":
        failures.append(f"{label} independent re-encoding did not prove the property")
    _validate_nonvacuous_smt(
        smt_text=regenerated_smt,
        persisted_path=solver_record[1],
        label=label,
        failures=failures,
    )


def _validate_function_formal_closure(
    *,
    label: str,
    manifest: dict[str, Any],
    formal_input: object,
    formal_input_record: tuple[dict[str, Any], Path, str],
    solver_input_record: tuple[dict[str, Any], Path, str],
    solver_result: object,
    failures: list[str],
) -> None:
    """Independently regenerate one corpus proof from its byte-bound input."""

    if not isinstance(formal_input, dict) or not isinstance(solver_result, dict):
        failures.append(f"{label} input/result documents are invalid")
        return
    source_binding = formal_input.get("source_normalized_ir")
    target_binding = formal_input.get("target_relift_normalized_ir")
    if not isinstance(source_binding, dict) or not isinstance(target_binding, dict):
        failures.append(f"{label} normalized function bindings are missing")
        return
    source_function = source_binding.get("formal_function")
    target_function = target_binding.get("formal_function")
    if not isinstance(source_function, dict) or not isinstance(target_function, dict):
        failures.append(f"{label} normalized formal functions are missing")
        return
    source_language = manifest.get("source", {}).get("language")
    target_language = manifest.get("target", {}).get("language")
    domain_api = _engine_domain_api(failures, label)
    if domain_api is None:
        return
    SemanticIR, enforce_semantic_domain, enforce_case_domain = domain_api
    try:
        source_ir = SemanticIR.from_mapping(source_binding.get("semantic_ir"))
        target_ir = SemanticIR.from_mapping(target_binding.get("semantic_ir"))
        enforce_semantic_domain(source_ir, source_language, target_language)
        enforce_semantic_domain(target_ir, source_language, target_language)
        if len(source_ir.functions) != 1 or len(target_ir.functions) != 1:
            raise ValueError("formal semantic IR must contain exactly one function")
        cases_path = formal_input_record[1].parent / "inputs" / "cases.json"
        cases = _load_json_array(cases_path)
        enforce_case_domain(
            source_ir.functions[0], cases, source_language, target_language
        )
    except Exception as exc:
        failures.append(f"{label} specialized semantic/case domain rejected: {exc}")
        return
    formal_input_reference = {
        "path": formal_input_record[1].name,
        "sha256": formal_input_record[2],
    }
    input_domain = "profile-total-domain"
    claim_scope = formal_input.get("claim_scope")
    if isinstance(claim_scope, dict) and isinstance(
        claim_scope.get("input_domain"), str
    ):
        input_domain = claim_scope["input_domain"]
    regenerated_closure = _fresh_formal_equivalence(
        source_function=source_function,
        target_function=target_function,
        source_language=source_language,
        target_language=target_language,
        input_digest=formal_input_record[2],
        formal_input_reference=formal_input_reference,
        input_domain=input_domain,
        label=label,
        failures=failures,
    )
    if regenerated_closure is None:
        return
    regenerated, regenerated_smt = regenerated_closure
    persisted_smt = solver_input_record[1].read_bytes()
    try:
        persisted_smt_text = persisted_smt.decode("utf-8")
    except UnicodeDecodeError as exc:
        failures.append(f"{label} persisted SMT is not UTF-8: {exc}")
        return
    _smt_assertions_equivalent(
        persisted_smt_text,
        regenerated_smt,
        label=label,
        failures=failures,
    )
    expected_result = {
        **regenerated,
        "formal_input_digest": formal_input_record[2],
        "solver_input_digest": solver_input_record[2],
    }
    if solver_result != expected_result:
        failures.append(f"{label} solver result differs from independent re-encoding")
    if regenerated.get("status") != "PROVED_UNDER_ASSUMPTIONS" or regenerated.get(
        "property_status"
    ) != "PROVED":
        failures.append(f"{label} independent re-encoding did not prove the property")
    _validate_nonvacuous_smt(
        smt_text=persisted_smt_text,
        persisted_path=solver_input_record[1],
        label=label,
        failures=failures,
    )


def strict_evidence_requested(certification: dict[str, Any]) -> bool:
    evidence_format = certification.get("evidence_format")
    return (
        isinstance(evidence_format, int)
        and not isinstance(evidence_format, bool)
        and evidence_format >= 2
    ) or "formal_equivalence" in certification


def _is_int(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _require_exact_keys(
    failures: list[str],
    value: object,
    *,
    required: set[str],
    allowed: set[str] | None = None,
    label: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        failures.append(f"{label} must be an object")
        return None
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - (allowed or required))
    if missing:
        failures.append(f"{label} missing keys: {', '.join(missing)}")
    if extra:
        failures.append(f"{label} has unknown keys: {', '.join(extra)}")
    return value


def _require_nonempty_strings(
    failures: list[str], values: object, label: str
) -> list[str] | None:
    if not isinstance(values, list) or any(
        not isinstance(item, str) or not item for item in values
    ):
        failures.append(f"{label} must be an array of non-empty strings")
        return None
    return values


def _require_digest(failures: list[str], value: object, label: str) -> str | None:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        failures.append(f"{label} must be a canonical sha256 digest")
        return None
    return value


def _resolve_below(
    root: Path, relative: object, label: str, failures: list[str]
) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        failures.append(f"{label} must be a non-empty route-relative path")
        return None
    root_resolved = root.resolve()
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        failures.append(f"{label} escapes the route directory: {relative}")
        return None
    return candidate


def _replay_execution_root(route: Path) -> Path:
    """Return the immutable root within which a replay command may resolve.

    Checked-in routes live below ``<repo>/routes`` and may invoke the pinned
    engine or runner from that repository.  Relocated evidence bundles keep
    their replay launcher below the route directory itself.
    """

    resolved = route.resolve()
    if resolved.parent.name == "routes":
        return resolved.parent.parent
    return resolved


def _resolve_replay_path(
    cwd: Path,
    token: str,
    execution_root: Path,
    label: str,
    failures: list[str],
) -> Path | None:
    if not token or Path(token).is_absolute() or "://" in token or "\\" in token:
        failures.append(f"{label} must be a relative POSIX path")
        return None
    candidate = (cwd / token).resolve(strict=False)
    try:
        candidate.relative_to(execution_root.resolve())
    except ValueError:
        failures.append(f"{label} escapes the replay execution root: {token}")
        return None
    if not candidate.is_file():
        failures.append(f"{label} does not exist: {token}")
        return None
    return candidate


def _resolve_replay_directory(
    cwd: Path,
    token: str,
    execution_root: Path,
    label: str,
    failures: list[str],
) -> Path | None:
    if not token or Path(token).is_absolute() or "://" in token or "\\" in token:
        failures.append(f"{label} must be a relative POSIX path")
        return None
    candidate = (cwd / token).resolve(strict=False)
    try:
        candidate.relative_to(execution_root.resolve())
    except ValueError:
        failures.append(f"{label} escapes the replay execution root: {token}")
        return None
    if not candidate.is_dir():
        failures.append(f"{label} does not exist: {token}")
        return None
    return candidate


def _validate_replay_command(
    *,
    route: Path,
    manifest: dict[str, Any],
    command: list[str],
    cwd: Path,
    records: dict[str, tuple[dict[str, Any], Path, str]],
    failures: list[str],
) -> None:
    """Validate that replay argv is executable, scoped, and byte-bound.

    The command is intentionally restricted to a Python launcher, optionally
    provisioned by ``uv run --locked``.  Repository evidence may invoke the
    exact route runner; a relocated pack may invoke its route-local integrity
    launcher.  In either case the executed Python file must be present in
    ``artifact_refs`` with the exact observed digest.
    """

    execution_root = _replay_execution_root(route)
    executable = command[0]
    script_index: int | None = None

    if executable == "uv":
        if shutil.which("uv") is None:
            failures.append("formal_proof.replay.command executable uv is unavailable")
        if len(command) < 8 or command[1] not in {"--directory", "--project"}:
            failures.append(
                "formal_proof.replay.command uv form must declare --directory or --project"
            )
            return
        uv_scope = command[1].removeprefix("--")
        uv_root = _resolve_replay_directory(
            cwd,
            command[2],
            execution_root,
            f"formal_proof.replay.command uv {uv_scope}",
            failures,
        )
        if command[1] == "--project" and uv_root is not None:
            for project_member in ("pyproject.toml", "uv.lock"):
                member_path = uv_root / project_member
                if not member_path.is_file():
                    failures.append(
                        "formal_proof.replay.command uv project is missing "
                        f"{project_member}"
                    )
                    continue
                member_digest = sha256_file(member_path)
                try:
                    member_relative = member_path.relative_to(route.resolve()).as_posix()
                except ValueError:
                    failures.append(
                        "formal_proof.replay.command uv project member is outside the route: "
                        f"{project_member}"
                    )
                    continue
                member_bindings = [
                    record
                    for record in records.values()
                    if record[0].get("role") == "engine-source"
                    and record[0].get("path") == member_relative
                    and record[2] == member_digest
                ]
                if len(member_bindings) != 1:
                    failures.append(
                        "formal_proof.replay.command uv project member must have exactly "
                        f"one engine-source binding: {project_member}"
                    )
        if command[3:6] != ["run", "--locked", "python"]:
            failures.append(
                "formal_proof.replay.command uv form must use run --locked python"
            )
        script_index = 6
    elif executable in {"python", "python3"}:
        if shutil.which(executable) is None:
            failures.append(
                f"formal_proof.replay.command executable {executable} is unavailable"
            )
        script_index = 1
    elif "/" in executable:
        interpreter = _resolve_replay_path(
            cwd,
            executable,
            execution_root,
            "formal_proof.replay.command interpreter",
            failures,
        )
        if interpreter is not None and (
            not interpreter.name.startswith("python")
            or not os.access(interpreter, os.X_OK)
        ):
            failures.append(
                "formal_proof.replay.command interpreter must be an executable Python binary"
            )
        script_index = 1
    else:
        failures.append(
            "formal_proof.replay.command must use python, python3, a relative Python binary, or uv"
        )
        return

    if script_index >= len(command):
        failures.append("formal_proof.replay.command is missing its Python script")
        return
    script = _resolve_replay_path(
        cwd,
        command[script_index],
        execution_root,
        "formal_proof.replay.command script",
        failures,
    )
    if script is None:
        return
    if script.suffix != ".py":
        failures.append("formal_proof.replay.command script must be a Python file")

    script_digest = sha256_file(script)
    try:
        route_relative = script.relative_to(route.resolve()).as_posix()
    except ValueError:
        root_relative = script.relative_to(execution_root.resolve()).as_posix()

        def path_matches(reference: str) -> bool:
            return reference == root_relative or reference.endswith("/" + root_relative)

    else:

        def path_matches(reference: str) -> bool:
            return reference == route_relative

    bindings = [
        record
        for record in records.values()
        if record[0].get("role") in {"engine-source", "replay-tool"}
        and record[2] == script_digest
        and isinstance(record[0].get("path"), str)
        and path_matches(record[0]["path"])
    ]
    if len(bindings) != 1:
        failures.append(
            "formal_proof.replay.command script must have exactly one matching engine-source or replay-tool artifact"
        )

    arguments = command[script_index + 1 :]
    parsed: dict[str, str] = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option not in {"--repo-root", "--route"} or index + 1 >= len(arguments):
            failures.append(
                f"formal_proof.replay.command has unsupported argument: {option}"
            )
            return
        if option in parsed:
            failures.append(f"formal_proof.replay.command repeats argument: {option}")
            return
        parsed[option] = arguments[index + 1]
        index += 2

    route_argument = parsed.get("--route")
    if route_argument == ".":
        if cwd.resolve() != route.resolve():
            failures.append(
                "formal_proof.replay.command --route . requires the route directory as cwd"
            )
    elif route_argument != manifest.get("route_key"):
        failures.append(
            "formal_proof.replay.command --route must bind the exact route_key"
        )
    repository_argument = parsed.get("--repo-root")
    if repository_argument is not None:
        repository_root = (cwd / repository_argument).resolve(strict=False)
        if repository_root != execution_root.resolve() or not repository_root.is_dir():
            failures.append(
                "formal_proof.replay.command --repo-root must resolve to the replay execution root"
            )


def validate_artifact_ref(
    route: Path,
    reference: object,
    label: str,
    failures: list[str],
    *,
    require_identity: bool = True,
) -> tuple[Path, str] | None:
    value = _require_exact_keys(
        failures,
        reference,
        required=ARTIFACT_REF_KEYS if require_identity else {"path", "sha256", "bytes"},
        label=label,
    )
    if value is None:
        return None
    if require_identity:
        artifact_id = value.get("artifact_id")
        if (
            not isinstance(artifact_id, str)
            or ARTIFACT_ID_RE.fullmatch(artifact_id) is None
        ):
            failures.append(f"{label}.artifact_id is invalid")
        role = value.get("role")
        if role not in ARTIFACT_ROLES:
            failures.append(f"{label}.role is invalid")
    path = _resolve_below(route, value.get("path"), f"{label}.path", failures)
    digest = _require_digest(failures, value.get("sha256"), f"{label}.sha256")
    byte_count = value.get("bytes")
    if not _is_int(byte_count, minimum=1):
        failures.append(f"{label}.bytes must be a positive integer")
    if path is None or digest is None or not _is_int(byte_count, minimum=1):
        return None
    if not path.is_file():
        failures.append(f"{label} artifact is missing: {value.get('path')}")
        return None
    observed_bytes = path.stat().st_size
    if observed_bytes != byte_count:
        failures.append(
            f"{label} byte count mismatch: expected {byte_count}, observed {observed_bytes}"
        )
    observed_digest = sha256_file(path)
    if observed_digest != digest:
        failures.append(f"{label} digest mismatch: {value.get('path')}")
    return path, observed_digest


def _artifact_record(
    records: dict[str, tuple[dict[str, Any], Path, str]],
    artifact_id: object,
    *,
    expected_roles: set[str],
    label: str,
    failures: list[str],
) -> tuple[dict[str, Any], Path, str] | None:
    if not isinstance(artifact_id, str) or artifact_id not in records:
        failures.append(f"{label} references unknown artifact_id: {artifact_id}")
        return None
    record = records[artifact_id]
    role = record[0].get("role")
    if role not in expected_roles:
        failures.append(
            f"{label} artifact {artifact_id} has role {role}, expected one of {sorted(expected_roles)}"
        )
        return None
    return record


def _json_pointer_value(document: object, pointer: str) -> object:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with /")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise ValueError(f"invalid array index {token!r}")
            index = int(token)
            if index >= len(current):
                raise ValueError(f"array index out of range: {index}")
            current = current[index]
        elif isinstance(current, dict):
            if token not in current:
                raise ValueError(f"object key does not exist: {token!r}")
            current = current[token]
        else:
            raise ValueError(f"cannot traverse through {type(current).__name__}")
    return current


def _artifact_pointer(
    records: dict[str, tuple[dict[str, Any], Path, str]],
    reference: object,
    *,
    expected_role: str,
    label: str,
    failures: list[str],
) -> tuple[str, str, object, tuple[dict[str, Any], Path, str]] | None:
    if not isinstance(reference, str) or reference.count("#") != 1:
        failures.append(f"{label} must be <artifact_id>#<RFC6901 JSON pointer>")
        return None
    artifact_id, pointer = reference.split("#", 1)
    record = _artifact_record(
        records,
        artifact_id,
        expected_roles={expected_role},
        label=label,
        failures=failures,
    )
    if record is None:
        return None
    try:
        document = json.loads(
            record[1].read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
        value = _json_pointer_value(document, pointer)
    except Exception as exc:
        failures.append(f"{label} cannot resolve JSON pointer {pointer!r}: {exc}")
        return None
    return artifact_id, pointer, value, record


def _validate_formal_input_document(
    route: Path,
    record: tuple[dict[str, Any], Path, str],
    records: dict[str, tuple[dict[str, Any], Path, str]],
    manifest: dict[str, Any],
    proof: dict[str, Any],
    label: str,
    failures: list[str],
) -> dict[str, Any] | None:
    try:
        document = load(record[1])
    except Exception as exc:
        failures.append(f"{label} is invalid JSON: {exc}")
        return None
    missing = FORMAL_INPUT_REQUIRED_KEYS - set(document)
    if missing:
        failures.append(f"{label} missing keys: {', '.join(sorted(missing))}")
        return document
    if document.get("kind") != "elmos.formal-equivalence-input":
        failures.append(f"{label}.kind is invalid")
    route_scope = document.get("route")
    if not isinstance(route_scope, dict):
        failures.append(f"{label}.route must be an object")
    else:
        expected_route = {
            "source_language": manifest.get("source", {}).get("language"),
            "target_language": manifest.get("target", {}).get("language"),
            "profile": manifest.get("profiles", {}).get("semantic_profile"),
        }
        if route_scope != expected_route:
            failures.append(f"{label}.route does not match route.json")
    claim_scope = document.get("claim_scope")
    if not isinstance(claim_scope, dict):
        failures.append(f"{label}.claim_scope must be an object")
    else:
        if (
            claim_scope.get("relation")
            != "canonical-normalized-source-ir-to-target-relift-ir"
            or claim_scope.get("original_source_bytes_theorem") is not False
            or claim_scope.get("source_compiler_runtime_soundness") != "NOT_RUN"
            or claim_scope.get("target_compiler_runtime_soundness") != "NOT_RUN"
        ):
            failures.append(f"{label}.claim_scope overstates the proved relation")
        if (
            manifest.get("gates", {}).get(
                "canonical_finite_no_error_input_domain_required"
            )
            is True
            and claim_scope.get("input_domain") != SPECIALIZED_INPUT_DOMAIN
        ):
            failures.append(f"{label}.claim_scope input domain drift")

    by_relative = {
        item[0].get("path"): item
        for item in records.values()
        if isinstance(item[0].get("path"), str)
    }
    formal_parent = record[1].parent

    def bound_sibling(
        reference: object, expected_role: str, child_label: str
    ) -> tuple[dict[str, Any], Path, str] | None:
        if not isinstance(reference, dict):
            failures.append(f"{label}.{child_label} reference must be an object")
            return None
        relative = reference.get("path")
        digest = reference.get("sha256")
        if not isinstance(relative, str) or not relative:
            failures.append(f"{label}.{child_label}.path is invalid")
            return None
        candidate = (formal_parent / relative).resolve(strict=False)
        try:
            route_relative = candidate.relative_to(route.resolve()).as_posix()
        except ValueError:
            failures.append(f"{label}.{child_label} escapes the route")
            return None
        child_record = by_relative.get(route_relative)
        if child_record is None:
            failures.append(
                f"{label}.{child_label} is not bound by artifact_refs: {route_relative}"
            )
            return None
        if child_record[0].get("role") != expected_role:
            failures.append(
                f"{label}.{child_label} has role {child_record[0].get('role')}, expected {expected_role}"
            )
        if digest != child_record[2]:
            failures.append(f"{label}.{child_label} digest mismatch")
        return child_record

    for field, role, expected_binding_role in (
        (
            "source_artifact",
            "corpus-artifact",
            "original-source-analyzer-input",
        ),
        ("target_artifact", "target-artifact", "emitted-target-analyzer-input"),
    ):
        binding = document.get(field)
        if not isinstance(binding, dict):
            failures.append(f"{label}.{field} must be an object")
            continue
        if binding.get("role") != expected_binding_role:
            failures.append(f"{label}.{field}.role is invalid")
        encoded = binding.get("content_base64")
        expected_digest = binding.get("sha256")
        expected_bytes = binding.get("byte_count")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, TypeError, ValueError):
            failures.append(f"{label}.{field}.content_base64 is invalid")
            decoded = b""
        if (
            not _is_int(expected_bytes, minimum=1)
            or len(decoded) != expected_bytes
            or sha256_bytes(decoded) != expected_digest
        ):
            failures.append(f"{label}.{field} embedded bytes do not match digest")
        child_record = bound_sibling(
            binding.get("content_reference"), role, f"{field}.content_reference"
        )
        if child_record is not None and child_record[1].read_bytes() != decoded:
            failures.append(f"{label}.{field} embedded/reference bytes differ")

    normalized_documents: dict[str, dict[str, Any]] = {}
    for field, role, expected_binding_role in (
        (
            "source_normalized_ir",
            "source-ir",
            "canonical-source-normalized-ir",
        ),
        (
            "target_relift_normalized_ir",
            "target-ir",
            "emitted-target-relift-normalized-ir",
        ),
    ):
        binding = document.get(field)
        if not isinstance(binding, dict):
            failures.append(f"{label}.{field} must be an object")
            continue
        if binding.get("role") != expected_binding_role:
            failures.append(f"{label}.{field}.role is invalid")
        child_record = bound_sibling(binding.get("artifact"), role, f"{field}.artifact")
        semantic_ir = binding.get("semantic_ir")
        formal_function = binding.get("formal_function")
        if not isinstance(semantic_ir, dict) or not isinstance(formal_function, dict):
            failures.append(f"{label}.{field} semantic IR/function is invalid")
            continue
        normalized_documents[field] = semantic_ir
        if child_record is not None:
            try:
                persisted_ir = load(child_record[1])
            except Exception as exc:
                failures.append(f"{label}.{field} persisted IR is invalid: {exc}")
            else:
                if persisted_ir != semantic_ir:
                    failures.append(f"{label}.{field} embedded/persisted IR differ")
        functions = semantic_ir.get("functions")
        if not isinstance(functions, list) or len(functions) != 1:
            failures.append(f"{label}.{field} must contain exactly one function")
        elif semantic_value(functions[0]) != formal_function:
            failures.append(f"{label}.{field} formal_function drift")
        if binding.get("semantic_ir_sha256") != canonical_json_sha256(semantic_ir):
            failures.append(f"{label}.{field} semantic_ir_sha256 mismatch")
        if binding.get("formal_function_sha256") != canonical_json_sha256(
            formal_function
        ):
            failures.append(f"{label}.{field} formal_function_sha256 mismatch")
    if semantic_value(
        normalized_documents.get("source_normalized_ir", {}).get("functions")
    ) != semantic_value(
        normalized_documents.get("target_relift_normalized_ir", {}).get("functions")
    ):
        failures.append(f"{label} source/target normalized functions differ")

    analyzer_identity = document.get("analyzer_identity")
    if not isinstance(analyzer_identity, dict):
        failures.append(f"{label}.analyzer_identity must be an object")
    else:
        for identity_field, ir_field, expected_language, expected_mode in (
            (
                "source",
                "source_normalized_ir",
                manifest.get("source", {}).get("language"),
                None,
            ),
            (
                "target_relift",
                "target_relift_normalized_ir",
                manifest.get("target", {}).get("language"),
                "emitted-target",
            ),
        ):
            identity = analyzer_identity.get(identity_field)
            semantic_ir = normalized_documents.get(ir_field, {})
            if (
                not isinstance(identity, dict)
                or identity.get("name") != semantic_ir.get("analyzer")
                or identity.get("version") != semantic_ir.get("analyzer_version")
                or identity.get("language") != expected_language
                or (expected_mode is not None and identity.get("mode") != expected_mode)
            ):
                failures.append(
                    f"{label}.analyzer_identity.{identity_field} differs from bound IR"
                )
    emitter_identity = document.get("emitter_identity")
    if (
        not isinstance(emitter_identity, dict)
        or emitter_identity.get("target_language")
        != manifest.get("target", {}).get("language")
        or not isinstance(emitter_identity.get("normalization_rules"), list)
        or not isinstance(emitter_identity.get("helper_digests"), list)
    ):
        failures.append(f"{label}.emitter_identity is invalid")

    implementation = document.get("implementation_identity")
    if not isinstance(implementation, dict):
        failures.append(f"{label}.implementation_identity must be an object")
    else:
        expected_files = {
            "engine": "src/elmos_polyglot_route/engine.py",
            "equivalence_encoder": "src/elmos_polyglot_route/equivalence.py",
            "emitter": "src/elmos_polyglot_route/emitter.py",
        }
        engine_records = [
            item for item in records.values() if item[0].get("role") == "engine-source"
        ]
        for identity, expected_suffix in expected_files.items():
            value = implementation.get(identity)
            if not isinstance(value, dict) or value.get("path") != expected_suffix:
                failures.append(
                    f"{label}.implementation_identity.{identity} is invalid"
                )
                continue
            matches = [
                item
                for item in engine_records
                if str(item[0].get("path", "")).endswith(
                    f"engines/polyglot-route-engine/{expected_suffix}"
                )
            ]
            if len(matches) != 1:
                failures.append(
                    f"{label}.implementation_identity.{identity} has no unique captured source"
                )
            elif (
                value.get("sha256") != matches[0][2]
                or value.get("byte_count") != matches[0][1].stat().st_size
            ):
                failures.append(
                    f"{label}.implementation_identity.{identity} digest/bytes drift"
                )

    assumptions = document.get("environment_assumptions")
    if (
        not isinstance(assumptions, list)
        or not assumptions
        or any(not isinstance(item, str) or not item for item in assumptions)
    ):
        failures.append(f"{label}.environment_assumptions must be non-empty")
    unsupported = document.get("unsupported_semantics")
    if (
        not isinstance(unsupported, list)
        or not unsupported
        or any(not isinstance(item, str) or not item for item in unsupported)
    ):
        failures.append(f"{label}.unsupported_semantics must be non-empty")
    solver = document.get("solver")
    if not isinstance(solver, dict):
        failures.append(f"{label}.solver must be an object")
    else:
        if solver.get("name") != proof.get("solver") or solver.get(
            "version"
        ) != proof.get("solver_version"):
            failures.append(f"{label}.solver identity differs from formal_proof")
        options = proof.get("solver_options")
        if isinstance(options, dict):
            for key in ("timeout_ms", "random_seed"):
                if solver.get(key) != options.get(key):
                    failures.append(f"{label}.solver {key} differs from formal_proof")
    return document


def _validate_optional_json_schema(
    data: dict[str, Any], schema_name: str, failures: list[str], label: str
) -> None:
    """Use jsonschema when the invoking environment provides it.

    Direct semantic validation below remains authoritative because the route CI
    intentionally runs with the standard-library Python interpreter as well as
    through the Batch 29 Make target that installs jsonschema.
    """

    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return
    schema = Path(__file__).resolve().parents[2] / "schemas" / "batch29" / schema_name
    try:
        jsonschema.Draft202012Validator(load(schema)).validate(data)
    except Exception as exc:
        failures.append(f"{label} schema validation failed: {exc}")


def validate_formal_equivalence(
    route: Path,
    manifest: dict[str, Any],
    certification: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate strict evidence format v2 without upgrading its proof claim.

    The return value is consumed by the route gate. Structural validation here
    proves only that referenced bytes and reported counts are internally
    consistent; the gate separately decides whether those states can pass.
    """

    failures: list[str] = []
    evidence_format = certification.get("evidence_format")
    if evidence_format is not None and not _is_int(evidence_format, minimum=1):
        failures.append("certification evidence_format must be a positive integer")
    if not strict_evidence_requested(certification):
        return None, failures

    reference = certification.get("formal_equivalence")
    resolved = validate_artifact_ref(
        route,
        reference,
        "formal_equivalence",
        failures,
        require_identity=False,
    )
    if resolved is None:
        return None, failures
    evidence_path, _ = resolved
    try:
        evidence = load(evidence_path)
    except Exception as exc:
        failures.append(str(exc))
        return None, failures

    _validate_optional_json_schema(
        evidence,
        "formal-equivalence-evidence.schema.json",
        failures,
        "formal equivalence evidence",
    )
    top = _require_exact_keys(
        failures,
        evidence,
        required=FORMAL_REQUIRED_KEYS,
        label="formal equivalence evidence",
    )
    if top is None:
        return evidence, failures
    if top.get("schema_version") != 2:
        failures.append("formal equivalence schema_version must be 2")
    if top.get("route_key") != manifest.get("route_key"):
        failures.append("formal equivalence route_key mismatch")
    profile = manifest.get("profiles", {}).get("semantic_profile")
    if top.get("semantic_profile") != profile:
        failures.append("formal equivalence semantic_profile mismatch")

    route_manifest_digest = _require_digest(
        failures, top.get("route_manifest_sha256"), "route_manifest_sha256"
    )
    if route_manifest_digest is not None and route_manifest_digest != sha256_file(
        route / "route.json"
    ):
        failures.append("route_manifest_sha256 does not bind route.json")
    profile_digest = _require_digest(
        failures, top.get("semantic_profile_sha256"), "semantic_profile_sha256"
    )
    profile_path = route / "lowering" / "profile.json"
    if not profile_path.is_file():
        failures.append("semantic profile artifact is missing")
    elif profile_digest is not None and profile_digest != sha256_file(profile_path):
        failures.append("semantic_profile_sha256 does not bind lowering/profile.json")
    artifact_digest = _require_digest(
        failures, top.get("artifact_sha256"), "artifact_sha256"
    )
    environment_digest = _require_digest(
        failures, top.get("environment_sha256"), "environment_sha256"
    )

    artifact_refs = top.get("artifact_refs")
    ref_digests: set[str] = set()
    ref_paths: set[str] = set()
    ref_records: dict[str, tuple[dict[str, Any], Path, str]] = {}
    if not isinstance(artifact_refs, list) or not artifact_refs:
        failures.append("artifact_refs must be a non-empty array")
    else:
        for index, item in enumerate(artifact_refs):
            verified = validate_artifact_ref(
                route, item, f"artifact_refs[{index}]", failures
            )
            if not isinstance(item, dict):
                continue
            relative = item.get("path")
            if isinstance(relative, str):
                if relative in ref_paths:
                    failures.append(
                        f"artifact_refs contains duplicate path: {relative}"
                    )
                ref_paths.add(relative)
            if verified is not None:
                ref_digests.add(verified[1])
                artifact_id = item.get("artifact_id")
                if isinstance(artifact_id, str):
                    if artifact_id in ref_records:
                        failures.append(
                            f"artifact_refs contains duplicate artifact_id: {artifact_id}"
                        )
                    else:
                        ref_records[artifact_id] = (item, verified[0], verified[1])

    formal_swift_receipt = _validate_swift_receipt_binding(
        source_language=manifest.get("source", {}).get("language"),
        target_language=manifest.get("target", {}).get("language"),
        records=[
            record
            for record in ref_records.values()
            if record[0].get("role") == "swift-analyzer-build-receipt"
        ],
        label="formal Swift analyzer build receipt",
        failures=failures,
    )
    if formal_swift_receipt is not None:
        swift_semantic_ir_count = 0
        for record in ref_records.values():
            if record[0].get("role") not in {"source-ir", "target-ir"}:
                continue
            try:
                semantic_document = load(record[1])
            except Exception:
                continue
            if _validate_swift_analyzer_version_binding(
                semantic_document=semantic_document,
                receipt=formal_swift_receipt,
                label=f"formal Swift semantic IR {record[0].get('path')}",
                failures=failures,
            ):
                swift_semantic_ir_count += 1
        if swift_semantic_ir_count != 3:
            failures.append(
                "formal Swift analyzer receipt must bind exactly three corpus semantic IR documents"
            )

    top_artifact_records: dict[str, tuple[dict[str, Any], Path, str]] = {}
    for label, artifact_id, digest, roles in (
        (
            "artifact",
            top.get("artifact_id"),
            artifact_digest,
            {"target-artifact"},
        ),
        (
            "environment",
            top.get("environment_artifact_id"),
            environment_digest,
            {"environment"},
        ),
    ):
        record = _artifact_record(
            ref_records,
            artifact_id,
            expected_roles=roles,
            label=f"{label}_artifact_id",
            failures=failures,
        )
        if record is not None and digest is not None and record[2] != digest:
            failures.append(
                f"{label}_sha256 does not match {label}_artifact_id {artifact_id}"
            )
        if record is not None:
            top_artifact_records[label] = record

    environment_document: dict[str, Any] | None = None
    environment_record = top_artifact_records.get("environment")
    if environment_record is not None:
        try:
            environment_document = load(environment_record[1])
        except Exception as exc:
            failures.append(f"environment artifact is invalid JSON: {exc}")
        else:
            if environment_document.get("route_key") != manifest.get("route_key"):
                failures.append("environment artifact route_key mismatch")
            if environment_document.get("independent_verification") != "NOT_RUN":
                failures.append(
                    "environment independent_verification must remain NOT_RUN"
                )
            if environment_document.get("external_certification") != "NOT_RUN":
                failures.append(
                    "environment external_certification must remain NOT_RUN"
                )
            source_manifest = environment_document.get("engine_source_manifest")
            if not isinstance(source_manifest, dict):
                failures.append("environment engine_source_manifest is missing")
            else:
                manifest_relative = source_manifest.get("path")
                manifest_record = next(
                    (
                        item
                        for item in ref_records.values()
                        if item[0].get("path") == manifest_relative
                    ),
                    None,
                )
                if (
                    manifest_record is None
                    or manifest_record[0].get("role") != "engine-source-manifest"
                ):
                    failures.append(
                        "environment engine_source_manifest is not role-bound"
                    )
                elif (
                    source_manifest.get("sha256") != manifest_record[2]
                    or source_manifest.get("bytes") != manifest_record[1].stat().st_size
                ):
                    failures.append(
                        "environment engine_source_manifest digest/bytes mismatch"
                    )
                else:
                    try:
                        source_manifest_document = load(manifest_record[1])
                    except Exception as exc:
                        failures.append(
                            f"engine source manifest is invalid JSON: {exc}"
                        )
                    else:
                        files = source_manifest_document.get("files")
                        if not isinstance(files, list) or not files:
                            failures.append("engine source manifest files are empty")
                        else:
                            declared_sources: set[str] = set()
                            live_repository_root = _replay_execution_root(route)
                            validate_live_sources = (
                                (live_repository_root / "engines").is_dir()
                                and (
                                    live_repository_root / "scripts" / "batch29"
                                ).is_dir()
                                and (
                                    live_repository_root / "schemas" / "batch29"
                                ).is_dir()
                            )
                            for index, item in enumerate(files):
                                if not isinstance(item, dict):
                                    failures.append(
                                        f"engine source manifest files[{index}] is invalid"
                                    )
                                    continue
                                repository_path = item.get("repository_path")
                                if (
                                    not isinstance(repository_path, str)
                                    or not repository_path
                                    or Path(repository_path).is_absolute()
                                    or "\\" in repository_path
                                    or any(
                                        part in {"", ".", ".."}
                                        for part in Path(repository_path).parts
                                    )
                                ):
                                    failures.append(
                                        f"engine source manifest files[{index}].repository_path is invalid"
                                    )
                                    repository_path = None
                                captured_path = item.get("captured_path")
                                declared_sources.add(str(captured_path))
                                captured_record = next(
                                    (
                                        record
                                        for record in ref_records.values()
                                        if record[0].get("path") == captured_path
                                    ),
                                    None,
                                )
                                if (
                                    captured_record is None
                                    or captured_record[0].get("role") != "engine-source"
                                ):
                                    failures.append(
                                        f"engine source manifest files[{index}] is not role-bound"
                                    )
                                elif (
                                    item.get("sha256") != captured_record[2]
                                    or item.get("bytes")
                                    != captured_record[1].stat().st_size
                                ):
                                    failures.append(
                                        f"engine source manifest files[{index}] digest/bytes mismatch"
                                    )
                                if (
                                    validate_live_sources
                                    and repository_path is not None
                                ):
                                    live_path = (
                                        live_repository_root / repository_path
                                    ).resolve(strict=False)
                                    try:
                                        live_path.relative_to(live_repository_root)
                                    except ValueError:
                                        failures.append(
                                            f"engine source manifest files[{index}].repository_path escapes the repository"
                                        )
                                    else:
                                        if not live_path.is_file():
                                            failures.append(
                                                f"engine source manifest live file is missing: {repository_path}"
                                            )
                                        elif (
                                            item.get("sha256") != sha256_file(live_path)
                                            or item.get("bytes")
                                            != live_path.stat().st_size
                                        ):
                                            failures.append(
                                                f"engine source manifest live file drifted: {repository_path}"
                                            )
                            actual_sources = {
                                str(record[0].get("path"))
                                for record in ref_records.values()
                                if record[0].get("role") == "engine-source"
                            }
                            if declared_sources != actual_sources:
                                failures.append(
                                    "engine source manifest does not exactly cover engine-source artifacts"
                                )
                            if source_manifest_document.get("file_count") != len(files):
                                failures.append(
                                    "engine source manifest file_count mismatch"
                                )
                            lock_reference = environment_document.get(
                                "route_engine_lock"
                            )
                            if not isinstance(lock_reference, dict):
                                failures.append(
                                    "environment route_engine_lock is missing"
                                )
                            else:
                                lock_entries = [
                                    item
                                    for item in files
                                    if isinstance(item, dict)
                                    and item.get("repository_path")
                                    == lock_reference.get("path")
                                ]
                                if len(lock_entries) != 1 or lock_entries[0].get(
                                    "sha256"
                                ) != lock_reference.get("sha256"):
                                    failures.append(
                                        "environment route_engine_lock is not bound by engine source manifest"
                                    )

    semantic_ir = _require_exact_keys(
        failures,
        top.get("semantic_ir"),
        required=SEMANTIC_IR_KEYS,
        label="semantic_ir",
    )
    if semantic_ir is not None:
        if semantic_ir.get("status") not in LAYER_STATUSES:
            failures.append("semantic_ir.status is invalid")
        for id_field, digest_field, role in (
            ("source_ir_artifact_id", "source_ir_sha256", "source-ir"),
            ("target_ir_artifact_id", "target_relift_ir_sha256", "target-ir"),
        ):
            digest = _require_digest(
                failures, semantic_ir.get(digest_field), f"semantic_ir.{digest_field}"
            )
            record = _artifact_record(
                ref_records,
                semantic_ir.get(id_field),
                expected_roles={role},
                label=f"semantic_ir.{id_field}",
                failures=failures,
            )
            if record is not None and digest is not None and record[2] != digest:
                failures.append(f"semantic_ir.{digest_field} does not match {id_field}")
        if not _is_int(semantic_ir.get("unknown_or_dropped_nodes"), minimum=0):
            failures.append(
                "semantic_ir.unknown_or_dropped_nodes must be a non-negative integer"
            )
        _require_nonempty_strings(
            failures, semantic_ir.get("differences"), "semantic_ir.differences"
        )

    semantic_chunks = _require_exact_keys(
        failures,
        top.get("semantic_chunks"),
        required=SEMANTIC_CHUNK_KEYS,
        label="semantic_chunks",
    )
    if semantic_chunks is not None:
        if semantic_chunks.get("status") not in LAYER_STATUSES:
            failures.append("semantic_chunks.status is invalid")
        chunk_evidence_ids = semantic_chunks.get("evidence_artifact_ids")
        if not isinstance(chunk_evidence_ids, list) or not chunk_evidence_ids:
            failures.append(
                "semantic_chunks.evidence_artifact_ids must be a non-empty array"
            )
        else:
            for index, artifact_id in enumerate(chunk_evidence_ids):
                _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"chunk-map"},
                    label=f"semantic_chunks.evidence_artifact_ids[{index}]",
                    failures=failures,
                )
        for field, minimum in (
            ("total", 1),
            ("matched", 0),
            ("unmatched", 0),
            ("ambiguous", 0),
        ):
            if not _is_int(semantic_chunks.get(field), minimum=minimum):
                failures.append(
                    f"semantic_chunks.{field} must be an integer >= {minimum}"
                )
        coverage = semantic_chunks.get("coverage")
        if not _is_number(coverage) or not 0 <= float(coverage) <= 1:
            failures.append("semantic_chunks.coverage must be between 0 and 1")
        chunks = semantic_chunks.get("chunks")
        ids: set[str] = set()
        observed = {"MATCHED": 0, "UNMATCHED": 0, "AMBIGUOUS": 0, "FAILED": 0}
        if not isinstance(chunks, list) or not chunks:
            failures.append("semantic_chunks.chunks must be a non-empty array")
        else:
            for index, item in enumerate(chunks):
                chunk = _require_exact_keys(
                    failures,
                    item,
                    required=CHUNK_KEYS,
                    label=f"semantic_chunks.chunks[{index}]",
                )
                if chunk is None:
                    continue
                chunk_id = chunk.get("chunk_id")
                if not isinstance(chunk_id, str) or not chunk_id:
                    failures.append(
                        f"semantic_chunks.chunks[{index}].chunk_id is invalid"
                    )
                elif chunk_id in ids:
                    failures.append(f"semantic chunk id is duplicated: {chunk_id}")
                else:
                    ids.add(chunk_id)
                semantic_hash = _require_digest(
                    failures,
                    chunk.get("semantic_hash"),
                    f"semantic_chunks.chunks[{index}].semantic_hash",
                )
                source_pointer = _artifact_pointer(
                    ref_records,
                    chunk.get("source_ref"),
                    expected_role="source-ir",
                    label=f"semantic_chunks.chunks[{index}].source_ref",
                    failures=failures,
                )
                target_pointer = _artifact_pointer(
                    ref_records,
                    chunk.get("target_ref"),
                    expected_role="target-ir",
                    label=f"semantic_chunks.chunks[{index}].target_ref",
                    failures=failures,
                )
                if source_pointer is not None and target_pointer is not None:
                    if source_pointer[1] != target_pointer[1]:
                        failures.append(
                            f"semantic_chunks.chunks[{index}] source/target JSON pointers differ"
                        )
                    for pointer_label, pointer in (
                        ("source", source_pointer),
                        ("target", target_pointer),
                    ):
                        observed_hash = canonical_json_sha256(
                            semantic_value(pointer[2])
                        )
                        if semantic_hash is not None and observed_hash != semantic_hash:
                            failures.append(
                                f"semantic_chunks.chunks[{index}] {pointer_label} subtree hash mismatch"
                            )
                status = chunk.get("status")
                if status not in CHUNK_STATUSES:
                    failures.append(
                        f"semantic_chunks.chunks[{index}].status is invalid"
                    )
                else:
                    observed[status] += 1
            total = semantic_chunks.get("total")
            if _is_int(total, minimum=1) and total != len(chunks):
                failures.append("semantic_chunks.total does not equal chunks length")
            if (
                _is_int(semantic_chunks.get("matched"))
                and semantic_chunks.get("matched") != observed["MATCHED"]
            ):
                failures.append("semantic_chunks.matched does not match chunk statuses")
            if (
                _is_int(semantic_chunks.get("unmatched"))
                and semantic_chunks.get("unmatched") != observed["UNMATCHED"]
            ):
                failures.append(
                    "semantic_chunks.unmatched does not match chunk statuses"
                )
            if (
                _is_int(semantic_chunks.get("ambiguous"))
                and semantic_chunks.get("ambiguous") != observed["AMBIGUOUS"]
            ):
                failures.append(
                    "semantic_chunks.ambiguous does not match chunk statuses"
                )
            if _is_int(total, minimum=1) and _is_number(coverage):
                expected_coverage = observed["MATCHED"] / total
                if abs(float(coverage) - expected_coverage) > 1e-12:
                    failures.append(
                        "semantic_chunks.coverage does not equal matched / total"
                    )
        expected_chunk_rows: set[tuple[str, str, str, str, str]] = set()
        if isinstance(chunk_evidence_ids, list):
            for artifact_id in chunk_evidence_ids:
                chunk_record = ref_records.get(artifact_id)
                if chunk_record is None:
                    continue
                try:
                    chunk_document = load(chunk_record[1])
                except Exception as exc:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} is invalid JSON: {exc}"
                    )
                    continue
                if chunk_document.get("status") != "PASSED":
                    failures.append(
                        f"semantic chunk artifact {artifact_id} did not pass"
                    )
                if chunk_document.get("path_scheme") != "rfc6901-json-pointer-v1":
                    failures.append(
                        f"semantic chunk artifact {artifact_id} does not use RFC6901 pointers"
                    )
                mappings = chunk_document.get("mappings")
                if not isinstance(mappings, list) or not mappings:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} has no mappings"
                    )
                    continue
                parent = chunk_record[1].parent
                source_candidates = [
                    (candidate_id, record)
                    for candidate_id, record in ref_records.items()
                    if record[0].get("role") == "source-ir"
                    and record[1].parent == parent
                ]
                target_candidates = [
                    (candidate_id, record)
                    for candidate_id, record in ref_records.items()
                    if record[0].get("role") == "target-ir"
                    and record[1].parent == parent
                ]
                if len(source_candidates) != 1 or len(target_candidates) != 1:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} must have one sibling source IR and target IR"
                    )
                    continue
                source_artifact_id = source_candidates[0][0]
                target_artifact_id = target_candidates[0][0]
                source_semantic_function = None
                target_semantic_function = None
                for side, candidate, destination in (
                    ("source", source_candidates[0][1], "source"),
                    ("target", target_candidates[0][1], "target"),
                ):
                    try:
                        semantic_document = load(candidate[1])
                        semantic_functions = semantic_document.get("functions")
                    except Exception as exc:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} {side} IR is invalid: {exc}"
                        )
                        continue
                    if not isinstance(semantic_functions, list) or len(semantic_functions) != 1:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} {side} IR must contain one function"
                        )
                        continue
                    if destination == "source":
                        source_semantic_function = semantic_functions[0]
                    else:
                        target_semantic_function = semantic_functions[0]
                for mapping_index, mapping in enumerate(mappings):
                    if (
                        not isinstance(mapping, dict)
                        or mapping.get("status") != "EXACT"
                    ):
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} is not EXACT"
                        )
                        continue
                    pointer = mapping.get("semantic_path")
                    semantic_hash = mapping.get("semantic_hash")
                    source_chunk_id = mapping.get("source_chunk_id")
                    target_chunk_id = mapping.get("target_chunk_id")
                    source_artifact_pointer = mapping.get("source_artifact_pointer")
                    target_artifact_pointer = mapping.get("target_artifact_pointer")
                    if not all(
                        isinstance(item, str) and item
                        for item in (
                            pointer,
                            semantic_hash,
                            source_chunk_id,
                            target_chunk_id,
                            source_artifact_pointer,
                            target_artifact_pointer,
                        )
                    ):
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} is incomplete"
                        )
                        continue
                    for pointer_label, artifact_pointer, expected_roles in (
                        (
                            "source_artifact_pointer",
                            source_artifact_pointer,
                            {"corpus-artifact"},
                        ),
                        (
                            "target_artifact_pointer",
                            target_artifact_pointer,
                            {"target-artifact"},
                        ),
                    ):
                        if artifact_pointer.count("#") != 1:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping {mapping_index} {pointer_label} is invalid"
                            )
                            continue
                        artifact_digest, artifact_json_pointer = artifact_pointer.split(
                            "#", 1
                        )
                        if artifact_json_pointer != pointer:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping {mapping_index} {pointer_label} pointer drift"
                            )
                        matches = [
                            record
                            for record in ref_records.values()
                            if record[2] == artifact_digest
                            and record[0].get("role") in expected_roles
                            and (
                                pointer_label != "target_artifact_pointer"
                                or record[1].parent == parent
                            )
                        ]
                        if not matches:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping {mapping_index} {pointer_label} digest is not role-bound"
                            )
                    expected_source_chunk_id = sha256_bytes(
                        (
                            f"{source_artifact_pointer.split('#', 1)[0]}\0{pointer}\0{semantic_hash}"
                        ).encode("utf-8")
                    )
                    expected_target_chunk_id = sha256_bytes(
                        (
                            f"{target_artifact_pointer.split('#', 1)[0]}\0{pointer}\0{semantic_hash}"
                        ).encode("utf-8")
                    )
                    if source_chunk_id != expected_source_chunk_id:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} source_chunk_id drift"
                        )
                    if target_chunk_id != expected_target_chunk_id:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} target_chunk_id drift"
                        )
                    expected_chunk_rows.add(
                        (
                            f"{parent.name}:{source_chunk_id}",
                            f"{source_artifact_id}#{pointer}",
                            f"{target_artifact_id}#{pointer}",
                            semantic_hash,
                            "MATCHED",
                        )
                    )
                required = chunk_document.get("required_source_chunk_count")
                mapped = chunk_document.get("mapped_source_chunk_count")
                if required != len(mappings) or mapped != len(mappings):
                    failures.append(
                        f"semantic chunk artifact {artifact_id} count fields do not match mappings"
                    )
                if chunk_document.get("coverage") != 1.0:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} coverage is not 1.0"
                    )
                if manifest.get("gates", {}).get("concrete_spans_required") is True:
                    span_validation = chunk_document.get("span_validation")
                    source_digest = (
                        span_validation.get("source", {}).get("artifact_sha256")
                        if isinstance(span_validation, dict)
                        and isinstance(span_validation.get("source"), dict)
                        else None
                    )
                    target_digest = (
                        span_validation.get("target", {}).get("artifact_sha256")
                        if isinstance(span_validation, dict)
                        and isinstance(span_validation.get("target"), dict)
                        else None
                    )
                    source_record = next(
                        (
                            record
                            for record in ref_records.values()
                            if record[2] == source_digest
                            and record[0].get("role") == "corpus-artifact"
                        ),
                        None,
                    )
                    target_record = next(
                        (
                            record
                            for record in ref_records.values()
                            if record[2] == target_digest
                            and record[0].get("role") == "target-artifact"
                        ),
                        None,
                    )
                    _validate_concrete_chunk_document(
                        chunk_document,
                        label=f"semantic chunk artifact {artifact_id}",
                        failures=failures,
                        source_record=source_record,
                        target_record=target_record,
                        source_function=source_semantic_function,
                        target_function=target_semantic_function,
                    )
        if isinstance(chunks, list):
            actual_chunk_rows = {
                (
                    item.get("chunk_id"),
                    item.get("source_ref"),
                    item.get("target_ref"),
                    item.get("semantic_hash"),
                    item.get("status"),
                )
                for item in chunks
                if isinstance(item, dict)
            }
            if actual_chunk_rows != expected_chunk_rows:
                failures.append(
                    "semantic_chunks.chunks do not exactly match bound chunk-map artifacts"
                )

    behavior = _require_exact_keys(
        failures,
        top.get("behavior_equivalence"),
        required=BEHAVIOR_KEYS,
        label="behavior_equivalence",
    )
    if behavior is not None:
        if behavior.get("status") not in LAYER_STATUSES:
            failures.append("behavior_equivalence.status is invalid")
        behavior_artifact_ids = behavior.get("evidence_artifact_ids")
        observed_behavior_documents: list[dict[str, Any]] = []
        if not isinstance(behavior_artifact_ids, list) or not behavior_artifact_ids:
            failures.append(
                "behavior_equivalence.evidence_artifact_ids must be a non-empty array"
            )
        else:
            for index, artifact_id in enumerate(behavior_artifact_ids):
                record = _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"behavior-result"},
                    label=f"behavior_equivalence.evidence_artifact_ids[{index}]",
                    failures=failures,
                )
                if record is None:
                    continue
                try:
                    document = load(record[1])
                except Exception as exc:
                    failures.append(
                        f"behavior artifact {artifact_id} is not valid JSON: {exc}"
                    )
                else:
                    observed_behavior_documents.append(document)
        for field in (
            "source_runtime_artifact_ids",
            "target_runtime_artifact_ids",
        ):
            runtime_ids = behavior.get(field)
            if not isinstance(runtime_ids, list) or not runtime_ids:
                failures.append(f"behavior_equivalence.{field} must be non-empty")
                continue
            for index, artifact_id in enumerate(runtime_ids):
                _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"behavior-result"},
                    label=f"behavior_equivalence.{field}[{index}]",
                    failures=failures,
                )
                if (
                    isinstance(behavior_artifact_ids, list)
                    and artifact_id not in behavior_artifact_ids
                ):
                    failures.append(
                        f"behavior_equivalence.{field}[{index}] is absent from evidence_artifact_ids"
                    )
        total_cases = behavior.get("total_cases")
        passed_cases = behavior.get("passed_cases")
        if not _is_int(total_cases, minimum=1):
            failures.append(
                "behavior_equivalence.total_cases must be a positive integer"
            )
        if not _is_int(passed_cases, minimum=0):
            failures.append(
                "behavior_equivalence.passed_cases must be a non-negative integer"
            )
        elif _is_int(total_cases, minimum=1) and passed_cases > total_cases:
            failures.append("behavior_equivalence.passed_cases exceeds total_cases")
        for field in (
            "canonical_oracle_passed",
            "source_runtime_passed",
            "target_runtime_passed",
        ):
            if not isinstance(behavior.get(field), bool):
                failures.append(f"behavior_equivalence.{field} must be boolean")
        counterexamples = behavior.get("counterexamples")
        if not isinstance(counterexamples, list):
            failures.append("behavior_equivalence.counterexamples must be an array")
        else:
            case_ids: set[str] = set()
            for index, item in enumerate(counterexamples):
                counterexample = _require_exact_keys(
                    failures,
                    item,
                    required=COUNTEREXAMPLE_REQUIRED_KEYS,
                    allowed=COUNTEREXAMPLE_ALLOWED_KEYS,
                    label=f"behavior_equivalence.counterexamples[{index}]",
                )
                if counterexample is None:
                    continue
                case_id = counterexample.get("case_id")
                reason = counterexample.get("reason")
                if not isinstance(case_id, str) or not case_id:
                    failures.append(
                        f"behavior_equivalence.counterexamples[{index}].case_id is invalid"
                    )
                elif case_id in case_ids:
                    failures.append(
                        f"behavior counterexample id is duplicated: {case_id}"
                    )
                else:
                    case_ids.add(case_id)
                if not isinstance(reason, str) or not reason:
                    failures.append(
                        f"behavior_equivalence.counterexamples[{index}].reason is invalid"
                    )
                evidence_ref = counterexample.get("evidence_ref")
                if evidence_ref is not None and evidence_ref not in ref_paths:
                    failures.append(
                        f"behavior_equivalence.counterexamples[{index}].evidence_ref is not in artifact_refs"
                    )
            if _is_int(total_cases, minimum=1) and _is_int(passed_cases):
                if total_cases - passed_cases != len(counterexamples):
                    failures.append(
                        "behavior counterexample count must equal total_cases - passed_cases"
                    )
        if observed_behavior_documents:
            observed_counts: list[tuple[int, int]] = []
            for index, item in enumerate(observed_behavior_documents):
                case_count = item.get("case_count")
                pass_count = item.get("pass_count")
                if not _is_int(case_count, minimum=1) or not _is_int(
                    pass_count, minimum=0
                ):
                    failures.append(
                        f"behavior artifact {index} has invalid case/pass counts"
                    )
                    continue
                observed_counts.append((case_count, pass_count))
            observed_total = sum(item[0] for item in observed_counts)
            observed_passed = sum(item[1] for item in observed_counts)
            if observed_total != total_cases:
                failures.append(
                    "behavior_equivalence.total_cases does not match behavior artifacts"
                )
            if observed_passed != passed_cases:
                failures.append(
                    "behavior_equivalence.passed_cases does not match behavior artifacts"
                )
            observed_oracle = all(
                item.get("oracle_conflict_count") == 0
                for item in observed_behavior_documents
            )
            observed_source = all(
                item.get("source_runtime_passed") is True
                for item in observed_behavior_documents
            )
            observed_target = all(
                item.get("target_runtime_passed") is True
                for item in observed_behavior_documents
            )
            for field, observed in (
                ("canonical_oracle_passed", observed_oracle),
                ("source_runtime_passed", observed_source),
                ("target_runtime_passed", observed_target),
            ):
                if behavior.get(field) is not observed:
                    failures.append(
                        f"behavior_equivalence.{field} does not match behavior artifacts"
                    )

    formal_proof = _require_exact_keys(
        failures,
        top.get("formal_proof"),
        required=FORMAL_PROOF_KEYS,
        label="formal_proof",
    )
    if formal_proof is not None:
        status = formal_proof.get("status")
        if status not in PROOF_STATUSES:
            failures.append("formal_proof.status is invalid")
        for field in ("solver", "solver_version"):
            if not isinstance(formal_proof.get(field), str) or not formal_proof.get(
                field
            ):
                failures.append(f"formal_proof.{field} must be a non-empty string")
        if isinstance(environment_document, dict):
            environment_solver = environment_document.get("solver")
            if (
                not isinstance(environment_solver, dict)
                or environment_solver.get("name") != formal_proof.get("solver")
                or environment_solver.get("version")
                != formal_proof.get("solver_version")
            ):
                failures.append(
                    "formal_proof solver identity differs from environment artifact"
                )
        options = formal_proof.get("solver_options")
        if not isinstance(options, dict) or not options:
            failures.append("formal_proof.solver_options must be a non-empty object")
        elif any(
            not isinstance(value, str | int | float | bool)
            for value in options.values()
        ):
            failures.append("formal_proof.solver_options contains a non-scalar value")
        input_digest = _require_digest(
            failures, formal_proof.get("input_digest"), "formal_proof.input_digest"
        )
        proof_input_record = _artifact_record(
            ref_records,
            formal_proof.get("input_artifact_id"),
            expected_roles={"proof-input-bundle"},
            label="formal_proof.input_artifact_id",
            failures=failures,
        )
        if (
            proof_input_record is not None
            and input_digest is not None
            and proof_input_record[2] != input_digest
        ):
            failures.append(
                "formal_proof.input_digest does not match input_artifact_id"
            )
        result_artifact_ids = formal_proof.get("result_artifact_ids")
        if not isinstance(result_artifact_ids, list) or not result_artifact_ids:
            failures.append("formal_proof.result_artifact_ids must be non-empty")
        else:
            for index, artifact_id in enumerate(result_artifact_ids):
                _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"solver-result"},
                    label=f"formal_proof.result_artifact_ids[{index}]",
                    failures=failures,
                )
        assumptions = _require_nonempty_strings(
            failures, formal_proof.get("assumptions"), "formal_proof.assumptions"
        )
        obligations = formal_proof.get("obligations")
        obligation_statuses: list[str] = []
        obligation_ids: set[str] = set()
        obligation_formal_input_ids: set[str] = set()
        obligation_solver_input_ids: set[str] = set()
        obligation_solver_result_ids: set[str] = set()
        obligation_assumption_union: set[str] = set()
        if not isinstance(obligations, list) or not obligations:
            failures.append("formal_proof.obligations must be a non-empty array")
        else:
            for index, item in enumerate(obligations):
                obligation = _require_exact_keys(
                    failures,
                    item,
                    required=OBLIGATION_REQUIRED_KEYS,
                    allowed=OBLIGATION_ALLOWED_KEYS,
                    label=f"formal_proof.obligations[{index}]",
                )
                if obligation is None:
                    continue
                obligation_id = obligation.get("obligation_id")
                if not isinstance(obligation_id, str) or not obligation_id:
                    failures.append(
                        f"formal_proof.obligations[{index}].obligation_id is invalid"
                    )
                elif obligation_id in obligation_ids:
                    failures.append(
                        f"formal proof obligation id is duplicated: {obligation_id}"
                    )
                else:
                    obligation_ids.add(obligation_id)
                obligation_status = obligation.get("status")
                if obligation_status not in PROOF_STATUSES:
                    failures.append(
                        f"formal_proof.obligations[{index}].status is invalid"
                    )
                else:
                    obligation_statuses.append(obligation_status)
                if not isinstance(obligation.get("scope"), str) or not obligation.get(
                    "scope"
                ):
                    failures.append(
                        f"formal_proof.obligations[{index}].scope is invalid"
                    )
                obligation_digest = _require_digest(
                    failures,
                    obligation.get("input_digest"),
                    f"formal_proof.obligations[{index}].input_digest",
                )
                formal_input_record = _artifact_record(
                    ref_records,
                    obligation.get("formal_input_artifact_id"),
                    expected_roles={"formal-input"},
                    label=f"formal_proof.obligations[{index}].formal_input_artifact_id",
                    failures=failures,
                )
                for field_name, destination in (
                    ("formal_input_artifact_id", obligation_formal_input_ids),
                    ("solver_input_artifact_id", obligation_solver_input_ids),
                    ("solver_result_artifact_id", obligation_solver_result_ids),
                ):
                    value = obligation.get(field_name)
                    if isinstance(value, str):
                        destination.add(value)
                solver_input_record = _artifact_record(
                    ref_records,
                    obligation.get("solver_input_artifact_id"),
                    expected_roles={"solver-input"},
                    label=f"formal_proof.obligations[{index}].solver_input_artifact_id",
                    failures=failures,
                )
                solver_result_record = _artifact_record(
                    ref_records,
                    obligation.get("solver_result_artifact_id"),
                    expected_roles={"solver-result"},
                    label=f"formal_proof.obligations[{index}].solver_result_artifact_id",
                    failures=failures,
                )
                formal_input_document = None
                if formal_input_record is not None:
                    formal_input_document = _validate_formal_input_document(
                        route,
                        formal_input_record,
                        ref_records,
                        manifest,
                        formal_proof,
                        f"formal_proof.obligations[{index}].formal_input",
                        failures,
                    )
                    environment_assumptions = (
                        formal_input_document.get("environment_assumptions")
                        if isinstance(formal_input_document, dict)
                        else None
                    )
                    obligation_assumptions = obligation.get("assumptions")
                    if (
                        isinstance(environment_assumptions, list)
                        and isinstance(obligation_assumptions, list)
                        and not set(environment_assumptions).issubset(
                            set(obligation_assumptions)
                        )
                    ):
                        failures.append(
                            f"formal_proof.obligations[{index}] omits formal-input assumptions"
                        )
                if (
                    solver_input_record is not None
                    and obligation_digest is not None
                    and solver_input_record[2] != obligation_digest
                ):
                    failures.append(
                        f"formal_proof.obligations[{index}].input_digest does not match solver_input_artifact_id"
                    )
                if (
                    isinstance(result_artifact_ids, list)
                    and obligation.get("solver_result_artifact_id")
                    not in result_artifact_ids
                ):
                    failures.append(
                        f"formal_proof.obligations[{index}] result is absent from formal_proof.result_artifact_ids"
                    )
                if formal_input_record is not None and solver_input_record is not None:
                    try:
                        solver_input_text = solver_input_record[1].read_text(
                            encoding="utf-8"
                        )
                    except Exception as exc:
                        failures.append(
                            f"formal_proof.obligations[{index}] solver input is unreadable: {exc}"
                        )
                    else:
                        if formal_input_record[2] not in solver_input_text:
                            failures.append(
                                f"formal_proof.obligations[{index}] SMT input does not bind formal input"
                            )
                if formal_input_record is not None and solver_result_record is not None:
                    try:
                        result_document = load(solver_result_record[1])
                    except Exception as exc:
                        failures.append(
                            f"formal_proof.obligations[{index}] solver result is invalid JSON: {exc}"
                        )
                    else:
                        formal_input_digest = formal_input_record[2]
                        declared_formal_input_digest = result_document.get(
                            "formal_input_digest"
                        )
                        if declared_formal_input_digest != formal_input_digest:
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result does not bind formal input"
                            )
                        if result_document.get("input_digest") != formal_input_digest:
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result input_digest differs from formal input"
                            )
                        formal_input_reference = result_document.get("formal_input")
                        expected_formal_input_path = formal_input_record[1].name
                        if (
                            not isinstance(formal_input_reference, dict)
                            or formal_input_reference.get("path")
                            != expected_formal_input_path
                            or formal_input_reference.get("sha256")
                            != formal_input_digest
                        ):
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result formal_input reference drift"
                            )
                        declared_solver_input_digest = result_document.get(
                            "solver_input_digest"
                        )
                        if (
                            solver_input_record is not None
                            and declared_solver_input_digest != solver_input_record[2]
                        ):
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result does not bind SMT input"
                            )
                        result_status = result_document.get("status")
                        if result_status != obligation_status:
                            failures.append(
                                f"formal_proof.obligations[{index}] status does not match solver result"
                            )
                        if (
                            manifest.get("gates", {}).get(
                                "canonical_finite_no_error_input_domain_required"
                            )
                            is True
                            and (
                                not isinstance(
                                    result_document.get("claim_scope"), dict
                                )
                                or result_document["claim_scope"].get("input_domain")
                                != SPECIALIZED_INPUT_DOMAIN
                            )
                        ):
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result input domain drift"
                            )
                        if (
                            isinstance(formal_input_document, dict)
                            and solver_input_record is not None
                            and manifest.get("gates", {}).get(
                                "canonical_finite_no_error_input_domain_required"
                            )
                            is True
                        ):
                            _validate_function_formal_closure(
                                label=f"formal_proof.obligations[{index}]",
                                manifest=manifest,
                                formal_input=formal_input_document,
                                formal_input_record=formal_input_record,
                                solver_input_record=solver_input_record,
                                solver_result=result_document,
                                failures=failures,
                            )
                _require_nonempty_strings(
                    failures,
                    obligation.get("assumptions"),
                    f"formal_proof.obligations[{index}].assumptions",
                )
                if isinstance(obligation.get("assumptions"), list):
                    obligation_assumption_union.update(obligation["assumptions"])

        if (
            isinstance(result_artifact_ids, list)
            and set(result_artifact_ids) != obligation_solver_result_ids
        ):
            failures.append(
                "formal_proof.result_artifact_ids do not exactly match obligations"
            )
        if (
            isinstance(assumptions, list)
            and set(assumptions) != obligation_assumption_union
        ):
            failures.append(
                "formal_proof.assumptions do not equal the obligation assumption union"
            )

        if proof_input_record is not None:
            try:
                proof_bundle = load(proof_input_record[1])
            except Exception as exc:
                failures.append(f"formal proof input bundle is invalid JSON: {exc}")
            else:
                if proof_bundle.get("route_key") != manifest.get("route_key"):
                    failures.append("formal proof input bundle route_key mismatch")
                if proof_bundle.get("same_input_required") is not True:
                    failures.append(
                        "formal proof input bundle must require same-input composition"
                    )
                runs = proof_bundle.get("runs")
                observed_bundle_ids: dict[str, set[str]] = {
                    "formal_input": set(),
                    "smt2": set(),
                    "result": set(),
                }
                if not isinstance(runs, list) or not runs:
                    failures.append("formal proof input bundle runs are empty")
                else:
                    corpora: set[str] = set()
                    by_relative = {
                        record[0].get("path"): (artifact_id, record)
                        for artifact_id, record in ref_records.items()
                    }
                    for run_index, run in enumerate(runs):
                        if not isinstance(run, dict):
                            failures.append(
                                f"formal proof input bundle runs[{run_index}] is invalid"
                            )
                            continue
                        corpus = run.get("corpus")
                        if not isinstance(corpus, str) or corpus in corpora:
                            failures.append(
                                f"formal proof input bundle runs[{run_index}] corpus is invalid/duplicate"
                            )
                        else:
                            corpora.add(corpus)
                        for field, roles in (
                            ("formal_input", {"formal-input"}),
                            ("smt2", {"solver-input"}),
                            ("result", {"solver-result"}),
                            ("composition", {"formal-composition"}),
                        ):
                            reference = run.get(field)
                            if not isinstance(reference, dict):
                                failures.append(
                                    f"formal proof input bundle runs[{run_index}].{field} is invalid"
                                )
                                continue
                            relative = reference.get("path")
                            bound = by_relative.get(relative)
                            if bound is None or bound[1][0].get("role") not in roles:
                                failures.append(
                                    f"formal proof input bundle runs[{run_index}].{field} is not role-bound"
                                )
                                continue
                            if (
                                reference.get("sha256") != bound[1][2]
                                or reference.get("bytes") != bound[1][1].stat().st_size
                            ):
                                failures.append(
                                    f"formal proof input bundle runs[{run_index}].{field} digest/bytes mismatch"
                                )
                            if field in observed_bundle_ids:
                                observed_bundle_ids[field].add(bound[0])
                    expected_bundle_ids = {
                        "formal_input": obligation_formal_input_ids,
                        "smt2": obligation_solver_input_ids,
                        "result": obligation_solver_result_ids,
                    }
                    for field, expected_ids in expected_bundle_ids.items():
                        if observed_bundle_ids[field] != expected_ids:
                            failures.append(
                                f"formal proof input bundle {field} set does not match obligations"
                            )

        if status == "PROVED":
            if any(item != "PROVED" for item in obligation_statuses):
                failures.append(
                    "formal_proof PROVED requires every obligation to be PROVED"
                )
            if assumptions:
                failures.append("formal_proof PROVED cannot carry assumptions")
            if isinstance(obligations, list) and any(
                item.get("assumptions")
                for item in obligations
                if isinstance(item, dict)
            ):
                failures.append("PROVED obligations cannot carry assumptions")
        elif status == "PROVED_UNDER_ASSUMPTIONS":
            if not assumptions:
                failures.append(
                    "PROVED_UNDER_ASSUMPTIONS requires explicit assumptions"
                )
            if any(
                item not in {"PROVED", "PROVED_UNDER_ASSUMPTIONS"}
                for item in obligation_statuses
            ):
                failures.append(
                    "PROVED_UNDER_ASSUMPTIONS cannot contain unresolved obligations"
                )
        elif status == "AXIOM" and not assumptions:
            failures.append("AXIOM evidence requires explicit assumptions")
        if status in PROOF_STATUSES and obligation_statuses:
            precedence = (
                "COUNTEREXAMPLE",
                "TIMEOUT",
                "UNKNOWN",
                "NOT_RUN",
                "BOUNDED",
                "AXIOM",
                "PROVED_UNDER_ASSUMPTIONS",
                "PROVED",
            )
            derived = next(item for item in precedence if item in obligation_statuses)
            if status != derived:
                failures.append(
                    f"formal_proof.status {status} does not match obligation aggregate {derived}"
                )

        replay = _require_exact_keys(
            failures,
            formal_proof.get("replay"),
            required=REPLAY_KEYS,
            label="formal_proof.replay",
        )
        if replay is not None:
            command = replay.get("command")
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(item, str) or not item for item in command)
            ):
                failures.append(
                    "formal_proof.replay.command must be a non-empty argv array"
                )
            cwd = _resolve_below(
                route, replay.get("cwd"), "formal_proof.replay.cwd", failures
            )
            if cwd is not None and not cwd.is_dir():
                failures.append("formal_proof.replay.cwd is not an existing directory")
            if (
                cwd is not None
                and cwd.is_dir()
                and isinstance(command, list)
                and command
            ):
                _validate_replay_command(
                    route=route,
                    manifest=manifest,
                    command=command,
                    cwd=cwd,
                    records=ref_records,
                    failures=failures,
                )
            if replay.get("expected_exit_code") != 0:
                failures.append("formal_proof.replay.expected_exit_code must be zero")
            replay_result_digest = _require_digest(
                failures,
                replay.get("expected_result_sha256"),
                "formal_proof.replay.expected_result_sha256",
            )
            replay_result = _artifact_record(
                ref_records,
                replay.get("expected_result_artifact_id"),
                expected_roles={"solver-result"},
                label="formal_proof.replay.expected_result_artifact_id",
                failures=failures,
            )
            if (
                replay_result is not None
                and replay_result_digest is not None
                and replay_result[2] != replay_result_digest
            ):
                failures.append(
                    "formal_proof.replay expected result digest does not match artifact"
                )

    return evidence, failures


def _validate_module_inventory_document(
    *,
    document: dict[str, Any],
    label: str,
    language: object,
    artifact_record: tuple[dict[str, Any], Path, str] | None,
    route_swift_receipt: dict[str, Any] | None,
    failures: list[str],
) -> None:
    expected_keys = set(MODULE_INVENTORY_BASE_KEYS)
    if language == "swift":
        expected_keys.add("analyzer_build_receipt")
    if set(document) != expected_keys:
        failures.append(f"{label} top-level keys are not exact")
    expected_file = artifact_record[1].name if artifact_record is not None else None
    if (
        document.get("schema_version") != "1.0.0"
        or document.get("kind") != "elmos.typed-pure-module-inventory"
        or document.get("profile") != "typed-pure-module-v1"
        or document.get("source_language") != language
        or document.get("source_file") != expected_file
        or document.get("enumeration_status") != "PASSED"
        or document.get("diagnostics") != []
    ):
        failures.append(f"{label} identity/status is invalid")
    for field in ("analyzer", "analyzer_version"):
        if not isinstance(document.get(field), str) or not document.get(field):
            failures.append(f"{label}.{field} is missing")
    if language == "swift":
        embedded_receipt = document.get("analyzer_build_receipt")
        _validate_swift_analyzer_receipt_document(
            embedded_receipt,
            label=f"{label}.analyzer_build_receipt",
            failures=failures,
        )
        if route_swift_receipt is None or embedded_receipt != route_swift_receipt:
            failures.append(
                f"{label}.analyzer_build_receipt differs from the route receipt artifact"
            )
        analyzer_version = document.get("analyzer_version")
        if isinstance(embedded_receipt, dict) and isinstance(analyzer_version, str):
            source_inputs = embedded_receipt.get("source_inputs", {})
            toolchain = embedded_receipt.get("toolchain", {})
            dependency = embedded_receipt.get("dependency", {})
            expected_suffix = (
                f";source-inputs={source_inputs.get('sha256')};"
                f"swift-driver={toolchain.get('swift_driver_sha256')};"
                f"swift-syntax-tree={dependency.get('sha256')}"
            )
            if not analyzer_version.endswith(expected_suffix):
                failures.append(f"{label}.analyzer_version receipt binding drift")
    elif "analyzer_build_receipt" in document:
        failures.append(f"{label} contains an unexpected Swift analyzer receipt")
    if artifact_record is not None:
        if document.get("source_artifact_sha256") != artifact_record[2]:
            failures.append(f"{label} source artifact digest backlink mismatch")
        if document.get("source_artifact_bytes") != artifact_record[1].stat().st_size:
            failures.append(f"{label} source artifact byte-count backlink mismatch")
        fresh_directives = _scan_module_language_directives(
            artifact_record[1], language
        )
        if document.get("directives") != fresh_directives:
            failures.append(f"{label}.directives differ from raw artifact bytes")

    subjects = document.get("subjects")
    if not isinstance(subjects, list) or not subjects:
        failures.append(f"{label}.subjects must be a non-empty array")
        return
    occurrences: dict[tuple[str, str], int] = {}
    artifact_size = artifact_record[1].stat().st_size if artifact_record else 0
    for index, subject in enumerate(subjects):
        subject_label = f"{label}.subjects[{index}]"
        if not isinstance(subject, dict):
            failures.append(f"{subject_label} must be an object")
            continue
        if set(subject) != MODULE_INVENTORY_SUBJECT_KEYS:
            failures.append(f"{subject_label} keys are not exact")
        name = subject.get("name")
        qualified_name = subject.get("qualified_name")
        declaration_kind = subject.get("declaration_kind")
        signature = subject.get("signature")
        if any(
            not isinstance(value, str) or not value
            for value in (name, qualified_name, declaration_kind)
        ):
            failures.append(f"{subject_label} identity is invalid")
        if not isinstance(subject.get("analyzable"), bool):
            failures.append(f"{subject_label}.analyzable must be boolean")
        if (
            not isinstance(signature, dict)
            or not isinstance(signature.get("visibility"), str)
            or not signature.get("visibility")
            or not isinstance(signature.get("storage"), str)
            or not signature.get("storage")
        ):
            failures.append(f"{subject_label}.signature visibility/storage is invalid")
        span = subject.get("source_span")
        if not isinstance(span, dict) or set(span) != {
            "file",
            "start_byte",
            "end_byte",
        }:
            failures.append(f"{subject_label}.source_span is invalid")
        else:
            start = span.get("start_byte")
            end = span.get("end_byte")
            valid_offsets = _is_int(start, minimum=0) and _is_int(end, minimum=1)
            if span.get("file") != expected_file or not valid_offsets:
                failures.append(f"{subject_label}.source_span identity/bounds are invalid")
            else:
                assert isinstance(start, int) and isinstance(end, int)
                if end <= start:
                    failures.append(
                        f"{subject_label}.source_span identity/bounds are invalid"
                    )
                elif artifact_record is not None and end > artifact_size:
                    failures.append(f"{subject_label}.source_span exceeds artifact bytes")
        if isinstance(declaration_kind, str) and isinstance(qualified_name, str):
            key = (declaration_kind, qualified_name)
            expected_occurrence = occurrences.get(key, 0) + 1
            occurrences[key] = expected_occurrence
            if subject.get("occurrence") != expected_occurrence:
                failures.append(f"{subject_label}.occurrence is not canonical")


def _scan_module_language_directives(
    artifact: Path, language: object
) -> list[dict[str, Any]]:
    """Independently enumerate every C-family directive from raw UTF-8 bytes."""

    if language not in {"cpp", "objc"}:
        return []
    content = artifact.read_bytes()
    directives: list[dict[str, Any]] = []
    offset = 0
    for line in content.splitlines(keepends=True):
        body = line.rstrip(b"\r\n")
        candidates = [
            (index, marker)
            for marker in (b"#", b"%:", b"??=")
            if (index := body.find(marker)) >= 0
        ]
        if not candidates:
            offset += len(line)
            continue
        marker_offset, marker = min(candidates, key=lambda item: item[0])
        raw = body[marker_offset:]
        payload = raw[len(marker) :].lstrip()
        match = re.match(rb"([A-Za-z_][A-Za-z0-9_]*)", payload)
        if marker != b"#":
            kind = "alternative-directive-marker"
            value_bytes = raw
        elif match is None:
            kind = "invalid"
            value_bytes = payload
        else:
            kind = match.group(1).decode("ascii").lower()
            value_bytes = payload[match.end() :].strip()
        directives.append(
            {
                "order": len(directives),
                "kind": kind,
                "value": value_bytes.decode(
                    "utf-8", errors="backslashreplace"
                ),
                "source_span": {
                    "file": artifact.name,
                    "start_byte": offset + marker_offset,
                    "end_byte": offset + len(body),
                },
                "sha256": sha256_bytes(raw),
            }
        )
        offset += len(line)
    return directives


def _validate_module_language_boundary(
    *,
    side: str,
    language: object,
    inventory: dict[str, Any],
    closure: dict[str, Any],
    artifact_record: tuple[dict[str, Any], Path, str] | None,
    failures: list[str],
) -> None:
    prelude = closure.get("verified_language_prelude", {}).get(side)
    expected_prelude = {
        "status": "EXACT_AND_CLOSED",
        "role": side,
        "language": language,
        "directives": inventory.get("directives"),
    }
    if prelude != expected_prelude:
        failures.append(f"module {side} verified language prelude is detached")
    expected_directives = {
        ("cpp", "source"): [("include", "<cstdint>")],
        ("cpp", "target"): [
            ("include", "<cstdint>"),
            ("include", "<stdexcept>"),
            ("include", "<string>"),
        ],
        ("objc", "source"): [("import", "<Foundation/Foundation.h>")],
        ("objc", "target"): [("import", "<Foundation/Foundation.h>")],
    }.get((language, side), [])
    directives = inventory.get("directives")
    observed_directives = (
        [(item.get("kind"), item.get("value")) for item in directives]
        if isinstance(directives, list)
        and all(isinstance(item, dict) for item in directives)
        else None
    )
    if observed_directives != expected_directives:
        failures.append(f"module {side} language prelude is not exact")

    wrapper = closure.get("verified_language_wrapper", {}).get(side)
    file_name = artifact_record[1].name if artifact_record is not None else None
    if language != "java":
        if wrapper != {
            "status": "NOT_APPLICABLE",
            "role": side,
            "language": language,
            "file": file_name,
        }:
            failures.append(f"module {side} language wrapper must be NOT_APPLICABLE")
        return
    if not isinstance(wrapper, dict) or set(wrapper) != {
        "status",
        "role",
        "language",
        "file",
        "name",
        "qualified_name",
        "declaration_kind",
        "analyzable",
        "occurrence",
        "source_span",
        "signature",
        "member_span_status",
        "member_subjects",
    }:
        failures.append(f"module {side} Java wrapper keys are invalid")
        return
    expected_name = Path(str(file_name)).stem
    expected_signature = {
        "type_kind": "CLASS",
        "visibility": "public",
        "storage": "top-level",
        "modifiers": ["final", "public"],
        "final": True,
        "abstract": False,
        "extends": "",
        "implements": [],
        "type_parameters": [],
        "annotations": [],
        "permits": [],
    }
    if (
        wrapper.get("status") != "EXACT_AND_CLOSED"
        or wrapper.get("role") != side
        or wrapper.get("language") != "java"
        or wrapper.get("file") != file_name
        or wrapper.get("name") != expected_name
        or wrapper.get("qualified_name") != expected_name
        or wrapper.get("declaration_kind") != "top-level-class-wrapper"
        or wrapper.get("analyzable") is not False
        or wrapper.get("occurrence") != 1
        or wrapper.get("signature") != expected_signature
        or wrapper.get("member_span_status") != "ALL_CONTAINED"
    ):
        failures.append(f"module {side} Java wrapper identity/signature drift")
    subjects = inventory.get("subjects")
    wrapper_subjects = [
        item
        for item in (subjects if isinstance(subjects, list) else [])
        if isinstance(item, dict)
        and item.get("declaration_kind") == "top-level-class-wrapper"
    ]
    if len(wrapper_subjects) != 1:
        failures.append(f"module {side} Java wrapper count is not exactly one")
        return
    wrapper_subject = wrapper_subjects[0]
    for field in (
        "name",
        "qualified_name",
        "declaration_kind",
        "analyzable",
        "occurrence",
        "source_span",
        "signature",
    ):
        if wrapper.get(field) != wrapper_subject.get(field):
            failures.append(
                f"module {side} Java wrapper {field} differs from inventory"
            )
    wrapper_span = wrapper.get("source_span")
    if not isinstance(wrapper_span, dict):
        failures.append(f"module {side} Java wrapper span is invalid")
        return
    wrapper_start = wrapper_span.get("start_byte")
    wrapper_end = wrapper_span.get("end_byte")
    if not isinstance(wrapper_start, int) or not isinstance(wrapper_end, int):
        failures.append(f"module {side} Java wrapper span is invalid")
        return
    member_kinds = {
        "constructor",
        "field",
        "instance-initializer",
        "method",
        "nested-type",
        "static-initializer",
    }
    expected_members: list[dict[str, Any]] = []
    for subject in subjects if isinstance(subjects, list) else []:
        if (
            not isinstance(subject, dict)
            or subject is wrapper_subject
            or subject.get("declaration_kind") not in member_kinds
        ):
            continue
        span = subject.get("source_span")
        if not isinstance(span, dict):
            failures.append(f"module {side} Java member span is invalid")
            continue
        start = span.get("start_byte")
        end = span.get("end_byte")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or not (wrapper_start <= start and end <= wrapper_end)
        ):
            failures.append(f"module {side} Java member escapes wrapper span")
        expected_members.append(
            {
                "name": subject.get("name"),
                "qualified_name": subject.get("qualified_name"),
                "declaration_kind": subject.get("declaration_kind"),
                "occurrence": subject.get("occurrence"),
                "source_span": span,
            }
        )
    expected_members.sort(
        key=lambda item: (
            int(item["source_span"]["start_byte"]),
            str(item["qualified_name"]),
        )
    )
    if wrapper.get("member_subjects") != expected_members:
        failures.append(f"module {side} Java wrapper members differ from inventory")


def _validate_module_profile_span_bindings(
    *,
    side: str,
    closure: dict[str, Any],
    semantic_document: dict[str, Any],
    failures: list[str],
) -> None:
    records = closure.get(f"{side}_profile_symbols")
    functions = semantic_document.get("functions")
    if not isinstance(records, list) or not isinstance(functions, list):
        failures.append(f"module {side} profile span binding inputs are invalid")
        return
    by_symbol = {
        item.get("name"): item
        for item in functions
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if len(by_symbol) != len(functions):
        failures.append(f"module {side} semantic symbol index is invalid")
    observed_symbols: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            failures.append(f"module {side} profile_symbols[{index}] is invalid")
            continue
        symbol = record.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            failures.append(f"module {side} profile_symbols[{index}].symbol is invalid")
            continue
        observed_symbols.append(symbol)
        function = by_symbol.get(symbol)
        if function is None:
            failures.append(f"module {side} inventory symbol {symbol} is absent from IR")
            continue
        if record.get("source_span") != function.get("source_span"):
            failures.append(
                f"module {side} inventory span for {symbol} differs from semantic IR"
            )
        canonical_signature = {
            "parameters": [
                {"name": parameter.get("name"), "type": parameter.get("type")}
                for parameter in function.get("parameters", [])
                if isinstance(parameter, dict)
            ],
            "return_type": function.get("return_type"),
        }
        if record.get("canonical_signature") != canonical_signature:
            failures.append(
                f"module {side} inventory signature for {symbol} differs from semantic IR"
            )
    if len(observed_symbols) != len(set(observed_symbols)):
        failures.append(f"module {side} profile inventory contains duplicate symbols")


def _validate_module_whole_file_closure(
    *,
    manifest: dict[str, Any],
    module_manifest: dict[str, Any],
    module_input: dict[str, Any],
    source_semantic_document: dict[str, Any],
    target_semantic_document: dict[str, Any],
    source_inventory_document: dict[str, Any],
    target_inventory_document: dict[str, Any],
    closure_document: dict[str, Any],
    source_validation_document: dict[str, Any],
    target_validation_document: dict[str, Any],
    source_observation_document: dict[str, Any],
    target_observation_document: dict[str, Any],
    source_artifact_record: tuple[dict[str, Any], Path, str] | None,
    target_artifact_record: tuple[dict[str, Any], Path, str] | None,
    source_inventory_record: tuple[dict[str, Any], Path, str] | None,
    target_inventory_record: tuple[dict[str, Any], Path, str] | None,
    closure_record: tuple[dict[str, Any], Path, str] | None,
    route_swift_receipt: dict[str, Any] | None,
    replay_native_behavior: bool,
    failures: list[str],
) -> None:
    source_language = manifest.get("source", {}).get("language")
    target_language = manifest.get("target", {}).get("language")
    _validate_module_inventory_document(
        document=source_inventory_document,
        label="source-module-inventory",
        language=source_language,
        artifact_record=source_artifact_record,
        route_swift_receipt=route_swift_receipt,
        failures=failures,
    )
    _validate_module_inventory_document(
        document=target_inventory_document,
        label="target-module-inventory",
        language=target_language,
        artifact_record=target_artifact_record,
        route_swift_receipt=route_swift_receipt,
        failures=failures,
    )
    if set(closure_document) != WHOLE_FILE_CLOSURE_KEYS:
        failures.append("whole-file-module-closure top-level keys are not exact")
    if (
        closure_document.get("schema_version") != "1.0.0"
        or closure_document.get("kind")
        != "elmos.typed-pure-module-whole-file-closure"
        or closure_document.get("profile") != "typed-pure-module-v1"
        or closure_document.get("status") != "PASSED"
        or closure_document.get("route")
        != {
            "source_language": source_language,
            "target_language": target_language,
        }
    ):
        failures.append("whole-file-module-closure identity/status is invalid")
    for side, inventory_record in (
        ("source", source_inventory_record),
        ("target", target_inventory_record),
    ):
        if inventory_record is None:
            continue
        if closure_document.get(f"{side}_inventory_sha256") != inventory_record[2]:
            failures.append(
                f"whole-file-module-closure {side} inventory digest backlink mismatch"
            )
        if closure_document.get(f"{side}_inventory_bytes") != inventory_record[
            1
        ].stat().st_size:
            failures.append(
                f"whole-file-module-closure {side} inventory byte backlink mismatch"
            )
    if closure_record is not None and module_input.get(
        "whole_file_closure_sha256"
    ) != closure_record[2]:
        failures.append("module_input whole-file closure digest backlink mismatch")
    if closure_document.get("blocked_declarations") != {"source": [], "target": []}:
        failures.append("whole-file-module-closure contains blocked declarations")
    if closure_document.get("source_user_call_graph") != {
        "edges": [],
        "status": "EMPTY_AND_CLOSED",
    }:
        failures.append("whole-file source user call graph is not empty and closed")
    _validate_module_language_boundary(
        side="source",
        language=source_language,
        inventory=source_inventory_document,
        closure=closure_document,
        artifact_record=source_artifact_record,
        failures=failures,
    )
    _validate_module_language_boundary(
        side="target",
        language=target_language,
        inventory=target_inventory_document,
        closure=closure_document,
        artifact_record=target_artifact_record,
        failures=failures,
    )
    if (
        closure_document.get("target_call_graph_policy")
        != "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS"
    ):
        failures.append("whole-file target call graph policy drift")
    entries = module_manifest.get("functions")
    manifest_symbols = sorted(
        entry.get("symbol")
        for entry in (entries if isinstance(entries, list) else [])
        if isinstance(entry, dict) and isinstance(entry.get("symbol"), str)
    )
    if closure_document.get("manifest_symbols") != manifest_symbols:
        failures.append("whole-file closure manifest symbol set mismatch")
    target_call_graph = closure_document.get("target_call_graph")
    if not isinstance(target_call_graph, dict) or set(target_call_graph) != {
        "status",
        "scope",
        "edges",
        "helper_internal_calls",
    }:
        failures.append("whole-file target call graph is invalid")
    else:
        if (
            target_call_graph.get("status")
            != "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
            or target_call_graph.get("scope")
            != "profile-functions-to-emitted-callees"
            or target_call_graph.get("helper_internal_calls")
            != {
                "status": "CONTENT_BOUND_NOT_EDGE_ENUMERATED",
                "binding": "verified_generated_helpers-exact-bytes-and-digests",
            }
        ):
            failures.append("whole-file target call graph identity drift")
        helper_identifiers = {
            identifier
            for helper in closure_document.get("target_helper_symbols", [])
            if isinstance(helper, dict)
            for identifier in (helper.get("name"), helper.get("qualified_name"))
            if isinstance(identifier, str) and identifier
        }
        normalizations = closure_document.get("target_builtin_normalizations")
        normalization_set = (
            set(normalizations) if isinstance(normalizations, list) else set()
        )
        edges = target_call_graph.get("edges")
        if not isinstance(edges, list):
            failures.append("whole-file target call graph edges are invalid")
        else:
            edge_keys = {
                "caller",
                "callee",
                "callee_kind",
                "canonical_domain",
                "canonical_operator",
                "normalization_rule",
            }
            normalized_edges: list[tuple[str, str, str, str]] = []
            for index, edge in enumerate(edges):
                if not isinstance(edge, dict) or set(edge) != edge_keys:
                    failures.append(
                        f"whole-file target call graph edge {index} keys are invalid"
                    )
                    continue
                caller = edge.get("caller")
                callee = edge.get("callee")
                callee_kind = edge.get("callee_kind")
                domain = edge.get("canonical_domain")
                operator = edge.get("canonical_operator")
                rule = edge.get("normalization_rule")
                if (
                    caller not in manifest_symbols
                    or not isinstance(callee, str)
                    or not callee
                    or domain not in {"integer", "number"}
                    or operator not in {"+", "-", "*", "/", "%"}
                    or rule not in normalization_set
                ):
                    failures.append(
                        f"whole-file target call graph edge {index} is detached"
                    )
                    continue
                if callee_kind == "exact-generated-helper":
                    if callee not in helper_identifiers:
                        failures.append(
                            f"whole-file target helper edge {index} is not inventory-bound"
                        )
                elif callee_kind == "pinned-target-builtin":
                    if callee in helper_identifiers:
                        failures.append(
                            f"whole-file target builtin edge {index} aliases a helper"
                        )
                else:
                    failures.append(
                        f"whole-file target call graph edge {index} callee kind is invalid"
                    )
                normalized_edges.append((caller, callee, str(domain), str(operator)))
            if len(normalized_edges) != len(set(normalized_edges)):
                failures.append("whole-file target call graph contains duplicate edges")
            if normalized_edges != sorted(normalized_edges):
                failures.append("whole-file target call graph edges are not canonical")
    _validate_module_profile_span_bindings(
        side="source",
        closure=closure_document,
        semantic_document=source_semantic_document,
        failures=failures,
    )
    _validate_module_profile_span_bindings(
        side="target",
        closure=closure_document,
        semantic_document=target_semantic_document,
        failures=failures,
    )

    required_values = (
        source_artifact_record,
        target_artifact_record,
        source_inventory_record,
        target_inventory_record,
        closure_record,
    )
    if any(value is None for value in required_values):
        return
    if not all(
        isinstance(value, dict) and value
        for value in (
            module_manifest,
            source_semantic_document,
            target_semantic_document,
            source_inventory_document,
            target_inventory_document,
            closure_document,
        )
    ):
        return
    assert source_artifact_record is not None
    assert target_artifact_record is not None
    snapshot_owner = tempfile.TemporaryDirectory(
        prefix="elmos-module-validator-snapshot-"
    )
    snapshot_root = Path(snapshot_owner.name)
    snapshot_root.chmod(0o700)
    try:
        source_bytes = source_artifact_record[1].read_bytes()
        target_bytes = target_artifact_record[1].read_bytes()
        source_digest = str(source_artifact_record[0].get("sha256"))
        target_digest = str(target_artifact_record[0].get("sha256"))
        if (
            sha256_bytes(source_bytes) != source_digest
            or source_artifact_record[2] != source_digest
            or len(source_bytes) != source_artifact_record[0].get("bytes")
        ):
            raise ValueError("source artifact changed before private snapshot")
        if (
            sha256_bytes(target_bytes) != target_digest
            or target_artifact_record[2] != target_digest
            or len(target_bytes) != target_artifact_record[0].get("bytes")
        ):
            raise ValueError("target artifact changed before private snapshot")
        source_snapshot = _private_snapshot(
            snapshot_root,
            role="source",
            logical_name=source_artifact_record[1].name,
            content=source_bytes,
        )
        target_snapshot = _private_snapshot(
            snapshot_root,
            role="target",
            logical_name=target_artifact_record[1].name,
            content=target_bytes,
        )
    except (OSError, ValueError) as exc:
        failures.append(f"module private artifact snapshot failed: {exc}")
        return
    closure_api = _engine_module_closure_api(
        failures, "module whole-file closure"
    )
    if closure_api is None:
        return
    (
        SemanticIR,
        emit,
        analyze,
        inventory_module,
        combine_function_irs,
        build_whole_file_closure,
        validate_source,
        validate_target,
    ) = closure_api
    try:
        persisted_source_ir = SemanticIR.from_mapping(source_semantic_document)
        persisted_target_ir = SemanticIR.from_mapping(target_semantic_document)
        fresh_source_ir = combine_function_irs(
            [
                analyze(source_snapshot, source_language, symbol)
                for symbol in manifest_symbols
            ],
            manifest_symbols,
            source_language,
            "source-validator-replay",
        )
        fresh_target_ir = combine_function_irs(
            [
                analyze(
                    target_snapshot,
                    target_language,
                    symbol,
                    emitted_target=True,
                )
                for symbol in manifest_symbols
            ],
            manifest_symbols,
            target_language,
            "target-validator-replay",
        )
        fresh_emitted = emit(fresh_source_ir, target_language)
    except Exception as exc:
        failures.append(f"module independent semantic re-lift/emitter replay failed: {exc}")
        return
    if fresh_source_ir.to_mapping() != persisted_source_ir.to_mapping():
        failures.append(
            "source-module-semantic-ir differs from independent source analysis"
        )
    if fresh_target_ir.to_mapping() != persisted_target_ir.to_mapping():
        failures.append(
            "target-module-semantic-ir differs from independent target re-lift"
        )
    if fresh_emitted.relative_path != module_input.get("target_logical_file"):
        failures.append("module deterministic emitter target path differs")
    if fresh_emitted.content.encode("utf-8") != target_bytes:
        failures.append("module deterministic emitter target bytes differ")
    if list(fresh_emitted.normalization_rules) != closure_document.get(
        "target_builtin_normalizations"
    ):
        failures.append("module deterministic emitter normalizations differ")
    try:
        fresh_source_inventory = inventory_module(
            source_snapshot, source_language
        )
        fresh_target_inventory = inventory_module(
            target_snapshot, target_language
        )
    except Exception as exc:
        failures.append(f"module independent whole-file inventory failed: {exc}")
        return
    if _module_inventory_stable_projection(
        fresh_source_inventory
    ) != _module_inventory_stable_projection(source_inventory_document):
        failures.append(
            "source-module-inventory differs from independent compiler enumeration"
        )
    if _module_inventory_stable_projection(
        fresh_target_inventory
    ) != _module_inventory_stable_projection(target_inventory_document):
        failures.append(
            "target-module-inventory differs from independent compiler enumeration"
        )
    try:
        fresh_closure = build_whole_file_closure(
            source_inventory=fresh_source_inventory,
            target_inventory=fresh_target_inventory,
            source_ir=fresh_source_ir,
            target_ir=fresh_target_ir,
            manifest=module_manifest,
            source_bytes=source_bytes,
            emitted=fresh_emitted,
        )
    except Exception as exc:
        failures.append(f"module independent whole-file closure rejected: {exc}")
        return
    if _whole_file_closure_stable_projection(
        fresh_closure,
        source_inventory=fresh_source_inventory,
        target_inventory=fresh_target_inventory,
    ) != _whole_file_closure_stable_projection(
        closure_document,
        source_inventory=source_inventory_document,
        target_inventory=target_inventory_document,
    ):
        failures.append(
            "whole-file-module-closure differs from independent reconstruction"
        )
    if not replay_native_behavior:
        _validate_snapshot_stability(
            label="module source",
            origin=source_artifact_record[1],
            snapshot=source_snapshot,
            expected_bytes=source_bytes,
            expected_digest=source_digest,
            failures=failures,
        )
        _validate_snapshot_stability(
            label="module target",
            origin=target_artifact_record[1],
            snapshot=target_snapshot,
            expected_bytes=target_bytes,
            expected_digest=target_digest,
            failures=failures,
        )
        return
    cases_by_symbol = {
        entry.get("symbol"): entry.get("cases")
        for entry in (
            module_manifest.get("functions")
            if isinstance(module_manifest.get("functions"), list)
            else []
        )
        if isinstance(entry, dict)
        and isinstance(entry.get("symbol"), str)
        and isinstance(entry.get("cases"), list)
    }
    source_functions = {
        function.name: function for function in fresh_source_ir.functions
    }
    fresh_source_validation: dict[str, Any] = {}
    fresh_target_validation: dict[str, Any] = {}
    try:
        with tempfile.TemporaryDirectory(
            prefix="elmos-module-native-validator-replay-"
        ) as temporary:
            replay_root = Path(temporary)
            for index, symbol in enumerate(manifest_symbols):
                function = source_functions[symbol]
                cases = cases_by_symbol[symbol]
                fresh_source_validation[symbol] = validate_source(
                    source_snapshot,
                    source_language,
                    function,
                    cases,
                    replay_root / "source" / f"{index:03d}",
                )
                fresh_target_validation[symbol] = validate_target(
                    fresh_emitted,
                    target_language,
                    function,
                    cases,
                    replay_root / "target" / f"{index:03d}",
                )
    except Exception as exc:
        failures.append(f"module independent native behavior replay failed: {exc}")
        return
    if fresh_source_validation != source_validation_document:
        failures.append(
            "source-module-validation differs from independent native replay"
        )
    if fresh_target_validation != target_validation_document:
        failures.append(
            "target-module-validation differs from independent native replay"
        )
    fresh_source_observations = {
        symbol: validation.get("observations")
        for symbol, validation in fresh_source_validation.items()
    }
    fresh_target_observations = {
        symbol: validation.get("observations")
        for symbol, validation in fresh_target_validation.items()
    }
    if fresh_source_observations != source_observation_document:
        failures.append(
            "source-module-observations differ from independent native replay"
        )
    if fresh_target_observations != target_observation_document:
        failures.append(
            "target-module-observations differ from independent native replay"
        )
    _validate_snapshot_stability(
        label="module source",
        origin=source_artifact_record[1],
        snapshot=source_snapshot,
        expected_bytes=source_bytes,
        expected_digest=source_digest,
        failures=failures,
    )
    _validate_snapshot_stability(
        label="module target",
        origin=target_artifact_record[1],
        snapshot=target_snapshot,
        expected_bytes=target_bytes,
        expected_digest=target_digest,
        failures=failures,
    )


def _validate_module_equivalence(
    route: Path,
    manifest: dict[str, Any],
    certification: dict[str, Any],
    *,
    replay_native_behavior: bool,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate module composition evidence without turning NOT_RUN into pass.

    Native source/target behavior replay is mandatory by default.  The frozen
    Batch 35 packed-evidence launcher explicitly disables only that step and
    reports ``native_route_reexecution=NOT_RUN``; semantic re-lift, emission,
    inventory, closure, proof re-encoding, and solver replay remain mandatory.
    """

    failures: list[str] = []
    gates = manifest.get("gates", {})
    required = gates.get("module_equivalence_required") is True
    minimum_functions = gates.get("minimum_module_functions", 3)
    if not _is_int(minimum_functions, minimum=3):
        failures.append("minimum_module_functions must be an integer >= 3")
        minimum_functions = 3
    reference = certification.get("module_equivalence")
    if reference is None:
        if required:
            failures.append("required module_equivalence evidence is missing")
        return None, failures
    resolved = validate_artifact_ref(
        route,
        reference,
        "module_equivalence",
        failures,
        require_identity=False,
    )
    if resolved is None:
        return None, failures
    evidence_path, _ = resolved
    try:
        evidence = load(evidence_path)
    except Exception as exc:
        failures.append(f"module equivalence evidence is invalid JSON: {exc}")
        return None, failures
    _validate_optional_json_schema(
        evidence,
        "module-equivalence-evidence.schema.json",
        failures,
        "module equivalence evidence",
    )
    route_scope = evidence.get("route")
    expected_route_scope = {
        "route_key": manifest.get("route_key"),
        "source_language": manifest.get("source", {}).get("language"),
        "target_language": manifest.get("target", {}).get("language"),
    }
    if route_scope != expected_route_scope:
        failures.append("module equivalence route tuple does not match route.json")
    if evidence.get("profile") != manifest.get("profiles", {}).get("module_profile"):
        failures.append("module equivalence profile does not match route.json")
    if evidence.get("certification_status") != "NOT_CERTIFIED":
        failures.append("module equivalence must remain NOT_CERTIFIED")
    if evidence.get("external_verification_status") != "NOT_RUN":
        failures.append("module equivalence external verification must remain NOT_RUN")

    artifact_refs = evidence.get("artifact_refs")
    artifacts_by_path: dict[str, tuple[dict[str, Any], Path, str]] = {}
    if not isinstance(artifact_refs, list):
        failures.append("module artifact_refs must be an array")
        artifact_refs = []
    for index, item in enumerate(artifact_refs):
        if not isinstance(item, dict):
            failures.append(f"module artifact_refs[{index}] must be an object")
            continue
        relative = item.get("path")
        role = item.get("role")
        digest = _require_digest(
            failures, item.get("sha256"), f"module artifact_refs[{index}].sha256"
        )
        size = item.get("bytes")
        path = _resolve_below(
            route, relative, f"module artifact_refs[{index}].path", failures
        )
        if path is None:
            continue
        if not path.is_file() or path.is_symlink():
            failures.append(f"module artifact_refs[{index}] is not a regular file")
            continue
        if not _is_int(size, minimum=1) or path.stat().st_size != size:
            failures.append(f"module artifact_refs[{index}] byte count mismatch")
        observed = sha256_file(path)
        if digest is not None and observed != digest:
            failures.append(f"module artifact_refs[{index}] digest mismatch")
        if not isinstance(relative, str):
            continue
        if relative in artifacts_by_path:
            failures.append(f"duplicate module artifact path: {relative}")
        else:
            artifacts_by_path[relative] = (item, path, observed)
        if role not in MODULE_ARTIFACT_ROLES:
            failures.append(f"module artifact_refs[{index}] role is invalid")

    module_input_digest = None
    if evidence.get("status") == "PASSED":
        module_input_digest = _require_digest(
            failures, evidence.get("module_input_sha256"), "module_input_sha256"
        )
    module_inputs = [
        item for item in artifacts_by_path.values() if item[0].get("role") == "module-formal-input"
    ]
    role_records: dict[str, list[tuple[dict[str, Any], Path, str]]] = {}
    for record in artifacts_by_path.values():
        role_records.setdefault(str(record[0].get("role")), []).append(record)
    if evidence.get("status") == "PASSED":
        route_swift_receipt = _validate_swift_receipt_binding(
            source_language=manifest.get("source", {}).get("language"),
            target_language=manifest.get("target", {}).get("language"),
            records=role_records.get("swift-analyzer-build-receipt", []),
            label="module Swift analyzer build receipt",
            failures=failures,
        )
    else:
        route_swift_receipt = None
        if role_records.get("swift-analyzer-build-receipt"):
            failures.append("non-passing module evidence cannot bind a Swift analyzer receipt")
    module_cases: dict[str, Any] = {}
    source_validation_document: dict[str, Any] = {}
    target_validation_document: dict[str, Any] = {}
    source_observation_document: dict[str, Any] = {}
    target_observation_document: dict[str, Any] = {}
    source_semantic_document: dict[str, Any] = {}
    target_semantic_document: dict[str, Any] = {}
    source_inventory_document: dict[str, Any] = {}
    target_inventory_document: dict[str, Any] = {}
    whole_file_closure_document: dict[str, Any] = {}
    if evidence.get("status") == "PASSED":
        if len(module_inputs) != 1:
            failures.append("passed module evidence must bind exactly one module formal input")
        elif module_input_digest is not None and module_inputs[0][2] != module_input_digest:
            failures.append("module_input_sha256 does not bind module-formal-input")
        module_input = evidence.get("module_input")
        if not isinstance(module_input, dict):
            failures.append("passed module evidence must include module_input")
        else:
            if canonical_json_sha256(module_input) != module_input_digest:
                failures.append("module_input_sha256 is not the canonical module_input digest")
            if module_inputs:
                try:
                    persisted_module_input = load(module_inputs[0][1])
                except Exception as exc:
                    failures.append(f"module-formal-input is invalid JSON: {exc}")
                else:
                    if persisted_module_input != module_input:
                        failures.append("module-formal-input differs from module_input")

            single_roles = MODULE_ARTIFACT_ROLES - {
                "formal-function-input",
                "formal-function-smt2",
                "formal-function-result",
                "swift-analyzer-build-receipt",
            }
            for role in sorted(single_roles):
                if len(role_records.get(role, [])) != 1:
                    failures.append(f"passed module evidence must bind exactly one {role}")
            input_bindings = (
                ("original-source-module-artifact", "source_artifact_sha256"),
                ("emitted-target-module-artifact", "target_artifact_sha256"),
                ("module-case-manifest", "corpus_sha256"),
                ("source-module-inventory", "source_inventory_sha256"),
                ("target-module-inventory", "target_inventory_sha256"),
                ("whole-file-module-closure", "whole_file_closure_sha256"),
            )
            for role, field in input_bindings:
                records = role_records.get(role, [])
                if len(records) == 1 and module_input.get(field) != records[0][2]:
                    failures.append(f"module_input.{field} does not bind {role}")
            if module_input.get("route") != {
                "source_language": manifest.get("source", {}).get("language"),
                "target_language": manifest.get("target", {}).get("language"),
            }:
                failures.append("module_input route tuple does not match route.json")
            if module_input.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                failures.append("module_input input domain drift")
            source_records = role_records.get("original-source-module-artifact", [])
            if len(source_records) == 1 and module_input.get(
                "source_logical_file"
            ) != source_records[0][1].name:
                failures.append("module_input source_logical_file drift")
            target_records = role_records.get("emitted-target-module-artifact", [])
            if len(target_records) == 1 and module_input.get(
                "target_logical_file"
            ) != target_records[0][1].name:
                failures.append("module_input target_logical_file drift")
            count_bindings = (
                ("original-source-module-artifact", "source_artifact_byte_count"),
                ("emitted-target-module-artifact", "target_artifact_byte_count"),
                ("source-module-inventory", "source_inventory_byte_count"),
                ("target-module-inventory", "target_inventory_byte_count"),
            )
            for role, field in count_bindings:
                records = role_records.get(role, [])
                if len(records) == 1 and module_input.get(field) != records[0][1].stat().st_size:
                    failures.append(f"module_input.{field} does not bind {role}")
            semantic_bindings = (
                ("source-module-semantic-ir", "source_semantic_ir_sha256"),
                ("target-module-semantic-ir", "target_semantic_ir_sha256"),
            )
            for role, field in semantic_bindings:
                records = role_records.get(role, [])
                if len(records) != 1:
                    continue
                try:
                    semantic_document = load(records[0][1])
                except Exception as exc:
                    failures.append(f"{role} is invalid JSON: {exc}")
                else:
                    if canonical_json_sha256(semantic_document) != module_input.get(field):
                        failures.append(f"module_input.{field} does not bind {role}")
                    side = "source" if role.startswith("source-") else "target"
                    expected_language = manifest.get(side, {}).get("language")
                    expected_logical_file = module_input.get(
                        f"{side}_logical_file"
                    )
                    if set(semantic_document) != {
                        "schema_version",
                        "source_language",
                        "source_file",
                        "analyzer",
                        "analyzer_version",
                        "functions",
                        "diagnostics",
                    }:
                        failures.append(f"{role} top-level keys are not exact")
                    if semantic_document.get("schema_version") != "1.0.0":
                        failures.append(f"{role} schema_version drift")
                    if semantic_document.get("source_language") != expected_language:
                        failures.append(f"{role} language does not bind route tuple")
                    if semantic_document.get("source_file") != expected_logical_file:
                        failures.append(f"{role} source_file does not bind module artifact")
                    if semantic_document.get("diagnostics") != []:
                        failures.append(f"{role} diagnostics must be empty")
                    for identity_field in ("analyzer", "analyzer_version"):
                        if not isinstance(
                            semantic_document.get(identity_field), str
                        ) or not semantic_document.get(identity_field):
                            failures.append(f"{role} {identity_field} is missing")
                    if expected_language == "swift":
                        _validate_swift_analyzer_version_binding(
                            semantic_document=semantic_document,
                            receipt=route_swift_receipt,
                            label=role,
                            failures=failures,
                        )
                    try:
                        from elmos_polyglot_route.models import (  # type: ignore[import-not-found]
                            SemanticIR,
                        )

                        round_trip = SemanticIR.from_mapping(
                            semantic_document
                        ).to_mapping()
                    except Exception as exc:
                        failures.append(f"{role} typed reconstruction failed: {exc}")
                    else:
                        if round_trip != semantic_document:
                            failures.append(f"{role} typed reconstruction drift")
                    if role == "source-module-semantic-ir":
                        source_semantic_document = semantic_document
                    else:
                        target_semantic_document = semantic_document
            for role, destination_name in (
                ("source-module-inventory", "source"),
                ("target-module-inventory", "target"),
                ("whole-file-module-closure", "closure"),
            ):
                records = role_records.get(role, [])
                if len(records) != 1:
                    continue
                try:
                    document = load(records[0][1])
                except Exception as exc:
                    failures.append(f"{role} is invalid JSON: {exc}")
                    continue
                if destination_name == "source":
                    source_inventory_document = document
                elif destination_name == "target":
                    target_inventory_document = document
                else:
                    whole_file_closure_document = document
                    if evidence.get("whole_file_closure") != document:
                        failures.append(
                            "module report whole_file_closure differs from bound artifact"
                        )
            case_records = role_records.get("module-case-manifest", [])
            if len(case_records) == 1:
                try:
                    case_manifest = load(case_records[0][1])
                except Exception as exc:
                    failures.append(f"module-case-manifest is invalid JSON: {exc}")
                else:
                    if canonical_json_sha256(case_manifest) != module_input.get(
                        "case_manifest_sha256"
                    ):
                        failures.append(
                            "module_input.case_manifest_sha256 does not bind module-case-manifest"
                        )
                    try:
                        _validate_optional_json_schema(
                            case_manifest,
                            "module-case-manifest.schema.json",
                            failures,
                            "module case manifest",
                        )
                    except Exception as exc:
                        failures.append(f"module case manifest schema validation crashed: {exc}")

            for role, report_field, destination_name in (
                ("source-module-validation", "source_validation", "source_validation"),
                ("target-module-validation", "target_validation", "target_validation"),
                ("source-module-observations", None, "source_observations"),
                ("target-module-observations", None, "target_observations"),
            ):
                records = role_records.get(role, [])
                if len(records) != 1:
                    continue
                try:
                    document = load(records[0][1])
                except Exception as exc:
                    failures.append(f"{role} is invalid JSON: {exc}")
                    continue
                if report_field is not None and evidence.get(report_field) != document:
                    failures.append(f"module report {report_field} differs from {role}")
                if destination_name == "source_validation":
                    source_validation_document = document
                elif destination_name == "target_validation":
                    target_validation_document = document
                elif destination_name == "source_observations":
                    source_observation_document = document
                else:
                    target_observation_document = document
            case_records = role_records.get("module-case-manifest", [])
            if len(case_records) == 1:
                try:
                    module_cases = load(case_records[0][1])
                except Exception:
                    pass

    contract = evidence.get("module_contract")
    if not isinstance(contract, dict):
        failures.append("module_contract must be an object")
        contract = {}
    symbol_sets: dict[str, list[str]] = {}
    for field in (
        "source_profile_symbols",
        "target_profile_symbols",
        "manifest_symbols",
    ):
        values = contract.get(field)
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item for item in values
        ):
            failures.append(f"module_contract.{field} must contain non-empty symbols")
            values = []
        if len(values) != len(set(values)):
            failures.append(f"module_contract.{field} contains duplicate symbols")
        symbol_sets[field] = values

    functions = evidence.get("functions")
    if not isinstance(functions, list):
        failures.append("module functions must be an array")
        functions = []
    module_entries = module_cases.get("functions")
    manifest_by_symbol = {
        item.get("symbol"): item
        for item in (module_entries if isinstance(module_entries, list) else [])
        if isinstance(item, dict)
        and isinstance(item.get("symbol"), str)
    }
    source_artifact_record = next(
        iter(role_records.get("original-source-module-artifact", [])), None
    )
    target_artifact_record = next(
        iter(role_records.get("emitted-target-module-artifact", [])), None
    )
    source_inventory_record = next(
        iter(role_records.get("source-module-inventory", [])), None
    )
    target_inventory_record = next(
        iter(role_records.get("target-module-inventory", [])), None
    )
    closure_record = next(
        iter(role_records.get("whole-file-module-closure", [])), None
    )
    if evidence.get("status") == "PASSED":
        _validate_module_whole_file_closure(
            manifest=manifest,
            module_manifest=module_cases,
            module_input=(
                evidence.get("module_input")
                if isinstance(evidence.get("module_input"), dict)
                else {}
            ),
            source_semantic_document=source_semantic_document,
            target_semantic_document=target_semantic_document,
            source_inventory_document=source_inventory_document,
            target_inventory_document=target_inventory_document,
            closure_document=whole_file_closure_document,
            source_validation_document=source_validation_document,
            target_validation_document=target_validation_document,
            source_observation_document=source_observation_document,
            target_observation_document=target_observation_document,
            source_artifact_record=source_artifact_record,
            target_artifact_record=target_artifact_record,
            source_inventory_record=source_inventory_record,
            target_inventory_record=target_inventory_record,
            closure_record=closure_record,
            route_swift_receipt=route_swift_receipt,
            replay_native_behavior=replay_native_behavior,
            failures=failures,
        )
    semantic_functions: dict[str, dict[str, dict[str, Any]]] = {}
    for side, document in (
        ("source", source_semantic_document),
        ("target", target_semantic_document),
    ):
        raw_functions = document.get("functions")
        index_by_symbol: dict[str, dict[str, Any]] = {}
        if not isinstance(raw_functions, list) or not raw_functions:
            failures.append(f"{side} module semantic IR functions are missing")
        else:
            for function_index, raw_function in enumerate(raw_functions):
                if not isinstance(raw_function, dict):
                    failures.append(
                        f"{side} module semantic IR function {function_index} is invalid"
                    )
                    continue
                name = raw_function.get("name")
                if not isinstance(name, str) or not name or name in index_by_symbol:
                    failures.append(
                        f"{side} module semantic IR symbol set is invalid/duplicate"
                    )
                    continue
                index_by_symbol[name] = raw_function
        semantic_functions[side] = index_by_symbol
    if evidence.get("status") == "PASSED":
        domain_api = _engine_domain_api(failures, "module equivalence")
        if domain_api is not None:
            SemanticIR, enforce_semantic_domain, enforce_case_domain = domain_api
            source_language = manifest.get("source", {}).get("language")
            target_language = manifest.get("target", {}).get("language")
            try:
                source_typed_ir = SemanticIR.from_mapping(source_semantic_document)
                target_typed_ir = SemanticIR.from_mapping(target_semantic_document)
                enforce_semantic_domain(
                    source_typed_ir, source_language, target_language
                )
                enforce_semantic_domain(
                    target_typed_ir, source_language, target_language
                )
                typed_source_by_symbol = {
                    function.name: function for function in source_typed_ir.functions
                }
                entries = module_cases.get("functions")
                if not isinstance(entries, list):
                    raise ValueError("module case functions are missing")
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise ValueError("module case function entry is invalid")
                    symbol = entry.get("symbol")
                    cases = entry.get("cases")
                    if symbol not in typed_source_by_symbol or not isinstance(cases, list):
                        raise ValueError(f"module cases are detached for {symbol}")
                    enforce_case_domain(
                        typed_source_by_symbol[symbol],
                        cases,
                        source_language,
                        target_language,
                    )
            except Exception as exc:
                failures.append(
                    f"module equivalence specialized semantic/case domain rejected: {exc}"
                )
    function_symbols: list[str] = []
    for index, function in enumerate(functions):
        if not isinstance(function, dict):
            failures.append(f"module functions[{index}] must be an object")
            continue
        symbol = function.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            failures.append(f"module functions[{index}].symbol is invalid")
            continue
        function_symbols.append(symbol)
        layers = function.get("layers")
        if not isinstance(layers, dict) or set(layers) != MODULE_FUNCTION_LAYER_KEYS:
            failures.append(f"module function {symbol} layers are incomplete")
            continue
        if evidence.get("status") == "PASSED":
            if function.get("status") != "PASSED":
                failures.append(f"module function {symbol} did not pass")
            for layer_name in ("semantic", "chunk", "behavior"):
                layer = layers.get(layer_name)
                if not isinstance(layer, dict) or layer.get("status") != "PASSED":
                    failures.append(f"module function {symbol} {layer_name} did not pass")
            entry = manifest_by_symbol.get(symbol)
            cases = entry.get("cases") if isinstance(entry, dict) else None
            source_function = semantic_functions.get("source", {}).get(symbol)
            target_function = semantic_functions.get("target", {}).get(symbol)
            if source_function is None or target_function is None:
                failures.append(f"module function {symbol} is absent from bound semantic IR")
                continue
            expected_signature = (
                entry.get("signature") if isinstance(entry, dict) else None
            )
            if function.get("signature") != expected_signature:
                failures.append(f"module function {symbol} signature differs from manifest")
            semantic_signature = {
                "parameters": [
                    {"name": item.get("name"), "type": item.get("type")}
                    for item in source_function.get("parameters", [])
                    if isinstance(item, dict)
                ],
                "return_type": source_function.get("return_type"),
            }
            if expected_signature != semantic_signature:
                failures.append(f"module function {symbol} signature differs from semantic IR")
            if isinstance(cases, list) and function.get(
                "case_manifest_sha256"
            ) != canonical_json_sha256(cases):
                failures.append(f"module function {symbol} case manifest digest drift")
            _validate_concrete_chunk_document(
                layers.get("chunk"),
                label=f"module function {symbol} chunk",
                failures=failures,
                source_record=source_artifact_record,
                target_record=target_artifact_record,
                source_function=source_function,
                target_function=target_function,
            )
            _validate_module_behavior_layer(
                symbol=symbol,
                source_function=source_function,
                layer=layers.get("behavior"),
                cases=cases,
                source_validation=source_validation_document.get(symbol),
                target_validation=target_validation_document.get(symbol),
                source_observations=source_observation_document.get(symbol),
                target_observations=target_observation_document.get(symbol),
                failures=failures,
            )
            formal = layers.get("formal")
            if not isinstance(formal, dict):
                failures.append(f"module function {symbol} formal layer is invalid")
            else:
                if formal.get("status") not in MODULE_PASSING_PROOF_STATUSES:
                    failures.append(f"module function {symbol} proof is non-passing")
                if formal.get("property_status") != "PROVED":
                    failures.append(f"module function {symbol} formal property is not proved")
                if formal.get("proof_strength") != "THEOREM_UNDER_ASSUMPTIONS":
                    failures.append(
                        f"module function {symbol} proof strength must be THEOREM_UNDER_ASSUMPTIONS"
                    )
                _validate_module_formal_closure(
                    symbol=symbol,
                    signature=function.get("signature"),
                    source_function=source_function,
                    target_function=target_function,
                    semantic_layer=layers.get("semantic"),
                    case_manifest_sha256=function.get("case_manifest_sha256"),
                    formal=formal,
                    module_input_sha256=module_input_digest,
                    route_scope=expected_route_scope,
                    artifacts_by_path=artifacts_by_path,
                    failures=failures,
                )
    if len(function_symbols) != len(set(function_symbols)):
        failures.append("module functions contain duplicate symbols")

    composition = evidence.get("composition")
    if not isinstance(composition, dict):
        failures.append("module composition must be an object")
        composition = {}
    if evidence.get("status") == "PASSED":
        expected_symbols = set(function_symbols)
        if len(functions) < int(minimum_functions):
            failures.append(
                f"module equivalence requires at least {minimum_functions} functions"
            )
        for field, values in symbol_sets.items():
            if set(values) != expected_symbols:
                failures.append(f"module_contract.{field} does not match function symbols")
        if contract.get("exact_profile_symbol_set") is not True:
            failures.append("module exact_profile_symbol_set is not true")
        if contract.get("exact_generated_helper_symbol_set") is not True:
            failures.append(
                "module exact_generated_helper_symbol_set is not true"
            )
        if contract.get("exact_profile_signature_set") is not True:
            failures.append("module exact_profile_signature_set is not true")
        closure_records = role_records.get("whole-file-module-closure", [])
        if len(closure_records) == 1 and contract.get(
            "whole_file_closure_sha256"
        ) != closure_records[0][2]:
            failures.append(
                "module_contract.whole_file_closure_sha256 does not bind closure artifact"
            )
        if contract.get("target_helper_symbols") != whole_file_closure_document.get(
            "target_helper_symbols"
        ):
            failures.append(
                "module_contract.target_helper_symbols differ from whole-file closure"
            )
        for side in ("source", "target"):
            closure_profile = whole_file_closure_document.get(
                f"{side}_profile_symbols"
            )
            closure_symbols = (
                [
                    item.get("symbol")
                    for item in closure_profile
                    if isinstance(item, dict)
                ]
                if isinstance(closure_profile, list)
                else None
            )
            if contract.get(f"{side}_profile_symbols") != closure_symbols:
                failures.append(
                    f"module_contract.{side}_profile_symbols differ from whole-file closure"
                )
        for field in (
            "verified_language_prelude",
            "verified_language_wrapper",
        ):
            if contract.get(field) != whole_file_closure_document.get(field):
                failures.append(
                    f"module_contract.{field} differs from whole-file closure"
                )
        target_helpers = contract.get("target_helper_symbols")
        if isinstance(target_helpers, list) and any(
            not isinstance(helper, dict) or helper.get("analyzable") is not True
            for helper in target_helpers
        ):
            failures.append("module target helper symbols are not all analyzable")
        independence = contract.get("independence")
        if not isinstance(independence, dict):
            failures.append("module_contract.independence is invalid")
        else:
            if independence.get("target_call_graph") != whole_file_closure_document.get(
                "target_call_graph"
            ):
                failures.append(
                    "module_contract.independence.target_call_graph differs from closure"
                )
            if independence.get(
                "target_generated_helper_symbols"
            ) != whole_file_closure_document.get("target_helper_symbols"):
                failures.append(
                    "module_contract independence helper symbols differ from closure"
                )
            if independence.get(
                "target_builtin_normalizations"
            ) != whole_file_closure_document.get("target_builtin_normalizations"):
                failures.append(
                    "module_contract independence normalizations differ from closure"
                )
        if composition.get("function_count") != len(functions):
            failures.append("module composition function_count mismatch")
        if composition.get("passed_function_count") != len(functions):
            failures.append("module composition passed_function_count mismatch")
        if composition.get("status") != "PASSED":
            failures.append("module composition did not pass")
        if composition.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
            failures.append("module composition input domain drift")
        if (
            composition.get("out_of_domain_arithmetic_behavior")
            != SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
        ):
            failures.append("module composition out-of-domain boundary drift")
        if composition.get("original_source_bytes_theorem") is not False:
            failures.append("module composition overstates original-source theorem")
        if composition.get("source_compiler_runtime_soundness") != "NOT_RUN":
            failures.append("module source compiler/runtime soundness must remain NOT_RUN")
        if composition.get("target_compiler_runtime_soundness") != "NOT_RUN":
            failures.append("module target compiler/runtime soundness must remain NOT_RUN")
        if composition.get("proof_strength") != "COMPOSED_THEOREMS_UNDER_ASSUMPTIONS":
            failures.append("module composition proof strength is overstated or invalid")
        if composition.get("analyzer_and_emitter_soundness") != "ASSUMPTION":
            failures.append("module analyzer/emitter soundness boundary must remain ASSUMPTION")
        if composition.get("source_user_call_graph") != "EMPTY_AND_CLOSED":
            failures.append("module source user call graph is not empty and closed")
        if (
            composition.get("target_call_graph")
            != "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS"
        ):
            failures.append("module target call graph policy drift")
        if (
            composition.get("target_profile_to_emitted_call_graph_status")
            != "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
        ):
            failures.append("module target profile call graph status drift")
        if (
            composition.get("target_profile_to_emitted_call_graph_scope")
            != "profile-functions-to-emitted-callees"
        ):
            failures.append("module target profile call graph scope drift")
        for role in (
            "formal-function-input",
            "formal-function-smt2",
            "formal-function-result",
        ):
            if len(role_records.get(role, [])) != len(functions):
                failures.append(
                    f"module {role} artifact count must equal function count"
                )
        observed_types: set[str] = set()
        for function in functions:
            if not isinstance(function, dict):
                continue
            signature = function.get("signature")
            if not isinstance(signature, dict):
                continue
            observed_types.add(str(signature.get("return_type")))
            parameters = signature.get("parameters")
            if isinstance(parameters, list):
                observed_types.update(
                    str(parameter.get("type"))
                    for parameter in parameters
                    if isinstance(parameter, dict)
                )
        if observed_types != {"integer", "number", "boolean"}:
            failures.append(
                "module signatures must cover exactly integer, number, and boolean"
            )
        case_records = role_records.get("module-case-manifest", [])
        if len(case_records) == 1:
            try:
                module_cases = load(case_records[0][1])
            except Exception as exc:
                failures.append(f"module-case-manifest is invalid JSON: {exc}")
            else:
                entries = module_cases.get("functions")
                if not isinstance(entries, list):
                    failures.append("module-case-manifest functions are invalid")
                else:
                    if set(manifest_by_symbol) != expected_symbols:
                        failures.append(
                            "module-case-manifest symbols do not match module functions"
                        )
                    for function in functions:
                        if not isinstance(function, dict):
                            continue
                        symbol = function.get("symbol")
                        entry = manifest_by_symbol.get(symbol)
                        if entry is None:
                            continue
                        if function.get("signature") != entry.get("signature"):
                            failures.append(
                                f"module function {symbol} signature differs from manifest"
                            )
                        if function.get("case_manifest_sha256") != canonical_json_sha256(
                            entry.get("cases")
                        ):
                            failures.append(
                                f"module function {symbol} case manifest digest drift"
                            )
    elif evidence.get("status") == "NOT_RUN":
        if functions or artifact_refs:
            failures.append("NOT_RUN module evidence cannot contain executed artifacts")
        limitations = evidence.get("limitations")
        if not isinstance(limitations, list) or not limitations:
            failures.append("NOT_RUN module evidence must explain its limitations")
    return evidence, failures


def validate_module_equivalence(
    route: Path,
    manifest: dict[str, Any],
    certification: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Authoritative Batch29 validation, including same-host native replay."""

    return _validate_module_equivalence(
        route,
        manifest,
        certification,
        replay_native_behavior=True,
    )


def validate_packed_module_equivalence(
    route: Path,
    manifest: dict[str, Any],
    certification: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Frozen packed closure replay that explicitly leaves native execution NOT_RUN."""

    return _validate_module_equivalence(
        route,
        manifest,
        certification,
        replay_native_behavior=False,
    )


def _validate_specialized_native_runtime_replay(
    route: Path,
    manifest: dict[str, Any],
    failures: list[str],
) -> None:
    """Re-execute all three exact-eight function corpora on pinned toolchains."""

    replay_api = _engine_module_closure_api(
        failures, "specialized function native replay"
    )
    domain_api = _engine_domain_api(
        failures, "specialized function native replay domain"
    )
    if replay_api is None or domain_api is None:
        return
    (
        _SemanticIR,
        emit,
        analyze,
        _inventory_module,
        _combine_function_irs,
        _build_whole_file_closure,
        validate_source,
        validate_target,
    ) = replay_api
    _, enforce_semantic_domain, enforce_case_domain = domain_api
    source_language = manifest.get("source", {}).get("language")
    target_language = manifest.get("target", {}).get("language")
    evidence_names = {
        "development": "local-development-evidence.json",
        "holdout": "local-holdout-evidence.json",
        "real-repository": "local-representative-evidence.json",
    }
    with tempfile.TemporaryDirectory(
        prefix="elmos-specialized-native-validator-replay-"
    ) as temporary:
        replay_root = Path(temporary)
        for corpus, evidence_name in evidence_names.items():
            corpus_root = route / "corpus" / corpus
            try:
                corpus_manifest = load(corpus_root / "manifest.json")
                source_name = corpus_manifest["source_file"]
                cases_name = corpus_manifest["cases_file"]
                function_name = corpus_manifest["function_name"]
                if any(
                    not isinstance(value, str) or not value
                    for value in (source_name, cases_name, function_name)
                ):
                    raise ValueError("corpus manifest source/cases/function is invalid")
                source_path = _resolve_below(
                    corpus_root,
                    source_name,
                    f"specialized {corpus} source_file",
                    failures,
                )
                cases_path = _resolve_below(
                    corpus_root,
                    cases_name,
                    f"specialized {corpus} cases_file",
                    failures,
                )
                if source_path is None or cases_path is None:
                    continue
                persisted = load(route / "certification" / evidence_name)
                source_bytes = source_path.read_bytes()
                cases_bytes = cases_path.read_bytes()
                source_digest = sha256_bytes(source_bytes)
                cases_digest = sha256_bytes(cases_bytes)
                persisted_source = persisted.get("source_validation")
                persisted_target = persisted.get("validation")
                persisted_target_artifact = persisted.get("target")
                if (
                    not isinstance(persisted_source, dict)
                    or persisted_source.get("artifact_sha256") != source_digest
                    or not isinstance(persisted_target, dict)
                    or not isinstance(persisted_target_artifact, dict)
                ):
                    raise ValueError("persisted runtime artifact binding is invalid")
                certified_input_root = (
                    route / "certification" / "artifacts" / corpus / "inputs"
                )
                certified_source = certified_input_root / source_path.name
                certified_cases = certified_input_root / "cases.json"
                if (
                    not certified_source.is_file()
                    or certified_source.is_symlink()
                    or certified_source.read_bytes() != source_bytes
                    or not certified_cases.is_file()
                    or certified_cases.is_symlink()
                    or certified_cases.read_bytes() != cases_bytes
                ):
                    raise ValueError("route corpus differs from byte-bound certified inputs")
                snapshot_parent = replay_root / corpus / "snapshot"
                snapshot_parent.mkdir(mode=0o700, parents=True, exist_ok=False)
                source_snapshot = _private_snapshot(
                    snapshot_parent,
                    role="source",
                    logical_name=source_path.name,
                    content=source_bytes,
                )
                cases_snapshot = _private_snapshot(
                    snapshot_parent,
                    role="cases",
                    logical_name=cases_path.name,
                    content=cases_bytes,
                )
                cases = _load_json_array(cases_snapshot)
                source_ir = analyze(
                    source_snapshot, source_language, function_name
                )
                if len(source_ir.functions) != 1:
                    raise ValueError("source analysis must contain exactly one function")
                source_function = source_ir.functions[0]
                enforce_semantic_domain(
                    source_ir, source_language, target_language
                )
                enforce_case_domain(
                    source_function, cases, source_language, target_language
                )
                emitted = emit(source_ir, target_language)
                target_artifact = (
                    route
                    / "certification"
                    / "artifacts"
                    / corpus
                    / emitted.relative_path
                )
                if not target_artifact.is_file() or target_artifact.is_symlink():
                    raise ValueError("persisted target artifact is missing or unsafe")
                target_bytes = target_artifact.read_bytes()
                target_digest = sha256_bytes(target_bytes)
                if (
                    persisted_target_artifact.get("path") != emitted.relative_path
                    or persisted_target_artifact.get("sha256") != target_digest
                ):
                    raise ValueError("persisted target runtime artifact binding is invalid")
                target_snapshot = _private_snapshot(
                    snapshot_parent,
                    role="target",
                    logical_name=target_artifact.name,
                    content=target_bytes,
                )
                fresh_target_bytes = emitted.content.encode("utf-8")
                if target_bytes != fresh_target_bytes:
                    failures.append(
                        f"specialized {corpus} target artifact differs from fresh emitter"
                    )
                fresh_target_snapshot = _private_snapshot(
                    snapshot_parent,
                    role="fresh-target",
                    logical_name=emitted.relative_path,
                    content=fresh_target_bytes,
                )
                target_ir = analyze(
                    fresh_target_snapshot,
                    target_language,
                    function_name,
                    emitted_target=True,
                )
                if len(target_ir.functions) != 1:
                    raise ValueError("target re-lift must contain exactly one function")
                enforce_semantic_domain(
                    target_ir, source_language, target_language
                )

                artifact_root = route / "certification" / "artifacts" / corpus
                semantic_report = persisted.get("semantic_equivalence")
                if not isinstance(semantic_report, dict):
                    raise ValueError("persisted semantic-equivalence binding is missing")
                source_ir_record = _resolve_below(
                    artifact_root,
                    semantic_report.get("source_ir_path"),
                    f"specialized {corpus} source semantic IR",
                    failures,
                )
                target_ir_record = _resolve_below(
                    artifact_root,
                    semantic_report.get("target_ir_path"),
                    f"specialized {corpus} target semantic IR",
                    failures,
                )
                if source_ir_record is None or target_ir_record is None:
                    raise ValueError("persisted semantic IR path is invalid")
                persisted_source_ir = load(source_ir_record)
                persisted_target_ir = load(target_ir_record)
                if (
                    sha256_file(source_ir_record)
                    != semantic_report.get("source_ir_sha256")
                    or sha256_file(target_ir_record)
                    != semantic_report.get("target_ir_sha256")
                ):
                    raise ValueError("persisted semantic IR digest binding is invalid")
                fresh_source_mapping = source_ir.to_mapping()
                fresh_target_mapping = target_ir.to_mapping()
                if persisted_source_ir != fresh_source_mapping:
                    failures.append(
                        f"specialized {corpus} source semantic IR differs from independent source analysis"
                    )
                if persisted_target_ir != fresh_target_mapping:
                    failures.append(
                        f"specialized {corpus} target semantic IR differs from independent emitted-target re-lift"
                    )

                formal_input_path = artifact_root / "formal-input.json"
                formal_input = load(formal_input_path)
                source_binding = formal_input.get("source_normalized_ir")
                target_binding = formal_input.get("target_relift_normalized_ir")
                if not isinstance(source_binding, dict) or not isinstance(
                    target_binding, dict
                ):
                    raise ValueError("formal input normalized bindings are missing")
                if source_binding.get("semantic_ir") != fresh_source_mapping:
                    failures.append(
                        f"specialized {corpus} formal source IR is detached from fresh source analysis"
                    )
                if target_binding.get("semantic_ir") != fresh_target_mapping:
                    failures.append(
                        f"specialized {corpus} formal target IR is detached from fresh target re-lift"
                    )
                if source_binding.get("formal_function") != semantic_value(
                    fresh_source_mapping["functions"][0]
                ):
                    failures.append(
                        f"specialized {corpus} formal source function is detached from fresh source analysis"
                    )
                if target_binding.get("formal_function") != semantic_value(
                    fresh_target_mapping["functions"][0]
                ):
                    failures.append(
                        f"specialized {corpus} formal target function is detached from fresh target re-lift"
                    )
                fresh_source_validation = validate_source(
                    source_snapshot,
                    source_language,
                    source_function,
                    cases,
                    replay_root / corpus / "source",
                )
                fresh_target_validation = validate_target(
                    emitted,
                    target_language,
                    source_function,
                    cases,
                    replay_root / corpus / "target",
                )
            except Exception as exc:
                failures.append(
                    f"specialized {corpus} independent native replay failed: {exc}"
                )
                continue
            if persisted.get("source_validation") != fresh_source_validation:
                failures.append(
                    f"specialized {corpus} source validation differs from native replay"
                )
            if persisted.get("validation") != fresh_target_validation:
                failures.append(
                    f"specialized {corpus} target validation differs from native replay"
                )
            for label, origin, snapshot, expected_bytes, expected_digest in (
                (
                    f"specialized {corpus} route source",
                    source_path,
                    source_snapshot,
                    source_bytes,
                    source_digest,
                ),
                (
                    f"specialized {corpus} certified source",
                    certified_source,
                    source_snapshot,
                    source_bytes,
                    source_digest,
                ),
                (
                    f"specialized {corpus} route cases",
                    cases_path,
                    cases_snapshot,
                    cases_bytes,
                    cases_digest,
                ),
                (
                    f"specialized {corpus} certified cases",
                    certified_cases,
                    cases_snapshot,
                    cases_bytes,
                    cases_digest,
                ),
                (
                    f"specialized {corpus} target",
                    target_artifact,
                    target_snapshot,
                    target_bytes,
                    target_digest,
                ),
                (
                    f"specialized {corpus} fresh emitted target",
                    fresh_target_snapshot,
                    fresh_target_snapshot,
                    fresh_target_bytes,
                    sha256_bytes(fresh_target_bytes),
                ),
            ):
                _validate_snapshot_stability(
                    label=label,
                    origin=origin,
                    snapshot=snapshot,
                    expected_bytes=expected_bytes,
                    expected_digest=expected_digest,
                    failures=failures,
                )


def specialized_negative_expected_reasons(
    route_key: str,
    source_language: str,
    case_id: str,
) -> frozenset[str]:
    """Return the complete, stable RouteError strings allowed for one case."""

    dynamic = {
        "specialized-string-semantics-unsupported": frozenset(
            {f"SPECIALIZED_STRING_SEMANTICS_UNSUPPORTED:{route_key}:same"}
        ),
        "specialized-number-arithmetic-unsupported": frozenset(
            {
                "SPECIALIZED_NUMBER_ARITHMETIC_UNSUPPORTED:"
                f"{route_key}:addNumber"
            }
        ),
        "specialized-non-finite-case-unsupported": frozenset(
            {
                "SPECIALIZED_CASE_NON_FINITE_NUMBER_UNSUPPORTED:"
                f"{route_key}:echoNumber:0"
            }
        ),
        "specialized-overflow-outside-no-error-domain": frozenset(
            {
                "SPECIALIZED_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN:"
                f"{route_key}:calculate:0:IntegerOverflow"
            }
        ),
        "missing-symbol-fails-closed": frozenset(
            {
                "NO_SUPPORTED_FUNCTIONS"
                if source_language in {"java", "swift"}
                else "FUNCTION_NOT_FOUND:__elmos_missing_function__"
            }
        ),
    }
    return dynamic.get(
        case_id,
        SPECIALIZED_NEGATIVE_STATIC_REASONS.get(case_id, frozenset()),
    )


def _specialized_negative_expected_paths(
    route: Path,
    source_language: str,
    case_id: str,
) -> tuple[str, ...]:
    """Derive exact evidence paths without deriving the replayed bytes."""

    negative_prefix = "corpus/negative/"
    language_filename = SPECIALIZED_NEGATIVE_SOURCE_FILES.get(case_id)
    if language_filename is not None:
        return (negative_prefix + language_filename,)
    if case_id == "specialized-number-arithmetic-unsupported":
        return (
            negative_prefix
            + SPECIALIZED_NUMBER_ARITHMETIC_SOURCE_FILES[source_language],
            negative_prefix + "number_arithmetic_cases.json",
        )
    if case_id == "specialized-string-semantics-unsupported":
        return (
            negative_prefix + SPECIALIZED_STRING_SOURCE_FILES[source_language],
            negative_prefix + "canonical_string_cases.json",
        )
    if case_id in {
        "specialized-non-finite-case-unsupported",
        "specialized-overflow-outside-no-error-domain",
        "missing-symbol-fails-closed",
    }:
        corpus = (
            "holdout"
            if case_id == "specialized-non-finite-case-unsupported"
            else "development"
        )
        corpus_manifest = load(route / "corpus" / corpus / "manifest.json")
        source_file = corpus_manifest.get("source_file")
        cases_file = corpus_manifest.get("cases_file")
        if not isinstance(source_file, str) or not isinstance(cases_file, str):
            raise ValueError(f"{corpus} corpus manifest input paths are invalid")
        cases_relative = (
            negative_prefix + "non_finite_number_cases.json"
            if case_id == "specialized-non-finite-case-unsupported"
            else negative_prefix + "canonical_overflow_cases.json"
            if case_id == "specialized-overflow-outside-no-error-domain"
            else f"corpus/{corpus}/{cases_file}"
        )
        return f"corpus/{corpus}/{source_file}", cases_relative
    if case_id == "undeclared-directed-route-fails-closed":
        return (
            negative_prefix + "undeclared_java_to_java.java",
            negative_prefix + "undeclared_java_to_java_cases.json",
        )
    raise ValueError(f"undeclared specialized negative case: {case_id}")


def validate_specialized_negative_evidence(
    route: Path,
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    failures: list[str],
) -> None:
    """Replay every exact-eight negative case from its byte-bound inputs.

    A negative report is not evidence merely because it names an expected
    error.  This validator snapshots the report-bound inputs, selects the API
    from the fixed case contract, and requires the origin-bound engine to raise
    the exact persisted ``RouteError`` without creating any output tree.
    """

    route_key = manifest.get("route_key")
    source_language = manifest.get("source", {}).get("language")
    target_language = manifest.get("target", {}).get("language")
    if not all(
        isinstance(value, str) and value
        for value in (route_key, source_language, target_language)
    ):
        failures.append("specialized negative replay route tuple is invalid")
        return
    if source_language not in SPECIALIZED_NEGATIVE_CASES or target_language not in (
        SPECIALIZED_NEGATIVE_CASES
    ):
        failures.append("specialized negative replay language is outside exact-eight")
        return

    expected_case_ids = {
        *SPECIALIZED_NEGATIVE_CASES[source_language],
        *SPECIALIZED_NEGATIVE_CASES[target_language],
        *SPECIALIZED_COMMON_NEGATIVE_CASES,
    }
    references = evidence.get("negative_runs")
    expected_reference = "certification/local-negative-evidence.json"
    if references != [expected_reference]:
        failures.append("specialized negative evidence reference set is not exact")
        return
    negative_path = _resolve_below(
        route,
        expected_reference,
        "specialized negative evidence",
        failures,
    )
    if negative_path is None:
        return
    try:
        negative_stat = negative_path.lstat()
        if negative_path.is_symlink() or not stat.S_ISREG(negative_stat.st_mode):
            raise ValueError("not a regular non-symlink file")
        negative_bytes = negative_path.read_bytes()
        result = json.loads(
            negative_bytes.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
        if not isinstance(result, dict):
            raise ValueError("JSON root must be an object")
    except Exception as exc:
        failures.append(f"specialized negative evidence is unreadable: {exc}")
        return

    if set(result) != {
        "schema_version",
        "route",
        "status",
        "expected_result",
        "test_integrity",
        "cases",
        "independent_verifier",
        "external_certification",
    }:
        failures.append("specialized negative evidence top-level keys are not exact")
    if (
        result.get("schema_version") != 1
        or result.get("route") != route_key
        or result.get("status") != "PASSED"
        or result.get("expected_result") != "BLOCKED"
        or result.get("test_integrity") != "PRESERVED"
        or result.get("independent_verifier") != "NOT_RUN"
        or result.get("external_certification") != "NOT_RUN"
    ):
        failures.append("specialized negative evidence boundary is invalid")

    cases = result.get("cases")
    if not isinstance(cases, list):
        failures.append("specialized negative cases are missing")
        return
    case_ids = [
        item.get("case_id") if isinstance(item, dict) else None for item in cases
    ]
    if case_ids != sorted(expected_case_ids):
        failures.append("specialized negative case order/set is not exact")
    if len(case_ids) != len(set(case_ids)):
        failures.append("specialized negative case IDs are duplicated")

    api = _engine_negative_replay_api(
        failures, f"specialized negative replay {route_key}"
    )
    if api is None:
        return
    migrate, migrate_module, analyze, RouteError = api
    provenance_before = _runtime_provenance(
        failures, f"specialized negative replay {route_key} before execution"
    )
    if provenance_before is None:
        return

    with tempfile.TemporaryDirectory(
        prefix=f"elmos-specialized-negative-replay-{route_key}-"
    ) as temporary:
        replay_root = Path(temporary)
        replay_root.chmod(0o700)
        for index, item in enumerate(cases):
            item_label = f"specialized negative cases[{index}]"
            if not isinstance(item, dict):
                failures.append(f"{item_label} must be an object")
                continue
            if set(item) != {
                "case_id",
                "status",
                "expected_result",
                "observed_reason",
                "input_refs",
                "native_analysis",
                "target_execution",
            }:
                failures.append(f"{item_label} keys are not exact")
            case_id = item.get("case_id")
            if not isinstance(case_id, str) or case_id not in expected_case_ids:
                failures.append(f"{item_label}.case_id is not declared for this route")
                continue
            if (
                item.get("status") != "PASSED"
                or item.get("expected_result") != "BLOCKED"
                or item.get("native_analysis") != "EXECUTED"
                or item.get("target_execution") != "NOT_REACHED_BY_DESIGN"
            ):
                failures.append(f"{item_label} did not preserve fail-closed status")
            observed_reason = item.get("observed_reason")
            expected_reasons = specialized_negative_expected_reasons(
                route_key, source_language, case_id
            )
            if not isinstance(observed_reason, str) or observed_reason not in expected_reasons:
                failures.append(f"{item_label}.observed_reason is not exact")

            expected_roles = SPECIALIZED_NEGATIVE_INPUT_ROLES.get(case_id)
            input_refs = item.get("input_refs")
            if expected_roles is None or not isinstance(input_refs, list):
                failures.append(f"{item_label}.input_refs contract is missing")
                continue
            try:
                expected_paths = _specialized_negative_expected_paths(
                    route, source_language, case_id
                )
            except Exception as exc:
                failures.append(f"{item_label}.input_refs paths cannot be derived: {exc}")
                continue
            observed_roles = [
                reference.get("role") if isinstance(reference, dict) else None
                for reference in input_refs
            ]
            if tuple(observed_roles) != expected_roles:
                failures.append(f"{item_label}.input_refs roles/order are not exact")
                continue
            observed_paths = [
                reference.get("path") if isinstance(reference, dict) else None
                for reference in input_refs
            ]
            if tuple(observed_paths) != expected_paths:
                failures.append(f"{item_label}.input_refs paths are not exact")
                continue
            if len(observed_roles) != len(set(observed_roles)):
                failures.append(f"{item_label}.input_refs roles are duplicated")
                continue

            case_root = replay_root / f"{index:03d}-{case_id}"
            case_root.mkdir(mode=0o700)
            snapshots: dict[str, Path] = {}
            bound_inputs: list[tuple[str, Path, Path, bytes, str]] = []
            inputs_valid = True
            for input_index, (role, reference) in enumerate(
                zip(expected_roles, input_refs, strict=True)
            ):
                input_label = f"{item_label}.input_refs[{input_index}]"
                if not isinstance(reference, dict) or set(reference) != {
                    "role",
                    "path",
                    "sha256",
                    "bytes",
                }:
                    failures.append(f"{input_label} keys are not exact")
                    inputs_valid = False
                    continue
                relative = reference.get("path")
                relative_path = Path(relative) if isinstance(relative, str) else None
                if (
                    relative_path is None
                    or not relative
                    or relative_path.is_absolute()
                    or "\\" in relative
                    or any(part in {"", ".", ".."} for part in relative_path.parts)
                ):
                    failures.append(f"{input_label}.path is unsafe")
                    inputs_valid = False
                    continue
                unresolved_origin = route / relative_path
                try:
                    origin_stat = unresolved_origin.lstat()
                    if unresolved_origin.is_symlink() or not stat.S_ISREG(
                        origin_stat.st_mode
                    ):
                        raise ValueError("not a regular non-symlink file")
                    origin = unresolved_origin.resolve(strict=True)
                    origin.relative_to(route.resolve(strict=True))
                    content = origin.read_bytes()
                except Exception as exc:
                    failures.append(f"{input_label} is not a safe bound file: {exc}")
                    inputs_valid = False
                    continue
                digest = sha256_bytes(content)
                byte_count = reference.get("bytes")
                if (
                    reference.get("role") != role
                    or reference.get("sha256") != digest
                    or not isinstance(byte_count, int)
                    or isinstance(byte_count, bool)
                    or byte_count != len(content)
                ):
                    failures.append(f"{input_label} byte binding drift")
                    inputs_valid = False
                    continue
                snapshot = _private_snapshot(
                    case_root,
                    role=role,
                    logical_name=origin.name,
                    content=content,
                )
                snapshots[role] = snapshot
                bound_inputs.append((role, origin, snapshot, content, digest))
            if not inputs_valid or set(snapshots) != set(expected_roles):
                continue

            output_root = case_root / "engine-output-must-not-exist"
            output = output_root / "output"
            fresh_reason: str | None = None
            if case_id == "missing-symbol-fails-closed":
                try:
                    development_manifest = load(
                        route / "corpus" / "development" / "manifest.json"
                    )
                    declared_function = development_manifest.get("function_name")
                    if not isinstance(declared_function, str) or not declared_function:
                        raise ValueError(
                            "development function_name is missing"
                        )
                    valid_source_ir = analyze(
                        snapshots["source"],
                        source_language,
                        declared_function,
                    )
                    if len(valid_source_ir.functions) != 1:
                        raise ValueError(
                            "development source did not yield exactly one declared function"
                        )
                except Exception as exc:
                    failures.append(
                        f"{item_label} valid development-source preflight failed: {exc}"
                    )
                    for role, origin, snapshot, content, digest in bound_inputs:
                        _validate_snapshot_stability(
                            label=f"{item_label}.{role}",
                            origin=origin,
                            snapshot=snapshot,
                            expected_bytes=content,
                            expected_digest=digest,
                            failures=failures,
                        )
                    continue
            try:
                analyze_spec = SPECIALIZED_NEGATIVE_ANALYZE_SPECS.get(case_id)
                if analyze_spec is not None:
                    language, function_name, emitted_target = analyze_spec
                    analyze(
                        snapshots["source"],
                        language,
                        function_name,
                        emitted_target=emitted_target,
                    )
                elif case_id == "undeclared-directed-route-fails-closed":
                    migrate_module(
                        snapshots["source-module"],
                        "java",
                        "java",
                        snapshots["case-manifest"],
                        output,
                    )
                else:
                    function_name = {
                        "specialized-string-semantics-unsupported": "same",
                        "specialized-number-arithmetic-unsupported": "addNumber",
                        "specialized-non-finite-case-unsupported": "echoNumber",
                        "specialized-overflow-outside-no-error-domain": "calculate",
                        "missing-symbol-fails-closed": "__elmos_missing_function__",
                    }[case_id]
                    migrate(
                        snapshots["source"],
                        source_language,
                        target_language,
                        function_name,
                        snapshots["cases"],
                        output,
                    )
            except Exception as exc:
                if type(exc) is not RouteError:
                    failures.append(
                        f"{item_label} raised unexpected exception type "
                        f"{type(exc).__module__}.{type(exc).__qualname__}: {exc}"
                    )
                else:
                    fresh_reason = str(exc)
            else:
                failures.append(f"{item_label} unexpectedly passed fresh replay")
            if output_root.exists():
                failures.append(f"{item_label} created an output/artifact directory")
            if fresh_reason is not None:
                if fresh_reason not in expected_reasons:
                    failures.append(
                        f"{item_label} fresh RouteError reason is not exact: {fresh_reason}"
                    )
                if fresh_reason != observed_reason:
                    failures.append(
                        f"{item_label} observed_reason differs from fresh replay: "
                        f"{observed_reason!r} != {fresh_reason!r}"
                    )
            for role, origin, snapshot, content, digest in bound_inputs:
                _validate_snapshot_stability(
                    label=f"{item_label}.{role}",
                    origin=origin,
                    snapshot=snapshot,
                    expected_bytes=content,
                    expected_digest=digest,
                    failures=failures,
                )
                try:
                    if origin.is_symlink() or not stat.S_ISREG(origin.lstat().st_mode):
                        raise ValueError("origin is no longer a regular non-symlink file")
                    if snapshot.is_symlink() or not stat.S_ISREG(
                        snapshot.lstat().st_mode
                    ):
                        raise ValueError("snapshot is no longer a regular non-symlink file")
                except Exception as exc:
                    failures.append(f"{item_label}.{role} file identity drift: {exc}")

    try:
        if negative_path.read_bytes() != negative_bytes:
            failures.append("specialized negative evidence changed during replay")
        if negative_path.is_symlink() or not stat.S_ISREG(negative_path.lstat().st_mode):
            failures.append("specialized negative evidence file identity changed during replay")
    except OSError as exc:
        failures.append(f"specialized negative evidence final stability check failed: {exc}")
    provenance_after = _runtime_provenance(
        failures, f"specialized negative replay {route_key} after execution"
    )
    if provenance_after is not None and provenance_after != provenance_before:
        failures.append("specialized negative replay runtime provenance changed during execution")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("route_dir", nargs="?")
    parser.add_argument(
        "--runtime-proof-probe",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if args.runtime_proof_probe:
        probe_failures: list[str] = []
        if _engine_proof_api(probe_failures, "Batch29 fresh runtime probe") is None:
            print(
                "\n".join(f"ERROR: {failure}" for failure in probe_failures),
                file=sys.stderr,
            )
            return 1
        print("OK: Batch29 fresh locked proof runtime")
        return 0
    if args.route_dir is None:
        parser.error("route_dir is required")
    route = Path(args.route_dir)
    errors: list[str] = []
    manifest: dict[str, Any] = {}
    certification: dict[str, Any] = {}
    specialized = False
    if not route.is_dir():
        errors.append(f"missing route dir: {route}")
    for directory in REQUIRED_DIRS:
        if not (route / directory).exists():
            errors.append(f"missing: {route / directory}")
    try:
        manifest = load(route / "route.json")
        from route_sets import (  # imported only at the CLI boundary for packed replay
            EVIDENCED_ROUTE_KEYS,
            SPECIALIZED_ROUTE_KEYS,
            split_route_key,
        )

        route_key = manifest.get("route_key")
        if route.name != route_key:
            errors.append("route directory name does not match route.json.route_key")
        if route_key not in EVIDENCED_ROUTE_KEYS:
            errors.append("route_key is outside the explicit Batch 29 allowlist")
        else:
            expected_source, expected_target = split_route_key(str(route_key))
            if (
                manifest.get("source", {}).get("language") != expected_source
                or manifest.get("target", {}).get("language") != expected_target
            ):
                errors.append("route source/target tuple does not match route_key")
            specialized = route_key in SPECIALIZED_ROUTE_KEYS
        for key in REQUIRED_ROUTE:
            if key not in manifest:
                errors.append(f"route.json missing key: {key}")
        if manifest.get("status") not in ALLOWED_ROUTE_STATUS:
            errors.append("invalid route status")
        if manifest.get("source", {}).get("language") == manifest.get("target", {}).get(
            "language"
        ):
            errors.append("source and target must differ")
        if not manifest.get("source", {}).get("versions"):
            errors.append("source versions are empty")
        if not manifest.get("target", {}).get("versions"):
            errors.append("target versions are empty")
        if manifest.get("owner") in {"", "UNASSIGNED", None}:
            errors.append("route owner is unassigned")
        if specialized:
            profiles = manifest.get("profiles", {})
            gates = manifest.get("gates", {})
            if manifest.get("status") != "limited":
                errors.append("specialized exact route status must remain limited")
            if profiles.get("module_profile") != "typed-pure-module-v1":
                errors.append("specialized module profile drift")
            if profiles.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                errors.append("specialized input domain drift")
            for field in (
                "module_equivalence_required",
                "concrete_spans_required",
                "canonical_finite_no_error_input_domain_required",
            ):
                if gates.get(field) is not True:
                    errors.append(f"specialized gate {field} must be true")
            if gates.get("specialized_string_semantics_allowed") is not False:
                errors.append("specialized string semantics must remain blocked")
            cpp_versions = [
                "C++20",
                "Apple clang version 21.0.0 (clang-2100.1.1.101)",
                "arm64-apple-darwin25.6.0",
            ]
            for side in ("source", "target"):
                side_value = manifest.get(side, {})
                if side_value.get("language") == "cpp" and side_value.get(
                    "versions"
                ) != cpp_versions:
                    errors.append(f"specialized {side} C++20/Apple clang tuple drift")
    except Exception as exc:
        errors.append(str(exc))
    try:
        support = load(route / "support-matrix.json")
        if support.get("route_key") != manifest.get("route_key"):
            errors.append("support matrix route_key mismatch")
        for capability in support.get("capabilities", []):
            if capability.get("status") not in ALLOWED_CAP_STATUS:
                errors.append(f"invalid capability status: {capability.get('id')}")
            evidence_refs = capability.get("evidence_refs")
            if (
                capability.get("status") in {"certified", "supported"}
                and not evidence_refs
            ):
                errors.append(
                    f"{capability.get('status')} capability lacks evidence: {capability.get('id')}"
                )
            if capability.get("status") in {
                "conditional",
                "blocked",
            } and not capability.get("reason"):
                errors.append(
                    f"conditional/blocked capability lacks reason: {capability.get('id')}"
                )
            if isinstance(evidence_refs, list):
                for index, reference in enumerate(evidence_refs):
                    path = _resolve_below(
                        route,
                        reference,
                        f"capability {capability.get('id')} evidence_refs[{index}]",
                        errors,
                    )
                    if path is not None and not path.is_file():
                        errors.append(
                            f"capability evidence is missing: {capability.get('id')}:{reference}"
                        )
        if specialized:
            capability_by_id = {
                item.get("id"): item
                for item in support.get("capabilities", [])
                if isinstance(item, dict)
            }
            expected_statuses = {
                "typed-pure-function-v1": "conditional",
                "primitive-types": "conditional",
                "canonical-finite-no-error-input-domain": "supported",
                "string-semantics": "blocked",
                "arithmetic-error-domain": "blocked",
                "finite-number-transport-comparison": "conditional",
                "number-arithmetic": "blocked",
            }
            for capability_id, expected_status in expected_statuses.items():
                if capability_by_id.get(capability_id, {}).get("status") != expected_status:
                    errors.append(
                        f"specialized capability {capability_id} status drift"
                    )
            mappings = load(route / "mappings" / "types.json")
            if mappings.get("types") != ["integer", "number", "boolean"]:
                errors.append("specialized type mapping is not exact integer/number/boolean")
            if mappings.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                errors.append("specialized type mapping input domain drift")
            if mappings.get("string_semantics") != "BLOCK":
                errors.append("specialized type mapping does not block string")
            if mappings.get("type_evidence_corpora") != {
                "integer": "corpus/development",
                "number": "corpus/holdout",
                "boolean": "corpus/real-repository",
            }:
                errors.append("specialized type evidence corpus mapping drift")
            lowering = load(route / "lowering" / "profile.json")
            if lowering.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                errors.append("specialized lowering input domain drift")
            if lowering.get("concrete_spans_required") is not True:
                errors.append("specialized lowering does not require concrete spans")
            if lowering.get("string_semantics") != "BLOCKED":
                errors.append("specialized lowering does not block string")
            if lowering.get("operator_domains", {}).get("number_arithmetic") != {
                "operators": [],
                "blocked_operators": ["+", "-", "*", "/", "%"],
                "status": "BLOCKED",
            }:
                errors.append("specialized number arithmetic lowering policy drift")
    except Exception as exc:
        errors.append(str(exc))
    for file_path in [
        route / "compat-runtime" / "manifest.json",
        route / "certification" / "evidence.json",
        route / "certification" / "certification.json",
    ]:
        try:
            load(file_path)
        except Exception as exc:
            errors.append(str(exc))
    try:
        certification = load(route / "certification" / "certification.json")
        route_evidence = load(route / "certification" / "evidence.json")
        if (
            str(certification.get("status", "")).lower()
            != str(manifest.get("status", "")).lower()
        ):
            errors.append("route and certification statuses must match")
        _, strict_errors = validate_formal_equivalence(route, manifest, certification)
        errors.extend(strict_errors)
        _, module_errors = validate_module_equivalence(
            route, manifest, certification
        )
        errors.extend(module_errors)
        if specialized:
            if certification.get("certification_decision") != "NOT_CERTIFIED":
                errors.append("specialized route must remain NOT_CERTIFIED")
            expected_type_coverage = {
                "development": ["integer"],
                "holdout": ["number"],
                "real-repository": ["boolean"],
            }
            for corpus, coverage in expected_type_coverage.items():
                corpus_manifest = load(
                    route / "corpus" / corpus / "manifest.json"
                )
                if corpus_manifest.get("type_coverage") != coverage:
                    errors.append(f"specialized {corpus} type coverage drift")
                if corpus_manifest.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                    errors.append(f"specialized {corpus} input domain drift")
            if route_evidence.get("execution_status") == "PASSED_LOCAL":
                if route_evidence.get("evidenced_type_coverage") != [
                    "integer",
                    "number",
                    "boolean",
                ]:
                    errors.append("specialized evidence type coverage drift")
                if route_evidence.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                    errors.append("specialized evidence input domain drift")
                if (
                    route_evidence.get("out_of_domain_arithmetic_behavior")
                    != SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
                ):
                    errors.append(
                        "specialized evidence out-of-domain arithmetic boundary drift"
                    )
                validate_specialized_negative_evidence(
                    route,
                    manifest,
                    route_evidence,
                    errors,
                )
                _validate_specialized_native_runtime_replay(
                    route, manifest, errors
                )
        if manifest.get("gates", {}).get("module_equivalence_required") is True:
            module_root = route / "corpus" / "module"
            module_manifest_path = module_root / "manifest.json"
            if not module_manifest_path.is_file():
                errors.append("specialized route module corpus manifest is missing")
            else:
                module_manifest = load(module_manifest_path)
                if module_manifest.get("corpus") != "module":
                    errors.append("module corpus identity is invalid")
                if module_manifest.get("profile") != "typed-pure-module-v1":
                    errors.append("module corpus profile is invalid")
                if module_manifest.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                    errors.append("module corpus input domain is invalid")
                if module_manifest.get("type_coverage_required") != [
                    "integer",
                    "number",
                    "boolean",
                ]:
                    errors.append("module corpus type coverage requirement drift")
                if module_manifest.get("source_language") != manifest.get("source", {}).get(
                    "language"
                ):
                    errors.append("module corpus source language mismatch")
                if module_manifest.get("minimum_function_count") != 3:
                    errors.append("module corpus minimum function count must be exactly 3")
                if (
                    module_manifest.get("independent") is not True
                    or module_manifest.get("independent_functions") is not True
                    or module_manifest.get("rule_authoring_input") is not False
                    or module_manifest.get("call_graph") != []
                ):
                    errors.append("module corpus independence contract is invalid")
                for field in ("source_file", "cases_file"):
                    value = module_manifest.get(field)
                    if (
                        not isinstance(value, str)
                        or not value
                        or Path(value).is_absolute()
                        or ".." in Path(value).parts
                        or not (module_root / value).is_file()
                    ):
                        errors.append(f"module corpus {field} is missing or unsafe")
                cases_value = module_manifest.get("cases_file")
                if isinstance(cases_value, str) and (module_root / cases_value).is_file():
                    module_cases = load(module_root / cases_value)
                    _validate_optional_json_schema(
                        module_cases,
                        "module-case-manifest.schema.json",
                        errors,
                        "module case manifest",
                    )
            for name in (
                "gap-inventory.md",
                "customer-support-profile.md",
                "economics.json",
            ):
                path = route / "certification" / name
                if not path.is_file() or path.stat().st_size == 0:
                    errors.append(f"specialized route certification file is missing: {name}")
            economics_path = route / "certification" / "economics.json"
            if economics_path.is_file():
                economics = load(economics_path)
                if economics.get("route_key") != manifest.get("route_key"):
                    errors.append("economics route_key mismatch")
                if economics.get("status") not in {"NOT_RUN", "PASSED"}:
                    errors.append("economics status is invalid")
    except Exception as exc:
        errors.append(str(exc))
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: {route}")
    return 0


if __name__ == "__main__":
    from fresh_route_runtime import run_in_fresh_locked_runtime

    fresh_runtime_exit = run_in_fresh_locked_runtime(
        Path(__file__), sys.argv[1:]
    )
    if fresh_runtime_exit is not None:
        raise SystemExit(fresh_runtime_exit)
    raise SystemExit(main())
