#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import types
from contextvars import ContextVar
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


def _bootstrap_toolchain_source_receipts() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load only models/toolchains without importing the proof-engine package."""

    package_name = "_elmos_batch29_bootstrap_toolchains"
    module_root = (
        DEFAULT_REPOSITORY_ROOT
        / "engines"
        / "polyglot-route-engine"
        / "src"
        / "elmos_polyglot_route"
    )
    package = types.ModuleType(package_name)
    package.__path__ = [str(module_root)]  # type: ignore[attr-defined]
    sys.modules[package_name] = package
    try:
        for module_name in ("models", "toolchains"):
            qualified = f"{package_name}.{module_name}"
            specification = importlib.util.spec_from_file_location(
                qualified, module_root / f"{module_name}.py"
            )
            if specification is None or specification.loader is None:
                raise RuntimeError("FORMAL_ENGINE_BOOTSTRAP_TOOLCHAINS_LOAD_FAILED")
            module = importlib.util.module_from_spec(specification)
            sys.modules[qualified] = module
            specification.loader.exec_module(module)
        toolchains = sys.modules[f"{package_name}.toolchains"]
        return (
            toolchains.python_source_archive_receipt(),
            toolchains.typescript_compiler_capture_receipt(),
        )
    finally:
        for name in tuple(sys.modules):
            if name == package_name or name.startswith(package_name + "."):
                sys.modules.pop(name, None)


def _copy_bootstrap_runtime_sources(
    root: Path,
    *,
    python_receipt: dict[str, Any],
    typescript_receipt: dict[str, Any],
    python_relative: str,
    typescript_relative: str,
) -> None:
    """Create a private first-materialization source bundle from sealed receipts."""

    root.chmod(0o700)
    python_source = Path(str(python_receipt.get("source_path", "")))
    python_digest = str(python_receipt.get("sha256", ""))
    python_bytes = python_receipt.get("bytes")
    if (
        python_receipt.get("capture_relative_path") != python_relative
        or not python_source.is_absolute()
        or python_source.is_symlink()
        or not python_source.is_file()
        or not isinstance(python_bytes, int)
        or isinstance(python_bytes, bool)
        or python_bytes <= 0
        or len(python_digest) != 64
    ):
        raise RuntimeError("FORMAL_ENGINE_BOOTSTRAP_PYTHON_RECEIPT_INVALID")
    python_content = python_source.read_bytes()
    if (
        len(python_content) != python_bytes
        or hashlib.sha256(python_content).hexdigest() != python_digest
    ):
        raise RuntimeError("FORMAL_ENGINE_BOOTSTRAP_PYTHON_SOURCE_DRIFT")
    python_destination = root / python_relative
    python_destination.parent.mkdir(mode=0o700, parents=True)
    python_destination.write_bytes(python_content)
    python_destination.chmod(0o444)
    if (
        python_source.read_bytes() != python_content
        or python_destination.read_bytes() != python_content
        or python_destination.stat().st_nlink != 1
    ):
        raise RuntimeError("FORMAL_ENGINE_BOOTSTRAP_PYTHON_COPY_DRIFT")

    typescript_source_root = Path(
        str(typescript_receipt.get("source_root", ""))
    )
    records = typescript_receipt.get("files")
    if (
        typescript_receipt.get("capture_relative_path") != typescript_relative
        or not typescript_source_root.is_absolute()
        or typescript_source_root.is_symlink()
        or not typescript_source_root.is_dir()
        or not isinstance(records, list)
        or len(records) != typescript_receipt.get("file_count")
        or typescript_receipt.get("file_count") != 108
        or typescript_receipt.get("bytes") != 19_067_381
    ):
        raise RuntimeError("FORMAL_ENGINE_BOOTSTRAP_TYPESCRIPT_RECEIPT_INVALID")
    seen: set[str] = set()
    total_bytes = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != {
            "path",
            "source_path",
            "sha256",
            "bytes",
            "mode",
        }:
            raise RuntimeError(
                f"FORMAL_ENGINE_BOOTSTRAP_TYPESCRIPT_RECORD_INVALID:{index}"
            )
        relative = record.get("path")
        source_path = record.get("source_path")
        digest = record.get("sha256")
        byte_count = record.get("bytes")
        mode = record.get("mode")
        if (
            not isinstance(relative, str)
            or not relative
            or relative in seen
            or Path(relative).is_absolute()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in Path(relative).parts)
            or not isinstance(source_path, str)
            or not Path(source_path).is_absolute()
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count <= 0
            or mode not in {"0444", "0555"}
        ):
            raise RuntimeError(
                f"FORMAL_ENGINE_BOOTSTRAP_TYPESCRIPT_RECORD_INVALID:{index}"
            )
        seen.add(relative)
        total_bytes += byte_count
        source = Path(source_path)
        try:
            resolved_source = source.resolve(strict=True)
            resolved_source.relative_to(typescript_source_root.resolve(strict=True))
        except (OSError, RuntimeError, ValueError) as exc:
            raise RuntimeError(
                f"FORMAL_ENGINE_BOOTSTRAP_TYPESCRIPT_SOURCE_INVALID:{relative}"
            ) from exc
        if source.is_symlink() or not resolved_source.is_file():
            raise RuntimeError(
                f"FORMAL_ENGINE_BOOTSTRAP_TYPESCRIPT_SOURCE_INVALID:{relative}"
            )
        content = resolved_source.read_bytes()
        if (
            len(content) != byte_count
            or hashlib.sha256(content).hexdigest() != digest
            or f"{stat.S_IMODE(resolved_source.stat().st_mode):04o}" != mode
        ):
            raise RuntimeError(
                f"FORMAL_ENGINE_BOOTSTRAP_TYPESCRIPT_SOURCE_DRIFT:{relative}"
            )
        destination = root / typescript_relative / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.write_bytes(content)
        destination.chmod(int(mode, 8))
        if (
            resolved_source.read_bytes() != content
            or destination.read_bytes() != content
            or destination.stat().st_nlink != 1
        ):
            raise RuntimeError(
                f"FORMAL_ENGINE_BOOTSTRAP_TYPESCRIPT_COPY_DRIFT:{relative}"
            )
    if total_bytes != typescript_receipt.get("bytes"):
        raise RuntimeError("FORMAL_ENGINE_BOOTSTRAP_TYPESCRIPT_BYTES_INVALID")


if __name__ == "__main__":
    from fresh_route_runtime import (
        PYTHON_CAPTURED_ARCHIVE_RELATIVE,
        TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
        run_in_fresh_locked_runtime,
    )

    captured_python_archive = (
        DEFAULT_REPOSITORY_ROOT / PYTHON_CAPTURED_ARCHIVE_RELATIVE
    )
    captured_typescript = (
        DEFAULT_REPOSITORY_ROOT / TYPESCRIPT_CAPTURED_ROOT_RELATIVE
    )
    bootstrap_directory: tempfile.TemporaryDirectory[str] | None = None
    if captured_python_archive.is_file() and captured_typescript.is_dir():
        bootstrap_root = DEFAULT_REPOSITORY_ROOT
    else:
        bootstrap_directory = tempfile.TemporaryDirectory(
            prefix="elmos-batch29-bootstrap-sources-"
        )
        bootstrap_root = Path(bootstrap_directory.name).resolve(strict=True)
        python_receipt, typescript_receipt = (
            _bootstrap_toolchain_source_receipts()
        )
        _copy_bootstrap_runtime_sources(
            bootstrap_root,
            python_receipt=python_receipt,
            typescript_receipt=typescript_receipt,
            python_relative=PYTHON_CAPTURED_ARCHIVE_RELATIVE,
            typescript_relative=TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
        )

    try:
        fresh_runtime_exit = run_in_fresh_locked_runtime(
            Path(__file__),
            sys.argv[1:],
            captured_python_archive_root=bootstrap_root,
            captured_python_archive_relative=PYTHON_CAPTURED_ARCHIVE_RELATIVE,
            captured_typescript_root=bootstrap_root,
            captured_typescript_relative=TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
        )
    finally:
        if bootstrap_directory is not None:
            bootstrap_directory.cleanup()
    if fresh_runtime_exit is not None:
        raise SystemExit(fresh_runtime_exit)

from elmos_polyglot_route.emitter import _SWIFT_HELPERS  # noqa: E402
from elmos_polyglot_route.engine import migrate, migrate_module  # noqa: E402
from elmos_polyglot_route.models import (  # noqa: E402
    PENDING_ANALYZER_LANGUAGES,
    PENDING_REPOSITORY_LANGUAGES,
    Language,
    RouteError,
    SemanticIR,
)
from elmos_polyglot_route.native import (  # noqa: E402
    swift_analyzer_build_receipt,
)
from elmos_polyglot_route.source_analyzer import analyze  # noqa: E402
from route_sets import (  # noqa: E402
    ALL_DECLARED_ROUTE_KEYS,
    COMPLETE_ROUTE_KEYS,
    COMPLETION_ROUTE_KEYS,
    CORE_LANGUAGES,
    CORE_ROUTE_KEYS,
    DEPRECATED_ROUTE_KEYS,
    DEPRECATED_ROUTE_LANGUAGES,
    ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS,
    ELEVEN_LANGUAGE_MATRIX_LANGUAGES,
    EVIDENCED_ROUTE_KEYS,
    EXECUTABLE_DIRECT_ROUTE_KEYS,
    EXECUTABLE_ROUTE_SETS,
    MODULE_EQUIVALENCE_ROUTE_KEYS,
    NINE_LANGUAGE_COMPLETE_ROUTE_KEYS,
    NINE_LANGUAGE_MATRIX_LANGUAGES,
    NODEJS_EXACT_ROUTE_KEYS,
    PHP_EXACT_ROUTE_KEYS,
    PREPARABLE_ROUTE_SETS,
    READ_ONLY_ROUTE_SETS,
    ROUTE_PROVENANCE_PARTITIONS,
    SPECIALIZED_ROUTE_KEYS,
    SUPPORTED_ROUTE_LANGUAGES,
    TEN_LANGUAGE_COMPLETE_ROUTE_KEYS,
    TEN_LANGUAGE_MATRIX_LANGUAGES,
    V3_EXACT_ROUTE_KEYS,
    V3_LANGUAGES,
    nodejs_negative_case_ids,
    provenance_route_set,
    split_executable_route_key,
    split_route_key,
)

EXACT_ROUTE_SETS: dict[str, tuple[str, ...]] = {
    "cpp-objc-swift-java-exact-8": SPECIALIZED_ROUTE_KEYS,
}


def _safe_canonical_path(path: Path) -> Path:
    raw_str = str(path)
    if sys.platform == "darwin":
        if raw_str.startswith("/var/"):
            return Path("/private" + raw_str)
        if raw_str.startswith("/tmp/"):
            return Path("/private" + raw_str)
        if raw_str.startswith("/etc/"):
            return Path("/private" + raw_str)
    return path
from route_runtime_metadata import (  # noqa: E402
    ENGINE_PATHS,
    LEGACY_CAMPAIGN_BYTES,
    LEGACY_CAMPAIGN_RELATIVE,
    LEGACY_CAMPAIGN_SHA256,
    LEGACY_PACK_KEY,
    LEGACY_REPLAY_ASSET_IDENTITIES,
    LEGACY_REPLAY_METHOD_SHA256,
    SHORT_VERSIONS,
    V3_RESEARCH_ROUTE_VERSION,
    VERSIONS,
    legacy_route_execution_authority_document,
    route_execution_authorities_document,
    support_matrix_markdown_bytes,
    v3_research_certification_document,
    v3_research_evidence_document,
    v3_research_support_document,
)

B16_LANGUAGES: tuple[Language, ...] = CORE_LANGUAGES  # type: ignore[assignment]
SPECIALIZED_INPUT_DOMAIN = "canonical-finite-no-error-input-domain"
SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC = "BLOCKED_NOT_EQUIVALENTLY_MODELED"
NODEJS_INPUT_DOMAIN = "nodejs-es2022-esm-safe-integer-finite-v1"
NODEJS_OUT_OF_DOMAIN_BEHAVIOR = (
    "BLOCKED_OUTSIDE_NODEJS_ES2022_ESM_SAFE_INTEGER_FINITE_V1"
)
EXECUTABLE_MUTABLE_ROUTE_KEYS = EXECUTABLE_DIRECT_ROUTE_KEYS
NOT_RUN_PREPARED_AT = "2026-08-09T00:00:00+00:00"
MODULE_SINGLE_ARTIFACT_ROLES = frozenset(
    {
        "identifier-plan",
        "raw-target-ir",
        "normalized-target-ir",
        "source-module-semantic-ir",
        "target-module-semantic-ir",
        "source-module-observations",
        "target-module-observations",
        "original-source-module-artifact",
        "emitted-target-module-artifact",
        "module-formal-input",
        "source-module-validation",
        "target-module-validation",
        "module-case-manifest",
        "source-module-inventory",
        "target-module-inventory",
        "whole-file-module-closure",
    }
)
MODULE_PER_FUNCTION_ARTIFACT_ROLES = frozenset(
    {"formal-function-input", "formal-function-smt2", "formal-function-result"}
)
SWIFT_DEPENDENCY_TREE = {
    "identity": "swift-syntax",
    "version": "600.0.1",
    "revision": "0687f71944021d616d34d922343dcef086855920",
    "sha256": "sha256:b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d",
    "file_count": 753,
    "bytes": 8_866_479,
}
SWIFT_DEPENDENCY_CACHE_KEYS = {
    "cache_key",
    "cache_schema",
    "object_store_policy",
    "identity",
    "version",
    "revision",
    "seed",
    "sha256",
    "file_count",
    "bytes",
}
SWIFT_DEPENDENCY_MIRROR_KEYS = {
    "seed",
    "cache",
    "git",
    "identity",
    "version",
    "revision",
    "sha256",
    "file_count",
    "bytes",
}
SWIFT_DEPENDENCY_SEED = "verified-content-addressed-standalone-cache"
SWIFT_DEPENDENCY_CACHE_SCHEMA = "swift-dependencies-standalone-v2"
SWIFT_DEPENDENCY_OBJECT_STORE_POLICY = (
    "standalone-no-alternates-no-hardlinks-v2"
)
SWIFT_DEPENDENCY_CACHE_KEY = (
    "swift-syntax-standalone-v2-600.0.1-"
    "0687f71944021d616d34d922343dcef086855920-"
    "b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
)
SWIFT_GIT_IDENTITY = {
    "path": "/Applications/Xcode.app/Contents/Developer/usr/bin/git",
    "sha256": "sha256:10f9c1df894525ae4c7454258febab6d3d25071062b42cb48dbb1842cdffd2a9",
    "version": "git version 2.50.1 (Apple Git-155)",
}


def nodejs_route_error_code(reason: str) -> str | None:
    """Return one exact Node.js domain code from a native wrapper or direct error."""

    if not reason or "\n" in reason or "\r" in reason:
        return None
    detail = reason
    prefix = "NATIVE_ANALYZER_FAILED:"
    if reason.startswith(prefix):
        wrapped = reason[len(prefix) :].split(":", 1)
        if len(wrapped) != 2 or not Path(wrapped[0]).is_absolute():
            return None
        detail = wrapped[1]
    code = detail.split(":", 1)[0]
    if (
        not code
        or not code[0].isupper()
        or any(
            not (character.isupper() or character.isdigit() or character == "_")
            for character in code
        )
    ):
        return None
    return code


def nodejs_stable_route_error(reason: str) -> str:
    """Remove only the private absolute analyzer snapshot path from an error."""

    prefix = "NATIVE_ANALYZER_FAILED:"
    if not reason.startswith(prefix):
        return reason
    wrapped = reason[len(prefix) :].split(":", 1)
    if len(wrapped) != 2 or not Path(wrapped[0]).is_absolute():
        raise RuntimeError(f"NODEJS_NATIVE_ERROR_WRAPPER_INVALID:{reason}")
    return wrapped[1]


def declared_input_domain(route_key: str) -> str:
    if route_key in SPECIALIZED_ROUTE_KEYS:
        return SPECIALIZED_INPUT_DOMAIN
    if route_key in NODEJS_EXACT_ROUTE_KEYS:
        return NODEJS_INPUT_DOMAIN
    if route_key in CORE_ROUTE_KEYS:
        return "legacy-profile-defined-domain"
    return "typed-pure-function-v1-declared-domain"


def is_nodejs_typescript_route(source: Language, target: Language) -> bool:
    """Return whether the exact Node route crosses TypeScript's number-only boundary."""

    return {source, target} == {"javascript", "typescript"}


def nodejs_route_types(source: Language, target: Language) -> list[str]:
    """Declare only types backed by the exact source and target annotations.

    TypeScript's ``number`` annotation cannot be re-labelled as canonical
    ``integer``.  The JavaScript/TypeScript pair therefore uses the shared
    finite-number, boolean, and strict string subset; every other Node route
    keeps string blocked and may use explicit JSDoc ``integer``.
    """

    if is_nodejs_typescript_route(source, target):
        return ["number", "boolean", "string"]
    return ["integer", "number", "boolean"]


EXTENSIONS = {
    "java": "java",
    "python": "py",
    "csharp": "cs",
    "typescript": "ts",
    "javascript": "mjs",
    "go": "go",
    "rust": "rs",
    "cpp": "cpp",
    "objc": "m",
    "swift": "swift",
    "php": "php",
    "kotlin": "kt",
    "react": "tsx",
    "flutter": "dart",
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

NODEJS_TYPESCRIPT_CORPUS_PROFILES: dict[str, dict[str, Any]] = {
    "development": {
        "source_name": "clamp_number",
        "function_name": "clampNumber",
        "type_coverage": ["number"],
        "sources": {
            "typescript": (
                "export function clampNumber(value: number, minimum: number, maximum: number): number {\n"
                "  if (value < minimum) { return minimum; }\n"
                "  if (value > maximum) { return maximum; }\n"
                "  return value;\n"
                "}\n"
            ),
            "javascript": (
                "/**\n"
                " * @param {number} value\n"
                " * @param {number} minimum\n"
                " * @param {number} maximum\n"
                " * @returns {number}\n"
                " */\n"
                "export function clampNumber(value, minimum, maximum) {\n"
                "  if (value < minimum) { return minimum; }\n"
                "  if (value > maximum) { return maximum; }\n"
                "  return value;\n"
                "}\n"
            ),
        },
        "cases": [
            {"args": [-10.5, 0.0, 100.0], "expected": 0.0},
            {"args": [55.25, 0.0, 100.0], "expected": 55.25},
            {"args": [101.5, 0.0, 100.0], "expected": 100.0},
        ],
    },
    "holdout": {
        "source_name": "same_string",
        "function_name": "sameString",
        "type_coverage": ["string"],
        "sources": {
            "typescript": (
                "export function sameString(left: string, right: string): boolean {\n"
                "  return left === right;\n"
                "}\n"
            ),
            "javascript": (
                "/**\n"
                " * @param {string} left\n"
                " * @param {string} right\n"
                " * @returns {boolean}\n"
                " */\n"
                "export function sameString(left, right) {\n"
                "  return left === right;\n"
                "}\n"
            ),
        },
        "cases": [
            {"args": ["same", "same"], "expected": True},
            {"args": ["left", "right"], "expected": False},
            {"args": ["é", "é"], "expected": False},
        ],
    },
    "real-repository": {
        "source_name": "both",
        "function_name": "both",
        "type_coverage": ["boolean"],
        "sources": {
            "typescript": (
                "export function both(left: boolean, right: boolean): boolean { return left && right; }\n"
            ),
            "javascript": (
                "/**\n"
                " * @param {boolean} left\n"
                " * @param {boolean} right\n"
                " * @returns {boolean}\n"
                " */\n"
                "export function both(left, right) { return left && right; }\n"
            ),
        },
        "cases": [
            {"args": [True, True], "expected": True},
            {"args": [True, False], "expected": False},
            {"args": [False, False], "expected": False},
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
            "objc": (
                "#import <Foundation/Foundation.h>\ndouble echoNumber(double value) { return value; }\n"
            ),
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
    "csharp": "EquivalenceModule.cs",
    "go": "equivalence_module.go",
    "rust": "equivalence_module.rs",
    "python": "equivalence_module.py",
    "typescript": "equivalence_module.ts",
    "cpp": "equivalence_module.cpp",
    "objc": "equivalence_module.m",
    "swift": "equivalence_module.swift",
    "javascript": "equivalence_module.mjs",
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
    ".mjs",
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
CONTROLLED_NATIVE_FULL_TREES = frozenset({"javascript", "rust", "typescript"})
CSHARP_ANALYZER_CAPTURE_INPUTS = (
    "engines/dotnet-engine/global.json",
    "engines/dotnet-engine/Directory.Build.props",
    "engines/dotnet-engine/Directory.Packages.props",
    (
        "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli/"
        "Elmos.Dotnet.SemanticCli.csproj"
    ),
    "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli/Program.cs",
    "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli/packages.lock.json",
)
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


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _stable_regular_file_bytes(
    root: Path,
    path: Path,
    *,
    label: str,
    require_nonempty: bool = True,
) -> bytes:
    """Read one confined, standalone regular file through a stable descriptor."""

    try:
        resolved_root = root.resolve(strict=True)
        root_metadata = root.lstat()
        relative = path.relative_to(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise RuntimeError(f"{label}_UNSAFE:{path}") from exc
    if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError(f"{label}_UNSAFE:{path}")

    current = root
    try:
        for part in relative.parts[:-1]:
            current = current / part
            metadata = current.lstat()
            if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeError
        before = path.lstat()
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(f"{label}_UNSAFE:{path}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        raise RuntimeError(f"{label}_UNSAFE:{path}")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            content = stream.read()
            after_descriptor = os.fstat(stream.fileno())
        after_path = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"{label}_UNSAFE:{path}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    def identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    if (
        identity(before) != identity(opened)
        or identity(opened) != identity(after_descriptor)
        or identity(after_descriptor) != identity(after_path)
        or after_path.st_nlink != 1
        or len(content) != after_path.st_size
        or (require_nonempty and not content)
    ):
        raise RuntimeError(f"{label}_CHANGED_DURING_READ:{path}")
    return content


_DirectoryIdentity = tuple[int, int, int, int, int]
_TRANSACTION_CREATED_DIRECTORIES: ContextVar[
    dict[Path, _DirectoryIdentity] | None
] = ContextVar("batch29_transaction_created_directories", default=None)


def _directory_identity(metadata: os.stat_result) -> _DirectoryIdentity:
    """Return fields that identify one owned directory across child changes."""

    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
    )


def _safe_atomic_write_parent(path: Path) -> tuple[Path, os.stat_result]:
    """Return a stable direct parent, creating only missing plain directories."""

    parent = _safe_canonical_path(path.parent)
    missing: list[Path] = []
    created_directories = _TRANSACTION_CREATED_DIRECTORIES.get()
    current = parent
    while True:
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            missing.append(current)
            if current.parent == current:
                raise RuntimeError(f"ATOMIC_WRITE_PARENT_UNSAFE:{path.parent}")
            current = current.parent
            continue
        if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(f"ATOMIC_WRITE_PARENT_UNSAFE:{path.parent}")
        break
    for directory in reversed(missing):
        try:
            directory.mkdir()
            metadata = directory.lstat()
        except OSError as exc:
            raise RuntimeError(f"ATOMIC_WRITE_PARENT_UNSAFE:{path.parent}") from exc
        if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(f"ATOMIC_WRITE_PARENT_UNSAFE:{path.parent}")
        if created_directories is not None:
            created_directories[directory] = _directory_identity(metadata)
    for ancestor in (parent, *parent.parents):
        try:
            ancestor_metadata = ancestor.lstat()
        except OSError as exc:
            raise RuntimeError(f"ATOMIC_WRITE_PARENT_UNSAFE:{path.parent}") from exc
        if ancestor.is_symlink() or not stat.S_ISDIR(ancestor_metadata.st_mode):
            raise RuntimeError(f"ATOMIC_WRITE_PARENT_UNSAFE:{path.parent}")
    try:
        parent_metadata = parent.lstat()
        resolved_parent = parent.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"ATOMIC_WRITE_PARENT_UNSAFE:{path.parent}") from exc
    if parent.is_symlink() or not stat.S_ISDIR(parent_metadata.st_mode):
        raise RuntimeError(f"ATOMIC_WRITE_PARENT_UNSAFE:{path.parent}")
    return resolved_parent, parent_metadata


def _atomic_write_bytes_impl(path: Path, content: bytes) -> None:
    resolved_parent, parent_before = _safe_atomic_write_parent(path)
    canonical_parent = _safe_canonical_path(path.parent)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise RuntimeError(f"ATOMIC_WRITE_TARGET_UNSAFE:{path}") from exc
    if existing is not None and (
        path.is_symlink()
        or not stat.S_ISREG(existing.st_mode)
        or existing.st_nlink != 1
    ):
        raise RuntimeError(f"ATOMIC_WRITE_TARGET_UNSAFE:{path}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=resolved_parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
        parent_after = canonical_parent.lstat()
        if (
            path.parent.is_symlink()
            or canonical_parent.is_symlink()
            or not stat.S_ISDIR(parent_after.st_mode)
            or (parent_before.st_dev, parent_before.st_ino)
            != (parent_after.st_dev, parent_after.st_ino)
        ):
            raise RuntimeError(f"ATOMIC_WRITE_PARENT_CHANGED:{path.parent}")
        try:
            current = path.lstat()
        except FileNotFoundError:
            current = None
        except OSError as exc:
            raise RuntimeError(f"ATOMIC_WRITE_TARGET_CHANGED:{path}") from exc
        if existing is None:
            if current is not None:
                raise RuntimeError(f"ATOMIC_WRITE_TARGET_CHANGED:{path}")
        elif current is None or (
            path.is_symlink()
            or not stat.S_ISREG(current.st_mode)
            or current.st_nlink != 1
            or (
                existing.st_dev,
                existing.st_ino,
                existing.st_mode,
                existing.st_size,
                existing.st_nlink,
                existing.st_mtime_ns,
                existing.st_ctime_ns,
            )
            != (
                current.st_dev,
                current.st_ino,
                current.st_mode,
                current.st_size,
                current.st_nlink,
                current.st_mtime_ns,
                current.st_ctime_ns,
            )
        ):
            raise RuntimeError(f"ATOMIC_WRITE_TARGET_CHANGED:{path}")
        os.replace(temporary, resolved_parent / path.name)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    _atomic_write_bytes_impl(path, content)


def _transaction_target_original(root: Path, path: Path) -> bytes | None:
    """Return exact original bytes, or ``None`` for a safely absent target."""

    try:
        root_metadata = root.lstat()
        resolved_root = root.resolve(strict=True)
        relative = path.relative_to(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise RuntimeError(f"DOCUMENT_TRANSACTION_SOURCE_UNSAFE:{path}") from exc
    if (
        root.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or not relative.parts
    ):
        raise RuntimeError(f"DOCUMENT_TRANSACTION_SOURCE_UNSAFE:{path}")

    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            # Once a confined ancestor is absent, the destination is absent as
            # well.  Directory creation remains deferred until transaction
            # commit so this snapshot phase has zero side effects.
            return None
        except OSError as exc:
            raise RuntimeError(
                f"DOCUMENT_TRANSACTION_SOURCE_UNSAFE:{path}"
            ) from exc
        if current.is_symlink():
            raise RuntimeError(f"DOCUMENT_TRANSACTION_SOURCE_UNSAFE:{path}")
        if index < len(relative.parts) - 1:
            if not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeError(
                    f"DOCUMENT_TRANSACTION_SOURCE_UNSAFE:{path}"
                )
            try:
                current.resolve(strict=True).relative_to(resolved_root)
            except (OSError, ValueError) as exc:
                raise RuntimeError(
                    f"DOCUMENT_TRANSACTION_SOURCE_UNSAFE:{path}"
                ) from exc
            continue
        return _stable_regular_file_bytes(
            root,
            path,
            label="DOCUMENT_TRANSACTION_SOURCE",
            require_nonempty=False,
        )
    raise RuntimeError(f"DOCUMENT_TRANSACTION_SOURCE_UNSAFE:{path}")


def _remove_transaction_created_file(
    root: Path, path: Path, expected_content: bytes
) -> None:
    """Remove only a confined standalone file written by this transaction."""

    observed = _transaction_target_original(root, path)
    if observed is None:
        return
    if observed != expected_content:
        raise RuntimeError(f"DOCUMENT_TRANSACTION_ROLLBACK_TARGET_CHANGED:{path}")
    try:
        before = path.lstat()
        resolved_parent, parent_before = _safe_atomic_write_parent(path)
        current = path.lstat()
        parent_current = path.parent.lstat()
    except OSError as exc:
        raise RuntimeError(
            f"DOCUMENT_TRANSACTION_ROLLBACK_REMOVE_FAILED:{path}"
        ) from exc
    def identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )
    if (
        path.is_symlink()
        or not stat.S_ISREG(current.st_mode)
        or current.st_nlink != 1
        or identity(before) != identity(current)
        or (parent_before.st_dev, parent_before.st_ino)
        != (parent_current.st_dev, parent_current.st_ino)
    ):
        raise RuntimeError(f"DOCUMENT_TRANSACTION_ROLLBACK_TARGET_CHANGED:{path}")
    try:
        os.unlink(resolved_parent / path.name)
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeError(
            f"DOCUMENT_TRANSACTION_ROLLBACK_REMOVE_FAILED:{path}"
        ) from exc
    raise RuntimeError(f"DOCUMENT_TRANSACTION_ROLLBACK_REMOVE_FAILED:{path}")


def _remove_transaction_created_directories(
    root: Path,
    created_directories: dict[Path, _DirectoryIdentity],
) -> list[str]:
    """Remove only still-owned empty directories created by this transaction."""

    failures: list[str] = []
    try:
        resolved_root = root.resolve(strict=True)
        root_metadata = root.lstat()
    except OSError as exc:
        return [f"{root}:DOCUMENT_TRANSACTION_DIRECTORY_ROOT_UNSAFE:{exc}"]
    if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        return [f"{root}:DOCUMENT_TRANSACTION_DIRECTORY_ROOT_UNSAFE"]

    ordered = sorted(
        created_directories.items(),
        key=lambda item: (len(item[0].parts), str(item[0])),
        reverse=True,
    )
    for directory, expected_identity in ordered:
        try:
            relative = directory.relative_to(root)
        except ValueError:
            failures.append(
                f"{directory}:DOCUMENT_TRANSACTION_DIRECTORY_PATH_ESCAPE"
            )
            continue
        if not relative.parts:
            failures.append(
                f"{directory}:DOCUMENT_TRANSACTION_DIRECTORY_ROOT_SELECTED"
            )
            continue

        current = root
        try:
            metadata: os.stat_result | None = None
            for part in relative.parts:
                current = current / part
                metadata = current.lstat()
                if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                    raise RuntimeError
            assert metadata is not None
            directory.resolve(strict=True).relative_to(resolved_root)
        except FileNotFoundError:
            continue
        except (OSError, RuntimeError, ValueError):
            failures.append(
                f"{directory}:DOCUMENT_TRANSACTION_DIRECTORY_CHANGED"
            )
            continue
        if _directory_identity(metadata) != expected_identity:
            failures.append(
                f"{directory}:DOCUMENT_TRANSACTION_DIRECTORY_CHANGED"
            )
            continue

        try:
            directory.rmdir()
        except FileNotFoundError:
            continue
        except OSError as exc:
            reason = (
                "DOCUMENT_TRANSACTION_DIRECTORY_NOT_EMPTY"
                if exc.errno in {errno.EEXIST, errno.ENOTEMPTY}
                else f"DOCUMENT_TRANSACTION_DIRECTORY_REMOVE_FAILED:{exc}"
            )
            failures.append(f"{directory}:{reason}")
            continue
        try:
            directory.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            failures.append(
                f"{directory}:DOCUMENT_TRANSACTION_DIRECTORY_REMOVE_FAILED:{exc}"
            )
            continue
        failures.append(
            f"{directory}:DOCUMENT_TRANSACTION_DIRECTORY_REAPPEARED"
        )
    return failures


def _transactional_write_bytes(
    root: Path, documents: tuple[tuple[Path, bytes], ...]
) -> None:
    """Create/replace a prebuilt set or restore every original path state."""

    paths = tuple(path for path, _ in documents)
    if not paths or len(paths) != len(set(paths)):
        raise RuntimeError("DOCUMENT_TRANSACTION_SELECTION_INVALID")
    originals = {path: _transaction_target_original(root, path) for path in paths}
    attempted: list[tuple[Path, bytes]] = []
    created_directories: dict[Path, _DirectoryIdentity] = {}
    tracker_token = _TRANSACTION_CREATED_DIRECTORIES.set(created_directories)
    try:
        try:
            for path, content in documents:
                attempted.append((path, content))
                _atomic_write_bytes(path, content)
        except BaseException as error:
            rollback_failures: list[str] = []
            for path, content in reversed(attempted):
                try:
                    original = originals[path]
                    if original is None:
                        _remove_transaction_created_file(root, path, content)
                    else:
                        _atomic_write_bytes_impl(path, original)
                except BaseException as rollback_error:  # pragma: no cover - host I/O loss
                    rollback_failures.append(f"{path}:{rollback_error}")
            rollback_failures.extend(
                _remove_transaction_created_directories(
                    root,
                    created_directories,
                )
            )
            if rollback_failures:
                raise RuntimeError(
                    "DOCUMENT_TRANSACTION_ROLLBACK_FAILED:"
                    + " | ".join(rollback_failures)
                ) from error
            raise
    finally:
        _TRANSACTION_CREATED_DIRECTORIES.reset(tracker_token)


def write_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_write_bytes(path, _json_bytes(value))


def validate_portable_swift_analyzer_receipt(receipt: dict[str, Any]) -> None:
    """Validate the complete receipt before any route artifact is written."""

    from validate_route import _validate_swift_analyzer_receipt_document

    binary = receipt.get("binary")
    live_binary = (
        Path(binary["path"])
        if isinstance(binary, dict) and isinstance(binary.get("path"), str)
        else None
    )
    failures: list[str] = []
    validated = _validate_swift_analyzer_receipt_document(
        receipt,
        label="generated Swift analyzer build receipt",
        failures=failures,
        live_binary=live_binary,
    )
    if validated is None or failures:
        detail = " | ".join(failures) if failures else "unknown receipt failure"
        raise RuntimeError(f"SWIFT_ANALYZER_BUILD_RECEIPT_INVALID:{detail}")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sealed_source_identity(path: Path, *, label: str) -> dict[str, Any]:
    """Read one regular source while binding its stable bytes and mode."""

    try:
        resolved = path.resolve(strict=True)
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise RuntimeError
        content = resolved.read_bytes()
        after = path.lstat()
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(f"FORMAL_ENGINE_SOURCE_SEAL_INVALID:{label}") from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_uid,
        after.st_gid,
        after.st_nlink,
        after.st_mtime_ns,
    )
    if (
        before_identity != after_identity
        or len(content) != after.st_size
        or not content
    ):
        raise RuntimeError(f"FORMAL_ENGINE_SOURCE_CHANGED_DURING_SEAL:{label}")
    return {
        "source": resolved,
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
    }


def _assert_sealed_source_identity(
    sealed: dict[str, Any], *, label: str
) -> None:
    observed = _sealed_source_identity(Path(sealed["source"]), label=label)
    for field in ("source", "sha256", "bytes", "mode"):
        if observed[field] != sealed[field]:
            raise RuntimeError(f"FORMAL_ENGINE_SOURCE_SEAL_DRIFT:{label}:{field}")


def legacy_campaign_authority(repo: Path) -> dict[str, Any]:
    """Recompute the immutable v1 campaign and exact-three replay authority.

    The original 30 routes are historical evidence.  Current source code is
    deliberately not an authority for replaying or rewriting it: every route
    must retain the same pack-captured launcher, validator, and Schema bytes.
    """

    campaign_path = repo / LEGACY_CAMPAIGN_RELATIVE
    campaign_payload = _stable_regular_file_bytes(
        repo,
        campaign_path,
        label="LEGACY_CAMPAIGN",
    )
    if (
        len(campaign_payload) != LEGACY_CAMPAIGN_BYTES
        or "sha256:" + hashlib.sha256(campaign_payload).hexdigest()
        != LEGACY_CAMPAIGN_SHA256
    ):
        raise RuntimeError("LEGACY_CAMPAIGN_IDENTITY_DRIFT")
    try:
        campaign = json.loads(campaign_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("LEGACY_CAMPAIGN_JSON_INVALID") from exc
    if not isinstance(campaign, dict):
        raise RuntimeError("LEGACY_CAMPAIGN_JSON_OBJECT_REQUIRED")
    if (
        campaign.get("schema_version") != 1
        or campaign.get("campaign_key") != LEGACY_PACK_KEY
        or campaign.get("version") != "1.0.0"
    ):
        raise RuntimeError("LEGACY_CAMPAIGN_CONTRACT_DRIFT")
    route_set = campaign.get("route_set")
    route_records = route_set.get("routes") if isinstance(route_set, dict) else None
    if not isinstance(route_records, list) or len(route_records) != len(
        CORE_ROUTE_KEYS
    ):
        raise RuntimeError("LEGACY_CAMPAIGN_ROUTE_COUNT_DRIFT")
    route_keys = [
        record.get("route_key") if isinstance(record, dict) else None
        for record in route_records
    ]
    if len(set(route_keys)) != len(route_keys) or set(route_keys) != set(
        CORE_ROUTE_KEYS
    ):
        raise RuntimeError("LEGACY_CAMPAIGN_ROUTE_PARTITION_DRIFT")

    routes_root = repo / "verification-packs" / LEGACY_PACK_KEY / "evidence" / "routes"
    try:
        observed_route_keys = {
            path.name
            for path in routes_root.iterdir()
            if path.is_dir() and not path.is_symlink()
        }
    except OSError as exc:
        raise RuntimeError("LEGACY_CAMPAIGN_ROUTE_ROOT_INVALID") from exc
    if observed_route_keys != set(CORE_ROUTE_KEYS):
        raise RuntimeError("LEGACY_CAMPAIGN_ROUTE_TREE_DRIFT")

    asset_authority: dict[str, dict[str, str | int]] = {}
    for relative, identity in LEGACY_REPLAY_ASSET_IDENTITIES.items():
        for route_key in CORE_ROUTE_KEYS:
            asset_path = routes_root / route_key / relative
            asset_payload = _stable_regular_file_bytes(
                repo,
                asset_path,
                label=f"LEGACY_REPLAY_{str(identity['role']).upper()}",
            )
            if (
                len(asset_payload) != identity["bytes"]
                or "sha256:" + hashlib.sha256(asset_payload).hexdigest()
                != identity["sha256"]
            ):
                raise RuntimeError(
                    f"LEGACY_REPLAY_ASSET_IDENTITY_DRIFT:{route_key}:{relative}"
                )
        asset_authority[str(identity["role"])] = {
            "path": relative,
            "sha256": str(identity["sha256"]),
            "bytes": int(identity["bytes"]),
        }

    authority: dict[str, Any] = {
        "policy": "immutable-pack-captured-v1",
        "pack_key": LEGACY_PACK_KEY,
        "route_set": "legacy-complete-30",
        "route_count": len(CORE_ROUTE_KEYS),
        "campaign": {
            "path": LEGACY_CAMPAIGN_RELATIVE,
            "sha256": LEGACY_CAMPAIGN_SHA256,
            "bytes": LEGACY_CAMPAIGN_BYTES,
        },
        "replay_assets": asset_authority,
        "method_sha256": LEGACY_REPLAY_METHOD_SHA256,
        "native_reexecution_status": "NOT_RUN",
    }
    authority_payload = json.dumps(
        authority,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    authority["authority_sha256"] = (
        "sha256:" + hashlib.sha256(authority_payload).hexdigest()
    )
    if authority != legacy_route_execution_authority_document():
        raise RuntimeError("LEGACY_EXECUTION_AUTHORITY_CONTRACT_DRIFT")
    return authority


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


def negative_input_ref(
    evidence_root: Path,
    path: Path,
    role: str,
) -> dict[str, str | int]:
    """Bind one negative replay input to an exact, unique semantic role."""

    if role not in {"source", "cases", "source-module", "case-manifest"}:
        raise RuntimeError(f"NEGATIVE_INPUT_ROLE_UNDECLARED:{role}")
    return {"role": role, **artifact_ref(evidence_root, path)}


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
    try:
        semantic_ir = SemanticIR.from_mapping(value)
    except RouteError as exc:
        raise RuntimeError(f"{label}_IR_INVALID:{exc}") from exc
    if semantic_ir.diagnostics or not semantic_ir.functions:
        raise RuntimeError(f"{label}_IR_NOT_EXACT")
    return [function.semantic_mapping() for function in semantic_ir.functions]


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
    engine_module_root = engine / "src" / "elmos_polyglot_route"
    from elmos_polyglot_route.toolchains import (
        python_source_archive_receipt,
        typescript_compiler_capture_receipt,
    )
    from fresh_route_runtime import (
        PYTHON_CAPTURED_ARCHIVE_RELATIVE,
        TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
    )

    python_receipt = python_source_archive_receipt()
    python_source_path = Path(str(python_receipt.get("source_path", "")))
    python_capture_relative = str(python_receipt.get("capture_relative_path", ""))
    python_sha256 = str(python_receipt.get("sha256", ""))
    python_bytes = python_receipt.get("bytes")
    if (
        python_capture_relative != PYTHON_CAPTURED_ARCHIVE_RELATIVE
        or python_sha256
        != PYTHON_CAPTURED_ARCHIVE_RELATIVE.removeprefix(
            "runtime/python/sha256-"
        ).removesuffix(".tar.gz")
        or not isinstance(python_bytes, int)
        or isinstance(python_bytes, bool)
        or python_bytes <= 0
        or python_source_path.is_symlink()
        or not python_source_path.is_file()
        or python_source_path.stat().st_size != python_bytes
        or hashlib.sha256(python_source_path.read_bytes()).hexdigest() != python_sha256
    ):
        raise RuntimeError("FORMAL_ENGINE_PYTHON_SOURCE_ARCHIVE_RECEIPT_INVALID")

    typescript_receipt = typescript_compiler_capture_receipt()
    typescript_capture_relative = str(
        typescript_receipt.get("capture_relative_path", "")
    )
    typescript_source_root = Path(str(typescript_receipt.get("source_root", "")))
    typescript_records = typescript_receipt.get("files")
    if (
        typescript_capture_relative != TYPESCRIPT_CAPTURED_ROOT_RELATIVE
        or typescript_source_root.is_symlink()
        or not typescript_source_root.is_dir()
        or not isinstance(typescript_records, list)
        or len(typescript_records) != typescript_receipt.get("file_count")
        or typescript_receipt.get("file_count") != 108
        or typescript_receipt.get("bytes") != 19_067_381
        or typescript_receipt.get("source_manifest_sha256")
        != "61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
        or typescript_receipt.get("runtime_manifest_sha256")
        != "2157e43e757e433c733e144df7409a54f5040faa22af4a9b13de977a663fd939"
        or typescript_receipt.get("compiler_closure_sha256")
        != "aaab28fada5888d767a49f86d40e5a0c9073b23412257ccb3755e9c8fb8080d9"
        or typescript_receipt.get("semantic_soundness") != "NOT_RUN"
    ):
        raise RuntimeError("FORMAL_ENGINE_TYPESCRIPT_CAPTURE_RECEIPT_INVALID")
    typescript_sources: list[tuple[str, Path]] = []
    stable_typescript_records: list[dict[str, Any]] = []
    for index, record in enumerate(typescript_records):
        if not isinstance(record, dict) or set(record) != {
            "path",
            "source_path",
            "sha256",
            "bytes",
            "mode",
        }:
            raise RuntimeError(
                f"FORMAL_ENGINE_TYPESCRIPT_CAPTURE_RECORD_INVALID:{index}"
            )
        relative = record.get("path")
        source_value = record.get("source_path")
        expected_bytes = record.get("bytes")
        expected_sha256 = record.get("sha256")
        expected_mode = record.get("mode")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in Path(relative).parts)
            or not isinstance(source_value, str)
            or not Path(source_value).is_absolute()
            or not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes <= 0
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or not isinstance(expected_mode, str)
            or expected_mode not in {"0444", "0555"}
        ):
            raise RuntimeError(
                f"FORMAL_ENGINE_TYPESCRIPT_CAPTURE_RECORD_INVALID:{index}"
            )
        source = Path(source_value)
        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(typescript_source_root.resolve(strict=True))
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            raise RuntimeError(
                f"FORMAL_ENGINE_TYPESCRIPT_CLOSURE_PATH_INVALID:{relative}"
            ) from exc
        if (
            source.is_symlink()
            or not resolved.is_file()
            or resolved.stat().st_size != expected_bytes
            or hashlib.sha256(resolved.read_bytes()).hexdigest() != expected_sha256
            or f"{stat.S_IMODE(resolved.stat().st_mode):04o}" != expected_mode
        ):
            raise RuntimeError(
                f"FORMAL_ENGINE_TYPESCRIPT_CLOSURE_IDENTITY_DRIFT:{relative}"
            )
        capture_path = f"{typescript_capture_relative}/{relative}"
        typescript_sources.append((capture_path, source))
        stable_typescript_records.append(
            {
                "path": relative,
                "sha256": expected_sha256,
                "bytes": expected_bytes,
                "mode": expected_mode,
            }
        )
    if stable_typescript_records != sorted(
        stable_typescript_records, key=lambda item: str(item["path"])
    ):
        raise RuntimeError("FORMAL_ENGINE_TYPESCRIPT_CAPTURE_ORDER_INVALID")
    sources = [
        engine_module_root / name
        for name in (
            "__init__.py",
            "canonical.py",
            "clang_analyzer.py",
            "dart_analyzer.py",
            "emitter.py",
            "engine.py",
            "equivalence.py",
            "flutter_repository.py",
            "identifier_hygiene.py",
            "kotlin_repository.py",
            "models.py",
            "native.py",
            "python_analyzer.py",
            "react_analyzer.py",
            "react_repository.py",
            "repository.py",
            "source_analyzer.py",
            "toolchains.py",
            "types.py",
            "validation.py",
        )
    ]
    sources.extend(repo / relative for relative in CSHARP_ANALYZER_CAPTURE_INPUTS)
    for native_root in (
        engine / "native" / "csharp",
        engine / "native" / "go",
        engine / "native" / "java",
        engine / "native" / "javascript",
        engine / "native" / "rust",
        engine / "native" / "swift",
        engine / "native" / "typescript",
    ):
        controlled_full_tree = native_root.name in CONTROLLED_NATIVE_FULL_TREES
        native_entries = tuple(native_root.rglob("*"))
        unsafe_links = [
            path
            for path in native_entries
            if path.is_symlink()
            and not any(
                part in EXCLUDED_REBUILDABLE_DIRECTORIES
                for part in path.relative_to(native_root).parts
            )
        ]
        if unsafe_links:
            raise RuntimeError(
                "FORMAL_ENGINE_NATIVE_SOURCE_SYMLINK_FORBIDDEN:"
                + ",".join(
                    path.relative_to(repo).as_posix() for path in sorted(unsafe_links)
                )
            )
        sources.extend(
            path
            for path in native_entries
            if path.is_file()
            and not any(
                part in EXCLUDED_REBUILDABLE_DIRECTORIES
                for part in path.relative_to(native_root).parts
            )
            and (
                controlled_full_tree
                or path.name == "Package.resolved"
                or path.suffix.lower()
                in {
                    ".cs",
                    ".csproj",
                    ".go",
                    ".java",
                    ".js",
                    ".json",
                    ".lock",
                    ".mjs",
                    ".rs",
                    ".swift",
                    ".toml",
                    ".txt",
                }
            )
        )
    sources.extend(
        [
            engine / "pyproject.toml",
            engine / "uv.lock",
            repo / "schemas" / "batch29" / "formal-equivalence-evidence.schema.json",
            repo / "schemas" / "batch29" / "formal-input.schema.json",
            repo / "schemas" / "batch29" / "formal-input-module-function.schema.json",
            repo / "schemas" / "batch29" / "identifier-plan.schema.json",
            repo / "schemas" / "batch29" / "module-case-manifest.schema.json",
            repo / "schemas" / "batch29" / "module-equivalence-evidence.schema.json",
            repo / "schemas" / "batch29" / "route-certification.schema.json",
            repo / "scripts" / "batch29" / "run_polyglot_routes.py",
            repo / "scripts" / "batch29" / "fresh_route_runtime.py",
            repo / "scripts" / "batch29" / "route_sets.py",
            repo / "scripts" / "batch29" / "run_route_gate.py",
            repo / "scripts" / "batch29" / "validate_route.py",
            repo / "scripts" / "operations" / "validate_translation_route_matrix.py",
        ]
    )
    runtime_source_receipts = {
        "python_source_archive": {
            key: python_receipt[key]
            for key in (
                "schema_version",
                "capture_relative_path",
                "sha256",
                "bytes",
                "mode",
                "uid",
                "gid",
                "nlink",
                "source_tree_sha256",
                "source_tree_record_count",
                "source_tree_file_count",
                "source_tree_bytes",
            )
        },
        "typescript_compiler_closure": {
            "schema_version": typescript_receipt["schema_version"],
            "capture_relative_path": typescript_capture_relative,
            "source_manifest_sha256": typescript_receipt[
                "source_manifest_sha256"
            ],
            "runtime_manifest_sha256": typescript_receipt[
                "runtime_manifest_sha256"
            ],
            "compiler_closure_sha256": typescript_receipt[
                "compiler_closure_sha256"
            ],
            "file_count": typescript_receipt["file_count"],
            "bytes": typescript_receipt["bytes"],
            "files": stable_typescript_records,
            "semantic_soundness": typescript_receipt["semantic_soundness"],
        },
    }
    capture_parent = route / "certification" / "formal-artifacts"
    capture_parent.mkdir(parents=True, exist_ok=True)
    capture_root = capture_parent / "engine-sources"
    backup_root = capture_parent / ".engine-sources.previous"
    if backup_root.exists() and not capture_root.exists():
        backup_root.rename(capture_root)
    elif backup_root.exists():
        shutil.rmtree(backup_root)
    staging_parent = Path(
        tempfile.mkdtemp(prefix=".engine-sources-staging-", dir=capture_parent)
    )
    staging_root = staging_parent / "engine-sources"
    captured: list[Path] = []
    entries: list[dict[str, Any]] = []
    try:
        source_paths = {
            source.relative_to(repo).as_posix(): source for source in set(sources)
        }
        if python_capture_relative in source_paths:
            raise RuntimeError("FORMAL_ENGINE_RUNTIME_SOURCE_PATH_CONFLICT")
        source_paths[python_capture_relative] = python_source_path
        for relative, source in typescript_sources:
            if relative in source_paths:
                raise RuntimeError("FORMAL_ENGINE_RUNTIME_SOURCE_PATH_CONFLICT")
            source_paths[relative] = source

        typescript_expected = {
            f"{typescript_capture_relative}/{record['path']}": record
            for record in stable_typescript_records
        }
        source_specifications: dict[str, dict[str, Any]] = {}
        for relative_value, source in sorted(source_paths.items()):
            sealed = _sealed_source_identity(source, label=relative_value)
            if relative_value == python_capture_relative:
                if (
                    sealed["sha256"] != f"sha256:{python_sha256}"
                    or sealed["bytes"] != python_bytes
                    or sealed["mode"] != python_receipt.get("mode")
                ):
                    raise RuntimeError(
                        "FORMAL_ENGINE_PYTHON_SOURCE_ARCHIVE_SEAL_MISMATCH"
                    )
            elif relative_value in typescript_expected:
                expected = typescript_expected[relative_value]
                if (
                    sealed["sha256"] != f"sha256:{expected['sha256']}"
                    or sealed["bytes"] != expected["bytes"]
                    or sealed["mode"] != expected["mode"]
                ):
                    raise RuntimeError(
                        "FORMAL_ENGINE_TYPESCRIPT_SOURCE_SEAL_MISMATCH:"
                        + relative_value
                    )
            source_specifications[relative_value] = sealed

        for relative_value, sealed in source_specifications.items():
            _assert_sealed_source_identity(sealed, label=relative_value)
            source = Path(sealed["source"])
            relative = Path(relative_value)
            staged = staging_root / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged)
            if (
                sha256_file(staged) != sealed["sha256"]
                or staged.stat().st_size != sealed["bytes"]
                or f"{stat.S_IMODE(staged.stat().st_mode):04o}" != sealed["mode"]
            ):
                raise RuntimeError(
                    f"FORMAL_ENGINE_SOURCE_COPY_MISMATCH:{relative.as_posix()}"
                )
            _assert_sealed_source_identity(sealed, label=relative_value)
            final_destination = capture_root / relative
            entries.append(
                {
                    "repository_path": relative.as_posix(),
                    "captured_path": final_destination.relative_to(route).as_posix(),
                    "sha256": sealed["sha256"],
                    "bytes": sealed["bytes"],
                }
            )
        for relative_value, sealed in source_specifications.items():
            _assert_sealed_source_identity(sealed, label=relative_value)
        if python_source_archive_receipt() != python_receipt:
            raise RuntimeError("FORMAL_ENGINE_PYTHON_RECEIPT_CHANGED_DURING_CAPTURE")
        if typescript_compiler_capture_receipt() != typescript_receipt:
            raise RuntimeError(
                "FORMAL_ENGINE_TYPESCRIPT_RECEIPT_CHANGED_DURING_CAPTURE"
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
            "runtime_source_receipts": runtime_source_receipts,
        },
    )
    return manifest, captured


def build_formal_equivalence_evidence(
    repo: Path,
    route: Path,
    source: Language,
    target: Language,
    reports: dict[str, dict[str, Any]],
    swift_analyzer_receipt_path: Path | None,
) -> dict[str, str | int]:
    """Compose strict, byte-bound route evidence from three successful runs.

    The per-artifact theorem compares the two normalized L0 denotations.  The
    route-level claim remains ``PROVED_UNDER_ASSUMPTIONS`` because compiler
    frontend/analyzer and emitter soundness are recorded assumptions rather
    than independently checked proof certificates.
    """

    route_key = f"{source}-to-{target}"
    assert_route_mutation_allowed(route, source, target)
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
        identifier_hygiene = report.get("identifier_hygiene")
        if (
            not isinstance(identifier_hygiene, dict)
            or identifier_hygiene.get("status") != "PASSED"
        ):
            raise RuntimeError(
                f"FORMAL_IDENTIFIER_HYGIENE_NOT_PASSED:{route_key}:{corpus}"
            )
        identifier_plan = _corpus_artifact(
            route,
            corpus,
            identifier_hygiene.get("plan_path"),
            "IDENTIFIER_PLAN",
        )
        raw_target_ir = _corpus_artifact(
            route,
            corpus,
            (
                identifier_hygiene.get("raw_target_relift", {}).get("path")
                if isinstance(identifier_hygiene.get("raw_target_relift"), dict)
                else None
            ),
            "RAW_TARGET_IR",
        )
        normalized_target_ir = _corpus_artifact(
            route,
            corpus,
            (
                identifier_hygiene.get("normalized_target_ir", {}).get("path")
                if isinstance(identifier_hygiene.get("normalized_target_ir"), dict)
                else None
            ),
            "NORMALIZED_TARGET_IR",
        )
        if normalized_target_ir != target_ir:
            raise RuntimeError(
                f"FORMAL_NORMALIZED_TARGET_IR_DETACHED:{route_key}:{corpus}"
            )
        for label, path, declared_digest in (
            (
                "IDENTIFIER_PLAN",
                identifier_plan,
                identifier_hygiene.get("plan_sha256"),
            ),
            (
                "RAW_TARGET_IR",
                raw_target_ir,
                identifier_hygiene.get("raw_target_relift", {}).get("sha256")
                if isinstance(identifier_hygiene.get("raw_target_relift"), dict)
                else None,
            ),
            (
                "NORMALIZED_TARGET_IR",
                normalized_target_ir,
                identifier_hygiene.get("normalized_target_ir", {}).get("sha256")
                if isinstance(identifier_hygiene.get("normalized_target_ir"), dict)
                else None,
            ),
        ):
            if declared_digest != sha256_file(path):
                raise RuntimeError(
                    f"FORMAL_{label}_DIGEST_MISMATCH:{route_key}:{corpus}"
                )
        source_functions = _normalized_functions(source_ir, "SOURCE")
        target_functions = _normalized_functions(target_ir, "TARGET")
        if source_functions != target_functions:
            raise RuntimeError(f"FORMAL_NORMALIZED_IR_MISMATCH:{route_key}:{corpus}")
        normalized_runs.append({"corpus": corpus, "functions": source_functions})
        bind(source_ir, "source-ir")
        bind(identifier_plan, "identifier-plan")
        bind(raw_target_ir, "raw-target-ir")
        bind(normalized_target_ir, "normalized-target-ir")

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

    if "swift" in {source, target}:
        if swift_analyzer_receipt_path is None:
            raise RuntimeError(f"SWIFT_ANALYZER_BUILD_RECEIPT_MISSING:{route_key}")
        bind(swift_analyzer_receipt_path, "swift-analyzer-build-receipt")
    elif swift_analyzer_receipt_path is not None:
        raise RuntimeError(f"SWIFT_ANALYZER_BUILD_RECEIPT_UNEXPECTED:{route_key}")

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
    evidence: dict[str, Any] = {
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


def module_out_of_domain_behavior(route_key: str) -> str:
    if route_key in SPECIALIZED_ROUTE_KEYS:
        return SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
    if route_key in NODEJS_EXACT_ROUTE_KEYS:
        return NODEJS_OUT_OF_DOMAIN_BEHAVIOR
    raise RuntimeError(f"MODULE_PROFILE_ROUTE_UNDECLARED:{route_key}")


def write_module_not_run_evidence(
    route: Path, source: Language, target: Language, reason: str
) -> dict[str, str | int]:
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
                "source_profile_symbols": [],
                "target_profile_symbols": [],
                "target_helper_symbols": [],
                "verified_language_prelude": {"status": "NOT_RUN"},
                "verified_language_wrapper": {"status": "NOT_RUN"},
                "manifest_symbols": [],
                "exact_profile_symbol_set": False,
                "exact_generated_helper_symbol_set": False,
                "exact_profile_signature_set": False,
                "whole_file_closure_sha256": None,
                "independence": {"status": "NOT_RUN"},
            },
            "functions": [],
            "composition": {
                "rule": "per-function-denotation-plus-module-composition",
                "input_domain": declared_input_domain(f"{source}-to-{target}"),
                "out_of_domain_arithmetic_behavior": module_out_of_domain_behavior(
                    f"{source}-to-{target}"
                ),
                "function_count": 0,
                "passed_function_count": 0,
                "status": "NOT_RUN",
                "proof_strength": "NONE",
                "original_source_bytes_theorem": False,
                "source_compiler_runtime_soundness": "NOT_RUN",
                "target_compiler_runtime_soundness": "NOT_RUN",
                "analyzer_and_emitter_soundness": "NOT_RUN",
                "source_user_call_graph": "NOT_RUN",
                "target_call_graph": "NOT_RUN",
                "target_profile_to_emitted_call_graph_status": "NOT_RUN",
                "target_profile_to_emitted_call_graph_scope": "NOT_RUN",
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

SPECIALIZED_NEGATIVE_SOURCES: dict[
    str, tuple[Language, str, str, str, tuple[str, ...]]
] = {
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
        ("CPP_UNSUPPORTED_TYPE:unsigned long long",),
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

NODEJS_NEGATIVE_ANALYZE_SOURCES: dict[
    str,
    tuple[str, str, str, frozenset[str]],
] = {
    "nodejs-ambiguous-jsdoc-type-unsupported": (
        "ambiguous_jsdoc_type.mjs",
        "ambiguousType",
        "/**\n * @param {Number} value\n * @returns {number}\n */\n"
        "export function ambiguousType(value) { return value; }\n",
        frozenset({"JAVASCRIPT_EXACT_JSDOC_TYPE_REQUIRED"}),
    ),
    "nodejs-async-function-unsupported": (
        "async_function.mjs",
        "asyncValue",
        "/**\n * @param {integer} value\n * @returns {integer}\n */\n"
        "export async function asyncValue(value) { return value; }\n",
        frozenset({"JAVASCRIPT_ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET"}),
    ),
    "nodejs-coercive-equality-unsupported": (
        "coercive_equality.mjs",
        "coerciveEqual",
        "/**\n * @param {string} left\n * @param {string} right\n * @returns {boolean}\n */\n"
        "export function coerciveEqual(left, right) { return left == right; }\n",
        frozenset({"JAVASCRIPT_OPERATOR_UNSUPPORTED"}),
    ),
    "nodejs-dynamic-eval-unsupported": (
        "dynamic_eval.mjs",
        "dynamicEval",
        "/**\n * @param {string} value\n * @returns {string}\n */\n"
        "export function dynamicEval(value) { return eval(value); }\n",
        frozenset({"JAVASCRIPT_EXPRESSION_UNSUPPORTED"}),
    ),
    "nodejs-generator-function-unsupported": (
        "generator_function.mjs",
        "generateValue",
        "/**\n * @param {integer} value\n * @returns {integer}\n */\n"
        "export function* generateValue(value) { return value; }\n",
        frozenset({"JAVASCRIPT_FUNCTION_SHAPE_UNSUPPORTED"}),
    ),
    "nodejs-import-unsupported": (
        "module_import.mjs",
        "importedValue",
        "import fs from 'node:fs';\n"
        "/**\n * @param {integer} value\n * @returns {integer}\n */\n"
        "export function importedValue(value) { return value; }\n",
        frozenset({"JAVASCRIPT_MODULE_IMPORT_EXPORT_OUTSIDE_CERTIFIED_SUBSET"}),
    ),
    "nodejs-missing-jsdoc-unsupported": (
        "missing_jsdoc.mjs",
        "missingJsdoc",
        "export function missingJsdoc(value) { return value; }\n",
        frozenset({"JAVASCRIPT_EXACT_JSDOC_TAG_SET_REQUIRED"}),
    ),
    "nodejs-promise-timer-unsupported": (
        "promise_timer.mjs",
        "scheduleValue",
        "/**\n * @param {integer} value\n * @returns {integer}\n */\n"
        "export function scheduleValue(value) { return setTimeout(value, 0); }\n",
        frozenset({"JAVASCRIPT_EXPRESSION_UNSUPPORTED"}),
    ),
    "nodejs-this-prototype-unsupported": (
        "this_prototype.mjs",
        "prototypeValue",
        "/**\n * @param {integer} value\n * @returns {integer}\n */\n"
        "export function prototypeValue(value) { return this.value; }\n",
        frozenset({"JAVASCRIPT_EXPRESSION_UNSUPPORTED"}),
    ),
    "nodejs-top-level-side-effect-unsupported": (
        "top_level_side_effect.mjs",
        "topLevelValue",
        "console.log('side effect');\n"
        "/**\n * @param {integer} value\n * @returns {integer}\n */\n"
        "export function topLevelValue(value) { return value; }\n",
        frozenset({"JAVASCRIPT_TOP_LEVEL_STATEMENT_OUTSIDE_CERTIFIED_SUBSET"}),
    ),
}

NODEJS_GENERATED_NEGATIVE_CASES: dict[str, dict[str, Any]] = {
    "nodejs-number-arithmetic-unsupported": {
        "stem": "node_number_arithmetic",
        "class_name": "NodeNumberArithmetic",
        "function_name": "addNumber",
        "parameters": (("left", "number"), ("right", "number")),
        "return_type": "number",
        "expression": "left + right",
        "cases": [{"args": [1.25, 2.5], "expected": 3.75}],
        "reason_code": "NODEJS_NUMBER_ARITHMETIC_UNSUPPORTED",
    },
    "nodejs-string-semantics-unsupported": {
        "stem": "node_string_semantics",
        "class_name": "NodeStringSemantics",
        "function_name": "echoString",
        "parameters": (("value", "string"),),
        "return_type": "string",
        "expression": "value",
        "cases": [{"args": ["node-esm"], "expected": "node-esm"}],
        "reason_code": "NODEJS_STRING_SEMANTICS_UNSUPPORTED",
    },
    "nodejs-unsafe-integer-intermediate-boolean-unsupported": {
        "stem": "node_unsafe_intermediate_boolean",
        "class_name": "NodeUnsafeIntermediateBoolean",
        "function_name": "positiveAfterAdd",
        "parameters": (("left", "integer"), ("right", "integer")),
        "return_type": "boolean",
        "expression": "left + right > 0",
        "cases": [{"args": [2**53 - 1, 1], "expected": True}],
        "reason_code": "NODEJS_CASE_UNSAFE_INTEGER_INTERMEDIATE_UNSUPPORTED",
    },
    "nodejs-unsafe-integer-intermediate-integer-unsupported": {
        "stem": "node_unsafe_intermediate_integer",
        "class_name": "NodeUnsafeIntermediateInteger",
        "function_name": "cancelAfterAdd",
        "parameters": (("left", "integer"), ("right", "integer")),
        "return_type": "integer",
        "expression": "(left + right) - right",
        "cases": [{"args": [1, 2**53 - 1], "expected": 1}],
        "reason_code": "NODEJS_CASE_UNSAFE_INTEGER_INTERMEDIATE_UNSUPPORTED",
    },
    "nodejs-unsafe-integer-intermediate-number-unsupported": {
        "stem": "node_unsafe_intermediate_number",
        "class_name": "NodeUnsafeIntermediateNumber",
        "function_name": "chooseAfterAdd",
        "parameters": (
            ("left", "integer"),
            ("right", "integer"),
            ("positive", "number"),
            ("negative", "number"),
        ),
        "return_type": "number",
        "condition": "left + right > 0",
        "positive": "positive",
        "negative": "negative",
        "cases": [
            {"args": [2**53 - 1, 1, 1.5, -1.5], "expected": 1.5}
        ],
        "reason_code": "NODEJS_CASE_UNSAFE_INTEGER_INTERMEDIATE_UNSUPPORTED",
    },
    "nodejs-division-by-zero-unsupported": {
        "stem": "node_divide_by_zero",
        "class_name": "NodeDivideByZero",
        "function_name": "divide",
        "parameters": (("left", "integer"), ("right", "integer")),
        "return_type": "integer",
        "expression": "left / right",
        "cases": [{"args": [7, 0], "expected": 0}],
        "reason_code": "NODEJS_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN",
        "canonical_error": "DivideByZero",
    },
    "nodejs-modulo-by-zero-unsupported": {
        "stem": "node_modulo_by_zero",
        "class_name": "NodeModuloByZero",
        "function_name": "remainder",
        "parameters": (("left", "integer"), ("right", "integer")),
        "return_type": "integer",
        "expression": "left % right",
        "cases": [{"args": [7, 0], "expected": 0}],
        "reason_code": "NODEJS_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN",
        "canonical_error": "DivideByZero",
    },
    "nodejs-integer-overflow-unsupported": {
        "stem": "node_integer_overflow",
        "class_name": "NodeIntegerOverflow",
        "function_name": "multiply",
        "parameters": (("left", "integer"), ("right", "integer")),
        "return_type": "integer",
        "expression": "left * right",
        "cases": [{"args": [2**27, 2**36], "expected": 0}],
        "reason_code": "NODEJS_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN",
        "canonical_error": "IntegerOverflow",
    },
}


def _nodejs_negative_type(language: Language, canonical_type: str) -> str:
    return {
        "java": {
            "integer": "long",
            "number": "double",
            "boolean": "boolean",
            "string": "String",
        },
        "python": {
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "string": "str",
        },
        "csharp": {
            "integer": "long",
            "number": "double",
            "boolean": "bool",
            "string": "string",
        },
        "typescript": {
            "integer": "number",
            "number": "number",
            "boolean": "boolean",
            "string": "string",
        },
        "javascript": {
            "integer": "integer",
            "number": "number",
            "boolean": "boolean",
            "string": "string",
        },
        "go": {
            "integer": "int64",
            "number": "float64",
            "boolean": "bool",
            "string": "string",
        },
        "rust": {
            "integer": "i64",
            "number": "f64",
            "boolean": "bool",
            "string": "String",
        },
        "cpp": {
            "integer": "std::int64_t",
            "number": "double",
            "boolean": "bool",
            "string": "std::string",
        },
        "objc": {
            "integer": "long long",
            "number": "double",
            "boolean": "BOOL",
            "string": "NSString *",
        },
        "swift": {
            "integer": "Int64",
            "number": "Double",
            "boolean": "Bool",
            "string": "String",
        },
    }[language][canonical_type]


def nodejs_generated_negative_source(
    language: Language,
    case_id: str,
) -> tuple[str, str, str, list[dict[str, Any]]]:
    """Build one exact native source used to exercise a Node domain boundary."""

    spec = NODEJS_GENERATED_NEGATIVE_CASES[case_id]
    function_name = str(spec["function_name"])
    parameters = tuple(spec["parameters"])
    return_type = str(spec["return_type"])
    typed_parameters = [
        (name, _nodejs_negative_type(language, canonical_type))
        for name, canonical_type in parameters
    ]
    rendered_return = _nodejs_negative_type(language, return_type)
    expression = spec.get("expression")
    condition = spec.get("condition")
    if expression is None and condition is None:
        raise RuntimeError(f"NODEJS_NEGATIVE_SOURCE_SPEC_INVALID:{case_id}")

    if language == "python":
        signature = ", ".join(f"{name}: {value_type}" for name, value_type in typed_parameters)
        body = (
            f"    return {expression}\n"
            if expression is not None
            else f"    if {condition}:\n        return {spec['positive']}\n"
            f"    return {spec['negative']}\n"
        )
        content = f"def {function_name}({signature}) -> {rendered_return}:\n{body}"
    elif language == "javascript":
        jsdoc = ["/**"]
        jsdoc.extend(
            f" * @param {{{canonical_type}}} {name}"
            for name, canonical_type in parameters
        )
        jsdoc.extend((f" * @returns {{{return_type}}}", " */"))
        signature = ", ".join(name for name, _ in parameters)
        body = (
            f"  return {expression};\n"
            if expression is not None
            else f"  if ({condition}) {{ return {spec['positive']}; }}\n"
            f"  return {spec['negative']};\n"
        )
        content = (
            "\n".join(jsdoc)
            + f"\nexport function {function_name}({signature}) {{\n{body}}}\n"
        )
    elif language == "typescript":
        signature = ", ".join(f"{name}: {value_type}" for name, value_type in typed_parameters)
        body = (
            f"  return {expression};\n"
            if expression is not None
            else f"  if ({condition}) {{ return {spec['positive']}; }}\n"
            f"  return {spec['negative']};\n"
        )
        content = (
            f"export function {function_name}({signature}): {rendered_return} {{\n{body}}}\n"
        )
    elif language == "go":
        signature = ", ".join(f"{name} {value_type}" for name, value_type in typed_parameters)
        body = (
            f"\treturn {expression}\n"
            if expression is not None
            else f"\tif {condition} {{ return {spec['positive']} }}\n"
            f"\treturn {spec['negative']}\n"
        )
        content = f"package negative\n\nfunc {function_name}({signature}) {rendered_return} {{\n{body}}}\n"
    elif language == "rust":
        signature = ", ".join(f"{name}: {value_type}" for name, value_type in typed_parameters)
        body = (
            f"    {expression}\n"
            if expression is not None
            else f"    if {condition} {{ return {spec['positive']}; }}\n"
            f"    {spec['negative']}\n"
        )
        content = f"fn {function_name}({signature}) -> {rendered_return} {{\n{body}}}\n"
    elif language == "swift":
        signature = ", ".join(f"_ {name}: {value_type}" for name, value_type in typed_parameters)
        body = (
            f"    return {expression}\n"
            if expression is not None
            else f"    if {condition} {{ return {spec['positive']} }}\n"
            f"    return {spec['negative']}\n"
        )
        content = f"func {function_name}({signature}) -> {rendered_return} {{\n{body}}}\n"
    else:
        signature = ", ".join(f"{value_type} {name}" for name, value_type in typed_parameters)
        body = (
            f"    return {expression};\n"
            if expression is not None
            else f"    if ({condition}) {{ return {spec['positive']}; }}\n"
            f"    return {spec['negative']};\n"
        )
        declaration = f"{rendered_return} {function_name}({signature}) {{\n{body}}}\n"
        if language == "java":
            class_name = str(spec["class_name"])
            content = (
                f"public final class {class_name} {{\n"
                f"    public static {declaration.replace(chr(10), chr(10) + '    ').rstrip()}\n"
                "}\n"
            )
        elif language == "csharp":
            class_name = str(spec["class_name"])
            content = (
                f"public static class {class_name}\n{{\n"
                f"    public static {declaration.replace(chr(10), chr(10) + '    ').rstrip()}\n"
                "}\n"
            )
        elif language == "cpp":
            includes = "#include <cstdint>\n"
            if return_type == "string" or any(
                canonical_type == "string" for _, canonical_type in parameters
            ):
                includes += "#include <string>\n"
            content = includes + "\n" + declaration
        elif language == "objc":
            content = "#import <Foundation/Foundation.h>\n\n" + declaration
        else:
            raise RuntimeError(f"NODEJS_NEGATIVE_SOURCE_LANGUAGE_INVALID:{language}")

    filename = (
        f"{spec['class_name']}.java"
        if language == "java"
        else f"{spec['stem']}.{EXTENSIONS[language]}"
    )
    return filename, function_name, content, list(spec["cases"])


def write_not_run_route_scaffold(
    route: Path, source: Language, target: Language
) -> None:
    """Create a complete, non-passing route record before native execution."""

    route_key = f"{source}-to-{target}"
    assert_route_mutation_allowed(route, source, target)
    specialized = route_key in SPECIALIZED_ROUTE_KEYS
    nodejs = route_key in NODEJS_EXACT_ROUTE_KEYS
    module_required = route_key in MODULE_EQUIVALENCE_ROUTE_KEYS
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
    if nodejs:
        negative_ids = list(nodejs_negative_case_ids(source, target))
    else:
        negative_ids = sorted(
            {
                *(
                    {
                        *SPECIALIZED_NEGATIVE_CASES.get(source, ()),
                        *SPECIALIZED_NEGATIVE_CASES.get(target, ()),
                        "specialized-non-finite-case-unsupported",
                        "specialized-number-arithmetic-unsupported",
                        "specialized-overflow-outside-no-error-domain",
                        "specialized-string-semantics-unsupported",
                    }
                    if specialized
                    else set()
                ),
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
        "notes": [
            "No local route or module behavior is claimed before native execution.",
            "Independent, external, customer, and production evidence remain NOT_RUN.",
        ],
    }
    module_ref: dict[str, object] | None = None
    if module_required:
        module_ref = write_module_not_run_evidence(
            route,
            source,
            target,
            "Native three-function module verification has not run.",
        )
        evidence["module_execution_status"] = "NOT_RUN"
        evidence["module_equivalence"] = module_ref
    write_json(route / "certification" / "evidence.json", evidence)
    evidence_refs: list[Any] = [*run_refs, negative_relative]
    gate_results: dict[str, str] = {
        "local_execution": "NOT_RUN",
        "external_execution": "NOT_RUN",
        "independent_verification": "NOT_RUN",
    }
    if module_required and module_ref is not None:
        evidence_refs.append(str(module_ref["path"]))
        gate_results["module_execution"] = "NOT_RUN"
    certification: dict[str, Any] = {
        "schema_version": 1,
        "route_key": route_key,
        "route_version": "1.0.0",
        "status": "limited",
        "certification_decision": "NOT_CERTIFIED",
        "declared_scope": (
            "typed-pure-function-v1+typed-pure-module-v1"
            if module_required
            else "typed-pure-function-v1"
        ),
        "issued_at": NOT_RUN_PREPARED_AT,
        "next_review_at": "2026-11-09T00:00:00+00:00",
        "metrics": evidence["metrics"],
        "evidence_refs": evidence_refs,
        "gate_results": gate_results,
    }
    if module_required and module_ref is not None:
        certification["module_equivalence"] = module_ref
    write_json(route / "certification" / "certification.json", certification)


def parse_route_key(value: str) -> tuple[Language, Language]:
    try:
        source, target = split_executable_route_key(value)
    except ValueError as error:
        reason = str(error)
        if reason.startswith("V3_ROUTE_RESEARCH_NOT_EXECUTABLE:"):
            raise argparse.ArgumentTypeError(reason) from None
        if reason.startswith(
            "LEGACY_ROUTE_IMMUTABLE_REEXECUTION_REQUIRES_NEW_PACK_VERSION:"
        ):
            raise argparse.ArgumentTypeError(reason) from None
        choices = ", ".join(EXECUTABLE_DIRECT_ROUTE_KEYS)
        raise argparse.ArgumentTypeError(
            f"route must be one exact executable mutable directed key: {choices}"
        ) from None
    return source, target  # type: ignore[return-value]


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
    if route_key not in EVIDENCED_ROUTE_KEYS:
        raise RuntimeError(f"UNDECLARED_DIRECTED_ROUTE:{route_key}")
    if route_key in V3_EXACT_ROUTE_KEYS:
        # Kotlin/React/Flutter directions remain an explicit research
        # partition. Their analyzers, emitters and repository surfaces are
        # locally executable, but the 66 route packs have no route-specific
        # native campaign. Reusing the limited-route writer here would
        # silently promote every prepared V3 scaffold to `limited`.
        raise RuntimeError(f"V3_ROUTE_RESEARCH_PACK_REQUIRES_CAMPAIGN:{route_key}")
    specialized = route_key in SPECIALIZED_ROUTE_KEYS
    nodejs = route_key in NODEJS_EXACT_ROUTE_KEYS
    module_required = route_key in MODULE_EQUIVALENCE_ROUTE_KEYS
    strict_module_profile = specialized or nodejs
    nodejs_types = nodejs_route_types(source, target)
    nodejs_typescript = nodejs and is_nodejs_typescript_route(source, target)
    input_domain = declared_input_domain(route_key)
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
            "module_profile": "typed-pure-module-v1"
            if module_required
            else "NOT_APPLICABLE",
            "target_profile": f"{target}-native-compiler",
            "input_domain": input_domain,
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
            "module_equivalence_required": module_required,
            "minimum_module_functions": 3,
            "concrete_spans_required": module_required,
            "canonical_finite_no_error_input_domain_required": specialized,
            "specialized_string_semantics_allowed": False if specialized else True,
            "nodejs_safe_integer_finite_domain_required": nodejs,
            "nodejs_effects_async_io_allowed": False,
            "nodejs_typescript_integer_semantics_allowed": not nodejs_typescript,
        },
    }
    support = {
        "schema_version": 1,
        "route_key": route_key,
        "capabilities": [
            {
                "id": "typed-pure-function-v1",
                "status": "conditional" if strict_module_profile else "supported",
                "strategy": "compiler-backed-semantic-ir",
                "reason": (
                    "Conditionally supported only for integer, finite-number, and boolean functions "
                    "inside the canonical finite no-error input domain; string semantics and arithmetic-error "
                    "outcomes are blocked. Native analysis, target compilation, separate typed corpora, "
                    "and behavior replay must each pass before local execution may be raised; "
                    "independent/external verification remain NOT_RUN."
                    if specialized
                    else "Conditionally supported for the route's explicitly declared exact JSDoc/target "
                    "types inside the Node.js ES2022 ESM safe-integer/finite no-effect domain. "
                    "Native analysis, concrete chunks, target compilation, behavior replay, and module "
                    "composition must all pass; async, I/O, imports, dynamic evaluation, independent "
                    "verification, and external certification remain blocked or NOT_RUN."
                    if nodejs
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
                "status": "conditional" if strict_module_profile else "supported",
                "strategy": "exact-type-mapping",
                "reason": (
                    "Integer, finite IEEE-754 binary64 number, and boolean are mapped explicitly only "
                    "inside the canonical finite no-error input domain. String is not in the specialized profile."
                    if specialized
                    else "TypeScript has no explicit canonical integer annotation in this profile; "
                    "JavaScript/TypeScript is limited to finite binary64 transport/comparison, boolean, "
                    "and strict ECMAScript string equality/concatenation. Integer is blocked."
                    if nodejs_typescript
                    else "Integer is restricted to Number.isSafeInteger-compatible values; number is "
                    "restricted to finite binary64 and boolean is exact. Cross-language string semantics "
                    "are blocked pending a separate Unicode/code-unit corpus."
                    if nodejs
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
                else [
                    {
                        "id": "nodejs-es2022-esm-safe-integer-finite-v1",
                        "status": "conditional",
                        "strategy": "exact-jsdoc-types-and-runtime-domain-guards",
                        "reason": "Integer values must satisfy Number.isSafeInteger, number values must "
                        "be finite binary64, modules are ESM, and all effects are absent.",
                        "evidence_refs": [
                            "lowering/profile.json",
                            "certification/local-development-evidence.json",
                            "certification/local-holdout-evidence.json",
                            "certification/local-representative-evidence.json",
                        ],
                    },
                    {
                        "id": "string-semantics",
                        "status": "conditional" if nodejs_typescript else "blocked",
                        "strategy": (
                            "strict-ecmascript-string-value-contract"
                            if nodejs_typescript
                            else "separate-unicode-code-unit-contract-required"
                        ),
                        "reason": (
                            "JavaScript and TypeScript share the pinned ECMAScript string value, strict "
                            "equality, and concatenation model; the independent string corpus is still required."
                            if nodejs_typescript
                            else "The Node analyzer can represent strict equality and concatenation, but "
                            "cross-runtime Unicode/code-unit equivalence is not claimed by this route."
                        ),
                        "evidence_refs": (
                            [
                                "certification/local-holdout-evidence.json",
                                "certification/module-equivalence.json",
                            ]
                            if nodejs_typescript
                            else ["certification/local-negative-evidence.json"]
                        ),
                    },
                    {
                        "id": "number-arithmetic",
                        "status": "blocked",
                        "strategy": "separate-floating-point-arithmetic-contract-required",
                        "reason": "Finite inputs can still produce non-finite results and rounding differences; "
                        "the Node exact route profile currently permits transport/comparison only.",
                        "evidence_refs": [],
                    },
                ]
                if nodejs
                else []
            ),
            {
                "id": "if-return-control-flow",
                "status": "conditional" if nodejs else "supported",
                "strategy": "typed-structured-lowering",
                "reason": (
                    "If and return statements remain conditional on exact JSDoc types, the ESM closure, "
                    "concrete spans, and successful native replay for this direction."
                    if nodejs
                    else "If and return statements are lowered from compiler-backed syntax trees."
                ),
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
                "status": "conditional" if module_required else "blocked",
                "strategy": "per-function-proof-plus-module-composition",
                "reason": (
                    "Requires at least three independently observed functions, exact symbol/signature "
                    "closure, semantic chunks, behavior replay, and module composition evidence."
                    if module_required
                    else "This legacy route has not requested the separate module profile."
                ),
                "evidence_refs": (
                    ["certification/module-equivalence.json"] if module_required else []
                ),
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
                else {
                    "integer_arithmetic": (
                        {
                            "operators": [],
                            "blocked_operators": ["+", "-", "*", "/", "%"],
                            "status": "BLOCKED_NO_EXPLICIT_INTEGER_TYPE",
                        }
                        if nodejs_typescript
                        else {
                            "operators": ["+", "-", "*", "/", "%"],
                            "status": "conditional-js-safe-integer-no-error-domain",
                        }
                    ),
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
                    "string_value": {
                        "operators": ["+", "==", "!="] if nodejs_typescript else [],
                        "status": "conditional" if nodejs_typescript else "BLOCKED",
                    },
                }
                if nodejs
                else {"status": "legacy-profile-defined"}
            ),
            "input_domain": input_domain,
            "integer_semantics": (
                "BLOCK_NO_EXPLICIT_INTEGER_TYPE"
                if nodejs_typescript
                else "SAFE_INTEGER_CONDITIONAL"
                if nodejs
                else "PROFILE_DEFINED"
            ),
            "out_of_domain_arithmetic_behavior": (
                SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
                if specialized
                else NODEJS_OUT_OF_DOMAIN_BEHAVIOR
                if nodejs
                else "profile-specific"
            ),
            "concrete_spans_required": module_required,
            "string_semantics": (
                "STRICT_ECMASCRIPT_VALUE_EQUALITY_CONCAT"
                if nodejs_typescript
                else "BLOCKED"
                if strict_module_profile
                else "PROFILE_DEFINED"
            ),
            "effect_semantics": "BLOCKED_ASYNC_IO_IMPORT_EVAL"
            if nodejs
            else "PROFILE_DEFINED",
            "fail_closed": True,
        },
    )
    write_json(
        route / "mappings" / "types.json",
        {
            "schema_version": 1,
            "source": source,
            "target": target,
            "types": (
                nodejs_types
                if nodejs
                else ["integer", "number", "boolean"]
                if specialized
                else ["integer", "number", "boolean", "string"]
            ),
            "type_evidence_corpora": (
                {
                    "integer": "corpus/development",
                    "number": "corpus/holdout",
                    "boolean": "corpus/real-repository",
                }
                if specialized
                else (
                    {
                        "number": "corpus/development+corpus/module",
                        "string": "corpus/holdout+corpus/module",
                        "boolean": "corpus/real-repository+corpus/module",
                    }
                    if nodejs_typescript
                    else {
                        "integer": "corpus/development+corpus/module",
                        "number": "corpus/module",
                        "boolean": "corpus/module",
                    }
                )
                if nodejs
                else {}
            ),
            "input_domain": input_domain,
            "integer_semantics": (
                "BLOCK_NO_EXPLICIT_INTEGER_TYPE"
                if nodejs_typescript
                else "SAFE_INTEGER_CONDITIONAL"
                if nodejs
                else "PROFILE_DEFINED"
            ),
            "string_semantics": (
                "STRICT_ECMASCRIPT_VALUE_EQUALITY_CONCAT"
                if nodejs_typescript
                else "BLOCK"
                if strict_module_profile
                else "PROFILE_DEFINED"
            ),
            "out_of_domain_arithmetic_behavior": (
                SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
                if specialized
                else NODEJS_OUT_OF_DOMAIN_BEHAVIOR
                if nodejs
                else "profile-specific"
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
            else "- Keep integer inference blocked while preserving only the pinned strict ECMAScript "
            "string subset; keep non-finite numbers, async, I/O, imports, dynamic evaluation, "
            "reflection, shared state, and undeclared calls blocked.\n"
            if nodejs_typescript
            else "- Keep unsafe integers, non-finite numbers, string semantics, async, I/O, imports, "
            "dynamic evaluation, reflection, shared state, and undeclared calls blocked.\n"
            if nodejs
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
            else "The JavaScript/TypeScript route is conditional on "
            "nodejs-es2022-esm-safe-integer-finite-v1; finite-number, boolean, and the pinned strict "
            "ECMAScript string subset require concrete spans and module evidence. Integer inference, "
            "async, I/O, imports, dynamic evaluation, reflection, and state remain blocked. "
            if nodejs_typescript
            else "The Node.js routes are conditional on nodejs-es2022-esm-safe-integer-finite-v1; "
            "integer, finite-number, and boolean semantics require concrete spans and module evidence. "
            "String, async, I/O, imports, dynamic evaluation, reflection, and state remain blocked. "
            if nodejs
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


def assert_limited_route_execution_allowed(
    route_key: str, *, allow_immutable_core: bool = False
) -> None:
    """Reject routes without a bounded, route-specific executable campaign.

    V3 route manifests are synchronized as research scaffolds only.  Keeping
    this check at every mutation boundary prevents a caller from bypassing
    ``configure_route`` and writing LIMITED/PASSED evidence for those routes.
    """

    if route_key in V3_EXACT_ROUTE_KEYS:
        raise RuntimeError(f"V3_ROUTE_RESEARCH_PACK_REQUIRES_CAMPAIGN:{route_key}")
    if route_key not in EVIDENCED_ROUTE_KEYS:
        raise RuntimeError(f"INACTIVE_OR_UNDECLARED_ROUTE_EXECUTION:{route_key}")
    if route_key in CORE_ROUTE_KEYS and not allow_immutable_core:
        raise RuntimeError(
            f"LEGACY_ROUTE_IMMUTABLE_REEXECUTION_REQUIRES_NEW_PACK_VERSION:{route_key}"
        )


def assert_route_mutation_allowed(
    route: Path, source: Language, target: Language
) -> str:
    """Bind a direct mutation call to one active, mutable route directory."""

    route_key = f"{source}-to-{target}"
    if route.name != route_key:
        raise RuntimeError(
            f"ROUTE_MUTATION_PATH_BINDING_INVALID:{route.name}:{route_key}"
        )
    assert_limited_route_execution_allowed(route_key)
    try:
        metadata = route.lstat()
    except OSError as exc:
        raise RuntimeError(f"ROUTE_MUTATION_DIRECTORY_UNSAFE:{route_key}") from exc
    if route.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"ROUTE_MUTATION_DIRECTORY_UNSAFE:{route_key}")
    return route_key


def preflight_route_set_execution(route_keys: tuple[str, ...]) -> None:
    """Validate an entire execution selection before any route-side effects."""

    historical = sorted(set(route_keys) & set(DEPRECATED_ROUTE_KEYS))
    if historical:
        raise RuntimeError(
            "HISTORICAL_ROUTE_SET_READ_ONLY:" + ",".join(historical)
        )
    for route_key in route_keys:
        assert_limited_route_execution_allowed(
            route_key, allow_immutable_core=True
        )


def _preflight_route_directory(
    repo: Path, route_key: str, *, allow_missing: bool
) -> Path:
    """Validate one existing or prospective route tree without mutating it."""

    routes_root = repo / "routes"
    route = routes_root / route_key
    try:
        routes_metadata = routes_root.lstat()
        resolved_routes = routes_root.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"ROUTE_PREPARE_ROOT_UNSAFE:{route_key}") from exc
    if routes_root.is_symlink() or not stat.S_ISDIR(routes_metadata.st_mode):
        raise RuntimeError(f"ROUTE_PREPARE_ROOT_UNSAFE:{route_key}")
    try:
        route_metadata = route.lstat()
    except FileNotFoundError:
        if allow_missing:
            return route
        raise RuntimeError(f"ROUTE_PREPARE_DIRECTORY_MISSING:{route_key}") from None
    except OSError as exc:
        raise RuntimeError(f"ROUTE_PREPARE_DIRECTORY_UNSAFE:{route_key}") from exc
    try:
        resolved_route = route.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"ROUTE_PREPARE_DIRECTORY_UNSAFE:{route_key}") from exc
    if (
        route.is_symlink()
        or not stat.S_ISDIR(route_metadata.st_mode)
        or resolved_route.parent != resolved_routes
    ):
        raise RuntimeError(f"ROUTE_PREPARE_DIRECTORY_UNSAFE:{route_key}")
    for candidate in sorted(route.rglob("*")):
        try:
            metadata = candidate.lstat()
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(resolved_route)
        except (OSError, RuntimeError, ValueError) as exc:
            raise RuntimeError(f"ROUTE_PREPARE_TREE_UNSAFE:{route_key}") from exc
        if candidate.is_symlink() or not (
            stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)
        ):
            raise RuntimeError(f"ROUTE_PREPARE_TREE_UNSAFE:{route_key}")
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
            raise RuntimeError(f"ROUTE_PREPARE_TREE_UNSAFE:{route_key}")
    return route


def preflight_route_set_preparation(
    repo: Path, route_set_name: str, route_keys: tuple[str, ...]
) -> None:
    """Validate a complete prepare selection before its first route write."""

    if set(route_keys) & set(DEPRECATED_ROUTE_KEYS):
        raise RuntimeError(f"HISTORICAL_ROUTE_SET_READ_ONLY:{route_set_name}")
    if (
        not route_keys
        or len(route_keys) != len(set(route_keys))
        or set(route_keys) - set(EVIDENCED_ROUTE_KEYS)
    ):
        raise RuntimeError(f"ROUTE_SET_PREPARE_SELECTION_INVALID:{route_set_name}")
    for route_key in route_keys:
        if route_key in CORE_ROUTE_KEYS:
            continue
        _preflight_route_directory(repo, route_key, allow_missing=True)
        if route_key in V3_EXACT_ROUTE_KEYS:
            _v3_research_route_documents(repo, route_key)
        else:
            assert_limited_route_execution_allowed(route_key)


def verify_route_set_read_only(
    repo: Path,
    route_set_name: str,
    route_keys: tuple[str, ...],
) -> None:
    """Validate one immutable set without executing or rewriting a route."""

    if (
        not route_keys
        or len(route_keys) != len(set(route_keys))
        or set(route_keys) - set(ALL_DECLARED_ROUTE_KEYS)
    ):
        raise RuntimeError(f"ROUTE_SET_READ_ONLY_SELECTION_INVALID:{route_set_name}")
    routes_root = repo / "routes"
    for route_key in route_keys:
        route = _preflight_route_directory(repo, route_key, allow_missing=False)
        required_json = {
            "route": route / "route.json",
            "support": route / "support-matrix.json",
            "evidence": route / "certification" / "evidence.json",
            "certification": route / "certification" / "certification.json",
        }
        documents: dict[str, dict[str, Any]] = {}
        raw_support = b""
        for label, path in required_json.items():
            payload = _stable_regular_file_bytes(
                routes_root,
                path,
                label=f"ROUTE_SET_READ_ONLY_{label.upper()}:{route_key}",
            )
            try:
                raw = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"ROUTE_SET_READ_ONLY_DOCUMENT_INVALID:{route_key}:{label}"
                ) from exc
            if not isinstance(raw, dict) or raw.get("route_key") != route_key:
                raise RuntimeError(
                    f"ROUTE_SET_READ_ONLY_DOCUMENT_INVALID:{route_key}:{label}"
                )
            documents[label] = raw
            if label == "support":
                raw_support = payload
        route_version = documents["route"].get("version")
        if (
            documents["evidence"].get("route_version") != route_version
            or documents["certification"].get("route_version") != route_version
        ):
            raise RuntimeError(f"ROUTE_SET_READ_ONLY_VERSION_DRIFT:{route_key}")
        expected_markdown = support_matrix_markdown_bytes(
            route_key,
            raw_support,
            documents["support"],
        )
        observed_markdown = _stable_regular_file_bytes(
            routes_root,
            route / "certification" / "support-matrix.md",
            label=f"ROUTE_SET_READ_ONLY_SUPPORT_VIEW:{route_key}",
        )
        if observed_markdown != expected_markdown:
            raise RuntimeError(f"ROUTE_SUPPORT_MATRIX_VIEW_DRIFT:{route_key}")
        if route_key in V3_EXACT_ROUTE_KEYS and (
            documents["route"]
            != _v3_research_route_manifest(repo, route_key)[2]
            or documents["support"] != v3_research_support_document(route_key)
            or documents["evidence"]
            != v3_research_evidence_document(route_key)
            or documents["certification"]
            != v3_research_certification_document(route_key)
        ):
            raise RuntimeError(f"V3_ROUTE_CAMPAIGN_OVERCLAIM:{route_key}")


def _v3_research_route_manifest(
    repo: Path, route_key: str
) -> tuple[Path, Path, dict[str, Any]]:
    """Preflight and build one exact V3 research manifest in memory.

    This is metadata synchronization only. It deliberately leaves the
    semantic and target profiles empty and the status at ``research``: exact
    analyzer/emitter paths and versions prove that the declared components
    exist, not that this directed route has completed its own corpus, replay,
    independent verification or certification gate.
    """

    if route_key not in V3_EXACT_ROUTE_KEYS:
        raise RuntimeError(f"V3_ROUTE_KEY_REQUIRED:{route_key}")
    source, target = split_route_key(route_key)
    routes_root = repo / "routes"
    route = routes_root / route_key
    manifest_path = route / "route.json"
    try:
        resolved_routes = routes_root.resolve(strict=True)
        resolved_route = route.resolve(strict=True)
        manifest_bytes = _stable_regular_file_bytes(
            routes_root,
            manifest_path,
            label="V3_ROUTE_MANIFEST",
        )
    except (OSError, RuntimeError) as error:
        raise RuntimeError(f"V3_ROUTE_PACK_MISSING_OR_UNSAFE:{route_key}") from error
    if (
        routes_root.is_symlink()
        or route.is_symlink()
        or resolved_route.parent != resolved_routes
        or not resolved_route.is_dir()
    ):
        raise RuntimeError(f"V3_ROUTE_PACK_MISSING_OR_UNSAFE:{route_key}")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"V3_ROUTE_MANIFEST_INVALID:{route_key}") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("route_key") != route_key
        or manifest.get("version") != V3_RESEARCH_ROUTE_VERSION
    ):
        raise RuntimeError(f"V3_ROUTE_MANIFEST_INVALID:{route_key}")
    document: dict[str, Any] = {
        "schema_version": 1,
        "route_key": route_key,
        "version": V3_RESEARCH_ROUTE_VERSION,
        "status": "research",
        "owner": "ELMOS Migration Platform",
        "maintenance_owner": "ELMOS Polyglot Route Maintainers",
        "review_date": "2026-11-24",
        "source": {
            "language": source,
            "versions": list(VERSIONS[source]),
            "engine_path": ENGINE_PATHS[source],
        },
        "target": {
            "language": target,
            "versions": list(VERSIONS[target]),
            "engine_path": (
                "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py"
            ),
        },
        "profiles": {"semantic_profile": "", "target_profile": ""},
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
    return route, manifest_path, document


def _v3_research_route_documents(
    repo: Path, route_key: str
) -> tuple[Path, tuple[tuple[Path, dict[str, Any]], ...]]:
    """Build every machine-readable V3 document before any write."""

    route, manifest_path, manifest = _v3_research_route_manifest(repo, route_key)
    certification_root = route / "certification"
    return route, (
        (manifest_path, manifest),
        (route / "support-matrix.json", v3_research_support_document(route_key)),
        (
            certification_root / "evidence.json",
            v3_research_evidence_document(route_key),
        ),
        (
            certification_root / "certification.json",
            v3_research_certification_document(route_key),
        ),
    )


def _v3_research_route_transaction_documents(
    route: Path,
    documents: tuple[tuple[Path, dict[str, Any]], ...],
) -> tuple[tuple[Path, bytes], ...]:
    """Serialize one V3 contract and derive its support view from those bytes."""

    serialized = tuple((path, _json_bytes(document)) for path, document in documents)
    support_path = route / "support-matrix.json"
    support_matches = tuple(
        (content, document)
        for (path, document), (_, content) in zip(documents, serialized, strict=True)
        if path == support_path
    )
    if len(support_matches) != 1:
        raise RuntimeError(f"V3_SUPPORT_DOCUMENT_SELECTION_INVALID:{route.name}")
    support_bytes, support_document = support_matches[0]
    return serialized + (
        (
            route / "certification" / "support-matrix.md",
            support_matrix_markdown_bytes(
                route.name,
                support_bytes,
                support_document,
            ),
        ),
    )


def synchronize_v3_research_route_manifest(repo: Path, route_key: str) -> Path:
    """Bind one V3 route to the conservative metadata/evidence authority."""

    route, documents = _v3_research_route_documents(repo, route_key)
    _transactional_write_bytes(
        repo / "routes",
        _v3_research_route_transaction_documents(route, documents),
    )
    return route


def synchronize_v3_research_route_manifests(
    repo: Path, route_keys: tuple[str, ...] = V3_EXACT_ROUTE_KEYS
) -> tuple[Path, ...]:
    """Preflight then atomically synchronize the exact 66-key partition.

    All documents are constructed before the first write. A process-level
    write failure restores the exact original bytes; an abrupt host failure can
    expose only complete per-file replacements, never truncated JSON.
    """

    if (
        not route_keys
        or len(route_keys) != len(set(route_keys))
        or set(route_keys) - set(V3_EXACT_ROUTE_KEYS)
    ):
        raise RuntimeError("V3_ROUTE_SYNC_SELECTION_INVALID")
    prepared = tuple(
        _v3_research_route_documents(repo, route_key) for route_key in route_keys
    )
    documents = tuple(
        document
        for route, route_documents in prepared
        for document in _v3_research_route_transaction_documents(
            route, route_documents
        )
    )
    _transactional_write_bytes(repo / "routes", documents)
    return tuple(route for route, _ in prepared)


def populate_corpus(route: Path, fixtures: Path, source: Language) -> None:
    direction = route.name.split("-to-")
    if len(direction) != 2 or not all(direction):
        raise RuntimeError(f"INACTIVE_OR_UNDECLARED_ROUTE_EXECUTION:{route.name}")
    route_source, route_target = direction
    assert_route_mutation_allowed(
        route, cast(Language, route_source), cast(Language, route_target)
    )
    if source != route_source:
        raise RuntimeError(
            f"ROUTE_MUTATION_SOURCE_BINDING_INVALID:{route.name}:{source}"
        )
    specialized = route.name in SPECIALIZED_ROUTE_KEYS
    nodejs = route.name in NODEJS_EXACT_ROUTE_KEYS
    nodejs_typescript = nodejs and is_nodejs_typescript_route(
        cast(Language, route_source), cast(Language, route_target)
    )
    input_domain = declared_input_domain(route.name)
    for corpus in CORPORA:
        destination = route / "corpus" / corpus
        destination.mkdir(parents=True, exist_ok=True)
        if nodejs_typescript:
            profile = NODEJS_TYPESCRIPT_CORPUS_PROFILES[corpus]
            source_file = destination / f"{profile['source_name']}.{EXTENSIONS[source]}"
            sources = cast(dict[str, str], profile["sources"])
            source_file.write_text(sources[source], encoding="utf-8")
            cases_path = destination / "cases.json"
            cases_path.write_text(
                json.dumps(
                    profile["cases"], ensure_ascii=False, indent=2, sort_keys=True
                )
                + "\n",
                encoding="utf-8",
            )
            function_name = str(profile["function_name"])
            type_coverage = list(profile["type_coverage"])
        elif specialized:
            profile = SPECIALIZED_CORPUS_PROFILES[corpus]
            source_name = (
                str(profile["class_name"])
                if source == "java"
                else str(profile["module_name"])
            )
            source_file = destination / f"{source_name}.{EXTENSIONS[source]}"
            source_file.write_text(
                specialized_corpus_source(source, corpus), encoding="utf-8"
            )
            cases_path = destination / "cases.json"
            cases_path.write_text(
                json.dumps(
                    profile["cases"], ensure_ascii=False, indent=2, sort_keys=True
                )
                + "\n",
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
            type_coverage = [
                "legacy-profile-defined"
                if route.name in CORE_ROUTE_KEYS
                else "nodejs-safe-integer-function"
                if nodejs
                else "typed-pure-function-v1"
            ]
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
                "input_domain": input_domain,
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

    direction = route.name.split("-to-")
    if len(direction) != 2 or not all(direction):
        raise RuntimeError(f"INACTIVE_OR_UNDECLARED_ROUTE_EXECUTION:{route.name}")
    route_source, route_target = direction
    assert_route_mutation_allowed(
        route, cast(Language, route_source), cast(Language, route_target)
    )
    if source != route_source:
        raise RuntimeError(
            f"ROUTE_MUTATION_SOURCE_BINDING_INVALID:{route.name}:{source}"
        )
    fixture_root = fixtures / "module"
    nodejs = route.name in NODEJS_EXACT_ROUTE_KEYS
    nodejs_typescript = nodejs and is_nodejs_typescript_route(
        cast(Language, route_source), cast(Language, route_target)
    )
    filename = (
        "equivalence_typescript_module.mjs"
        if nodejs_typescript and source == "javascript"
        else MODULE_FIXTURE_FILES.get(source)
    )
    if filename is None:
        raise RuntimeError(f"MODULE_FIXTURE_LANGUAGE_UNDECLARED:{source}")
    source_file = fixture_root / source / filename
    cases_file = fixture_root / (
        "nodejs-typescript-cases.json"
        if nodejs_typescript
        else "nodejs-cases.json"
        if nodejs
        else "cases.json"
    )
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
            "input_domain": NODEJS_INPUT_DOMAIN if nodejs else SPECIALIZED_INPUT_DOMAIN,
            "type_coverage_required": (
                nodejs_route_types(
                    cast(Language, route_source), cast(Language, route_target)
                )
                if nodejs
                else ["integer", "number", "boolean"]
            ),
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
    swift_analyzer_receipt_path: Path | None,
) -> tuple[dict[str, str | int], dict[str, str | int]]:
    """Run and persist the real three-function module verification campaign."""

    assert_route_mutation_allowed(route, source, target)
    populate_module_corpus(route, fixtures, source)
    module_root = route / "corpus" / "module"
    module_manifest = json.loads(
        (module_root / "manifest.json").read_text(encoding="utf-8")
    )
    source_file = module_root / str(module_manifest["source_file"])
    cases_file = module_root / str(module_manifest["cases_file"])
    with tempfile.TemporaryDirectory(
        prefix=f"elmos-module-{source}-to-{target}-"
    ) as temporary:
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
        raw_references = report.get("artifact_refs")
        functions = report.get("functions")
        if not isinstance(raw_references, list) or not isinstance(functions, list):
            raise RuntimeError(f"MODULE_EQUIVALENCE_ARTIFACTS_INVALID:{route.name}")
        role_counts: dict[str, int] = {}
        seen_paths: set[str] = set()
        for index, reference in enumerate(raw_references):
            if not isinstance(reference, dict) or set(reference) != {
                "role",
                "path",
                "sha256",
                "bytes",
            }:
                raise RuntimeError(
                    f"MODULE_EQUIVALENCE_ARTIFACT_REF_INVALID:{route.name}:{index}"
                )
            role = reference.get("role")
            relative = reference.get("path")
            if not isinstance(role, str) or not isinstance(relative, str):
                raise RuntimeError(
                    f"MODULE_EQUIVALENCE_ARTIFACT_REF_INVALID:{route.name}:{index}"
                )
            candidate = (generated / relative).resolve(strict=True)
            try:
                candidate.relative_to(generated.resolve(strict=True))
            except ValueError as exc:
                raise RuntimeError(
                    f"MODULE_EQUIVALENCE_ARTIFACT_PATH_ESCAPE:{route.name}:{relative}"
                ) from exc
            if (
                relative in seen_paths
                or not candidate.is_file()
                or candidate.is_symlink()
                or reference.get("sha256") != sha256_file(candidate)
                or reference.get("bytes") != candidate.stat().st_size
            ):
                raise RuntimeError(
                    f"MODULE_EQUIVALENCE_ARTIFACT_BINDING_INVALID:{route.name}:{relative}"
                )
            seen_paths.add(relative)
            role_counts[role] = role_counts.get(role, 0) + 1
        expected_single_roles = set(MODULE_SINGLE_ARTIFACT_ROLES)
        if source == "javascript" and source_file.suffix == ".js":
            expected_single_roles.add("source-javascript-esm-descriptor")
        for role in expected_single_roles:
            if role_counts.get(role) != 1:
                raise RuntimeError(
                    f"MODULE_EQUIVALENCE_ARTIFACT_ROLE_COUNT:{route.name}:{role}"
                )
        for role in MODULE_PER_FUNCTION_ARTIFACT_ROLES:
            if role_counts.get(role) != len(functions):
                raise RuntimeError(
                    f"MODULE_EQUIVALENCE_ARTIFACT_ROLE_COUNT:{route.name}:{role}"
                )
        if set(role_counts) != (
            expected_single_roles | MODULE_PER_FUNCTION_ARTIFACT_ROLES
        ):
            raise RuntimeError(
                f"MODULE_EQUIVALENCE_ARTIFACT_ROLE_UNDECLARED:{route.name}"
            )
        closure_reference = next(
            reference
            for reference in raw_references
            if reference["role"] == "whole-file-module-closure"
        )
        if json.loads(
            (generated / str(closure_reference["path"])).read_text(encoding="utf-8")
        ) != report.get("whole_file_closure"):
            raise RuntimeError(
                f"MODULE_EQUIVALENCE_WHOLE_FILE_CLOSURE_DETACHED:{route.name}"
            )
        write_json(generated / "typed-pure-module-equivalence.json", report)
        manifest_ref = persist_artifact_directory(repo, route, "module", generated)

    artifact_prefix = "certification/artifacts/module/"
    route_report = json.loads(json.dumps(report))
    for reference in route_report["artifact_refs"]:
        reference["path"] = artifact_prefix + str(reference["path"])
    if "swift" in {source, target}:
        if swift_analyzer_receipt_path is None:
            raise RuntimeError(
                f"MODULE_SWIFT_ANALYZER_BUILD_RECEIPT_MISSING:{route.name}"
            )
        route_report["artifact_refs"].append(
            {
                "role": "swift-analyzer-build-receipt",
                **artifact_ref(route, swift_analyzer_receipt_path),
            }
        )
    elif swift_analyzer_receipt_path is not None:
        raise RuntimeError(
            f"MODULE_SWIFT_ANALYZER_BUILD_RECEIPT_UNEXPECTED:{route.name}"
        )
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


def execute_route(
    repo: Path, fixtures: Path, source: Language, target: Language
) -> None:
    route_key = f"{source}-to-{target}"
    assert_limited_route_execution_allowed(route_key)
    swift_receipt: dict[str, Any] | None = None
    if "swift" in {source, target}:
        swift_receipt = swift_analyzer_build_receipt()
        validate_portable_swift_analyzer_receipt(swift_receipt)
    route = configure_route(repo, source, target)
    populate_corpus(route, fixtures, source)
    reports: dict[str, dict[str, Any]] = {}
    artifact_manifests: dict[str, dict[str, str | int]] = {}
    with tempfile.TemporaryDirectory(
        prefix=f"elmos-{source}-to-{target}-"
    ) as temporary:
        root = Path(temporary)
        for corpus in CORPORA:
            corpus_root = route / "corpus" / corpus
            corpus_manifest = json.loads(
                (corpus_root / "manifest.json").read_text(encoding="utf-8")
            )
            source_file = corpus_root / str(corpus_manifest["source_file"])
            function_name = str(corpus_manifest["function_name"])
            cases = corpus_root / str(corpus_manifest["cases_file"])
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
    swift_analyzer_receipt_path: Path | None = None
    if "swift" in {source, target}:
        swift_analyzer_receipt_path = (
            route
            / "certification"
            / "formal-artifacts"
            / "swift-analyzer-build-receipt.json"
        )
        if swift_receipt is None:
            raise RuntimeError("SWIFT_ANALYZER_BUILD_RECEIPT_PREFLIGHT_MISSING")
        write_json(swift_analyzer_receipt_path, swift_receipt)
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
    if route_key in SPECIALIZED_ROUTE_KEYS:
        evidence["input_domain"] = SPECIALIZED_INPUT_DOMAIN
        evidence["out_of_domain_arithmetic_behavior"] = (
            SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
        )
        evidence["evidenced_type_coverage"] = ["integer", "number", "boolean"]
        evidence["notes"].append(
            "critical_unknown_semantics=0 is scoped only to canonical-finite-no-error-input-domain; "
            "string semantics and arithmetic-error-domain behavior remain blocked."
        )
    elif route_key in NODEJS_EXACT_ROUTE_KEYS:
        evidence["input_domain"] = NODEJS_INPUT_DOMAIN
        evidence["out_of_domain_arithmetic_behavior"] = NODEJS_OUT_OF_DOMAIN_BEHAVIOR
        evidence["evidenced_type_coverage"] = nodejs_route_types(source, target)
        evidence["notes"].append(
            "critical_unknown_semantics=0 is scoped only to the exact Node.js ES2022 ESM "
            "safe-integer/finite no-effect domain. JavaScript/TypeScript additionally admits "
            "the pinned strict ECMAScript string subset but explicitly excludes integer semantics; "
            "other cross-runtime string semantics, async, I/O, import, dynamic-eval, reflection, "
            "and shared state remain blocked."
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
        swift_analyzer_receipt_path,
    )
    certification["evidence_format"] = 2
    certification["formal_equivalence"] = formal_ref
    certification["evidence_refs"] = [
        *certification["evidence_refs"],
        str(formal_ref["path"]),
    ]
    if route_key in MODULE_EQUIVALENCE_ROUTE_KEYS:
        module_ref, module_manifest_ref = execute_module_route(
            repo,
            route,
            fixtures,
            source,
            target,
            swift_analyzer_receipt_path,
        )
        certification["module_equivalence"] = module_ref
        certification["declared_scope"] = "typed-pure-function-v1+typed-pure-module-v1"
        certification["gate_results"]["module_execution"] = "PASSED"
        certification["evidence_refs"].extend(
            [str(module_ref["path"]), str(module_manifest_ref["path"])]
        )
        evidence["module_equivalence"] = module_ref
        evidence["module_execution_status"] = "PASSED_LOCAL"
        evidence["module_artifact_manifest"] = module_manifest_ref
        evidence["artifact_refs"].append(module_manifest_ref)
        evidence["notes"].append(
            "The typed-pure-module-v1 run composed independently observed functions covering "
            "finite-number, boolean, and the pinned strict ECMAScript string subset; integer "
            "inference remained blocked, with exact symbol/signature closure and byte-bound "
            "per-function proof artifacts."
            if is_nodejs_typescript_route(source, target)
            else (
                "The typed-pure-module-v1 run composed at least three independently observed functions "
                "covering integer, finite-number, and boolean semantics with exact symbol/signature "
                "closure and byte-bound per-function proof artifacts."
            )
        )
    write_json(route / "certification" / "certification.json", certification)
    evidence["formal_equivalence"] = formal_ref
    write_json(route / "certification" / "evidence.json", evidence)


def write_route_gate_documents(
    route: Path,
    source: Language,
    target: Language,
    allow_immutable_core: bool = False,
) -> None:
    route_key = f"{source}-to-{target}"
    assert_limited_route_execution_allowed(
        route_key, allow_immutable_core=allow_immutable_core
    )
    specialized = route_key in SPECIALIZED_ROUTE_KEYS
    nodejs = route_key in NODEJS_EXACT_ROUTE_KEYS
    nodejs_typescript = nodejs and is_nodejs_typescript_route(source, target)
    module_required = route_key in MODULE_EQUIVALENCE_ROUTE_KEYS
    module_line = (
        "- Six-function typed-pure module composition (finite-number/string/boolean; integer blocked): `PASSED`\n"
        if nodejs_typescript
        else "- Five-function typed-pure module composition (integer/finite-number/boolean): `PASSED`\n"
        if module_required
        else ""
    )
    declared_profile = (
        "`typed-pure-function-v1` plus `typed-pure-module-v1`"
        if module_required
        else "`typed-pure-function-v1`"
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
            else "- Input domain: `nodejs-es2022-esm-safe-integer-finite-v1`\n"
            "- Integer inference, non-finite number, async, I/O, import, and dynamic eval: `BLOCKED`; "
            "strict ECMAScript strings: `PASSED`\n"
            if nodejs_typescript
            else "- Input domain: `nodejs-es2022-esm-safe-integer-finite-v1`\n"
            "- Unsafe integer/non-finite number, string, async, I/O, import, and dynamic eval: `BLOCKED`\n"
            if nodejs
            else ""
        )
        + "- Independent verifier: `NOT_RUN`\n"
        "- External/customer certification: `NOT_RUN`\n\n"
        f"The route is supported only for {declared_profile}. "
        + (
            "Local zero-unknown claims apply only to integer, finite-number transport/comparison, "
            "and boolean semantics inside the canonical finite no-error input domain. "
            if specialized
            else "Local zero-unknown claims apply only to finite-number transport/comparison, boolean, "
            "and the pinned strict ECMAScript string subset; integer remains blocked inside the "
            "Node.js ES2022 ESM finite no-effect domain. "
            if nodejs_typescript
            else "Local zero-unknown claims apply only to integer, finite-number transport/comparison, "
            "and boolean semantics inside the Node.js ES2022 ESM safe-integer/finite no-effect domain. "
            if nodejs
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
            else "The JavaScript/TypeScript exact profile covers finite-number transport/comparison, "
            "boolean, and pinned strict ECMAScript string semantics; integer inference, async, I/O, "
            "import, dynamic eval, and shared state are blocked. "
            if nodejs_typescript
            else "The Node.js exact profile covers safe integer, finite-number transport/comparison, "
            "and boolean; string, async, I/O, import, dynamic eval, and shared state are blocked. "
            if nodejs
            else ""
        )
        + "The reverse direction is a separate route. Native parsing, target compilation, "
        "and three local behavior corpora pass, so the bounded route is `limited`. "
        "Whole-repository orchestration never broadens the semantic profile; independent "
        "and external certification remain `NOT_RUN`.\n",
        encoding="utf-8",
    )


def execute_specialized_negative(
    route: Path, fixtures: Path, source: Language, target: Language
) -> str:
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
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-specialized-number-arithmetic-{route_key}-"
            ) as temporary:
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
                    raise RuntimeError(
                        "SPECIALIZED_NUMBER_ARITHMETIC_UNEXPECTEDLY_PASSED"
                    )
                if output.exists():
                    raise RuntimeError(
                        "SPECIALIZED_NUMBER_ARITHMETIC_CREATED_ARTIFACTS"
                    )
            expected_fragments = (
                f"SPECIALIZED_NUMBER_ARITHMETIC_UNSUPPORTED:{route_key}:addNumber",
            )
            input_refs = [
                negative_input_ref(route, number_source, "source"),
                negative_input_ref(route, number_cases, "cases"),
            ]
        elif case_id == "specialized-non-finite-case-unsupported":
            holdout_manifest = json.loads(
                (route / "corpus" / "holdout" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            non_finite_source = (
                route / "corpus" / "holdout" / str(holdout_manifest["source_file"])
            )
            non_finite_cases = negative_root / "non_finite_number_cases.json"
            non_finite_cases.write_text(
                '[{"args":[1e400],"expected":0.0}]\n', encoding="utf-8"
            )
            function_name = str(holdout_manifest["function_name"])
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-specialized-non-finite-{route_key}-"
            ) as temporary:
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
            expected_fragments = (
                f"SPECIALIZED_CASE_NON_FINITE_NUMBER_UNSUPPORTED:{route_key}:{function_name}:0",
            )
            input_refs = [
                negative_input_ref(route, non_finite_source, "source"),
                negative_input_ref(route, non_finite_cases, "cases"),
            ]
        elif case_id == "specialized-overflow-outside-no-error-domain":
            development_manifest = json.loads(
                (route / "corpus" / "development" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            overflow_source = (
                route
                / "corpus"
                / "development"
                / str(development_manifest["source_file"])
            )
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
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-specialized-overflow-{route_key}-"
            ) as temporary:
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
                negative_input_ref(route, overflow_source, "source"),
                negative_input_ref(route, overflow_cases, "cases"),
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
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-specialized-string-{route_key}-"
            ) as temporary:
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
            expected_fragments = (
                f"SPECIALIZED_STRING_SEMANTICS_UNSUPPORTED:{route_key}:same",
            )
            input_refs = [
                negative_input_ref(route, string_source, "source"),
                negative_input_ref(route, string_cases, "cases"),
            ]
        elif case_id == "missing-symbol-fails-closed":
            development_manifest = json.loads(
                (route / "corpus" / "development" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            missing_source = (
                route
                / "corpus"
                / "development"
                / str(development_manifest["source_file"])
            )
            missing_cases = route / "corpus" / "development" / "cases.json"
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-missing-symbol-{route_key}-"
            ) as temporary:
                output = Path(temporary) / "must-not-exist"
                try:
                    migrate(
                        missing_source,
                        source,
                        target,
                        "__elmos_missing_function__",
                        missing_cases,
                        output,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError("MISSING_SYMBOL_UNEXPECTEDLY_PASSED")
                if output.exists():
                    raise RuntimeError("MISSING_SYMBOL_CREATED_ARTIFACTS")
            expected_fragments = (
                ("NO_SUPPORTED_FUNCTIONS",)
                if source == "swift"
                else ("FUNCTION_NOT_FOUND:__elmos_missing_function__",)
            )
            input_refs = [
                negative_input_ref(route, missing_source, "source"),
                negative_input_ref(route, missing_cases, "cases"),
            ]
        elif case_id == "undeclared-directed-route-fails-closed":
            module_source = fixtures / "module" / "java" / MODULE_FIXTURE_FILES["java"]
            module_cases = fixtures / "module" / "cases.json"
            undeclared_source = negative_root / "undeclared_java_to_java.java"
            undeclared_cases = negative_root / "undeclared_java_to_java_cases.json"
            shutil.copy2(module_source, undeclared_source)
            shutil.copy2(module_cases, undeclared_cases)
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-undeclared-{route_key}-"
            ) as temporary:
                output = Path(temporary) / "must-not-exist"
                try:
                    migrate_module(
                        undeclared_source,
                        "java",
                        "java",
                        undeclared_cases,
                        output,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError("UNDECLARED_DIRECTED_ROUTE_UNEXPECTEDLY_PASSED")
                if output.exists():
                    raise RuntimeError("UNDECLARED_DIRECTED_ROUTE_CREATED_ARTIFACTS")
            expected_fragments = ("SOURCE_AND_TARGET_MUST_DIFFER",)
            input_refs = [
                negative_input_ref(route, undeclared_source, "source-module"),
                negative_input_ref(route, undeclared_cases, "case-manifest"),
            ]
        elif case_id == "swift-helper-tamper":
            expected_helper = _SWIFT_HELPERS["non_zero_double"]
            tampered_helper = expected_helper.replace(
                "    return value\n", "    return -value\n", 1
            )
            if tampered_helper == expected_helper:
                raise RuntimeError("SWIFT_HELPER_TAMPER_FIXTURE_NOT_MUTATED")
            source_path = negative_root / "swift_helper_tamper.swift"
            source_path.write_text(
                tampered_helper
                + "\nfunc quotient(_ left: Double, _ right: Double) -> Double { "
                "return left / elmosNonZero(right) }\n",
                encoding="utf-8",
            )
            try:
                analyze(source_path, "swift", "quotient", emitted_target=True)
            except RouteError as exc:
                reason = str(exc)
            else:
                raise RuntimeError("SWIFT_HELPER_TAMPER_UNEXPECTEDLY_PASSED")
            expected_fragments = (
                "EMITTED_HELPER_SOURCE_MISMATCH:swift:non_zero_double:elmosNonZero",
            )
            input_refs = [negative_input_ref(route, source_path, "source")]
        else:
            specification = SPECIALIZED_NEGATIVE_SOURCES.get(case_id)
            if specification is None:
                raise RuntimeError(f"SPECIALIZED_NEGATIVE_CASE_UNDECLARED:{case_id}")
            language, filename, function_name, content, expected_fragments = (
                specification
            )
            source_path = negative_root / filename
            source_path.write_text(content, encoding="utf-8")
            try:
                analyze(source_path, language, function_name)
            except RouteError as exc:
                reason = str(exc)
            else:
                raise RuntimeError(
                    f"SPECIALIZED_NEGATIVE_UNEXPECTEDLY_PASSED:{case_id}"
                )
            input_refs = [negative_input_ref(route, source_path, "source")]
        if reason not in expected_fragments:
            raise RuntimeError(f"SPECIALIZED_NEGATIVE_WRONG_FAILURE:{case_id}:{reason}")
        results.append(
            {
                "case_id": case_id,
                "status": "PASSED",
                "expected_result": "BLOCKED",
                "observed_reason": reason,
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


def execute_nodejs_negative(
    route: Path,
    fixtures: Path,
    source: Language,
    target: Language,
) -> str:
    """Execute the exact Node.js fail-closed corpus for one direction."""

    route_key = f"{source}-to-{target}"
    expected_case_ids = nodejs_negative_case_ids(source, target)
    negative_root = route / "corpus" / "negative"
    negative_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for case_id in expected_case_ids:
        specification = NODEJS_NEGATIVE_ANALYZE_SOURCES.get(case_id)
        output_root: Path | None = None
        if case_id == "nodejs-commonjs-unsupported":
            case_source = negative_root / "commonjs_module.cjs"
            case_source.write_text(
                "module.exports.commonJsValue = function commonJsValue(value) { "
                "return value; };\n",
                encoding="utf-8",
            )
            case_path = negative_root / "commonjs_cases.json"
            write_json(case_path, [{"args": [1], "expected": 1}])
            counterpart = target if source == "javascript" else source
            expected_codes = frozenset({"JAVASCRIPT_CJS_SOURCE_BLOCKED"})
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-nodejs-commonjs-{route_key}-"
            ) as temporary:
                output_root = Path(temporary) / "must-not-exist"
                try:
                    migrate(
                        case_source,
                        "javascript",
                        counterpart,
                        "commonJsValue",
                        case_path,
                        output_root,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError(
                        f"NODEJS_NEGATIVE_UNEXPECTEDLY_PASSED:{case_id}"
                    )
                if output_root.exists():
                    raise RuntimeError(
                        f"NODEJS_NEGATIVE_CREATED_ARTIFACTS:{case_id}"
                    )
            input_refs = [
                negative_input_ref(route, case_source, "source"),
                negative_input_ref(route, case_path, "cases"),
            ]
        elif specification is not None:
            filename, function_name, content, expected_codes = specification
            case_source = negative_root / filename
            case_source.write_text(content, encoding="utf-8")
            try:
                analyze(case_source, "javascript", function_name)
            except RouteError as exc:
                reason = str(exc)
            else:
                raise RuntimeError(f"NODEJS_NEGATIVE_UNEXPECTEDLY_PASSED:{case_id}")
            input_refs = [negative_input_ref(route, case_source, "source")]
        elif case_id in NODEJS_GENERATED_NEGATIVE_CASES:
            filename, function_name, content, cases = (
                nodejs_generated_negative_source(source, case_id)
            )
            case_source = negative_root / filename
            case_source.write_text(content, encoding="utf-8")
            case_path = negative_root / f"{NODEJS_GENERATED_NEGATIVE_CASES[case_id]['stem']}_cases.json"
            write_json(case_path, cases)
            expected_code = str(
                NODEJS_GENERATED_NEGATIVE_CASES[case_id]["reason_code"]
            )
            if source == "python" and case_id in {
                "nodejs-division-by-zero-unsupported",
                "nodejs-modulo-by-zero-unsupported",
            }:
                expected_code = {
                    "nodejs-division-by-zero-unsupported": (
                        "PYTHON_TRUE_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET"
                    ),
                    "nodejs-modulo-by-zero-unsupported": (
                        "PYTHON_FLOORED_MODULO_OUTSIDE_CERTIFIED_SUBSET"
                    ),
                }[case_id]
            expected_codes = frozenset({expected_code})
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-nodejs-generated-negative-{route_key}-"
            ) as temporary:
                output_root = Path(temporary) / "must-not-exist"
                try:
                    migrate(
                        case_source,
                        source,
                        target,
                        function_name,
                        case_path,
                        output_root,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError(
                        f"NODEJS_NEGATIVE_UNEXPECTEDLY_PASSED:{case_id}"
                    )
                if output_root.exists():
                    raise RuntimeError(
                        f"NODEJS_NEGATIVE_CREATED_ARTIFACTS:{case_id}"
                    )
            input_refs = [
                negative_input_ref(route, case_source, "source"),
                negative_input_ref(route, case_path, "cases"),
            ]
        elif case_id in {
            "nodejs-non-finite-case-unsupported",
            "nodejs-unsafe-integer-case-unsupported",
            "nodejs-unsafe-integer-result-unsupported",
        }:
            development_manifest = json.loads(
                (route / "corpus" / "development" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            case_source = (
                route
                / "corpus"
                / "development"
                / str(development_manifest["source_file"])
            )
            function_name = str(development_manifest["function_name"])
            original_cases = json.loads(
                (
                    route
                    / "corpus"
                    / "development"
                    / str(development_manifest["cases_file"])
                ).read_text(encoding="utf-8")
            )
            if not isinstance(original_cases, list) or not original_cases:
                raise RuntimeError("NODEJS_NEGATIVE_DEVELOPMENT_CASES_INVALID")
            case_value = dict(original_cases[0])
            arguments = list(case_value.get("args", []))
            if not arguments:
                raise RuntimeError("NODEJS_NEGATIVE_DEVELOPMENT_ARGUMENTS_INVALID")
            case_path = negative_root / {
                "nodejs-non-finite-case-unsupported": "non_finite_number_cases.json",
                "nodejs-unsafe-integer-case-unsupported": "unsafe_integer_cases.json",
                "nodejs-unsafe-integer-result-unsupported": "unsafe_integer_result_cases.json",
            }[case_id]
            if case_id == "nodejs-non-finite-case-unsupported":
                arguments[0] = "__ELMOS_NON_FINITE_NUMBER__"
                case_value["args"] = arguments
                encoded = json.dumps(
                    [case_value], ensure_ascii=False, indent=2, sort_keys=True
                )
                case_path.write_text(
                    encoded.replace('"__ELMOS_NON_FINITE_NUMBER__"', "1e400") + "\n",
                    encoding="utf-8",
                )
                expected_codes = frozenset(
                    {"NODEJS_CASE_NON_FINITE_NUMBER_UNSUPPORTED"}
                )
            elif case_id == "nodejs-unsafe-integer-case-unsupported":
                arguments[0] = 2**53
                case_value["args"] = arguments
                case_path.write_text(
                    json.dumps(
                        [case_value], ensure_ascii=False, indent=2, sort_keys=True
                    )
                    + "\n",
                    encoding="utf-8",
                )
                expected_codes = frozenset({"NODEJS_CASE_UNSAFE_INTEGER_UNSUPPORTED"})
            else:
                if len(arguments) != 2:
                    raise RuntimeError(
                        "NODEJS_NEGATIVE_DEVELOPMENT_RESULT_ARGUMENTS_INVALID"
                    )
                case_value["args"] = [2**53 - 1, 1]
                case_value["expected"] = 2**53
                case_path.write_text(
                    json.dumps(
                        [case_value], ensure_ascii=False, indent=2, sort_keys=True
                    )
                    + "\n",
                    encoding="utf-8",
                )
                expected_codes = frozenset(
                    {"NODEJS_CASE_UNSAFE_INTEGER_RESULT_UNSUPPORTED"}
                )
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-nodejs-domain-negative-{route_key}-"
            ) as temporary:
                output_root = Path(temporary) / "must-not-exist"
                try:
                    migrate(
                        case_source,
                        source,
                        target,
                        function_name,
                        case_path,
                        output_root,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError(f"NODEJS_NEGATIVE_UNEXPECTEDLY_PASSED:{case_id}")
                if output_root.exists():
                    raise RuntimeError(f"NODEJS_NEGATIVE_CREATED_ARTIFACTS:{case_id}")
            input_refs = [
                negative_input_ref(route, case_source, "source"),
                negative_input_ref(route, case_path, "cases"),
            ]
        elif case_id == "nodejs-typescript-integer-contract-unsupported":
            if source == "javascript":
                filename = "typescript_integer_contract.mjs"
                content = (
                    "/**\n * @param {integer} value\n * @returns {integer}\n */\n"
                    "export function integerContract(value) { return value; }\n"
                )
                expected_codes = frozenset(
                    {"NODEJS_TYPESCRIPT_INTEGER_EVIDENCE_UNAVAILABLE"}
                )
            else:
                filename = "typescript_integer_contract.ts"
                content = "export function integerContract(value: number): number { return value; }\n"
                expected_codes = frozenset(
                    {"PURE_MODULE_CASE_MANIFEST_SIGNATURE_MISMATCH"}
                )
            case_source = negative_root / filename
            case_source.write_text(content, encoding="utf-8")
            case_path = negative_root / "typescript_integer_contract_cases.json"
            write_json(
                case_path,
                {
                    "schema_version": "1.0.0",
                    "profile": "typed-pure-module-v1",
                    "composition": {
                        "call_graph": [],
                        "global_state": "none",
                        "effects": "none",
                        "exceptions": "domain-guards-fail-closed-before-execution",
                        "input_domain": NODEJS_INPUT_DOMAIN,
                    },
                    "functions": [
                        {
                            "symbol": "integerContract",
                            "signature": {
                                "parameters": [{"name": "value", "type": "integer"}],
                                "return_type": "integer",
                            },
                            "cases": [{"args": [1], "expected": 1}],
                        }
                    ],
                },
            )
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-nodejs-typescript-integer-{route_key}-"
            ) as temporary:
                output_root = Path(temporary) / "must-not-exist"
                try:
                    migrate_module(
                        case_source,
                        source,
                        target,
                        case_path,
                        output_root,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError(f"NODEJS_NEGATIVE_UNEXPECTEDLY_PASSED:{case_id}")
                if output_root.exists():
                    raise RuntimeError(f"NODEJS_NEGATIVE_CREATED_ARTIFACTS:{case_id}")
            input_refs = [
                negative_input_ref(route, case_source, "source-module"),
                negative_input_ref(route, case_path, "case-manifest"),
            ]
        elif case_id == "undeclared-directed-route-fails-closed":
            module_source = fixtures / "module" / "java" / MODULE_FIXTURE_FILES["java"]
            module_cases = fixtures / "module" / "cases.json"
            case_source = negative_root / "undeclared_java_to_java.java"
            case_path = negative_root / "undeclared_java_to_java_cases.json"
            shutil.copy2(module_source, case_source)
            shutil.copy2(module_cases, case_path)
            expected_codes = frozenset({"SOURCE_AND_TARGET_MUST_DIFFER"})
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-nodejs-undeclared-{route_key}-"
            ) as temporary:
                output_root = Path(temporary) / "must-not-exist"
                try:
                    migrate_module(
                        case_source,
                        "java",
                        "java",
                        case_path,
                        output_root,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError(f"NODEJS_NEGATIVE_UNEXPECTEDLY_PASSED:{case_id}")
                if output_root.exists():
                    raise RuntimeError(f"NODEJS_NEGATIVE_CREATED_ARTIFACTS:{case_id}")
            input_refs = [
                negative_input_ref(route, case_source, "source-module"),
                negative_input_ref(route, case_path, "case-manifest"),
            ]
        elif case_id == "missing-symbol-fails-closed":
            fixture_source, _, fixture_cases = source_path(
                fixtures, "development", source
            )
            case_source = negative_root / f"missing_symbol_source.{EXTENSIONS[source]}"
            case_path = negative_root / "missing_symbol_cases.json"
            shutil.copy2(fixture_source, case_source)
            shutil.copy2(fixture_cases, case_path)
            expected_codes = frozenset({"FUNCTION_NOT_FOUND", "NO_SUPPORTED_FUNCTIONS"})
            with tempfile.TemporaryDirectory(
                prefix=f"elmos-nodejs-missing-symbol-{route_key}-"
            ) as temporary:
                output_root = Path(temporary) / "must-not-exist"
                try:
                    migrate(
                        case_source,
                        source,
                        target,
                        "__elmos_missing_function__",
                        case_path,
                        output_root,
                    )
                except RouteError as exc:
                    reason = str(exc)
                else:
                    raise RuntimeError(f"NODEJS_NEGATIVE_UNEXPECTEDLY_PASSED:{case_id}")
                if output_root.exists():
                    raise RuntimeError(f"NODEJS_NEGATIVE_CREATED_ARTIFACTS:{case_id}")
            input_refs = [
                negative_input_ref(route, case_source, "source"),
                negative_input_ref(route, case_path, "cases"),
            ]
        else:
            raise RuntimeError(f"NODEJS_NEGATIVE_CASE_UNDECLARED:{case_id}")

        reason = nodejs_stable_route_error(reason)
        reason_code = nodejs_route_error_code(reason)
        if reason_code not in expected_codes:
            raise RuntimeError(f"NODEJS_NEGATIVE_WRONG_FAILURE:{case_id}:{reason}")
        results.append(
            {
                "case_id": case_id,
                "status": "PASSED",
                "expected_result": "BLOCKED",
                "observed_reason": reason,
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
            "case_ids": list(expected_case_ids),
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


def execute_negative(
    route: Path, fixtures: Path, source: Language, target: Language
) -> str:
    route_key = f"{source}-to-{target}"
    assert_limited_route_execution_allowed(route_key, allow_immutable_core=True)
    if route_key in SPECIALIZED_ROUTE_KEYS:
        return execute_specialized_negative(route, fixtures, source, target)
    if route_key in NODEJS_EXACT_ROUTE_KEYS:
        return execute_nodejs_negative(route, fixtures, source, target)
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
    write_route_gate_documents(route, source, target, allow_immutable_core=True)
    return relative


def current_engine_source_binding(repo: Path, route_root: Path) -> tuple[bool, str]:
    """Return whether persisted local evidence still binds the live engine bytes."""

    manifest_path = (
        route_root
        / "certification"
        / "formal-artifacts"
        / "engine-source-manifest.json"
    )
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return False, "ENGINE_SOURCE_MANIFEST_MISSING"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False, "ENGINE_SOURCE_MANIFEST_INVALID"
    if set(manifest) != {
        "schema_version",
        "kind",
        "file_count",
        "files",
        "runtime_source_receipts",
    } or manifest.get("schema_version") != 1 or manifest.get("kind") != (
        "polyglot-route-engine-source-bundle"
    ):
        return False, "ENGINE_SOURCE_MANIFEST_INVALID"
    files = manifest.get("files")
    if (
        not isinstance(files, list)
        or not files
        or manifest.get("file_count") != len(files)
    ):
        return False, "ENGINE_SOURCE_MANIFEST_INVALID"

    try:
        from elmos_polyglot_route.toolchains import (
            python_source_archive_receipt,
            typescript_compiler_capture_receipt,
        )
        from fresh_route_runtime import (
            PYTHON_CAPTURED_ARCHIVE_RELATIVE,
            TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
        )

        python_receipt = python_source_archive_receipt()
        typescript_receipt = typescript_compiler_capture_receipt()
    except (OSError, RuntimeError, RouteError):
        return False, "ENGINE_RUNTIME_SOURCE_RECEIPT_UNAVAILABLE"
    runtime_receipts = manifest.get("runtime_source_receipts")
    if not isinstance(runtime_receipts, dict) or set(runtime_receipts) != {
        "python_source_archive",
        "typescript_compiler_closure",
    }:
        return False, "ENGINE_SOURCE_MANIFEST_INVALID"
    expected_python_receipt = {
        key: python_receipt[key]
        for key in (
            "schema_version",
            "capture_relative_path",
            "sha256",
            "bytes",
            "mode",
            "uid",
            "gid",
            "nlink",
            "source_tree_sha256",
            "source_tree_record_count",
            "source_tree_file_count",
            "source_tree_bytes",
        )
    }
    if runtime_receipts.get("python_source_archive") != expected_python_receipt:
        return False, "ENGINE_RUNTIME_SOURCE_RECEIPT_STALE"
    expected_typescript_receipt = {
        "schema_version": typescript_receipt["schema_version"],
        "capture_relative_path": typescript_receipt["capture_relative_path"],
        "source_manifest_sha256": typescript_receipt["source_manifest_sha256"],
        "runtime_manifest_sha256": typescript_receipt[
            "runtime_manifest_sha256"
        ],
        "compiler_closure_sha256": typescript_receipt[
            "compiler_closure_sha256"
        ],
        "file_count": typescript_receipt["file_count"],
        "bytes": typescript_receipt["bytes"],
        "files": [
            {
                key: record[key]
                for key in ("path", "sha256", "bytes", "mode")
            }
            for record in typescript_receipt["files"]
        ],
        "semantic_soundness": typescript_receipt["semantic_soundness"],
    }
    if (
        runtime_receipts.get("typescript_compiler_closure")
        != expected_typescript_receipt
    ):
        return False, "ENGINE_RUNTIME_SOURCE_RECEIPT_STALE"
    if (
        typescript_receipt.get("capture_relative_path")
        != TYPESCRIPT_CAPTURED_ROOT_RELATIVE
        or not isinstance(typescript_receipt.get("source_root"), str)
        or not isinstance(typescript_receipt.get("files"), list)
    ):
        return False, "ENGINE_RUNTIME_SOURCE_RECEIPT_STALE"
    typescript_source_root = Path(str(typescript_receipt["source_root"]))
    typescript_live_sources = {
        f"{TYPESCRIPT_CAPTURED_ROOT_RELATIVE}/{record['path']}": Path(
            str(record["source_path"])
        )
        for record in typescript_receipt["files"]
        if isinstance(record, dict)
        and isinstance(record.get("path"), str)
        and isinstance(record.get("source_path"), str)
    }
    if len(typescript_live_sources) != typescript_receipt.get("file_count"):
        return False, "ENGINE_RUNTIME_SOURCE_RECEIPT_STALE"

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
        if repository_path == PYTHON_CAPTURED_ARCHIVE_RELATIVE:
            candidates = (
                (
                    Path(str(python_receipt["source_path"])).parent,
                    Path(str(python_receipt["source_path"])),
                ),
                (route_resolved, route_resolved / captured_path),
            )
        elif repository_path in typescript_live_sources:
            candidates = (
                (
                    typescript_source_root,
                    typescript_live_sources[repository_path],
                ),
                (route_resolved, route_resolved / captured_path),
            )
        else:
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
    legacy_authority = legacy_campaign_authority(repo)
    prepared_v3_routes = tuple(
        _v3_research_route_documents(repo, route_key)
        for route_key in V3_EXACT_ROUTE_KEYS
    )
    v3_documents = {
        route.name: {
            path.name: document
            for path, document in documents
        }
        for route, documents in prepared_v3_routes
    }
    routes_root = repo / "routes"
    support_matrix_documents: list[tuple[Path, bytes]] = []
    for route_key in ALL_DECLARED_ROUTE_KEYS:
        v3_route_documents = v3_documents.get(route_key)
        if v3_route_documents is not None:
            raw_support = v3_route_documents["support-matrix.json"]
            support_bytes = _json_bytes(raw_support)
        else:
            support_path = routes_root / route_key / "support-matrix.json"
            support_bytes = _stable_regular_file_bytes(
                routes_root,
                support_path,
                label=f"ROUTE_SUPPORT_MATRIX:{route_key}",
            )
            try:
                raw_support = json.loads(support_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"SUPPORT_MATRIX_DOCUMENT_INVALID:{route_key}"
                ) from exc
            if not isinstance(raw_support, dict):
                raise RuntimeError(f"SUPPORT_MATRIX_DOCUMENT_INVALID:{route_key}")
        if v3_route_documents is not None:
            continue
        support_matrix_documents.append(
            (
                routes_root
                / route_key
                / "certification"
                / "support-matrix.md",
                support_matrix_markdown_bytes(route_key, support_bytes, raw_support),
            )
        )
    routes: list[dict[str, Any]] = []
    for route_key in EVIDENCED_ROUTE_KEYS:
        source_value, target_value = split_route_key(route_key)
        route_root = repo / "routes" / route_key
        v3_route_documents = v3_documents.get(route_key)
        if v3_route_documents is None:
            try:
                manifest = json.loads(
                    _stable_regular_file_bytes(
                        routes_root,
                        route_root / "route.json",
                        label=f"ROUTE_MANIFEST:{route_key}",
                    ).decode("utf-8")
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"ROUTE_DOCUMENT_INVALID:{route_key}:route.json"
                ) from exc
        else:
            manifest = v3_route_documents["route.json"]
        evidence_path = route_root / "certification" / "evidence.json"
        certification_path = route_root / "certification" / "certification.json"
        if v3_route_documents is None:
            try:
                evidence = json.loads(
                    _stable_regular_file_bytes(
                        routes_root,
                        evidence_path,
                        label=f"ROUTE_EVIDENCE:{route_key}",
                    ).decode("utf-8")
                )
                certification = json.loads(
                    _stable_regular_file_bytes(
                        routes_root,
                        certification_path,
                        label=f"ROUTE_CERTIFICATION:{route_key}",
                    ).decode("utf-8")
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"ROUTE_DOCUMENT_INVALID:{route_key}:certification"
                ) from exc
        else:
            evidence = v3_route_documents["evidence.json"]
            certification = v3_route_documents["certification.json"]
        if (
            not isinstance(manifest, dict)
            or not isinstance(evidence, dict)
            or not isinstance(certification, dict)
            or manifest.get("route_key") != route_key
            or evidence.get("route_key") != route_key
            or certification.get("route_key") != route_key
            or evidence.get("route_version") != manifest.get("version")
            or certification.get("route_version") != manifest.get("version")
        ):
            raise RuntimeError(f"ROUTE_DOCUMENT_BINDING_DRIFT:{route_key}")
        module_required = route_key in MODULE_EQUIVALENCE_ROUTE_KEYS
        if route_key in V3_EXACT_ROUTE_KEYS:
            if (
                manifest.get("status") != "research"
                or evidence != v3_research_evidence_document(route_key)
                or certification
                != v3_research_certification_document(route_key)
            ):
                raise RuntimeError(f"V3_ROUTE_CAMPAIGN_OVERCLAIM:{route_key}")
            function_passed = False
            module_passed = False
            source_binding_current = False
            local_status = "NOT_RUN"
            local_execution_reason = "V3_ROUTE_CAMPAIGN_NOT_RUN"
        else:
            function_passed = evidence.get("execution_status") == "PASSED_LOCAL"
            module_passed = (
                evidence.get("module_execution_status") == "PASSED_LOCAL"
                if module_required
                else True
            )
            source_binding_current, source_binding_reason = current_engine_source_binding(
                repo, route_root
            )
            if function_passed and module_passed and source_binding_current:
                local_status = "PASSED_LOCAL"
            elif (
                evidence.get("execution_status") == "FAILED"
                or evidence.get("module_execution_status") == "FAILED"
            ):
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
                "route_set": provenance_route_set(route_key),
                "source": source_value,
                "source_version": SHORT_VERSIONS[source_value],
                "target": target_value,
                "target_version": SHORT_VERSIONS[target_value],
                "status": manifest.get("status"),
                "local_execution_status": local_status,
                "local_execution_reason": local_execution_reason,
                "module_execution_status": (
                    (
                        evidence.get("module_execution_status", "NOT_RUN")
                        if source_binding_current
                        else "NOT_RUN"
                    )
                    if module_required
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
        "FAILED"
        if "FAILED" in local_statuses
        else "PASSED_LOCAL"
        if local_statuses == {"PASSED_LOCAL"}
        else "NOT_RUN"
    )
    status_counts = {
        status: sum(1 for entry in routes if entry["status"] == status)
        for status in ("research", "experimental", "limited", "blocked", "certified")
    }
    # Prebuild the inventory, all 330 V3 contract/view documents, and the
    # remaining 110 support-matrix views before the first write. They form one
    # process-level transaction: any injected or ordinary write failure
    # restores every target's exact original bytes.
    inventory_document = {
            "schema_version": "1.4.0",
            "route_policy": {
                "mode": "complete-directed-matrix",
                "cartesian_expansion": "EXPLICIT_THIRTEEN_LANGUAGE_MATRIX",
                "complete_route_set": "thirteen-language-complete-156",
                "legacy_route_set": "legacy-complete-30",
                "specialized_route_set": "cpp-objc-swift-java-exact-8",
                "completion_route_set": "nine-language-completion-34",
                "nodejs_route_set": "javascript-node26-completion-18",
                "php_route_set": "php-php85-completion-20",
                "v3_route_set": "kotlin-react-flutter-completion-66",
                "deprecated_route_set": "javascript-node26-completion-18",
                "preserved_nine_language_route_set": "nine-language-complete-72",
                "preserved_ten_language_route_set": "ten-language-complete-90",
                "preserved_eleven_language_route_set": "eleven-language-complete-110",
            },
            "route_provenance_partition": {
                "policy": "exact-disjoint-authority-partition",
                # Covers active AND deprecated directions: a partition owns
                # filed evidence, and deprecating javascript did not unfile it.
                "route_count": len(ALL_DECLARED_ROUTE_KEYS),
                "active_route_count": len(COMPLETE_ROUTE_KEYS),
                "deprecated_route_count": len(DEPRECATED_ROUTE_KEYS),
                "sets": {
                    name: list(route_keys)
                    for name, route_keys in ROUTE_PROVENANCE_PARTITIONS.items()
                },
            },
            "route_execution_authorities": route_execution_authorities_document(),
            "route_sets": {
                "legacy-complete-30": {
                    "policy": "complete-directed-permutation",
                    "languages": list(CORE_LANGUAGES),
                    "route_count": len(CORE_ROUTE_KEYS),
                    "route_keys": list(CORE_ROUTE_KEYS),
                    "execution_authority_sha256": legacy_authority["authority_sha256"],
                },
                "cpp-objc-swift-java-exact-8": {
                    "policy": "exact-explicit-set",
                    "languages": ["cpp", "objc", "swift", "java"],
                    "route_count": len(SPECIALIZED_ROUTE_KEYS),
                    "route_keys": list(SPECIALIZED_ROUTE_KEYS),
                    "module_profile": "typed-pure-module-v1",
                },
                "nine-language-completion-34": {
                    "policy": "exact-matrix-completion-set",
                    "languages": list(NINE_LANGUAGE_MATRIX_LANGUAGES),
                    "route_count": len(COMPLETION_ROUTE_KEYS),
                    "route_keys": list(COMPLETION_ROUTE_KEYS),
                },
                "nine-language-complete-72": {
                    "policy": "complete-directed-permutation",
                    "languages": list(NINE_LANGUAGE_MATRIX_LANGUAGES),
                    "route_count": len(NINE_LANGUAGE_COMPLETE_ROUTE_KEYS),
                    "route_keys": list(NINE_LANGUAGE_COMPLETE_ROUTE_KEYS),
                },
                "javascript-node26-completion-18": {
                    "policy": "exact-nodejs-matrix-completion-set",
                    "languages": list(TEN_LANGUAGE_MATRIX_LANGUAGES),
                    "route_count": len(NODEJS_EXACT_ROUTE_KEYS),
                    "route_keys": list(NODEJS_EXACT_ROUTE_KEYS),
                    "runtime_profile": "Node.js 26.0.0 / ES2022 / ESM",
                    "module_profile": "typed-pure-module-v1",
                    "input_domain": NODEJS_INPUT_DOMAIN,
                },
                "ten-language-complete-90": {
                    "policy": "complete-directed-permutation",
                    "languages": list(TEN_LANGUAGE_MATRIX_LANGUAGES),
                    "route_count": len(TEN_LANGUAGE_COMPLETE_ROUTE_KEYS),
                    "route_keys": list(TEN_LANGUAGE_COMPLETE_ROUTE_KEYS),
                },
                "php-php85-completion-20": {
                    "policy": "exact-matrix-completion-set",
                    # Repointed off SUPPORTED_ROUTE_LANGUAGES: this set's 20
                    # keys are an eleven-language fact and must not follow the
                    # active language tuple.
                    "languages": list(ELEVEN_LANGUAGE_MATRIX_LANGUAGES),
                    "route_count": len(PHP_EXACT_ROUTE_KEYS),
                    "route_keys": list(PHP_EXACT_ROUTE_KEYS),
                    "runtime_profile": "PHP 8.5.9 (cli) (NTS) / strict_types=1",
                },
                "eleven-language-complete-110": {
                    "policy": "complete-directed-permutation",
                    "languages": list(ELEVEN_LANGUAGE_MATRIX_LANGUAGES),
                    "route_count": len(ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS),
                    "route_keys": list(ELEVEN_LANGUAGE_COMPLETE_ROUTE_KEYS),
                    "deprecated_route_keys": list(DEPRECATED_ROUTE_KEYS),
                },
                "kotlin-react-flutter-completion-66": {
                    "policy": "exact-matrix-completion-set",
                    "languages": list(SUPPORTED_ROUTE_LANGUAGES),
                    "route_count": len(V3_EXACT_ROUTE_KEYS),
                    "route_keys": list(V3_EXACT_ROUTE_KEYS),
                    "analyzer_status": "LOCAL_SINGLE_UNIT_READY",
                    "pending_analyzer_languages": list(PENDING_ANALYZER_LANGUAGES),
                    "repository_status": "LOCAL_REPOSITORY_READY",
                    "pending_repository_languages": list(PENDING_REPOSITORY_LANGUAGES),
                },
                "thirteen-language-complete-156": {
                    "policy": "complete-directed-permutation",
                    "languages": list(SUPPORTED_ROUTE_LANGUAGES),
                    "route_count": len(COMPLETE_ROUTE_KEYS),
                    "route_keys": list(COMPLETE_ROUTE_KEYS),
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
            "console_exposed_languages": list(SUPPORTED_ROUTE_LANGUAGES),
            "deprecated_languages": list(DEPRECATED_ROUTE_LANGUAGES),
            "pending_analyzer_languages": list(PENDING_ANALYZER_LANGUAGES),
            "pending_repository_languages": list(PENDING_REPOSITORY_LANGUAGES),
            "languages": {
                language: {
                    "version": SHORT_VERSIONS[language],
                    "exact_versions": list(VERSIONS[language]),
                    "engine_path": ENGINE_PATHS[language],
                    **(
                        {"analyzer_status": "PENDING_ANALYZER"}
                        if language in PENDING_ANALYZER_LANGUAGES
                        else {"analyzer_status": "LOCAL_SINGLE_UNIT_READY"}
                        if language in V3_LANGUAGES
                        else {}
                    ),
                    **(
                        {"repository_status": "PENDING_REPOSITORY_SURFACE"}
                        if language in PENDING_REPOSITORY_LANGUAGES
                        else {"repository_status": "LOCAL_REPOSITORY_READY"}
                    ),
                }
                for language in SUPPORTED_ROUTE_LANGUAGES
            },
            "deprecated_language_details": {
                language: {
                    "version": SHORT_VERSIONS[language],
                    "exact_versions": list(VERSIONS[language]),
                    "engine_path": ENGINE_PATHS[language],
                    "status": "DEPRECATED",
                    "retained_route_set": "javascript-node26-completion-18",
                }
                for language in DEPRECATED_ROUTE_LANGUAGES
            },
        "routes": routes,
    }
    transaction_documents = tuple(
        document
        for route, documents in prepared_v3_routes
        for document in _v3_research_route_transaction_documents(route, documents)
    ) + tuple(support_matrix_documents) + (
        (repo / "routes" / "inventory.json", _json_bytes(inventory_document)),
    )
    _transactional_write_bytes(routes_root, transaction_documents)


def run_route_checks(repo: Path, route: Path) -> int:
    # The conservative gate invokes validate_route.main in its own fresh
    # locked runtime before evaluating any gate policy.  Running the validator
    # as a separate process here would duplicate the complete native replay
    # and, for Swift routes, a second isolated analyzer build without adding an
    # independent authority boundary.
    completed = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "batch29" / "run_route_gate.py"),
            str(route),
        ],
        cwd=repo,
        check=False,
    )
    return completed.returncode


def ensure_route_scaffold(repo: Path, route_key: str) -> None:
    """Create only an allowlisted missing route directory through the Batch29 factory."""

    route = repo / "routes" / route_key
    if route.is_dir():
        return
    source, target = split_route_key(route_key)
    subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "batch29" / "scaffold_route.py"),
            "--source",
            source,
            "--target",
            target,
            "--repo-root",
            str(repo),
        ],
        cwd=repo,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inventory-only", action="store_true")
    mode.add_argument("--negative-only", action="store_true")
    mode.add_argument(
        "--route-set",
        choices=sorted(EXECUTABLE_ROUTE_SETS),
        help=(
            "run only the admitted mutable members of one exact route set; "
            "immutable legacy members are verified read-only"
        ),
    )
    mode.add_argument(
        "--prepare-route-set",
        choices=sorted(set(PREPARABLE_ROUTE_SETS) | set(READ_ONLY_ROUTE_SETS)),
        help="prepare complete NOT_RUN route scaffolds without claiming native execution",
    )
    mode.add_argument(
        "--verify-route-set",
        choices=sorted(READ_ONLY_ROUTE_SETS),
        help="verify an exact active or historical route set without writing or executing it",
    )
    mode.add_argument(
        "--route",
        type=parse_route_key,
        metavar="SOURCE-TO-TARGET",
        help=(
            "replay exactly one executable non-V3 mutable route, then run its "
            "validator and gate"
        ),
    )
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    if args.inventory_only:
        write_inventory(repo)
        print(
            "PASS: exact route inventory and support views synchronized; "
            "unexecuted routes remain NOT_RUN"
        )
        return 0
    if args.verify_route_set is not None:
        verify_route_set_read_only(
            repo,
            args.verify_route_set,
            READ_ONLY_ROUTE_SETS[args.verify_route_set],
        )
        print(
            f"PASS: exact route set {args.verify_route_set} verified read-only; "
            "route execution remains NOT_RUN"
        )
        return 0
    fixtures = repo / "engines" / "polyglot-route-engine" / "fixtures"
    if args.prepare_route_set is not None:
        if (
            args.prepare_route_set in READ_ONLY_ROUTE_SETS
            and args.prepare_route_set not in PREPARABLE_ROUTE_SETS
        ):
            raise RuntimeError(
                f"HISTORICAL_ROUTE_SET_READ_ONLY:{args.prepare_route_set}"
            )
        prepared_route_keys = PREPARABLE_ROUTE_SETS[args.prepare_route_set]
        preflight_route_set_preparation(
            repo, args.prepare_route_set, prepared_route_keys
        )
        if set(prepared_route_keys) & set(CORE_ROUTE_KEYS):
            legacy_campaign_authority(repo)
        v3_prepared_route_keys = tuple(
            route_key
            for route_key in prepared_route_keys
            if route_key in V3_EXACT_ROUTE_KEYS
        )
        if v3_prepared_route_keys:
            synchronize_v3_research_route_manifests(repo, v3_prepared_route_keys)
        for route_key in (
            route_key
            for route_key in prepared_route_keys
            if route_key not in CORE_ROUTE_KEYS
            and route_key not in V3_EXACT_ROUTE_KEYS
        ):
            ensure_route_scaffold(repo, route_key)
            source_value, target_value = split_route_key(route_key)
            source = cast(Language, source_value)
            target = cast(Language, target_value)
            route = configure_route(repo, source, target)
            populate_corpus(route, fixtures, source)
            if route_key in MODULE_EQUIVALENCE_ROUTE_KEYS:
                populate_module_corpus(route, fixtures, source)
            else:
                (route / "certification" / "module-equivalence.json").unlink(
                    missing_ok=True
                )
            write_not_run_route_scaffold(route, source, target)
        print(
            f"PASS: prepared mutable members of exact route set {args.prepare_route_set} "
            "as NOT_RUN / NOT_CERTIFIED; immutable legacy members were verified read-only"
        )
        return 0
    if args.negative_only:
        legacy_campaign_authority(repo)
        for route_key in EXECUTABLE_MUTABLE_ROUTE_KEYS:
            source, target = split_route_key(route_key)
            route = repo / "routes" / route_key
            reference = execute_negative(route, fixtures, source, target)  # type: ignore[arg-type]
            evidence_path = route / "certification" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["negative_runs"] = [reference]
            write_json(evidence_path, evidence)
        print(
            f"PASS: {len(EXECUTABLE_MUTABLE_ROUTE_KEYS)} executable mutable route negatives failed closed; "
            "immutable legacy 30 verified read-only"
        )
        return 0
    if args.route is not None:
        source, target = args.route
        requested_route_key = f"{source}-to-{target}"
        preflight_route_set_execution((requested_route_key,))
        if requested_route_key in CORE_ROUTE_KEYS:
            legacy_campaign_authority(repo)
            raise RuntimeError(
                "LEGACY_ROUTE_IMMUTABLE_REEXECUTION_REQUIRES_NEW_PACK_VERSION:"
                f"{requested_route_key}"
            )
        selected = [args.route]
    else:
        selected_name = args.route_set or "legacy-complete-30"
        requested_route_keys = EXECUTABLE_ROUTE_SETS[selected_name]
        preflight_route_set_execution(requested_route_keys)
        if set(requested_route_keys) & set(CORE_ROUTE_KEYS):
            legacy_campaign_authority(repo)
        selected = [
            split_route_key(route_key)
            for route_key in requested_route_keys
            if route_key not in CORE_ROUTE_KEYS
        ]
        if not selected:
            print(
                "PASS: immutable legacy-complete-30 campaign and exact-three "
                "pack-captured replay authority verified read-only; native reexecution NOT_RUN"
            )
            return 0
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
    print(
        f"PASS: exact route set {selected_name} ran {len(selected)} admitted mutable "
        "route(s); any immutable legacy members were verified read-only; "
        "decision remains NOT_CERTIFIED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
