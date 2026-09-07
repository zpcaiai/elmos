from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

import elmos_polyglot_route.engine as route_engine
from elmos_polyglot_route.emitter import EmittedFile, emit
from elmos_polyglot_route.engine import (
    _bind_function_spans_from_inventory,
    _build_whole_file_closure,
    _close_profile_inventory,
    _combine_function_irs,
    _emitted_helper_regions,
    _profile_symbol_record,
    _target_call_graph,
    _verify_inventory_artifact,
    migrate,
    migrate_module,
    verify_pure_module,
)
from elmos_polyglot_route.equivalence import (
    _module_function_index,
    canonical_json_bytes,
    chunk_equivalence,
    module_equivalence,
    semantic_equivalence,
    sha256_bytes,
)
from elmos_polyglot_route.identifier_hygiene import (
    alpha_normalize_target,
    identifier_plan_bytes,
    plan_identifiers,
    target_ir_view,
)
from elmos_polyglot_route.models import Expression, Language, RouteError, SemanticIR, SourceSpan, Statement
from elmos_polyglot_route.native import analyze, inventory_module
from elmos_polyglot_route.toolchains import exact_toolchain

SOURCE_BYTES = b"s" * 4_000
TARGET_BYTES = b"t" * 4_000
SOURCE_DIGEST = sha256_bytes(SOURCE_BYTES)
TARGET_DIGEST = sha256_bytes(TARGET_BYTES)
CORPUS_DIGEST = "sha256:" + "c" * 64
ENGINE_ROOT = Path(__file__).resolve().parents[1]

JAVASCRIPT_ROUTE_RETIRED = pytest.mark.skip(
    reason=(
        "javascript is deprecated; engine.migrate rejects the direction with "
        "UNSUPPORTED_DIRECTED_ROUTE before any Node.js specific logic runs"
    )
)


def _require_native_toolchain(language: str) -> None:
    try:
        exact_toolchain(language)  # type: ignore[arg-type]
    except RouteError as error:
        pytest.skip(str(error))


def _span(file: str, start: int, end: int) -> dict[str, object]:
    return {"source_span": {"file": file, "start_byte": start, "end_byte": end}}


def _binary_function(
    file: str,
    name: str,
    operator: str,
    base: int,
) -> dict[str, object]:
    return {
        "name": name,
        "parameters": [
            {"name": "left", "type": "integer", **_span(file, base + 10, base + 20)},
            {"name": "right", "type": "integer", **_span(file, base + 30, base + 41)},
        ],
        "return_type": "integer",
        "body": [
            {
                "kind": "return",
                "expression": {
                    "kind": "binary",
                    "operator": operator,
                    "left": {"kind": "name", "value": "left", **_span(file, base + 130, base + 140)},
                    "right": {
                        "kind": "name",
                        "value": "right",
                        **_span(file, base + 160, base + 171),
                    },
                    **_span(file, base + 120, base + 180),
                },
                **_span(file, base + 100, base + 200),
            }
        ],
        **_span(file, base, base + 300),
    }


def _minimum_function(file: str, base: int) -> dict[str, object]:
    return {
        "name": "minimum",
        "parameters": [
            {"name": "left", "type": "integer", **_span(file, base + 10, base + 20)},
            {"name": "right", "type": "integer", **_span(file, base + 30, base + 41)},
        ],
        "return_type": "integer",
        "body": [
            {
                "kind": "if",
                "condition": {
                    "kind": "binary",
                    "operator": "<",
                    "left": {"kind": "name", "value": "left", **_span(file, base + 120, base + 130)},
                    "right": {
                        "kind": "name",
                        "value": "right",
                        **_span(file, base + 150, base + 161),
                    },
                    **_span(file, base + 110, base + 170),
                },
                "then": [
                    {
                        "kind": "return",
                        "expression": {
                            "kind": "name",
                            "value": "left",
                            **_span(file, base + 220, base + 230),
                        },
                        **_span(file, base + 200, base + 250),
                    }
                ],
                "else": [
                    {
                        "kind": "return",
                        "expression": {
                            "kind": "name",
                            "value": "right",
                            **_span(file, base + 320, base + 331),
                        },
                        **_span(file, base + 300, base + 350),
                    }
                ],
                **_span(file, base + 90, base + 380),
            }
        ],
        **_span(file, base, base + 500),
    }


def _module(language: str, file: str, offset: int = 0) -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": language,
            "source_file": file,
            "analyzer": f"test-{language}",
            "analyzer_version": "1",
            "functions": [
                _binary_function(file, "add", "+", offset + 100),
                _binary_function(file, "subtract", "-", offset + 1_100),
                _minimum_function(file, offset + 2_100),
            ],
            "diagnostics": [],
        }
    )


def _manifest(source: SemanticIR) -> dict[str, object]:
    cases = {
        "add": [{"args": [2, 3], "expected": 5}, {"args": [-2, 3], "expected": 1}],
        "subtract": [{"args": [7, 2], "expected": 5}, {"args": [-2, 3], "expected": -5}],
        "minimum": [{"args": [7, 2], "expected": 2}, {"args": [-2, 3], "expected": -2}],
    }
    return {
        "schema_version": "1.0.0",
        "profile": "typed-pure-module-v1",
        "composition": {
            "call_graph": [],
            "global_state": "none",
            "effects": "none",
            "exceptions": "canonical-arithmetic-errors-only",
            "input_domain": "canonical-finite-no-error-input-domain",
        },
        "functions": [
            {
                "symbol": function.name,
                "signature": function.signature_mapping(),
                "cases": cases[function.name],
            }
            for function in source.functions
        ],
    }


def _observations(manifest: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for entry in manifest["functions"]:  # type: ignore[index,union-attr]
        result[entry["symbol"]] = [  # type: ignore[index]
            {"case_id": index, "status": "RETURNED", "value": case["expected"]}
            for index, case in enumerate(entry["cases"])  # type: ignore[index]
        ]
    return result


def _equivalent_inputs() -> tuple[
    SemanticIR,
    SemanticIR,
    dict[str, object],
    dict[str, list[dict[str, object]]],
    EmittedFile,
]:
    source = _module("python", "module.py")
    target = _module("java", "Migrated.java", 50)
    manifest = _manifest(source)
    observations = _observations(manifest)
    emitted = EmittedFile(relative_path="Migrated.java", content=TARGET_BYTES.decode("ascii"))
    return source, target, manifest, observations, emitted


def _synthetic_inventory(ir: SemanticIR, artifact: bytes) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-inventory",
        "profile": "typed-pure-module-v1",
        "source_language": ir.source_language,
        "source_file": ir.source_file,
        "analyzer": ir.analyzer,
        "analyzer_version": ir.analyzer_version,
        "enumeration_status": "PASSED",
        "subjects": [],
        "diagnostics": [],
        "source_artifact_sha256": sha256_bytes(artifact),
        "source_artifact_bytes": len(artifact),
    }


def _synthetic_swift_build_receipt() -> dict[str, object]:
    digest = "sha256:" + "a" * 64
    dependency_digest = "sha256:b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
    dependency_revision = "0687f71944021d616d34d922343dcef086855920"
    dependency_cache_key = "swift-syntax-standalone-v2-600.0.1-" + dependency_revision + "-" + dependency_digest[7:]
    binary_root = Path("/private/tmp/elmos-swift-analyzer-test")
    binary = {
        "name": "ElmosSwiftAnalyzer",
        "path": str(binary_root / "ElmosSwiftAnalyzer"),
        "sha256": digest,
        "bytes": 1,
        "mode": "0500",
        "uid": os.getuid(),
        "gid": os.getgid(),
        "nlink": 1,
        "device": 1,
        "inode": 2,
    }
    toolchain = route_engine._swift_toolchain_receipt(exact_toolchain("swift"))
    probe_compiler = next(
        component for component in toolchain["build_closure"]["components"] if component["role"] == "clang"
    )
    probe_root = binary_root / "network-probe-execution"
    probe_binary = {
        "name": route_engine._SANDBOX_NETWORK_PROBE_BINARY_NAME,
        "path": str(probe_root / route_engine._SANDBOX_NETWORK_PROBE_BINARY_NAME),
        "sha256": "sha256:" + route_engine._SANDBOX_NETWORK_PROBE_BINARY_SHA256,
        "bytes": route_engine._SANDBOX_NETWORK_PROBE_BINARY_BYTES,
        "mode": "0500",
        "uid": os.getuid(),
        "gid": os.getgid(),
        "nlink": 1,
        "device": 1,
        "inode": 4,
    }
    receipt: dict[str, object] = {
        "schema_version": "1.0.0",
        "kind": "elmos.swift-analyzer-build-receipt",
        "source_inputs": {
            "sha256": digest,
            "files": [
                {"path": "Package.swift", "sha256": digest, "bytes": 1},
                {"path": "Package.resolved", "sha256": digest, "bytes": 1},
                {"path": "Sources/Analyzer/main.swift", "sha256": digest, "bytes": 1},
            ],
        },
        "dependency": {
            "identity": "swift-syntax",
            "version": "600.0.1",
            "revision": dependency_revision,
            "sha256": dependency_digest,
            "file_count": 753,
            "bytes": 8_866_479,
            "mirror": {
                "seed": "verified-content-addressed-standalone-cache",
                "cache": {
                    "cache_key": dependency_cache_key,
                    "cache_schema": "swift-dependencies-standalone-v2",
                    "object_store_policy": "standalone-no-alternates-no-hardlinks-v2",
                    "identity": "swift-syntax",
                    "version": "600.0.1",
                    "revision": dependency_revision,
                    "seed": "verified-content-addressed-standalone-cache",
                    "sha256": dependency_digest,
                    "file_count": 753,
                    "bytes": 8_866_479,
                },
                "git": {
                    "path": "/Applications/Xcode.app/Contents/Developer/usr/bin/git",
                    "sha256": "sha256:10f9c1df894525ae4c7454258febab6d3d25071062b42cb48dbb1842cdffd2a9",
                    "version": "git version 2.50.1 (Apple Git-155)",
                },
                "identity": "swift-syntax",
                "version": "600.0.1",
                "revision": dependency_revision,
                "sha256": dependency_digest,
                "file_count": 753,
                "bytes": 8_866_479,
            },
        },
        "toolchain": toolchain,
        "network_isolation": {
            "status": "PASSED",
            "scope": "swift-build-process-tree",
            "sandbox": {
                "path": "/usr/bin/sandbox-exec",
                "sha256": "sha256:abc5bb136d6b5cce8fa85d789f78e3326c51ca60cae637b2064adfb67a1dcd9a",
                "bytes": 102_368,
                "mode": "0755",
                "uid": 0,
                "gid": 0,
                "nlink": 1,
                "cdhash_full": "4828e16826baf4052b8212b82d1f3f2c13216303e062f0cc2b398f045d422625",
            },
            "verifier": {
                "path": "/usr/bin/codesign",
                "sha256": "sha256:844d30a12929b59c9f2215e2a308c3e1db572831a478f35906e452a54025603e",
                "bytes": 458_576,
                "mode": "0755",
                "uid": 0,
                "gid": 0,
                "nlink": 1,
            },
            "policy": {
                "text": "(version 1)\n(allow default)\n(deny network*)\n",
                "sha256": sha256_bytes(b"(version 1)\n(allow default)\n(deny network*)\n"),
                "bytes": 44,
            },
            "probe": {
                "result": "NETWORK_DENIED:1",
                "source": {
                    "text": route_engine._SANDBOX_NETWORK_PROBE_SOURCE,
                    "sha256": "sha256:" + route_engine._SANDBOX_NETWORK_PROBE_SOURCE_SHA256,
                    "bytes": route_engine._SANDBOX_NETWORK_PROBE_SOURCE_BYTES,
                },
                "build": {
                    "environment_policy": "sanitized-swift-build-deterministic-v1",
                    "argv": list(route_engine._SANDBOX_NETWORK_PROBE_BUILD_ARGV),
                    "environment": dict(route_engine._SANDBOX_NETWORK_PROBE_BUILD_ENVIRONMENT),
                    "compiler": probe_compiler,
                },
                "binary": probe_binary,
                "execution_seal": {
                    "policy": "private-nonwritable-execution-root-v1",
                    "root": str(probe_root),
                    "mode": "0500",
                    "uid": os.getuid(),
                    "gid": os.getgid(),
                    "device": 1,
                    "inode": 3,
                    "binary": probe_binary,
                },
                "mach_o": {
                    "architecture": "arm64",
                    "file_type": "MH_EXECUTE",
                    "uuid": route_engine._SANDBOX_NETWORK_PROBE_UUID,
                    "cdhash_full": route_engine._SANDBOX_NETWORK_PROBE_CDHASH_FULL,
                    "linked_libraries": list(route_engine._SANDBOX_NETWORK_PROBE_LINKED_LIBRARIES),
                },
            },
        },
        "build": {
            "configuration": "release",
            "automatic_resolution": False,
            "manifest_cache": "none",
            "environment_policy": "minimal-empty-home-deterministic-v1",
            "deterministic_environment": {
                "SOURCE_DATE_EPOCH": "0",
                "SWIFT_DETERMINISTIC_HASHING": "1",
                "ZERO_AR_DATE": "1",
            },
            "mtime_normalization": {
                "epoch_nanoseconds": 0,
                "scope": ["source-snapshot", "dependency-mirror"],
            },
            "reproducible_path_policy": "debug-file-macro-prefix-map-no-uuid-v1",
            "argv": [
                "<sandbox-exec>",
                "-p",
                "<deny-network-policy>",
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
                "--disable-sandbox",
                "--disable-automatic-resolution",
                "-c",
                "release",
                "-Xswiftc",
                "-debug-prefix-map",
                "-Xswiftc",
                "<build-root>=/elmos/swift-analyzer",
                "-Xswiftc",
                "-file-prefix-map",
                "-Xswiftc",
                "<build-root>=/elmos/swift-analyzer",
                "-Xswiftc",
                "-file-compilation-dir",
                "-Xswiftc",
                "<canonical-compilation-dir>",
                "-Xswiftc",
                "-gnone",
                "-Xswiftc",
                "-no-serialize-debugging-options",
                "-Xcc",
                "-fdebug-prefix-map=<build-root>=/elmos/swift-analyzer",
                "-Xcc",
                "-ffile-prefix-map=<build-root>=/elmos/swift-analyzer",
                "-Xcc",
                "-fmacro-prefix-map=<build-root>=/elmos/swift-analyzer",
                "-Xcc",
                "-frandom-seed=elmos-swift-analyzer",
                "-Xlinker",
                "-no_uuid",
            ],
        },
        "binary": binary,
        "execution_seal": {
            "policy": "private-nonwritable-execution-root-v1",
            "root": str(binary_root),
            "mode": "0500",
            "uid": os.getuid(),
            "gid": os.getgid(),
            "device": 1,
            "inode": 1,
            "binary": binary,
        },
    }
    canonical = route_engine._canonical_swift_analyzer_receipt(receipt)
    receipt["canonical_identity"] = {
        "sha256": route_engine._canonical_digest(canonical),
        "receipt": canonical,
    }
    return receipt


def _synthetic_swift_inventory(artifact: bytes) -> dict[str, object]:
    inventory = _synthetic_inventory(_module("swift", "module.swift"), artifact)
    inventory["directives"] = []
    receipt = _synthetic_swift_build_receipt()
    receipt["source_inputs"]["sha256"] = sha256_bytes(  # type: ignore[index]
        json.dumps(
            {"files": receipt["source_inputs"]["files"]},  # type: ignore[index]
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    stable_digest = str(receipt["source_inputs"]["sha256"])  # type: ignore[index]
    canonical = route_engine._canonical_swift_analyzer_receipt(receipt)  # type: ignore[arg-type]
    receipt["canonical_identity"] = {  # type: ignore[index]
        "sha256": route_engine._canonical_digest(canonical),
        "receipt": canonical,
    }
    binary_digest = receipt["binary"]["sha256"]  # type: ignore[index]
    canonical_toolchain = route_engine._canonical_swift_toolchain_identity(  # type: ignore[attr-defined,arg-type]
        receipt["toolchain"]
    )
    toolchain_digest = route_engine._canonical_digest(canonical_toolchain)  # type: ignore[attr-defined]
    build_closure_digest = route_engine._canonical_digest(  # type: ignore[attr-defined]
        canonical_toolchain["build_closure"]
    )
    policy_digest = receipt["network_isolation"]["policy"]["sha256"]  # type: ignore[index]
    canonical_digest = receipt["canonical_identity"]["sha256"]  # type: ignore[index]
    dependency_digest = receipt["dependency"]["sha256"]  # type: ignore[index]
    swift_driver_digest = receipt["toolchain"]["swift_driver_sha256"]  # type: ignore[index]
    inventory["analyzer_version"] = (
        "swift-syntax;"
        f"source-inputs={stable_digest};"
        f"swift-driver={swift_driver_digest};"
        f"swift-syntax-tree={dependency_digest};"
        f"canonical-receipt={canonical_digest};binary={binary_digest};"
        f"toolchain={toolchain_digest};build-closure={build_closure_digest};"
        f"network-policy={policy_digest}"
    )
    inventory["analyzer_build_receipt"] = receipt
    return inventory


def test_swift_inventory_requires_and_byte_binds_private_build_receipt() -> None:
    artifact = b"func identity(_ value: Int64) -> Int64 { value }\n"
    inventory = _synthetic_swift_inventory(artifact)

    _verify_inventory_artifact(
        inventory,
        role="source",
        language="swift",
        logical_file="module.swift",
        artifact_bytes=artifact,
    )
    original_digest = sha256_bytes(canonical_json_bytes(inventory))

    changed = json.loads(json.dumps(inventory))
    changed["analyzer_build_receipt"]["binary"]["sha256"] = "sha256:" + "c" * 64
    with pytest.raises(RouteError, match="PURE_MODULE_ANALYZER_EXECUTION_SEAL_INVALID:source:swift"):
        _verify_inventory_artifact(
            changed,
            role="source",
            language="swift",
            logical_file="module.swift",
            artifact_bytes=artifact,
        )
    assert sha256_bytes(canonical_json_bytes(changed)) != original_digest

    missing = dict(inventory)
    missing.pop("analyzer_build_receipt")
    with pytest.raises(RouteError, match="PURE_MODULE_INVENTORY_KEYS_INVALID:source:swift"):
        _verify_inventory_artifact(
            missing,
            role="source",
            language="swift",
            logical_file="module.swift",
            artifact_bytes=artifact,
        )


def test_swift_canonical_build_identity_excludes_raw_absolute_paths_and_file_ids() -> None:
    first = _synthetic_swift_build_receipt()
    second = json.loads(json.dumps(first))
    second["toolchain"]["swiftc"] = "/second/toolchain/swiftc"
    second["toolchain"]["swift_driver"] = "/second/toolchain/swift"
    second["network_isolation"]["sandbox"]["path"] = "/second/usr/bin/sandbox-exec"
    second["network_isolation"]["verifier"]["path"] = "/second/usr/bin/codesign"
    probe = second["network_isolation"]["probe"]
    probe["build"]["compiler"].update(
        {
            "path": "/second/toolchain/clang",
            "resolved_path": "/second/toolchain/clang",
            "uid": 502,
            "gid": 21,
        }
    )
    probe["binary"].update(
        {
            "path": "/second/build/network-probe-execution/ElmosNetworkDenyProbe",
            "uid": 502,
            "gid": 21,
            "device": 9,
            "inode": 12,
        }
    )
    probe["execution_seal"].update(
        {
            "root": "/second/build/network-probe-execution",
            "uid": 502,
            "gid": 21,
            "device": 9,
            "inode": 11,
            "binary": probe["binary"],
        }
    )
    second["binary"]["path"] = "/second/build/ElmosSwiftAnalyzer"
    second["binary"]["uid"] = 502
    second["binary"]["gid"] = 21
    second["binary"]["device"] = 9
    second["binary"]["inode"] = 10
    second["execution_seal"]["root"] = "/second/build"
    second["execution_seal"]["uid"] = 502
    second["execution_seal"]["gid"] = 21
    second["execution_seal"]["device"] = 9
    second["execution_seal"]["inode"] = 11
    second["execution_seal"]["binary"] = second["binary"]

    assert first != second
    assert route_engine._canonical_swift_analyzer_receipt(first) == route_engine._canonical_swift_analyzer_receipt(
        second
    )


def test_swift_inventory_rejects_source_input_aggregate_mismatch() -> None:
    artifact = b"func identity(_ value: Int64) -> Int64 { value }\n"
    inventory = _synthetic_swift_inventory(artifact)
    inventory["analyzer_build_receipt"]["source_inputs"]["sha256"] = (  # type: ignore[index]
        "sha256:" + "d" * 64
    )

    with pytest.raises(
        RouteError,
        match="PURE_MODULE_ANALYZER_BUILD_RECEIPT_INPUT_CLOSURE_MISMATCH:source:swift",
    ):
        _verify_inventory_artifact(
            inventory,
            role="source",
            language="swift",
            logical_file="module.swift",
            artifact_bytes=artifact,
        )


def test_swift_inventory_rejects_build_without_deterministic_link_uuid_policy() -> None:
    artifact = b"func identity(_ value: Int64) -> Int64 { value }\n"
    inventory = _synthetic_swift_inventory(artifact)
    build = inventory["analyzer_build_receipt"]["build"]  # type: ignore[index]
    build["reproducible_path_policy"] = "debug-prefix-map-v1"  # type: ignore[index]
    build["argv"] = build["argv"][:-2]  # type: ignore[index]

    with pytest.raises(
        RouteError,
        match="PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:source:swift",
    ):
        _verify_inventory_artifact(
            inventory,
            role="source",
            language="swift",
            logical_file="module.swift",
            artifact_bytes=artifact,
        )


def test_swift_inventory_rejects_dependency_mirror_tuple_mismatch() -> None:
    artifact = b"func identity(_ value: Int64) -> Int64 { value }\n"
    inventory = _synthetic_swift_inventory(artifact)
    inventory["analyzer_build_receipt"]["dependency"]["mirror"]["bytes"] = 2  # type: ignore[index]

    with pytest.raises(
        RouteError,
        match="PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:source:swift",
    ):
        _verify_inventory_artifact(
            inventory,
            role="source",
            language="swift",
            logical_file="module.swift",
            artifact_bytes=artifact,
        )


def test_swift_inventory_rejects_unknown_dependency_seed() -> None:
    artifact = b"func identity(_ value: Int64) -> Int64 { value }\n"
    inventory = _synthetic_swift_inventory(artifact)
    inventory["analyzer_build_receipt"]["dependency"]["mirror"]["seed"] = (  # type: ignore[index]
        "ambient-cache"
    )

    with pytest.raises(
        RouteError,
        match="PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:source:swift",
    ):
        _verify_inventory_artifact(
            inventory,
            role="source",
            language="swift",
            logical_file="module.swift",
            artifact_bytes=artifact,
        )


def test_swift_inventory_rejects_non_standalone_dependency_cache_policy() -> None:
    artifact = b"func identity(_ value: Int64) -> Int64 { value }\n"
    inventory = _synthetic_swift_inventory(artifact)
    cache = inventory["analyzer_build_receipt"]["dependency"]["mirror"]["cache"]  # type: ignore[index]
    cache["object_store_policy"] = "borrowed-object-store"  # type: ignore[index]

    with pytest.raises(
        RouteError,
        match="PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:source:swift",
    ):
        _verify_inventory_artifact(
            inventory,
            role="source",
            language="swift",
            logical_file="module.swift",
            artifact_bytes=artifact,
        )


def _synthetic_whole_file_inputs(
    source: SemanticIR,
    target: SemanticIR,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    source_inventory = _synthetic_inventory(source, SOURCE_BYTES)
    target_inventory = _synthetic_inventory(target, TARGET_BYTES)
    closure = {
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-whole-file-closure",
        "profile": "typed-pure-module-v1",
        "route": {
            "source_language": source.source_language,
            "target_language": target.source_language,
        },
        "status": "PASSED",
        "source_inventory_sha256": sha256_bytes(canonical_json_bytes(source_inventory)),
        "source_inventory_bytes": len(canonical_json_bytes(source_inventory)),
        "target_inventory_sha256": sha256_bytes(canonical_json_bytes(target_inventory)),
        "target_inventory_bytes": len(canonical_json_bytes(target_inventory)),
        "manifest_symbols": sorted(function.name for function in source.functions),
        "source_profile_symbols": [],
        "target_profile_symbols": [],
        "target_helper_symbols": [],
        "verified_generated_helpers": [],
        "verified_language_prelude": {
            "source": {
                "status": "EXACT_AND_CLOSED",
                "role": "source",
                "language": source.source_language,
                "directives": [],
            },
            "target": {
                "status": "EXACT_AND_CLOSED",
                "role": "target",
                "language": target.source_language,
                "directives": [],
            },
        },
        "verified_language_wrapper": {
            "source": {
                "status": "NOT_APPLICABLE",
                "role": "source",
                "language": source.source_language,
                "file": source.source_file,
            },
            "target": {
                "status": "NOT_APPLICABLE",
                "role": "target",
                "language": target.source_language,
                "file": target.source_file,
            },
        },
        "blocked_declarations": {"source": [], "target": []},
        "source_user_call_graph": {"edges": [], "status": "EMPTY_AND_CLOSED"},
        "target_call_graph_policy": "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS",
        "target_call_graph": {
            "status": "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS",
            "scope": "profile-functions-to-emitted-callees",
            "edges": [],
            "helper_internal_calls": {
                "status": "CONTENT_BOUND_NOT_EDGE_ENUMERATED",
                "binding": "verified_generated_helpers-exact-bytes-and-digests",
            },
        },
        "target_builtin_normalizations": [],
    }
    return source_inventory, target_inventory, closure


def _compose(
    source: SemanticIR,
    target: SemanticIR,
    manifest: dict[str, object],
    observations: dict[str, list[dict[str, object]]],
    emitted: EmittedFile,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    _module_function_index(source, "source")
    _module_function_index(target, "target")
    source_inventory, target_inventory, closure = _synthetic_whole_file_inputs(source, target)
    plan = plan_identifiers(source, target.source_language)
    target_view = target_ir_view(source, plan)
    plan_bytes = identifier_plan_bytes(plan)
    identifier_hygiene = {
        "status": "PASSED",
        "policy_id": plan.policy_id,
        "policy_sha256": plan.policy_sha256,
        "unit_namespace": plan.unit_namespace.to_mapping(),
        "unit_namespace_sha256": plan.unit_namespace.digest,
        "plan": {"path": "identifier-plan.json", "sha256": plan.digest, "bytes": len(plan_bytes)},
        "raw_target_ir": {
            "path": "target-semantic-ir.raw.json",
            "sha256": sha256_bytes(canonical_json_bytes(target.to_mapping())),
            "bytes": len(canonical_json_bytes(target.to_mapping())),
        },
        "normalized_target_ir": {
            "path": "target-semantic-ir.normalized.json",
            "sha256": sha256_bytes(canonical_json_bytes(target.to_mapping())),
            "bytes": len(canonical_json_bytes(target.to_mapping())),
        },
        "functions": [
            {
                "raw_symbol": raw_function.name,
                "canonical_symbol": canonical_function.name,
                "parameters": [
                    {
                        "raw_name": raw_parameter.name,
                        "canonical_name": canonical_parameter.name,
                        "canonical_type": canonical_parameter.type,
                    }
                    for raw_parameter, canonical_parameter in zip(
                        raw_function.parameters,
                        canonical_function.parameters,
                        strict=True,
                    )
                ],
            }
            for raw_function, canonical_function in zip(
                target_view.functions,
                source.functions,
                strict=True,
            )
        ],
        "renamed": any(binding.decision == "ALPHA_RENAMED" for binding in plan.bindings),
    }
    return module_equivalence(
        source=source,
        target=target,
        case_manifest=manifest,
        source_observations=observations,
        target_observations=observations,
        source_artifact_sha256=SOURCE_DIGEST,
        target_artifact_sha256=TARGET_DIGEST,
        corpus_sha256=CORPUS_DIGEST,
        emitted=emitted,
        source_artifact_bytes=SOURCE_BYTES,
        source_logical_file="module.py",
        source_inventory_sha256=sha256_bytes(canonical_json_bytes(source_inventory)),
        source_inventory_byte_count=len(canonical_json_bytes(source_inventory)),
        target_inventory_sha256=sha256_bytes(canonical_json_bytes(target_inventory)),
        target_inventory_byte_count=len(canonical_json_bytes(target_inventory)),
        whole_file_closure=closure,
        identifier_hygiene=identifier_hygiene,
    )


def test_three_function_module_composes_every_layer_under_explicit_assumptions() -> None:
    source, target, manifest, observations, emitted = _equivalent_inputs()

    report, proof_closures = _compose(source, target, manifest, observations, emitted)

    assert report["kind"] == "typed-pure-module-equivalence"
    assert report["status"] == "PASSED"
    assert report["local_verification_status"] == "PASSED"
    assert report["composition"] == {
        "rule": "per-function-denotation-plus-exact-emitter-helper-closure",
        "function_count": 3,
        "passed_function_count": 3,
        "status": "PASSED",
        "proof_strength": "COMPOSED_THEOREMS_UNDER_ASSUMPTIONS",
        "input_domain": "canonical-finite-no-error-input-domain",
        "out_of_domain_arithmetic_behavior": "BLOCKED_NOT_EQUIVALENTLY_MODELED",
        "original_source_bytes_theorem": False,
        "source_compiler_runtime_soundness": "NOT_RUN",
        "target_compiler_runtime_soundness": "NOT_RUN",
        "analyzer_and_emitter_soundness": "ASSUMPTION",
        "source_user_call_graph": "EMPTY_AND_CLOSED",
        "target_call_graph": "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS",
        "target_profile_to_emitted_call_graph_status": ("EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"),
        "target_profile_to_emitted_call_graph_scope": ("profile-functions-to-emitted-callees"),
    }
    assert set(proof_closures) == {"add", "subtract", "minimum"}
    for function in report["functions"]:
        assert function["status"] == "PASSED"
        assert function["layers"]["semantic"]["status"] == "PASSED"
        assert function["layers"]["chunk"]["status"] == "PASSED"
        assert function["layers"]["chunk"]["span_validation"]["status"] == "PASSED"
        assert function["layers"]["behavior"]["status"] == "PASSED"
        assert function["layers"]["formal"]["status"] == "PROVED_UNDER_ASSUMPTIONS"
        assert function["layers"]["formal"]["proof_strength"] == "THEOREM_UNDER_ASSUMPTIONS"
        assert function["layers"]["formal"]["assumptions"]
        assert function["layers"]["formal"]["countermodel"] is None
        closure = proof_closures[function["symbol"]]
        assert function["layers"]["formal"]["formal_input_sha256"] == closure["formal_input_sha256"]
        assert function["layers"]["formal"]["solver_input_sha256"] == closure["solver_input_sha256"]
        assert function["layers"]["formal"]["formal_result_sha256"] == closure["formal_result_sha256"]
        assert f"; formal_input_digest: {closure['formal_input_sha256']}" in closure["solver_input"]
        assert (
            function["layers"]["formal"]["external_soundness_boundary"]["source_compiler_runtime_soundness"]
            == "NOT_RUN"
        )
        for mapping in function["layers"]["chunk"]["mappings"]:
            assert mapping["source_semantic_pointer"] == mapping["target_semantic_pointer"]
            assert mapping["source_span"] is not None
            assert mapping["target_span"] is not None


def test_source_positions_are_excluded_from_semantic_hashes() -> None:
    source, target, _, _, _ = _equivalent_inputs()

    semantic = semantic_equivalence(source, target)

    assert semantic["status"] == "PASSED"
    assert semantic["source_view_sha256"] == semantic["target_view_sha256"]


def test_exact_eight_requires_spans_while_legacy_thirty_keeps_semantic_pointer_contract() -> None:
    source, target, _, _, emitted = _equivalent_inputs()
    source_without_spans = SemanticIR.from_mapping(
        {
            **source.to_mapping(),
            "functions": [function.semantic_mapping() for function in source.functions],
        }
    )
    target_without_spans = SemanticIR.from_mapping(
        {
            **target.to_mapping(),
            "functions": [function.semantic_mapping() for function in target.functions],
        }
    )

    legacy = chunk_equivalence(
        source_without_spans,
        target_without_spans,
        SOURCE_DIGEST,
        TARGET_DIGEST,
        emitted,
        require_concrete_spans=False,
    )
    specialized = chunk_equivalence(
        source_without_spans,
        target_without_spans,
        SOURCE_DIGEST,
        TARGET_DIGEST,
        emitted,
        require_concrete_spans=True,
    )

    assert legacy["status"] == "PASSED"
    assert legacy["span_validation"]["status"] == "NOT_REQUIRED"
    assert legacy["missing_source_span_count"] > 0
    assert specialized["status"] == "FAILED"
    assert specialized["span_validation"]["status"] == "NOT_RUN"
    assert any(mapping["status"] == "SOURCE_SPAN_MISSING" for mapping in specialized["mappings"])


def test_verify_pure_module_persists_byte_bound_children(tmp_path: Path) -> None:
    source, target, manifest, observations, emitted = _equivalent_inputs()
    plan = plan_identifiers(source, target.source_language)
    manifest_bytes = canonical_json_bytes(manifest)
    source_inventory, target_inventory, closure = _synthetic_whole_file_inputs(source, target)
    name_map = {b.source_name: b.target_name for b in plan.bindings if b.role == "function"}
    raw_target = replace(target, functions=tuple(replace(f, name=name_map[f.name]) for f in target.functions))

    report = verify_pure_module(
        source_ir=source,
        raw_target_ir=raw_target,
        target_ir=target,
        identifier_plan=plan,
        case_manifest=manifest,
        source_observations=observations,
        target_observations=observations,
        source_artifact_sha256=SOURCE_DIGEST,
        target_artifact_sha256=TARGET_DIGEST,
        corpus_sha256=sha256_bytes(manifest_bytes),
        emitted=emitted,
        source_artifact_bytes=SOURCE_BYTES,
        source_logical_file="module.py",
        case_manifest_bytes=manifest_bytes,
        source_inventory=source_inventory,
        target_inventory=target_inventory,
        whole_file_closure=closure,
        output=tmp_path / "evidence",
    )

    root = tmp_path / "evidence"
    persisted = json.loads((root / "typed-pure-module-equivalence.json").read_text(encoding="utf-8"))
    assert persisted == report
    assert report["module_input_sha256"] == next(
        item["sha256"] for item in report["artifact_refs"] if item["role"] == "module-formal-input"
    )
    assert len([item for item in report["artifact_refs"] if item["role"] == "formal-function-smt2"]) == 3
    assert len([item for item in report["artifact_refs"] if item["role"] == "formal-function-input"]) == 3
    assert len([item for item in report["artifact_refs"] if item["role"] == "formal-function-result"]) == 3
    for reference in report["artifact_refs"]:
        assert set(reference) == {"role", "path", "sha256", "bytes"}
        content = (root / reference["path"]).read_bytes()
        assert reference["bytes"] == len(content)
        assert reference["sha256"] == sha256_bytes(content)

    input_keys = {
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
        "identifier_hygiene",
    }
    result_keys = {
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
    for index, function in enumerate(report["functions"]):
        formal = function["layers"]["formal"]
        input_path = root / f"formal-function-{index:03d}-input.json"
        solver_path = root / f"formal-function-{index:03d}.smt2"
        result_path = root / f"formal-function-{index:03d}-result.json"
        formal_input = json.loads(input_path.read_text(encoding="utf-8"))
        formal_result = json.loads(result_path.read_text(encoding="utf-8"))
        solver_input = solver_path.read_text(encoding="utf-8")

        assert set(formal_input) == input_keys
        assert set(formal_result) == result_keys
        assert formal_input["module_input_sha256"] == report["module_input_sha256"]
        assert formal_input["symbol"] == function["symbol"]
        assert formal_input["input_domain"] == "canonical-finite-no-error-input-domain"
        assert formal_input["source_function_sha256"] == sha256_bytes(
            canonical_json_bytes(formal_input["source_function"])
        )
        assert formal_input["target_function_sha256"] == sha256_bytes(
            canonical_json_bytes(formal_input["target_function"])
        )
        assert formal_result["solver"] == "z3"
        assert isinstance(formal_result["version"], str) and formal_result["version"]
        assert set(formal_result["options"]) == {"timeout_ms", "random_seed", "theories"}
        assert formal_result["status"] == "PROVED_UNDER_ASSUMPTIONS"
        assert formal_result["property_status"] == "PROVED"
        assert formal_result["proof_strength"] == "THEOREM_UNDER_ASSUMPTIONS"
        assert formal_result["assumptions"]
        assert formal_result["countermodel"] is None
        assert formal_result["formal_input_digest"] == sha256_bytes(input_path.read_bytes())
        assert formal_result["solver_input_digest"] == sha256_bytes(solver_path.read_bytes())
        assert f"; formal_input_digest: {formal_result['formal_input_digest']}" in solver_input
        assert formal_result["replay_contract"] == {
            "kind": "z3-cli-check-sat",
            "argv": ["z3", "-smt2", solver_path.name],
            "working_directory": ".",
            "expected_exit_code": 0,
            "expected_stdout": "unsat",
        }
        assert formal["formal_input_path"] == input_path.name
        assert formal["solver_input_path"] == solver_path.name
        assert formal["formal_result_path"] == result_path.name
        assert formal["formal_result_sha256"] == sha256_bytes(result_path.read_bytes())


def test_exact_symbol_and_signature_sets_fail_closed() -> None:
    source, target, manifest, observations, emitted = _equivalent_inputs()
    renamed = replace(target.functions[-1], name="other")
    symbol_mismatch = replace(target, functions=(*target.functions[:-1], renamed))
    with pytest.raises(RouteError, match="PURE_MODULE_SYMBOL_SET_MISMATCH"):
        _compose(source, symbol_mismatch, manifest, observations, emitted)

    signature_drift = replace(target.functions[0], return_type="number")
    signature_mismatch = replace(target, functions=(signature_drift, *target.functions[1:]))
    with pytest.raises(RouteError, match="PURE_MODULE_SIGNATURE_MISMATCH:add"):
        _compose(source, signature_mismatch, manifest, observations, emitted)


def test_manifest_missing_cases_unknown_fields_and_two_function_modules_fail_closed() -> None:
    source, target, manifest, observations, emitted = _equivalent_inputs()
    missing = {**manifest, "functions": manifest["functions"][:-1]}
    with pytest.raises(RouteError, match="PURE_MODULE_CASE_MANIFEST_SYMBOL_SET_MISMATCH"):
        _compose(source, target, missing, observations, emitted)

    unknown = {**manifest, "ignored": True}
    with pytest.raises(RouteError, match="PURE_MODULE_MANIFEST_KEYS_INVALID:root"):
        _compose(source, target, unknown, observations, emitted)

    duplicate_case = json.loads(json.dumps(manifest))
    duplicate_case["functions"][0]["cases"].append(duplicate_case["functions"][0]["cases"][0])
    with pytest.raises(RouteError, match="PURE_MODULE_DUPLICATE_CASE:add"):
        _compose(source, target, duplicate_case, observations, emitted)

    two_source = replace(source, functions=source.functions[:2])
    two_target = replace(target, functions=target.functions[:2])
    with pytest.raises(RouteError, match="PURE_MODULE_AT_LEAST_THREE_FUNCTIONS_REQUIRED"):
        _compose(two_source, two_target, manifest, observations, emitted)


def test_calls_and_mutable_state_are_not_composable() -> None:
    source, target, manifest, observations, emitted = _equivalent_inputs()
    original = source.functions[0]
    original_statement = original.body[0]
    assert original_statement.expression is not None
    call = Expression(
        kind="call",
        value="subtract",
        source_span=original_statement.expression.source_span,
    )
    call_function = replace(
        original,
        body=(replace(original_statement, expression=call),),
    )
    with pytest.raises(RouteError, match="PURE_MODULE_CALLS_UNSUPPORTED"):
        _compose(
            replace(source, functions=(call_function, *source.functions[1:])),
            target,
            manifest,
            observations,
            emitted,
        )

    state_function = replace(
        original,
        body=(Statement(kind="assignment", source_span=original_statement.source_span),),
    )
    with pytest.raises(RouteError, match="PURE_MODULE_STATE_UNSUPPORTED"):
        _compose(
            replace(source, functions=(state_function, *source.functions[1:])),
            target,
            manifest,
            observations,
            emitted,
        )


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (SourceSpan("wrong.py", 100, 400), "SOURCE_SPAN_FILE_MISMATCH"),
        (SourceSpan("module.py", 100, 4_001), "SOURCE_SPAN_OUT_OF_BOUNDS"),
        (SourceSpan("module.py", 150, 190), "SOURCE_SPAN_PARENT_COVERAGE_INVALID"),
    ],
)
def test_concrete_span_file_bounds_and_parent_coverage_fail_closed(
    mutation: SourceSpan,
    expected: str,
) -> None:
    source, target, manifest, observations, emitted = _equivalent_inputs()
    first = source.functions[0]
    if expected == "SOURCE_SPAN_PARENT_COVERAGE_INVALID":
        statement = replace(first.body[0], source_span=mutation)
        first = replace(first, body=(statement,))
    else:
        first = replace(first, source_span=mutation)
    mutated = replace(source, functions=(first, *source.functions[1:]))

    with pytest.raises(RouteError, match=expected):
        _compose(mutated, target, manifest, observations, emitted)


def test_non_explicit_directed_route_is_rejected_before_artifact_work(tmp_path: Path) -> None:
    source, _, manifest, observations, _ = _equivalent_inputs()
    target = _module("python", "migrated.py")
    emitted = EmittedFile(relative_path="migrated.py", content=TARGET_BYTES.decode("ascii"))
    source_inventory, target_inventory, closure = _synthetic_whole_file_inputs(source, target)
    plan = plan_identifiers(source, target.source_language)

    with pytest.raises(RouteError, match="UNSUPPORTED_DIRECTED_ROUTE:python-to-python"):
        verify_pure_module(
            source_ir=source,
            raw_target_ir=target,
            target_ir=target,
            identifier_plan=plan,
            case_manifest=manifest,
            source_observations=observations,
            target_observations=observations,
            source_artifact_sha256=SOURCE_DIGEST,
            target_artifact_sha256=TARGET_DIGEST,
            corpus_sha256=CORPUS_DIGEST,
            emitted=emitted,
            source_artifact_bytes=SOURCE_BYTES,
            source_logical_file="module.py",
            case_manifest_bytes=canonical_json_bytes(manifest),
            source_inventory=source_inventory,
            target_inventory=target_inventory,
            whole_file_closure=closure,
            output=tmp_path / "must-not-exist",
        )
    assert not (tmp_path / "must-not-exist").exists()


def test_module_input_digest_is_canonical_and_location_bound() -> None:
    source, target, manifest, observations, emitted = _equivalent_inputs()
    report, _ = _compose(source, target, manifest, observations, emitted)

    assert report["module_input_sha256"] == sha256_bytes(canonical_json_bytes(report["module_input"]))


def test_profile_inventory_span_must_exactly_match_function_ir_span() -> None:
    function = _module("cpp", "module.cpp").functions[0]
    assert function.source_span is not None
    subject = {
        "qualified_name": function.name,
        "declaration_kind": "FunctionDecl",
        "occurrence": 1,
        "source_span": {
            **function.source_span.to_mapping(),
            "end_byte": function.source_span.end_byte - 1,
        },
        "signature": {
            "parameters": [
                {"name": parameter.name, "source_type": "std::int64_t"} for parameter in function.parameters
            ],
            "source_type": "std::int64_t (std::int64_t, std::int64_t)",
            "visibility": "external",
            "storage": "none",
        },
    }

    with pytest.raises(RouteError, match="PURE_MODULE_PROFILE_SPAN_MISMATCH:target:add"):
        _profile_symbol_record(subject, function, function, role="target")


def test_named_analysis_binds_unique_independent_inventory_span() -> None:
    analyzed = _module("typescript", "module.ts")
    function = replace(analyzed.functions[0], source_span=None)
    analyzed = replace(analyzed, functions=(function,))
    inventory = {
        "source_language": "typescript",
        "source_file": "module.ts",
        "subjects": [
            {
                "name": function.name,
                "analyzable": True,
                "source_span": {
                    "file": "module.ts",
                    "start_byte": 10,
                    "end_byte": 80,
                },
            }
        ],
    }

    bound = _bind_function_spans_from_inventory(analyzed, inventory, role="target")

    assert bound.functions[0].source_span == SourceSpan("module.ts", 10, 80)


def test_named_analysis_rejects_inventory_span_conflict() -> None:
    analyzed = _module("typescript", "module.ts")
    function = analyzed.functions[0]
    assert function.source_span is not None
    inventory = {
        "source_language": "typescript",
        "source_file": "module.ts",
        "subjects": [
            {
                "name": function.name,
                "analyzable": True,
                "source_span": {
                    **function.source_span.to_mapping(),
                    "end_byte": function.source_span.end_byte + 1,
                },
            }
        ],
    }

    with pytest.raises(
        RouteError,
        match=f"PURE_MODULE_ANALYSIS_INVENTORY_SPAN_MISMATCH:target:{function.name}",
    ):
        _bind_function_spans_from_inventory(analyzed, inventory, role="target")


def test_typescript_named_relift_binds_actual_inventory_span_and_closes_module(
    tmp_path: Path,
) -> None:
    _require_native_toolchain("javascript")
    _require_native_toolchain("typescript")
    source = tmp_path / "identity.js"
    source_bytes = (
        b"/** @param {number} value @returns {number} */\n"
        b"export function echoNumber(value) { return value; }\n\n"
        b"/** @param {boolean} value @returns {boolean} */\n"
        b"export function echoBoolean(value) { return value; }\n\n"
        b"/** @param {string} value @returns {string} */\n"
        b"export function echoString(value) { return value; }\n"
    )
    source.write_bytes(source_bytes)
    (tmp_path / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    symbols = ["echoBoolean", "echoNumber", "echoString"]
    source_inventory = inventory_module(source, "javascript")
    source_ir = _bind_function_spans_from_inventory(
        _combine_function_irs(
            [analyze(source, "javascript", symbol) for symbol in symbols],
            symbols,
            "javascript",
            "source",
        ),
        source_inventory,
        role="source",
    )
    plan = plan_identifiers(source_ir, "typescript")
    emitted = emit(source_ir, "typescript", identifier_plan=plan)
    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")
    target_inventory = inventory_module(target, "typescript")
    target_names = [function.name for function in target_ir_view(source_ir, plan).functions]
    analyzed_target = _combine_function_irs(
        [analyze(target, "typescript", symbol, emitted_target=True) for symbol in target_names],
        target_names,
        "typescript",
        "target",
    )
    # The native TypeScript analyzer now binds exact declaration spans itself.
    # The inventory binder must still re-validate those spans against the
    # independently collected whole-file inventory before module closure.
    assert all(function.source_span is not None for function in analyzed_target.functions)
    raw_target_ir = _bind_function_spans_from_inventory(
        analyzed_target,
        target_inventory,
        role="target",
    )
    assert all(function.source_span is not None for function in raw_target_ir.functions)
    target_ir = alpha_normalize_target(source_ir, raw_target_ir, plan)
    manifest = {
        "functions": [
            {
                "symbol": function.name,
                "signature": function.signature_mapping(),
            }
            for function in source_ir.functions
        ]
    }

    closure = _build_whole_file_closure(
        source_inventory=source_inventory,
        target_inventory=target_inventory,
        source_ir=source_ir,
        raw_target_ir=raw_target_ir,
        target_ir=target_ir,
        identifier_plan=plan,
        manifest=manifest,
        source_bytes=source_bytes,
        emitted=emitted,
    )

    assert closure["status"] == "PASSED"
    assert all(item["source_span"] for item in closure["target_profile_symbols"])


@pytest.mark.parametrize("target_language", ["cpp", "objc"])
def test_open_global_targets_close_raw_and_canonical_multifunction_inventory(
    target_language: Language,
) -> None:
    source = _module("python", "module.py")
    plan = plan_identifiers(source, target_language)
    raw_target_ir = replace(
        target_ir_view(source, plan),
        source_language=target_language,
        source_file=f"migrated.{target_language}",
    )
    canonical_target_ir = replace(
        source,
        source_language=target_language,
        source_file=f"migrated.{target_language}",
    )
    canonical_by_raw = {
        raw_function.name: canonical_function
        for raw_function, canonical_function in zip(
            raw_target_ir.functions,
            canonical_target_ir.functions,
            strict=True,
        )
    }
    inventory = _synthetic_inventory(raw_target_ir, TARGET_BYTES)
    inventory["subjects"] = [
        {
            "name": function.name,
            "qualified_name": function.name,
            "declaration_kind": "FunctionDecl",
            "analyzable": True,
            "occurrence": 1,
            "source_span": function.source_span.to_mapping() if function.source_span else None,
            "signature": {
                "parameters": [
                    {"name": parameter.name, "source_type": "std::int64_t"} for parameter in function.parameters
                ],
                "source_type": "std::int64_t (std::int64_t, std::int64_t)",
                "visibility": "external",
                "storage": "none",
            },
        }
        for function in raw_target_ir.functions
    ]
    manifest_signatures = {function.name: function.signature_mapping() for function in canonical_target_ir.functions}

    records, helpers = _close_profile_inventory(
        inventory,
        raw_target_ir,
        manifest_signatures,
        role="target",
        canonical_functions_by_raw=canonical_by_raw,
    )

    assert not helpers
    assert [record["canonical_symbol"] for record in records] == sorted(manifest_signatures)
    assert all(record["raw_symbol"] != record["canonical_symbol"] for record in records)
    assert all(
        raw_name != canonical_name
        for record in records
        for raw_name, canonical_name in zip(
            record["raw_parameter_names"],
            [parameter["name"] for parameter in record["canonical_signature"]["parameters"]],
            strict=True,
        )
    )

    wrong_mapping = dict(canonical_by_raw)
    first_raw, second_raw = list(wrong_mapping)[:2]
    wrong_mapping[first_raw] = wrong_mapping[second_raw]
    with pytest.raises(RouteError, match="PURE_MODULE_PROFILE_CANONICAL_SYMBOL_DUPLICATED:target"):
        _close_profile_inventory(
            inventory,
            raw_target_ir,
            manifest_signatures,
            role="target",
            canonical_functions_by_raw=wrong_mapping,
        )


@pytest.mark.parametrize("target_language", ["cpp", "objc"])
def test_open_global_targets_bind_raw_and_canonical_multifunction_callers(
    target_language: Language,
) -> None:
    source = _module("python", "module.py")
    plan = plan_identifiers(source, target_language)
    raw_target_ir = replace(
        target_ir_view(source, plan),
        source_language=target_language,
        source_file=f"migrated.{target_language}",
    )
    canonical_by_raw = {
        raw_function.name: canonical_function
        for raw_function, canonical_function in zip(
            raw_target_ir.functions,
            source.functions,
            strict=True,
        )
    }
    emitted = emit(source, target_language, identifier_plan=plan)
    helpers: dict[tuple[str, str], dict[str, object]] = {}
    for _operator, (callee, helper_ids) in route_engine._CHECKED_INTEGER_CALL[target_language].items():
        for helper_id in helper_ids:
            helpers[(helper_id, callee)] = {
                "helper_id": helper_id,
                "name": callee,
                "qualified_name": callee,
            }

    graph = _target_call_graph(
        raw_target_ir,
        canonical_by_raw,
        emitted,
        list(helpers.values()),
    )

    expected_raw_names = {
        canonical_function.name: raw_function.name
        for raw_function, canonical_function in zip(
            raw_target_ir.functions,
            source.functions,
            strict=True,
        )
    }
    assert {(edge["canonical_caller"], edge["caller"], edge["canonical_operator"]) for edge in graph["edges"]} == {
        ("add", expected_raw_names["add"], "+"),
        ("subtract", expected_raw_names["subtract"], "-"),
    }
    assert all(edge["caller"] != edge["canonical_caller"] for edge in graph["edges"])


def test_emitted_helper_digest_tamper_fails_closed() -> None:
    source = _module("java", "Module.java")
    emitted = emit(source, "cpp")
    helper_id, helper_digest = emitted.helper_digests[0]
    tampered = replace(
        emitted,
        helper_digests=((helper_id, "sha256:" + "0" * 64), *emitted.helper_digests[1:]),
    )
    assert helper_digest != tampered.helper_digests[0][1]

    with pytest.raises(
        RouteError,
        match=f"PURE_MODULE_TARGET_HELPER_DIGEST_MISMATCH:{helper_id}",
    ):
        _emitted_helper_regions(tampered, "cpp")


def test_target_call_graph_rejects_unregistered_normalization_and_matches_java_qualified_helper() -> None:
    target = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Migrated.java",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [_binary_function("Migrated.java", "divide", "/", 100)],
            "diagnostics": [],
        }
    )
    emitted = emit(target, "java")
    graph = _target_call_graph(
        target,
        {function.name: function for function in target.functions},
        emitted,
        [
            {
                "helper_id": "checked_div",
                "name": "elmosCheckedDiv",
                "qualified_name": "Migrated.elmosCheckedDiv",
            }
        ],
    )

    assert graph["edges"] == [
        {
            "caller": "divide",
            "canonical_caller": "divide",
            "callee": "Migrated.elmosCheckedDiv",
            "callee_kind": "exact-generated-helper",
            "canonical_domain": "integer",
            "canonical_operator": "/",
            "normalization_rule": "java.integer./.call:Migrated.elmosCheckedDiv",
        }
    ]

    tampered = replace(
        emitted,
        normalization_rules=(*emitted.normalization_rules, "java.integer./.call:System.exit"),
    )
    with pytest.raises(RouteError, match="PURE_MODULE_TARGET_CALL_NORMALIZATION_INVALID"):
        _target_call_graph(
            target,
            {function.name: function for function in target.functions},
            tampered,
            [],
        )


def test_javascript_target_call_graph_closes_signature_and_result_guards() -> None:
    target = _module("javascript", "migrated.mjs")
    emitted = emit(target, "javascript")
    helper_symbols = [
        {
            "helper_id": "safe_integer",
            "name": "_elmosRequireSafeInteger",
            "qualified_name": "_elmosRequireSafeInteger",
        }
    ]
    graph = _target_call_graph(
        target,
        {function.name: function for function in target.functions},
        emitted,
        helper_symbols,
    )

    assert len(graph["edges"]) == 11
    assert {
        (
            edge["canonical_caller"],
            edge["guard_scope"],
            edge.get("canonical_guard_subject", edge["guard_subject"]),
        )
        for edge in graph["edges"]
    } >= {
        ("add", "signature-parameter", "left"),
        ("add", "signature-parameter", "right"),
        ("add", "signature-return", "return"),
        ("add", "arithmetic-result", "+"),
        ("subtract", "arithmetic-result", "-"),
        ("minimum", "signature-return", "return"),
    }
    assert all(edge["callee"] == "_elmosRequireSafeInteger" for edge in graph["edges"])

    missing = replace(
        emitted,
        normalization_rules=tuple(
            rule for rule in emitted.normalization_rules if rule != "javascript.parameter.integer.exact"
        ),
    )
    with pytest.raises(
        RouteError,
        match="PURE_MODULE_TARGET_JAVASCRIPT_GUARD_NORMALIZATION_INVALID",
    ):
        _target_call_graph(
            target,
            {function.name: function for function in target.functions},
            missing,
            helper_symbols,
        )


def test_java_to_cpp_whole_file_closure_is_content_bound_and_call_closed(
    tmp_path: Path,
) -> None:
    _require_native_toolchain("java")
    _require_native_toolchain("cpp")
    output = tmp_path / "evidence"

    report = migrate_module(
        ENGINE_ROOT / "fixtures/module/java/EquivalenceModule.java",
        "java",
        "cpp",
        ENGINE_ROOT / "fixtures/module/cases.json",
        output,
    )

    closure = report["whole_file_closure"]
    assert closure["status"] == "PASSED"
    assert closure["manifest_symbols"] == [
        "both",
        "calculate",
        "clamp",
        "clampNumber",
        "difference",
    ]
    assert [symbol["symbol"] for symbol in closure["source_profile_symbols"]] == closure["manifest_symbols"]
    assert [symbol["symbol"] for symbol in closure["target_profile_symbols"]] == closure["manifest_symbols"]
    assert {
        (symbol["helper_id"], symbol["name"], symbol["visibility"], symbol["storage"])
        for symbol in closure["target_helper_symbols"]
    } == {
        ("checked_add", "elmos_checked_add", "internal", "static"),
        ("checked_sub", "elmos_checked_sub", "internal", "static"),
    }
    assert all(
        len(helper["symbols"]) == 1 and helper["symbols"][0]["analyzable"] is True
        for helper in closure["verified_generated_helpers"]
    )
    assert closure["verified_language_wrapper"]["source"]["name"] == "EquivalenceModule"
    assert closure["verified_language_wrapper"]["source"]["member_span_status"] == ("ALL_CONTAINED")
    assert closure["verified_language_wrapper"]["target"]["status"] == "NOT_APPLICABLE"
    assert [
        (directive["kind"], directive["value"])
        for directive in closure["verified_language_prelude"]["target"]["directives"]
    ] == [
        ("include", "<cstdint>"),
        ("include", "<stdexcept>"),
        ("include", "<string>"),
    ]
    target_call_graph = closure["target_call_graph"]
    assert target_call_graph["status"] == "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
    assert target_call_graph["scope"] == "profile-functions-to-emitted-callees"
    assert {
        (
            edge["canonical_caller"],
            edge["callee"],
            edge["canonical_operator"],
            edge["normalization_rule"],
        )
        for edge in target_call_graph["edges"]
    } == {
        ("calculate", "elmos_checked_add", "+", "cpp.integer.+.call:elmos_checked_add"),
        ("difference", "elmos_checked_sub", "-", "cpp.integer.-.call:elmos_checked_sub"),
    }
    assert all(edge["caller"] != edge["canonical_caller"] for edge in target_call_graph["edges"])
    assert target_call_graph["helper_internal_calls"] == {
        "status": "CONTENT_BOUND_NOT_EDGE_ENUMERATED",
        "binding": "verified_generated_helpers-exact-bytes-and-digests",
    }
    references = {reference["role"]: reference for reference in report["artifact_refs"]}
    for role in (
        "source-module-inventory",
        "target-module-inventory",
        "whole-file-module-closure",
    ):
        assert role in references
    assert report["module_input"]["source_inventory_sha256"] == references["source-module-inventory"]["sha256"]
    assert report["module_input"]["target_inventory_sha256"] == references["target-module-inventory"]["sha256"]
    assert report["module_contract"]["independence"]["target_call_graph"] == closure["target_call_graph"]


@JAVASCRIPT_ROUTE_RETIRED
def test_java_to_javascript_single_function_migration_relifts_internal_helper(
    tmp_path: Path,
) -> None:
    _require_native_toolchain("java")
    _require_native_toolchain("javascript")
    source = tmp_path / "NodeSingle.java"
    source.write_text(
        "public final class NodeSingle {\n    public static long identity(long value) { return value; }\n}\n",
        encoding="utf-8",
    )
    cases = tmp_path / "single-cases.json"
    cases.write_text(json.dumps([{"args": [7], "expected": 7}]), encoding="utf-8")

    report = migrate(
        source,
        "java",
        "javascript",
        "identity",
        cases,
        tmp_path / "single-evidence",
    )

    assert report["status"] == "PASSED"
    assert report["route"] == "java-to-javascript"


@JAVASCRIPT_ROUTE_RETIRED
def test_java_to_javascript_multifunction_module_closes_each_internal_helper(
    tmp_path: Path,
) -> None:
    _require_native_toolchain("java")
    _require_native_toolchain("javascript")
    report = migrate_module(
        ENGINE_ROOT / "fixtures/module/java/EquivalenceModule.java",
        "java",
        "javascript",
        ENGINE_ROOT / "fixtures/module/nodejs-cases.json",
        tmp_path / "multi-evidence",
    )

    helpers = report["whole_file_closure"]["target_helper_symbols"]
    assert {(helper["helper_id"], helper["name"], helper["visibility"], helper["storage"]) for helper in helpers} == {
        ("safe_integer", "_elmosRequireSafeInteger", "internal", "file-scope"),
        ("exact_boolean", "_elmosRequireBoolean", "internal", "file-scope"),
        ("finite_number", "_elmosRequireFiniteNumber", "internal", "file-scope"),
    }
    assert all(helper["analyzable"] is True and helper["arity"] == 1 for helper in helpers)

    edges = report["whole_file_closure"]["target_call_graph"]["edges"]
    assert len(edges) == 19
    assert all(edge["callee_kind"] == "exact-generated-helper" for edge in edges)
    assert {
        (
            edge["caller"],
            edge["guard_subject"],
            edge["canonical_domain"],
            edge["callee"],
        )
        for edge in edges
        if edge["guard_scope"] == "signature-parameter"
    } == {
        ("calculate", "subtotal", "integer", "_elmosRequireSafeInteger"),
        ("calculate", "tax", "integer", "_elmosRequireSafeInteger"),
        ("clamp", "value", "integer", "_elmosRequireSafeInteger"),
        ("clamp", "minimum", "integer", "_elmosRequireSafeInteger"),
        ("clamp", "maximum", "integer", "_elmosRequireSafeInteger"),
        ("difference", "left", "integer", "_elmosRequireSafeInteger"),
        ("difference", "right", "integer", "_elmosRequireSafeInteger"),
        ("clampNumber", "value", "number", "_elmosRequireFiniteNumber"),
        ("clampNumber", "minimum", "number", "_elmosRequireFiniteNumber"),
        ("clampNumber", "maximum", "number", "_elmosRequireFiniteNumber"),
        ("both", "left", "boolean", "_elmosRequireBoolean"),
        ("both", "right", "boolean", "_elmosRequireBoolean"),
    }
    assert {
        (edge["caller"], edge["canonical_domain"], edge["callee"])
        for edge in edges
        if edge["guard_scope"] == "signature-return"
    } == {
        ("calculate", "integer", "_elmosRequireSafeInteger"),
        ("clamp", "integer", "_elmosRequireSafeInteger"),
        ("difference", "integer", "_elmosRequireSafeInteger"),
        ("clampNumber", "number", "_elmosRequireFiniteNumber"),
        ("both", "boolean", "_elmosRequireBoolean"),
    }
    assert {
        (edge["caller"], edge["canonical_operator"], edge["callee"])
        for edge in edges
        if edge["guard_scope"] == "arithmetic-result"
    } == {
        ("calculate", "+", "_elmosRequireSafeInteger"),
        ("difference", "-", "_elmosRequireSafeInteger"),
    }


def test_module_pipeline_uses_private_input_snapshots_across_phase_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_native_toolchain("java")
    _require_native_toolchain("cpp")
    source = tmp_path / "EquivalenceModule.java"
    manifest = tmp_path / "cases.json"
    initial_source = (ENGINE_ROOT / "fixtures/module/java/EquivalenceModule.java").read_bytes()
    initial_manifest = (ENGINE_ROOT / "fixtures/module/cases.json").read_bytes()
    source.write_bytes(initial_source)
    manifest.write_bytes(initial_manifest)
    real_inventory = route_engine.inventory_module
    tampered = False

    def inventory_then_tamper(path: Path, language: str, **kwargs: object) -> dict[str, object]:
        nonlocal tampered
        inventory = real_inventory(path, language, **kwargs)  # type: ignore[arg-type]
        if not tampered and language == "java" and path.name == source.name:
            assert path.resolve() != source.resolve()
            source.write_text("public final class EquivalenceModule {}\n", encoding="utf-8")
            manifest.write_text("{}\n", encoding="utf-8")
            tampered = True
        return inventory

    monkeypatch.setattr(route_engine, "inventory_module", inventory_then_tamper)
    output = tmp_path / "evidence"

    report = migrate_module(source, "java", "cpp", manifest, output)

    assert tampered is True
    assert report["status"] == "PASSED"
    assert report["module_input"]["source_artifact_sha256"] == sha256_bytes(initial_source)
    assert report["module_input"]["corpus_sha256"] == sha256_bytes(initial_manifest)
    assert source.read_bytes() != initial_source
    assert manifest.read_bytes() != initial_manifest


def test_cpp_to_java_whole_file_closure_binds_private_static_helper(
    tmp_path: Path,
) -> None:
    _require_native_toolchain("cpp")
    _require_native_toolchain("java")
    source = tmp_path / "arithmetic.cpp"
    source.write_text(
        "#include <cstdint>\n\n"
        "std::int64_t add(std::int64_t left, std::int64_t right) { return left + right; }\n"
        "std::int64_t subtract(std::int64_t left, std::int64_t right) "
        "{ return left - right; }\n"
        "std::int64_t divide(std::int64_t left, std::int64_t right) { return left / right; }\n",
        encoding="utf-8",
    )
    signatures = {
        symbol: {
            "parameters": [
                {"name": "left", "type": "integer"},
                {"name": "right", "type": "integer"},
            ],
            "return_type": "integer",
        }
        for symbol in ("add", "subtract", "divide")
    }
    expected = {"add": 9, "subtract": 5, "divide": 3}
    manifest = {
        "schema_version": "1.0.0",
        "profile": "typed-pure-module-v1",
        "composition": {
            "call_graph": [],
            "global_state": "none",
            "effects": "none",
            "exceptions": "canonical-arithmetic-errors-only",
            "input_domain": "canonical-finite-no-error-input-domain",
        },
        "functions": [
            {
                "symbol": symbol,
                "signature": signatures[symbol],
                "cases": [{"args": [7, 2], "expected": expected[symbol]}],
            }
            for symbol in ("add", "subtract", "divide")
        ],
    }
    manifest_path = tmp_path / "cases.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = migrate_module(
        source,
        "cpp",
        "java",
        manifest_path,
        tmp_path / "evidence",
    )

    closure = report["whole_file_closure"]
    assert len(closure["target_helper_symbols"]) == 1
    helper = closure["target_helper_symbols"][0]
    assert {
        key: helper[key]
        for key in (
            "helper_id",
            "name",
            "qualified_name",
            "declaration_kind",
            "analyzable",
            "occurrence",
            "arity",
            "visibility",
            "storage",
        )
    } == {
        "helper_id": "checked_div",
        "name": "elmosCheckedDiv",
        "qualified_name": "Migrated.elmosCheckedDiv",
        "declaration_kind": "method",
        "analyzable": True,
        "occurrence": 1,
        "arity": 2,
        "visibility": "private",
        "storage": "static",
    }
    assert helper["raw_signature"]["modifiers"] == [
        "private",
        "static",
    ]
    assert any(
        edge["callee"] == "Migrated.elmosCheckedDiv" and edge["callee_kind"] == "exact-generated-helper"
        for edge in closure["target_call_graph"]["edges"]
    )


@pytest.mark.parametrize(
    ("language", "fixture", "filename", "mutate", "reason"),
    [
        (
            "cpp",
            "fixtures/module/cpp/equivalence_module.cpp",
            "equivalence_module.cpp",
            lambda source: source + "\nstd::int64_t hidden(std::int64_t value) { return value; }\n",
            "PURE_MODULE_WHOLE_FILE_DECLARATION_NOT_ALLOWED:source:FunctionDecl:hidden",
        ),
        (
            "cpp",
            "fixtures/module/cpp/equivalence_module.cpp",
            "equivalence_module.cpp",
            lambda source: source.replace(
                "#include <cstdint>\n",
                "#include <cstdint>\nstd::int64_t hiddenState = 0;\n",
                1,
            ),
            "PURE_MODULE_WHOLE_FILE_DECLARATION_NOT_ALLOWED:source:VarDecl:hiddenState",
        ),
        (
            "java",
            "fixtures/module/java/EquivalenceModule.java",
            "EquivalenceModule.java",
            lambda source: source.replace(
                "public final class EquivalenceModule {",
                "public final class EquivalenceModule {\n    private EquivalenceModule() {}",
                1,
            ),
            ("PURE_MODULE_WHOLE_FILE_DECLARATION_NOT_ALLOWED:source:constructor:EquivalenceModule.<init>"),
        ),
        (
            "java",
            "fixtures/module/java/EquivalenceModule.java",
            "EquivalenceModule.java",
            lambda source: source + "\nfinal class Hidden {}\n",
            "PURE_MODULE_LANGUAGE_WRAPPER_COUNT_MISMATCH:source:2",
        ),
        (
            "java",
            "fixtures/module/java/EquivalenceModule.java",
            "EquivalenceModule.java",
            lambda source: "package example;\n" + source,
            "PURE_MODULE_WHOLE_FILE_DECLARATION_NOT_ALLOWED:source:package:example",
        ),
        (
            "java",
            "fixtures/module/java/EquivalenceModule.java",
            "EquivalenceModule.java",
            lambda source: source.replace(
                "public final class EquivalenceModule {",
                "public final class EquivalenceModule {\n    static {}",
                1,
            ),
            (
                "PURE_MODULE_WHOLE_FILE_DECLARATION_NOT_ALLOWED:source:"
                "static-initializer:EquivalenceModule.<static-initializer>"
            ),
        ),
        (
            "cpp",
            "fixtures/module/cpp/equivalence_module.cpp",
            "equivalence_module.cpp",
            lambda source: source.replace(
                "#include <cstdint>\n",
                "#include <cstdint>\ntypedef std::int64_t Hidden;\n",
                1,
            ),
            "PURE_MODULE_WHOLE_FILE_DECLARATION_NOT_ALLOWED:source:TypedefDecl:Hidden",
        ),
        (
            "cpp",
            "fixtures/module/cpp/equivalence_module.cpp",
            "equivalence_module.cpp",
            lambda source: source.replace(
                "#include <cstdint>\n",
                "#include <cstdint>\nusing Hidden = std::int64_t;\n",
                1,
            ),
            "PURE_MODULE_WHOLE_FILE_DECLARATION_NOT_ALLOWED:source:TypeAliasDecl:Hidden",
        ),
    ],
)
def test_source_whole_file_extra_declarations_fail_before_output(
    tmp_path: Path,
    language: str,
    fixture: str,
    filename: str,
    mutate: Callable[[str], str],
    reason: str,
) -> None:
    _require_native_toolchain(language)
    _require_native_toolchain("cpp" if language == "java" else "java")
    source = tmp_path / filename
    fixture_source = (ENGINE_ROOT / fixture).read_text(encoding="utf-8")
    source.write_text(mutate(fixture_source), encoding="utf-8")
    output = tmp_path / "must-not-exist"

    with pytest.raises(RouteError, match=reason):
        migrate_module(
            source,
            language,  # type: ignore[arg-type]
            "cpp" if language == "java" else "java",
            ENGINE_ROOT / "fixtures/module/cases.json",
            output,
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "prelude",
    [
        "#include <cstdint>\n#include <vector>\n",
        "#include <cstdint>\n#include <cstdint>\n",
        "#define HIDDEN 1\n#include <cstdint>\n",
        "#if 1\n#include <cstdint>\n#endif\n",
        "#pragma once\n#include <cstdint>\n",
        "#include \\\n<cstdint>\n",
    ],
)
def test_cpp_prelude_extra_duplicate_conditional_macro_pragma_and_continuation_fail_closed(
    tmp_path: Path,
    prelude: str,
) -> None:
    _require_native_toolchain("cpp")
    _require_native_toolchain("java")
    fixture = (ENGINE_ROOT / "fixtures/module/cpp/equivalence_module.cpp").read_text(encoding="utf-8")
    source = tmp_path / "equivalence_module.cpp"
    source.write_text(
        fixture.replace("#include <cstdint>\n", prelude, 1),
        encoding="utf-8",
    )
    output = tmp_path / "must-not-exist"

    with pytest.raises(RouteError, match="PURE_MODULE_LANGUAGE_PRELUDE_MISMATCH:source:cpp"):
        migrate_module(
            source,
            "cpp",
            "java",
            ENGINE_ROOT / "fixtures/module/cases.json",
            output,
        )
    assert not output.exists()
