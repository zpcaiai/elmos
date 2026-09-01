"""Pure, side-effect-free runtime metadata authority for Batch 29 routes."""

from __future__ import annotations

import hashlib
import html
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
SUPPORT_CAPABILITY_STATUSES = frozenset(
    {
        "certified",
        "supported",
        "conditional",
        "experimental",
        "detected-only",
        "blocked",
    }
)
_MARKDOWN_TEXT_META = frozenset("\\`*_{}[]()#!|~^$")
V3_RESEARCH_SUPPORT_CAPABILITIES = (
    (
        "type-system",
        "experimental",
        "deterministic-lowering",
        "Analyzer and emitter components are locally available, but no route "
        "semantic or target profile is admitted; route execution remains NOT_RUN.",
    ),
    (
        "generics",
        "detected-only",
        "obligation",
        "Generic syntax may be detected, but direction-specific lowering and "
        "route execution evidence remain NOT_RUN.",
    ),
    (
        "nullability",
        "detected-only",
        "obligation",
        "Nullability may be detected, but no direction-specific nullability "
        "contract or route execution evidence has been admitted.",
    ),
    (
        "numeric",
        "detected-only",
        "obligation",
        "Numeric syntax may be detected, but no direction-specific numeric "
        "semantics or route execution evidence has been admitted.",
    ),
    (
        "time",
        "detected-only",
        "obligation",
        "Time-related syntax may be detected, but no direction-specific time "
        "contract or route execution evidence has been admitted.",
    ),
    (
        "exceptions",
        "detected-only",
        "obligation",
        "Exception syntax may be detected, but no direction-specific exception "
        "contract or route execution evidence has been admitted.",
    ),
    (
        "async",
        "detected-only",
        "obligation",
        "Async syntax may be detected, but async behavior has no admitted route "
        "profile and route execution remains NOT_RUN.",
    ),
    (
        "concurrency",
        "blocked",
        "human-review",
        "Concurrency requires a direction-specific semantic contract, runtime "
        "campaign, and independent evidence; none has run.",
    ),
    (
        "reflection",
        "blocked",
        "human-review",
        "Reflection requires a direction-specific semantic contract, runtime "
        "campaign, and independent evidence; none has run.",
    ),
    (
        "serialization",
        "detected-only",
        "contract-mapping",
        "Serialization boundaries may be detected, but no exact wire contract "
        "or route execution evidence has been admitted.",
    ),
    (
        "interop",
        "blocked",
        "retain-runtime-or-sidecar",
        "Interop requires an explicit boundary plan and independently verified "
        "runtime evidence; neither has been admitted.",
    ),
)

LEGACY_PACK_KEY = "polyglot-30-route-formal-equivalence-v1"
LEGACY_CAMPAIGN_RELATIVE = (
    f"verification-packs/{LEGACY_PACK_KEY}/formal-route-campaign.json"
)
LEGACY_CAMPAIGN_SHA256 = (
    "sha256:4a31a2c67e0f2aaa03ba24b343abb4f60dd8b600121fb9cf7cd77aa1cba95c9c"
)
LEGACY_CAMPAIGN_BYTES = 578_643
LEGACY_REPLAY_METHOD_SHA256 = (
    "sha256:52a1e58a6c044eb5744bd70e1de43d6880bb7bd2e34838ae237503ec87a78ec"
)
LEGACY_REPLAY_ASSET_IDENTITIES = {
    "certification/replay/validate_packed_route.py": {
        "role": "launcher",
        "sha256": "sha256:d7cf4017a6d0296c01f880e568950ef6b1dd341b61b48a09b90d61e0cff686da",
        "bytes": 6_753,
    },
    "certification/replay/scripts/batch29/validate_route.py": {
        "role": "validator",
        "sha256": "sha256:650470cc8078fe8158eea881885ccd5390ea68d2eb81b4809ed6b672c553c6f9",
        "bytes": 95_431,
    },
    "certification/replay/schemas/batch29/formal-equivalence-evidence.schema.json": {
        "role": "schema",
        "sha256": "sha256:c4821219c01e037ca86bb749f7790a892b612e2c6d0cfd382eb40c503a0280c7",
        "bytes": 11_670,
    },
}


def _markdown_field(value: str, invalid_code: str) -> str:
    """Normalize one bounded Markdown field and escape embedded HTML."""

    if not value.strip() or any(
        (ord(character) < 32 and character not in "\r\n\t")
        or 127 <= ord(character) <= 159
        for character in value
    ):
        raise ValueError(invalid_code)
    normalized = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return html.escape(normalized, quote=False)


def _markdown_text(value: str, invalid_code: str) -> str:
    """Escape Markdown metacharacters in a normal inline-text context."""

    normalized = _markdown_field(value, invalid_code)
    return "".join(
        f"\\{character}" if character in _MARKDOWN_TEXT_META else character
        for character in normalized
    )


def _markdown_code(value: str, invalid_code: str) -> str:
    """Return a code span whose fence cannot be closed by document content."""

    normalized = _markdown_field(value, invalid_code)
    longest_run = 0
    current_run = 0
    for character in normalized:
        if character == "`":
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    fence = "`" * (longest_run + 1)
    padding = " " if normalized.startswith("`") or normalized.endswith("`") else ""
    return f"{fence}{padding}{normalized}{padding}{fence}"


def v3_research_support_document(route_key: str) -> dict[str, Any]:
    """Build the exact non-promoted support contract for one V3 route."""

    from route_sets import V3_EXACT_ROUTE_KEYS

    if route_key not in V3_EXACT_ROUTE_KEYS:
        raise ValueError(f"V3_ROUTE_KEY_REQUIRED:{route_key}")
    return {
        "schema_version": 1,
        "route_key": route_key,
        "capabilities": [
            {
                "id": capability_id,
                "status": status,
                "strategy": strategy,
                "reason": reason,
                "evidence_refs": [],
            }
            for capability_id, status, strategy, reason in (
                V3_RESEARCH_SUPPORT_CAPABILITIES
            )
        ],
    }


def support_matrix_markdown_bytes(
    route_key: str,
    source_bytes: bytes,
    document: dict[str, Any],
) -> bytes:
    """Render the human view from the exact machine-readable JSON bytes."""

    try:
        decoded = json.loads(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"SUPPORT_MATRIX_DOCUMENT_INVALID:{route_key}") from exc
    capabilities = document.get("capabilities")
    if (
        not isinstance(route_key, str)
        or not route_key.strip()
        or decoded != document
        or set(document) != {"schema_version", "route_key", "capabilities"}
        or document.get("schema_version") != 1
        or document.get("route_key") != route_key
        or not isinstance(capabilities, list)
        or not capabilities
    ):
        raise ValueError(f"SUPPORT_MATRIX_DOCUMENT_INVALID:{route_key}")

    document_invalid = f"SUPPORT_MATRIX_DOCUMENT_INVALID:{route_key}"
    capability_invalid = f"SUPPORT_MATRIX_CAPABILITY_INVALID:{route_key}"
    rendered_route_key = _markdown_text(route_key, document_invalid)
    sections: list[str] = []
    for raw in capabilities:
        if not isinstance(raw, dict) or set(raw) != {
            "id",
            "status",
            "strategy",
            "reason",
            "evidence_refs",
        }:
            raise ValueError(f"SUPPORT_MATRIX_CAPABILITY_INVALID:{route_key}")
        capability_id = raw.get("id")
        status = raw.get("status")
        strategy = raw.get("strategy")
        reason = raw.get("reason")
        evidence_refs = raw.get("evidence_refs")
        if (
            not all(
                isinstance(value, str) and value
                for value in (capability_id, status, strategy, reason)
            )
            or not isinstance(evidence_refs, list)
            or any(not isinstance(value, str) or not value for value in evidence_refs)
        ):
            raise ValueError(capability_invalid)
        if status not in SUPPORT_CAPABILITY_STATUSES or (
            status == "certified" and not evidence_refs
        ):
            raise ValueError(capability_invalid)
        evidence = (
            ", ".join(
                _markdown_code(value, capability_invalid) for value in evidence_refs
            )
            or "None"
        )
        sections.append(
            "\n".join(
                (
                    f"## {_markdown_text(capability_id, capability_invalid)}",
                    "",
                    f"- Status: {_markdown_code(status, capability_invalid)}",
                    f"- Strategy: {_markdown_code(strategy, capability_invalid)}",
                    f"- Evidence: {evidence}",
                    f"- Reason: {_markdown_text(reason, capability_invalid)}",
                )
            )
        )
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    content = (
        f"# Support matrix: {rendered_route_key}\n\n"
        "Generated from the route's authoritative `../support-matrix.json`; "
        "this view does not create execution or certification evidence.\n\n"
        f"- Source SHA-256: `sha256:{source_sha256}`\n"
        f"- Source bytes: `{len(source_bytes)}`\n\n"
        + "\n\n".join(sections)
        + "\n"
    )
    return content.encode("utf-8")


def legacy_route_execution_authority_document() -> dict[str, Any]:
    """Return the exact immutable legacy campaign authority."""

    replay_assets = {
        str(identity["role"]): {
            "path": relative,
            "sha256": str(identity["sha256"]),
            "bytes": int(identity["bytes"]),
        }
        for relative, identity in LEGACY_REPLAY_ASSET_IDENTITIES.items()
    }
    authority: dict[str, Any] = {
        "policy": "immutable-pack-captured-v1",
        "pack_key": LEGACY_PACK_KEY,
        "route_set": "legacy-complete-30",
        "route_count": 30,
        "campaign": {
            "path": LEGACY_CAMPAIGN_RELATIVE,
            "sha256": LEGACY_CAMPAIGN_SHA256,
            "bytes": LEGACY_CAMPAIGN_BYTES,
        },
        "replay_assets": replay_assets,
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
    return authority


def route_execution_authorities_document() -> dict[str, Any]:
    """Return every exact route-set execution authority as a fresh document."""

    return {
        "legacy-complete-30": legacy_route_execution_authority_document(),
        "cpp-objc-swift-java-exact-8": {
            "policy": "current-versioned-campaign",
            "native_reexecution_status": "NOT_RUN",
        },
        "nine-language-completion-34": {
            "policy": "current-versioned-route-evidence",
            "native_reexecution_status": "NOT_RUN",
        },
        "javascript-node26-completion-18": {
            "policy": "historical-read-only-route-evidence",
            "native_reexecution_status": "NOT_RUN",
        },
        "php-php85-completion-20": {
            "policy": "mixed-provenance-read-only-route-evidence",
            "active_execution_selection": "php-php85-active-completion-18",
            "native_reexecution_status": "NOT_RUN",
        },
        "kotlin-react-flutter-completion-66": {
            "policy": "local-analyzers-and-repository-surfaces-ready",
            "native_reexecution_status": "NOT_RUN",
        },
    }


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
    "kotlin": "71be41a8096b4c35bf41a7438a4b8bef2be1217905bf94ba25e2c3b69f0ddd7b",
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
    "e6f62f8d7766e219a0926ce1ae3c542e02f7e823859b59ff6e27421c5d51e46f"
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
