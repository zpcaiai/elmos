"""Pure, side-effect-free runtime metadata authority for Batch 29 routes."""

from __future__ import annotations

import hashlib
import json
from typing import Any


V3_RESEARCH_ROUTE_VERSION = "0.1.0"
V3_RESEARCH_DECLARED_SCOPE = "NO_ROUTE_PROFILE_ADMITTED"
V3_RESEARCH_ISSUED_AT = "2026-08-09T00:00:00+00:00"
V3_RESEARCH_NEXT_REVIEW_AT = "2026-11-24T00:00:00+00:00"
V3_RESEARCH_GATE_KEYS = (
    "local_execution",
    "external_execution",
    "independent_verification",
)
V3_RESEARCH_METRIC_KEYS = (
    "build_green_rate",
    "first_build_pass_rate",
    "p0_behavior_pass_rate",
    "source_map_coverage",
    "manual_hours",
    "cost_per_verified_workload",
)


def v3_research_gate_results() -> dict[str, str]:
    """Return a fresh, non-vacuous fail-closed V3 route gate result."""

    return {key: "NOT_RUN" for key in V3_RESEARCH_GATE_KEYS}


def v3_research_metrics() -> dict[str, None]:
    """Return unmeasured V3 metrics without manufacturing successful zeros."""

    return {key: None for key in V3_RESEARCH_METRIC_KEYS}


def v3_research_evidence_document(route_key: str) -> dict[str, Any]:
    """Build the exact raw-evidence contract for one unexecuted V3 route."""

    return {
        "schema_version": 1,
        "route_key": route_key,
        "route_version": V3_RESEARCH_ROUTE_VERSION,
        "route_maturity": "RESEARCH",
        "execution_status": "NOT_RUN",
        "module_execution_status": "NOT_RUN",
        "repository_execution_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "external_certification_status": "NOT_RUN",
        "runs": [],
        "negative_runs": [],
        "metrics": v3_research_metrics(),
        "critical_unknown_semantics": None,
        "critical_behavior_regressions": None,
        "test_integrity_violations": None,
        "notes": [
            "No V3 route-level semantic profile or target profile has been admitted.",
            "Analyzer and emitter bindings are metadata, not route execution evidence.",
            "Local, repository, independent, external, customer, and production evidence remain NOT_RUN.",
        ],
    }


def v3_research_certification_document(route_key: str) -> dict[str, Any]:
    """Build the exact non-certified decision for one unexecuted V3 route."""

    return {
        "schema_version": 1,
        "route_key": route_key,
        "route_version": V3_RESEARCH_ROUTE_VERSION,
        "status": "research",
        "certification_decision": "NOT_CERTIFIED",
        "declared_scope": V3_RESEARCH_DECLARED_SCOPE,
        "gate_results": v3_research_gate_results(),
        "metrics": v3_research_metrics(),
        "evidence_refs": [],
        "issued_at": V3_RESEARCH_ISSUED_AT,
        "next_review_at": V3_RESEARCH_NEXT_REVIEW_AT,
    }


# Exact ``ExactToolchain`` receipt authority.  The ordered active tuple is
# deliberately independent of the human-facing dictionaries below, which also
# retain deprecated JavaScript metadata.  Both the producer and the central
# runtime doctor recompute the contract digest from these values before trusting
# any receipt.
EXACT_TOOLCHAIN_RECEIPT_SCHEMA_VERSION = "1.1.0"
EXACT_TOOLCHAIN_ACTIVE_LANGUAGES = (
    "java",
    "python",
    "csharp",
    "typescript",
    "go",
    "rust",
    "cpp",
    "objc",
    "swift",
    "php",
    "kotlin",
    "react",
    "flutter",
)
EXACT_TOOLCHAIN_DEPRECATED_LANGUAGES = ("javascript",)


# Exact ``ExactToolchain.version`` values emitted by the route-engine receipt.
# These are intentionally distinct from the human-facing VERSIONS and
# SHORT_VERSIONS values below. The receipt producer and central doctor both
# consume this tuple so a marketing-version match cannot hide engine drift.
EXACT_TOOLCHAIN_VERSIONS: dict[str, str] = {
    "java": "21.0.11",
    "python": "3.12.12+20260211",
    "csharp": "10.0.301",
    "typescript": "5.9.2 / Node 26.0.0",
    "go": "1.25.0",
    "rust": "1.89.0",
    "cpp": "Apple clang version 21.0.0 (clang-2100.1.1.101)",
    "objc": "Apple clang version 21.0.0 (clang-2100.1.1.101)",
    "swift": (
        "Apple Swift version 6.3.3 "
        "(swiftlang-6.3.3.1.3 clang-2100.1.1.101)"
    ),
    "php": "PHP 8.5.9 (cli) (built: Jul 28 2026 13:06:52) (NTS)",
    "kotlin": "kotlinc-jvm 2.2.20 (JRE 21.0.11)",
    "react": (
        "React 19.2.7 / React DOM 19.2.7 / TypeScript 5.9.2 / Node 26.0.0"
    ),
    "flutter": "Flutter 3.44.1 / Dart 3.12.1",
}


# SHA-256 over each complete portable ExactToolchain record, including its
# language, exact version, executable and auxiliary identities, full ordered
# profile, and executable digests. Kotlin paths below its governed shared
# install root use ``<polyglot-toolchain-root>``; moving the same byte-identical
# pinned tree between approved absolute roots therefore preserves the record,
# while a relative path, path escape, profile edit, executable replacement,
# tree change, JAR change, JVM change, or auxiliary drift still changes it.
EXACT_TOOLCHAIN_RECORD_SHA256: dict[str, str] = {
    "java": "5c7afc06a2fa1a92d4bcc4034773f77c78df623d89b451f154cadbb16f92c32e",
    "python": "c923d7711e0c8cc7cb70a3f5d042cf9a76d6b78f52846513d9b5253925d6a4c7",
    "csharp": "9568b7bf8845e3f99e4231f861c89fc28339d1149ea20cb36a99eab7b02505ba",
    "typescript": "0851a20c0504992959d674e16c291dc923865969ba8571f8c8ef6604339e0872",
    "go": "68148dfcead6e11f0d85ea6e9fd22e5e1fed88a8ce18e5f547818e023653f6b6",
    "rust": "d033956010ef8bc88c0dc4ce4db0e509013830eacf6bb7e73c29ae77c4e490d6",
    "cpp": "5640f0ce9e65fd7d4a5616f8754f7511c9ddb06d9c90cd6d1ec2a199f017966b",
    "objc": "fbb108ab8528c620f48ec4a12bcde14d284d625b6667493f78ef20ecda63463d",
    "swift": "4f672b92ce63ea95cb8b4cc115f6ca496b3f06aac8de21020e548373ac4a4057",
    "php": "afcfdfd6ee3cfbe5b94eae687b35b86ee63de868e29e70769200aa9c2f4e9bdb",
    "kotlin": "5798779eb5d7de33e6eb76a925f467d683b51da85cde37724ae4504d18a2aae2",
    "react": "e36637f8e855a4e7b4c64275ab0d1995368318c0e14572fef87a8e652b865884",
    "flutter": "9da3d455a7d37a42acc7f709b9843def354de5e2277763f4b69cfc215ea6e160",
}


def exact_toolchain_record_sha256(record: object) -> str:
    """Return the canonical digest used for one full portable record."""

    return hashlib.sha256(
        json.dumps(
            record,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def exact_toolchain_contract_document() -> dict[str, object]:
    """Return the complete ordered exact-toolchain receipt contract."""

    return {
        "receipt_schema_version": EXACT_TOOLCHAIN_RECEIPT_SCHEMA_VERSION,
        "active_languages": list(EXACT_TOOLCHAIN_ACTIVE_LANGUAGES),
        "deprecated_languages": list(EXACT_TOOLCHAIN_DEPRECATED_LANGUAGES),
        "versions": {
            language: EXACT_TOOLCHAIN_VERSIONS[language]
            for language in EXACT_TOOLCHAIN_ACTIVE_LANGUAGES
        },
        "record_sha256": {
            language: EXACT_TOOLCHAIN_RECORD_SHA256[language]
            for language in EXACT_TOOLCHAIN_ACTIVE_LANGUAGES
        },
    }


def exact_toolchain_contract_sha256() -> str:
    """Recompute the whole contract digest from its authoritative fields."""

    return exact_toolchain_record_sha256(exact_toolchain_contract_document())


# A literal pin, rather than an alias to the computed value, makes accidental
# edits to any version, record hash, language order, or deprecated language fail
# closed until the complete contract is intentionally re-pinned.
EXACT_TOOLCHAIN_CONTRACT_SHA256 = (
    "3e62e8500c6c041315fdec52eeafd3cc2a3d6a82da1b7ae7862c741d381eedbd"
)


VERSIONS: dict[str, tuple[str, ...]] = {
    "java": ("Java 21.0.11", "JDK Compiler Tree API"),
    "python": ("Python 3.12.12", "CPython AST"),
    "csharp": ("C# 14", ".NET SDK 10.0.301", "Roslyn 5.6.0"),
    "typescript": ("TypeScript 5.9.2", "Node.js 26.0.0"),
    "javascript": (
        "JavaScript ES2022",
        "Node.js 26.0.0",
        "ECMAScript Modules (ESM)",
        "exact JSDoc canonical types",
    ),
    "go": ("Go 1.25.0", "go/parser AST"),
    "rust": ("Rust 1.89.0", "syn 2.0.119"),
    "cpp": (
        "C++20",
        "Apple clang version 21.0.0 (clang-2100.1.1.101)",
        "arm64-apple-darwin25.6.0",
    ),
    "objc": (
        "Objective-C",
        "Apple clang version 21.0.0 (clang-2100.1.1.101)",
        "arm64-apple-darwin25.6.0",
        "Foundation",
    ),
    "swift": (
        "Apple Swift 6.3.3 (swiftlang-6.3.3.1.3 clang-2100.1.1.101)",
        "arm64-apple-macosx26.0",
        "SwiftSyntax 600.0.1",
    ),
    "php": (
        "PHP 8.5.9 (cli) (built: Jul 28 2026 13:06:52) (NTS)",
        "ext/tokenizer Zend token stream",
        "strict_types=1",
    ),
    "kotlin": ("Kotlin 2.2.20", "JDK 21.0.11", "Kotlin compiler PSI"),
    "react": (
        "React 19.2.7",
        "React DOM 19.2.7",
        "TypeScript 5.9.2 Compiler API",
        "Node.js 26.0.0",
    ),
    "flutter": (
        "Flutter 3.44.1 revision 924134a44c189315be2148659913dda1671cbe99",
        "Dart 3.12.1",
        "analyzer 10.1.0",
        "_fe_analyzer_shared 95.0.0",
    ),
}

ENGINE_PATHS: dict[str, str] = {
    "java": "engines/polyglot-route-engine/native/java/Analyzer.java",
    "python": "engines/polyglot-route-engine/src/elmos_polyglot_route/python_analyzer.py",
    "csharp": "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli",
    "typescript": "engines/frontend-client-engine/src/polyglot.ts",
    "javascript": "engines/polyglot-route-engine/native/javascript/analyzer.mjs",
    "go": "engines/polyglot-route-engine/native/go/analyzer.go",
    "rust": "engines/polyglot-route-engine/native/rust/src/main.rs",
    "cpp": "engines/polyglot-route-engine/src/elmos_polyglot_route/clang_analyzer.py",
    "objc": "engines/polyglot-route-engine/src/elmos_polyglot_route/clang_analyzer.py",
    "swift": "engines/polyglot-route-engine/native/swift/Sources/ElmosSwiftAnalyzer/main.swift",
    "php": "engines/polyglot-route-engine/native/php/analyzer.php",
    "kotlin": "engines/polyglot-route-engine/native/kotlin/analyzer.kt",
    "react": "engines/polyglot-route-engine/native/react/analyzer.mjs",
    "flutter": "engines/polyglot-route-engine/native/dart/analyzer.dart",
}

SHORT_VERSIONS: dict[str, str] = {
    "java": "21.0.11",
    "python": "3.12.12",
    "csharp": "10.0.301",
    "typescript": "5.9.2 / Node 26.0.0",
    "javascript": "Node.js 26.0.0 / ES2022 / ESM",
    "go": "1.25.0",
    "rust": "1.89.0",
    "cpp": "C++20 / Apple clang 21.0.0 / arm64-apple-darwin25.6.0",
    "objc": "Objective-C / Apple clang 21.0.0 / arm64-apple-darwin25.6.0",
    "swift": "Swift 6.3.3 / arm64-apple-macosx26.0",
    "php": "PHP 8.5.9 (NTS) / ext/tokenizer",
    "kotlin": "Kotlin 2.2.20 / JDK 21.0.11 / compiler PSI",
    "react": "React 19.2.7 / TypeScript 5.9.2 / Node 26.0.0",
    "flutter": "Flutter 3.44.1 / Dart 3.12.1 / analyzer 10.1.0",
}
