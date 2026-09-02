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
    "elmos_polyglot_route.identifier_hygiene": "elmos_polyglot_route/identifier_hygiene.py",
    "elmos_polyglot_route.types": "elmos_polyglot_route/types.py",
    "elmos_polyglot_route.canonical": "elmos_polyglot_route/canonical.py",
    "elmos_polyglot_route.native": "elmos_polyglot_route/native.py",
    "elmos_polyglot_route.clang_analyzer": "elmos_polyglot_route/clang_analyzer.py",
    "elmos_polyglot_route.python_analyzer": "elmos_polyglot_route/python_analyzer.py",
    "elmos_polyglot_route.repository": "elmos_polyglot_route/repository.py",
    "elmos_polyglot_route.toolchains": "elmos_polyglot_route/toolchains.py",
    "elmos_polyglot_route.validation": "elmos_polyglot_route/validation.py",
}
ENGINE_RUNTIME_PROJECT_RELATIVE = "engines/polyglot-route-engine"
ENGINE_RUNTIME_MODULE_REPOSITORY_PATHS = {
    module_name: (f"{ENGINE_RUNTIME_PROJECT_RELATIVE}/src/{module_relative}")
    for module_name, module_relative in ENGINE_RUNTIME_MODULES.items()
}
ENGINE_SOURCE_REQUIRED_ASSETS = frozenset(
    {
        *ENGINE_RUNTIME_MODULE_REPOSITORY_PATHS.values(),
        f"{ENGINE_RUNTIME_PROJECT_RELATIVE}/uv.lock",
        "scripts/batch29/run_polyglot_routes.py",
        "scripts/batch29/validate_route.py",
    }
)
ENGINE_SOURCE_MANIFEST_FILE_KEYS = {
    "repository_path",
    "captured_path",
    "sha256",
    "bytes",
}
PINNED_Z3_VERSION = "4.16.0"
PYTHON_CAPTURED_ARCHIVE_RELATIVE = (
    "runtime/python/sha256-"
    "22625deaf5757e7c266cf1a096c9151a06b598b1e14632a2ec9993d58ec5fe84.tar.gz"
)
PYTHON_SOURCE_ARCHIVE_SHA256 = (
    "22625deaf5757e7c266cf1a096c9151a06b598b1e14632a2ec9993d58ec5fe84"
)
PYTHON_SOURCE_ARCHIVE_BYTES = 17_667_661
PYTHON_SOURCE_TREE_SHA256 = (
    "1400403c757cb4da3ce2df42d17d02e1368c54afd46bbed71ae84e25d081a154"
)
TYPESCRIPT_CAPTURED_ROOT_RELATIVE = (
    "runtime/typescript/sha256-"
    "61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
TYPESCRIPT_SOURCE_MANIFEST_SHA256 = (
    "61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
TYPESCRIPT_RUNTIME_MANIFEST_SHA256 = (
    "2157e43e757e433c733e144df7409a54f5040faa22af4a9b13de977a663fd939"
)
TYPESCRIPT_COMPILER_CLOSURE_SHA256 = (
    "aaab28fada5888d767a49f86d40e5a0c9073b23412257ccb3755e9c8fb8080d9"
)
TYPESCRIPT_COMPILER_FILE_COUNT = 108
TYPESCRIPT_COMPILER_BYTES = 19_067_381
SWIFT_BUILD_CLOSURE_COMPONENT_MAXIMUM_BYTES = 400_000_000
SWIFT_BUILD_CLOSURE_TREE_MAXIMUM_BYTES = 1_000_000_000

SPECIALIZED_NEGATIVE_CASES = {
    "java": frozenset({"java-int-width", "java-string-raw-reference-equality"}),
    "cpp": frozenset({"cpp-long-width", "cpp-unsigned-domain"}),
    "objc": frozenset({"objc-nsinteger-width", "objc-nsstring-pointer-identity"}),
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
    **{case_id: ("source",) for case_id in SPECIALIZED_NEGATIVE_ANALYZE_SPECS},
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
    "java-int-width": frozenset({"JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int"}),
    "java-string-raw-reference-equality": frozenset(
        {"JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET"}
    ),
    "cpp-long-width": frozenset({"CPP_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:long"}),
    "cpp-unsigned-domain": frozenset({"CPP_UNSUPPORTED_TYPE:unsigned long long"}),
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

NODEJS_NEGATIVE_ANALYZE_SOURCE_FILES = {
    "nodejs-ambiguous-jsdoc-type-unsupported": "ambiguous_jsdoc_type.mjs",
    "nodejs-async-function-unsupported": "async_function.mjs",
    "nodejs-coercive-equality-unsupported": "coercive_equality.mjs",
    "nodejs-dynamic-eval-unsupported": "dynamic_eval.mjs",
    "nodejs-generator-function-unsupported": "generator_function.mjs",
    "nodejs-import-unsupported": "module_import.mjs",
    "nodejs-missing-jsdoc-unsupported": "missing_jsdoc.mjs",
    "nodejs-promise-timer-unsupported": "promise_timer.mjs",
    "nodejs-this-prototype-unsupported": "this_prototype.mjs",
    "nodejs-top-level-side-effect-unsupported": "top_level_side_effect.mjs",
}
NODEJS_NEGATIVE_ANALYZE_FUNCTIONS = {
    "nodejs-ambiguous-jsdoc-type-unsupported": "ambiguousType",
    "nodejs-async-function-unsupported": "asyncValue",
    "nodejs-coercive-equality-unsupported": "coerciveEqual",
    "nodejs-dynamic-eval-unsupported": "dynamicEval",
    "nodejs-generator-function-unsupported": "generateValue",
    "nodejs-import-unsupported": "importedValue",
    "nodejs-missing-jsdoc-unsupported": "missingJsdoc",
    "nodejs-promise-timer-unsupported": "scheduleValue",
    "nodejs-this-prototype-unsupported": "prototypeValue",
    "nodejs-top-level-side-effect-unsupported": "topLevelValue",
}
NODEJS_NEGATIVE_SOURCE_EXTENSIONS = {
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
}
NODEJS_GENERATED_NEGATIVE_SPECS = {
    "nodejs-number-arithmetic-unsupported": (
        "node_number_arithmetic",
        "NodeNumberArithmetic",
        "addNumber",
        "NODEJS_NUMBER_ARITHMETIC_UNSUPPORTED",
    ),
    "nodejs-string-semantics-unsupported": (
        "node_string_semantics",
        "NodeStringSemantics",
        "echoString",
        "NODEJS_STRING_SEMANTICS_UNSUPPORTED",
    ),
    "nodejs-unsafe-integer-intermediate-boolean-unsupported": (
        "node_unsafe_intermediate_boolean",
        "NodeUnsafeIntermediateBoolean",
        "positiveAfterAdd",
        "NODEJS_CASE_UNSAFE_INTEGER_INTERMEDIATE_UNSUPPORTED",
    ),
    "nodejs-unsafe-integer-intermediate-integer-unsupported": (
        "node_unsafe_intermediate_integer",
        "NodeUnsafeIntermediateInteger",
        "cancelAfterAdd",
        "NODEJS_CASE_UNSAFE_INTEGER_INTERMEDIATE_UNSUPPORTED",
    ),
    "nodejs-unsafe-integer-intermediate-number-unsupported": (
        "node_unsafe_intermediate_number",
        "NodeUnsafeIntermediateNumber",
        "chooseAfterAdd",
        "NODEJS_CASE_UNSAFE_INTEGER_INTERMEDIATE_UNSUPPORTED",
    ),
    "nodejs-division-by-zero-unsupported": (
        "node_divide_by_zero",
        "NodeDivideByZero",
        "divide",
        "NODEJS_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN",
    ),
    "nodejs-modulo-by-zero-unsupported": (
        "node_modulo_by_zero",
        "NodeModuloByZero",
        "remainder",
        "NODEJS_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN",
    ),
    "nodejs-integer-overflow-unsupported": (
        "node_integer_overflow",
        "NodeIntegerOverflow",
        "multiply",
        "NODEJS_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN",
    ),
}
NODEJS_NEGATIVE_REASON_CODES = {
    "nodejs-ambiguous-jsdoc-type-unsupported": frozenset(
        {"JAVASCRIPT_EXACT_JSDOC_TYPE_REQUIRED:ambiguousType:value:Number"}
    ),
    "nodejs-async-function-unsupported": frozenset(
        {"JAVASCRIPT_ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET:asyncValue"}
    ),
    "nodejs-coercive-equality-unsupported": frozenset(
        {"JAVASCRIPT_OPERATOR_UNSUPPORTED:EqualsEqualsToken"}
    ),
    "nodejs-commonjs-unsupported": frozenset({"JAVASCRIPT_CJS_SOURCE_BLOCKED"}),
    "nodejs-dynamic-eval-unsupported": frozenset(
        {"JAVASCRIPT_EXPRESSION_UNSUPPORTED:CallExpression"}
    ),
    "nodejs-generator-function-unsupported": frozenset(
        {"JAVASCRIPT_FUNCTION_SHAPE_UNSUPPORTED:generateValue"}
    ),
    "nodejs-import-unsupported": frozenset(
        {"JAVASCRIPT_MODULE_IMPORT_EXPORT_OUTSIDE_CERTIFIED_SUBSET"}
    ),
    "nodejs-missing-jsdoc-unsupported": frozenset(
        {"JAVASCRIPT_EXACT_JSDOC_TAG_SET_REQUIRED:missingJsdoc"}
    ),
    "nodejs-promise-timer-unsupported": frozenset(
        {"JAVASCRIPT_EXPRESSION_UNSUPPORTED:CallExpression"}
    ),
    "nodejs-this-prototype-unsupported": frozenset(
        {"JAVASCRIPT_EXPRESSION_UNSUPPORTED:PropertyAccessExpression"}
    ),
    "nodejs-top-level-side-effect-unsupported": frozenset(
        {"JAVASCRIPT_TOP_LEVEL_STATEMENT_OUTSIDE_CERTIFIED_SUBSET:ExpressionStatement"}
    ),
    "nodejs-non-finite-case-unsupported": frozenset(
        {"NODEJS_CASE_NON_FINITE_NUMBER_UNSUPPORTED"}
    ),
    **{
        case_id: frozenset({specification[3]})
        for case_id, specification in NODEJS_GENERATED_NEGATIVE_SPECS.items()
    },
    "nodejs-unsafe-integer-case-unsupported": frozenset(
        {"NODEJS_CASE_UNSAFE_INTEGER_UNSUPPORTED"}
    ),
    "nodejs-unsafe-integer-result-unsupported": frozenset(
        {"NODEJS_CASE_UNSAFE_INTEGER_RESULT_UNSUPPORTED"}
    ),
    "undeclared-directed-route-fails-closed": frozenset(
        {"SOURCE_AND_TARGET_MUST_DIFFER"}
    ),
    "missing-symbol-fails-closed": frozenset(
        {"FUNCTION_NOT_FOUND", "NO_SUPPORTED_FUNCTIONS"}
    ),
}
NODEJS_NEGATIVE_INPUT_ROLES = {
    **{case_id: ("source",) for case_id in NODEJS_NEGATIVE_ANALYZE_SOURCE_FILES},
    **{case_id: ("source", "cases") for case_id in NODEJS_GENERATED_NEGATIVE_SPECS},
    "nodejs-commonjs-unsupported": ("source", "cases"),
    "nodejs-non-finite-case-unsupported": ("source", "cases"),
    "nodejs-unsafe-integer-case-unsupported": ("source", "cases"),
    "nodejs-unsafe-integer-result-unsupported": ("source", "cases"),
    "nodejs-typescript-integer-contract-unsupported": (
        "source-module",
        "case-manifest",
    ),
    "undeclared-directed-route-fails-closed": (
        "source-module",
        "case-manifest",
    ),
    "missing-symbol-fails-closed": ("source", "cases"),
}


def _nodejs_route_error_code(reason: object) -> str | None:
    """Return one exact Node.js domain code from a native wrapper or direct error."""

    if not isinstance(reason, str) or not reason or "\n" in reason or "\r" in reason:
        return None
    detail = reason
    prefix = "NATIVE_ANALYZER_FAILED:"
    if reason.startswith(prefix):
        wrapped = reason[len(prefix) :].split(":", 1)
        if len(wrapped) != 2 or not Path(wrapped[0]).is_absolute():
            return None
        detail = wrapped[1]
    code = detail.split(":", 1)[0]
    if re.fullmatch(r"[A-Z][A-Z0-9_]*", code) is None:
        return None
    return code


def _nodejs_stable_route_error(reason: object) -> str | None:
    """Project a native analyzer wrapper onto its stable semantic error text."""

    if not isinstance(reason, str) or not reason or "\n" in reason or "\r" in reason:
        return None
    prefix = "NATIVE_ANALYZER_FAILED:"
    if not reason.startswith(prefix):
        return reason
    wrapped = reason[len(prefix) :].split(":", 1)
    if len(wrapped) != 2 or not Path(wrapped[0]).is_absolute():
        return None
    return wrapped[1]


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
V3_RESEARCH_CAPABILITY_STATUS = {
    "experimental",
    "detected-only",
    "blocked",
}
V3_TARGET_EMITTER_RELATIVE_PATH = (
    "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py"
)
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
    "identifier-plan",
    "raw-target-ir",
    "normalized-target-ir",
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
    "identifier_hygiene",
    "implementation_identity",
    "analyzer_identity",
    "emitter_identity",
    "solver",
    "environment",
    "environment_assumptions",
    "unsupported_semantics",
}
FORMAL_IDENTIFIER_HYGIENE_KEYS = {
    "kind",
    "policy_id",
    "policy_sha256",
    "unit_namespace",
    "unit_namespace_sha256",
    "plan",
    "plan_digest",
    "source_function_name",
    "target_function_name",
    "raw_target_relift_ir",
    "normalized_target_ir",
}
FORMAL_IR_BINDING_KEYS = {
    "role",
    "artifact",
    "semantic_ir",
    "semantic_ir_sha256",
    "formal_function",
    "formal_function_sha256",
}
MODULE_FUNCTION_LAYER_KEYS = {"semantic", "chunk", "behavior", "formal"}
MODULE_PASSING_PROOF_STATUSES = {"PROVED", "PROVED_UNDER_ASSUMPTIONS"}
MODULE_ARTIFACT_ROLES = {
    "identifier-plan",
    "raw-target-ir",
    "normalized-target-ir",
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
    "source-javascript-esm-descriptor",
    "module-case-manifest",
    "source-module-inventory",
    "target-module-inventory",
    "whole-file-module-closure",
    "swift-analyzer-build-receipt",
}
JAVASCRIPT_ESM_DESCRIPTOR_KEYS = {
    "logical_path",
    "snapshot_path",
    "artifact_path",
    "sha256",
    "bytes",
    "type",
}
JAVASCRIPT_ESM_DESCRIPTOR_OBSERVATION_KEYS = {"observed_origin_path"}
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
SWIFT_DEPENDENCY_SEED = "verified-content-addressed-standalone-cache"
SWIFT_ANALYZER_MIRROR_SEEDS = frozenset({SWIFT_DEPENDENCY_SEED})
SWIFT_DEPENDENCY_IDENTITY = "swift-syntax"
SWIFT_DEPENDENCY_VERSION = "600.0.1"
SWIFT_DEPENDENCY_REVISION = "0687f71944021d616d34d922343dcef086855920"
SWIFT_DEPENDENCY_SHA256 = (
    "sha256:b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
)
SWIFT_DEPENDENCY_FILE_COUNT = 753
SWIFT_DEPENDENCY_BYTES = 8_866_479
SWIFT_DEPENDENCY_CACHE_SCHEMA = "swift-dependencies-standalone-v2"
SWIFT_DEPENDENCY_OBJECT_STORE_POLICY = "standalone-no-alternates-no-hardlinks-v2"
SWIFT_DEPENDENCY_CACHE_KEY = (
    "swift-syntax-standalone-v2-600.0.1-"
    "0687f71944021d616d34d922343dcef086855920-"
    "b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
)
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
SWIFT_ANALYZER_MIRROR_KEYS = {
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
SWIFT_GIT_PATH = "/Applications/Xcode.app/Contents/Developer/usr/bin/git"
SWIFT_GIT_SHA256 = (
    "sha256:10f9c1df894525ae4c7454258febab6d3d25071062b42cb48dbb1842cdffd2a9"
)
SWIFT_GIT_BYTES = 3_704_880
SWIFT_GIT_VERSION = "git version 2.50.1 (Apple Git-155)"
SWIFT_ANALYZER_RECEIPT_KEYS = {
    "schema_version",
    "kind",
    "source_inputs",
    "dependency",
    "toolchain",
    "network_isolation",
    "build",
    "binary",
    "execution_seal",
    "canonical_identity",
}
SWIFT_ANALYZER_BINARY_KEYS = {
    "name",
    "path",
    "sha256",
    "bytes",
    "mode",
    "uid",
    "gid",
    "nlink",
    "device",
    "inode",
}
SWIFT_ANALYZER_EXECUTION_SEAL_KEYS = {
    "policy",
    "root",
    "mode",
    "uid",
    "gid",
    "device",
    "inode",
    "binary",
}
SWIFT_XCODE_ROOT = "/Applications/Xcode.app/Contents"
SWIFT_TOOLCHAIN_ROOT = (
    f"{SWIFT_XCODE_ROOT}/Developer/Toolchains/XcodeDefault.xctoolchain"
)
SWIFT_PLATFORM_ROOT = (
    f"{SWIFT_XCODE_ROOT}/Developer/Platforms/MacOSX.platform/Developer"
)
SWIFT_SDK_ROOT = f"{SWIFT_PLATFORM_ROOT}/SDKs/MacOSX26.5.sdk"
SWIFT_SDK_RESOLVED_ROOT = f"{SWIFT_PLATFORM_ROOT}/SDKs/MacOSX.sdk"
SWIFT_SHARED_FRAMEWORKS = f"{SWIFT_XCODE_ROOT}/SharedFrameworks"
SWIFT_BUILD_CLOSURE_SCHEMA = "swiftpm-build-execution-closure-v1"
SWIFT_BUILD_CLOSURE_SCOPE = (
    "pinned-local-xcode-swiftpm-direct-components-and-critical-sdk-projection-v1"
)
SWIFT_BUILD_CLOSURE_COMPONENT_SPECS = (
    (
        "swift-dispatcher",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-frontend",
        "swift-frontend",
        "2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb",
        171_036_592,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swiftc-dispatcher",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swiftc",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-frontend",
        "swift-frontend",
        "2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb",
        171_036_592,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-build-dispatcher",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-build",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-package",
        "swift-package",
        "dc1a5f5bd4f05be81b8cc4a4bc6e0fd8846210e4cb829062d0fed3d03f79b753",
        23_293_616,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-package",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-package",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-package",
        None,
        "dc1a5f5bd4f05be81b8cc4a4bc6e0fd8846210e4cb829062d0fed3d03f79b753",
        23_293_616,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-driver",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-driver",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-driver",
        None,
        "fead52ebe00ec6ec700ecbb4be30f0b6204dd0506cb271dda72ac257261bd64b",
        3_011_968,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-frontend",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-frontend",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/swift-frontend",
        None,
        "2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb",
        171_036_592,
        "0755",
        0,
        0,
        1,
    ),
    (
        "clang",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/clang",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/clang",
        None,
        "7def90dd8829726686213a747fc5bff1583df933dae5edc55d755479e0bfe00a",
        141_373_024,
        "0755",
        0,
        0,
        1,
    ),
    (
        "clangxx-dispatcher",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/clang++",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/clang",
        "clang",
        "7def90dd8829726686213a747fc5bff1583df933dae5edc55d755479e0bfe00a",
        141_373_024,
        "0755",
        0,
        0,
        1,
    ),
    (
        "linker",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/ld",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/ld",
        None,
        "5897b275efd93b201b6df5832dd541262b3f20f290859ba78f2200a6a66ef38b",
        2_331_792,
        "0755",
        0,
        0,
        1,
    ),
    (
        "archiver",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/ar",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/ar",
        None,
        "e49ffad64ad1cee722540fc5ecb00a230fd8071680682c60d9c851029d20e814",
        73_520,
        "0755",
        0,
        0,
        1,
    ),
    (
        "libtool",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/libtool",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/bin/libtool",
        None,
        "229eb9d8027953d2aee0590f983eed587d52bdd1ebc21114a62ce693f77b03f1",
        210_800,
        "0755",
        0,
        0,
        1,
    ),
    (
        "platform-swift-plugin-server",
        f"{SWIFT_PLATFORM_ROOT}/usr/bin/swift-plugin-server",
        f"{SWIFT_PLATFORM_ROOT}/usr/bin/swift-plugin-server",
        None,
        "438b8b9027176baed23c149a51250a94dc6a6360116aa818523168d1c4df68c8",
        71_520,
        "0755",
        0,
        0,
        1,
    ),
    (
        "in-process-plugin-server",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/host/libSwiftInProcPluginServer.dylib",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/host/libSwiftInProcPluginServer.dylib",
        None,
        "55385f1fbf98dd8e9a73cd0e87c0d93fbc778c6abe04c6fb744bff9278ef5811",
        91_424,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-driver-library",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/libSwiftDriver.dylib",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/libSwiftDriver.dylib",
        None,
        "38ea28895a054a7d72da72042a786722884b62cdefdf0362d18f84a174ef87fb",
        3_031_376,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-tools-support-library",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/libSwiftToolsSupport.dylib",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/libSwiftToolsSupport.dylib",
        None,
        "066f824adc6dffbfb4b88aeec2bce96bc2634b4cda4922ee2e999b4c9df431c1",
        1_190_496,
        "0755",
        0,
        0,
        1,
    ),
    (
        "build-server-protocol",
        f"{SWIFT_SHARED_FRAMEWORKS}/BuildServerProtocol.framework/Versions/A/BuildServerProtocol",
        f"{SWIFT_SHARED_FRAMEWORKS}/BuildServerProtocol.framework/Versions/A/BuildServerProtocol",
        None,
        "05be7dcb9f19802d036a5caa5cc5530c63ed0f2b3133185910200a5ee48dcec3",
        488_112,
        "0755",
        0,
        0,
        1,
    ),
    (
        "language-server-protocol",
        f"{SWIFT_SHARED_FRAMEWORKS}/LanguageServerProtocol.framework/Versions/A/LanguageServerProtocol",
        f"{SWIFT_SHARED_FRAMEWORKS}/LanguageServerProtocol.framework/Versions/A/LanguageServerProtocol",
        None,
        "7c4f0641f2d7533c2432bd0234e285bbd464274b8928b335bf2861cda19f5e00",
        2_689_424,
        "0755",
        0,
        0,
        1,
    ),
    (
        "language-server-protocol-transport",
        f"{SWIFT_SHARED_FRAMEWORKS}/LanguageServerProtocolTransport.framework/Versions/A/LanguageServerProtocolTransport",
        f"{SWIFT_SHARED_FRAMEWORKS}/LanguageServerProtocolTransport.framework/Versions/A/LanguageServerProtocolTransport",
        None,
        "3ef1a0607d060769cdae18edbae5f622d974d2f2b157385d6cb03c6d6e6f8069",
        254_480,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swb-build-service",
        f"{SWIFT_SHARED_FRAMEWORKS}/SwiftBuild.framework/Versions/A/PlugIns/SWBBuildService.bundle/Contents/Frameworks/SWBBuildService.framework/Versions/A/SWBBuildService",
        f"{SWIFT_SHARED_FRAMEWORKS}/SwiftBuild.framework/Versions/A/PlugIns/SWBBuildService.bundle/Contents/Frameworks/SWBBuildService.framework/Versions/A/SWBBuildService",
        None,
        "9e8908fcb0d74d0348b31641c0d3ec0fc97bd6467f82a574b1756432a73433de",
        1_395_264,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swb-project-model",
        f"{SWIFT_SHARED_FRAMEWORKS}/SwiftBuild.framework/Versions/A/PlugIns/SWBBuildService.bundle/Contents/Frameworks/SWBProjectModel.framework/Versions/A/SWBProjectModel",
        f"{SWIFT_SHARED_FRAMEWORKS}/SwiftBuild.framework/Versions/A/PlugIns/SWBBuildService.bundle/Contents/Frameworks/SWBProjectModel.framework/Versions/A/SWBProjectModel",
        None,
        "46c09eeff03bf97d179e6b6385fe6a58fea28245d6125ac61943a7615cc2acf9",
        540_144,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swb-util",
        f"{SWIFT_SHARED_FRAMEWORKS}/SwiftBuild.framework/Versions/A/PlugIns/SWBBuildService.bundle/Contents/Frameworks/SWBUtil.framework/Versions/A/SWBUtil",
        f"{SWIFT_SHARED_FRAMEWORKS}/SwiftBuild.framework/Versions/A/PlugIns/SWBBuildService.bundle/Contents/Frameworks/SWBUtil.framework/Versions/A/SWBUtil",
        None,
        "165998df0e1326f5b254f40e0efe57e501f03c93bbe8ce306c82e8a77f14646c",
        3_196_784,
        "0755",
        0,
        0,
        1,
    ),
    (
        "swift-build-framework",
        f"{SWIFT_SHARED_FRAMEWORKS}/SwiftBuild.framework/Versions/A/SwiftBuild",
        f"{SWIFT_SHARED_FRAMEWORKS}/SwiftBuild.framework/Versions/A/SwiftBuild",
        None,
        "3ae14a15416d3641949cb4eedecd972eec863eb058e753f1f564e5f35fe01973",
        3_413_216,
        "0755",
        0,
        0,
        1,
    ),
    (
        "tools-protocols-swift-extensions",
        f"{SWIFT_SHARED_FRAMEWORKS}/ToolsProtocolsSwiftExtensions.framework/Versions/A/ToolsProtocolsSwiftExtensions",
        f"{SWIFT_SHARED_FRAMEWORKS}/ToolsProtocolsSwiftExtensions.framework/Versions/A/ToolsProtocolsSwiftExtensions",
        None,
        "cf57590d1be3819fbbb7ebc51435423804e9b34723b068a1b5f83e11abe603bd",
        199_824,
        "0755",
        0,
        0,
        1,
    ),
    (
        "llbuild-framework",
        f"{SWIFT_SHARED_FRAMEWORKS}/llbuild.framework/Versions/A/llbuild",
        f"{SWIFT_SHARED_FRAMEWORKS}/llbuild.framework/Versions/A/llbuild",
        None,
        "25bfb2c3d42c28cc5b01bd303268f63e26ee017c54c626d98bddbe135ed28f36",
        1_432_608,
        "0755",
        0,
        0,
        1,
    ),
    (
        "sdk-settings-json",
        f"{SWIFT_SDK_ROOT}/SDKSettings.json",
        f"{SWIFT_SDK_RESOLVED_ROOT}/SDKSettings.json",
        None,
        "f8d005f09381389167f9e0aeaa169bc9e7dff162ef22ca2fd8e98df7ff1acafe",
        7_774,
        "0644",
        0,
        0,
        1,
    ),
    (
        "sdk-settings-plist",
        f"{SWIFT_SDK_ROOT}/SDKSettings.plist",
        f"{SWIFT_SDK_RESOLVED_ROOT}/SDKSettings.plist",
        None,
        "e5c7c40b8c5dc1a9f99f8b9fa51870f8fe180421225b8201d0c4c826aad11bdc",
        5_388,
        "0644",
        0,
        0,
        1,
    ),
    (
        "sdk-foundation-tbd",
        f"{SWIFT_SDK_ROOT}/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation.tbd",
        f"{SWIFT_SDK_RESOLVED_ROOT}/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation.tbd",
        None,
        "f425b7c55986e46ab62fd8d8a457ee3fb1ddbe4af46b41abe1e63110ef7fba44",
        5_602_567,
        "0644",
        0,
        0,
        1,
    ),
    (
        "sdk-libswift-foundation-tbd",
        f"{SWIFT_SDK_ROOT}/usr/lib/swift/libswiftFoundation.tbd",
        f"{SWIFT_SDK_RESOLVED_ROOT}/usr/lib/swift/libswiftFoundation.tbd",
        None,
        "c9a08100fa08663ed70835c177b05ce9ff4a0f81bfb6b7d32114cdc0e0371539",
        420,
        "0644",
        0,
        0,
        1,
    ),
)
SWIFT_BUILD_CLOSURE_TREE_SPECS = (
    (
        "manifest-api",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/pm/ManifestAPI",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/pm/ManifestAPI",
        "aaf47697e4ada643c682431426648cc1a915416afd2caf5beec096f8fa36417a",
        9,
        3_659_442,
    ),
    (
        "plugin-api",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/pm/PluginAPI",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/pm/PluginAPI",
        "1a3dd060b6803d6873648832cea0b52635f9ae1a261e34bfeb133f7178ca645a",
        5,
        3_386_557,
    ),
    (
        "toolchain-host-plugins",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/host/plugins",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/host/plugins",
        "912a7dbdbe6735e08ce84b0c7f313d18e4bb0ebf850c36f199cc1b46e35357ed",
        4,
        1_617_344,
    ),
    (
        "platform-host-plugins",
        f"{SWIFT_PLATFORM_ROOT}/usr/lib/swift/host/plugins",
        f"{SWIFT_PLATFORM_ROOT}/usr/lib/swift/host/plugins",
        "6408d05c19f22daf7918307aa95077d8f2849fce8c85b722c90d5d9b1fa6d417",
        15,
        5_125_484,
    ),
    (
        "sdk-foundation-module",
        f"{SWIFT_SDK_ROOT}/System/Library/Frameworks/Foundation.framework/Versions/C/Modules",
        f"{SWIFT_SDK_RESOLVED_ROOT}/System/Library/Frameworks/Foundation.framework/Versions/C/Modules",
        "7165c4716fa827f8803998ea3e436e4458539900c0511cd61d3327293890d1f9",
        9,
        7_727_385,
    ),
    (
        "sdk-corefoundation-module",
        f"{SWIFT_SDK_ROOT}/usr/lib/swift/CoreFoundation.swiftmodule",
        f"{SWIFT_SDK_RESOLVED_ROOT}/usr/lib/swift/CoreFoundation.swiftmodule",
        "a0405db90f83fb73a3fa7c63d4aa5f23c801d9fe07c24e690fb309837569710d",
        8,
        104_510,
    ),
    (
        "sdk-objectivec-module",
        f"{SWIFT_SDK_ROOT}/usr/lib/swift/ObjectiveC.swiftmodule",
        f"{SWIFT_SDK_RESOLVED_ROOT}/usr/lib/swift/ObjectiveC.swiftmodule",
        "09c0b3b5ccc32bf959edf60385077623eda7e9f3b8a03f229fd655a08376845c",
        8,
        52_177,
    ),
    (
        "sdk-darwin-foundation1-module",
        f"{SWIFT_SDK_ROOT}/usr/lib/swift/_DarwinFoundation1.swiftmodule",
        f"{SWIFT_SDK_RESOLVED_ROOT}/usr/lib/swift/_DarwinFoundation1.swiftmodule",
        "afd2771e20e7908556e4093be833fc27a989610d1a67adcf3d2192fc0bed20a1",
        8,
        162_910,
    ),
    (
        "sdk-darwin-foundation2-module",
        f"{SWIFT_SDK_ROOT}/usr/lib/swift/_DarwinFoundation2.swiftmodule",
        f"{SWIFT_SDK_RESOLVED_ROOT}/usr/lib/swift/_DarwinFoundation2.swiftmodule",
        "7cb0327244e386b14d8464ed2bcabcbd307ac72e303786d590a0dc90b9535b72",
        8,
        12_270,
    ),
    (
        "sdk-darwin-foundation3-module",
        f"{SWIFT_SDK_ROOT}/usr/lib/swift/_DarwinFoundation3.swiftmodule",
        f"{SWIFT_SDK_RESOLVED_ROOT}/usr/lib/swift/_DarwinFoundation3.swiftmodule",
        "8662a95e3ab622e93e92ce13177a31d6831760e49906357c457e7aa811ece40a",
        8,
        7_854,
    ),
    (
        "toolchain-foundation-prebuilt-module",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/macosx/prebuilt-modules/26.5/Foundation.swiftmodule",
        f"{SWIFT_TOOLCHAIN_ROOT}/usr/lib/swift/macosx/prebuilt-modules/26.5/Foundation.swiftmodule",
        "cc03cfb24425d6842fe72ed89c2f2b2e26ae641cb35cd3211e3f2d93d5bd9b93",
        4,
        15_112_272,
    ),
    (
        "sdk-foundation-headers",
        f"{SWIFT_SDK_ROOT}/System/Library/Frameworks/Foundation.framework/Versions/C/Headers",
        f"{SWIFT_SDK_RESOLVED_ROOT}/System/Library/Frameworks/Foundation.framework/Versions/C/Headers",
        "7c6b6a8f06f51aeaa26411b9fb79cb28800461f939eac310c2be9a4f5edcec91",
        174,
        1_707_906,
    ),
    (
        "sdk-objc-headers",
        f"{SWIFT_SDK_ROOT}/usr/include/objc",
        f"{SWIFT_SDK_RESOLVED_ROOT}/usr/include/objc",
        "798fa35ace9193dc45fceb26954f025f04b67116e329596673319d851485517a",
        17,
        136_132,
    ),
)


def _expected_swift_build_closure() -> dict[str, Any]:
    return {
        "schema": SWIFT_BUILD_CLOSURE_SCHEMA,
        "scope": SWIFT_BUILD_CLOSURE_SCOPE,
        "compiler_runtime_soundness": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "components": [
            {
                "role": role,
                "path": path,
                "resolved_path": resolved,
                "link_target": link_target,
                "sha256": "sha256:" + sha256,
                "bytes": byte_count,
                "mode": mode,
                "uid": uid,
                "gid": gid,
                "nlink": nlink,
            }
            for (
                role,
                path,
                resolved,
                link_target,
                sha256,
                byte_count,
                mode,
                uid,
                gid,
                nlink,
            ) in SWIFT_BUILD_CLOSURE_COMPONENT_SPECS
        ],
        "trees": [
            {
                "role": role,
                "root": root,
                "sha256": "sha256:" + sha256,
                "file_count": file_count,
                "bytes": byte_count,
            }
            for role, root, _resolved, sha256, file_count, byte_count in SWIFT_BUILD_CLOSURE_TREE_SPECS
        ],
    }


SWIFT_ANALYZER_BUILD_CLOSURE = _expected_swift_build_closure()
SWIFT_ANALYZER_TOOLCHAIN = {
    "swiftc": (
        "/Applications/Xcode.app/Contents/Developer/Toolchains/"
        "XcodeDefault.xctoolchain/usr/bin/swiftc"
    ),
    "swiftc_sha256": (
        "sha256:2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb"
    ),
    "swift_driver": (
        "/Applications/Xcode.app/Contents/Developer/Toolchains/"
        "XcodeDefault.xctoolchain/usr/bin/swift"
    ),
    "swift_driver_sha256": (
        "sha256:2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb"
    ),
    "version": ("Apple Swift version 6.3.3 (swiftlang-6.3.3.1.3 clang-2100.1.1.101)"),
    "profile": [
        "platform=Darwin/arm64",
        "xcode=26.6/17F113",
        "macosx-sdk=26.5",
        (
            "sdk-path=/Applications/Xcode.app/Contents/Developer/Platforms/"
            "MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk"
        ),
        "swift-language-mode=6",
        "integer=Int64",
    ],
    "build_closure": SWIFT_ANALYZER_BUILD_CLOSURE,
}
SWIFT_ANALYZER_BUILD = {
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
}
SWIFT_NETWORK_PROBE_COMPILER = next(
    component
    for component in SWIFT_ANALYZER_BUILD_CLOSURE["components"]
    if component["role"] == "clang"
)
SWIFT_NETWORK_POLICY_TEXT = "(version 1)\n(allow default)\n(deny network*)\n"
SWIFT_NETWORK_POLICY_SHA256 = (
    "sha256:5c358b8d847211333e7ba22df82d84f796b5f30a41a2682209a949d783adbd08"
)
SWIFT_NETWORK_PROBE_SOURCE = r"""#include <arpa/inet.h>
#include <errno.h>
#include <stdint.h>
#include <sys/socket.h>
#include <unistd.h>

int main(void) {
    const int descriptor = socket(AF_INET, SOCK_STREAM, 0);
    if (descriptor < 0) {
        return 2;
    }
    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = htons(9);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    errno = 0;
    const int status = connect(
        descriptor,
        (const struct sockaddr *)&address,
        (socklen_t)sizeof(address)
    );
    const int error = errno;
    if (close(descriptor) != 0) {
        return 3;
    }
    if (status != -1 || error != EPERM) {
        return 4;
    }
    static const char result[] = "NETWORK_DENIED:1\n";
    const ssize_t written = write(STDOUT_FILENO, result, sizeof(result) - 1);
    if (written != (ssize_t)(sizeof(result) - 1)) {
        return 5;
    }
    return 0;
}
"""
SWIFT_NETWORK_PROBE_SOURCE_SHA256 = (
    "sha256:8a82a5f438ec38c0e733881eb868d91a4fb82c3ce95c3d8f27507a720dee7c19"
)
SWIFT_NETWORK_PROBE_SOURCE_BYTES = 923
SWIFT_NETWORK_PROBE_BINARY_NAME = "ElmosNetworkDenyProbe"
SWIFT_NETWORK_PROBE_BINARY_SHA256 = (
    "sha256:446fc22c935c695feeea983fe3dba5705b399d32c93c285d797b7d90d0bdcbb7"
)
SWIFT_NETWORK_PROBE_BINARY_BYTES = 33_784
SWIFT_NETWORK_PROBE_UUID = "3C8F074C-FA7E-3977-B467-A98D3FC2BE00"
SWIFT_NETWORK_PROBE_CDHASH_FULL = (
    "5e87ec802f0589e8d88db8eed94de7f41f5c855110c202ec3959cb8cfb9d7dc4"
)
SWIFT_NETWORK_PROBE_LINKED_LIBRARIES = ["/usr/lib/libSystem.B.dylib"]
SWIFT_NETWORK_PROBE_BUILD_ARGV = [
    "<sandbox-exec>",
    "-p",
    "<deny-network-policy>",
    "<clang>",
    "-x",
    "c",
    "-std=c17",
    "-target",
    "arm64-apple-macosx26.0",
    "-Os",
    "-fno-ident",
    "-isysroot",
    "<swift-sdk>",
    "-Wl,-dead_strip",
    "-o",
    "<probe-output>",
    "-",
]
SWIFT_NETWORK_PROBE_BUILD_ENVIRONMENT = {
    "PATH": (
        "<swift-toolchain-bin>:<system-usr-bin>:<system-bin>:"
        "<system-usr-sbin>:<system-sbin>"
    ),
    "HOME": "<isolated-home>",
    "TMPDIR": "<isolated-tmp>",
    "LANG": "C",
    "LC_ALL": "C",
    "TZ": "UTC",
    "NO_COLOR": "1",
    "CLICOLOR": "0",
    "SOURCE_DATE_EPOCH": "0",
    "ZERO_AR_DATE": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "<null-device>",
    "GIT_TERMINAL_PROMPT": "0",
    "XDG_CACHE_HOME": "<isolated-home>/.cache",
    "PYTHONHASHSEED": "0",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "SWIFT_DETERMINISTIC_HASHING": "1",
}
SWIFT_NETWORK_SANDBOX = {
    "path": "/usr/bin/sandbox-exec",
    "sha256": (
        "sha256:abc5bb136d6b5cce8fa85d789f78e3326c51ca60cae637b2064adfb67a1dcd9a"
    ),
    "bytes": 102_368,
    "mode": "0755",
    "uid": 0,
    "gid": 0,
    "nlink": 1,
    "cdhash_full": ("4828e16826baf4052b8212b82d1f3f2c13216303e062f0cc2b398f045d422625"),
}
SWIFT_NETWORK_VERIFIER = {
    "path": "/usr/bin/codesign",
    "sha256": (
        "sha256:844d30a12929b59c9f2215e2a308c3e1db572831a478f35906e452a54025603e"
    ),
    "bytes": 458_576,
    "mode": "0755",
    "uid": 0,
    "gid": 0,
    "nlink": 1,
}
SWIFT_NETWORK_PROBE_KEYS = {
    "result",
    "source",
    "build",
    "binary",
    "execution_seal",
    "mach_o",
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
    "identifier_hygiene",
}
SPECIALIZED_INPUT_DOMAIN = "canonical-finite-no-error-input-domain"
SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC = "BLOCKED_NOT_EQUIVALENTLY_MODELED"
NODEJS_INPUT_DOMAIN = "nodejs-es2022-esm-safe-integer-finite-v1"
NODEJS_OUT_OF_DOMAIN_BEHAVIOR = (
    "BLOCKED_OUTSIDE_NODEJS_ES2022_ESM_SAFE_INTEGER_FINITE_V1"
)
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
    "identifier_hygiene",
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
MODULE_IDENTIFIER_HYGIENE_KEYS = {
    "status",
    "policy_id",
    "policy_sha256",
    "unit_namespace",
    "unit_namespace_sha256",
    "plan",
    "raw_target_ir",
    "normalized_target_ir",
    "functions",
    "renamed",
}
WHOLE_FILE_IDENTIFIER_HYGIENE_KEYS = {
    "status",
    "policy_id",
    "policy_sha256",
    "unit_namespace",
    "unit_namespace_sha256",
    "plan_sha256",
    "functions",
}
IDENTIFIER_FUNCTION_MAPPING_KEYS = {
    "raw_symbol",
    "canonical_symbol",
    "parameters",
}
IDENTIFIER_PARAMETER_MAPPING_KEYS = {
    "raw_name",
    "canonical_name",
    "canonical_type",
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


def _validate_engine_runtime_source_receipts(
    source_manifest: dict[str, Any],
    files_by_repository_path: dict[str, dict[str, Any]],
    captured_paths_by_repository_path: dict[str, Path],
    failures: list[str],
) -> None:
    """Cross-bind every portable runtime source to its captured manifest entry."""

    if set(source_manifest) != {
        "schema_version",
        "kind",
        "file_count",
        "files",
        "runtime_source_receipts",
    }:
        failures.append("engine source manifest fields are not exact")
        return
    if (
        source_manifest.get("schema_version") != 1
        or source_manifest.get("kind") != "polyglot-route-engine-source-bundle"
    ):
        failures.append("engine source manifest identity is invalid")
    receipts = source_manifest.get("runtime_source_receipts")
    if not isinstance(receipts, dict) or set(receipts) != {
        "python_source_archive",
        "typescript_compiler_closure",
    }:
        failures.append("engine runtime source receipts are not exact")
        return

    python = receipts.get("python_source_archive")
    python_keys = {
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
    }
    if not isinstance(python, dict) or set(python) != python_keys:
        failures.append("engine Python source archive receipt is not exact")
        return
    if (
        python.get("schema_version") != 1
        or python.get("capture_relative_path") != PYTHON_CAPTURED_ARCHIVE_RELATIVE
        or python.get("sha256") != PYTHON_SOURCE_ARCHIVE_SHA256
        or python.get("bytes") != PYTHON_SOURCE_ARCHIVE_BYTES
        or python.get("mode") != "0444"
        or python.get("nlink") != 1
        or python.get("source_tree_sha256") != PYTHON_SOURCE_TREE_SHA256
        or python.get("source_tree_record_count") != 1_899
        or python.get("source_tree_file_count") != 1_890
        or python.get("source_tree_bytes") != 47_880_708
        or not isinstance(python.get("uid"), int)
        or isinstance(python.get("uid"), bool)
        or not isinstance(python.get("gid"), int)
        or isinstance(python.get("gid"), bool)
    ):
        failures.append("engine Python source archive receipt identity is invalid")
    python_entry = files_by_repository_path.get(PYTHON_CAPTURED_ARCHIVE_RELATIVE)
    python_path = captured_paths_by_repository_path.get(
        PYTHON_CAPTURED_ARCHIVE_RELATIVE
    )
    if (
        python_entry is None
        or python_entry.get("sha256") != f"sha256:{PYTHON_SOURCE_ARCHIVE_SHA256}"
        or python_entry.get("bytes") != PYTHON_SOURCE_ARCHIVE_BYTES
        or python_path is None
        or f"{stat.S_IMODE(python_path.stat().st_mode):04o}" != "0444"
    ):
        failures.append("engine Python source archive entry does not match its receipt")

    typescript = receipts.get("typescript_compiler_closure")
    typescript_keys = {
        "schema_version",
        "capture_relative_path",
        "source_manifest_sha256",
        "runtime_manifest_sha256",
        "compiler_closure_sha256",
        "file_count",
        "bytes",
        "files",
        "semantic_soundness",
    }
    if not isinstance(typescript, dict) or set(typescript) != typescript_keys:
        failures.append("engine TypeScript compiler closure receipt is not exact")
        return
    records = typescript.get("files")
    if not isinstance(records, list) or len(records) != TYPESCRIPT_COMPILER_FILE_COUNT:
        failures.append("engine TypeScript compiler closure file set is not exact")
        return
    paths: list[str] = []
    total_bytes = 0
    stable_source_records: list[dict[str, Any]] = []
    stable_runtime_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != {
            "path",
            "sha256",
            "bytes",
            "mode",
        }:
            failures.append(
                f"engine TypeScript compiler closure files[{index}] is not exact"
            )
            continue
        relative = record.get("path")
        digest = record.get("sha256")
        byte_count = record.get("bytes")
        mode = record.get("mode")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in Path(relative).parts)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count <= 0
            or mode not in {"0444", "0555"}
        ):
            failures.append(
                f"engine TypeScript compiler closure files[{index}] is invalid"
            )
            continue
        paths.append(relative)
        total_bytes += byte_count
        stable_source_records.append(
            {"path": relative, "bytes": byte_count, "sha256": digest}
        )
        stable_runtime_records.append(
            {
                "path": relative,
                "bytes": byte_count,
                "sha256": digest,
                "mode": mode,
            }
        )
        repository_path = f"{TYPESCRIPT_CAPTURED_ROOT_RELATIVE}/{relative}"
        entry = files_by_repository_path.get(repository_path)
        captured_path = captured_paths_by_repository_path.get(repository_path)
        if (
            entry is None
            or entry.get("sha256") != f"sha256:{digest}"
            or entry.get("bytes") != byte_count
            or captured_path is None
            or f"{stat.S_IMODE(captured_path.stat().st_mode):04o}" != mode
        ):
            failures.append(
                "engine TypeScript compiler closure entry does not match its receipt: "
                + relative
            )
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        failures.append("engine TypeScript compiler closure paths are not exact")
    source_digest = hashlib.sha256(
        json.dumps(
            {"files": stable_source_records},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    runtime_digest = hashlib.sha256(
        json.dumps(
            {"files": stable_runtime_records},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if (
        typescript.get("schema_version") != 1
        or typescript.get("capture_relative_path") != TYPESCRIPT_CAPTURED_ROOT_RELATIVE
        or typescript.get("source_manifest_sha256") != TYPESCRIPT_SOURCE_MANIFEST_SHA256
        or source_digest != TYPESCRIPT_SOURCE_MANIFEST_SHA256
        or typescript.get("runtime_manifest_sha256")
        != TYPESCRIPT_RUNTIME_MANIFEST_SHA256
        or runtime_digest != TYPESCRIPT_RUNTIME_MANIFEST_SHA256
        or typescript.get("compiler_closure_sha256")
        != TYPESCRIPT_COMPILER_CLOSURE_SHA256
        or typescript.get("file_count") != TYPESCRIPT_COMPILER_FILE_COUNT
        or typescript.get("bytes") != TYPESCRIPT_COMPILER_BYTES
        or total_bytes != TYPESCRIPT_COMPILER_BYTES
        or typescript.get("semantic_soundness") != "NOT_RUN"
    ):
        failures.append(
            "engine TypeScript compiler closure receipt identity is invalid"
        )
    expected_runtime_paths = {
        PYTHON_CAPTURED_ARCHIVE_RELATIVE,
        *(f"{TYPESCRIPT_CAPTURED_ROOT_RELATIVE}/{relative}" for relative in paths),
    }
    observed_runtime_paths = {
        path
        for path in files_by_repository_path
        if path.startswith("runtime/python/") or path.startswith("runtime/typescript/")
    }
    if observed_runtime_paths != expected_runtime_paths:
        failures.append("engine runtime source manifest inventory is not exact")


def _validate_required_engine_source_bindings(
    *,
    route: Path,
    manifest_relative: object,
    source_manifest: dict[str, Any],
    ref_records: dict[str, tuple[dict[str, Any], Path, str]],
    runtime_provenance: dict[str, Any] | None,
    failures: list[str],
) -> None:
    """Bind the replay-critical Python implementation to canonical captures.

    The engine-source manifest is an inventory, so a producer could otherwise
    remove a source from both that inventory and ``artifact_refs`` while
    keeping the two reduced sets internally consistent.  This check owns the
    non-optional implementation closure: every runtime module imported by the
    proof validator, the uv lockfile, and the frozen route runner/validator.
    """

    if not isinstance(manifest_relative, str):
        failures.append("engine source manifest path is not canonical")
        return
    manifest_path = Path(manifest_relative)
    if (
        manifest_path.parts[:1] != ("certification",)
        or len(manifest_path.parts) != 3
        or manifest_path.parts[1] not in {"formal-artifacts", "strict-artifacts"}
        or manifest_path.name != "engine-source-manifest.json"
        or manifest_path.as_posix() != manifest_relative
    ):
        failures.append("engine source manifest path is not canonical")
        return
    artifact_root = manifest_path.parent.as_posix()

    files = source_manifest.get("files")
    if not isinstance(files, list):
        failures.append("engine source manifest files are invalid")
        return
    entries_by_repository_path: dict[str, list[dict[str, Any]]] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        repository_path = item.get("repository_path")
        if isinstance(repository_path, str):
            entries_by_repository_path.setdefault(repository_path, []).append(item)

    refs_by_path: dict[str, list[tuple[dict[str, Any], Path, str]]] = {}
    for record in ref_records.values():
        relative = record[0].get("path")
        if isinstance(relative, str):
            refs_by_path.setdefault(relative, []).append(record)

    required_entries: dict[str, dict[str, Any]] = {}
    for repository_path in sorted(ENGINE_SOURCE_REQUIRED_ASSETS):
        entries = entries_by_repository_path.get(repository_path, [])
        if len(entries) != 1:
            failures.append(
                "engine source manifest must contain exactly one required asset: "
                + repository_path
            )
            continue
        entry = entries[0]
        required_entries[repository_path] = entry
        if set(entry) != ENGINE_SOURCE_MANIFEST_FILE_KEYS:
            failures.append(
                "engine source manifest required asset fields are not exact: "
                + repository_path
            )
        expected_captured_path = f"{artifact_root}/engine-sources/{repository_path}"
        if entry.get("captured_path") != expected_captured_path:
            failures.append(
                "engine source manifest required asset captured_path is not canonical: "
                + repository_path
            )
        entry_digest = _require_digest(
            failures,
            entry.get("sha256"),
            f"engine source manifest required asset {repository_path}.sha256",
        )
        entry_bytes = entry.get("bytes")
        if not _is_int(entry_bytes, minimum=1):
            failures.append(
                "engine source manifest required asset bytes are invalid: "
                + repository_path
            )

        bindings = refs_by_path.get(expected_captured_path, [])
        if len(bindings) != 1 or bindings[0][0].get("role") != "engine-source":
            failures.append(
                "engine source manifest required asset must have exactly one "
                "engine-source ref: " + repository_path
            )
            continue
        reference, captured, observed_digest = bindings[0]
        canonical_captured = route / expected_captured_path
        path_cursor = route
        has_symlink_component = False
        for component in Path(expected_captured_path).parts:
            path_cursor /= component
            if path_cursor.is_symlink():
                has_symlink_component = True
                break
        if has_symlink_component:
            failures.append(
                "engine source manifest required asset path cannot contain a symlink: "
                + repository_path
            )
        try:
            canonical_resolved = canonical_captured.resolve(strict=True)
        except OSError:
            failures.append(
                "engine source manifest required asset is missing: " + repository_path
            )
            continue
        if captured.resolve() != canonical_resolved:
            failures.append(
                "engine source manifest required asset ref path mismatch: "
                + repository_path
            )
        if entry_digest is not None and (
            entry_digest != reference.get("sha256") or entry_digest != observed_digest
        ):
            failures.append(
                "engine source manifest required asset digest is not cross-bound: "
                + repository_path
            )
        if _is_int(entry_bytes, minimum=1) and (
            entry_bytes != reference.get("bytes")
            or entry_bytes != canonical_resolved.stat().st_size
        ):
            failures.append(
                "engine source manifest required asset bytes are not cross-bound: "
                + repository_path
            )

    if runtime_provenance is None:
        failures.append("engine source runtime provenance is unavailable")
        return
    modules = runtime_provenance.get("engine_modules")
    if not isinstance(modules, dict) or set(modules) != set(ENGINE_RUNTIME_MODULES):
        failures.append("engine source runtime module provenance is not exact")
        return
    layout = _runtime_layout()
    if layout is None:
        failures.append("engine source runtime layout is unavailable")
        return
    source_root, _, _ = layout
    for module_name, module_relative in ENGINE_RUNTIME_MODULES.items():
        repository_path = ENGINE_RUNTIME_MODULE_REPOSITORY_PATHS[module_name]
        entry = required_entries.get(repository_path)
        provenance = modules.get(module_name)
        if entry is None:
            continue
        if not isinstance(provenance, dict) or set(provenance) != {"path", "sha256"}:
            failures.append(
                "engine source runtime module provenance is invalid: " + module_name
            )
            continue
        expected_runtime_path = (source_root / module_relative).resolve(strict=True)
        provenance_path = provenance.get("path")
        try:
            observed_runtime_path = Path(str(provenance_path)).resolve(strict=True)
        except OSError:
            observed_runtime_path = None
        if observed_runtime_path != expected_runtime_path:
            failures.append(
                "engine source runtime module path is not cross-bound: " + module_name
            )
        if provenance.get("sha256") != entry.get("sha256"):
            failures.append(
                "engine source runtime module digest is not cross-bound: " + module_name
            )

    lock_repository_path = f"{ENGINE_RUNTIME_PROJECT_RELATIVE}/uv.lock"
    lock_entry = required_entries.get(lock_repository_path)
    lock_provenance = runtime_provenance.get("route_engine_lock")
    if lock_entry is not None:
        if not isinstance(lock_provenance, dict) or set(lock_provenance) != {
            "path",
            "sha256",
        }:
            failures.append("engine source runtime lock provenance is invalid")
        else:
            expected_lock_path = (source_root.parent / "uv.lock").resolve(strict=True)
            try:
                observed_lock_path = Path(str(lock_provenance.get("path"))).resolve(
                    strict=True
                )
            except OSError:
                observed_lock_path = None
            if observed_lock_path != expected_lock_path:
                failures.append("engine source runtime lock path is not cross-bound")
            if lock_provenance.get("sha256") != lock_entry.get("sha256"):
                failures.append("engine source runtime lock digest is not cross-bound")


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
    if (
        snapshot_bytes != expected_bytes
        or sha256_bytes(snapshot_bytes) != expected_digest
    ):
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
    if not all(
        (source_root / relative).is_file()
        for relative in ENGINE_RUNTIME_MODULES.values()
    ):
        return None
    return (
        source_root.resolve(),
        venv_root.resolve(),
        (executable.parent / "z3").resolve(),
    )


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


def _runtime_provenance(failures: list[str], label: str) -> dict[str, Any] | None:
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
            failures.append(
                f"{label} engine module origin rejected for {module_name}: {exc}"
            )
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
        if (
            cli_version_run.returncode != 0
            or cli_version_run.stdout.strip() != expected_version_line
        ):
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


def _engine_proof_api(failures: list[str], label: str) -> tuple[Any, Any, Any] | None:
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


def _engine_domain_api(failures: list[str], label: str) -> tuple[Any, Any, Any] | None:
    """Load the exact-eight and Node domain guards only after origin binding."""

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.engine import (  # type: ignore[import-not-found]
            _enforce_nodejs_case_domain,
            _enforce_nodejs_semantic_domain,
            _enforce_specialized_case_domain,
            _enforce_specialized_semantic_domain,
        )
        from elmos_polyglot_route.models import SemanticIR  # type: ignore[import-not-found]
    except Exception as exc:
        failures.append(f"{label} cannot load pinned strict-domain API: {exc}")
        return None

    def enforce_semantic_domain(
        ir: Any, source_language: Any, target_language: Any
    ) -> None:
        _enforce_specialized_semantic_domain(ir, source_language, target_language)
        _enforce_nodejs_semantic_domain(ir, source_language, target_language)

    def enforce_case_domain(
        function: Any,
        cases: Any,
        source_language: Any,
        target_language: Any,
    ) -> None:
        _enforce_specialized_case_domain(
            function, cases, source_language, target_language
        )
        _enforce_nodejs_case_domain(function, cases, source_language, target_language)

    return (
        SemanticIR,
        enforce_semantic_domain,
        enforce_case_domain,
    )


def _engine_identifier_api(
    failures: list[str], label: str
) -> tuple[Any, Any, Any, Any, Any, Any, Any, Any] | None:
    """Load the origin-bound identifier plan and alpha-normalization API."""

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.engine import (  # type: ignore[import-not-found]
            _bind_function_spans_from_inventory,
        )
        from elmos_polyglot_route.identifier_hygiene import (  # type: ignore[import-not-found]
            IdentifierPlan,
            alpha_normalize_target,
            identifier_plan_bytes,
            standalone_artifact_unit_namespace,
            target_ir_view,
            validate_identifier_plan,
        )
        from elmos_polyglot_route.models import SemanticIR  # type: ignore[import-not-found]
    except Exception as exc:
        failures.append(f"{label} cannot load pinned identifier API: {exc}")
        return None
    return (
        SemanticIR,
        IdentifierPlan,
        validate_identifier_plan,
        alpha_normalize_target,
        identifier_plan_bytes,
        target_ir_view,
        standalone_artifact_unit_namespace,
        _bind_function_spans_from_inventory,
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
) -> tuple[Any, Any, Any, Any, Any, Any, Any, Any, Any, Any] | None:
    """Load the exact module inventory/emission closure implementation."""

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.emitter import emit  # type: ignore[import-not-found]
        from elmos_polyglot_route.engine import (  # type: ignore[import-not-found]
            _build_whole_file_closure,
            _combine_function_irs,
        )
        from elmos_polyglot_route.identifier_hygiene import (  # type: ignore[import-not-found]
            alpha_normalize_target,
            target_ir_view,
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
        target_ir_view,
        alpha_normalize_target,
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


def _swift_closure_directory_chain(directory: Path) -> tuple[tuple[object, ...], ...]:
    xcode_root = Path(SWIFT_XCODE_ROOT)
    if not directory.is_absolute() or not directory.is_relative_to(xcode_root):
        raise ValueError("path is outside pinned Xcode root")
    cursor = Path("/")
    identities: list[tuple[object, ...]] = []
    for part in directory.parts[1:]:
        cursor = cursor / part
        metadata = cursor.lstat()
        is_applications_root = cursor == Path("/Applications")
        unsafe_mode = (
            stat.S_IMODE(metadata.st_mode) & 0o002
            if is_applications_root
            else stat.S_IMODE(metadata.st_mode) & 0o022
        )
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or unsafe_mode
        ):
            raise ValueError(f"unsafe Xcode directory: {cursor}")
        identities.append(
            (
                str(cursor),
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_uid,
                metadata.st_gid,
                metadata.st_mtime_ns,
            )
        )
    if directory.resolve(strict=True) != directory:
        raise ValueError("Xcode directory chain resolves elsewhere")
    return tuple(identities)


def _stable_read_swift_closure_file(file_path: Path) -> tuple[bytes, os.stat_result]:
    before = file_path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size < 0
        or before.st_size > SWIFT_BUILD_CLOSURE_COMPONENT_MAXIMUM_BYTES
    ):
        raise ValueError("Swift closure component exceeds maximum size")
    descriptor = os.open(
        file_path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or opened_before.st_size < 0
            or opened_before.st_size
            > SWIFT_BUILD_CLOSURE_COMPONENT_MAXIMUM_BYTES
        ):
            raise ValueError("Swift closure component exceeds maximum size")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > SWIFT_BUILD_CLOSURE_COMPONENT_MAXIMUM_BYTES:
                raise ValueError("Swift closure component exceeds maximum size")
            chunks.append(chunk)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = file_path.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    for observed in (opened_before, opened_after, after):
        if identity != (
            observed.st_dev,
            observed.st_ino,
            observed.st_mode,
            observed.st_nlink,
            observed.st_uid,
            observed.st_gid,
            observed.st_size,
            observed.st_mtime_ns,
            observed.st_ctime_ns,
        ):
            raise ValueError("Swift closure component changed while read")
    content = b"".join(chunks)
    if (
        not stat.S_ISREG(after.st_mode)
        or after.st_uid != 0
        or after.st_gid != 0
        or stat.S_IMODE(after.st_mode) & 0o022
        or len(content) != after.st_size
    ):
        raise ValueError("Swift closure component metadata is unsafe")
    return content, after


def _stable_read_exact_file(
    file_path: Path,
    *,
    maximum_bytes: int,
    allowed_uids: frozenset[int],
) -> tuple[bytes, os.stat_result, tuple[object, ...]]:
    before = file_path.lstat()
    descriptor = os.open(
        file_path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened_before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError("file exceeds maximum size")
            chunks.append(chunk)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = file_path.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    for observed in (opened_before, opened_after, after):
        if identity != (
            observed.st_dev,
            observed.st_ino,
            observed.st_mode,
            observed.st_nlink,
            observed.st_uid,
            observed.st_gid,
            observed.st_size,
            observed.st_mtime_ns,
            observed.st_ctime_ns,
        ):
            raise ValueError("file changed while read")
    content = b"".join(chunks)
    if (
        not stat.S_ISREG(after.st_mode)
        or after.st_uid not in allowed_uids
        or stat.S_IMODE(after.st_mode) & 0o022
        or after.st_nlink != 1
        or len(content) != after.st_size
        or file_path.resolve(strict=True) != file_path
    ):
        raise ValueError("file metadata is unsafe")
    return content, after, identity


def _system_directory_chain(directory: Path) -> tuple[tuple[object, ...], ...]:
    if directory != Path("/usr/bin"):
        raise ValueError("system tool directory is not pinned")
    cursor = Path("/")
    identities: list[tuple[object, ...]] = []
    for part in directory.parts[1:]:
        cursor = cursor / part
        metadata = cursor.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise ValueError(f"unsafe system directory: {cursor}")
        identities.append(
            (
                str(cursor),
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_uid,
                metadata.st_gid,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            )
        )
    if directory.resolve(strict=True) != directory:
        raise ValueError("system tool directory resolves elsewhere")
    return tuple(identities)


def _observe_swift_network_system_tool(
    expected: dict[str, Any],
) -> tuple[dict[str, Any], tuple[object, ...]]:
    path = Path(expected["path"])
    chain_before = _system_directory_chain(path.parent)
    content, metadata, identity = _stable_read_exact_file(
        path,
        maximum_bytes=int(expected["bytes"]),
        allowed_uids=frozenset({0}),
    )
    chain_after = _system_directory_chain(path.parent)
    observed = {
        "path": str(path),
        "sha256": sha256_bytes(content),
        "bytes": len(content),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
    }
    expected_file = {
        key: expected[key]
        for key in ("path", "sha256", "bytes", "mode", "uid", "gid", "nlink")
    }
    if chain_before != chain_after or observed != expected_file:
        raise ValueError("network system tool identity differs")
    return observed, (chain_after, identity)


def _verify_swift_network_sandbox_signature(
    *,
    environment: dict[str, str],
    cwd: Path,
) -> None:
    verify = subprocess.run(
        [
            SWIFT_NETWORK_VERIFIER["path"],
            "--verify",
            "--strict",
            SWIFT_NETWORK_SANDBOX["path"],
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    details = subprocess.run(
        [
            SWIFT_NETWORK_VERIFIER["path"],
            "-d",
            "--verbose=4",
            SWIFT_NETWORK_SANDBOX["path"],
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    lines = set((details.stdout + details.stderr).splitlines())
    if (
        verify.returncode != 0
        or details.returncode != 0
        or not {
            "Identifier=com.apple.sandbox-exec",
            "Authority=Apple Root CA",
            "TeamIdentifier=not set",
            f"CandidateCDHashFull sha256={SWIFT_NETWORK_SANDBOX['cdhash_full']}",
        }.issubset(lines)
    ):
        raise ValueError("sandbox-exec code-signature identity differs")


def _observe_swift_git_identity() -> dict[str, str]:
    path = Path(SWIFT_GIT_PATH)
    chain_before = _swift_closure_directory_chain(path.parent)
    content_before, _metadata_before, identity_before = _stable_read_exact_file(
        path,
        maximum_bytes=SWIFT_GIT_BYTES,
        allowed_uids=frozenset({0}),
    )
    version = subprocess.run(
        [str(path), "--version"],
        cwd=path.parent,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={"LANG": "C", "LC_ALL": "C", "PATH": str(path.parent)},
    )
    content_after, _metadata_after, identity_after = _stable_read_exact_file(
        path,
        maximum_bytes=SWIFT_GIT_BYTES,
        allowed_uids=frozenset({0}),
    )
    chain_after = _swift_closure_directory_chain(path.parent)
    if (
        version.returncode != 0
        or version.stdout.strip() != SWIFT_GIT_VERSION
        or version.stderr != ""
        or chain_before != chain_after
        or identity_before != identity_after
        or content_before != content_after
        or len(content_after) != SWIFT_GIT_BYTES
        or sha256_bytes(content_after) != SWIFT_GIT_SHA256
    ):
        raise ValueError("direct Xcode Git identity differs")
    return {
        "path": SWIFT_GIT_PATH,
        "sha256": SWIFT_GIT_SHA256,
        "version": SWIFT_GIT_VERSION,
    }


def _inspect_swift_network_probe_macho(content: bytes) -> dict[str, Any]:
    if len(content) < 32:
        raise ValueError("probe Mach-O header is truncated")
    (
        magic,
        cpu_type,
        _cpu_subtype,
        file_type,
        command_count,
        command_bytes,
        _flags,
        _reserved,
    ) = struct.unpack_from("<IiiIIIII", content, 0)
    if magic != 0xFEEDFACF or cpu_type != 0x0100000C or file_type != 2:
        raise ValueError("probe Mach-O identity differs")
    command_end = 32 + command_bytes
    if command_end > len(content):
        raise ValueError("probe Mach-O commands are truncated")
    offset = 32
    uuids: list[bytes] = []
    linked_libraries: list[str] = []
    signature_commands: list[tuple[int, int]] = []
    dylib_commands = frozenset(
        {0xC, 0x18 | 0x80000000, 0x1F | 0x80000000, 0x23 | 0x80000000, 0x20}
    )
    for _index in range(command_count):
        if offset + 8 > command_end:
            raise ValueError("probe Mach-O command header is truncated")
        command, size = struct.unpack_from("<II", content, offset)
        if size < 8 or size % 8 != 0 or offset + size > command_end:
            raise ValueError("probe Mach-O command size is invalid")
        if command == 0x1B:
            if size != 24:
                raise ValueError("probe LC_UUID is invalid")
            uuids.append(content[offset + 8 : offset + 24])
        elif command in dylib_commands:
            if size < 24:
                raise ValueError("probe dylib command is invalid")
            name_offset = struct.unpack_from("<I", content, offset + 8)[0]
            if name_offset < 24 or name_offset >= size:
                raise ValueError("probe dylib name offset is invalid")
            name = content[offset + name_offset : offset + size].split(b"\0", 1)[0]
            linked_libraries.append(name.decode("utf-8"))
        elif command == 0x1D:
            if size != 16:
                raise ValueError("probe code-signature command is invalid")
            signature_commands.append(struct.unpack_from("<II", content, offset + 8))
        offset += size
    if offset != command_end or len(uuids) != 1 or len(signature_commands) != 1:
        raise ValueError("probe Mach-O command inventory is invalid")
    signature_offset, signature_size = signature_commands[0]
    if signature_size == 0 or signature_offset + signature_size != len(content):
        raise ValueError("probe code-signature range is invalid")
    uuid_hex = uuids[0].hex().upper()
    uuid_value = (
        f"{uuid_hex[:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
        f"{uuid_hex[16:20]}-{uuid_hex[20:]}"
    )
    return {
        "architecture": "arm64",
        "file_type": "MH_EXECUTE",
        "uuid": uuid_value,
        "cdhash_full": SWIFT_NETWORK_PROBE_CDHASH_FULL,
        "linked_libraries": linked_libraries,
    }


def _verify_swift_network_probe_signature(
    binary: Path,
    *,
    environment: dict[str, str],
    cwd: Path,
) -> None:
    verify = subprocess.run(
        [SWIFT_NETWORK_VERIFIER["path"], "--verify", "--strict", str(binary)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    if verify.returncode != 0:
        raise ValueError("probe code signature did not verify")
    details = subprocess.run(
        [SWIFT_NETWORK_VERIFIER["path"], "-d", "--verbose=4", str(binary)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    lines = set((details.stdout + details.stderr).splitlines())
    if details.returncode != 0 or not {
        f"Identifier={SWIFT_NETWORK_PROBE_BINARY_NAME}",
        "Signature=adhoc",
        "TeamIdentifier=not set",
        f"CandidateCDHashFull sha256={SWIFT_NETWORK_PROBE_CDHASH_FULL}",
    }.issubset(lines):
        raise ValueError("probe code-signature identity differs")


def _probe_validation_environment(root: Path) -> dict[str, str]:
    home = root / "home"
    temporary = root / "tmp"
    home.mkdir(mode=0o700)
    temporary.mkdir(mode=0o700)
    return {
        "HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.pathsep.join(
            (
                str(Path(SWIFT_NETWORK_PROBE_COMPILER["path"]).parent),
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
            )
        ),
        "SOURCE_DATE_EPOCH": "0",
        "SWIFT_DETERMINISTIC_HASHING": "1",
        "TMPDIR": str(temporary),
        "ZERO_AR_DATE": "1",
        "TZ": "UTC",
        "NO_COLOR": "1",
        "CLICOLOR": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "TEST_TELEMETRY_DIR": str(home / ".elmos-go-telemetry"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


def _observe_swift_network_probe_toolchain() -> tuple[object, ...]:
    compiler = Path(SWIFT_NETWORK_PROBE_COMPILER["path"])
    chain_before = _swift_closure_directory_chain(compiler.parent)
    content, metadata, identity = _stable_read_exact_file(
        compiler,
        maximum_bytes=int(SWIFT_NETWORK_PROBE_COMPILER["bytes"]),
        allowed_uids=frozenset({0}),
    )
    chain_after = _swift_closure_directory_chain(compiler.parent)
    observed_compiler = {
        **SWIFT_NETWORK_PROBE_COMPILER,
        "sha256": sha256_bytes(content),
        "bytes": len(content),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
    }
    sdk = Path(SWIFT_SDK_ROOT)
    sdk_metadata = sdk.lstat()
    sdk_target = os.readlink(sdk)
    sdk_resolved = sdk.resolve(strict=True)
    if (
        chain_before != chain_after
        or observed_compiler != SWIFT_NETWORK_PROBE_COMPILER
        or stat.S_ISLNK(compiler.lstat().st_mode)
        or compiler.resolve(strict=True)
        != Path(SWIFT_NETWORK_PROBE_COMPILER["resolved_path"])
        or SWIFT_NETWORK_PROBE_COMPILER["link_target"] is not None
        or not stat.S_ISLNK(sdk_metadata.st_mode)
        or sdk_metadata.st_uid != 0
        or sdk_metadata.st_gid != 0
        or sdk_target != "MacOSX.sdk"
        or sdk_resolved != Path(SWIFT_SDK_RESOLVED_ROOT)
    ):
        raise ValueError("probe compiler or SDK identity differs")
    return (
        chain_after,
        identity,
        _swift_closure_directory_chain(sdk_resolved),
        sdk_metadata.st_dev,
        sdk_metadata.st_ino,
        sdk_metadata.st_mode,
        sdk_metadata.st_uid,
        sdk_metadata.st_gid,
        sdk_metadata.st_mtime_ns,
        sdk_target,
    )


def _independently_rebuild_swift_network_probe() -> None:
    with tempfile.TemporaryDirectory(
        prefix="elmos-swift-network-probe-validator-"
    ) as temporary:
        root = Path(temporary).resolve(strict=True)
        root.chmod(0o700)
        environment = _probe_validation_environment(root)
        sandbox_before = _observe_swift_network_system_tool(SWIFT_NETWORK_SANDBOX)
        verifier_before = _observe_swift_network_system_tool(SWIFT_NETWORK_VERIFIER)
        toolchain_before = _observe_swift_network_probe_toolchain()
        _verify_swift_network_sandbox_signature(environment=environment, cwd=root)
        output = root / SWIFT_NETWORK_PROBE_BINARY_NAME
        command = [
            SWIFT_NETWORK_SANDBOX["path"],
            "-p",
            SWIFT_NETWORK_POLICY_TEXT,
            SWIFT_NETWORK_PROBE_COMPILER["path"],
            "-x",
            "c",
            "-std=c17",
            "-target",
            "arm64-apple-macosx26.0",
            "-Os",
            "-fno-ident",
            "-isysroot",
            SWIFT_SDK_ROOT,
            "-Wl,-dead_strip",
            "-o",
            str(output),
            "-",
        ]
        build = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            input=SWIFT_NETWORK_PROBE_SOURCE,
            timeout=120,
            env=environment,
        )
        if build.returncode != 0:
            raise ValueError(f"independent probe compile failed: {build.stderr[-500:]}")
        content, metadata, _identity = _stable_read_exact_file(
            output,
            maximum_bytes=SWIFT_NETWORK_PROBE_BINARY_BYTES,
            allowed_uids=frozenset({os.getuid()}),
        )
        if (
            sha256_bytes(content) != SWIFT_NETWORK_PROBE_BINARY_SHA256
            or len(content) != SWIFT_NETWORK_PROBE_BINARY_BYTES
            or f"{stat.S_IMODE(metadata.st_mode):04o}" != "0755"
            or _inspect_swift_network_probe_macho(content)
            != {
                "architecture": "arm64",
                "file_type": "MH_EXECUTE",
                "uuid": SWIFT_NETWORK_PROBE_UUID,
                "cdhash_full": SWIFT_NETWORK_PROBE_CDHASH_FULL,
                "linked_libraries": SWIFT_NETWORK_PROBE_LINKED_LIBRARIES,
            }
        ):
            raise ValueError("independently rebuilt probe identity differs")
        _verify_swift_network_probe_signature(
            output,
            environment=environment,
            cwd=root,
        )
        execution = subprocess.run(
            [
                SWIFT_NETWORK_SANDBOX["path"],
                "-p",
                SWIFT_NETWORK_POLICY_TEXT,
                str(output),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
        if (
            execution.returncode != 0
            or execution.stdout != "NETWORK_DENIED:1\n"
            or execution.stderr != ""
        ):
            raise ValueError("independently rebuilt probe did not observe exact EPERM")
        sandbox_after = _observe_swift_network_system_tool(SWIFT_NETWORK_SANDBOX)
        verifier_after = _observe_swift_network_system_tool(SWIFT_NETWORK_VERIFIER)
        toolchain_after = _observe_swift_network_probe_toolchain()
        _verify_swift_network_sandbox_signature(environment=environment, cwd=root)
        if (
            sandbox_before != sandbox_after
            or verifier_before != verifier_after
            or toolchain_before != toolchain_after
        ):
            raise ValueError("probe build/execution closure changed during replay")


def _checked_swift_tree_byte_total(
    current: int,
    additional: int,
    *,
    role: str,
) -> int:
    if (
        type(current) is not int
        or type(additional) is not int
        or current < 0
        or additional < 0
        or additional > SWIFT_BUILD_CLOSURE_TREE_MAXIMUM_BYTES - current
    ):
        raise ValueError(f"tree exceeds aggregate byte bound: {role}")
    return current + additional


def _observe_swift_build_closure() -> dict[str, Any]:
    sdk_root = Path(SWIFT_SDK_ROOT)
    sdk_link = sdk_root.lstat()
    if (
        not stat.S_ISLNK(sdk_link.st_mode)
        or sdk_link.st_uid != 0
        or sdk_link.st_gid != 0
        or os.readlink(sdk_root) != "MacOSX.sdk"
        or sdk_root.resolve(strict=True) != Path(SWIFT_SDK_RESOLVED_ROOT)
    ):
        raise ValueError("pinned Swift SDK root link is invalid")

    content_cache: dict[Path, tuple[bytes, os.stat_result]] = {}
    components: list[dict[str, Any]] = []
    for (
        role,
        path_text,
        resolved_text,
        link_target,
        *_expected,
    ) in SWIFT_BUILD_CLOSURE_COMPONENT_SPECS:
        lexical = Path(path_text)
        lexical_metadata = lexical.lstat()
        if link_target is None:
            if stat.S_ISLNK(lexical_metadata.st_mode):
                raise ValueError(f"unexpected component symlink: {role}")
        elif (
            not stat.S_ISLNK(lexical_metadata.st_mode)
            or lexical_metadata.st_uid != 0
            or lexical_metadata.st_gid != 0
            or os.readlink(lexical) != link_target
            or Path(link_target).is_absolute()
            or ".." in Path(link_target).parts
        ):
            raise ValueError(f"component symlink differs: {role}")
        resolved = lexical.resolve(strict=True)
        if resolved != Path(resolved_text):
            raise ValueError(f"component resolution differs: {role}")
        _swift_closure_directory_chain(resolved.parent)
        if resolved not in content_cache:
            content_cache[resolved] = _stable_read_swift_closure_file(resolved)
        content, metadata = content_cache[resolved]
        components.append(
            {
                "role": role,
                "path": str(lexical),
                "resolved_path": str(resolved),
                "link_target": link_target,
                "sha256": sha256_bytes(content),
                "bytes": len(content),
                "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                "uid": metadata.st_uid,
                "gid": metadata.st_gid,
                "nlink": metadata.st_nlink,
            }
        )

    trees: list[dict[str, Any]] = []
    for role, root_text, resolved_text, *_expected in SWIFT_BUILD_CLOSURE_TREE_SPECS:
        root = Path(root_text)
        resolved = root.resolve(strict=True)
        if resolved != Path(resolved_text):
            raise ValueError(f"tree resolution differs: {role}")
        root_identity = _swift_closure_directory_chain(resolved)

        def discover(tree_root: Path, tree_role: str) -> list[Path]:
            files: list[Path] = []
            declared_total = 0
            candidates = sorted(
                tree_root.rglob("*"),
                key=lambda item: item.relative_to(tree_root).as_posix(),
            )
            if len(candidates) > 10_000:
                raise ValueError(f"tree is unexpectedly large: {tree_role}")
            for item in candidates:
                metadata = item.lstat()
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or metadata.st_uid != 0
                    or metadata.st_gid != 0
                    or stat.S_IMODE(metadata.st_mode) & 0o022
                    or not (
                        stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)
                    )
                ):
                    raise ValueError(f"tree entry is unsafe: {tree_role}")
                if stat.S_ISREG(metadata.st_mode):
                    declared_total = _checked_swift_tree_byte_total(
                        declared_total,
                        metadata.st_size,
                        role=tree_role,
                    )
                    files.append(item)
            return files

        paths = discover(resolved, role)
        file_records: list[dict[str, Any]] = []
        total = 0
        for item in paths:
            content, _metadata = _stable_read_swift_closure_file(item)
            total = _checked_swift_tree_byte_total(
                total,
                len(content),
                role=role,
            )
            file_records.append(
                {
                    "path": item.relative_to(resolved).as_posix(),
                    "sha256": sha256_bytes(content),
                    "bytes": len(content),
                }
            )
        if [
            item.relative_to(resolved).as_posix() for item in discover(resolved, role)
        ] != [item["path"] for item in file_records] or _swift_closure_directory_chain(
            resolved
        ) != root_identity:
            raise ValueError(f"tree changed while read: {role}")
        trees.append(
            {
                "role": role,
                "root": str(root),
                "sha256": _receipt_payload_sha256({"files": file_records}),
                "file_count": len(file_records),
                "bytes": total,
            }
        )
    return {
        "schema": SWIFT_BUILD_CLOSURE_SCHEMA,
        "scope": SWIFT_BUILD_CLOSURE_SCOPE,
        "compiler_runtime_soundness": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "components": components,
        "trees": trees,
    }


def _canonical_swift_build_closure_identity(closure: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": closure.get("schema"),
        "scope": closure.get("scope"),
        "compiler_runtime_soundness": closure.get("compiler_runtime_soundness"),
        "certification": closure.get("certification"),
        "components": [
            {
                key: item.get(key)
                for key in ("role", "link_target", "sha256", "bytes", "mode", "nlink")
            }
            for item in closure.get("components", [])
            if isinstance(item, dict)
        ],
        "trees": [
            {key: item.get(key) for key in ("role", "sha256", "file_count", "bytes")}
            for item in closure.get("trees", [])
            if isinstance(item, dict)
        ],
    }


def _canonical_swift_toolchain_identity(
    toolchain: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild the portable Swift toolchain identity from exact raw fields."""

    profile = toolchain.get("profile")
    profile_items = profile if isinstance(profile, list) else []
    return {
        "swiftc_sha256": toolchain.get("swiftc_sha256"),
        "swift_driver_sha256": toolchain.get("swift_driver_sha256"),
        "version": toolchain.get("version"),
        "profile": [
            item
            for item in profile_items
            if isinstance(item, str) and not item.startswith("sdk-path=")
        ],
        "build_closure": _canonical_swift_build_closure_identity(
            toolchain.get("build_closure")
            if isinstance(toolchain.get("build_closure"), dict)
            else {}
        ),
    }


def _rebuild_portable_swift_receipt_identity(
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Independently construct the host-path-free canonical receipt.

    This deliberately does not read ``receipt.canonical_identity`` and only
    selects exact portable fields from the raw, independently validated
    receipt.  Scratch roots, executable paths, device/inode and ownership are
    therefore incapable of entering persisted stable comparisons.
    """

    dependency = receipt["dependency"]
    mirror = dependency["mirror"]
    cache = mirror["cache"]
    network = receipt["network_isolation"]
    network_probe = network["probe"]
    probe_compiler = network_probe["build"]["compiler"]
    binary = receipt["binary"]
    seal = receipt["execution_seal"]
    return {
        "schema_version": receipt["schema_version"],
        "kind": receipt["kind"],
        "source_inputs": receipt["source_inputs"],
        "dependency": {
            "identity": dependency["identity"],
            "version": dependency["version"],
            "revision": dependency["revision"],
            "sha256": dependency["sha256"],
            "file_count": dependency["file_count"],
            "bytes": dependency["bytes"],
            "mirror": {
                "seed": mirror["seed"],
                "identity": mirror["identity"],
                "version": mirror["version"],
                "revision": mirror["revision"],
                "sha256": mirror["sha256"],
                "file_count": mirror["file_count"],
                "bytes": mirror["bytes"],
                "git": {
                    "sha256": mirror["git"]["sha256"],
                    "version": mirror["git"]["version"],
                },
                "cache": {
                    key: cache[key]
                    for key in (
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
                    )
                },
            },
        },
        "toolchain": _canonical_swift_toolchain_identity(receipt["toolchain"]),
        "build": receipt["build"],
        "network_isolation": {
            "status": network["status"],
            "scope": network["scope"],
            "sandbox": {
                key: network["sandbox"][key]
                for key in ("sha256", "bytes", "mode", "nlink", "cdhash_full")
            },
            "verifier": {
                key: network["verifier"][key]
                for key in ("sha256", "bytes", "mode", "nlink")
            },
            "policy": network["policy"],
            "probe": {
                "result": network_probe["result"],
                "source": network_probe["source"],
                "build": {
                    "environment_policy": network_probe["build"]["environment_policy"],
                    "argv": network_probe["build"]["argv"],
                    "environment": network_probe["build"]["environment"],
                    "compiler": {
                        key: probe_compiler[key]
                        for key in (
                            "role",
                            "link_target",
                            "sha256",
                            "bytes",
                            "mode",
                            "nlink",
                        )
                    },
                },
                "binary": {
                    key: network_probe["binary"][key]
                    for key in ("name", "sha256", "bytes", "mode", "nlink")
                },
                "execution_seal": {
                    "policy": network_probe["execution_seal"]["policy"],
                    "mode": network_probe["execution_seal"]["mode"],
                    "binary": {
                        key: network_probe["execution_seal"]["binary"][key]
                        for key in ("name", "sha256", "bytes", "mode", "nlink")
                    },
                },
                "mach_o": {
                    **{
                        key: network_probe["mach_o"][key]
                        for key in (
                            "architecture",
                            "file_type",
                            "uuid",
                            "cdhash_full",
                        )
                    },
                    "linked_libraries": ["system-libSystem"],
                },
            },
        },
        "binary": {
            key: binary[key] for key in ("name", "sha256", "bytes", "mode", "nlink")
        },
        "execution_seal": {
            "policy": seal["policy"],
            "mode": seal["mode"],
            "binary": {
                key: seal["binary"][key]
                for key in ("name", "sha256", "bytes", "mode", "nlink")
            },
        },
    }


def _swift_receipt_stable_projection(receipt: dict[str, Any]) -> dict[str, Any]:
    """Return an independently rebuilt content-addressed stable identity."""

    canonical = _rebuild_portable_swift_receipt_identity(receipt)
    return {
        "sha256": _receipt_payload_sha256(canonical),
        "receipt": canonical,
    }


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
        projected["analyzer_build_receipt"] = _swift_receipt_stable_projection(receipt)
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
    starting_failure_count = len(failures)
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
        expected_paths = [
            path.relative_to(package).as_posix() for path in expected_sources
        ]
        if observed_paths != expected_paths:
            failures.append(
                f"{label}.source_inputs file set differs from locked engine sources"
            )
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
                failures.append(
                    f"{label}.source_inputs locked source invalid: {relative}: {exc}"
                )
                continue
            if not isinstance(record, dict) or (
                record.get("sha256") != sha256_bytes(content)
                or record.get("bytes") != len(content)
            ):
                failures.append(
                    f"{label}.source_inputs source binding mismatch: {relative}"
                )

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
    if {
        field: dependency.get(field) for field in ("identity", "version", "revision")
    } != {
        "identity": SWIFT_DEPENDENCY_IDENTITY,
        "version": SWIFT_DEPENDENCY_VERSION,
        "revision": SWIFT_DEPENDENCY_REVISION,
    }:
        failures.append(f"{label}.dependency identity is invalid")
    _require_digest(failures, dependency.get("sha256"), f"{label}.dependency.sha256")
    if dependency.get("sha256") != SWIFT_DEPENDENCY_SHA256:
        failures.append(f"{label}.dependency.sha256 is not the pinned tree")
    for field in ("file_count", "bytes"):
        if not _is_int(dependency.get(field), minimum=1):
            failures.append(f"{label}.dependency.{field} is invalid")
    if dependency.get("file_count") != SWIFT_DEPENDENCY_FILE_COUNT:
        failures.append(f"{label}.dependency.file_count is not the pinned tree")
    if dependency.get("bytes") != SWIFT_DEPENDENCY_BYTES:
        failures.append(f"{label}.dependency.bytes is not the pinned tree")

    mirror = dependency.get("mirror")
    if not isinstance(mirror, dict) or set(mirror) != SWIFT_ANALYZER_MIRROR_KEYS:
        failures.append(f"{label}.dependency.mirror keys are not exact")
        mirror = {}
    if mirror.get("seed") not in SWIFT_ANALYZER_MIRROR_SEEDS:
        failures.append(f"{label}.dependency.mirror.seed is invalid")
    if {field: mirror.get(field) for field in ("identity", "version", "revision")} != {
        "identity": SWIFT_DEPENDENCY_IDENTITY,
        "version": SWIFT_DEPENDENCY_VERSION,
        "revision": SWIFT_DEPENDENCY_REVISION,
    }:
        failures.append(f"{label}.dependency.mirror identity is invalid")
    for field in ("sha256", "file_count", "bytes"):
        if mirror.get(field) != dependency.get(field):
            failures.append(
                f"{label}.dependency.mirror.{field} differs from dependency tree"
            )

    cache = mirror.get("cache")
    if not isinstance(cache, dict) or set(cache) != SWIFT_DEPENDENCY_CACHE_KEYS:
        failures.append(f"{label}.dependency.mirror.cache keys are not exact")
        cache = {}
    if cache.get("cache_key") != SWIFT_DEPENDENCY_CACHE_KEY:
        failures.append(f"{label}.dependency.mirror.cache.cache_key is invalid")
    if cache.get("cache_schema") != SWIFT_DEPENDENCY_CACHE_SCHEMA:
        failures.append(f"{label}.dependency.mirror.cache.cache_schema is invalid")
    if cache.get("object_store_policy") != SWIFT_DEPENDENCY_OBJECT_STORE_POLICY:
        failures.append(
            f"{label}.dependency.mirror.cache.object_store_policy is invalid"
        )
    if cache.get("seed") not in SWIFT_ANALYZER_MIRROR_SEEDS:
        failures.append(f"{label}.dependency.mirror.cache.seed is invalid")
    if {field: cache.get(field) for field in ("identity", "version", "revision")} != {
        "identity": SWIFT_DEPENDENCY_IDENTITY,
        "version": SWIFT_DEPENDENCY_VERSION,
        "revision": SWIFT_DEPENDENCY_REVISION,
    }:
        failures.append(f"{label}.dependency.mirror.cache identity is invalid")
    for field in ("sha256", "file_count", "bytes"):
        if cache.get(field) != dependency.get(field):
            failures.append(
                f"{label}.dependency.mirror.cache.{field} differs from dependency tree"
            )

    git = mirror.get("git")
    if not isinstance(git, dict) or set(git) != {"path", "sha256", "version"}:
        failures.append(f"{label}.dependency.mirror.git keys are not exact")
        git = {}
    if git != {
        "path": SWIFT_GIT_PATH,
        "sha256": SWIFT_GIT_SHA256,
        "version": SWIFT_GIT_VERSION,
    }:
        failures.append(f"{label}.dependency.mirror.git identity is invalid")
    _require_digest(
        failures, git.get("sha256"), f"{label}.dependency.mirror.git.sha256"
    )
    try:
        if _observe_swift_git_identity() != git:
            raise ValueError("direct Xcode Git receipt differs")
    except (OSError, ValueError) as exc:
        failures.append(f"{label}.dependency.mirror.git provenance invalid: {exc}")

    toolchain = receipt.get("toolchain")
    if not isinstance(toolchain, dict) or set(toolchain) != set(
        SWIFT_ANALYZER_TOOLCHAIN
    ):
        failures.append(f"{label}.toolchain keys are not exact")
        toolchain = {}
    if toolchain != SWIFT_ANALYZER_TOOLCHAIN:
        failures.append(f"{label}.toolchain exact identity is invalid")
    build_closure = toolchain.get("build_closure")
    if not isinstance(build_closure, dict) or set(build_closure) != {
        "schema",
        "scope",
        "compiler_runtime_soundness",
        "certification",
        "components",
        "trees",
    }:
        failures.append(f"{label}.toolchain.build_closure keys are not exact")
    try:
        observed_build_closure = _observe_swift_build_closure()
    except (OSError, ValueError) as exc:
        failures.append(
            f"{label}.toolchain.build_closure live provenance invalid: {exc}"
        )
    else:
        if observed_build_closure != SWIFT_ANALYZER_BUILD_CLOSURE:
            failures.append(f"{label}.toolchain.build_closure pinned identity differs")
        if build_closure != observed_build_closure:
            failures.append(f"{label}.toolchain.build_closure receipt mismatch")
    for path_field, digest_field in (
        ("swiftc", "swiftc_sha256"),
        ("swift_driver", "swift_driver_sha256"),
    ):
        _require_digest(
            failures,
            toolchain.get(digest_field),
            f"{label}.toolchain.{digest_field}",
        )
        tool_path = Path(str(toolchain.get(path_field, "")))
        try:
            link_metadata = tool_path.lstat()
            resolved_tool = tool_path.resolve(strict=True)
            metadata = resolved_tool.lstat()
            if (
                not tool_path.is_absolute()
                or not stat.S_ISREG(metadata.st_mode)
                or resolved_tool.parent != tool_path.parent
                or resolved_tool.name != "swift-frontend"
                or not stat.S_ISLNK(link_metadata.st_mode)
                or link_metadata.st_uid != 0
                or os.readlink(tool_path) != "swift-frontend"
                or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) & 0o022
                or sha256_file(tool_path) != toolchain.get(digest_field)
            ):
                raise ValueError(f"{path_field} identity differs")
        except (OSError, ValueError) as exc:
            failures.append(f"{label}.toolchain.{path_field} provenance invalid: {exc}")

    build = receipt.get("build")
    if not isinstance(build, dict) or set(build) != set(SWIFT_ANALYZER_BUILD):
        failures.append(f"{label}.build keys are not exact")
        build = {}
    if build != SWIFT_ANALYZER_BUILD:
        failures.append(f"{label}.build policy is invalid")

    network = receipt.get("network_isolation")
    if not isinstance(network, dict) or set(network) != {
        "status",
        "scope",
        "sandbox",
        "verifier",
        "policy",
        "probe",
    }:
        failures.append(f"{label}.network_isolation keys are not exact")
        network = {}
    sandbox = network.get("sandbox")
    verifier = network.get("verifier")
    policy = network.get("policy")
    probe = network.get("probe")
    if not isinstance(probe, dict) or set(probe) != SWIFT_NETWORK_PROBE_KEYS:
        failures.append(f"{label}.network_isolation.probe keys are not exact")
        probe = {}
    expected_policy = {
        "text": SWIFT_NETWORK_POLICY_TEXT,
        "sha256": SWIFT_NETWORK_POLICY_SHA256,
        "bytes": len(SWIFT_NETWORK_POLICY_TEXT.encode("utf-8")),
    }
    if (
        network.get("status") != "PASSED"
        or network.get("scope") != "swift-build-process-tree"
        or sandbox != SWIFT_NETWORK_SANDBOX
        or verifier != SWIFT_NETWORK_VERIFIER
        or policy != expected_policy
    ):
        failures.append(f"{label}.network_isolation policy/provenance is invalid")
    source = probe.get("source")
    expected_source = {
        "text": SWIFT_NETWORK_PROBE_SOURCE,
        "sha256": SWIFT_NETWORK_PROBE_SOURCE_SHA256,
        "bytes": SWIFT_NETWORK_PROBE_SOURCE_BYTES,
    }
    if (
        source != expected_source
        or (
            sha256_bytes(SWIFT_NETWORK_PROBE_SOURCE.encode("utf-8"))
            != SWIFT_NETWORK_PROBE_SOURCE_SHA256
        )
        or len(SWIFT_NETWORK_PROBE_SOURCE.encode("utf-8"))
        != SWIFT_NETWORK_PROBE_SOURCE_BYTES
    ):
        failures.append(f"{label}.network_isolation.probe.source is invalid")
    probe_build = probe.get("build")
    expected_probe_build = {
        "environment_policy": "sanitized-swift-build-deterministic-v1",
        "argv": SWIFT_NETWORK_PROBE_BUILD_ARGV,
        "environment": SWIFT_NETWORK_PROBE_BUILD_ENVIRONMENT,
        "compiler": SWIFT_NETWORK_PROBE_COMPILER,
    }
    if (
        not isinstance(probe_build, dict)
        or set(probe_build) != {"environment_policy", "argv", "environment", "compiler"}
        or probe_build != expected_probe_build
    ):
        failures.append(f"{label}.network_isolation.probe.build is invalid")
    probe_binary = probe.get("binary")
    if (
        not isinstance(probe_binary, dict)
        or set(probe_binary) != SWIFT_ANALYZER_BINARY_KEYS
    ):
        failures.append(f"{label}.network_isolation.probe.binary keys are not exact")
        probe_binary = {}
    probe_binary_path = Path(str(probe_binary.get("path", "")))
    if (
        probe.get("result") != "NETWORK_DENIED:1"
        or probe_binary.get("name") != SWIFT_NETWORK_PROBE_BINARY_NAME
        or probe_binary.get("sha256") != SWIFT_NETWORK_PROBE_BINARY_SHA256
        or probe_binary.get("bytes") != SWIFT_NETWORK_PROBE_BINARY_BYTES
        or probe_binary.get("mode") != "0500"
        or probe_binary.get("uid") != os.getuid()
        or not _is_int(probe_binary.get("gid"), minimum=0)
        or probe_binary.get("nlink") != 1
        or not _is_int(probe_binary.get("device"), minimum=1)
        or not _is_int(probe_binary.get("inode"), minimum=1)
        or not probe_binary_path.is_absolute()
        or probe_binary_path.name != SWIFT_NETWORK_PROBE_BINARY_NAME
        or probe_binary_path.parent.name != "network-probe-execution"
        or not probe_binary_path.parent.parent.name.startswith("elmos-swift-analyzer-")
        or ".." in probe_binary_path.parts
    ):
        failures.append(f"{label}.network_isolation.probe.binary identity is invalid")
    probe_seal = probe.get("execution_seal")
    if (
        not isinstance(probe_seal, dict)
        or set(probe_seal) != SWIFT_ANALYZER_EXECUTION_SEAL_KEYS
    ):
        failures.append(
            f"{label}.network_isolation.probe.execution_seal keys are not exact"
        )
        probe_seal = {}
    probe_seal_root = Path(str(probe_seal.get("root", "")))
    if (
        probe_seal.get("policy") != "private-nonwritable-execution-root-v1"
        or probe_seal.get("mode") != "0500"
        or probe_seal.get("uid") != probe_binary.get("uid")
        or probe_seal.get("gid") != probe_binary.get("gid")
        or probe_seal.get("device") != probe_binary.get("device")
        or not _is_int(probe_seal.get("inode"), minimum=1)
        or probe_seal.get("binary") != probe_binary
        or probe_seal_root != probe_binary_path.parent
        or not probe_seal_root.is_absolute()
        or ".." in probe_seal_root.parts
    ):
        failures.append(f"{label}.network_isolation.probe.execution_seal is invalid")
    expected_mach_o = {
        "architecture": "arm64",
        "file_type": "MH_EXECUTE",
        "uuid": SWIFT_NETWORK_PROBE_UUID,
        "cdhash_full": SWIFT_NETWORK_PROBE_CDHASH_FULL,
        "linked_libraries": SWIFT_NETWORK_PROBE_LINKED_LIBRARIES,
    }
    mach_o = probe.get("mach_o")
    if (
        not isinstance(mach_o, dict)
        or set(mach_o) != set(expected_mach_o)
        or mach_o != expected_mach_o
    ):
        failures.append(f"{label}.network_isolation.probe.mach_o is invalid")

    validation_environment = {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin"}
    try:
        sandbox_observed = _observe_swift_network_system_tool(SWIFT_NETWORK_SANDBOX)[0]
        verifier_observed = _observe_swift_network_system_tool(SWIFT_NETWORK_VERIFIER)[
            0
        ]
        _verify_swift_network_sandbox_signature(
            environment=validation_environment,
            cwd=Path.cwd(),
        )
        if (
            sandbox_observed
            != {key: SWIFT_NETWORK_SANDBOX[key] for key in sandbox_observed}
            or verifier_observed != SWIFT_NETWORK_VERIFIER
        ):
            raise ValueError("system tool receipt differs")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        failures.append(
            f"{label}.network_isolation live system provenance invalid: {exc}"
        )

    if live_binary is not None:
        try:
            analyzer_root = live_binary.resolve(strict=True).parent
            if probe_binary_path.parent.parent != analyzer_root:
                raise ValueError("probe is outside the fresh analyzer execution root")
            sandbox_before = _observe_swift_network_system_tool(SWIFT_NETWORK_SANDBOX)
            verifier_before = _observe_swift_network_system_tool(SWIFT_NETWORK_VERIFIER)
            content_before, metadata_before, identity_before = _stable_read_exact_file(
                probe_binary_path,
                maximum_bytes=SWIFT_NETWORK_PROBE_BINARY_BYTES,
                allowed_uids=frozenset({os.getuid()}),
            )
            observed_binary = {
                "name": SWIFT_NETWORK_PROBE_BINARY_NAME,
                "path": str(probe_binary_path),
                "sha256": sha256_bytes(content_before),
                "bytes": len(content_before),
                "mode": f"{stat.S_IMODE(metadata_before.st_mode):04o}",
                "uid": metadata_before.st_uid,
                "gid": metadata_before.st_gid,
                "nlink": metadata_before.st_nlink,
                "device": metadata_before.st_dev,
                "inode": metadata_before.st_ino,
            }
            seal_metadata = probe_seal_root.lstat()
            observed_seal_root = {
                "policy": "private-nonwritable-execution-root-v1",
                "root": str(probe_seal_root),
                "mode": f"{stat.S_IMODE(seal_metadata.st_mode):04o}",
                "uid": seal_metadata.st_uid,
                "gid": seal_metadata.st_gid,
                "device": seal_metadata.st_dev,
                "inode": seal_metadata.st_ino,
            }
            if (
                observed_binary != probe_binary
                or observed_seal_root
                != {key: probe_seal[key] for key in observed_seal_root}
                or _inspect_swift_network_probe_macho(content_before) != expected_mach_o
            ):
                raise ValueError("fresh probe receipt differs from live sealed bytes")
            _verify_swift_network_probe_signature(
                probe_binary_path,
                environment=validation_environment,
                cwd=analyzer_root,
            )
            execution = subprocess.run(
                [
                    SWIFT_NETWORK_SANDBOX["path"],
                    "-p",
                    SWIFT_NETWORK_POLICY_TEXT,
                    str(probe_binary_path),
                ],
                cwd=analyzer_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=validation_environment,
            )
            content_after, metadata_after, identity_after = _stable_read_exact_file(
                probe_binary_path,
                maximum_bytes=SWIFT_NETWORK_PROBE_BINARY_BYTES,
                allowed_uids=frozenset({os.getuid()}),
            )
            sandbox_after = _observe_swift_network_system_tool(SWIFT_NETWORK_SANDBOX)
            verifier_after = _observe_swift_network_system_tool(SWIFT_NETWORK_VERIFIER)
            if (
                execution.returncode != 0
                or execution.stdout != "NETWORK_DENIED:1\n"
                or execution.stderr != ""
                or content_before != content_after
                or identity_before != identity_after
                or metadata_before.st_dev != metadata_after.st_dev
                or sandbox_before != sandbox_after
                or verifier_before != verifier_after
            ):
                raise ValueError(
                    "fresh sealed probe changed or did not observe exact EPERM"
                )
            _independently_rebuild_swift_network_probe()
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            failures.append(
                f"{label}.network_isolation live probe provenance invalid: {exc}"
            )

    binary = receipt.get("binary")
    if not isinstance(binary, dict) or set(binary) != SWIFT_ANALYZER_BINARY_KEYS:
        failures.append(f"{label}.binary keys are not exact")
        binary = {}
    binary_path = Path(str(binary.get("path", "")))
    if (
        binary.get("name") != "ElmosSwiftAnalyzer"
        or not binary_path.is_absolute()
        or binary_path.name != "ElmosSwiftAnalyzer"
        or not binary_path.parent.name.startswith("elmos-swift-analyzer-")
        or ".." in binary_path.parts
        or not _is_int(binary.get("bytes"), minimum=1)
        or int(binary.get("bytes", 0)) > 100_000_000
        or binary.get("mode") != "0500"
        or binary.get("uid") != os.getuid()
        or binary.get("gid") != os.getgid()
        or binary.get("nlink") != 1
        or not _is_int(binary.get("device"), minimum=1)
        or not _is_int(binary.get("inode"), minimum=1)
    ):
        failures.append(f"{label}.binary identity/seal metadata is invalid")
    _require_digest(failures, binary.get("sha256"), f"{label}.binary.sha256")

    execution_seal = receipt.get("execution_seal")
    if (
        not isinstance(execution_seal, dict)
        or set(execution_seal) != SWIFT_ANALYZER_EXECUTION_SEAL_KEYS
    ):
        failures.append(f"{label}.execution_seal keys are not exact")
        execution_seal = {}
    seal_root = Path(str(execution_seal.get("root", "")))
    if (
        execution_seal.get("policy") != "private-nonwritable-execution-root-v1"
        or not seal_root.is_absolute()
        or not seal_root.name.startswith("elmos-swift-analyzer-")
        or ".." in seal_root.parts
        or execution_seal.get("mode") != "0500"
        or execution_seal.get("uid") != binary.get("uid")
        or execution_seal.get("gid") != binary.get("gid")
        or execution_seal.get("device") != binary.get("device")
        or not _is_int(execution_seal.get("inode"), minimum=1)
        or binary_path.parent != seal_root
        or execution_seal.get("binary") != binary
    ):
        failures.append(f"{label}.execution_seal identity is invalid")

    canonical_identity = receipt.get("canonical_identity")
    if not isinstance(canonical_identity, dict) or set(canonical_identity) != {
        "sha256",
        "receipt",
    }:
        failures.append(f"{label}.canonical_identity keys are not exact")
        canonical_identity = {}
    try:
        rebuilt_canonical = _rebuild_portable_swift_receipt_identity(receipt)
    except (KeyError, TypeError) as exc:
        failures.append(f"{label}.canonical_identity cannot be rebuilt: {exc}")
        rebuilt_canonical = None
    if rebuilt_canonical is not None:
        rebuilt_digest = _receipt_payload_sha256(rebuilt_canonical)

        def contains_host_path(value: object) -> bool:
            if isinstance(value, dict):
                return any(contains_host_path(item) for item in value.values())
            if isinstance(value, list):
                return any(contains_host_path(item) for item in value)
            return isinstance(value, str) and Path(value).is_absolute()

        if contains_host_path(rebuilt_canonical):
            failures.append(f"{label}.canonical_identity contains a host path")
        if (
            canonical_identity.get("receipt") != rebuilt_canonical
            or canonical_identity.get("sha256") != rebuilt_digest
        ):
            failures.append(f"{label}.canonical_identity mismatch")

    if live_binary is not None:
        try:
            if live_binary.is_symlink():
                raise ValueError("binary is a symlink")
            resolved_binary = live_binary.resolve(strict=True)
            if str(resolved_binary) != binary.get("path"):
                raise ValueError("binary path differs from receipt")
            metadata = resolved_binary.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size != binary.get("bytes")
                or f"{stat.S_IMODE(metadata.st_mode):04o}" != binary.get("mode")
                or metadata.st_uid != binary.get("uid")
                or metadata.st_gid != binary.get("gid")
                or metadata.st_nlink != binary.get("nlink")
                or metadata.st_dev != binary.get("device")
                or metadata.st_ino != binary.get("inode")
                or sha256_file(resolved_binary) != binary.get("sha256")
            ):
                raise ValueError("binary bytes/identity differ from receipt")
            root_metadata = seal_root.lstat()
            if (
                not stat.S_ISDIR(root_metadata.st_mode)
                or f"{stat.S_IMODE(root_metadata.st_mode):04o}"
                != execution_seal.get("mode")
                or root_metadata.st_uid != execution_seal.get("uid")
                or root_metadata.st_gid != execution_seal.get("gid")
                or root_metadata.st_dev != execution_seal.get("device")
                or root_metadata.st_ino != execution_seal.get("inode")
                or resolved_binary.parent != seal_root
            ):
                raise ValueError("execution root identity differs from receipt")
            if layout is not None and resolved_binary.is_relative_to(layout[0].parent):
                raise ValueError("repository build cache was used as analyzer binary")
        except (OSError, ValueError) as exc:
            failures.append(f"{label}.binary live provenance invalid: {exc}")

    return receipt if len(failures) == starting_failure_count else None


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
        failures.append(
            f"{label} stable projection differs from independent scratch rebuild"
        )
    return persisted


def _validate_swift_analyzer_version_binding(
    *,
    semantic_document: object,
    receipt: dict[str, Any] | None,
    label: str,
    failures: list[str],
) -> bool:
    if (
        not isinstance(semantic_document, dict)
        or semantic_document.get("source_language") != "swift"
    ):
        return False
    if receipt is None:
        failures.append(f"{label} has no bound Swift analyzer build receipt")
        return True
    source_inputs = receipt.get("source_inputs")
    toolchain = receipt.get("toolchain")
    dependency = receipt.get("dependency")
    binary = receipt.get("binary")
    network = receipt.get("network_isolation")
    canonical = receipt.get("canonical_identity")
    if not all(
        isinstance(item, dict)
        for item in (
            source_inputs,
            toolchain,
            dependency,
            binary,
            network,
            canonical,
        )
    ):
        failures.append(f"{label} Swift analyzer receipt projection is invalid")
        return True
    canonical_toolchain = _canonical_swift_toolchain_identity(toolchain)
    network_policy = network.get("policy")
    policy_digest = (
        network_policy.get("sha256") if isinstance(network_policy, dict) else None
    )
    expected_suffix = (
        f";source-inputs={source_inputs.get('sha256')};"
        f"swift-driver={toolchain.get('swift_driver_sha256')};"
        f"swift-syntax-tree={dependency.get('sha256')};"
        f"canonical-receipt={canonical.get('sha256')};"
        f"binary={binary.get('sha256')};"
        f"toolchain={_receipt_payload_sha256(canonical_toolchain)};"
        f"build-closure={_receipt_payload_sha256(canonical_toolchain['build_closure'])};"
        f"network-policy={policy_digest}"
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
print(
    json.dumps(
        {
            "result": result,
            "smt_base64": base64.b64encode(smt.encode("utf-8")).decode("ascii"),
            "provenance": provenance,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
)
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
        response = json.loads(completed.stdout, parse_constant=_reject_json_constant)
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
        child_cli = {key: child_cli.get(key) for key in ("path", "sha256", "version")}
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
                    f"{artifact_digest}\0{semantic_path}\0{observed_semantic_hash}".encode()
                )
                if mapping.get(f"{side}_chunk_id") != expected_chunk_id:
                    failures.append(f"{label}.mappings[{index}].{side}_chunk_id drift")

        parents = semantic_parents.get(side, {})
        children = semantic_children.get(side, {})
        for path, parent in parents.items():
            if (
                parent is None
                or path not in spans_by_path
                or parent not in spans_by_path
            ):
                continue
            child_span = spans_by_path[path]
            parent_span = spans_by_path[parent]
            if child_span.get("start_byte", -1) < parent_span.get(
                "start_byte", 0
            ) or child_span.get("end_byte", 0) > parent_span.get("end_byte", -1):
                failures.append(f"{label} {side} parent span does not cover {path}")
        for _parent, child_paths in children.items():
            ranged = [
                (
                    spans_by_path[path].get("start_byte"),
                    spans_by_path[path].get("end_byte"),
                    path,
                )
                for path in child_paths
                if path in spans_by_path
            ]
            if any(
                not _is_int(start) or not _is_int(end, minimum=1)
                for start, end, _ in ranged
            ):
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
    if not isinstance(source_validation, dict) or not isinstance(
        target_validation, dict
    ):
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
                    and observation.get("raw") == struct.pack(">d", float(value)).hex()
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
    module_identifier_hygiene: object,
    input_domain: str,
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
    _validate_optional_json_schema(
        formal_input,
        "formal-input-module-function.schema.json",
        failures,
        f"{label} input",
    )
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
        ("input_domain", input_domain),
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
    if not isinstance(module_identifier_hygiene, dict):
        failures.append(f"{label} module identifier hygiene is invalid")
    else:
        identifier_functions = module_identifier_hygiene.get("functions")
        matching_functions = [
            mapping
            for mapping in (
                identifier_functions if isinstance(identifier_functions, list) else []
            )
            if isinstance(mapping, dict) and mapping.get("canonical_symbol") == symbol
        ]
        plan_ref = module_identifier_hygiene.get("plan")
        raw_ref = module_identifier_hygiene.get("raw_target_ir")
        norm_ref = module_identifier_hygiene.get("normalized_target_ir")
        expected_identifier_hygiene = (
            {
                "plan": (
                    {"role": "identifier-plan", **plan_ref}
                    if isinstance(plan_ref, dict)
                    else None
                ),
                "unit_namespace": module_identifier_hygiene.get("unit_namespace"),
                "unit_namespace_sha256": module_identifier_hygiene.get(
                    "unit_namespace_sha256"
                ),
                "raw_target_ir": (
                    {"role": "raw-target-ir", **raw_ref}
                    if isinstance(raw_ref, dict)
                    else None
                ),
                "normalized_target_ir": (
                    {"role": "normalized-target-ir", **norm_ref}
                    if isinstance(norm_ref, dict)
                    else None
                ),
                "function": matching_functions[0],
            }
            if len(matching_functions) == 1
            else None
        )
        if formal_input.get("identifier_hygiene") != expected_identifier_hygiene:
            failures.append(f"{label} identifier hygiene closure drift")
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
    if (
        not isinstance(assumptions, list)
        or not assumptions
        or any(not isinstance(item, str) or not item for item in assumptions)
    ):
        failures.append(f"{label} assumptions must be non-empty")
    claim_scope = formal_result.get("claim_scope")
    if (
        not isinstance(claim_scope, dict)
        or claim_scope.get("input_domain") != input_domain
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
        f"; input-domain: {input_domain}",
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
        input_domain=input_domain,
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
        "external_soundness_boundary": regenerated.get("external_soundness_boundary"),
        "independent_encodings": regenerated.get("independent_encodings"),
        "certification_status": regenerated.get("certification_status"),
    }
    if formal_result != expected_result:
        failures.append(f"{label} result differs from independent re-encoding")
    if (
        regenerated.get("status") != "PROVED_UNDER_ASSUMPTIONS"
        or regenerated.get("property_status") != "PROVED"
    ):
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
    if (
        regenerated.get("status") != "PROVED_UNDER_ASSUMPTIONS"
        or regenerated.get("property_status") != "PROVED"
    ):
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
                    member_relative = member_path.relative_to(
                        route.resolve()
                    ).as_posix()
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
        and (
            record[2] == script_digest
            or (record[1].is_file() and record[2] == sha256_file(record[1]))
        )
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
    expected_roles: set[str],
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
        expected_roles=expected_roles,
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
    _validate_optional_json_schema(
        document,
        "formal-input.schema.json",
        failures,
        label,
    )
    is_specialized = (
        manifest.get("gates", {}).get("canonical_finite_no_error_input_domain_required") is True
    )
    expected_required_keys = (
        FORMAL_INPUT_REQUIRED_KEYS
        if (is_specialized or "identifier_hygiene" in document)
        else (FORMAL_INPUT_REQUIRED_KEYS - {"identifier_hygiene"})
    )
    missing = expected_required_keys - set(document)
    if missing:
        failures.append(f"{label} missing keys: {', '.join(sorted(missing))}")
        return document
    extra = set(document) - expected_required_keys
    if extra:
        failures.append(f"{label} has unexpected keys: {', '.join(sorted(extra))}")
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
        gates = manifest.get("gates", {})
        expected_strict_domain = (
            SPECIALIZED_INPUT_DOMAIN
            if gates.get("canonical_finite_no_error_input_domain_required") is True
            else NODEJS_INPUT_DOMAIN
            if gates.get("nodejs_safe_integer_finite_domain_required") is True
            else None
        )
        if (
            expected_strict_domain is not None
            and claim_scope.get("input_domain") != expected_strict_domain
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
        if set(reference) != {"path", "sha256"}:
            failures.append(f"{label}.{child_label} reference keys are not exact")
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
        expected_roles = {expected_role} if isinstance(expected_role, str) else set(expected_role)
        if child_record[0].get("role") not in expected_roles:
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
            {"normalized-target-ir", "target-ir"},
            "emitted-target-relift-normalized-ir",
        ),
    ):
        binding = document.get(field)
        if not isinstance(binding, dict):
            failures.append(f"{label}.{field} must be an object")
            continue
        if set(binding) != FORMAL_IR_BINDING_KEYS:
            failures.append(f"{label}.{field} keys are not exact")
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

    hygiene = document.get("identifier_hygiene")
    plan_record: tuple[dict[str, Any], Path, str] | None = None
    raw_mapping: dict[str, Any] | None = None
    if (is_specialized or hygiene is not None) and not isinstance(hygiene, dict):
        failures.append(f"{label}.identifier_hygiene must be an object")
    elif hygiene is not None:
        if set(hygiene) != FORMAL_IDENTIFIER_HYGIENE_KEYS:
            failures.append(f"{label}.identifier_hygiene keys are not exact")
        if hygiene.get("kind") != "elmos.verified-alpha-normalization":
            failures.append(f"{label}.identifier_hygiene.kind is invalid")
        plan_reference = hygiene.get("plan")
        if (
            not isinstance(plan_reference, dict)
            or plan_reference.get("path") != "identifier-plan.json"
        ):
            failures.append(f"{label}.identifier_hygiene.plan path is not exact")
        plan_record = bound_sibling(
            plan_reference,
            "identifier-plan",
            "identifier_hygiene.plan",
        )

        raw_binding = hygiene.get("raw_target_relift_ir")
        if not isinstance(raw_binding, dict):
            failures.append(
                f"{label}.identifier_hygiene.raw_target_relift_ir must be an object"
            )
        else:
            if set(raw_binding) != FORMAL_IR_BINDING_KEYS:
                failures.append(
                    f"{label}.identifier_hygiene.raw_target_relift_ir keys are not exact"
                )
            if raw_binding.get("role") != "emitted-target-relift-raw-ir":
                failures.append(
                    f"{label}.identifier_hygiene.raw_target_relift_ir role is invalid"
                )
            raw_reference = raw_binding.get("artifact")
            if (
                not isinstance(raw_reference, dict)
                or raw_reference.get("path") != "target-semantic-ir.raw.json"
            ):
                failures.append(
                    f"{label}.identifier_hygiene.raw_target_relift_ir path is not exact"
                )
            raw_record = bound_sibling(
                raw_reference,
                "raw-target-ir",
                "identifier_hygiene.raw_target_relift_ir.artifact",
            )
            raw_value = raw_binding.get("semantic_ir")
            raw_function = raw_binding.get("formal_function")
            if not isinstance(raw_value, dict) or not isinstance(raw_function, dict):
                failures.append(
                    f"{label}.identifier_hygiene.raw_target_relift_ir semantic IR/function is invalid"
                )
            else:
                raw_mapping = raw_value
                if raw_record is not None:
                    try:
                        persisted_raw = load(raw_record[1])
                    except Exception as exc:
                        failures.append(
                            f"{label}.identifier_hygiene raw target IR is invalid: {exc}"
                        )
                    else:
                        if persisted_raw != raw_value:
                            failures.append(
                                f"{label}.identifier_hygiene raw embedded/persisted IR differ"
                            )
                raw_functions = raw_value.get("functions")
                if not isinstance(raw_functions, list) or len(raw_functions) != 1:
                    failures.append(
                        f"{label}.identifier_hygiene raw target IR must contain exactly one function"
                    )
                elif semantic_value(raw_functions[0]) != raw_function:
                    failures.append(
                        f"{label}.identifier_hygiene raw formal_function drift"
                    )
                if raw_binding.get("semantic_ir_sha256") != canonical_json_sha256(
                    raw_value
                ):
                    failures.append(
                        f"{label}.identifier_hygiene raw semantic_ir_sha256 mismatch"
                    )
                if raw_binding.get("formal_function_sha256") != canonical_json_sha256(
                    raw_function
                ):
                    failures.append(
                        f"{label}.identifier_hygiene raw formal_function_sha256 mismatch"
                    )

        normalized_reference = hygiene.get("normalized_target_ir")
        target_binding = document.get("target_relift_normalized_ir")
        expected_normalized_reference = (
            target_binding.get("artifact") if isinstance(target_binding, dict) else None
        )
        if normalized_reference != expected_normalized_reference:
            failures.append(
                f"{label}.identifier_hygiene normalized target reference mismatch"
            )
        if (
            not isinstance(normalized_reference, dict)
            or normalized_reference.get("path") != "target-semantic-ir.normalized.json"
        ):
            failures.append(
                f"{label}.identifier_hygiene normalized target path is not exact"
            )

    source_mapping = normalized_documents.get("source_normalized_ir")
    target_mapping = normalized_documents.get("target_relift_normalized_ir")
    if (
        isinstance(hygiene, dict)
        and plan_record is not None
        and raw_record is not None
        and isinstance(raw_mapping, dict)
        and isinstance(source_mapping, dict)
        and isinstance(target_mapping, dict)
    ):
        identifier_api = _engine_identifier_api(failures, label)
        if identifier_api is not None:
            (
                SemanticIR,
                IdentifierPlan,
                validate_identifier_plan,
                alpha_normalize_target,
                identifier_plan_bytes,
                _target_ir_view,
                standalone_artifact_unit_namespace,
                _bind_function_spans_from_inventory,
            ) = identifier_api
            try:
                plan_payload = load(plan_record[1])
                _validate_optional_json_schema(
                    plan_payload,
                    "identifier-plan.schema.json",
                    failures,
                    f"{label}.identifier_hygiene.plan",
                )
                source_ir = SemanticIR.from_mapping(source_mapping)
                raw_target_ir = SemanticIR.from_mapping(raw_mapping)
                normalized_target_ir = SemanticIR.from_mapping(target_mapping)
                plan = IdentifierPlan.from_mapping(plan_payload)
                source_artifact = document.get("source_artifact")
                if not isinstance(source_artifact, dict):
                    raise ValueError("source artifact is unavailable")
                source_logical_path = source_artifact.get("path")
                source_sha256 = source_artifact.get("sha256")
                if not isinstance(source_logical_path, str) or not isinstance(
                    source_sha256, str
                ):
                    raise ValueError("source artifact namespace inputs are invalid")
                expected_unit_namespace = standalone_artifact_unit_namespace(
                    source_logical_path,
                    source_sha256,
                )
                validate_identifier_plan(
                    source_ir,
                    plan,
                    expected_unit_namespace=expected_unit_namespace,
                )
                canonical_plan_bytes = identifier_plan_bytes(plan)
                if plan_record[1].read_bytes() != canonical_plan_bytes:
                    raise ValueError("identifier plan bytes are not canonical")
                if plan_record[2] != plan.digest:
                    raise ValueError("identifier plan artifact digest differs")
                if (
                    hygiene.get("plan_digest") != plan.digest
                    or hygiene.get("policy_id") != plan.policy_id
                    or hygiene.get("policy_sha256") != plan.policy_sha256
                    or hygiene.get("unit_namespace")
                    != expected_unit_namespace.to_mapping()
                    or hygiene.get("unit_namespace_sha256")
                    != expected_unit_namespace.digest
                    or plan.target_language
                    != manifest.get("target", {}).get("language")
                ):
                    raise ValueError("identifier plan summary differs")
                recomputed_target = alpha_normalize_target(
                    source_ir, raw_target_ir, plan
                )
                if recomputed_target.to_mapping() != normalized_target_ir.to_mapping():
                    raise ValueError("raw to alpha-normalized target closure differs")
                if (
                    hygiene.get("source_function_name") != source_ir.functions[0].name
                    or hygiene.get("target_function_name")
                    != raw_target_ir.functions[0].name
                ):
                    raise ValueError("identifier function name summary differs")
            except Exception as exc:
                failures.append(f"{label}.identifier_hygiene closure is invalid: {exc}")

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
        if is_specialized or "identifier_hygiene" in implementation:
            expected_files["identifier_hygiene"] = "src/elmos_polyglot_route/identifier_hygiene.py"
        if set(implementation) != set(expected_files):
            failures.append(f"{label}.implementation_identity keys are not exact")
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
    """Require the pinned JSON Schema validator for exact evidence shapes."""

    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError as exc:
        failures.append(
            f"{label} schema validation unavailable: jsonschema is required: {exc}"
        )
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
            if record[0].get("role") not in {
                "source-ir",
                "target-ir",
                "normalized-target-ir",
            }:
                continue
            try:
                semantic_document: dict[str, Any] | None = load(record[1])
            except Exception:
                semantic_document = None
            if semantic_document is None:
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
                            files_by_repository_path: dict[str, dict[str, Any]] = {}
                            captured_paths_by_repository_path: dict[str, Path] = {}
                            live_repository_root = _replay_execution_root(route)
                            is_specialized = (
                                manifest.get("gates", {}).get(
                                    "canonical_finite_no_error_input_domain_required"
                                )
                                is True
                            )
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
                                elif repository_path in files_by_repository_path:
                                    failures.append(
                                        "engine source manifest contains duplicate "
                                        f"repository_path: {repository_path}"
                                    )
                                else:
                                    files_by_repository_path[repository_path] = item
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
                                elif repository_path is not None:
                                    captured_paths_by_repository_path[
                                        repository_path
                                    ] = captured_record[1]
                                if (
                                    validate_live_sources
                                    and repository_path is not None
                                    and not repository_path.startswith("runtime/")
                                ):
                                    live_path = (
                                        live_repository_root / repository_path
                                    ).resolve(strict=False)
                                    try:
                                        live_path.relative_to(live_repository_root)
                                    except ValueError:
                                        failures.append(
                                            "engine source manifest "
                                            f"files[{index}].repository_path "
                                            "escapes the repository"
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
                            if is_specialized:
                                _validate_engine_runtime_source_receipts(
                                    source_manifest_document,
                                    files_by_repository_path,
                                    captured_paths_by_repository_path,
                                    failures,
                                )
                                _validate_required_engine_source_bindings(
                                    route=route,
                                    manifest_relative=manifest_relative,
                                    source_manifest=source_manifest_document,
                                    ref_records=ref_records,
                                    runtime_provenance=_runtime_provenance(
                                        failures,
                                        "formal engine source evidence",
                                    ),
                                    failures=failures,
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
            for index, item in enumerate(chunk_evidence_ids):
                _artifact_record(
                    ref_records,
                    item,
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
        if not isinstance(coverage, int | float) or not 0 <= coverage <= 1:
            failures.append("semantic_chunks.coverage must be between 0 and 1")
        chunks = semantic_chunks.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            failures.append("semantic_chunks.chunks must be a non-empty array")
        else:
            observed = {"MATCHED": 0, "UNMATCHED": 0, "AMBIGUOUS": 0}
            for index, chunk in enumerate(chunks):
                chunk_obj = _require_exact_keys(
                    failures,
                    chunk,
                    required=CHUNK_KEYS,
                    label=f"semantic_chunks.chunks[{index}]",
                )
                if chunk_obj is None:
                    continue
                chunk_id = chunk.get("chunk_id")
                if not isinstance(chunk_id, str) or not chunk_id:
                    failures.append(
                        f"semantic_chunks.chunks[{index}].chunk_id is invalid"
                    )
                semantic_hash = _require_digest(
                    failures,
                    chunk.get("semantic_hash"),
                    f"semantic_chunks.chunks[{index}].semantic_hash",
                )
                source_pointer = _artifact_pointer(
                    ref_records,
                    chunk.get("source_ref"),
                    expected_roles={"source-ir"},
                    label=f"semantic_chunks.chunks[{index}].source_ref",
                    failures=failures,
                )
                target_pointer = _artifact_pointer(
                    ref_records,
                    chunk.get("target_ref"),
                    expected_roles={"normalized-target-ir", "target-ir"},
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
                    if record[0].get("role") in {"normalized-target-ir", "target-ir"}
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
                    if (
                        not isinstance(semantic_functions, list)
                        or len(semantic_functions) != 1
                    ):
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
                                f"semantic chunk artifact {artifact_id} mapping "
                                f"{mapping_index} {pointer_label} is invalid"
                            )
                            continue
                        artifact_digest, artifact_json_pointer = artifact_pointer.split(
                            "#", 1
                        )
                        if artifact_json_pointer != pointer:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping "
                                f"{mapping_index} {pointer_label} pointer drift"
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
                                f"semantic chunk artifact {artifact_id} mapping "
                                f"{mapping_index} {pointer_label} digest is not "
                                "role-bound"
                            )
                    expected_source_chunk_id = sha256_bytes(
                        (
                            f"{source_artifact_pointer.split('#', 1)[0]}\0{pointer}\0{semantic_hash}"
                        ).encode()
                    )
                    expected_target_chunk_id = sha256_bytes(
                        (
                            f"{target_artifact_pointer.split('#', 1)[0]}\0{pointer}\0{semantic_hash}"
                        ).encode()
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
                                f"formal_proof.obligations[{index}] solver result "
                                "input_digest differs from formal input"
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
                        gates = manifest.get("gates", {})
                        expected_strict_domain = (
                            SPECIALIZED_INPUT_DOMAIN
                            if gates.get(
                                "canonical_finite_no_error_input_domain_required"
                            )
                            is True
                            else NODEJS_INPUT_DOMAIN
                            if gates.get("nodejs_safe_integer_finite_domain_required")
                            is True
                            else None
                        )
                        if expected_strict_domain is not None and (
                            not isinstance(result_document.get("claim_scope"), dict)
                            or result_document["claim_scope"].get("input_domain")
                            != expected_strict_domain
                        ):
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result input domain drift"
                            )
                        if (
                            isinstance(formal_input_document, dict)
                            and solver_input_record is not None
                            and expected_strict_domain is not None
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
        _validate_swift_analyzer_version_binding(
            semantic_document=document,
            receipt=(embedded_receipt if isinstance(embedded_receipt, dict) else None),
            label=label,
            failures=failures,
        )
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
                failures.append(
                    f"{subject_label}.source_span identity/bounds are invalid"
                )
            else:
                assert isinstance(start, int) and isinstance(end, int)
                if end <= start:
                    failures.append(
                        f"{subject_label}.source_span identity/bounds are invalid"
                    )
                elif artifact_record is not None and end > artifact_size:
                    failures.append(
                        f"{subject_label}.source_span exceeds artifact bytes"
                    )
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
                "value": value_bytes.decode("utf-8", errors="backslashreplace"),
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
    raw_semantic_document: dict[str, Any] | None = None,
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
    raw_document = raw_semantic_document or semantic_document
    raw_functions = raw_document.get("functions")
    raw_by_symbol = {
        item.get("name"): item
        for item in (raw_functions if isinstance(raw_functions, list) else [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if not isinstance(raw_functions, list) or len(raw_by_symbol) != len(raw_functions):
        failures.append(f"module {side} raw semantic symbol index is invalid")
    observed_symbols: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            failures.append(f"module {side} profile_symbols[{index}] is invalid")
            continue
        symbol = record.get("symbol")
        raw_symbol = record.get("raw_symbol")
        canonical_symbol = record.get("canonical_symbol")
        if (
            not isinstance(symbol, str)
            or not symbol
            or not isinstance(raw_symbol, str)
            or not raw_symbol
            or not isinstance(canonical_symbol, str)
            or not canonical_symbol
            or symbol != canonical_symbol
        ):
            failures.append(f"module {side} profile_symbols[{index}].symbol is invalid")
            continue
        observed_symbols.append(symbol)
        function = by_symbol.get(canonical_symbol)
        raw_function = raw_by_symbol.get(raw_symbol)
        if function is None or raw_function is None:
            failures.append(
                f"module {side} inventory symbol {raw_symbol}/{canonical_symbol} is absent from IR"
            )
            continue
        if record.get("source_span") != raw_function.get("source_span"):
            failures.append(
                f"module {side} inventory span for {symbol} differs from semantic IR"
            )
        raw_parameters = raw_function.get("parameters")
        expected_raw_parameter_names = [
            parameter.get("name")
            for parameter in (
                raw_parameters if isinstance(raw_parameters, list) else []
            )
            if isinstance(parameter, dict)
        ]
        if record.get("raw_parameter_names") != expected_raw_parameter_names:
            failures.append(
                f"module {side} raw parameter names for {raw_symbol} differ from raw semantic IR"
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


def _validate_identifier_function_mapping_shape(
    mappings: object,
    *,
    label: str,
    minimum_functions: int,
    failures: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(mappings, list) or len(mappings) < minimum_functions:
        failures.append(f"{label} functions are invalid")
        return []
    parsed: list[dict[str, Any]] = []
    for function_index, mapping in enumerate(mappings):
        if (
            not isinstance(mapping, dict)
            or set(mapping) != IDENTIFIER_FUNCTION_MAPPING_KEYS
        ):
            failures.append(f"{label} function {function_index} keys are not exact")
            continue
        raw_symbol = mapping.get("raw_symbol")
        canonical_symbol = mapping.get("canonical_symbol")
        parameters = mapping.get("parameters")
        if (
            not isinstance(raw_symbol, str)
            or not raw_symbol
            or not isinstance(canonical_symbol, str)
            or not canonical_symbol
            or not isinstance(parameters, list)
        ):
            failures.append(f"{label} function {function_index} is invalid")
            continue
        valid = True
        for parameter_index, parameter in enumerate(parameters):
            if (
                not isinstance(parameter, dict)
                or set(parameter) != IDENTIFIER_PARAMETER_MAPPING_KEYS
                or not isinstance(parameter.get("raw_name"), str)
                or not parameter.get("raw_name")
                or not isinstance(parameter.get("canonical_name"), str)
                or not parameter.get("canonical_name")
                or parameter.get("canonical_type")
                not in _TARGET_CALL_GRAPH_CANONICAL_TYPES
            ):
                failures.append(
                    f"{label} function {function_index} parameter {parameter_index} is invalid"
                )
                valid = False
        if valid:
            parsed.append(mapping)
    raw_symbols = [mapping["raw_symbol"] for mapping in parsed]
    canonical_symbols = [mapping["canonical_symbol"] for mapping in parsed]
    if len(raw_symbols) != len(set(raw_symbols)):
        failures.append(f"{label} contains duplicate raw symbols")
    if len(canonical_symbols) != len(set(canonical_symbols)):
        failures.append(f"{label} contains duplicate canonical symbols")
    return parsed


def _validate_module_javascript_esm_descriptor(
    *,
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    module_input: dict[str, Any],
    role_records: dict[str, list[tuple[dict[str, Any], Path, str]]],
    source_artifact_record: tuple[dict[str, Any], Path, str] | None,
    failures: list[str],
) -> tuple[dict[str, Any], Path, str] | None:
    """Bind a JavaScript ``.js`` module to its exact route-local ESM descriptor."""

    source_language = manifest.get("source", {}).get("language")
    source_logical_file = module_input.get("source_logical_file")
    descriptor_required = (
        source_language == "javascript"
        and isinstance(source_logical_file, str)
        and source_logical_file.endswith(".js")
        and not source_logical_file.endswith(".mjs")
    )
    descriptor = evidence.get("javascript_esm_descriptor")
    input_descriptor = module_input.get("javascript_esm_descriptor")
    observation = evidence.get("javascript_esm_descriptor_observation")
    records = role_records.get("source-javascript-esm-descriptor", [])
    if not descriptor_required:
        if (
            descriptor is not None
            or input_descriptor is not None
            or observation is not None
        ):
            failures.append(
                "JavaScript ESM descriptor fields are forbidden for this module source"
            )
        if records:
            failures.append(
                "source-javascript-esm-descriptor is forbidden for this module source"
            )
        return None

    if source_artifact_record is None:
        failures.append("JavaScript ESM descriptor has no bound source artifact")
        return None
    if len(records) != 1:
        failures.append(
            "JavaScript .js module must bind exactly one source-javascript-esm-descriptor"
        )
        return None
    record = records[0]
    if (
        not isinstance(descriptor, dict)
        or set(descriptor) != JAVASCRIPT_ESM_DESCRIPTOR_KEYS
    ):
        failures.append("module JavaScript ESM descriptor keys are not exact")
        return None
    if input_descriptor != descriptor:
        failures.append("module_input JavaScript ESM descriptor differs from report")
    if (
        not isinstance(observation, dict)
        or set(observation) != JAVASCRIPT_ESM_DESCRIPTOR_OBSERVATION_KEYS
    ):
        failures.append(
            "module JavaScript ESM descriptor observation keys are not exact"
        )
    else:
        observed_origin = observation.get("observed_origin_path")
        if (
            not isinstance(observed_origin, str)
            or not Path(observed_origin).is_absolute()
            or Path(observed_origin).name != "package.json"
        ):
            failures.append(
                "module JavaScript ESM descriptor observation path is invalid"
            )

    logical_path = descriptor.get("logical_path")
    logical_parts = (
        Path(str(logical_path)).parts if isinstance(logical_path, str) else ()
    )
    if (
        not isinstance(logical_path, str)
        or not logical_path
        or Path(logical_path).is_absolute()
        or "\\" in logical_path
        or any(
            ord(character) < 32 or ord(character) == 127 for character in logical_path
        )
        or not logical_parts
        or any(part in {"", "."} for part in logical_parts)
        or logical_parts[-1] != "package.json"
    ):
        failures.append("module JavaScript ESM descriptor logical_path is invalid")
    bound_artifact_path = record[0].get("path")
    canonical_artifact_path = "source-module-artifact/package.json"
    source_path = source_artifact_record[0].get("path")
    expected_source_sibling = (
        (Path(source_path).parent / "package.json").as_posix()
        if isinstance(source_path, str)
        else None
    )
    if (
        descriptor.get("snapshot_path") != "source/package.json"
        or descriptor.get("artifact_path") != canonical_artifact_path
        or not isinstance(bound_artifact_path, str)
        or not (
            bound_artifact_path == canonical_artifact_path
            or bound_artifact_path.endswith("/" + canonical_artifact_path)
        )
        or bound_artifact_path != expected_source_sibling
        or descriptor.get("sha256") != record[2]
        or descriptor.get("bytes") != record[1].stat().st_size
        or descriptor.get("type") != "module"
    ):
        failures.append("module JavaScript ESM descriptor binding is invalid")
    try:
        package = load(record[1])
    except Exception as exc:
        failures.append(f"module JavaScript ESM descriptor is invalid JSON: {exc}")
    else:
        if package.get("type") != "module":
            failures.append(
                "module JavaScript ESM descriptor package type is not module"
            )
    return record


def _validate_module_identifier_closure(
    *,
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    module_input: dict[str, Any],
    closure_document: dict[str, Any],
    role_records: dict[str, list[tuple[dict[str, Any], Path, str]]],
    source_semantic_document: dict[str, Any],
    target_semantic_document: dict[str, Any],
    source_inventory_document: dict[str, Any],
    target_inventory_document: dict[str, Any],
    minimum_functions: int,
    failures: list[str],
) -> dict[str, Any]:
    """Recompute the module IdentifierPlan and raw-to-canonical IR closure."""

    hygiene = evidence.get("identifier_hygiene")
    if not isinstance(hygiene, dict):
        failures.append("module identifier_hygiene must be an object")
        return {}
    if set(hygiene) != MODULE_IDENTIFIER_HYGIENE_KEYS:
        failures.append("module identifier_hygiene keys are not exact")
    if module_input.get("identifier_hygiene") != hygiene:
        failures.append("module_input identifier_hygiene differs from module report")

    expected_references: dict[str, dict[str, Any]] = {}
    for field, role, filename in (
        ("plan", "identifier-plan", "identifier-plan.json"),
        ("raw_target_ir", "raw-target-ir", "target-semantic-ir.raw.json"),
        (
            "normalized_target_ir",
            "normalized-target-ir",
            "target-semantic-ir.normalized.json",
        ),
    ):
        records = role_records.get(role, [])
        if len(records) != 1:
            failures.append(f"module identifier closure requires exactly one {role}")
            continue
        record = records[0]
        expected_reference = {
            "path": filename,
            "sha256": record[2],
            "bytes": record[1].stat().st_size,
        }
        expected_references[field] = expected_reference
        if record[1].name != filename:
            failures.append(f"module {role} filename is not exact")
        if hygiene.get(field) != expected_reference:
            failures.append(f"module identifier_hygiene.{field} is detached")

    required_roles = {"identifier-plan", "raw-target-ir", "normalized-target-ir"}
    if not all(len(role_records.get(role, [])) == 1 for role in required_roles):
        return {}
    plan_record = role_records["identifier-plan"][0]
    raw_record = role_records["raw-target-ir"][0]
    normalized_record = role_records["normalized-target-ir"][0]
    try:
        plan_mapping = load(plan_record[1])
        raw_mapping = load(raw_record[1])
        normalized_mapping = load(normalized_record[1])
    except Exception as exc:
        failures.append(f"module identifier artifact is invalid JSON: {exc}")
        return {}
    _validate_optional_json_schema(
        plan_mapping,
        "identifier-plan.schema.json",
        failures,
        "module identifier plan",
    )
    if normalized_mapping != target_semantic_document:
        failures.append(
            "module normalized-target-ir differs from target-module-semantic-ir"
        )

    identifier_api = _engine_identifier_api(failures, "module identifier closure")
    if identifier_api is None:
        return {}
    (
        SemanticIR,
        IdentifierPlan,
        validate_identifier_plan,
        alpha_normalize_target,
        identifier_plan_bytes,
        target_ir_view,
        standalone_artifact_unit_namespace,
        bind_function_spans_from_inventory,
    ) = identifier_api
    closure_result: dict[str, Any] = {}
    try:
        source_ir = bind_function_spans_from_inventory(
            SemanticIR.from_mapping(source_semantic_document),
            source_inventory_document,
            role="source-validator-replay",
        )
        raw_target_ir = bind_function_spans_from_inventory(
            SemanticIR.from_mapping(raw_mapping),
            target_inventory_document,
            role="target-validator-replay",
        )
        normalized_target_ir = SemanticIR.from_mapping(normalized_mapping)
        plan = IdentifierPlan.from_mapping(plan_mapping)
        source_logical_file = module_input.get("source_logical_file")
        source_artifact_sha256 = module_input.get("source_artifact_sha256")
        if not isinstance(source_logical_file, str) or not isinstance(
            source_artifact_sha256, str
        ):
            raise ValueError("module unit namespace inputs are invalid")
        expected_unit_namespace = standalone_artifact_unit_namespace(
            source_logical_file,
            source_artifact_sha256,
        )
        validate_identifier_plan(
            source_ir,
            plan,
            expected_unit_namespace=expected_unit_namespace,
        )
        if plan_record[1].read_bytes() != identifier_plan_bytes(plan):
            raise ValueError("identifier plan bytes are not canonical")
        if plan_record[2] != plan.digest:
            raise ValueError("identifier plan artifact digest differs")
        if plan.target_language != manifest.get("target", {}).get("language"):
            raise ValueError("identifier plan target language differs")
        recomputed = alpha_normalize_target(source_ir, raw_target_ir, plan)
        if recomputed.to_mapping() != normalized_target_ir.to_mapping():
            raise ValueError("raw to alpha-normalized target closure differs")
        expected_raw_view = target_ir_view(source_ir, plan)
        raw_by_symbol = {
            function.name: function for function in raw_target_ir.functions
        }
        canonical_by_symbol = {
            function.name: function for function in normalized_target_ir.functions
        }
        expected_functions: list[dict[str, Any]] = []
        for source_function, expected_raw_function in zip(
            source_ir.functions,
            expected_raw_view.functions,
            strict=True,
        ):
            raw_function = raw_by_symbol.get(expected_raw_function.name)
            canonical_function = canonical_by_symbol.get(source_function.name)
            if raw_function is None or canonical_function is None:
                raise ValueError("identifier function mapping is incomplete")
            expected_functions.append(
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
            )
        _validate_identifier_function_mapping_shape(
            hygiene.get("functions"),
            label="module identifier_hygiene",
            minimum_functions=minimum_functions,
            failures=failures,
        )
        expected_hygiene = {
            "status": "PASSED",
            "policy_id": plan.policy_id,
            "policy_sha256": plan.policy_sha256,
            "unit_namespace": expected_unit_namespace.to_mapping(),
            "unit_namespace_sha256": expected_unit_namespace.digest,
            **expected_references,
            "functions": expected_functions,
            "renamed": any(
                binding.decision == "ALPHA_RENAMED" for binding in plan.bindings
            ),
        }
        if hygiene != expected_hygiene:
            raise ValueError("module identifier hygiene summary differs")
        expected_whole_file_hygiene = {
            "status": "PASSED",
            "policy_id": plan.policy_id,
            "policy_sha256": plan.policy_sha256,
            "unit_namespace": expected_unit_namespace.to_mapping(),
            "unit_namespace_sha256": expected_unit_namespace.digest,
            "plan_sha256": plan.digest,
            "functions": sorted(
                expected_functions,
                key=lambda mapping: str(mapping["canonical_symbol"]),
            ),
        }
        observed_whole_file_hygiene = closure_document.get("identifier_hygiene")
        if (
            not isinstance(observed_whole_file_hygiene, dict)
            or set(observed_whole_file_hygiene) != WHOLE_FILE_IDENTIFIER_HYGIENE_KEYS
            or observed_whole_file_hygiene != expected_whole_file_hygiene
        ):
            raise ValueError("whole-file identifier hygiene summary differs")
        closure_result = {
            "source_ir": source_ir,
            "raw_target_ir": raw_target_ir,
            "normalized_target_ir": normalized_target_ir,
            "plan": plan,
            "functions": expected_functions,
        }
    except Exception as exc:
        failures.append(f"module identifier closure is invalid: {exc}")
    return closure_result


_TARGET_CALL_GRAPH_BASE_EDGE_KEYS = frozenset(
    {
        "caller",
        "canonical_caller",
        "callee",
        "callee_kind",
        "canonical_domain",
        "canonical_operator",
        "normalization_rule",
    }
)
_TARGET_CALL_GRAPH_GUARD_KEYS = _TARGET_CALL_GRAPH_BASE_EDGE_KEYS | {
    "guard_scope",
    "guard_subject",
    "canonical_guard_subject",
}
_TARGET_CALL_GRAPH_SCOPED_ARITHMETIC_KEYS = _TARGET_CALL_GRAPH_BASE_EDGE_KEYS | {
    "guard_scope",
    "guard_subject",
}
_TARGET_CALL_GRAPH_LEGACY_BASE_EDGE_KEYS = _TARGET_CALL_GRAPH_BASE_EDGE_KEYS - {
    "canonical_caller"
}
_TARGET_CALL_GRAPH_LEGACY_SCOPED_ARITHMETIC_KEYS = (
    _TARGET_CALL_GRAPH_SCOPED_ARITHMETIC_KEYS - {"canonical_caller"}
)
_TARGET_CALL_GRAPH_ARITHMETIC_OPERATORS = frozenset({"+", "-", "*", "/", "%"})
_TARGET_CALL_GRAPH_CANONICAL_TYPES = frozenset(
    {"integer", "number", "boolean", "string"}
)
_JAVASCRIPT_GUARD_HELPERS = {
    "integer": "_elmosRequireSafeInteger",
    "number": "_elmosRequireFiniteNumber",
    "boolean": "_elmosRequireBoolean",
    "string": "_elmosRequireString",
}
_JAVASCRIPT_RETURN_GUARD_RULES = {
    "integer": "javascript.return.integer.safe-integer",
    "number": "javascript.return.number.finite",
    "boolean": "javascript.return.boolean.exact",
    "string": "javascript.return.string.exact",
}


def _module_expression_type_and_operator_uses(
    expression: object,
    environment: dict[str, str],
    operator_uses: set[tuple[str, str]],
) -> str:
    """Independently type one canonical expression and collect arithmetic uses."""

    if not isinstance(expression, dict):
        raise ValueError("expression is not an object")
    kind = expression.get("kind")
    if kind == "name":
        name = expression.get("value")
        if not isinstance(name, str) or name not in environment:
            raise ValueError(f"undeclared expression name: {name!r}")
        return environment[name]
    if kind == "literal":
        value = expression.get("value")
        if type(value) is bool:
            return "boolean"
        if type(value) is int:
            return "integer"
        if type(value) is float:
            return "number"
        if type(value) is str:
            return "string"
        raise ValueError("literal is outside the canonical type domain")
    if kind != "binary":
        raise ValueError(f"unsupported expression kind: {kind!r}")

    operator = expression.get("operator")
    if not isinstance(operator, str):
        raise ValueError("binary expression operator is invalid")
    left = _module_expression_type_and_operator_uses(
        expression.get("left"), environment, operator_uses
    )
    right = _module_expression_type_and_operator_uses(
        expression.get("right"), environment, operator_uses
    )
    numeric_types = {"integer", "number"}
    if operator in _TARGET_CALL_GRAPH_ARITHMETIC_OPERATORS:
        if operator == "+" and left == right == "string":
            return "string"
        if left not in numeric_types or right not in numeric_types:
            raise ValueError(
                f"arithmetic operand type mismatch: {operator}:{left}:{right}"
            )
        domain = "number" if "number" in {left, right} else "integer"
        operator_uses.add((domain, operator))
        return domain
    if operator in {"<", "<=", ">", ">="}:
        if left not in numeric_types or right not in numeric_types:
            raise ValueError(
                f"ordering operand type mismatch: {operator}:{left}:{right}"
            )
        return "boolean"
    if operator in {"==", "!="}:
        if left != right and not (left in numeric_types and right in numeric_types):
            raise ValueError(
                f"equality operand type mismatch: {operator}:{left}:{right}"
            )
        return "boolean"
    if operator in {"&&", "||"}:
        if left != "boolean" or right != "boolean":
            raise ValueError(
                f"logical operand type mismatch: {operator}:{left}:{right}"
            )
        return "boolean"
    raise ValueError(f"unsupported binary operator: {operator!r}")


def _module_function_operator_uses(function: dict[str, Any]) -> set[tuple[str, str]]:
    parameters = function.get("parameters")
    if not isinstance(parameters, list):
        raise ValueError("function parameters are invalid")
    environment: dict[str, str] = {}
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise ValueError("function parameter is invalid")
        name = parameter.get("name")
        domain = parameter.get("type")
        if (
            not isinstance(name, str)
            or not name
            or name in environment
            or domain not in _TARGET_CALL_GRAPH_CANONICAL_TYPES
        ):
            raise ValueError("function parameter signature is invalid")
        environment[name] = str(domain)

    operator_uses: set[tuple[str, str]] = set()

    def walk_statements(statements: object) -> None:
        if not isinstance(statements, list):
            raise ValueError("function statements are invalid")
        for statement in statements:
            if not isinstance(statement, dict):
                raise ValueError("function statement is invalid")
            for expression_key in ("expression", "condition"):
                expression = statement.get(expression_key)
                if expression is not None:
                    _module_expression_type_and_operator_uses(
                        expression, environment, operator_uses
                    )
            for branch_key in ("then", "else"):
                branch = statement.get(branch_key)
                if branch is not None:
                    walk_statements(branch)

    walk_statements(function.get("body"))
    return operator_uses


def _javascript_expected_target_call_graph_edges(
    raw_target_semantic_document: dict[str, Any],
    target_semantic_document: dict[str, Any],
    identifier_functions: list[dict[str, Any]],
    failures: list[str],
) -> list[dict[str, str]]:
    """Reconstruct every JavaScript signature and arithmetic guard edge."""

    raw_functions = raw_target_semantic_document.get("functions")
    canonical_functions = target_semantic_document.get("functions")
    if not isinstance(raw_functions, list) or not isinstance(canonical_functions, list):
        failures.append(
            "JavaScript raw/canonical target semantic functions are invalid"
        )
        return []
    canonical_by_symbol = {
        function.get("name"): function
        for function in canonical_functions
        if isinstance(function, dict) and isinstance(function.get("name"), str)
    }
    mapping_by_raw = {
        mapping.get("raw_symbol"): mapping
        for mapping in identifier_functions
        if isinstance(mapping, dict) and isinstance(mapping.get("raw_symbol"), str)
    }
    expected: list[dict[str, str]] = []
    for function_index, raw_function in enumerate(raw_functions):
        if not isinstance(raw_function, dict):
            failures.append(
                f"JavaScript raw target semantic function {function_index} is invalid"
            )
            continue
        caller = raw_function.get("name")
        mapping = mapping_by_raw.get(caller)
        canonical_caller = (
            mapping.get("canonical_symbol") if isinstance(mapping, dict) else None
        )
        canonical_function = canonical_by_symbol.get(canonical_caller)
        parameters = raw_function.get("parameters")
        canonical_parameters = (
            canonical_function.get("parameters")
            if isinstance(canonical_function, dict)
            else None
        )
        parameter_mappings = (
            mapping.get("parameters") if isinstance(mapping, dict) else None
        )
        return_type = raw_function.get("return_type")
        if (
            not isinstance(caller, str)
            or not caller
            or not isinstance(canonical_caller, str)
            or not canonical_caller
            or not isinstance(parameters, list)
            or not isinstance(canonical_parameters, list)
            or not isinstance(parameter_mappings, list)
            or len(parameters) != len(canonical_parameters)
            or len(parameters) != len(parameter_mappings)
            or return_type not in _TARGET_CALL_GRAPH_CANONICAL_TYPES
            or not isinstance(canonical_function, dict)
            or canonical_function.get("return_type") != return_type
        ):
            failures.append(
                f"JavaScript target semantic function {function_index} signature is invalid"
            )
            continue
        signature_valid = True
        for parameter_index, (
            parameter,
            canonical_parameter,
            parameter_mapping,
        ) in enumerate(
            zip(parameters, canonical_parameters, parameter_mappings, strict=True)
        ):
            if (
                not isinstance(parameter, dict)
                or not isinstance(canonical_parameter, dict)
                or not isinstance(parameter_mapping, dict)
            ):
                failures.append(
                    "JavaScript target semantic parameter "
                    f"{caller}[{parameter_index}] is invalid"
                )
                signature_valid = False
                continue
            subject = parameter.get("name")
            canonical_subject = canonical_parameter.get("name")
            domain = parameter.get("type")
            if (
                not isinstance(subject, str)
                or not subject
                or not isinstance(canonical_subject, str)
                or not canonical_subject
                or domain not in _TARGET_CALL_GRAPH_CANONICAL_TYPES
                or canonical_parameter.get("type") != domain
                or parameter_mapping
                != {
                    "raw_name": subject,
                    "canonical_name": canonical_subject,
                    "canonical_type": domain,
                }
            ):
                failures.append(
                    "JavaScript target semantic parameter "
                    f"{caller}[{parameter_index}] signature is invalid"
                )
                signature_valid = False
                continue
            expected.append(
                {
                    "caller": caller,
                    "canonical_caller": canonical_caller,
                    "callee": _JAVASCRIPT_GUARD_HELPERS[str(domain)],
                    "callee_kind": "exact-generated-helper",
                    "canonical_domain": str(domain),
                    "canonical_operator": "guard",
                    "normalization_rule": f"javascript.parameter.{domain}.exact",
                    "guard_scope": "signature-parameter",
                    "guard_subject": subject,
                    "canonical_guard_subject": canonical_subject,
                }
            )
        expected.append(
            {
                "caller": caller,
                "canonical_caller": canonical_caller,
                "callee": _JAVASCRIPT_GUARD_HELPERS[str(return_type)],
                "callee_kind": "exact-generated-helper",
                "canonical_domain": str(return_type),
                "canonical_operator": "guard",
                "normalization_rule": _JAVASCRIPT_RETURN_GUARD_RULES[str(return_type)],
                "guard_scope": "signature-return",
                "guard_subject": "return",
                "canonical_guard_subject": "return",
            }
        )
        if not signature_valid:
            continue
        try:
            operator_uses = _module_function_operator_uses(raw_function)
        except ValueError as exc:
            failures.append(
                f"JavaScript target semantic function {caller} cannot be typed: {exc}"
            )
            continue
        for domain, operator in sorted(operator_uses):
            result_callee = _JAVASCRIPT_GUARD_HELPERS[domain]
            result_rule = (
                f"javascript.integer.{operator}.safe-integer"
                if domain == "integer"
                else f"javascript.number.{operator}.finite-result"
            )
            expected.append(
                {
                    "caller": caller,
                    "canonical_caller": canonical_caller,
                    "callee": result_callee,
                    "callee_kind": "exact-generated-helper",
                    "canonical_domain": domain,
                    "canonical_operator": operator,
                    "normalization_rule": result_rule,
                    "guard_scope": "arithmetic-result",
                    "guard_subject": operator,
                }
            )
            if domain == "integer" and operator in {"/", "%"}:
                divisor_rule = (
                    "javascript.integer./.truncating-non-zero"
                    if operator == "/"
                    else "javascript.integer.%.non-zero"
                )
                expected.append(
                    {
                        "caller": caller,
                        "canonical_caller": canonical_caller,
                        "callee": "_elmosRequireNonZero",
                        "callee_kind": "exact-generated-helper",
                        "canonical_domain": domain,
                        "canonical_operator": operator,
                        "normalization_rule": divisor_rule,
                        "guard_scope": "arithmetic-divisor",
                        "guard_subject": operator,
                    }
                )
    return expected


def _typescript_expected_target_call_graph_edges(
    raw_target_semantic_document: dict[str, Any],
    target_semantic_document: dict[str, Any],
    identifier_functions: list[dict[str, Any]],
    failures: list[str],
) -> list[dict[str, str]]:
    """Independently reconstruct every required TypeScript runtime guard edge."""

    raw_functions = raw_target_semantic_document.get("functions")
    canonical_functions = target_semantic_document.get("functions")
    if not isinstance(raw_functions, list) or not isinstance(canonical_functions, list):
        failures.append(
            "TypeScript raw/canonical target semantic functions are invalid"
        )
        return []
    canonical_by_symbol = {
        function.get("name"): function
        for function in canonical_functions
        if isinstance(function, dict) and isinstance(function.get("name"), str)
    }
    mapping_by_raw = {
        mapping.get("raw_symbol"): mapping
        for mapping in identifier_functions
        if isinstance(mapping, dict) and isinstance(mapping.get("raw_symbol"), str)
    }
    expected: list[dict[str, str]] = []
    for function_index, raw_function in enumerate(raw_functions):
        if not isinstance(raw_function, dict):
            failures.append(
                f"TypeScript raw target semantic function {function_index} is invalid"
            )
            continue
        caller = raw_function.get("name")
        mapping = mapping_by_raw.get(caller)
        canonical_caller = (
            mapping.get("canonical_symbol") if isinstance(mapping, dict) else None
        )
        canonical_function = canonical_by_symbol.get(canonical_caller)
        parameters = raw_function.get("parameters")
        canonical_parameters = (
            canonical_function.get("parameters")
            if isinstance(canonical_function, dict)
            else None
        )
        parameter_mappings = (
            mapping.get("parameters") if isinstance(mapping, dict) else None
        )
        return_type = raw_function.get("return_type")
        if (
            not isinstance(caller, str)
            or not caller
            or not isinstance(canonical_caller, str)
            or not canonical_caller
            or not isinstance(parameters, list)
            or not isinstance(canonical_parameters, list)
            or not isinstance(parameter_mappings, list)
            or len(parameters) != len(canonical_parameters)
            or len(parameters) != len(parameter_mappings)
            or return_type not in _TARGET_CALL_GRAPH_CANONICAL_TYPES
            or not isinstance(canonical_function, dict)
            or canonical_function.get("return_type") != return_type
        ):
            failures.append(
                f"TypeScript target semantic function {function_index} signature is invalid"
            )
            continue
        signature_valid = True
        for parameter_index, (
            parameter,
            canonical_parameter,
            parameter_mapping,
        ) in enumerate(
            zip(parameters, canonical_parameters, parameter_mappings, strict=True)
        ):
            if (
                not isinstance(parameter, dict)
                or not isinstance(canonical_parameter, dict)
                or not isinstance(parameter_mapping, dict)
            ):
                failures.append(
                    "TypeScript target semantic parameter "
                    f"{caller}[{parameter_index}] is invalid"
                )
                signature_valid = False
                continue
            subject = parameter.get("name")
            canonical_subject = canonical_parameter.get("name")
            domain = parameter.get("type")
            if (
                not isinstance(subject, str)
                or not subject
                or not isinstance(canonical_subject, str)
                or not canonical_subject
                or domain not in _TARGET_CALL_GRAPH_CANONICAL_TYPES
                or canonical_parameter.get("type") != domain
                or parameter_mapping
                != {
                    "raw_name": subject,
                    "canonical_name": canonical_subject,
                    "canonical_type": domain,
                }
            ):
                failures.append(
                    "TypeScript target semantic parameter "
                    f"{caller}[{parameter_index}] signature is invalid"
                )
                signature_valid = False
                continue
            if domain == "integer":
                expected.append(
                    {
                        "caller": caller,
                        "canonical_caller": canonical_caller,
                        "callee": "_elmosRequireSafeInteger",
                        "callee_kind": "exact-generated-helper",
                        "canonical_domain": "integer",
                        "canonical_operator": "guard",
                        "normalization_rule": (
                            "typescript.parameter.integer.safe-integer"
                        ),
                        "guard_scope": "signature-parameter",
                        "guard_subject": subject,
                        "canonical_guard_subject": canonical_subject,
                    }
                )
        if return_type in {"integer", "number"}:
            expected.append(
                {
                    "caller": caller,
                    "canonical_caller": canonical_caller,
                    "callee": (
                        "_elmosRequireSafeInteger"
                        if return_type == "integer"
                        else "_elmosRequireFiniteNumber"
                    ),
                    "callee_kind": "exact-generated-helper",
                    "canonical_domain": str(return_type),
                    "canonical_operator": "guard",
                    "normalization_rule": (
                        f"typescript.return.{return_type}."
                        + ("safe-integer" if return_type == "integer" else "finite")
                    ),
                    "guard_scope": "signature-return",
                    "guard_subject": "return",
                    "canonical_guard_subject": "return",
                }
            )
        if not signature_valid:
            continue
        try:
            operator_uses = _module_function_operator_uses(raw_function)
        except ValueError as exc:
            failures.append(
                f"TypeScript target semantic function {caller} cannot be typed: {exc}"
            )
            continue
        for domain, operator in sorted(operator_uses):
            result_callee = (
                "_elmosRequireSafeInteger"
                if domain == "integer"
                else "_elmosRequireFiniteNumber"
            )
            expected.append(
                {
                    "caller": caller,
                    "canonical_caller": canonical_caller,
                    "callee": result_callee,
                    "callee_kind": "exact-generated-helper",
                    "canonical_domain": domain,
                    "canonical_operator": operator,
                    "normalization_rule": (
                        f"typescript.integer.{operator}.safe-integer"
                        if domain == "integer"
                        else f"typescript.number.{operator}.finite-result"
                    ),
                    "guard_scope": "arithmetic-result",
                    "guard_subject": operator,
                }
            )
            if operator in {"/", "%"}:
                expected.append(
                    {
                        "caller": caller,
                        "canonical_caller": canonical_caller,
                        "callee": "_elmosRequireNonZero",
                        "callee_kind": "exact-generated-helper",
                        "canonical_domain": domain,
                        "canonical_operator": operator,
                        "normalization_rule": (
                            (
                                "typescript.integer./.truncating-non-zero"
                                if operator == "/"
                                else "typescript.integer.%.non-zero"
                            )
                            if domain == "integer"
                            else (
                                f"typescript.number.{operator}."
                                "non-zero:_elmosRequireNonZero"
                            )
                        ),
                        "guard_scope": "arithmetic-divisor",
                        "guard_subject": operator,
                    }
                )
    return expected


def _target_call_graph_edge_identity(edge: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(edge.get(key, ""))
        for key in (
            "caller",
            "canonical_caller",
            "callee",
            "callee_kind",
            "canonical_domain",
            "canonical_operator",
            "normalization_rule",
            "guard_scope",
            "guard_subject",
            "canonical_guard_subject",
        )
    )


def _target_call_graph_sort_key(edge: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(value)
        for value in (
            edge.get("caller", ""),
            edge.get("canonical_caller", ""),
            edge.get("callee", ""),
            edge.get("canonical_domain", ""),
            edge.get("canonical_operator", ""),
            edge.get("guard_scope", "operator"),
            edge.get("guard_subject", ""),
            edge.get("canonical_guard_subject", ""),
        )
    )


def _validate_target_call_graph(
    *,
    target_call_graph: object,
    manifest_symbols: list[str],
    target_language: object,
    raw_target_semantic_document: dict[str, Any],
    target_semantic_document: dict[str, Any],
    identifier_functions: list[dict[str, Any]],
    helper_identifiers: set[str],
    normalizations: object,
    failures: list[str],
) -> None:
    """Validate exact helper edges without trusting engine-authored closure counts."""

    if not isinstance(target_call_graph, dict) or set(target_call_graph) != {
        "status",
        "scope",
        "edges",
        "helper_internal_calls",
    }:
        failures.append("whole-file target call graph is invalid")
        return
    if (
        target_call_graph.get("status") != "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
        or target_call_graph.get("scope") != "profile-functions-to-emitted-callees"
        or target_call_graph.get("helper_internal_calls")
        != {
            "status": "CONTENT_BOUND_NOT_EDGE_ENUMERATED",
            "binding": "verified_generated_helpers-exact-bytes-and-digests",
        }
    ):
        failures.append("whole-file target call graph identity drift")
    normalization_set = (
        set(normalizations) if isinstance(normalizations, list) else set()
    )
    edges = target_call_graph.get("edges")
    if not isinstance(edges, list):
        failures.append("whole-file target call graph edges are invalid")
        return
    identifier_by_raw = {
        mapping.get("raw_symbol"): mapping
        for mapping in identifier_functions
        if isinstance(mapping, dict) and isinstance(mapping.get("raw_symbol"), str)
    }

    valid_edges: list[dict[str, Any]] = []
    normalized_edges: list[tuple[str, ...]] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            failures.append(
                f"whole-file target call graph edge {index} keys are invalid"
            )
            continue
        operator = edge.get("canonical_operator")
        edge_keys = set(edge)
        if operator == "guard":
            keys_valid = edge_keys == _TARGET_CALL_GRAPH_GUARD_KEYS
        else:
            keys_valid = (
                edge_keys == _TARGET_CALL_GRAPH_BASE_EDGE_KEYS
                or edge_keys == _TARGET_CALL_GRAPH_SCOPED_ARITHMETIC_KEYS
                or edge_keys == _TARGET_CALL_GRAPH_LEGACY_BASE_EDGE_KEYS
                or edge_keys == _TARGET_CALL_GRAPH_LEGACY_SCOPED_ARITHMETIC_KEYS
            )
        if not keys_valid:
            failures.append(
                f"whole-file target call graph edge {index} keys are invalid"
            )
            continue

        caller = edge.get("caller")
        canonical_caller = edge.get("canonical_caller")
        callee = edge.get("callee")
        callee_kind = edge.get("callee_kind")
        domain = edge.get("canonical_domain")
        rule = edge.get("normalization_rule")
        scope = edge.get("guard_scope")
        subject = edge.get("guard_subject")
        canonical_subject = edge.get("canonical_guard_subject")
        identifier_mapping = identifier_by_raw.get(caller)
        valid = True
        legacy_non_javascript_edge = (
            target_language != "javascript"
            and "canonical_caller" not in edge
            and caller in manifest_symbols
        )
        if (
            not legacy_non_javascript_edge
            and (
                not isinstance(identifier_mapping, dict)
                or canonical_caller != identifier_mapping.get("canonical_symbol")
                or canonical_caller not in manifest_symbols
            )
            or not isinstance(callee, str)
            or not callee
            or not isinstance(rule, str)
            or rule not in normalization_set
        ):
            valid = False
        if operator == "guard":
            if (
                target_language not in {"javascript", "typescript"}
                or domain not in _TARGET_CALL_GRAPH_CANONICAL_TYPES
                or scope not in {"signature-parameter", "signature-return"}
                or not isinstance(subject, str)
                or not subject
                or (scope == "signature-return" and subject != "return")
                or not isinstance(canonical_subject, str)
                or not canonical_subject
                or (scope == "signature-return" and canonical_subject != "return")
                or callee_kind != "exact-generated-helper"
            ):
                valid = False
        else:
            if (
                domain not in {"integer", "number"}
                or operator not in _TARGET_CALL_GRAPH_ARITHMETIC_OPERATORS
            ):
                valid = False
            if edge_keys in {
                _TARGET_CALL_GRAPH_SCOPED_ARITHMETIC_KEYS,
                _TARGET_CALL_GRAPH_LEGACY_SCOPED_ARITHMETIC_KEYS,
            } and (
                scope not in {"arithmetic-result", "arithmetic-divisor"}
                or subject != operator
                or (scope == "arithmetic-divisor" and operator not in {"/", "%"})
            ):
                valid = False
        if not valid:
            failures.append(f"whole-file target call graph edge {index} is detached")
            continue
        if callee_kind == "exact-generated-helper":
            if callee not in helper_identifiers:
                failures.append(
                    f"whole-file target helper edge {index} is not inventory-bound"
                )
                continue
        elif callee_kind == "pinned-target-builtin":
            if callee in helper_identifiers:
                failures.append(
                    f"whole-file target builtin edge {index} aliases a helper"
                )
                continue
        else:
            failures.append(
                f"whole-file target call graph edge {index} callee kind is invalid"
            )
            continue
        valid_edges.append(edge)
        normalized_edges.append(_target_call_graph_sort_key(edge))

    if len(normalized_edges) != len(set(normalized_edges)):
        failures.append("whole-file target call graph contains duplicate edges")
    if [_target_call_graph_sort_key(edge) for edge in valid_edges] != sorted(
        _target_call_graph_sort_key(edge) for edge in valid_edges
    ):
        failures.append("whole-file target call graph edges are not canonical")

    if target_language not in {"javascript", "typescript"}:
        return
    if target_language == "javascript":
        expected_edges = _javascript_expected_target_call_graph_edges(
            raw_target_semantic_document,
            target_semantic_document,
            identifier_functions,
            failures,
        )
    else:
        expected_edges = _typescript_expected_target_call_graph_edges(
            raw_target_semantic_document,
            target_semantic_document,
            identifier_functions,
            failures,
        )
    expected_by_identity = {
        _target_call_graph_edge_identity(edge): edge for edge in expected_edges
    }
    observed_by_identity = {
        _target_call_graph_edge_identity(edge): edge for edge in valid_edges
    }
    target_language_label = {
        "javascript": "JavaScript",
        "typescript": "TypeScript",
    }[target_language]
    for identity in sorted(expected_by_identity.keys() - observed_by_identity.keys()):
        edge = expected_by_identity[identity]
        failures.append(
            f"whole-file {target_language_label} target call graph is missing exact edge "
            f"{edge['caller']}:{edge['guard_scope']}:{edge['guard_subject']}:"
            f"{edge['canonical_domain']}:{edge['canonical_operator']}"
        )
    for identity in sorted(observed_by_identity.keys() - expected_by_identity.keys()):
        edge = observed_by_identity[identity]
        failures.append(
            f"whole-file {target_language_label} target call graph contains unexpected edge "
            f"{edge['caller']}:{edge.get('guard_scope', 'operator')}:"
            f"{edge.get('guard_subject', '')}:{edge['canonical_domain']}:"
            f"{edge['canonical_operator']}"
        )


def _validate_module_whole_file_closure(
    *,
    manifest: dict[str, Any],
    module_manifest: dict[str, Any],
    module_input: dict[str, Any],
    source_semantic_document: dict[str, Any],
    target_semantic_document: dict[str, Any],
    identifier_closure: dict[str, Any],
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
    javascript_descriptor_record: tuple[dict[str, Any], Path, str] | None,
    role_records: dict[str, list[tuple[dict[str, Any], Path, str]]],
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
        or closure_document.get("kind") != "elmos.typed-pure-module-whole-file-closure"
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
        if (
            closure_document.get(f"{side}_inventory_bytes")
            != inventory_record[1].stat().st_size
        ):
            failures.append(
                f"whole-file-module-closure {side} inventory byte backlink mismatch"
            )
    if (
        closure_record is not None
        and module_input.get("whole_file_closure_sha256") != closure_record[2]
    ):
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
    manifest_symbols: list[str] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        symbol = entry.get("symbol")
        if isinstance(symbol, str):
            manifest_symbols.append(symbol)
    manifest_symbols.sort()
    if closure_document.get("manifest_symbols") != manifest_symbols:
        failures.append("whole-file closure manifest symbol set mismatch")
    helper_identifiers = {
        identifier
        for helper in closure_document.get("target_helper_symbols", [])
        if isinstance(helper, dict)
        for identifier in (helper.get("name"), helper.get("qualified_name"))
        if isinstance(identifier, str) and identifier
    }
    raw_target_ir = identifier_closure.get("raw_target_ir")
    raw_target_semantic_document = (
        raw_target_ir.to_mapping() if raw_target_ir is not None else {}
    )
    identifier_functions = identifier_closure.get("functions")
    if not isinstance(identifier_functions, list):
        identifier_functions = []
    _validate_target_call_graph(
        target_call_graph=closure_document.get("target_call_graph"),
        manifest_symbols=manifest_symbols,
        target_language=target_language,
        raw_target_semantic_document=raw_target_semantic_document,
        target_semantic_document=target_semantic_document,
        identifier_functions=identifier_functions,
        helper_identifiers=helper_identifiers,
        normalizations=closure_document.get("target_builtin_normalizations"),
        failures=failures,
    )
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
        raw_semantic_document=raw_target_semantic_document,
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
        javascript_descriptor_snapshot: Path | None = None
        javascript_descriptor_bytes: bytes | None = None
        javascript_descriptor_digest: str | None = None
        if javascript_descriptor_record is not None:
            javascript_descriptor_bytes = javascript_descriptor_record[1].read_bytes()
            javascript_descriptor_digest = str(
                javascript_descriptor_record[0].get("sha256")
            )
            if (
                sha256_bytes(javascript_descriptor_bytes)
                != javascript_descriptor_digest
                or javascript_descriptor_record[2] != javascript_descriptor_digest
                or len(javascript_descriptor_bytes)
                != javascript_descriptor_record[0].get("bytes")
            ):
                raise ValueError(
                    "JavaScript ESM descriptor changed before private snapshot"
                )
            javascript_descriptor_snapshot = _private_snapshot(
                snapshot_root,
                role="source",
                logical_name="package.json",
                content=javascript_descriptor_bytes,
            )
            if javascript_descriptor_snapshot.parent != source_snapshot.parent:
                raise ValueError(
                    "JavaScript ESM descriptor snapshot is detached from source"
                )
    except (OSError, ValueError) as exc:
        failures.append(f"module private artifact snapshot failed: {exc}")
        return
    closure_api = _engine_module_closure_api(failures, "module whole-file closure")
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
        target_ir_view,
        alpha_normalize_target,
    ) = closure_api
    try:
        persisted_source_ir = SemanticIR.from_mapping(source_semantic_document)
        persisted_target_ir = SemanticIR.from_mapping(target_semantic_document)
        plan_record_list = role_records.get("identifier-plan", [])
        plan_record = plan_record_list[0] if plan_record_list else None
        if plan_record is not None:
            identifier_api = _engine_identifier_api(failures, "module identifier replay")
            if identifier_api is not None:
                _, IdentifierPlan_cls, _, _, _, _, _, _ = identifier_api
                identifier_plan = IdentifierPlan_cls.from_mapping(load(plan_record[1]))
            else:
                identifier_plan = identifier_closure.get("plan")
        else:
            identifier_plan = identifier_closure.get("plan")
        fresh_source_ir = combine_function_irs(
            [
                analyze(source_snapshot, source_language, symbol)
                for symbol in manifest_symbols
            ],
            manifest_symbols,
            source_language,
            "source-validator-replay",
        )
        if identifier_plan is not None:
            fresh_target_view = target_ir_view(fresh_source_ir, identifier_plan)
            raw_target_symbols = [function.name for function in fresh_target_view.functions]
        else:
            raw_target_symbols = manifest_symbols
        fresh_raw_target_ir = combine_function_irs(
            [
                analyze(
                    target_snapshot,
                    target_language,
                    symbol,
                    emitted_target=True,
                )
                for symbol in raw_target_symbols
            ],
            raw_target_symbols,
            target_language,
            "target-validator-replay",
        )
        if identifier_plan is not None:
            fresh_target_ir = alpha_normalize_target(
                fresh_source_ir,
                fresh_raw_target_ir,
                identifier_plan,
            )
            fresh_emitted = emit(
                fresh_source_ir,
                target_language,
                identifier_plan=identifier_plan,
            )
        else:
            fresh_target_ir = fresh_raw_target_ir
            fresh_emitted = None
    except Exception as exc:
        failures.append(
            f"module independent semantic re-lift/emitter replay failed: {exc}"
        )
        return
    if fresh_source_ir.to_mapping() != persisted_source_ir.to_mapping():
        failures.append(
            "source-module-semantic-ir differs from independent source analysis"
        )
    persisted_raw_target_ir = identifier_closure.get("raw_target_ir")
    if (
        persisted_raw_target_ir is not None
        and fresh_raw_target_ir.to_mapping() != persisted_raw_target_ir.to_mapping()
    ):
        failures.append("raw-target-ir differs from independent target re-lift")
    if fresh_target_ir.to_mapping() != persisted_target_ir.to_mapping():
        failures.append(
            "target-module-semantic-ir differs from independent target re-lift"
        )
    if fresh_emitted is not None:
        if fresh_emitted.relative_path != module_input.get("target_logical_file"):
            failures.append("module deterministic emitter target path differs")
        if fresh_emitted.content.encode("utf-8") != target_bytes:
            failures.append("module deterministic emitter target bytes differ")
        if list(fresh_emitted.normalization_rules) != closure_document.get(
            "target_builtin_normalizations"
        ):
            failures.append("module deterministic emitter normalizations differ")
    try:
        fresh_source_inventory = inventory_module(source_snapshot, source_language)
        fresh_target_inventory = inventory_module(target_snapshot, target_language)
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
            raw_target_ir=fresh_raw_target_ir,
            target_ir=fresh_target_ir,
            identifier_plan=identifier_plan,
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
        if (
            javascript_descriptor_record is not None
            and javascript_descriptor_snapshot is not None
            and javascript_descriptor_bytes is not None
            and javascript_descriptor_digest is not None
        ):
            _validate_snapshot_stability(
                label="module JavaScript ESM descriptor",
                origin=javascript_descriptor_record[1],
                snapshot=javascript_descriptor_snapshot,
                expected_bytes=javascript_descriptor_bytes,
                expected_digest=javascript_descriptor_digest,
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
    target_functions = {
        source_function.name: target_function
        for source_function, target_function in zip(
            fresh_source_ir.functions,
            fresh_target_view.functions,
            strict=True,
        )
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
                    target_functions[symbol],
                    cases,
                    replay_root / "target" / f"{index:03d}",
                )
    except Exception as exc:
        failures.append(f"module independent native behavior replay failed: {exc}")
        return

    def stable_source_validation_projection(
        document: dict[str, Any],
    ) -> dict[str, Any]:
        """Remove only the diagnostic host path from source replay evidence."""

        projected: dict[str, Any] = {}
        for symbol, validation in document.items():
            if not isinstance(validation, dict):
                projected[symbol] = validation
                continue
            projected[symbol] = {
                key: value
                for key, value in validation.items()
                if key != "javascript_esm_descriptor_observation"
            }
        return projected

    if javascript_descriptor_record is not None:
        expected_snapshot_origin = (
            str(javascript_descriptor_snapshot)
            if javascript_descriptor_snapshot is not None
            else None
        )
        for symbol, validation in fresh_source_validation.items():
            observation = validation.get("javascript_esm_descriptor_observation")
            if observation != {"observed_origin_path": expected_snapshot_origin}:
                failures.append(
                    f"fresh source validation {symbol} JavaScript ESM descriptor "
                    "observation is not bound to the private snapshot"
                )
        for symbol, validation in source_validation_document.items():
            observation = (
                validation.get("javascript_esm_descriptor_observation")
                if isinstance(validation, dict)
                else None
            )
            observed_origin = (
                observation.get("observed_origin_path")
                if isinstance(observation, dict)
                else None
            )
            if (
                not isinstance(observation, dict)
                or set(observation) != JAVASCRIPT_ESM_DESCRIPTOR_OBSERVATION_KEYS
                or not isinstance(observed_origin, str)
                or not Path(observed_origin).is_absolute()
                or Path(observed_origin).name != "package.json"
            ):
                failures.append(
                    f"persisted source validation {symbol} JavaScript ESM descriptor "
                    "observation is invalid"
                )
    elif any(
        isinstance(validation, dict)
        and "javascript_esm_descriptor_observation" in validation
        for validation in source_validation_document.values()
    ):
        failures.append(
            "source-module-validation has an unexpected JavaScript ESM descriptor observation"
        )

    if stable_source_validation_projection(
        fresh_source_validation
    ) != stable_source_validation_projection(source_validation_document):
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
    if (
        javascript_descriptor_record is not None
        and javascript_descriptor_snapshot is not None
        and javascript_descriptor_bytes is not None
        and javascript_descriptor_digest is not None
    ):
        _validate_snapshot_stability(
            label="module JavaScript ESM descriptor",
            origin=javascript_descriptor_record[1],
            snapshot=javascript_descriptor_snapshot,
            expected_bytes=javascript_descriptor_bytes,
            expected_digest=javascript_descriptor_digest,
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
    expected_input_domain_value = manifest.get("profiles", {}).get("input_domain")
    expected_input_domain = (
        expected_input_domain_value
        if isinstance(expected_input_domain_value, str)
        else ""
    )
    expected_out_of_domain_behavior = (
        NODEJS_OUT_OF_DOMAIN_BEHAVIOR
        if expected_input_domain == NODEJS_INPUT_DOMAIN
        else SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
    )
    try:
        expected_module_types = set(
            load(route / "mappings" / "types.json").get("types", [])
        )
    except Exception:
        expected_module_types = set()
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
        item
        for item in artifacts_by_path.values()
        if item[0].get("role") == "module-formal-input"
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
            failures.append(
                "non-passing module evidence cannot bind a Swift analyzer receipt"
            )
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
            failures.append(
                "passed module evidence must bind exactly one module formal input"
            )
        elif (
            module_input_digest is not None
            and module_inputs[0][2] != module_input_digest
        ):
            failures.append("module_input_sha256 does not bind module-formal-input")
        module_input = evidence.get("module_input")
        if not isinstance(module_input, dict):
            failures.append("passed module evidence must include module_input")
        else:
            if canonical_json_sha256(module_input) != module_input_digest:
                failures.append(
                    "module_input_sha256 is not the canonical module_input digest"
                )
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
                "source-javascript-esm-descriptor",
                "swift-analyzer-build-receipt",
            }
            for role in sorted(single_roles):
                if len(role_records.get(role, [])) != 1:
                    failures.append(
                        f"passed module evidence must bind exactly one {role}"
                    )
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
            if module_input.get("input_domain") != expected_input_domain:
                failures.append("module_input input domain drift")
            source_records = role_records.get("original-source-module-artifact", [])
            if (
                len(source_records) == 1
                and module_input.get("source_logical_file") != source_records[0][1].name
            ):
                failures.append("module_input source_logical_file drift")
            target_records = role_records.get("emitted-target-module-artifact", [])
            if (
                len(target_records) == 1
                and module_input.get("target_logical_file") != target_records[0][1].name
            ):
                failures.append("module_input target_logical_file drift")
            count_bindings = (
                ("original-source-module-artifact", "source_artifact_byte_count"),
                ("emitted-target-module-artifact", "target_artifact_byte_count"),
                ("source-module-inventory", "source_inventory_byte_count"),
                ("target-module-inventory", "target_inventory_byte_count"),
            )
            for role, field in count_bindings:
                records = role_records.get(role, [])
                if (
                    len(records) == 1
                    and module_input.get(field) != records[0][1].stat().st_size
                ):
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
                    if canonical_json_sha256(semantic_document) != module_input.get(
                        field
                    ):
                        failures.append(f"module_input.{field} does not bind {role}")
                    side = "source" if role.startswith("source-") else "target"
                    expected_language = manifest.get(side, {}).get("language")
                    expected_logical_file = module_input.get(f"{side}_logical_file")
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
                        failures.append(
                            f"{role} source_file does not bind module artifact"
                        )
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
                        failures.append(
                            f"module case manifest schema validation crashed: {exc}"
                        )

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
                    loaded_module_cases: dict[str, Any] | None = load(
                        case_records[0][1]
                    )
                except Exception:
                    loaded_module_cases = None
                if loaded_module_cases is not None:
                    module_cases = loaded_module_cases

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
        if isinstance(item, dict) and isinstance(item.get("symbol"), str)
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
    closure_record = next(iter(role_records.get("whole-file-module-closure", [])), None)
    javascript_descriptor_record = _validate_module_javascript_esm_descriptor(
        manifest=manifest,
        evidence=evidence,
        module_input=(
            evidence.get("module_input")
            if isinstance(evidence.get("module_input"), dict)
            else {}
        ),
        role_records=role_records,
        source_artifact_record=source_artifact_record,
        failures=failures,
    )
    identifier_closure: dict[str, Any] = {}
    if evidence.get("status") == "PASSED":
        identifier_closure = _validate_module_identifier_closure(
            manifest=manifest,
            evidence=evidence,
            module_input=(
                evidence.get("module_input")
                if isinstance(evidence.get("module_input"), dict)
                else {}
            ),
            closure_document=whole_file_closure_document,
            role_records=role_records,
            source_semantic_document=source_semantic_document,
            target_semantic_document=target_semantic_document,
            source_inventory_document=source_inventory_document,
            target_inventory_document=target_inventory_document,
            minimum_functions=int(minimum_functions),
            failures=failures,
        )
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
            identifier_closure=identifier_closure,
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
            javascript_descriptor_record=javascript_descriptor_record,
            role_records=role_records,
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
                    if symbol not in typed_source_by_symbol or not isinstance(
                        cases, list
                    ):
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
                    failures.append(
                        f"module function {symbol} {layer_name} did not pass"
                    )
            entry = manifest_by_symbol.get(symbol)
            cases = entry.get("cases") if isinstance(entry, dict) else None
            source_function = semantic_functions.get("source", {}).get(symbol)
            target_function = semantic_functions.get("target", {}).get(symbol)
            if source_function is None or target_function is None:
                failures.append(
                    f"module function {symbol} is absent from bound semantic IR"
                )
                continue
            expected_signature = (
                entry.get("signature") if isinstance(entry, dict) else None
            )
            if function.get("signature") != expected_signature:
                failures.append(
                    f"module function {symbol} signature differs from manifest"
                )
            semantic_signature = {
                "parameters": [
                    {"name": item.get("name"), "type": item.get("type")}
                    for item in source_function.get("parameters", [])
                    if isinstance(item, dict)
                ],
                "return_type": source_function.get("return_type"),
            }
            if expected_signature != semantic_signature:
                failures.append(
                    f"module function {symbol} signature differs from semantic IR"
                )
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
                    failures.append(
                        f"module function {symbol} formal property is not proved"
                    )
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
                    module_identifier_hygiene=evidence.get("identifier_hygiene"),
                    input_domain=expected_input_domain,
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
                failures.append(
                    f"module_contract.{field} does not match function symbols"
                )
        if contract.get("exact_profile_symbol_set") is not True:
            failures.append("module exact_profile_symbol_set is not true")
        if contract.get("exact_generated_helper_symbol_set") is not True:
            failures.append("module exact_generated_helper_symbol_set is not true")
        if contract.get("exact_profile_signature_set") is not True:
            failures.append("module exact_profile_signature_set is not true")
        closure_records = role_records.get("whole-file-module-closure", [])
        if (
            len(closure_records) == 1
            and contract.get("whole_file_closure_sha256") != closure_records[0][2]
        ):
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
            closure_profile = whole_file_closure_document.get(f"{side}_profile_symbols")
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
        if composition.get("input_domain") != expected_input_domain:
            failures.append("module composition input domain drift")
        if (
            composition.get("out_of_domain_arithmetic_behavior")
            != expected_out_of_domain_behavior
        ):
            failures.append("module composition out-of-domain boundary drift")
        if composition.get("original_source_bytes_theorem") is not False:
            failures.append("module composition overstates original-source theorem")
        if composition.get("source_compiler_runtime_soundness") != "NOT_RUN":
            failures.append(
                "module source compiler/runtime soundness must remain NOT_RUN"
            )
        if composition.get("target_compiler_runtime_soundness") != "NOT_RUN":
            failures.append(
                "module target compiler/runtime soundness must remain NOT_RUN"
            )
        if composition.get("proof_strength") != "COMPOSED_THEOREMS_UNDER_ASSUMPTIONS":
            failures.append(
                "module composition proof strength is overstated or invalid"
            )
        if composition.get("analyzer_and_emitter_soundness") != "ASSUMPTION":
            failures.append(
                "module analyzer/emitter soundness boundary must remain ASSUMPTION"
            )
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
        if observed_types != expected_module_types:
            failures.append(
                "module signatures do not cover the exact route type mapping"
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
                        if function.get(
                            "case_manifest_sha256"
                        ) != canonical_json_sha256(entry.get("cases")):
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
    identifier_api = _engine_identifier_api(
        failures, "specialized function native replay identifier closure"
    )
    if replay_api is None or domain_api is None or identifier_api is None:
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
        target_ir_view,
        alpha_normalize_target,
    ) = replay_api
    _, enforce_semantic_domain, enforce_case_domain = domain_api
    (
        _IdentifierSemanticIR,
        IdentifierPlan,
        validate_identifier_plan,
        _identifier_alpha_normalize_target,
        _identifier_plan_bytes,
        _identifier_target_ir_view,
        standalone_artifact_unit_namespace,
        _bind_function_spans_from_inventory,
    ) = identifier_api
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
                    raise ValueError(
                        "route corpus differs from byte-bound certified inputs"
                    )
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
                source_ir = analyze(source_snapshot, source_language, function_name)
                if len(source_ir.functions) != 1:
                    raise ValueError(
                        "source analysis must contain exactly one function"
                    )
                source_function = source_ir.functions[0]
                enforce_semantic_domain(source_ir, source_language, target_language)
                enforce_case_domain(
                    source_function, cases, source_language, target_language
                )
                artifact_root = route / "certification" / "artifacts" / corpus
                identifier_hygiene = persisted.get("identifier_hygiene")
                if (
                    not isinstance(identifier_hygiene, dict)
                    or identifier_hygiene.get("status") != "PASSED"
                ):
                    raise ValueError("persisted identifier hygiene is not passed")
                identifier_plan_path = _resolve_below(
                    artifact_root,
                    identifier_hygiene.get("plan_path"),
                    f"specialized {corpus} identifier plan",
                    failures,
                )
                if identifier_plan_path is None:
                    raise ValueError("persisted identifier plan path is invalid")
                identifier_plan = IdentifierPlan.from_mapping(
                    load(identifier_plan_path)
                )
                try:
                    validate_identifier_plan(
                        source_ir,
                        identifier_plan,
                        expected_unit_namespace=standalone_artifact_unit_namespace(
                            source_path.name,
                            source_digest,
                        ),
                    )
                except Exception as exc:
                    raise ValueError(
                        "identifier plan is detached from fresh source analysis"
                    ) from exc
                if sha256_file(identifier_plan_path) != identifier_hygiene.get(
                    "plan_sha256"
                ):
                    raise ValueError("persisted identifier plan digest is invalid")
                target_view = target_ir_view(source_ir, identifier_plan)
                if len(target_view.functions) != 1:
                    raise ValueError(
                        "identifier target view must contain exactly one function"
                    )
                emitted = emit(
                    source_ir,
                    target_language,
                    identifier_plan=identifier_plan,
                )
                target_artifact = artifact_root / emitted.relative_path
                if not target_artifact.is_file() or target_artifact.is_symlink():
                    raise ValueError("persisted target artifact is missing or unsafe")
                target_bytes = target_artifact.read_bytes()
                target_digest = sha256_bytes(target_bytes)
                if (
                    persisted_target_artifact.get("path") != emitted.relative_path
                    or persisted_target_artifact.get("sha256") != target_digest
                ):
                    raise ValueError(
                        "persisted target runtime artifact binding is invalid"
                    )
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
                    target_view.functions[0].name,
                    emitted_target=True,
                )
                if len(target_ir.functions) != 1:
                    raise ValueError("target re-lift must contain exactly one function")
                target_ir = alpha_normalize_target(
                    source_ir,
                    target_ir,
                    identifier_plan,
                )
                enforce_semantic_domain(target_ir, source_language, target_language)

                semantic_report = persisted.get("semantic_equivalence")
                if not isinstance(semantic_report, dict):
                    raise ValueError(
                        "persisted semantic-equivalence binding is missing"
                    )
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
                if sha256_file(source_ir_record) != semantic_report.get(
                    "source_ir_sha256"
                ) or sha256_file(target_ir_record) != semantic_report.get(
                    "target_ir_sha256"
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
                    target_view.functions[0],
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
            {f"SPECIALIZED_NUMBER_ARITHMETIC_UNSUPPORTED:{route_key}:addNumber"}
        ),
        "specialized-non-finite-case-unsupported": frozenset(
            {f"SPECIALIZED_CASE_NON_FINITE_NUMBER_UNSUPPORTED:{route_key}:echoNumber:0"}
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
            if (
                not isinstance(observed_reason, str)
                or observed_reason not in expected_reasons
            ):
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
                failures.append(
                    f"{item_label}.input_refs paths cannot be derived: {exc}"
                )
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
                        raise ValueError("development function_name is missing")
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
                        raise ValueError(
                            "origin is no longer a regular non-symlink file"
                        )
                    if snapshot.is_symlink() or not stat.S_ISREG(
                        snapshot.lstat().st_mode
                    ):
                        raise ValueError(
                            "snapshot is no longer a regular non-symlink file"
                        )
                except Exception as exc:
                    failures.append(f"{item_label}.{role} file identity drift: {exc}")

    try:
        if negative_path.read_bytes() != negative_bytes:
            failures.append("specialized negative evidence changed during replay")
        if negative_path.is_symlink() or not stat.S_ISREG(
            negative_path.lstat().st_mode
        ):
            failures.append(
                "specialized negative evidence file identity changed during replay"
            )
    except OSError as exc:
        failures.append(
            f"specialized negative evidence final stability check failed: {exc}"
        )
    provenance_after = _runtime_provenance(
        failures, f"specialized negative replay {route_key} after execution"
    )
    if provenance_after is not None and provenance_after != provenance_before:
        failures.append(
            "specialized negative replay runtime provenance changed during execution"
        )


def nodejs_negative_expected_reasons(
    *,
    route_key: str,
    source_language: str,
    case_id: str,
    development_function: str,
) -> frozenset[str]:
    """Return every exact stable error string allowed for one Node negative."""

    if case_id in NODEJS_NEGATIVE_ANALYZE_SOURCE_FILES:
        return NODEJS_NEGATIVE_REASON_CODES[case_id]
    if case_id == "nodejs-commonjs-unsupported":
        return frozenset({"JAVASCRIPT_CJS_SOURCE_BLOCKED"})
    if case_id in NODEJS_GENERATED_NEGATIVE_SPECS:
        _, _, function_name, reason_code = NODEJS_GENERATED_NEGATIVE_SPECS[case_id]
        if source_language == "python" and case_id in {
            "nodejs-division-by-zero-unsupported",
            "nodejs-modulo-by-zero-unsupported",
        }:
            return frozenset(
                {
                    {
                        "nodejs-division-by-zero-unsupported": (
                            "PYTHON_TRUE_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET"
                        ),
                        "nodejs-modulo-by-zero-unsupported": (
                            "PYTHON_FLOORED_MODULO_OUTSIDE_CERTIFIED_SUBSET"
                        ),
                    }[case_id]
                }
            )
        if case_id in {
            "nodejs-number-arithmetic-unsupported",
            "nodejs-string-semantics-unsupported",
        }:
            return frozenset({f"{reason_code}:{route_key}:{function_name}"})
        if case_id in {
            "nodejs-unsafe-integer-intermediate-boolean-unsupported",
            "nodejs-unsafe-integer-intermediate-integer-unsupported",
            "nodejs-unsafe-integer-intermediate-number-unsupported",
        }:
            return frozenset({f"{reason_code}:{route_key}:{function_name}:0"})
        canonical_error = {
            "nodejs-division-by-zero-unsupported": "DivideByZero",
            "nodejs-modulo-by-zero-unsupported": "DivideByZero",
            "nodejs-integer-overflow-unsupported": "IntegerOverflow",
        }[case_id]
        return frozenset(
            {f"{reason_code}:{route_key}:{function_name}:0:{canonical_error}"}
        )
    if case_id == "nodejs-non-finite-case-unsupported":
        return frozenset(
            {
                "NODEJS_CASE_NON_FINITE_NUMBER_UNSUPPORTED:"
                f"{route_key}:{development_function}:0"
            }
        )
    if case_id == "nodejs-unsafe-integer-case-unsupported":
        return frozenset(
            {
                "NODEJS_CASE_UNSAFE_INTEGER_UNSUPPORTED:"
                f"{route_key}:{development_function}:0:subtotal"
            }
        )
    if case_id == "nodejs-unsafe-integer-result-unsupported":
        return frozenset(
            {
                "NODEJS_CASE_UNSAFE_INTEGER_RESULT_UNSUPPORTED:"
                f"{route_key}:{development_function}:0"
            }
        )
    if case_id == "nodejs-typescript-integer-contract-unsupported":
        return frozenset(
            {
                (
                    "NODEJS_TYPESCRIPT_INTEGER_EVIDENCE_UNAVAILABLE:"
                    f"{route_key}:integerContract"
                )
                if source_language == "javascript"
                else "PURE_MODULE_CASE_MANIFEST_SIGNATURE_MISMATCH:integerContract"
            }
        )
    if case_id == "undeclared-directed-route-fails-closed":
        return frozenset({"SOURCE_AND_TARGET_MUST_DIFFER"})
    if case_id == "missing-symbol-fails-closed":
        return frozenset(
            {
                "NO_SUPPORTED_FUNCTIONS"
                if source_language in {"java", "swift"}
                else "FUNCTION_NOT_FOUND:__elmos_missing_function__"
            }
        )
    return frozenset()


def _nodejs_negative_expected_paths(
    *,
    source_language: str,
    case_id: str,
    development_source_path: str,
    development_suffix: str,
) -> tuple[str, ...]:
    """Return the exact route-local inputs for one Node negative case."""

    prefix = "corpus/negative/"
    analyzer_filename = NODEJS_NEGATIVE_ANALYZE_SOURCE_FILES.get(case_id)
    if analyzer_filename is not None:
        return (prefix + analyzer_filename,)
    if case_id == "nodejs-commonjs-unsupported":
        return prefix + "commonjs_module.cjs", prefix + "commonjs_cases.json"
    generated = NODEJS_GENERATED_NEGATIVE_SPECS.get(case_id)
    if generated is not None:
        stem, java_class, _, _ = generated
        filename = (
            f"{java_class}.java"
            if source_language == "java"
            else f"{stem}.{NODEJS_NEGATIVE_SOURCE_EXTENSIONS[source_language]}"
        )
        return prefix + filename, prefix + f"{stem}_cases.json"
    if case_id in {
        "nodejs-non-finite-case-unsupported",
        "nodejs-unsafe-integer-case-unsupported",
        "nodejs-unsafe-integer-result-unsupported",
    }:
        cases_filename = {
            "nodejs-non-finite-case-unsupported": "non_finite_number_cases.json",
            "nodejs-unsafe-integer-case-unsupported": "unsafe_integer_cases.json",
            "nodejs-unsafe-integer-result-unsupported": (
                "unsafe_integer_result_cases.json"
            ),
        }[case_id]
        return development_source_path, prefix + cases_filename
    if case_id == "nodejs-typescript-integer-contract-unsupported":
        return (
            prefix
            + "typescript_integer_contract."
            + ("mjs" if source_language == "javascript" else "ts"),
            prefix + "typescript_integer_contract_cases.json",
        )
    if case_id == "undeclared-directed-route-fails-closed":
        return (
            prefix + "undeclared_java_to_java.java",
            prefix + "undeclared_java_to_java_cases.json",
        )
    if case_id == "missing-symbol-fails-closed":
        return (
            prefix + "missing_symbol_source" + development_suffix,
            prefix + "missing_symbol_cases.json",
        )
    raise ValueError(f"undeclared Node.js negative case: {case_id}")


def _replay_nodejs_negative_cases(
    *,
    route: Path,
    route_key: str,
    source_language: str,
    target_language: str,
    expected_case_ids: tuple[str, ...],
    cases: list[Any],
    development_source_path: str,
    development_suffix: str,
    development_function: str,
    failures: list[str],
) -> None:
    """Replay every Node negative from private byte-bound snapshots."""

    api = _engine_negative_replay_api(failures, f"Node.js negative replay {route_key}")
    if api is None:
        return
    migrate, migrate_module, analyze, RouteError = api
    provenance_before = _runtime_provenance(
        failures, f"Node.js negative replay {route_key} before execution"
    )
    if provenance_before is None:
        return

    with tempfile.TemporaryDirectory(
        prefix=f"elmos-nodejs-negative-replay-{route_key}-"
    ) as temporary:
        replay_root = Path(temporary)
        replay_root.chmod(0o700)
        for index, item in enumerate(cases):
            label = f"Node.js negative cases[{index}]"
            if not isinstance(item, dict):
                continue
            case_id = item.get("case_id")
            if not isinstance(case_id, str) or case_id not in expected_case_ids:
                continue
            expected_roles = NODEJS_NEGATIVE_INPUT_ROLES.get(case_id)
            input_refs = item.get("input_refs")
            if expected_roles is None or not isinstance(input_refs, list):
                continue
            try:
                expected_paths = _nodejs_negative_expected_paths(
                    source_language=source_language,
                    case_id=case_id,
                    development_source_path=development_source_path,
                    development_suffix=development_suffix,
                )
            except ValueError:
                continue
            if len(input_refs) != len(expected_roles):
                continue

            case_root = replay_root / f"{index:03d}-{case_id}"
            case_root.mkdir(mode=0o700)
            snapshots: dict[str, Path] = {}
            bound_inputs: list[tuple[str, Path, Path, bytes, str]] = []
            inputs_valid = True
            for input_index, (role, expected_path, reference) in enumerate(
                zip(expected_roles, expected_paths, input_refs, strict=True)
            ):
                input_label = f"{label}.input_refs[{input_index}]"
                if not isinstance(reference, dict) or set(reference) != {
                    "role",
                    "path",
                    "sha256",
                    "bytes",
                }:
                    inputs_valid = False
                    continue
                if (
                    reference.get("role") != role
                    or reference.get("path") != expected_path
                ):
                    inputs_valid = False
                    continue
                origin = _resolve_below(
                    route,
                    expected_path,
                    f"{input_label}.path",
                    failures,
                )
                if origin is None:
                    inputs_valid = False
                    continue
                try:
                    origin_stat = origin.lstat()
                    if origin.is_symlink() or not stat.S_ISREG(origin_stat.st_mode):
                        raise ValueError("not a regular non-symlink file")
                    content = origin.read_bytes()
                except (OSError, ValueError) as exc:
                    failures.append(f"{input_label} cannot be snapshotted: {exc}")
                    inputs_valid = False
                    continue
                digest = sha256_bytes(content)
                byte_count = reference.get("bytes")
                if (
                    reference.get("sha256") != digest
                    or not isinstance(byte_count, int)
                    or isinstance(byte_count, bool)
                    or byte_count != len(content)
                    or not content
                ):
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

            output = case_root / "engine-output-must-not-exist"
            fresh_reason: str | None = None
            try:
                if case_id in NODEJS_NEGATIVE_ANALYZE_FUNCTIONS:
                    analyze(
                        snapshots["source"],
                        "javascript",
                        NODEJS_NEGATIVE_ANALYZE_FUNCTIONS[case_id],
                    )
                elif case_id == "nodejs-commonjs-unsupported":
                    counterpart = (
                        target_language
                        if source_language == "javascript"
                        else source_language
                    )
                    migrate(
                        snapshots["source"],
                        "javascript",
                        counterpart,
                        "commonJsValue",
                        snapshots["cases"],
                        output,
                    )
                elif case_id in NODEJS_GENERATED_NEGATIVE_SPECS:
                    migrate(
                        snapshots["source"],
                        source_language,
                        target_language,
                        NODEJS_GENERATED_NEGATIVE_SPECS[case_id][2],
                        snapshots["cases"],
                        output,
                    )
                elif case_id in {
                    "nodejs-non-finite-case-unsupported",
                    "nodejs-unsafe-integer-case-unsupported",
                    "nodejs-unsafe-integer-result-unsupported",
                }:
                    migrate(
                        snapshots["source"],
                        source_language,
                        target_language,
                        development_function,
                        snapshots["cases"],
                        output,
                    )
                elif case_id == "nodejs-typescript-integer-contract-unsupported":
                    migrate_module(
                        snapshots["source-module"],
                        source_language,
                        target_language,
                        snapshots["case-manifest"],
                        output,
                    )
                elif case_id == "undeclared-directed-route-fails-closed":
                    migrate_module(
                        snapshots["source-module"],
                        "java",
                        "java",
                        snapshots["case-manifest"],
                        output,
                    )
                elif case_id == "missing-symbol-fails-closed":
                    migrate(
                        snapshots["source"],
                        source_language,
                        target_language,
                        "__elmos_missing_function__",
                        snapshots["cases"],
                        output,
                    )
                else:
                    failures.append(f"{label} has no replay implementation")
                    continue
            except Exception as exc:
                if type(exc) is not RouteError:
                    failures.append(
                        f"{label} raised unexpected exception type "
                        f"{type(exc).__module__}.{type(exc).__qualname__}: {exc}"
                    )
                else:
                    fresh_reason = _nodejs_stable_route_error(str(exc))
            else:
                failures.append(f"{label} unexpectedly passed fresh replay")
            if output.exists():
                failures.append(f"{label} created an output/artifact directory")

            expected_reasons = nodejs_negative_expected_reasons(
                route_key=route_key,
                source_language=source_language,
                case_id=case_id,
                development_function=development_function,
            )
            if fresh_reason is not None:
                if fresh_reason not in expected_reasons:
                    failures.append(
                        f"{label} fresh RouteError reason is not exact: {fresh_reason}"
                    )
                if fresh_reason != item.get("observed_reason"):
                    failures.append(
                        f"{label} observed_reason differs from fresh replay: "
                        f"{item.get('observed_reason')!r} != {fresh_reason!r}"
                    )
            for role, origin, snapshot, content, digest in bound_inputs:
                _validate_snapshot_stability(
                    label=f"{label}.{role}",
                    origin=origin,
                    snapshot=snapshot,
                    expected_bytes=content,
                    expected_digest=digest,
                    failures=failures,
                )

    provenance_after = _runtime_provenance(
        failures, f"Node.js negative replay {route_key} after execution"
    )
    if provenance_after is not None and provenance_after != provenance_before:
        failures.append(
            "Node.js negative replay runtime provenance changed during execution"
        )


def validate_nodejs_negative_evidence(
    route: Path,
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    failures: list[str],
) -> None:
    """Validate the exact, byte-bound Node.js negative corpus."""

    from route_sets import nodejs_negative_case_ids

    route_key = manifest.get("route_key")
    source_language = manifest.get("source", {}).get("language")
    target_language = manifest.get("target", {}).get("language")
    if not all(
        isinstance(value, str) and value
        for value in (route_key, source_language, target_language)
    ):
        failures.append("Node.js negative route identity is invalid")
        return
    try:
        expected_case_ids = nodejs_negative_case_ids(
            source_language,
            target_language,
        )
    except ValueError as exc:
        failures.append(str(exc))
        return
    references = evidence.get("negative_runs")
    if references != ["certification/local-negative-evidence.json"]:
        failures.append("Node.js negative evidence reference is not exact")
        return
    negative_path = route / "certification" / "local-negative-evidence.json"
    try:
        result = load(negative_path)
    except Exception as exc:
        failures.append(f"Node.js negative evidence is unreadable: {exc}")
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
        failures.append("Node.js negative evidence top-level keys are not exact")
    if (
        result.get("schema_version") != 1
        or result.get("route") != route_key
        or result.get("status") != "PASSED"
        or result.get("expected_result") != "BLOCKED"
        or result.get("test_integrity") != "PRESERVED"
        or result.get("independent_verifier") != "NOT_RUN"
        or result.get("external_certification") != "NOT_RUN"
    ):
        failures.append("Node.js negative evidence boundary is invalid")

    manifest_path = route / "corpus" / "negative" / "manifest.json"
    try:
        negative_manifest = load(manifest_path)
    except Exception as exc:
        failures.append(f"Node.js negative manifest is unreadable: {exc}")
        negative_manifest = {}
    if negative_manifest != {
        "schema_version": 1,
        "route_key": route_key,
        "case_ids": list(expected_case_ids),
        "independent": True,
        "rule_authoring_input": False,
        "expected_result": "BLOCKED",
    }:
        failures.append("Node.js negative manifest contract is invalid")

    cases = result.get("cases")
    if not isinstance(cases, list):
        failures.append("Node.js negative cases are missing")
        return
    observed_case_ids = [
        item.get("case_id") if isinstance(item, dict) else None for item in cases
    ]
    if observed_case_ids != list(expected_case_ids):
        failures.append("Node.js negative case order/set is not exact")
    if len(observed_case_ids) != len(set(observed_case_ids)):
        failures.append("Node.js negative case IDs are duplicated")

    try:
        development_manifest = load(route / "corpus" / "development" / "manifest.json")
    except Exception as exc:
        failures.append(f"Node.js development manifest is unreadable: {exc}")
        development_manifest = {}
    development_source = development_manifest.get("source_file")
    development_source_path = (
        f"corpus/development/{development_source}"
        if isinstance(development_source, str) and development_source
        else ""
    )
    development_suffix = (
        Path(development_source).suffix
        if isinstance(development_source, str) and development_source
        else ""
    )
    development_function = development_manifest.get("function_name")
    if not isinstance(development_function, str) or not development_function:
        failures.append("Node.js development function identity is invalid")
        development_function = ""

    for index, item in enumerate(cases):
        label = f"Node.js negative cases[{index}]"
        if not isinstance(item, dict):
            failures.append(f"{label} must be an object")
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
            failures.append(f"{label} keys are not exact")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or case_id not in expected_case_ids:
            failures.append(f"{label}.case_id is not declared for this route")
            continue
        if (
            item.get("status") != "PASSED"
            or item.get("expected_result") != "BLOCKED"
            or item.get("native_analysis") != "EXECUTED"
            or item.get("target_execution") != "NOT_REACHED_BY_DESIGN"
        ):
            failures.append(f"{label} did not preserve fail-closed status")
        reason = item.get("observed_reason")
        expected_reasons = nodejs_negative_expected_reasons(
            route_key=route_key,
            source_language=source_language,
            case_id=case_id,
            development_function=development_function,
        )
        if not isinstance(reason, str) or reason not in expected_reasons:
            failures.append(f"{label}.observed_reason is not exact")

        roles = NODEJS_NEGATIVE_INPUT_ROLES.get(case_id)
        if roles is None:
            failures.append(f"{label}.input_refs roles are undeclared")
            continue
        try:
            expected_paths = _nodejs_negative_expected_paths(
                source_language=source_language,
                case_id=case_id,
                development_source_path=development_source_path,
                development_suffix=development_suffix,
            )
        except ValueError as exc:
            failures.append(f"{label}.input_refs paths cannot be derived: {exc}")
            continue
        input_refs = item.get("input_refs")
        if not isinstance(input_refs, list) or len(input_refs) != len(roles):
            failures.append(f"{label}.input_refs count is invalid")
            continue
        for ref_index, (role, expected_path, reference) in enumerate(
            zip(roles, expected_paths, input_refs, strict=True)
        ):
            ref_label = f"{label}.input_refs[{ref_index}]"
            if not isinstance(reference, dict) or set(reference) != {
                "role",
                "path",
                "sha256",
                "bytes",
            }:
                failures.append(f"{ref_label} keys are not exact")
                continue
            if reference.get("role") != role or reference.get("path") != expected_path:
                failures.append(f"{ref_label} role/path binding drift")
                continue
            path = _resolve_below(route, expected_path, f"{ref_label}.path", failures)
            if path is None or not path.is_file() or path.is_symlink():
                failures.append(f"{ref_label} bound input is missing or unsafe")
                continue
            payload = path.read_bytes()
            if (
                reference.get("sha256") != sha256_bytes(payload)
                or type(reference.get("bytes")) is not int
                or reference.get("bytes") != len(payload)
                or not payload
            ):
                failures.append(f"{ref_label} byte binding drift")

    _replay_nodejs_negative_cases(
        route=route,
        route_key=route_key,
        source_language=source_language,
        target_language=target_language,
        expected_case_ids=expected_case_ids,
        cases=cases,
        development_source_path=development_source_path,
        development_suffix=development_suffix,
        development_function=development_function,
        failures=failures,
    )


def v3_research_route_manifest_document(route_key: str) -> dict[str, Any]:
    """Return the exact analyzer-bound, unexecuted V3 route manifest.

    The analyzer and emitter paths describe components that are locally
    available.  Empty route profiles are intentional: those component bindings
    do not constitute evidence that this directed route has been executed.
    """

    from route_runtime_metadata import (  # local import keeps packed legacy replay portable
        ENGINE_PATHS,
        V3_RESEARCH_ROUTE_VERSION,
        VERSIONS,
    )
    from route_sets import V3_EXACT_ROUTE_KEYS, split_route_key

    if route_key not in V3_EXACT_ROUTE_KEYS:
        raise ValueError(f"V3_ROUTE_KEY_REQUIRED:{route_key}")
    source, target = split_route_key(route_key)
    return {
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
            "engine_path": V3_TARGET_EMITTER_RELATIVE_PATH,
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


def validate_v3_research_route_contract(
    manifest: dict[str, Any],
    support: dict[str, Any],
    evidence: dict[str, Any],
    certification: dict[str, Any],
    failures: list[str],
) -> None:
    """Enforce the same fail-closed V3 contract as the full matrix validator."""

    from route_runtime_metadata import (
        v3_research_certification_document,
        v3_research_evidence_document,
    )
    from route_sets import V3_EXACT_ROUTE_KEYS

    route_key = manifest.get("route_key")
    if not isinstance(route_key, str) or route_key not in V3_EXACT_ROUTE_KEYS:
        failures.append("V3 route key is outside the exact research partition")
        return

    if manifest != v3_research_route_manifest_document(route_key):
        failures.append("V3 route manifest is not the exact research contract")
    if evidence != v3_research_evidence_document(route_key):
        failures.append("V3 route raw evidence overclaims or drifts from NOT_RUN")
    if certification != v3_research_certification_document(route_key):
        failures.append("V3 route certification overclaims or drifts from NOT_CERTIFIED")

    if set(support) != {"schema_version", "route_key", "capabilities"}:
        failures.append("V3 support matrix top-level keys are not exact")
    if support.get("schema_version") != 1 or support.get("route_key") != route_key:
        failures.append("V3 support matrix identity is invalid")
    capabilities = support.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        failures.append("V3 support matrix capabilities are empty")
        return

    capability_ids: list[str] = []
    for index, capability in enumerate(capabilities):
        label = f"V3 support capability[{index}]"
        if not isinstance(capability, dict) or set(capability) != {
            "id",
            "status",
            "strategy",
            "reason",
            "evidence_refs",
        }:
            failures.append(f"{label} keys are not exact")
            continue
        capability_id = capability.get("id")
        if not isinstance(capability_id, str) or not capability_id.strip():
            failures.append(f"{label} id is empty")
        else:
            capability_ids.append(capability_id)
            if capability_id == "typed-pure-function-v1":
                failures.append("V3 support matrix admits an unexecuted route profile")
        if capability.get("status") not in V3_RESEARCH_CAPABILITY_STATUS:
            failures.append(f"{label} overclaims research capability support")
        for field in ("strategy", "reason"):
            value = capability.get(field)
            if not isinstance(value, str) or not value.strip():
                failures.append(f"{label} {field} is empty")
        if capability.get("evidence_refs") != []:
            failures.append(f"{label} binds evidence while route execution is NOT_RUN")
    if len(capability_ids) != len(set(capability_ids)):
        failures.append("V3 support matrix capability ids are duplicated")


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
    support: dict[str, Any] = {}
    specialized = False
    nodejs = False
    v3 = False
    module_required = False
    if not route.is_dir():
        errors.append(f"missing route dir: {route}")
    for directory in REQUIRED_DIRS:
        if not (route / directory).exists():
            errors.append(f"missing: {route / directory}")
    try:
        manifest = load(route / "route.json")
        from route_sets import (  # imported only at the CLI boundary for packed replay
            EVIDENCED_ROUTE_KEYS,
            MODULE_EQUIVALENCE_ROUTE_KEYS,
            NODEJS_EXACT_ROUTE_KEYS,
            SPECIALIZED_ROUTE_KEYS,
            V3_EXACT_ROUTE_KEYS,
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
            nodejs = route_key in NODEJS_EXACT_ROUTE_KEYS
            v3 = route_key in V3_EXACT_ROUTE_KEYS
            module_required = route_key in MODULE_EQUIVALENCE_ROUTE_KEYS
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
                if (
                    side_value.get("language") == "cpp"
                    and side_value.get("versions") != cpp_versions
                ):
                    errors.append(f"specialized {side} C++20/Apple clang tuple drift")
        if nodejs:
            profiles = manifest.get("profiles", {})
            gates = manifest.get("gates", {})
            nodejs_typescript = {
                manifest.get("source", {}).get("language"),
                manifest.get("target", {}).get("language"),
            } == {"javascript", "typescript"}
            if manifest.get("status") != "limited":
                errors.append("Node.js exact route status must remain limited")
            if profiles.get("module_profile") != "typed-pure-module-v1":
                errors.append("Node.js module profile drift")
            if profiles.get("input_domain") != NODEJS_INPUT_DOMAIN:
                errors.append("Node.js input domain drift")
            for field in (
                "module_equivalence_required",
                "concrete_spans_required",
                "nodejs_safe_integer_finite_domain_required",
            ):
                if gates.get(field) is not True:
                    errors.append(f"Node.js gate {field} must be true")
            if gates.get("nodejs_effects_async_io_allowed") is not False:
                errors.append("Node.js async/I/O effects must remain blocked")
            if gates.get("nodejs_typescript_integer_semantics_allowed") is not (
                not nodejs_typescript
            ):
                errors.append("Node.js/TypeScript integer gate drift")
    except Exception as exc:
        errors.append(str(exc))
    try:
        support = load(route / "support-matrix.json")
        _validate_optional_json_schema(
            support,
            "support-matrix.schema.json",
            errors,
            "support matrix",
        )
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
                if (
                    capability_by_id.get(capability_id, {}).get("status")
                    != expected_status
                ):
                    errors.append(
                        f"specialized capability {capability_id} status drift"
                    )
            mappings = load(route / "mappings" / "types.json")
            if mappings.get("types") != ["integer", "number", "boolean"]:
                errors.append(
                    "specialized type mapping is not exact integer/number/boolean"
                )
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
        if nodejs:
            capability_by_id = {
                item.get("id"): item
                for item in support.get("capabilities", [])
                if isinstance(item, dict)
            }
            mappings = load(route / "mappings" / "types.json")
            nodejs_typescript = {
                manifest.get("source", {}).get("language"),
                manifest.get("target", {}).get("language"),
            } == {"javascript", "typescript"}
            expected_types = (
                ["number", "boolean", "string"]
                if nodejs_typescript
                else ["integer", "number", "boolean"]
            )
            expected_capability_statuses = {
                "typed-pure-function-v1": "conditional",
                "primitive-types": "conditional",
                "nodejs-es2022-esm-safe-integer-finite-v1": "conditional",
                "string-semantics": "conditional" if nodejs_typescript else "blocked",
                "number-arithmetic": "blocked",
                "if-return-control-flow": "conditional",
                "framework-database-async-concurrency": "blocked",
                "typed-pure-module-v1": "conditional",
            }
            for capability_id, expected_status in expected_capability_statuses.items():
                if (
                    capability_by_id.get(capability_id, {}).get("status")
                    != expected_status
                ):
                    errors.append(f"Node.js capability {capability_id} status drift")
            if mappings.get("types") != expected_types:
                errors.append(
                    "Node.js type mapping does not match its exact source profile"
                )
            if mappings.get("input_domain") != NODEJS_INPUT_DOMAIN:
                errors.append("Node.js type mapping input domain drift")
            expected_string = (
                "STRICT_ECMASCRIPT_VALUE_EQUALITY_CONCAT"
                if nodejs_typescript
                else "BLOCK"
            )
            if mappings.get("string_semantics") != expected_string:
                errors.append("Node.js route string mapping boundary drift")
            expected_integer = (
                "BLOCK_NO_EXPLICIT_INTEGER_TYPE"
                if nodejs_typescript
                else "SAFE_INTEGER_CONDITIONAL"
            )
            if mappings.get("integer_semantics") != expected_integer:
                errors.append("Node.js route integer mapping boundary drift")
            lowering = load(route / "lowering" / "profile.json")
            if lowering.get("input_domain") != NODEJS_INPUT_DOMAIN:
                errors.append("Node.js lowering input domain drift")
            if lowering.get("concrete_spans_required") is not True:
                errors.append("Node.js lowering must require concrete spans")
            if lowering.get("effect_semantics") != "BLOCKED_ASYNC_IO_IMPORT_EVAL":
                errors.append("Node.js lowering effect boundary drift")
            if lowering.get("integer_semantics") != expected_integer:
                errors.append("Node.js lowering integer boundary drift")
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
        if v3:
            validate_v3_research_route_contract(
                manifest,
                support,
                route_evidence,
                certification,
                errors,
            )
        _, strict_errors = validate_formal_equivalence(route, manifest, certification)
        errors.extend(strict_errors)
        _, module_errors = validate_module_equivalence(route, manifest, certification)
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
                corpus_manifest = load(route / "corpus" / corpus / "manifest.json")
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
                _validate_specialized_native_runtime_replay(route, manifest, errors)
        if nodejs:
            if certification.get("certification_decision") != "NOT_CERTIFIED":
                errors.append("Node.js route must remain NOT_CERTIFIED")
            if route_evidence.get("execution_status") == "PASSED_LOCAL":
                nodejs_typescript = {
                    manifest.get("source", {}).get("language"),
                    manifest.get("target", {}).get("language"),
                } == {"javascript", "typescript"}
                expected_types = (
                    ["number", "boolean", "string"]
                    if nodejs_typescript
                    else ["integer", "number", "boolean"]
                )
                if route_evidence.get("evidenced_type_coverage") != expected_types:
                    errors.append("Node.js evidence type coverage drift")
                if route_evidence.get("input_domain") != NODEJS_INPUT_DOMAIN:
                    errors.append("Node.js evidence input domain drift")
                if (
                    route_evidence.get("out_of_domain_arithmetic_behavior")
                    != NODEJS_OUT_OF_DOMAIN_BEHAVIOR
                ):
                    errors.append("Node.js evidence out-of-domain boundary drift")
                validate_nodejs_negative_evidence(
                    route,
                    manifest,
                    route_evidence,
                    errors,
                )
        if module_required:
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
                expected_module_domain = (
                    NODEJS_INPUT_DOMAIN if nodejs else SPECIALIZED_INPUT_DOMAIN
                )
                if module_manifest.get("input_domain") != expected_module_domain:
                    errors.append("module corpus input domain is invalid")
                nodejs_typescript = nodejs and {
                    manifest.get("source", {}).get("language"),
                    manifest.get("target", {}).get("language"),
                } == {"javascript", "typescript"}
                expected_module_types = (
                    ["number", "boolean", "string"]
                    if nodejs_typescript
                    else ["integer", "number", "boolean"]
                )
                if (
                    module_manifest.get("type_coverage_required")
                    != expected_module_types
                ):
                    errors.append("module corpus type coverage requirement drift")
                if module_manifest.get("source_language") != manifest.get(
                    "source", {}
                ).get("language"):
                    errors.append("module corpus source language mismatch")
                if module_manifest.get("minimum_function_count") != 3:
                    errors.append(
                        "module corpus minimum function count must be exactly 3"
                    )
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
                if (
                    isinstance(cases_value, str)
                    and (module_root / cases_value).is_file()
                ):
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
                    errors.append(
                        f"specialized route certification file is missing: {name}"
                    )
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

    fresh_runtime_exit = run_in_fresh_locked_runtime(Path(__file__), sys.argv[1:])
    if fresh_runtime_exit is not None:
        raise SystemExit(fresh_runtime_exit)
    raise SystemExit(main())
