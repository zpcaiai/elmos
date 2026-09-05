from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import platform
import stat
import tempfile
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

from . import canonical, types
from .emitter import (
    _CHECKED_INTEGER_CALL,
    _FLOAT_NON_ZERO_GUARD,
    _HELPERS,
    EmittedFile,
    emit,
)
from .equivalence import (
    L1_PLUS_UNSUPPORTED,
    NODEJS_INPUT_DOMAIN,
    SPECIALIZED_INPUT_DOMAIN,
    DirectedRouteKey,
    behavior_equivalence,
    canonical_json_bytes,
    chunk_equivalence,
    compose_layered_report,
    formal_environment_assumptions,
    formal_equivalence,
    formal_solver_identity,
    module_equivalence,
    normalize_pure_module_case_manifest,
    semantic_equivalence,
    sha256_bytes,
    validate_pure_module_manifest_shape,
    verify_content_reference,
    verify_formal_input_closure,
    write_json,
)
from .identifier_hygiene import (
    IdentifierPlan,
    IdentifierUnitNamespace,
    alpha_normalize_target,
    identifier_plan_bytes,
    plan_identifiers,
    standalone_artifact_unit_namespace,
    target_function_view,
    target_ir_view,
    validate_identifier_plan,
)
from .models import (
    DEPRECATED_DIRECTED_PAIRS,
    REPOSITORY_LANGUAGE_LIFECYCLE_ACTIVE,
    REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY,
    REPOSITORY_SURFACE_LANGUAGES,
    TYPED_PURE_FUNCTION_PROFILE,
    Expression,
    Function,
    Language,
    RouteError,
    SemanticIR,
    SourceSpan,
    Statement,
    is_routed_pair,
    is_specialized_pair,
    requires_concrete_source_spans,
)
from .models import (
    repository_language_lifecycle as expected_repository_language_lifecycle,
)
from .native import (
    _SANDBOX_NETWORK_PROBE_BINARY_BYTES,
    _SANDBOX_NETWORK_PROBE_BINARY_NAME,
    _SANDBOX_NETWORK_PROBE_BINARY_SHA256,
    _SANDBOX_NETWORK_PROBE_BUILD_ARGV,
    _SANDBOX_NETWORK_PROBE_BUILD_ENVIRONMENT,
    _SANDBOX_NETWORK_PROBE_CDHASH_FULL,
    _SANDBOX_NETWORK_PROBE_LINKED_LIBRARIES,
    _SANDBOX_NETWORK_PROBE_SOURCE,
    _SANDBOX_NETWORK_PROBE_SOURCE_BYTES,
    _SANDBOX_NETWORK_PROBE_SOURCE_SHA256,
    _SANDBOX_NETWORK_PROBE_UUID,
    _canonical_digest,
    _canonical_swift_analyzer_receipt,
    _canonical_swift_toolchain_identity,
    _swift_toolchain_receipt,
)
from .repository import javascript_esm_descriptor
from .source_analyzer import analyze, inventory_module
from .toolchains import exact_toolchain
from .validation import safe_output, validate, validate_source


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def repository_language_lifecycle_for_execution(
    source_language: Language,
    target_language: Language,
    *,
    repository_execution_mode: bool,
    supplied: str | None,
) -> str | None:
    """Require an explicit deprecated-replay marker at the execution edge."""

    expected = expected_repository_language_lifecycle(
        source_language,
        target_language,
    )
    if expected is None:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if not repository_execution_mode:
        if supplied is not None:
            raise RouteError("REPOSITORY_LANGUAGE_LIFECYCLE_MODE_INVALID")
        return None
    if expected == REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY:
        if supplied != REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY:
            raise RouteError("DEPRECATED_REPLAY_LIFECYCLE_REQUIRED")
        return expected
    if supplied not in (None, REPOSITORY_LANGUAGE_LIFECYCLE_ACTIVE):
        raise RouteError("REPOSITORY_LANGUAGE_LIFECYCLE_INVALID")
    return REPOSITORY_LANGUAGE_LIFECYCLE_ACTIVE


def _identifier_unit_namespace_for_migration(
    *,
    source: Path,
    source_bytes: bytes,
    repository_execution_mode: bool,
    supplied: IdentifierUnitNamespace | None,
) -> IdentifierUnitNamespace:
    source_sha256 = _digest(source_bytes)
    if supplied is None:
        if repository_execution_mode:
            raise RouteError("IDENTIFIER_REPOSITORY_UNIT_NAMESPACE_REQUIRED")
        return standalone_artifact_unit_namespace(source.name, source_sha256)
    # Never trust a directly constructed frozen dataclass.  Reparse its exact
    # shape before comparing it with the immutable input snapshot.
    namespace = IdentifierUnitNamespace.from_mapping(supplied.to_mapping())
    if namespace.source_sha256 != source_sha256:
        raise RouteError("IDENTIFIER_UNIT_NAMESPACE_SOURCE_DIGEST_MISMATCH")
    if repository_execution_mode:
        if namespace.scope != "repository-work-unit":
            raise RouteError("IDENTIFIER_REPOSITORY_UNIT_NAMESPACE_REQUIRED")
    elif namespace.scope == "repository-work-unit":
        raise RouteError("IDENTIFIER_REPOSITORY_UNIT_NAMESPACE_MODE_MISMATCH")
    elif namespace.scope != "standalone-artifact" or namespace.source_logical_path != source.name:
        raise RouteError("IDENTIFIER_STANDALONE_UNIT_NAMESPACE_MISMATCH")
    return namespace


def _private_input_snapshot(
    root: Path,
    role: str,
    logical_name: str,
    content: bytes,
) -> Path:
    role_root = root / role
    role_root.mkdir(mode=0o700, exist_ok=True)
    path = role_root / logical_name
    path.write_bytes(content)
    path.chmod(0o600)
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size != len(content)
        or path.read_bytes() != content
    ):
        raise RouteError(f"PRIVATE_INPUT_SNAPSHOT_INVALID:{role}")
    return path


def _javascript_descriptor_input(source: Path) -> tuple[dict[str, Any], bytes] | None:
    descriptor = javascript_esm_descriptor(source)
    if descriptor is None:
        return None
    descriptor_path = Path(str(descriptor.get("path", "")))
    expected_sha256 = descriptor.get("sha256")
    expected_bytes = descriptor.get("bytes")
    if (
        not descriptor_path.is_absolute()
        or not isinstance(expected_sha256, str)
        or not isinstance(expected_bytes, int)
        or expected_bytes < 0
    ):
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_PRIVATE_INPUT_INVALID")
    try:
        before = descriptor_path.lstat()
        content = descriptor_path.read_bytes()
        after = descriptor_path.lstat()
    except OSError as error:
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_PRIVATE_INPUT_INVALID") from error
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if (
        identity_before != identity_after
        or descriptor_path.is_symlink()
        or not stat.S_ISREG(after.st_mode)
        or after.st_nlink != 1
        or len(content) != expected_bytes
        or hashlib.sha256(content).hexdigest() != expected_sha256
        or javascript_esm_descriptor(source) != descriptor
    ):
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_CHANGED_DURING_PRIVATE_INPUT_SNAPSHOT")
    return (
        {
            "observed_origin_path": str(descriptor_path),
            "logical_path": Path(os.path.relpath(descriptor_path, source.resolve().parent)).as_posix(),
            "sha256": _digest(content),
            "bytes": len(content),
            "type": "module",
        },
        content,
    )


def _private_javascript_source_snapshot(
    root: Path,
    source: Path,
    source_language: Language,
    source_bytes: bytes,
) -> tuple[Path, dict[str, Any] | None, bytes | None, Path | None]:
    if source_language != "javascript":
        source_snapshot = _private_input_snapshot(root, "source", source.name, source_bytes)
        return source_snapshot, None, None, None
    descriptor_input = _javascript_descriptor_input(source)
    if descriptor_input is None:
        source_snapshot = _private_input_snapshot(root, "source", source.name, source_bytes)
        return source_snapshot, None, None, None
    binding, descriptor_bytes = descriptor_input
    descriptor_snapshot = _private_input_snapshot(root, "source", "package.json", descriptor_bytes)
    logical_descriptor = PurePosixPath(str(binding.get("logical_path", "")))
    logical_parts = logical_descriptor.parts
    if (
        not logical_parts
        or logical_parts[-1] != "package.json"
        or any(part != ".." for part in logical_parts[:-1])
        or len(logical_parts) > 65
    ):
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_LOGICAL_PATH_UNSUPPORTED")
    source_parent = descriptor_snapshot.parent
    private_components: list[str] = []
    for index in range(len(logical_parts) - 1):
        component = f"nested-{index:03d}"
        private_components.append(component)
        source_parent /= component
        source_parent.mkdir(mode=0o700)
        metadata = source_parent.lstat()
        if (
            source_parent.is_symlink()
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise RouteError("JAVASCRIPT_ESM_PRIVATE_SOURCE_TOPOLOGY_INVALID")
    source_relative_path = Path(*private_components, source.name).as_posix()
    source_snapshot = _private_input_snapshot(
        root,
        "source",
        source_relative_path,
        source_bytes,
    )
    if (
        Path(os.path.relpath(descriptor_snapshot, source_snapshot.parent)).as_posix()
        != str(logical_descriptor)
    ):
        raise RouteError("JAVASCRIPT_ESM_PRIVATE_SOURCE_TOPOLOGY_MISMATCH")
    binding = {
        **binding,
        "snapshot_path": descriptor_snapshot.relative_to(root).as_posix(),
    }
    _require_javascript_descriptor_snapshot(binding, descriptor_snapshot, descriptor_bytes)
    return source_snapshot, binding, descriptor_bytes, descriptor_snapshot


def _require_javascript_descriptor_origin_unchanged(source: Path, expected: dict[str, Any] | None) -> None:
    if expected is None:
        return
    observed = _javascript_descriptor_input(source)
    if observed is None or observed[0] != {
        key: expected[key] for key in ("observed_origin_path", "logical_path", "sha256", "bytes", "type")
    }:
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_ORIGIN_CHANGED_DURING_MIGRATION")


def _require_javascript_descriptor_snapshot(
    expected: dict[str, Any] | None,
    snapshot: Path | None,
    expected_bytes: bytes | None,
) -> None:
    if expected is None:
        if snapshot is not None or expected_bytes is not None:
            raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_SNAPSHOT_UNEXPECTED")
        return
    if snapshot is None or expected_bytes is None:
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_SNAPSHOT_REQUIRED")
    try:
        metadata = snapshot.lstat()
        content = snapshot.read_bytes()
    except OSError as error:
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_SNAPSHOT_CHANGED_DURING_MIGRATION") from error
    if (
        snapshot.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or content != expected_bytes
        or _digest(content) != expected.get("sha256")
    ):
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_SNAPSHOT_CHANGED_DURING_MIGRATION")


def _javascript_descriptor_snapshot_for_source(
    source: Path,
    expected: dict[str, Any] | None,
) -> Path | None:
    if expected is None:
        return None
    logical_descriptor = PurePosixPath(str(expected.get("logical_path", "")))
    parts = logical_descriptor.parts
    if (
        not source.is_absolute()
        or not parts
        or parts[-1] != "package.json"
        or any(part != ".." for part in parts[:-1])
        or len(parts) > 65
        or expected.get("snapshot_path") != "source/package.json"
    ):
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_SNAPSHOT_PATH_INVALID")
    cursor = source.parent
    for _part in parts[:-1]:
        try:
            metadata = cursor.lstat()
        except OSError as error:
            raise RouteError("JAVASCRIPT_ESM_PRIVATE_SOURCE_TOPOLOGY_INVALID") from error
        if (
            cursor.is_symlink()
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise RouteError("JAVASCRIPT_ESM_PRIVATE_SOURCE_TOPOLOGY_INVALID")
        cursor = cursor.parent
    if cursor.name != "source":
        raise RouteError("JAVASCRIPT_ESM_PRIVATE_SOURCE_TOPOLOGY_MISMATCH")
    try:
        root_metadata = cursor.lstat()
    except OSError as error:
        raise RouteError("JAVASCRIPT_ESM_PRIVATE_SOURCE_TOPOLOGY_INVALID") from error
    if (
        cursor.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise RouteError("JAVASCRIPT_ESM_PRIVATE_SOURCE_TOPOLOGY_INVALID")
    return cursor / "package.json"


def _bound_javascript_runtime_descriptor_observation(
    expected: dict[str, Any],
    snapshot: Path,
    runtime_evidence: list[dict[str, Any]],
) -> dict[str, str]:
    """Bind the persisted diagnostic observation to the executed snapshot.

    The stable descriptor fields remain content-addressed and portable.  The
    absolute observation is deliberately diagnostic, but it must identify the
    same private ``package.json`` that every source runtime actually consumed;
    recording the live checkout path here would contradict the validation
    evidence and break the assembly evidence closure.
    """

    stable_expected = {
        "logical_path": expected.get("logical_path"),
        "sha256": expected.get("sha256"),
        "bytes": expected.get("bytes"),
        "type": expected.get("type"),
    }
    expected_observation = {"observed_origin_path": str(snapshot)}
    if (
        not snapshot.is_absolute()
        or snapshot.name != "package.json"
        or not runtime_evidence
        or stable_expected["type"] != "module"
    ):
        raise RouteError("JAVASCRIPT_ESM_RUNTIME_DESCRIPTOR_EVIDENCE_INVALID")
    for evidence in runtime_evidence:
        if (
            not isinstance(evidence, dict)
            or evidence.get("javascript_esm_descriptor") != stable_expected
            or evidence.get("javascript_esm_descriptor_observation")
            != expected_observation
        ):
            raise RouteError("JAVASCRIPT_ESM_RUNTIME_DESCRIPTOR_EVIDENCE_MISMATCH")
    return expected_observation


def _file_identity(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": f"src/elmos_polyglot_route/{path.name}",
        "sha256": _digest(content),
        "byte_count": len(content),
    }


def _artifact_binding(
    role: str,
    path: str,
    content: bytes,
    evidence_path: str,
) -> dict[str, Any]:
    digest = _digest(content)
    return {
        "role": role,
        "path": path,
        "sha256": digest,
        "byte_count": len(content),
        "content_base64": base64.b64encode(content).decode("ascii"),
        "content_reference": {"path": evidence_path, "sha256": digest},
    }


def _normalized_ir_binding(
    role: str,
    artifact_reference: dict[str, str],
    ir: SemanticIR,
    function: Function,
) -> dict[str, Any]:
    # Source spans remain in `semantic_ir` as concrete evidence bindings, but
    # the theorem term is location independent.
    function_mapping = function.semantic_mapping()
    return {
        "role": role,
        "artifact": artifact_reference,
        "semantic_ir": ir.to_mapping(),
        "semantic_ir_sha256": sha256_bytes(canonical_json_bytes(ir.to_mapping())),
        "formal_function": function_mapping,
        "formal_function_sha256": sha256_bytes(canonical_json_bytes(function_mapping)),
    }


def _formal_input_payload(
    *,
    source_language: Language,
    target_language: Language,
    source_path: str,
    source_bytes: bytes,
    target_path: str,
    target_bytes: bytes,
    source_ir: SemanticIR,
    raw_target_ir: SemanticIR,
    target_ir: SemanticIR,
    source_ir_reference: dict[str, str],
    raw_target_ir_reference: dict[str, str],
    target_ir_reference: dict[str, str],
    identifier_plan: IdentifierPlan,
    identifier_plan_reference: dict[str, str],
    emitted: EmittedFile,
) -> dict[str, Any]:
    module_root = Path(__file__).resolve().parent
    assumptions = formal_environment_assumptions(source_language, target_language)
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.formal-equivalence-input",
        "route": {
            "source_language": source_language,
            "target_language": target_language,
            "profile": "typed-pure-function-v1",
        },
        "claim_scope": {
            "relation": "canonical-normalized-source-ir-to-target-relift-ir",
            "source_term": "source_normalized_ir.formal_function",
            "target_term": "target_relift_normalized_ir.formal_function",
            "original_source_bytes_theorem": False,
            "input_domain": declared_formal_input_domain(source_language, target_language),
            "source_compiler_runtime_soundness": "NOT_RUN",
            "target_compiler_runtime_soundness": "NOT_RUN",
        },
        "source_artifact": _artifact_binding(
            "original-source-analyzer-input",
            source_path,
            source_bytes,
            f"source-runtime/{source_path}",
        ),
        "target_artifact": _artifact_binding(
            "emitted-target-analyzer-input",
            target_path,
            target_bytes,
            target_path,
        ),
        "source_normalized_ir": _normalized_ir_binding(
            "canonical-source-normalized-ir",
            source_ir_reference,
            source_ir,
            source_ir.functions[0],
        ),
        "target_relift_normalized_ir": _normalized_ir_binding(
            "emitted-target-relift-normalized-ir",
            target_ir_reference,
            target_ir,
            target_ir.functions[0],
        ),
        "identifier_hygiene": {
            "kind": "elmos.verified-alpha-normalization",
            "policy_id": identifier_plan.policy_id,
            "policy_sha256": identifier_plan.policy_sha256,
            "unit_namespace": identifier_plan.unit_namespace.to_mapping(),
            "unit_namespace_sha256": identifier_plan.unit_namespace.digest,
            "plan": identifier_plan_reference,
            "plan_digest": identifier_plan.digest,
            "source_function_name": source_ir.functions[0].name,
            "target_function_name": raw_target_ir.functions[0].name,
            "raw_target_relift_ir": _normalized_ir_binding(
                "emitted-target-relift-raw-ir",
                raw_target_ir_reference,
                raw_target_ir,
                raw_target_ir.functions[0],
            ),
            "normalized_target_ir": target_ir_reference,
        },
        "implementation_identity": {
            "engine": _file_identity(module_root / "engine.py"),
            "equivalence_encoder": _file_identity(module_root / "equivalence.py"),
            "emitter": _file_identity(module_root / "emitter.py"),
            "identifier_hygiene": _file_identity(module_root / "identifier_hygiene.py"),
        },
        "analyzer_identity": {
            "source": {
                "name": source_ir.analyzer,
                "version": source_ir.analyzer_version,
                "language": source_language,
            },
            "target_relift": {
                "name": target_ir.analyzer,
                "version": target_ir.analyzer_version,
                "language": target_language,
                "mode": "emitted-target",
            },
        },
        "emitter_identity": {
            "target_language": target_language,
            "normalization_rules": list(emitted.normalization_rules),
            "helper_digests": [
                {"helper_id": helper_id, "sha256": digest} for helper_id, digest in emitted.helper_digests
            ],
        },
        "solver": formal_solver_identity(),
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "environment_assumptions": assumptions,
        "unsupported_semantics": list(L1_PLUS_UNSUPPORTED),
    }


def _load_cases(path: Path, parameter_count: int) -> list[dict[str, Any]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list) or not loaded:
        raise RouteError("BEHAVIOR_CASES_REQUIRED")
    result: list[dict[str, Any]] = []
    for item in loaded:
        if not isinstance(item, dict) or not isinstance(item.get("args"), list) or "expected" not in item:
            raise RouteError("INVALID_BEHAVIOR_CASE")
        if len(item["args"]) != parameter_count:
            raise RouteError("BEHAVIOR_ARGUMENT_COUNT_MISMATCH")
        result.append(item)
    return result


def _expression_uses_string(expression: Expression) -> bool:
    if expression.kind == "literal" and isinstance(expression.value, str):
        return True
    return any(nested is not None and _expression_uses_string(nested) for nested in (expression.left, expression.right))


def _expression_uses_non_finite_number(expression: Expression) -> bool:
    return (
        expression.kind == "literal" and isinstance(expression.value, float) and not math.isfinite(expression.value)
    ) or any(
        nested is not None and _expression_uses_non_finite_number(nested)
        for nested in (expression.left, expression.right)
    )


def _expression_uses_negative_zero_literal(expression: Expression) -> bool:
    return (
        expression.kind == "literal"
        and isinstance(expression.value, float)
        and expression.value == 0.0
        and math.copysign(1.0, expression.value) < 0
    ) or any(
        nested is not None and _expression_uses_negative_zero_literal(nested)
        for nested in (expression.left, expression.right)
    )


def _expression_uses_number_arithmetic(
    expression: Expression,
    environment: dict[str, str],
) -> bool:
    if (
        expression.kind == "binary"
        and expression.operator in types.ARITHMETIC_OPERATORS
        and types.infer(expression, environment) == "number"
    ):
        return True
    return any(
        nested is not None and _expression_uses_number_arithmetic(nested, environment)
        for nested in (expression.left, expression.right)
    )


def _statement_uses_string(statement: Statement) -> bool:
    return any(
        expression is not None and _expression_uses_string(expression)
        for expression in (statement.expression, statement.condition)
    ) or any(_statement_uses_string(nested) for nested in (*statement.then_body, *statement.else_body))


def _statement_uses_non_finite_number(statement: Statement) -> bool:
    return any(
        expression is not None and _expression_uses_non_finite_number(expression)
        for expression in (statement.expression, statement.condition)
    ) or any(_statement_uses_non_finite_number(nested) for nested in (*statement.then_body, *statement.else_body))


def _statement_uses_negative_zero_literal(statement: Statement) -> bool:
    return any(
        expression is not None and _expression_uses_negative_zero_literal(expression)
        for expression in (statement.expression, statement.condition)
    ) or any(_statement_uses_negative_zero_literal(nested) for nested in (*statement.then_body, *statement.else_body))


def _statement_uses_number_arithmetic(
    statement: Statement,
    environment: dict[str, str],
) -> bool:
    return any(
        expression is not None and _expression_uses_number_arithmetic(expression, environment)
        for expression in (statement.expression, statement.condition)
    ) or any(
        _statement_uses_number_arithmetic(nested, environment)
        for nested in (*statement.then_body, *statement.else_body)
    )


def is_nodejs_pair(source_language: Language, target_language: Language) -> bool:
    return source_language != target_language and "javascript" in {
        source_language,
        target_language,
    }


def is_nodejs_typescript_pair(
    source_language: Language,
    target_language: Language,
) -> bool:
    return {source_language, target_language} == {"javascript", "typescript"}


def declared_formal_input_domain(
    source_language: Language,
    target_language: Language,
) -> str:
    if is_specialized_pair(source_language, target_language):
        return SPECIALIZED_INPUT_DOMAIN
    if {source_language, target_language} & {"javascript", "typescript", "react"}:
        return NODEJS_INPUT_DOMAIN
    return "profile-total-domain"


def _enforce_nodejs_semantic_domain(
    ir: SemanticIR,
    source_language: Language,
    target_language: Language,
) -> None:
    if not ({source_language, target_language} & {"javascript", "typescript", "react"}):
        return
    nodejs_pair = is_nodejs_pair(source_language, target_language)
    nodejs_typescript = is_nodejs_typescript_pair(source_language, target_language)
    for function in ir.functions:
        environment = {parameter.name: parameter.type for parameter in function.parameters}
        if any(_statement_uses_negative_zero_literal(statement) for statement in function.body):
            languages = {source_language, target_language}
            runtime = (
                "JAVASCRIPT"
                if "javascript" in languages
                else "REACT"
                if "react" in languages
                else "TYPESCRIPT"
            )
            raise RouteError(
                f"{runtime}_NEGATIVE_ZERO_LITERAL_UNSUPPORTED:{source_language}-to-{target_language}:{function.name}"
            )
        if not nodejs_pair:
            continue
        if nodejs_typescript and (
            function.return_type == "integer" or any(parameter.type == "integer" for parameter in function.parameters)
        ):
            raise RouteError(
                f"NODEJS_TYPESCRIPT_INTEGER_EVIDENCE_UNAVAILABLE:{source_language}-to-{target_language}:{function.name}"
            )
        if not nodejs_typescript and (
            function.return_type == "string"
            or any(parameter.type == "string" for parameter in function.parameters)
            or any(_statement_uses_string(statement) for statement in function.body)
        ):
            raise RouteError(
                f"NODEJS_STRING_SEMANTICS_UNSUPPORTED:{source_language}-to-{target_language}:{function.name}"
            )
        if any(_statement_uses_non_finite_number(statement) for statement in function.body):
            raise RouteError(
                f"NODEJS_NON_FINITE_NUMBER_UNSUPPORTED:{source_language}-to-{target_language}:{function.name}"
            )
        if any(_statement_uses_number_arithmetic(statement, environment) for statement in function.body):
            raise RouteError(
                f"NODEJS_NUMBER_ARITHMETIC_UNSUPPORTED:{source_language}-to-{target_language}:{function.name}"
            )


def _enforce_nodejs_case_domain(
    function: Function,
    cases: list[dict[str, Any]],
    source_language: Language,
    target_language: Language,
) -> None:
    if not ({source_language, target_language} & {"javascript", "typescript", "react"}):
        return
    safe_integer_max = 2**53 - 1
    for case_index, case in enumerate(cases):
        values = [*case["args"], case["expected"]]
        if any(isinstance(value, float) and not math.isfinite(value) for value in values):
            raise RouteError(
                f"NODEJS_CASE_NON_FINITE_NUMBER_UNSUPPORTED:{source_language}-to-{target_language}:"
                f"{function.name}:{case_index}"
            )
        for parameter, value in zip(function.parameters, case["args"], strict=True):
            if parameter.type == "integer" and (
                not isinstance(value, int) or isinstance(value, bool) or abs(value) > safe_integer_max
            ):
                raise RouteError(
                    f"NODEJS_CASE_UNSAFE_INTEGER_UNSUPPORTED:{source_language}-to-{target_language}:"
                    f"{function.name}:{case_index}:{parameter.name}"
                )
        try:
            evaluation = canonical.evaluate(function, list(case["args"]))
        except canonical.CanonicalError as error:
            raise RouteError(
                f"NODEJS_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN:{source_language}-to-{target_language}:"
                f"{function.name}:{case_index}:{type(error).__name__}"
            ) from error
        if function.return_type == "integer" and (
            not isinstance(evaluation.value, int)
            or isinstance(evaluation.value, bool)
            or abs(evaluation.value) > safe_integer_max
        ):
            raise RouteError(
                f"NODEJS_CASE_UNSAFE_INTEGER_RESULT_UNSUPPORTED:{source_language}-to-{target_language}:"
                f"{function.name}:{case_index}"
            )
        if not evaluation.within_safe_integers:
            raise RouteError(
                f"NODEJS_CASE_UNSAFE_INTEGER_INTERMEDIATE_UNSUPPORTED:{source_language}-to-{target_language}:"
                f"{function.name}:{case_index}"
            )
        if isinstance(evaluation.value, float) and not math.isfinite(evaluation.value):
            raise RouteError(
                f"NODEJS_CASE_NON_FINITE_RESULT_UNSUPPORTED:{source_language}-to-{target_language}:"
                f"{function.name}:{case_index}"
            )
        if not evaluation.within_finite_numbers:
            raise RouteError(
                f"NODEJS_CASE_NON_FINITE_INTERMEDIATE_UNSUPPORTED:{source_language}-to-{target_language}:"
                f"{function.name}:{case_index}"
            )


def _enforce_specialized_semantic_domain(
    ir: SemanticIR,
    source_language: Language,
    target_language: Language,
) -> None:
    """Reject string semantics that are not shared by the native exact eight.

    Swift string equality uses Unicode canonical equivalence, Java compares
    UTF-16 code units, and C++ compares bytes. Objective-C adds a Foundation
    representation boundary. Until a versioned encoding and normalization
    contract is enforced at every call boundary, accepting canonical
    ``string`` would create a false equivalence claim. The original complete
    30-route matrix retains its existing contract; this restriction belongs
    only to the explicitly declared native exact-eight set.
    """

    if not is_specialized_pair(source_language, target_language):
        return
    for function in ir.functions:
        environment = {parameter.name: parameter.type for parameter in function.parameters}
        if (
            function.return_type == "string"
            or any(parameter.type == "string" for parameter in function.parameters)
            or any(_statement_uses_string(statement) for statement in function.body)
        ):
            raise RouteError(
                f"SPECIALIZED_STRING_SEMANTICS_UNSUPPORTED:{source_language}-to-{target_language}:{function.name}"
            )
        if any(_statement_uses_non_finite_number(statement) for statement in function.body):
            raise RouteError(
                f"SPECIALIZED_NON_FINITE_NUMBER_UNSUPPORTED:{source_language}-to-{target_language}:{function.name}"
            )
        if any(_statement_uses_number_arithmetic(statement, environment) for statement in function.body):
            raise RouteError(
                f"SPECIALIZED_NUMBER_ARITHMETIC_UNSUPPORTED:{source_language}-to-{target_language}:{function.name}"
            )


def _enforce_specialized_case_domain(
    function: Function,
    cases: list[dict[str, Any]],
    source_language: Language,
    target_language: Language,
) -> None:
    """Block native execution before an exact-eight case reaches an error domain."""

    if not is_specialized_pair(source_language, target_language):
        return
    for case_index, case in enumerate(cases):
        values = [*case["args"], case["expected"]]
        if any(isinstance(value, float) and not math.isfinite(value) for value in values):
            raise RouteError(
                "SPECIALIZED_CASE_NON_FINITE_NUMBER_UNSUPPORTED:"
                f"{source_language}-to-{target_language}:{function.name}:{case_index}"
            )
        try:
            evaluation = canonical.evaluate(function, list(case["args"]))
        except canonical.CanonicalError as error:
            raise RouteError(
                "SPECIALIZED_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN:"
                f"{source_language}-to-{target_language}:{function.name}:{case_index}:"
                f"{type(error).__name__}"
            ) from error
        if isinstance(evaluation.value, float) and not math.isfinite(evaluation.value):
            raise RouteError(
                "SPECIALIZED_CASE_NON_FINITE_RESULT_UNSUPPORTED:"
                f"{source_language}-to-{target_language}:{function.name}:{case_index}"
            )


def _require_sha256(value: str, label: str) -> None:
    if (
        len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise RouteError(f"INVALID_SHA256:{label}")


def _artifact_ref(root: Path, path: Path, role: str) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_root not in resolved_path.parents or not path.is_file() or path.is_symlink():
        raise RouteError(f"MODULE_ARTIFACT_PATH_INVALID:{role}")
    content = path.read_bytes()
    return {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "sha256": _digest(content),
        "bytes": len(content),
    }


def verify_pure_module(
    *,
    source_ir: SemanticIR,
    raw_target_ir: SemanticIR,
    target_ir: SemanticIR,
    identifier_plan: IdentifierPlan,
    case_manifest: dict[str, Any],
    source_observations: dict[str, list[dict[str, Any]]],
    target_observations: dict[str, list[dict[str, Any]]],
    source_artifact_sha256: str,
    target_artifact_sha256: str,
    corpus_sha256: str,
    emitted: EmittedFile,
    source_artifact_bytes: bytes,
    source_logical_file: str,
    case_manifest_bytes: bytes,
    source_inventory: dict[str, Any],
    target_inventory: dict[str, Any],
    whole_file_closure: dict[str, Any],
    output: Path,
    javascript_descriptor: dict[str, Any] | None = None,
    javascript_descriptor_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Persist a content-bound typed-pure-module equivalence composition.

    Callers supply observations produced by real source and target executions;
    :func:`migrate_module` below is the end-to-end entry point that creates
    those observations.  This lower-level function is useful to route runners
    that already own isolated compilation/execution.
    """

    source_language = source_ir.source_language
    target_language = target_ir.source_language
    if (
        not is_routed_pair(source_language, target_language)
        and (source_language, target_language) not in DEPRECATED_DIRECTED_PAIRS
    ):
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    validate_identifier_plan(source_ir, identifier_plan)
    observed_normalized_target = alpha_normalize_target(source_ir, raw_target_ir, identifier_plan)
    if observed_normalized_target.to_mapping() != target_ir.to_mapping():
        raise RouteError("PURE_MODULE_NORMALIZED_TARGET_IR_MISMATCH")
    _enforce_specialized_semantic_domain(source_ir, source_language, target_language)
    _enforce_specialized_semantic_domain(target_ir, source_language, target_language)
    _enforce_nodejs_semantic_domain(source_ir, source_language, target_language)
    _enforce_nodejs_semantic_domain(target_ir, source_language, target_language)
    source_functions = {function.name: function for function in source_ir.functions}
    cases_by_symbol = normalize_pure_module_case_manifest(case_manifest, source_functions)
    for symbol, cases in cases_by_symbol.items():
        _enforce_specialized_case_domain(source_functions[symbol], cases, source_language, target_language)
        _enforce_nodejs_case_domain(source_functions[symbol], cases, source_language, target_language)
    for label, digest in (
        ("source_artifact", source_artifact_sha256),
        ("target_artifact", target_artifact_sha256),
        ("corpus", corpus_sha256),
    ):
        _require_sha256(digest, label)
    emitted_bytes = emitted.content.encode("utf-8")
    if _digest(source_artifact_bytes) != source_artifact_sha256:
        raise RouteError("SOURCE_MODULE_ARTIFACT_DIGEST_MISMATCH")
    if _digest(case_manifest_bytes) != corpus_sha256:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_DIGEST_MISMATCH")
    if _digest(emitted_bytes) != target_artifact_sha256:
        raise RouteError("TARGET_MODULE_ARTIFACT_DIGEST_MISMATCH")
    if (javascript_descriptor is None) != (javascript_descriptor_bytes is None):
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_MODULE_INPUT_INCOMPLETE")
    if javascript_descriptor is not None and javascript_descriptor_bytes is not None:
        if (
            javascript_descriptor.get("type") != "module"
            or javascript_descriptor.get("sha256") != _digest(javascript_descriptor_bytes)
            or javascript_descriptor.get("bytes") != len(javascript_descriptor_bytes)
            or not isinstance(javascript_descriptor.get("observed_origin_path"), str)
            or not isinstance(javascript_descriptor.get("logical_path"), str)
            or not isinstance(javascript_descriptor.get("snapshot_path"), str)
        ):
            raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_MODULE_INPUT_INVALID")
    # Reuse the span path contract before constructing a destination path.
    SourceSpan.from_mapping({"file": source_logical_file, "start_byte": 0, "end_byte": 1})

    output = safe_output(output)
    output.mkdir(parents=True, exist_ok=True)
    identifier_plan_path = output / "identifier-plan.json"
    raw_target_ir_path = output / "target-semantic-ir.raw.json"
    normalized_target_ir_path = output / "target-semantic-ir.normalized.json"
    identifier_plan_path.write_bytes(identifier_plan_bytes(identifier_plan))
    write_json(raw_target_ir_path, raw_target_ir.to_mapping())
    write_json(normalized_target_ir_path, target_ir.to_mapping())
    identifier_plan_reference = _artifact_ref(output, identifier_plan_path, "identifier-plan")
    raw_target_ir_reference = _artifact_ref(output, raw_target_ir_path, "raw-target-ir")
    normalized_target_ir_reference = _artifact_ref(
        output,
        normalized_target_ir_path,
        "normalized-target-ir",
    )
    if identifier_plan_reference["sha256"] != identifier_plan.digest:
        raise RouteError("IDENTIFIER_PLAN_PERSISTED_DIGEST_MISMATCH")

    expected_target_view = target_ir_view(source_ir, identifier_plan)
    raw_target_index = {function.name: function for function in raw_target_ir.functions}
    canonical_target_index = {function.name: function for function in target_ir.functions}
    identifier_functions: list[dict[str, Any]] = []
    for source_function, expected_raw_function in zip(
        source_ir.functions,
        expected_target_view.functions,
        strict=True,
    ):
        raw_function = raw_target_index.get(expected_raw_function.name)
        canonical_function = canonical_target_index.get(source_function.name)
        if raw_function is None or canonical_function is None:
            raise RouteError("PURE_MODULE_TARGET_IDENTIFIER_MAP_INCOMPLETE")
        identifier_functions.append(
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
    identifier_hygiene = {
        "status": "PASSED",
        "policy_id": identifier_plan.policy_id,
        "policy_sha256": identifier_plan.policy_sha256,
        "unit_namespace": identifier_plan.unit_namespace.to_mapping(),
        "unit_namespace_sha256": identifier_plan.unit_namespace.digest,
        "plan": {key: identifier_plan_reference[key] for key in ("path", "sha256", "bytes")},
        "raw_target_ir": {key: raw_target_ir_reference[key] for key in ("path", "sha256", "bytes")},
        "normalized_target_ir": {key: normalized_target_ir_reference[key] for key in ("path", "sha256", "bytes")},
        "functions": identifier_functions,
        "renamed": any(binding.decision == "ALPHA_RENAMED" for binding in identifier_plan.bindings),
    }
    source_inventory_path = output / "source-module-inventory.json"
    target_inventory_path = output / "target-module-inventory.json"
    whole_file_closure_path = output / "whole-file-module-closure.json"
    source_inventory_sha256 = write_json(source_inventory_path, source_inventory)
    target_inventory_sha256 = write_json(target_inventory_path, target_inventory)
    whole_file_closure_sha256 = write_json(whole_file_closure_path, whole_file_closure)
    if whole_file_closure.get("source_inventory_sha256") != source_inventory_sha256:
        raise RouteError("PURE_MODULE_SOURCE_INVENTORY_BACKLINK_MISMATCH")
    if whole_file_closure.get("target_inventory_sha256") != target_inventory_sha256:
        raise RouteError("PURE_MODULE_TARGET_INVENTORY_BACKLINK_MISMATCH")
    if whole_file_closure.get("status") != "PASSED":
        raise RouteError("PURE_MODULE_WHOLE_FILE_CLOSURE_NOT_PASSED")
    source_ir_path = output / "source-module-semantic-ir.json"
    target_ir_path = output / "target-module-semantic-ir.json"
    source_observations_path = output / "source-module-observations.json"
    target_observations_path = output / "target-module-observations.json"
    target_artifact_path = output / emitted.relative_path
    source_artifact_path = output / "source-module-artifact" / source_logical_file
    case_manifest_path = output / "module-case-manifest.json"
    write_json(source_ir_path, source_ir.to_mapping())
    write_json(target_ir_path, target_ir.to_mapping())
    write_json(source_observations_path, source_observations)
    write_json(target_observations_path, target_observations)
    source_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    source_artifact_path.write_bytes(source_artifact_bytes)
    case_manifest_path.write_bytes(case_manifest_bytes)
    target_artifact_path.write_bytes(emitted_bytes)
    javascript_descriptor_input: dict[str, Any] | None = None
    javascript_descriptor_reference: dict[str, Any] | None = None
    if javascript_descriptor is not None and javascript_descriptor_bytes is not None:
        descriptor_artifact_path = source_artifact_path.parent / "package.json"
        descriptor_artifact_path.write_bytes(javascript_descriptor_bytes)
        javascript_descriptor_reference = _artifact_ref(
            output,
            descriptor_artifact_path,
            "source-javascript-esm-descriptor",
        )
        javascript_descriptor_input = {
            "logical_path": javascript_descriptor["logical_path"],
            "snapshot_path": javascript_descriptor["snapshot_path"],
            "artifact_path": javascript_descriptor_reference["path"],
            "sha256": javascript_descriptor_reference["sha256"],
            "bytes": javascript_descriptor_reference["bytes"],
            "type": "module",
        }

    report, proof_closures_by_symbol = module_equivalence(
        source=source_ir,
        target=target_ir,
        case_manifest=case_manifest,
        source_observations=source_observations,
        target_observations=target_observations,
        source_artifact_sha256=source_artifact_sha256,
        target_artifact_sha256=target_artifact_sha256,
        corpus_sha256=corpus_sha256,
        emitted=emitted,
        source_artifact_bytes=source_artifact_bytes,
        source_logical_file=source_logical_file,
        source_inventory_sha256=source_inventory_sha256,
        source_inventory_byte_count=source_inventory_path.stat().st_size,
        target_inventory_sha256=target_inventory_sha256,
        target_inventory_byte_count=target_inventory_path.stat().st_size,
        whole_file_closure=whole_file_closure,
        identifier_hygiene=identifier_hygiene,
        javascript_esm_descriptor=javascript_descriptor_input,
    )
    formal_input_path = output / "module-formal-input.json"
    formal_input_sha256 = write_json(formal_input_path, report["module_input"])
    if formal_input_sha256 != report["module_input_sha256"]:
        raise RouteError("PURE_MODULE_FORMAL_INPUT_DIGEST_MISMATCH")

    artifact_refs = [
        identifier_plan_reference,
        raw_target_ir_reference,
        normalized_target_ir_reference,
        _artifact_ref(output, source_ir_path, "source-module-semantic-ir"),
        _artifact_ref(output, target_ir_path, "target-module-semantic-ir"),
        _artifact_ref(output, source_observations_path, "source-module-observations"),
        _artifact_ref(output, target_observations_path, "target-module-observations"),
        _artifact_ref(output, source_artifact_path, "original-source-module-artifact"),
        _artifact_ref(output, target_artifact_path, "emitted-target-module-artifact"),
        _artifact_ref(output, case_manifest_path, "module-case-manifest"),
        _artifact_ref(output, formal_input_path, "module-formal-input"),
        _artifact_ref(output, source_inventory_path, "source-module-inventory"),
        _artifact_ref(output, target_inventory_path, "target-module-inventory"),
        _artifact_ref(output, whole_file_closure_path, "whole-file-module-closure"),
    ]
    if artifact_refs[-1]["sha256"] != whole_file_closure_sha256:
        raise RouteError("PURE_MODULE_WHOLE_FILE_CLOSURE_DIGEST_MISMATCH")
    if javascript_descriptor_reference is not None:
        artifact_refs.append(javascript_descriptor_reference)
    report["whole_file_closure"] = whole_file_closure
    report["identifier_hygiene"] = identifier_hygiene
    if javascript_descriptor_input is not None:
        assert javascript_descriptor is not None
        report["javascript_esm_descriptor"] = javascript_descriptor_input
        report["javascript_esm_descriptor_observation"] = {
            "observed_origin_path": javascript_descriptor["observed_origin_path"]
        }
    for function_report in report["functions"]:
        symbol = function_report["symbol"]
        closure = proof_closures_by_symbol[symbol]
        formal_input_path = output / closure["formal_input_path"]
        solver_input_path = output / closure["solver_input_path"]
        formal_result_path = output / closure["formal_result_path"]

        observed_formal_input_sha256 = write_json(formal_input_path, closure["formal_input"])
        if observed_formal_input_sha256 != closure["formal_input_sha256"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_INPUT_DIGEST_MISMATCH:{symbol}")
        solver_input_path.write_text(closure["solver_input"], encoding="utf-8")
        solver_reference = _artifact_ref(output, solver_input_path, "formal-function-smt2")
        if solver_reference["sha256"] != closure["solver_input_sha256"]:
            raise RouteError(f"PURE_MODULE_SOLVER_INPUT_DIGEST_MISMATCH:{symbol}")
        formal_result_sha256 = write_json(formal_result_path, closure["formal_result"])
        if formal_result_sha256 != closure["formal_result_sha256"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_RESULT_DIGEST_MISMATCH:{symbol}")

        formal_input_reference = _artifact_ref(
            output,
            formal_input_path,
            "formal-function-input",
        )
        formal_result_reference = _artifact_ref(
            output,
            formal_result_path,
            "formal-function-result",
        )
        formal_layer = function_report["layers"]["formal"]
        if formal_input_reference["sha256"] != formal_layer["formal_input_digest"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_INPUT_BACKLINK_MISMATCH:{symbol}")
        if solver_reference["sha256"] != formal_layer["solver_input_digest"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_SOLVER_INPUT_BACKLINK_MISMATCH:{symbol}")
        if formal_result_reference["sha256"] != formal_layer["formal_result_sha256"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_RESULT_BACKLINK_MISMATCH:{symbol}")
        expected_header = f"; formal_input_digest: {formal_input_reference['sha256']}"
        if expected_header not in closure["solver_input"]:
            raise RouteError(f"PURE_MODULE_SOLVER_INPUT_HEADER_MISMATCH:{symbol}")
        persisted_result = closure["formal_result"]
        if (
            persisted_result.get("formal_input_digest") != formal_input_reference["sha256"]
            or persisted_result.get("solver_input_digest") != solver_reference["sha256"]
            or persisted_result.get("proof_strength") != "THEOREM_UNDER_ASSUMPTIONS"
            or not persisted_result.get("assumptions")
            or persisted_result.get("countermodel") is not None
            or persisted_result.get("external_soundness_boundary", {}).get("source_compiler_runtime_soundness")
            != "NOT_RUN"
            or persisted_result.get("external_soundness_boundary", {}).get("target_compiler_runtime_soundness")
            != "NOT_RUN"
        ):
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_RESULT_NOT_CLOSED:{symbol}")
        replay_contract = persisted_result.get("replay_contract")
        if not isinstance(replay_contract, dict) or replay_contract != {
            "kind": "z3-cli-check-sat",
            "argv": ["z3", "-smt2", solver_reference["path"]],
            "working_directory": ".",
            "expected_exit_code": 0,
            "expected_stdout": "unsat",
        }:
            raise RouteError(f"PURE_MODULE_FUNCTION_REPLAY_CONTRACT_INVALID:{symbol}")
        artifact_refs.extend([formal_input_reference, solver_reference, formal_result_reference])
    report["artifact_refs"] = artifact_refs
    write_json(output / "typed-pure-module-equivalence.json", report)
    return report


def _load_module_manifest(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RouteError(f"PURE_MODULE_CASE_MANIFEST_DUPLICATE_KEY:{key}")
            result[key] = value
        return result

    try:
        loaded = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_JSON_INVALID") from error
    if not isinstance(loaded, dict):
        raise RouteError("PURE_MODULE_CASE_MANIFEST_MAPPING_REQUIRED")
    return loaded


def _manifest_symbols(manifest: dict[str, Any]) -> list[str]:
    validate_pure_module_manifest_shape(manifest)
    entries = manifest.get("functions")
    if not isinstance(entries, list) or len(entries) < 3:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_AT_LEAST_THREE_FUNCTIONS_REQUIRED")
    symbols: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise RouteError("PURE_MODULE_CASE_MANIFEST_ENTRY_INVALID")
        symbol = str(entry.get("symbol", "")).strip()
        if not symbol or symbol in symbols:
            raise RouteError(f"PURE_MODULE_CASE_MANIFEST_DUPLICATE_SYMBOL:{symbol}")
        symbols.append(symbol)
    return sorted(symbols)


def _combine_function_irs(
    analyzed: list[SemanticIR],
    expected_symbols: list[str],
    language: Language,
    role: str,
) -> SemanticIR:
    if len(analyzed) != len(expected_symbols) or not analyzed:
        raise RouteError(f"PURE_MODULE_ANALYSIS_SET_INCOMPLETE:{role}")
    first = analyzed[0]
    functions: dict[str, Function] = {}
    diagnostics: list[str] = []
    for ir in analyzed:
        if ir.source_language != language or len(ir.functions) != 1:
            raise RouteError(f"PURE_MODULE_ANALYSIS_FUNCTION_SET_INVALID:{role}")
        if ir.analyzer != first.analyzer or ir.analyzer_version != first.analyzer_version:
            raise RouteError(f"PURE_MODULE_ANALYZER_IDENTITY_MISMATCH:{role}")
        function = ir.functions[0]
        if function.name in functions:
            raise RouteError(f"PURE_MODULE_DUPLICATE_SYMBOL:{role}:{function.name}")
        functions[function.name] = function
        diagnostics.extend(ir.diagnostics)
    if sorted(functions) != sorted(expected_symbols):
        raise RouteError(f"PURE_MODULE_ANALYZED_SYMBOL_SET_MISMATCH:{role}")
    return SemanticIR(
        source_language=language,
        source_file=first.source_file,
        analyzer=first.analyzer,
        analyzer_version=first.analyzer_version,
        functions=tuple(functions[symbol] for symbol in expected_symbols),
        diagnostics=tuple(diagnostics),
    )


def _bind_function_spans_from_inventory(
    analyzed_ir: SemanticIR,
    inventory: dict[str, Any],
    *,
    role: str,
) -> SemanticIR:
    """Close named analysis against an independent whole-file inventory.

    Some exact native frontends deliberately keep the named semantic payload
    free of concrete locations while their independent inventory mode owns the
    byte spans.  A module artifact needs both views: the semantic relift and an
    exact declaration span in the same immutable file.  Bind only a unique,
    analyzable, same-named inventory subject, and reject any frontend that
    supplies a conflicting span.
    """

    if (
        inventory.get("source_language") != analyzed_ir.source_language
        or inventory.get("source_file") != analyzed_ir.source_file
    ):
        raise RouteError(f"PURE_MODULE_ANALYSIS_INVENTORY_IDENTITY_MISMATCH:{role}")
    subjects = inventory.get("subjects")
    if not isinstance(subjects, list):
        raise RouteError(f"PURE_MODULE_INVENTORY_SUBJECTS_INVALID:{role}")

    subjects_by_name: dict[str, list[dict[str, Any]]] = {}
    for subject in subjects:
        if not isinstance(subject, dict):
            raise RouteError(f"PURE_MODULE_INVENTORY_SUBJECTS_INVALID:{role}")
        name = subject.get("name")
        if isinstance(name, str):
            subjects_by_name.setdefault(name, []).append(subject)

    bound_functions: list[Function] = []
    for function in analyzed_ir.functions:
        matches = subjects_by_name.get(function.name, [])
        if len(matches) != 1:
            raise RouteError(f"PURE_MODULE_ANALYSIS_INVENTORY_SYMBOL_COUNT_INVALID:{role}:{function.name}")
        subject = matches[0]
        if subject.get("analyzable") is not True:
            raise RouteError(f"PURE_MODULE_ANALYSIS_INVENTORY_SYMBOL_NOT_ANALYZABLE:{role}:{function.name}")
        span_value = subject.get("source_span")
        if not isinstance(span_value, dict):
            raise RouteError(f"PURE_MODULE_INVENTORY_SPAN_REQUIRED:{role}:{function.name}")
        span = SourceSpan.from_mapping(
            span_value,
            _path=f"{role}.inventory.subjects[{function.name}].source_span",
        )
        if span.file != analyzed_ir.source_file:
            raise RouteError(f"PURE_MODULE_ANALYSIS_INVENTORY_SPAN_MISMATCH:{role}:{function.name}")
        if function.source_span is not None and function.source_span != span:
            raise RouteError(f"PURE_MODULE_ANALYSIS_INVENTORY_SPAN_MISMATCH:{role}:{function.name}")
        bound_functions.append(replace(function, source_span=span))
    return replace(analyzed_ir, functions=tuple(bound_functions))


def _module_manifest_signatures(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = manifest.get("functions")
    if not isinstance(entries, list):
        raise RouteError("PURE_MODULE_CASE_MANIFEST_FUNCTIONS_REQUIRED")
    contracts: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RouteError("PURE_MODULE_CASE_MANIFEST_ENTRY_INVALID")
        symbol = entry.get("symbol")
        signature = entry.get("signature")
        if not isinstance(symbol, str) or not symbol or not isinstance(signature, dict):
            raise RouteError("PURE_MODULE_CASE_MANIFEST_ENTRY_INVALID")
        if symbol in contracts:
            raise RouteError(f"PURE_MODULE_CASE_MANIFEST_DUPLICATE_SYMBOL:{symbol}")
        contracts[symbol] = signature
    return contracts


def _inventory_span(subject: dict[str, Any], role: str) -> tuple[int, int]:
    span = subject.get("source_span")
    qualified_name = str(subject.get("qualified_name", subject.get("name", "unknown")))
    if not isinstance(span, dict):
        raise RouteError(f"PURE_MODULE_INVENTORY_SPAN_REQUIRED:{role}:{qualified_name}")
    start = span.get("start_byte")
    end = span.get("end_byte")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        raise RouteError(f"PURE_MODULE_INVENTORY_SPAN_REQUIRED:{role}:{qualified_name}")
    return start, end


def _verify_inventory_analyzer_build_receipt(
    inventory: dict[str, Any],
    *,
    role: str,
    language: Language,
) -> None:
    """Fail closed around the private Swift analyzer build provenance.

    The complete receipt remains in the inventory object.  Consequently its
    exact bytes are covered by the inventory digest, whole-file-closure digest,
    and canonical module input below.  A fresh verifier compares only the
    receipt's canonical, path-independent build projection and independently
    recomputes its digest. The full observed receipt remains byte-bound too.
    """

    receipt = inventory.get("analyzer_build_receipt")
    if language != "swift":
        if "analyzer_build_receipt" in inventory:
            raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_UNEXPECTED:{role}:{language}")
        return
    if not isinstance(receipt, dict) or set(receipt) != {
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
    }:
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    if receipt.get("schema_version") != "1.0.0" or receipt.get("kind") != "elmos.swift-analyzer-build-receipt":
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")

    source_inputs = receipt.get("source_inputs")
    dependency = receipt.get("dependency")
    toolchain = receipt.get("toolchain")
    build = receipt.get("build")
    binary = receipt.get("binary")
    network_isolation = receipt.get("network_isolation")
    execution_seal = receipt.get("execution_seal")
    canonical_identity = receipt.get("canonical_identity")
    if (
        not isinstance(source_inputs, dict)
        or set(source_inputs) != {"sha256", "files"}
        or not isinstance(dependency, dict)
        or set(dependency)
        != {
            "identity",
            "version",
            "revision",
            "sha256",
            "file_count",
            "bytes",
            "mirror",
        }
        or not isinstance(toolchain, dict)
        or set(toolchain)
        != {
            "swiftc",
            "swiftc_sha256",
            "swift_driver",
            "swift_driver_sha256",
            "version",
            "profile",
            "build_closure",
        }
        or not isinstance(build, dict)
        or set(build)
        != {
            "configuration",
            "automatic_resolution",
            "manifest_cache",
            "environment_policy",
            "deterministic_environment",
            "mtime_normalization",
            "reproducible_path_policy",
            "argv",
        }
        or not isinstance(binary, dict)
        or set(binary) != {"name", "path", "sha256", "bytes", "mode", "uid", "gid", "nlink", "device", "inode"}
        or not isinstance(network_isolation, dict)
        or not isinstance(execution_seal, dict)
        or not isinstance(canonical_identity, dict)
        or set(canonical_identity) != {"sha256", "receipt"}
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")

    files = source_inputs.get("files")
    if not isinstance(files, list) or not files:
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    file_paths: list[str] = []
    for item in files:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "sha256", "bytes"}
            or not isinstance(item.get("path"), str)
            or not item["path"]
            or Path(item["path"]).is_absolute()
            or ".." in Path(item["path"]).parts
            or not isinstance(item.get("bytes"), int)
            or item["bytes"] <= 0
        ):
            raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
        file_paths.append(item["path"])
        _require_sha256(str(item.get("sha256")), f"{role}_swift_analyzer_input")
    if (
        len(set(file_paths)) != len(file_paths)
        or file_paths[:2] != ["Package.swift", "Package.resolved"]
        or file_paths[2:] != sorted(file_paths[2:])
        or not all(path.startswith("Sources/") and path.endswith(".swift") for path in file_paths[2:])
        or source_inputs.get("sha256")
        != _digest(
            json.dumps(
                {"files": files},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INPUT_CLOSURE_MISMATCH:{role}:swift")

    mirror = dependency.get("mirror")
    if (
        dependency.get("identity") != "swift-syntax"
        or dependency.get("version") != "600.0.1"
        or dependency.get("revision") != "0687f71944021d616d34d922343dcef086855920"
        or dependency.get("sha256") != "sha256:b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
        or dependency.get("file_count") != 753
        or dependency.get("bytes") != 8_866_479
        or not isinstance(mirror, dict)
        or set(mirror)
        != {
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
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    _require_sha256(str(source_inputs.get("sha256")), f"{role}_swift_analyzer_inputs")
    _require_sha256(str(dependency.get("sha256")), f"{role}_swift_analyzer_dependency")
    _require_sha256(str(mirror.get("sha256")), f"{role}_swift_analyzer_mirror")
    git = mirror.get("git")
    cache = mirror.get("cache")
    if (
        mirror.get("seed") != "verified-content-addressed-standalone-cache"
        or mirror.get("identity") != dependency.get("identity")
        or mirror.get("version") != dependency.get("version")
        or mirror.get("revision") != dependency.get("revision")
        or mirror.get("sha256") != dependency.get("sha256")
        or mirror.get("file_count") != dependency.get("file_count")
        or mirror.get("bytes") != dependency.get("bytes")
        or not isinstance(git, dict)
        or set(git) != {"path", "sha256", "version"}
        or git.get("path") != "/Applications/Xcode.app/Contents/Developer/usr/bin/git"
        or git.get("sha256") != "sha256:10f9c1df894525ae4c7454258febab6d3d25071062b42cb48dbb1842cdffd2a9"
        or git.get("version") != "git version 2.50.1 (Apple Git-155)"
        or not isinstance(cache, dict)
        or set(cache)
        != {
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
        or cache.get("cache_key")
        != (
            "swift-syntax-standalone-v2-600.0.1-0687f71944021d616d34d922343dcef086855920-"
            "b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
        )
        or cache.get("cache_schema") != "swift-dependencies-standalone-v2"
        or cache.get("object_store_policy") != "standalone-no-alternates-no-hardlinks-v2"
        or cache.get("seed") != "verified-content-addressed-standalone-cache"
        or cache.get("identity") != dependency.get("identity")
        or cache.get("version") != dependency.get("version")
        or cache.get("revision") != dependency.get("revision")
        or cache.get("sha256") != dependency.get("sha256")
        or cache.get("file_count") != dependency.get("file_count")
        or cache.get("bytes") != dependency.get("bytes")
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    _require_sha256(str(git.get("sha256")), f"{role}_swift_analyzer_git")
    if (
        dependency["sha256"] != mirror["sha256"]
        or dependency["file_count"] != mirror["file_count"]
        or dependency["bytes"] != mirror["bytes"]
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_DEPENDENCY_MISMATCH:{role}:swift")

    expected_build = {
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
    binary_path = Path(str(binary.get("path", "")))
    if (
        toolchain != _swift_toolchain_receipt(exact_toolchain("swift"))
        or build != expected_build
        or binary.get("name") != "ElmosSwiftAnalyzer"
        or not binary_path.is_absolute()
        or binary_path.name != "ElmosSwiftAnalyzer"
        or not binary_path.parent.name.startswith("elmos-swift-analyzer-")
        or not isinstance(binary.get("bytes"), int)
        or not 0 < binary["bytes"] <= 100_000_000
        or binary.get("mode") != "0500"
        or binary.get("uid") != os.getuid()
        or binary.get("gid") != os.getgid()
        or binary.get("nlink") != 1
        or not isinstance(binary.get("device"), int)
        or binary["device"] <= 0
        or not isinstance(binary.get("inode"), int)
        or binary["inode"] <= 0
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    _require_sha256(str(toolchain.get("swiftc_sha256")), f"{role}_swiftc")
    _require_sha256(str(toolchain.get("swift_driver_sha256")), f"{role}_swift_driver")
    _require_sha256(str(binary.get("sha256")), f"{role}_swift_analyzer_binary")

    policy_text = "(version 1)\n(allow default)\n(deny network*)\n"
    expected_network_prefix = {
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
            "text": policy_text,
            "sha256": "sha256:5c358b8d847211333e7ba22df82d84f796b5f30a41a2682209a949d783adbd08",
            "bytes": 44,
        },
    }
    if set(network_isolation) != {"status", "scope", "sandbox", "verifier", "policy", "probe"} or any(
        network_isolation.get(key) != value for key, value in expected_network_prefix.items()
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_NETWORK_ISOLATION_INVALID:{role}:swift")
    probe = network_isolation.get("probe")
    if not isinstance(probe, dict) or set(probe) != {
        "result",
        "source",
        "build",
        "binary",
        "execution_seal",
        "mach_o",
    }:
        raise RouteError(f"PURE_MODULE_ANALYZER_NETWORK_ISOLATION_INVALID:{role}:swift")
    probe_source = probe.get("source")
    probe_build = probe.get("build")
    probe_binary = probe.get("binary")
    probe_execution_seal = probe.get("execution_seal")
    probe_mach_o = probe.get("mach_o")
    closure_components = toolchain["build_closure"].get("components")
    probe_compilers = (
        [item for item in closure_components if isinstance(item, dict) and item.get("role") == "clang"]
        if isinstance(closure_components, list)
        else []
    )
    if len(probe_compilers) != 1:
        raise RouteError(f"PURE_MODULE_ANALYZER_NETWORK_ISOLATION_INVALID:{role}:swift")
    expected_probe_source = {
        "text": _SANDBOX_NETWORK_PROBE_SOURCE,
        "sha256": "sha256:" + _SANDBOX_NETWORK_PROBE_SOURCE_SHA256,
        "bytes": _SANDBOX_NETWORK_PROBE_SOURCE_BYTES,
    }
    expected_probe_build = {
        "environment_policy": "sanitized-swift-build-deterministic-v1",
        "argv": list(_SANDBOX_NETWORK_PROBE_BUILD_ARGV),
        "environment": dict(_SANDBOX_NETWORK_PROBE_BUILD_ENVIRONMENT),
        "compiler": probe_compilers[0],
    }
    if (
        probe.get("result") != "NETWORK_DENIED:1"
        or probe_source != expected_probe_source
        or not isinstance(probe_build, dict)
        or set(probe_build) != {"environment_policy", "argv", "environment", "compiler"}
        or probe_build != expected_probe_build
        or not isinstance(probe_binary, dict)
        or set(probe_binary) != {"name", "path", "sha256", "bytes", "mode", "uid", "gid", "nlink", "device", "inode"}
        or not isinstance(probe_execution_seal, dict)
        or set(probe_execution_seal) != {"policy", "root", "mode", "uid", "gid", "device", "inode", "binary"}
        or not isinstance(probe_mach_o, dict)
        or set(probe_mach_o) != {"architecture", "file_type", "uuid", "cdhash_full", "linked_libraries"}
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_NETWORK_ISOLATION_INVALID:{role}:swift")
    probe_binary_path = Path(str(probe_binary.get("path", "")))
    probe_seal_root = Path(str(probe_execution_seal.get("root", "")))
    if (
        probe_binary.get("name") != _SANDBOX_NETWORK_PROBE_BINARY_NAME
        or probe_binary.get("sha256") != "sha256:" + _SANDBOX_NETWORK_PROBE_BINARY_SHA256
        or probe_binary.get("bytes") != _SANDBOX_NETWORK_PROBE_BINARY_BYTES
        or probe_binary.get("mode") != "0500"
        or probe_binary.get("uid") != os.getuid()
        or not isinstance(probe_binary.get("gid"), int)
        or probe_binary.get("nlink") != 1
        or not isinstance(probe_binary.get("device"), int)
        or probe_binary["device"] <= 0
        or not isinstance(probe_binary.get("inode"), int)
        or probe_binary["inode"] <= 0
        or not probe_binary_path.is_absolute()
        or probe_binary_path.name != _SANDBOX_NETWORK_PROBE_BINARY_NAME
        or probe_binary_path.parent.name != "network-probe-execution"
        or probe_binary_path.parent.parent != binary_path.parent
        or probe_execution_seal.get("policy") != "private-nonwritable-execution-root-v1"
        or probe_execution_seal.get("mode") != "0500"
        or probe_execution_seal.get("uid") != probe_binary.get("uid")
        or probe_execution_seal.get("gid") != probe_binary.get("gid")
        or probe_execution_seal.get("device") != probe_binary.get("device")
        or not isinstance(probe_execution_seal.get("inode"), int)
        or probe_execution_seal["inode"] <= 0
        or probe_execution_seal.get("binary") != probe_binary
        or probe_seal_root != probe_binary_path.parent
        or probe_mach_o
        != {
            "architecture": "arm64",
            "file_type": "MH_EXECUTE",
            "uuid": _SANDBOX_NETWORK_PROBE_UUID,
            "cdhash_full": _SANDBOX_NETWORK_PROBE_CDHASH_FULL,
            "linked_libraries": list(_SANDBOX_NETWORK_PROBE_LINKED_LIBRARIES),
        }
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_NETWORK_ISOLATION_INVALID:{role}:swift")
    _require_sha256(str(probe_source.get("sha256")), f"{role}_swift_network_probe_source")
    _require_sha256(str(probe_binary.get("sha256")), f"{role}_swift_network_probe_binary")
    if (
        set(execution_seal) != {"policy", "root", "mode", "uid", "gid", "device", "inode", "binary"}
        or execution_seal.get("policy") != "private-nonwritable-execution-root-v1"
        or execution_seal.get("mode") != "0500"
        or execution_seal.get("uid") != binary.get("uid")
        or execution_seal.get("gid") != binary.get("gid")
        or execution_seal.get("device") != binary.get("device")
        or not isinstance(execution_seal.get("inode"), int)
        or execution_seal["inode"] <= 0
        or Path(str(execution_seal.get("root", ""))) != binary_path.parent
        or execution_seal.get("binary") != binary
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_EXECUTION_SEAL_INVALID:{role}:swift")
    canonical_receipt = _canonical_swift_analyzer_receipt(receipt)
    canonical_digest = _canonical_digest(canonical_receipt)

    def contains_absolute_path(value: object) -> bool:
        if isinstance(value, dict):
            return any(contains_absolute_path(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_absolute_path(item) for item in value)
        return isinstance(value, str) and Path(value).is_absolute()

    if (
        contains_absolute_path(canonical_receipt)
        or canonical_identity.get("receipt") != canonical_receipt
        or canonical_identity.get("sha256") != canonical_digest
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_CANONICAL_IDENTITY_INVALID:{role}:swift")

    analyzer_version = inventory.get("analyzer_version")
    canonical_toolchain = _canonical_swift_toolchain_identity(toolchain)
    expected_suffix = (
        f";source-inputs={source_inputs['sha256']};"
        f"swift-driver={toolchain['swift_driver_sha256']};"
        f"swift-syntax-tree={dependency['sha256']};"
        f"canonical-receipt={canonical_digest};binary={binary['sha256']};"
        f"toolchain={_canonical_digest(canonical_toolchain)};"
        f"build-closure={_canonical_digest(canonical_toolchain['build_closure'])};"
        f"network-policy={network_isolation['policy']['sha256']}"
    )
    if not isinstance(analyzer_version, str) or not analyzer_version.endswith(expected_suffix):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_BINDING_MISMATCH:{role}:swift")


def _verify_inventory_artifact(
    inventory: dict[str, Any],
    *,
    role: str,
    language: Language,
    logical_file: str,
    artifact_bytes: bytes,
) -> None:
    expected_keys = {
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
    if language == "swift":
        expected_keys.add("analyzer_build_receipt")
    if set(inventory) != expected_keys:
        raise RouteError(f"PURE_MODULE_INVENTORY_KEYS_INVALID:{role}:{language}")
    if inventory.get("enumeration_status") != "PASSED":
        raise RouteError(f"PURE_MODULE_INVENTORY_STATUS_NOT_PASSED:{role}")
    if inventory.get("diagnostics") != []:
        raise RouteError(f"PURE_MODULE_INVENTORY_DIAGNOSTICS_PRESENT:{role}")
    if (
        inventory.get("source_language") != language
        or inventory.get("source_file") != logical_file
        or inventory.get("source_artifact_sha256") != _digest(artifact_bytes)
        or inventory.get("source_artifact_bytes") != len(artifact_bytes)
    ):
        raise RouteError(f"PURE_MODULE_INVENTORY_ARTIFACT_MISMATCH:{role}")
    _verify_inventory_analyzer_build_receipt(inventory, role=role, language=language)


def _verify_language_prelude(
    inventory: dict[str, Any],
    *,
    role: str,
    language: Language,
    artifact_bytes: bytes,
) -> dict[str, Any]:
    expected_directives = {
        ("cpp", "source"): [(b"#include <cstdint>", "include", "<cstdint>")],
        ("cpp", "target"): [
            (b"#include <cstdint>", "include", "<cstdint>"),
            (b"#include <stdexcept>", "include", "<stdexcept>"),
            (b"#include <string>", "include", "<string>"),
        ],
        ("objc", "source"): [
            (b"#import <Foundation/Foundation.h>", "import", "<Foundation/Foundation.h>")
        ],
        ("objc", "target"): [
            (b"#import <Foundation/Foundation.h>", "import", "<Foundation/Foundation.h>")
        ],
        ("php", "source"): [
            (b"declare(strict_types=1);", "declare", "strict_types=1")
        ],
        ("php", "target"): [
            (b"declare(strict_types=1);", "declare", "strict_types=1")
        ],
    }.get((language, role), [])
    directives = inventory.get("directives")
    if not isinstance(directives, list):
        raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_INVENTORY_INVALID:{role}")
    if len(directives) != len(expected_directives):
        raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_MISMATCH:{role}:{language}")
    for order, (directive, expected) in enumerate(zip(directives, expected_directives, strict=True)):
        if not isinstance(directive, dict) or set(directive) != {
            "order",
            "kind",
            "value",
            "source_span",
            "sha256",
        }:
            raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_INVENTORY_INVALID:{role}")
        source_span = directive.get("source_span")
        if not isinstance(source_span, dict):
            raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_INVENTORY_INVALID:{role}")
        start = source_span.get("start_byte")
        end = source_span.get("end_byte")
        observed = artifact_bytes[start:end] if isinstance(start, int) and isinstance(end, int) else b""
        expected_raw, expected_kind, expected_value = expected
        if (
            directive.get("order") != order
            or directive.get("kind") != expected_kind
            or directive.get("value") != expected_value
            or source_span.get("file") != inventory.get("source_file")
            or observed != expected_raw
            or directive.get("sha256") != _digest(expected_raw)
        ):
            raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_MISMATCH:{role}:{language}")
    return {
        "status": "EXACT_AND_CLOSED",
        "role": role,
        "language": language,
        "directives": directives,
    }


def _separate_verified_language_wrapper(
    inventory: dict[str, Any],
    *,
    role: str,
    language: Language,
) -> tuple[dict[str, Any], dict[str, Any]]:
    subjects = inventory.get("subjects")
    if not isinstance(subjects, list):
        raise RouteError(f"PURE_MODULE_INVENTORY_SUBJECTS_INVALID:{role}")
    wrappers = [
        subject
        for subject in subjects
        if isinstance(subject, dict) and subject.get("declaration_kind") == "top-level-class-wrapper"
    ]
    if language != "java":
        if wrappers:
            raise RouteError(f"PURE_MODULE_LANGUAGE_WRAPPER_UNEXPECTED:{role}:{language}")
        return inventory, {
            "status": "NOT_APPLICABLE",
            "role": role,
            "language": language,
            "file": inventory.get("source_file"),
        }
    if len(wrappers) != 1:
        raise RouteError(f"PURE_MODULE_LANGUAGE_WRAPPER_COUNT_MISMATCH:{role}:{len(wrappers)}")
    wrapper = wrappers[0]
    expected_name = Path(str(inventory.get("source_file"))).stem
    if (
        wrapper.get("name") != expected_name
        or wrapper.get("qualified_name") != expected_name
        or wrapper.get("analyzable") is not False
        or wrapper.get("occurrence") != 1
    ):
        raise RouteError(f"PURE_MODULE_LANGUAGE_WRAPPER_IDENTITY_MISMATCH:{role}")
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
    if wrapper.get("signature") != expected_signature:
        raise RouteError(f"PURE_MODULE_LANGUAGE_WRAPPER_SIGNATURE_MISMATCH:{role}")
    wrapper_start, wrapper_end = _inventory_span(wrapper, role)
    members: list[dict[str, Any]] = []
    member_kinds = {
        "constructor",
        "field",
        "instance-initializer",
        "method",
        "nested-type",
        "static-initializer",
    }
    for subject in subjects:
        if subject is wrapper or not isinstance(subject, dict):
            continue
        if subject.get("declaration_kind") not in member_kinds:
            continue
        start, end = _inventory_span(subject, role)
        if not (wrapper_start <= start and end <= wrapper_end):
            raise RouteError(
                f"PURE_MODULE_LANGUAGE_WRAPPER_SPAN_CONTAINMENT_MISMATCH:{role}:{subject.get('qualified_name')}"
            )
        members.append(
            {
                "name": subject["name"],
                "qualified_name": subject["qualified_name"],
                "declaration_kind": subject["declaration_kind"],
                "occurrence": subject["occurrence"],
                "source_span": subject["source_span"],
            }
        )
    filtered_inventory = {
        **inventory,
        "subjects": [subject for subject in subjects if subject is not wrapper],
    }
    return filtered_inventory, {
        "status": "EXACT_AND_CLOSED",
        "role": role,
        "language": language,
        "file": inventory["source_file"],
        "name": wrapper["name"],
        "qualified_name": wrapper["qualified_name"],
        "declaration_kind": wrapper["declaration_kind"],
        "analyzable": wrapper["analyzable"],
        "occurrence": wrapper["occurrence"],
        "source_span": wrapper["source_span"],
        "signature": wrapper["signature"],
        "member_span_status": "ALL_CONTAINED",
        "member_subjects": sorted(
            members,
            key=lambda item: (
                int(item["source_span"]["start_byte"]),
                str(item["qualified_name"]),
            ),
        ),
    }


def _verify_profile_subject_contract(
    language: Language,
    subject: dict[str, Any],
    *,
    role: str,
    symbol: str,
) -> None:
    expected = {
        "cpp": ("FunctionDecl", "external", "none"),
        "objc": ("FunctionDecl", "external", "none"),
        "swift": ("FunctionDeclSyntax", "internal", "file-scope"),
        "java": ("method", "public", "static"),
    }.get(language)
    if expected is None:
        return
    signature = subject.get("signature")
    if not isinstance(signature, dict):
        raise RouteError(f"PURE_MODULE_PROFILE_SIGNATURE_MISMATCH:{role}:{symbol}")
    declaration_kind, visibility, storage = expected
    if (
        subject.get("declaration_kind") != declaration_kind
        or signature.get("visibility") != visibility
        or signature.get("storage") != storage
    ):
        raise RouteError(f"PURE_MODULE_PROFILE_DECLARATION_CONTRACT_MISMATCH:{role}:{symbol}")
    if language == "java" and signature.get("modifiers") != ["public", "static"]:
        raise RouteError(f"PURE_MODULE_PROFILE_DECLARATION_CONTRACT_MISMATCH:{role}:{symbol}")


def _profile_symbol_record(
    subject: dict[str, Any],
    raw_function: Function,
    canonical_function: Function,
    *,
    role: str,
) -> dict[str, Any]:
    signature = subject.get("signature")
    assert isinstance(signature, dict)
    raw_parameters = signature.get("parameters")
    if not isinstance(raw_parameters, list):
        raw_parameters = []
    if raw_function.source_span is None or raw_function.source_span.to_mapping() != subject.get("source_span"):
        raise RouteError(f"PURE_MODULE_PROFILE_SPAN_MISMATCH:{role}:{raw_function.name}")
    return {
        "symbol": canonical_function.name,
        "raw_symbol": raw_function.name,
        "canonical_symbol": canonical_function.name,
        "qualified_name": subject["qualified_name"],
        "declaration_kind": subject["declaration_kind"],
        "occurrence": subject["occurrence"],
        "source_span": subject["source_span"],
        "raw_signature": signature,
        "raw_parameter_names": [parameter.get("name") for parameter in raw_parameters if isinstance(parameter, dict)],
        "canonical_signature": canonical_function.signature_mapping(),
    }


def _close_profile_inventory(
    inventory: dict[str, Any],
    raw_ir: SemanticIR,
    manifest_signatures: dict[str, dict[str, Any]],
    *,
    role: str,
    helper_regions: list[dict[str, Any]] | None = None,
    canonical_functions_by_raw: dict[str, Function] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_functions = {function.name: function for function in raw_ir.functions}
    if len(raw_functions) != len(raw_ir.functions):
        raise RouteError(f"PURE_MODULE_PROFILE_SYMBOL_DUPLICATED:{role}")
    canonical_by_raw = canonical_functions_by_raw or raw_functions
    if set(canonical_by_raw) != set(raw_functions):
        raise RouteError(f"PURE_MODULE_PROFILE_RAW_SYMBOL_SET_MISMATCH:{role}")
    canonical_functions = {function.name: function for function in canonical_by_raw.values()}
    if len(canonical_functions) != len(canonical_by_raw):
        raise RouteError(f"PURE_MODULE_PROFILE_CANONICAL_SYMBOL_DUPLICATED:{role}")
    if set(canonical_functions) != set(manifest_signatures):
        raise RouteError(f"PURE_MODULE_PROFILE_SYMBOL_SET_MISMATCH:{role}")
    for symbol, function in canonical_functions.items():
        if function.signature_mapping() != manifest_signatures[symbol]:
            raise RouteError(f"PURE_MODULE_PROFILE_SIGNATURE_MISMATCH:{role}:{symbol}")

    profile_subjects: dict[str, dict[str, Any]] = {}
    helper_subjects: list[dict[str, Any]] = []
    subjects = inventory.get("subjects")
    if not isinstance(subjects, list):
        raise RouteError(f"PURE_MODULE_INVENTORY_SUBJECTS_INVALID:{role}")
    for subject in subjects:
        if not isinstance(subject, dict):
            raise RouteError(f"PURE_MODULE_INVENTORY_SUBJECTS_INVALID:{role}")
        start, end = _inventory_span(subject, role)
        matched_helpers = [
            region for region in helper_regions or [] if region["start_byte"] <= start and end <= region["end_byte"]
        ]
        if len(matched_helpers) > 1:
            raise RouteError("PURE_MODULE_TARGET_HELPER_REGION_OVERLAP")
        if matched_helpers:
            helper_subjects.append({**subject, "helper_id": matched_helpers[0]["helper_id"]})
            continue

        raw_symbol = subject.get("name")
        qualified_name = str(subject.get("qualified_name", raw_symbol or "unknown"))
        declaration_kind = str(subject.get("declaration_kind", "unknown"))
        if not isinstance(raw_symbol, str) or raw_symbol not in raw_functions:
            raise RouteError(
                f"PURE_MODULE_WHOLE_FILE_DECLARATION_NOT_ALLOWED:{role}:{declaration_kind}:{qualified_name}"
            )
        symbol = raw_symbol
        if subject.get("analyzable") is not True:
            raise RouteError(f"PURE_MODULE_PROFILE_SYMBOL_NOT_ANALYZABLE:{role}:{qualified_name}")
        if symbol in profile_subjects:
            raise RouteError(f"PURE_MODULE_PROFILE_SYMBOL_DUPLICATED:{role}:{symbol}")
        _verify_profile_subject_contract(
            raw_ir.source_language,
            subject,
            role=role,
            symbol=symbol,
        )
        profile_subjects[symbol] = subject

    if set(profile_subjects) != set(raw_functions):
        raise RouteError(f"PURE_MODULE_PROFILE_SYMBOL_SET_MISMATCH:{role}")

    records: list[dict[str, Any]] = []
    for raw_symbol in sorted(raw_functions, key=lambda symbol: canonical_by_raw[symbol].name):
        raw_function = raw_functions[raw_symbol]
        canonical_function = canonical_by_raw[raw_symbol]
        subject = profile_subjects[raw_symbol]
        record = _profile_symbol_record(subject, raw_function, canonical_function, role=role)
        expected_parameter_names = [parameter.name for parameter in raw_function.parameters]
        if record["raw_parameter_names"] != expected_parameter_names:
            raise RouteError(f"PURE_MODULE_PROFILE_SIGNATURE_MISMATCH:{role}:{raw_symbol}")
        records.append(record)
    return records, helper_subjects


def _emitted_helper_regions(emitted: EmittedFile, target_language: Language) -> list[dict[str, Any]]:
    registry = _HELPERS.get(target_language, {})
    emitted_bytes = emitted.content.encode("utf-8")
    regions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for helper_id, claimed_digest in emitted.helper_digests:
        if helper_id in seen:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_DUPLICATED:{helper_id}")
        seen.add(helper_id)
        helper_source = registry.get(helper_id)
        if helper_source is None:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_UNREGISTERED:{helper_id}")
        helper_bytes = helper_source.encode("utf-8")
        observed_digest = _digest(helper_bytes)
        if claimed_digest != observed_digest:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_DIGEST_MISMATCH:{helper_id}")
        if emitted_bytes.count(helper_bytes) != 1:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_SOURCE_COUNT_INVALID:{helper_id}")
        start = emitted_bytes.index(helper_bytes)
        regions.append(
            {
                "helper_id": helper_id,
                "sha256": observed_digest,
                "bytes": len(helper_bytes),
                "start_byte": start,
                "end_byte": start + len(helper_bytes),
            }
        )
    return sorted(regions, key=lambda item: (item["start_byte"], item["helper_id"]))


def _verify_helper_visibility(language: Language, subject: dict[str, Any]) -> tuple[str, str]:
    signature = subject.get("signature")
    if not isinstance(signature, dict):
        raise RouteError("PURE_MODULE_TARGET_HELPER_SIGNATURE_INVALID")
    visibility = signature.get("visibility")
    storage = signature.get("storage")
    allowed = {
        "cpp": {("internal", "static")},
        "javascript": {("internal", "file-scope")},
        "objc": {("internal", "static")},
        "java": {("private", "static")},
        "swift": {("private", "file-scope"), ("fileprivate", "file-scope")},
        "typescript": {("internal", "file-scope")},
        "react": {("internal", "file-scope")},
        "kotlin": {("private", "file-scope")},
        "flutter": {("private", "file-scope")},
        # PHP has no file-private function scope: a `function` at file scope is
        # unconditionally global, and no `static`/`private` spelling changes
        # that. This value describes the *emitted* unit, which is what the
        # analyzer inventories, and for that artifact ("external", "none") is
        # simply true -- claiming a privacy PHP does not have would be worse
        # than recording the weaker guarantee.
        #
        # Two compensating controls carry what the visibility does not.
        # `identifier_hygiene._FORBIDDEN["php"]` reserves every helper name, so
        # a converted identifier can never be allocated one. And
        # `assembly._place_php` puts each assembled unit in its own namespace,
        # which is what actually makes a multi-unit project loadable -- without
        # it two units that both need `elmos_checked_add` are a fatal "Cannot
        # redeclare function" the moment Composer autoloads the second.
        "php": {("external", "none")},
    }.get(language, set())
    if (visibility, storage) not in allowed:
        raise RouteError(
            f"PURE_MODULE_TARGET_HELPER_VISIBILITY_INVALID:{subject.get('helper_id')}:{subject.get('qualified_name')}"
        )
    if language == "javascript":
        expected = {
            "safe_integer": ("_elmosRequireSafeInteger", "integer", "integer"),
            "finite_number": ("_elmosRequireFiniteNumber", "number", "number"),
            "exact_boolean": ("_elmosRequireBoolean", "boolean", "boolean"),
            "exact_string": ("_elmosRequireString", "string", "string"),
            "non_zero": ("_elmosRequireNonZero", "number", "number"),
        }.get(str(subject.get("helper_id")))
        if expected is None:
            raise RouteError("PURE_MODULE_TARGET_HELPER_SIGNATURE_INVALID")
        name, parameter_type, return_type = expected
        expected_signature = {
            "parameters": [{"name": "value", "source_type": parameter_type}],
            "source_return_type": return_type,
            "visibility": "internal",
            "storage": "file-scope",
        }
        if (
            subject.get("name") != name
            or subject.get("qualified_name") != name
            or subject.get("declaration_kind") != "FunctionDeclaration"
            or signature != expected_signature
        ):
            raise RouteError("PURE_MODULE_TARGET_HELPER_SIGNATURE_INVALID")
    if language in {"typescript", "react"}:
        expected = {
            "safe_integer": ("_elmosRequireSafeInteger", "integer", "integer"),
            "finite_number": ("_elmosRequireFiniteNumber", "number", "number"),
            "non_zero": ("_elmosRequireNonZero", "number", "number"),
        }.get(str(subject.get("helper_id")))
        if expected is None:
            raise RouteError("PURE_MODULE_TARGET_HELPER_SIGNATURE_INVALID")
        name, parameter_type, return_type = expected
        expected_signature = {
            "parameters": [{"name": "value", "source_type": parameter_type}],
            "source_return_type": return_type,
            "visibility": "internal",
            "storage": "file-scope",
        }
        if (
            subject.get("name") != name
            or subject.get("qualified_name") != name
            or subject.get("declaration_kind") != "FunctionDeclaration"
            or signature != expected_signature
        ):
            raise RouteError("PURE_MODULE_TARGET_HELPER_SIGNATURE_INVALID")
    return str(visibility), str(storage)


def _specialized_helper_contract(
    language: Language,
    helper_id: str,
) -> tuple[str, str, int]:
    candidates: set[tuple[str, int]] = set()
    for callee, helper_ids in _CHECKED_INTEGER_CALL.get(language, {}).values():
        if helper_id in helper_ids:
            candidates.add((callee, 2))
    float_guard = _FLOAT_NON_ZERO_GUARD.get(language)
    if float_guard is not None and helper_id == float_guard[1]:
        candidates.add((float_guard[0], 1))
    if len(candidates) != 1:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_CONTRACT_MISSING:{helper_id}")
    qualified_name, arity = candidates.pop()
    return qualified_name.rsplit(".", 1)[-1], qualified_name, arity


def _verify_specialized_helper_subject(
    *,
    language: Language,
    region: dict[str, Any],
    symbols: list[dict[str, Any]],
    target_bytes: bytes,
) -> None:
    helper_id = str(region["helper_id"])
    if len(symbols) != 1:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SUBJECT_SET_MISMATCH:{helper_id}")
    symbol = symbols[0]
    if symbol.get("analyzable") is not True:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_NOT_ANALYZABLE:{helper_id}")
    expected_kinds = {
        "cpp": "FunctionDecl",
        "objc": "FunctionDecl",
        "java": "method",
        "swift": "FunctionDeclSyntax",
        "php": "Stmt_Function",
    }
    if symbol.get("declaration_kind") != expected_kinds[language]:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_DECLARATION_KIND_INVALID:{helper_id}")
    expected_name, expected_qualified_name, expected_arity = _specialized_helper_contract(language, helper_id)
    if symbol.get("name") != expected_name or symbol.get("qualified_name") not in {
        expected_name,
        expected_qualified_name,
    }:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_NAME_MISMATCH:{helper_id}")
    signature = symbol.get("raw_signature")
    parameters = signature.get("parameters") if isinstance(signature, dict) else None
    if not isinstance(parameters, list) or len(parameters) != expected_arity:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SIGNATURE_MISMATCH:{helper_id}")
    if symbol.get("occurrence") != 1:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_OCCURRENCE_INVALID:{helper_id}")
    source_span = symbol.get("source_span")
    if not isinstance(source_span, dict):
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SPAN_COVERAGE_INVALID:{helper_id}")
    start = source_span.get("start_byte")
    end = source_span.get("end_byte")
    if not isinstance(start, int) or not isinstance(end, int):
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SPAN_COVERAGE_INVALID:{helper_id}")
    prefix = target_bytes[int(region["start_byte"]) : start]
    suffix = target_bytes[end : int(region["end_byte"])]
    if prefix.strip() or suffix.strip():
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SPAN_COVERAGE_INVALID:{helper_id}")


def _function_operator_uses(function: Function) -> set[tuple[str, str]]:
    environment = types.check_function(function)
    uses: set[tuple[str, str]] = set()

    def expression_uses(expression: Expression) -> None:
        if expression.kind != "binary" or expression.left is None or expression.right is None:
            return
        left_type = types.infer(expression.left, environment)
        right_type = types.infer(expression.right, environment)
        domain = "integer" if left_type == right_type == "integer" else "number"
        uses.add((domain, str(expression.operator)))
        expression_uses(expression.left)
        expression_uses(expression.right)

    def statement_uses(statement: Statement) -> None:
        if statement.expression is not None:
            expression_uses(statement.expression)
        if statement.condition is not None:
            expression_uses(statement.condition)
        for nested in (*statement.then_body, *statement.else_body):
            statement_uses(nested)

    for statement in function.body:
        statement_uses(statement)
    return uses


def _javascript_guard_edges(
    raw_target_ir: SemanticIR,
    canonical_functions_by_raw: dict[str, Function],
    emitted: EmittedFile,
    helper_ids: set[str],
    helper_identifiers: set[str],
) -> list[dict[str, Any]]:
    if raw_target_ir.source_language != "javascript":
        return []

    guards = {
        "integer": ("_elmosRequireSafeInteger", "safe_integer"),
        "number": ("_elmosRequireFiniteNumber", "finite_number"),
        "boolean": ("_elmosRequireBoolean", "exact_boolean"),
        "string": ("_elmosRequireString", "exact_string"),
    }
    return_rules = {
        "integer": "javascript.return.integer.safe-integer",
        "number": "javascript.return.number.finite",
        "boolean": "javascript.return.boolean.exact",
        "string": "javascript.return.string.exact",
    }
    emitted_rules = set(emitted.normalization_rules)
    expected_rules: set[str] = set()
    edges: list[dict[str, Any]] = []

    def append_guard(
        *,
        raw_function: Function,
        canonical_function: Function,
        domain: str,
        rule: str,
        scope: str,
        subject: str,
        operator: str,
        callee: str,
        helper_id: str,
        canonical_subject: str | None = None,
    ) -> None:
        expected_rules.add(rule)
        if helper_id not in helper_ids or callee not in helper_identifiers:
            raise RouteError(f"PURE_MODULE_TARGET_CALL_GRAPH_HELPER_MISMATCH:{rule}")
        edges.append(
            {
                "caller": raw_function.name,
                "canonical_caller": canonical_function.name,
                "callee": callee,
                "callee_kind": "exact-generated-helper",
                "canonical_domain": domain,
                "canonical_operator": operator,
                "normalization_rule": rule,
                "guard_scope": scope,
                "guard_subject": subject,
                **({"canonical_guard_subject": canonical_subject} if canonical_subject is not None else {}),
            }
        )

    for raw_function in raw_target_ir.functions:
        canonical_function = canonical_functions_by_raw.get(raw_function.name)
        if canonical_function is None:
            raise RouteError("PURE_MODULE_TARGET_CALL_GRAPH_IDENTIFIER_MAP_INCOMPLETE")
        for raw_parameter, canonical_parameter in zip(
            raw_function.parameters,
            canonical_function.parameters,
            strict=True,
        ):
            callee, helper_id = guards[raw_parameter.type]
            append_guard(
                raw_function=raw_function,
                canonical_function=canonical_function,
                domain=raw_parameter.type,
                rule=f"javascript.parameter.{raw_parameter.type}.exact",
                scope="signature-parameter",
                subject=raw_parameter.name,
                canonical_subject=canonical_parameter.name,
                operator="guard",
                callee=callee,
                helper_id=helper_id,
            )

        return_callee, return_helper_id = guards[raw_function.return_type]
        append_guard(
            raw_function=raw_function,
            canonical_function=canonical_function,
            domain=raw_function.return_type,
            rule=return_rules[raw_function.return_type],
            scope="signature-return",
            subject="return",
            canonical_subject="return",
            operator="guard",
            callee=return_callee,
            helper_id=return_helper_id,
        )

        for domain, operator in sorted(_function_operator_uses(raw_function)):
            if operator not in types.ARITHMETIC_OPERATORS:
                continue
            if domain == "integer":
                append_guard(
                    raw_function=raw_function,
                    canonical_function=canonical_function,
                    domain=domain,
                    rule=f"javascript.integer.{operator}.safe-integer",
                    scope="arithmetic-result",
                    subject=operator,
                    operator=operator,
                    callee="_elmosRequireSafeInteger",
                    helper_id="safe_integer",
                )
                if operator in {"/", "%"}:
                    non_zero_rule = (
                        "javascript.integer./.truncating-non-zero"
                        if operator == "/"
                        else "javascript.integer.%.non-zero"
                    )
                    append_guard(
                        raw_function=raw_function,
                        canonical_function=canonical_function,
                        domain=domain,
                        rule=non_zero_rule,
                        scope="arithmetic-divisor",
                        subject=operator,
                        operator=operator,
                        callee="_elmosRequireNonZero",
                        helper_id="non_zero",
                    )
            else:
                append_guard(
                    raw_function=raw_function,
                    canonical_function=canonical_function,
                    domain=domain,
                    rule=f"javascript.number.{operator}.finite-result",
                    scope="arithmetic-result",
                    subject=operator,
                    operator=operator,
                    callee="_elmosRequireFiniteNumber",
                    helper_id="finite_number",
                )

    ignored_normalizations = {
        "javascript.integer.negative-zero-normalized",
        "javascript.parameter.integer.negative-zero-normalized",
        "javascript.return.integer.negative-zero-normalized",
    }
    observed_rules = {
        rule
        for rule in emitted_rules
        if rule not in ignored_normalizations
        and (
            rule.startswith("javascript.parameter.")
            or rule.startswith("javascript.return.")
            or rule.endswith(".safe-integer")
            or rule.endswith(".finite-result")
            or rule
            in {
                "javascript.integer./.truncating-non-zero",
                "javascript.integer.%.non-zero",
            }
        )
    }
    if observed_rules != expected_rules:
        raise RouteError("PURE_MODULE_TARGET_JAVASCRIPT_GUARD_NORMALIZATION_INVALID")
    return edges


def _typescript_guard_edges(
    raw_target_ir: SemanticIR,
    canonical_functions_by_raw: dict[str, Function],
    emitted: EmittedFile,
    helper_ids: set[str],
    helper_identifiers: set[str],
) -> list[dict[str, Any]]:
    language = raw_target_ir.source_language
    if language not in {"typescript", "react"}:
        return []
    emitted_rules = set(emitted.normalization_rules)
    expected_rules: set[str] = set()
    edges: list[dict[str, Any]] = []

    def append_guard(
        *,
        raw_function: Function,
        canonical_function: Function,
        domain: str,
        rule: str,
        scope: str,
        subject: str,
        canonical_subject: str | None,
        operator: str,
        callee: str,
        helper_id: str,
    ) -> None:
        expected_rules.add(rule)
        if helper_id not in helper_ids or callee not in helper_identifiers:
            raise RouteError(f"PURE_MODULE_TARGET_CALL_GRAPH_HELPER_MISMATCH:{rule}")
        edges.append(
            {
                "caller": raw_function.name,
                "canonical_caller": canonical_function.name,
                "callee": callee,
                "callee_kind": "exact-generated-helper",
                "canonical_domain": domain,
                "canonical_operator": operator,
                "normalization_rule": rule,
                "guard_scope": scope,
                "guard_subject": subject,
                **({"canonical_guard_subject": canonical_subject} if canonical_subject is not None else {}),
            }
        )

    for raw_function in raw_target_ir.functions:
        canonical_function = canonical_functions_by_raw.get(raw_function.name)
        if canonical_function is None:
            raise RouteError("PURE_MODULE_TARGET_CALL_GRAPH_IDENTIFIER_MAP_INCOMPLETE")
        for raw_parameter, canonical_parameter in zip(
            raw_function.parameters,
            canonical_function.parameters,
            strict=True,
        ):
            if raw_parameter.type != "integer":
                continue
            append_guard(
                raw_function=raw_function,
                canonical_function=canonical_function,
                domain="integer",
                rule=f"{language}.parameter.integer.safe-integer",
                scope="signature-parameter",
                subject=raw_parameter.name,
                canonical_subject=canonical_parameter.name,
                operator="guard",
                callee="_elmosRequireSafeInteger",
                helper_id="safe_integer",
            )

        if raw_function.return_type in {"integer", "number"}:
            return_domain = raw_function.return_type
            return_callee = "_elmosRequireSafeInteger" if return_domain == "integer" else "_elmosRequireFiniteNumber"
            append_guard(
                raw_function=raw_function,
                canonical_function=canonical_function,
                domain=return_domain,
                rule=f"{language}.return.{return_domain}."
                + ("safe-integer" if return_domain == "integer" else "finite"),
                scope="signature-return",
                subject="return",
                canonical_subject="return",
                operator="guard",
                callee=return_callee,
                helper_id="safe_integer" if return_domain == "integer" else "finite_number",
            )

        for domain, operator in sorted(_function_operator_uses(raw_function)):
            if operator not in types.ARITHMETIC_OPERATORS:
                continue
            if domain == "integer":
                append_guard(
                    raw_function=raw_function,
                    canonical_function=canonical_function,
                    domain=domain,
                    rule=f"{language}.integer.{operator}.safe-integer",
                    scope="arithmetic-result",
                    subject=operator,
                    canonical_subject=None,
                    operator=operator,
                    callee="_elmosRequireSafeInteger",
                    helper_id="safe_integer",
                )
                if operator in {"/", "%"}:
                    append_guard(
                        raw_function=raw_function,
                        canonical_function=canonical_function,
                        domain=domain,
                        rule=(
                            f"{language}.integer./.truncating-non-zero"
                            if operator == "/"
                            else f"{language}.integer.%.non-zero"
                        ),
                        scope="arithmetic-divisor",
                        subject=operator,
                        canonical_subject=None,
                        operator=operator,
                        callee="_elmosRequireNonZero",
                        helper_id="non_zero",
                    )
            else:
                append_guard(
                    raw_function=raw_function,
                    canonical_function=canonical_function,
                    domain=domain,
                    rule=f"{language}.number.{operator}.finite-result",
                    scope="arithmetic-result",
                    subject=operator,
                    canonical_subject=None,
                    operator=operator,
                    callee="_elmosRequireFiniteNumber",
                    helper_id="finite_number",
                )
                if operator in {"/", "%"}:
                    append_guard(
                        raw_function=raw_function,
                        canonical_function=canonical_function,
                        domain=domain,
                        rule=f"{language}.number.{operator}.non-zero:_elmosRequireNonZero",
                        scope="arithmetic-divisor",
                        subject=operator,
                        canonical_subject=None,
                        operator=operator,
                        callee="_elmosRequireNonZero",
                        helper_id="non_zero",
                    )

    observed_rules = {
        rule
        for rule in emitted_rules
        if rule != f"{language}.parameter.integer.negative-zero-normalized"
        and (
            rule.startswith(f"{language}.parameter.")
            or rule.startswith(f"{language}.return.")
            or rule.startswith(f"{language}.integer.")
            or rule.startswith(f"{language}.number.")
        )
    }
    if observed_rules != expected_rules:
        raise RouteError(f"PURE_MODULE_TARGET_{language.upper()}_GUARD_NORMALIZATION_INVALID")
    return edges


def _target_call_graph(
    raw_target_ir: SemanticIR,
    canonical_functions_by_raw: dict[str, Function],
    emitted: EmittedFile,
    target_helper_symbols: list[dict[str, Any]],
) -> dict[str, Any]:
    helper_identifiers = {
        str(identifier) for symbol in target_helper_symbols for identifier in (symbol["name"], symbol["qualified_name"])
    }
    helper_ids = {str(symbol["helper_id"]) for symbol in target_helper_symbols}
    registered_rules: dict[str, tuple[str, str, str, tuple[str, ...]]] = {}
    raw_functions = {function.name: function for function in raw_target_ir.functions}
    if set(raw_functions) != set(canonical_functions_by_raw):
        raise RouteError("PURE_MODULE_TARGET_CALL_GRAPH_IDENTIFIER_MAP_INCOMPLETE")
    for operator, (callee, required_helpers) in _CHECKED_INTEGER_CALL.get(raw_target_ir.source_language, {}).items():
        rule = f"{raw_target_ir.source_language}.integer.{operator}.call:{callee}"
        registered_rules[rule] = ("integer", operator, callee, required_helpers)
    float_guard = _FLOAT_NON_ZERO_GUARD.get(raw_target_ir.source_language)
    if raw_target_ir.source_language in {"typescript", "react"}:
        float_guard = None
    if float_guard is not None:
        callee, helper_id = float_guard
        for operator in ("/", "%"):
            rule = f"{raw_target_ir.source_language}.number.{operator}.non-zero:{callee}"
            registered_rules[rule] = ("number", operator, callee, (helper_id,))

    call_rules = {
        rule
        for rule in emitted.normalization_rules
        if raw_target_ir.source_language not in {"typescript", "react"}
        and (".call:" in rule or ".non-zero:" in rule)
    }
    if not call_rules <= set(registered_rules):
        raise RouteError("PURE_MODULE_TARGET_CALL_NORMALIZATION_INVALID")

    edges = _javascript_guard_edges(
        raw_target_ir,
        canonical_functions_by_raw,
        emitted,
        helper_ids,
        helper_identifiers,
    )
    edges.extend(
        _typescript_guard_edges(
            raw_target_ir,
            canonical_functions_by_raw,
            emitted,
            helper_ids,
            helper_identifiers,
        )
    )
    matched_rules: set[str] = set()
    for rule in sorted(call_rules):
        domain, operator, callee, required_helpers = registered_rules[rule]
        if required_helpers:
            if not set(required_helpers) <= helper_ids or callee not in helper_identifiers:
                raise RouteError(f"PURE_MODULE_TARGET_CALL_GRAPH_HELPER_MISMATCH:{rule}")
            callee_kind = "exact-generated-helper"
        else:
            if callee in helper_identifiers:
                raise RouteError(f"PURE_MODULE_TARGET_CALL_GRAPH_BUILTIN_MISMATCH:{rule}")
            callee_kind = "pinned-target-builtin"
        for raw_function in raw_target_ir.functions:
            if (domain, operator) not in _function_operator_uses(raw_function):
                continue
            canonical_function = canonical_functions_by_raw[raw_function.name]
            matched_rules.add(rule)
            edges.append(
                {
                    "caller": raw_function.name,
                    "canonical_caller": canonical_function.name,
                    "callee": callee,
                    "callee_kind": callee_kind,
                    "canonical_domain": domain,
                    "canonical_operator": operator,
                    "normalization_rule": rule,
                }
            )
    if matched_rules != call_rules:
        raise RouteError("PURE_MODULE_TARGET_CALL_GRAPH_NOT_CLOSED")
    return {
        "status": "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS",
        "scope": "profile-functions-to-emitted-callees",
        "edges": sorted(
            edges,
            key=lambda edge: (
                edge["caller"],
                edge["callee"],
                edge["canonical_domain"],
                edge["canonical_operator"],
                str(edge.get("guard_scope", "operator")),
                str(edge.get("guard_subject", "")),
            ),
        ),
        "helper_internal_calls": {
            "status": "CONTENT_BOUND_NOT_EDGE_ENUMERATED",
            "binding": "verified_generated_helpers-exact-bytes-and-digests",
        },
    }


def _build_whole_file_closure(
    *,
    source_inventory: dict[str, Any],
    target_inventory: dict[str, Any],
    source_ir: SemanticIR,
    raw_target_ir: SemanticIR,
    target_ir: SemanticIR,
    identifier_plan: IdentifierPlan,
    manifest: dict[str, Any],
    source_bytes: bytes,
    emitted: EmittedFile,
) -> dict[str, Any]:
    validate_identifier_plan(source_ir, identifier_plan)
    expected_target_view = target_ir_view(source_ir, identifier_plan)
    raw_target_functions = {function.name: function for function in raw_target_ir.functions}
    canonical_target_functions = {function.name: function for function in target_ir.functions}
    if len(raw_target_functions) != len(raw_target_ir.functions):
        raise RouteError("PURE_MODULE_TARGET_RAW_SYMBOL_DUPLICATED")
    if len(canonical_target_functions) != len(target_ir.functions):
        raise RouteError("PURE_MODULE_TARGET_CANONICAL_SYMBOL_DUPLICATED")
    canonical_functions_by_raw: dict[str, Function] = {}
    for source_function, expected_raw_function in zip(
        source_ir.functions,
        expected_target_view.functions,
        strict=True,
    ):
        raw_function = raw_target_functions.get(expected_raw_function.name)
        canonical_function = canonical_target_functions.get(source_function.name)
        if raw_function is None or canonical_function is None:
            raise RouteError("PURE_MODULE_TARGET_IDENTIFIER_MAP_INCOMPLETE")
        canonical_functions_by_raw[raw_function.name] = canonical_function
    if set(canonical_functions_by_raw) != set(raw_target_functions):
        raise RouteError("PURE_MODULE_TARGET_IDENTIFIER_MAP_INCOMPLETE")

    manifest_signatures = _module_manifest_signatures(manifest)
    target_bytes = emitted.content.encode("utf-8")
    _verify_inventory_artifact(
        source_inventory,
        role="source",
        language=source_ir.source_language,
        logical_file=source_ir.source_file,
        artifact_bytes=source_bytes,
    )
    _verify_inventory_artifact(
        target_inventory,
        role="target",
        language=raw_target_ir.source_language,
        logical_file=raw_target_ir.source_file,
        artifact_bytes=target_bytes,
    )
    source_prelude = _verify_language_prelude(
        source_inventory,
        role="source",
        language=source_ir.source_language,
        artifact_bytes=source_bytes,
    )
    target_prelude = _verify_language_prelude(
        target_inventory,
        role="target",
        language=raw_target_ir.source_language,
        artifact_bytes=target_bytes,
    )
    source_profile_inventory, source_wrapper = _separate_verified_language_wrapper(
        source_inventory,
        role="source",
        language=source_ir.source_language,
    )
    target_profile_inventory, target_wrapper = _separate_verified_language_wrapper(
        target_inventory,
        role="target",
        language=raw_target_ir.source_language,
    )
    source_profile_symbols, source_helpers = _close_profile_inventory(
        source_profile_inventory,
        source_ir,
        manifest_signatures,
        role="source",
    )
    if source_helpers:
        raise RouteError("PURE_MODULE_SOURCE_HELPER_EXCEPTION_FORBIDDEN")

    helper_regions = _emitted_helper_regions(emitted, raw_target_ir.source_language)
    target_profile_symbols, raw_helper_subjects = _close_profile_inventory(
        target_profile_inventory,
        raw_target_ir,
        manifest_signatures,
        role="target",
        helper_regions=helper_regions,
        canonical_functions_by_raw=canonical_functions_by_raw,
    )
    helpers_by_id: dict[str, list[dict[str, Any]]] = {str(region["helper_id"]): [] for region in helper_regions}
    target_helper_symbols: list[dict[str, Any]] = []
    for subject in raw_helper_subjects:
        helper_id = str(subject["helper_id"])
        visibility, storage = _verify_helper_visibility(raw_target_ir.source_language, subject)
        signature = subject["signature"]
        parameters = signature.get("parameters")
        arity = len(parameters) if isinstance(parameters, list) else 0
        symbol = {
            "helper_id": helper_id,
            "name": subject["name"],
            "qualified_name": subject["qualified_name"],
            "declaration_kind": subject["declaration_kind"],
            "analyzable": subject["analyzable"],
            "occurrence": subject["occurrence"],
            "arity": arity,
            "visibility": visibility,
            "storage": storage,
            "source_span": subject["source_span"],
            "raw_signature": signature,
        }
        helpers_by_id[helper_id].append(symbol)
        target_helper_symbols.append(symbol)

    verified_helpers: list[dict[str, Any]] = []
    for region in helper_regions:
        helper_id = str(region["helper_id"])
        symbols = sorted(helpers_by_id[helper_id], key=lambda item: item["qualified_name"])
        if not symbols:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_INVENTORY_MISSING:{helper_id}")
        if is_specialized_pair(source_ir.source_language, raw_target_ir.source_language):
            _verify_specialized_helper_subject(
                language=raw_target_ir.source_language,
                region=region,
                symbols=symbols,
                target_bytes=target_bytes,
            )
        verified_helpers.append(
            {
                **region,
                "source_span": {
                    "file": emitted.relative_path,
                    "start_byte": region["start_byte"],
                    "end_byte": region["end_byte"],
                },
                "symbols": symbols,
            }
        )

    source_inventory_bytes = canonical_json_bytes(source_inventory)
    target_inventory_bytes = canonical_json_bytes(target_inventory)
    target_call_graph = _target_call_graph(
        raw_target_ir,
        canonical_functions_by_raw,
        emitted,
        target_helper_symbols,
    )
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-whole-file-closure",
        "profile": "typed-pure-module-v1",
        "route": {
            "source_language": source_ir.source_language,
            "target_language": raw_target_ir.source_language,
        },
        "status": "PASSED",
        "source_inventory_sha256": _digest(source_inventory_bytes),
        "source_inventory_bytes": len(source_inventory_bytes),
        "target_inventory_sha256": _digest(target_inventory_bytes),
        "target_inventory_bytes": len(target_inventory_bytes),
        "manifest_symbols": sorted(manifest_signatures),
        "source_profile_symbols": source_profile_symbols,
        "target_profile_symbols": target_profile_symbols,
        "target_helper_symbols": sorted(
            target_helper_symbols, key=lambda item: (item["helper_id"], item["qualified_name"])
        ),
        "verified_generated_helpers": verified_helpers,
        "verified_language_prelude": {
            "source": source_prelude,
            "target": target_prelude,
        },
        "verified_language_wrapper": {
            "source": source_wrapper,
            "target": target_wrapper,
        },
        "blocked_declarations": {"source": [], "target": []},
        "source_user_call_graph": {"edges": [], "status": "EMPTY_AND_CLOSED"},
        "target_call_graph_policy": "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS",
        "target_call_graph": target_call_graph,
        "target_builtin_normalizations": list(emitted.normalization_rules),
        "identifier_hygiene": {
            "status": "PASSED",
            "policy_id": identifier_plan.policy_id,
            "policy_sha256": identifier_plan.policy_sha256,
            "unit_namespace": identifier_plan.unit_namespace.to_mapping(),
            "unit_namespace_sha256": identifier_plan.unit_namespace.digest,
            "plan_sha256": identifier_plan.digest,
            "functions": [
                {
                    "raw_symbol": raw_symbol,
                    "canonical_symbol": canonical_functions_by_raw[raw_symbol].name,
                    "parameters": [
                        {
                            "raw_name": raw_parameter.name,
                            "canonical_name": canonical_parameter.name,
                            "canonical_type": canonical_parameter.type,
                        }
                        for raw_parameter, canonical_parameter in zip(
                            raw_target_functions[raw_symbol].parameters,
                            canonical_functions_by_raw[raw_symbol].parameters,
                            strict=True,
                        )
                    ],
                }
                for raw_symbol in sorted(
                    canonical_functions_by_raw,
                    key=lambda symbol: canonical_functions_by_raw[symbol].name,
                )
            ],
        },
    }


def migrate_module(
    source: Path,
    source_language: Language,
    target_language: Language,
    manifest_path: Path,
    output: Path,
) -> dict[str, Any]:
    """Snapshot immutable module inputs, then run the closed migration."""

    if source_language not in REPOSITORY_SURFACE_LANGUAGES or target_language not in REPOSITORY_SURFACE_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    if (
        not is_routed_pair(source_language, target_language)
        and (source_language, target_language) not in DEPRECATED_DIRECTED_PAIRS
    ):
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    resolved_source = source.resolve()
    resolved_manifest = manifest_path.resolve()
    source_bytes = resolved_source.read_bytes()
    manifest_bytes = resolved_manifest.read_bytes()
    identifier_unit_namespace = standalone_artifact_unit_namespace(
        resolved_source.name,
        _digest(source_bytes),
    )
    with tempfile.TemporaryDirectory(prefix="elmos-module-input-snapshot-") as temporary:
        snapshot_root = Path(temporary)
        snapshot_root.chmod(0o700)
        (
            source_snapshot,
            descriptor_binding,
            descriptor_bytes,
            descriptor_snapshot,
        ) = _private_javascript_source_snapshot(snapshot_root, resolved_source, source_language, source_bytes)
        manifest_snapshot = _private_input_snapshot(
            snapshot_root,
            "manifest",
            resolved_manifest.name,
            manifest_bytes,
        )
        try:
            report = _migrate_module_snapshot(
                source_snapshot,
                source_language,
                target_language,
                manifest_snapshot,
                output,
                identifier_unit_namespace=identifier_unit_namespace,
                javascript_descriptor=descriptor_binding,
                javascript_descriptor_bytes=descriptor_bytes,
            )
        except Exception as error:
            try:
                _require_javascript_descriptor_origin_unchanged(resolved_source, descriptor_binding)
                _require_javascript_descriptor_snapshot(descriptor_binding, descriptor_snapshot, descriptor_bytes)
            except RouteError as changed:
                raise changed from error
            raise
        _require_javascript_descriptor_origin_unchanged(resolved_source, descriptor_binding)
        _require_javascript_descriptor_snapshot(descriptor_binding, descriptor_snapshot, descriptor_bytes)
        return report


def _migrate_module_snapshot(
    source: Path,
    source_language: Language,
    target_language: Language,
    manifest_path: Path,
    output: Path,
    *,
    identifier_unit_namespace: IdentifierUnitNamespace,
    javascript_descriptor: dict[str, Any] | None = None,
    javascript_descriptor_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Analyze, emit, relift, execute, and compose a real pure module."""

    if source_language not in REPOSITORY_SURFACE_LANGUAGES or target_language not in REPOSITORY_SURFACE_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    if (
        not is_routed_pair(source_language, target_language)
        and (source_language, target_language) not in DEPRECATED_DIRECTED_PAIRS
    ):
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    source = source.resolve()
    manifest_path = manifest_path.resolve()
    source_bytes = source.read_bytes()
    manifest_bytes = manifest_path.read_bytes()
    descriptor_snapshot = _javascript_descriptor_snapshot_for_source(
        source,
        javascript_descriptor,
    )
    _require_javascript_descriptor_snapshot(
        javascript_descriptor,
        descriptor_snapshot,
        javascript_descriptor_bytes,
    )
    manifest = _load_module_manifest(manifest_path)
    symbols = _manifest_symbols(manifest)

    # Whole-file closure is a precondition, not evidence appended after the
    # conversion has already emitted output. The real compiler inventory runs
    # before any caller-owned output directory is created.
    source_inventory = inventory_module(source, source_language)
    source_analyses = [analyze(source, source_language, symbol) for symbol in symbols]
    source_ir = _bind_function_spans_from_inventory(
        _combine_function_irs(source_analyses, symbols, source_language, "source"),
        source_inventory,
        role="source",
    )
    _enforce_specialized_semantic_domain(source_ir, source_language, target_language)
    _enforce_nodejs_semantic_domain(source_ir, source_language, target_language)
    cases_by_symbol = normalize_pure_module_case_manifest(
        manifest,
        {function.name: function for function in source_ir.functions},
    )
    for function in source_ir.functions:
        _enforce_specialized_case_domain(
            function,
            cases_by_symbol[function.name],
            source_language,
            target_language,
        )
        _enforce_nodejs_case_domain(
            function,
            cases_by_symbol[function.name],
            source_language,
            target_language,
        )
    if identifier_unit_namespace.source_sha256 != _digest(source_bytes):
        raise RouteError("IDENTIFIER_UNIT_NAMESPACE_SNAPSHOT_DIGEST_MISMATCH")
    identifier_plan = plan_identifiers(
        source_ir,
        target_language,
        unit_namespace=identifier_unit_namespace,
    )
    validate_identifier_plan(
        source_ir,
        identifier_plan,
        expected_unit_namespace=identifier_unit_namespace,
    )
    target_view = target_ir_view(source_ir, identifier_plan)
    target_symbols = [function.name for function in target_view.functions]
    emitted = emit(source_ir, target_language, identifier_plan=identifier_plan)
    with tempfile.TemporaryDirectory(prefix="elmos-module-closure-") as temporary:
        target_path = Path(temporary) / emitted.relative_path
        target_path.write_text(emitted.content, encoding="utf-8")
        target_inventory = inventory_module(
            target_path,
            target_language,
            emitted_target=True,
        )
        target_analyses = [
            analyze(target_path, target_language, symbol, emitted_target=True) for symbol in target_symbols
        ]
    raw_target_ir = _bind_function_spans_from_inventory(
        _combine_function_irs(target_analyses, target_symbols, target_language, "target"),
        target_inventory,
        role="target",
    )
    target_ir = alpha_normalize_target(source_ir, raw_target_ir, identifier_plan)
    _enforce_specialized_semantic_domain(target_ir, source_language, target_language)
    _enforce_nodejs_semantic_domain(target_ir, source_language, target_language)
    whole_file_closure = _build_whole_file_closure(
        source_inventory=source_inventory,
        target_inventory=target_inventory,
        source_ir=source_ir,
        raw_target_ir=raw_target_ir,
        target_ir=target_ir,
        identifier_plan=identifier_plan,
        manifest=manifest,
        source_bytes=source_bytes,
        emitted=emitted,
    )
    if source.read_bytes() != source_bytes:
        raise RouteError("PURE_MODULE_SOURCE_CHANGED_DURING_CLOSURE")
    if manifest_path.read_bytes() != manifest_bytes:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_CHANGED_DURING_CLOSURE")
    _require_javascript_descriptor_snapshot(
        javascript_descriptor,
        descriptor_snapshot,
        javascript_descriptor_bytes,
    )

    output = safe_output(output)
    output.mkdir(parents=True, exist_ok=True)
    identifier_plan_path = output / "identifier-plan.json"
    identifier_plan_path.write_bytes(identifier_plan_bytes(identifier_plan))
    if sha256_bytes(identifier_plan_path.read_bytes()) != identifier_plan.digest:
        raise RouteError("IDENTIFIER_PLAN_PERSISTED_DIGEST_MISMATCH")
    source_validation: dict[str, Any] = {}
    source_observations: dict[str, list[dict[str, Any]]] = {}
    for index, symbol in enumerate(symbols):
        function = next(item for item in source_ir.functions if item.name == symbol)
        validation = validate_source(
            source,
            source_language,
            function,
            cases_by_symbol[symbol],
            output / "source-runtime" / f"{index:03d}",
        )
        source_validation[symbol] = validation
        source_observations[symbol] = list(validation.get("observations", []))

    module_javascript_runtime_observation: dict[str, str] | None = None
    report_javascript_descriptor = javascript_descriptor
    if javascript_descriptor is not None:
        if descriptor_snapshot is None:
            raise RouteError("JAVASCRIPT_ESM_RUNTIME_DESCRIPTOR_EVIDENCE_REQUIRED")
        module_javascript_runtime_observation = _bound_javascript_runtime_descriptor_observation(
            javascript_descriptor,
            descriptor_snapshot,
            list(source_validation.values()),
        )
        report_javascript_descriptor = {
            **javascript_descriptor,
            **module_javascript_runtime_observation,
        }

    target_validation: dict[str, Any] = {}
    target_observations: dict[str, list[dict[str, Any]]] = {}
    for index, symbol in enumerate(symbols):
        function = next(item for item in target_view.functions if item.name == target_symbols[index])
        validation = validate(
            emitted,
            target_language,
            function,
            cases_by_symbol[symbol],
            output / "target-runtime" / f"{index:03d}",
        )
        target_validation[symbol] = validation
        target_observations[symbol] = list(validation.get("observations", []))

    report = verify_pure_module(
        source_ir=source_ir,
        raw_target_ir=raw_target_ir,
        target_ir=target_ir,
        identifier_plan=identifier_plan,
        case_manifest=manifest,
        source_observations=source_observations,
        target_observations=target_observations,
        source_artifact_sha256=_digest(source_bytes),
        target_artifact_sha256=_digest(emitted.content.encode("utf-8")),
        corpus_sha256=_digest(manifest_bytes),
        emitted=emitted,
        source_artifact_bytes=source_bytes,
        source_logical_file=source.name,
        case_manifest_bytes=manifest_bytes,
        source_inventory=source_inventory,
        target_inventory=target_inventory,
        whole_file_closure=whole_file_closure,
        javascript_descriptor=report_javascript_descriptor,
        javascript_descriptor_bytes=javascript_descriptor_bytes,
        output=output,
    )
    source_validation_path = output / "source-module-validation.json"
    target_validation_path = output / "target-module-validation.json"
    write_json(source_validation_path, source_validation)
    write_json(target_validation_path, target_validation)
    report["source_validation"] = source_validation
    report["target_validation"] = target_validation
    report["artifact_refs"].extend(
        [
            _artifact_ref(output, source_validation_path, "source-module-validation"),
            _artifact_ref(output, target_validation_path, "target-module-validation"),
        ]
    )
    write_json(output / "typed-pure-module-equivalence.json", report)
    _require_javascript_descriptor_snapshot(
        javascript_descriptor,
        descriptor_snapshot,
        javascript_descriptor_bytes,
    )
    if report["status"] != "PASSED":
        raise RouteError("PURE_MODULE_EQUIVALENCE_FAILED")
    return report


def migrate(
    source: Path,
    source_language: Language,
    target_language: Language,
    function_name: str,
    cases_path: Path,
    output: Path,
    *,
    repository_execution_mode: bool = False,
    repository_language_lifecycle: str | None = None,
    identifier_unit_namespace: IdentifierUnitNamespace | None = None,
) -> dict[str, Any]:
    """Snapshot immutable single-function inputs before any compiler phase."""

    if source_language not in REPOSITORY_SURFACE_LANGUAGES or target_language not in REPOSITORY_SURFACE_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    routed_pair = is_routed_pair(source_language, target_language)
    if not routed_pair and not repository_execution_mode:
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    expected_lifecycle = repository_language_lifecycle_for_execution(
        source_language,
        target_language,
        repository_execution_mode=repository_execution_mode,
        supplied=repository_language_lifecycle,
    )
    resolved_source = source.resolve()
    resolved_cases = cases_path.resolve()
    source_bytes = resolved_source.read_bytes()
    cases_bytes = resolved_cases.read_bytes()
    unit_namespace = _identifier_unit_namespace_for_migration(
        source=resolved_source,
        source_bytes=source_bytes,
        repository_execution_mode=repository_execution_mode,
        supplied=identifier_unit_namespace,
    )
    with tempfile.TemporaryDirectory(prefix="elmos-function-input-snapshot-") as temporary:
        snapshot_root = Path(temporary)
        snapshot_root.chmod(0o700)
        (
            source_snapshot,
            descriptor_binding,
            descriptor_bytes,
            descriptor_snapshot,
        ) = _private_javascript_source_snapshot(snapshot_root, resolved_source, source_language, source_bytes)
        cases_snapshot = _private_input_snapshot(
            snapshot_root,
            "cases",
            resolved_cases.name,
            cases_bytes,
        )
        try:
            report = _migrate_from_snapshot(
                source_snapshot,
                source_language,
                target_language,
                function_name,
                cases_snapshot,
                output,
                repository_execution_mode=repository_execution_mode,
                repository_language_lifecycle=expected_lifecycle,
                identifier_unit_namespace=unit_namespace,
                javascript_descriptor=descriptor_binding,
                javascript_descriptor_bytes=descriptor_bytes,
            )
        except Exception as error:
            try:
                _require_javascript_descriptor_origin_unchanged(resolved_source, descriptor_binding)
                _require_javascript_descriptor_snapshot(descriptor_binding, descriptor_snapshot, descriptor_bytes)
            except RouteError as changed:
                raise changed from error
            raise
        _require_javascript_descriptor_origin_unchanged(resolved_source, descriptor_binding)
        _require_javascript_descriptor_snapshot(descriptor_binding, descriptor_snapshot, descriptor_bytes)
        return report


def _migrate_from_snapshot(
    source: Path,
    source_language: Language,
    target_language: Language,
    function_name: str,
    cases_path: Path,
    output: Path,
    *,
    repository_execution_mode: bool = False,
    repository_language_lifecycle: str | None = None,
    identifier_unit_namespace: IdentifierUnitNamespace,
    javascript_descriptor: dict[str, Any] | None = None,
    javascript_descriptor_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Translate and execute one bounded function.

    ``repository_execution_mode`` is deliberately non-certifying. It opens
    every distinct pair in ``REPOSITORY_SURFACE_LANGUAGES`` for source/target compiler
    and behavior execution so repository orchestration has the complete directed
    local surface, while skipping route-pack layered/formal claims. The report
    remains ``PASSED_LOCAL_UNCERTIFIED`` with critical unknown semantics until
    the exact directed route has independent repository evidence.
    """
    descriptor_snapshot = _javascript_descriptor_snapshot_for_source(
        source,
        javascript_descriptor,
    )
    _require_javascript_descriptor_snapshot(
        javascript_descriptor,
        descriptor_snapshot,
        javascript_descriptor_bytes,
    )
    if source_language not in REPOSITORY_SURFACE_LANGUAGES or target_language not in REPOSITORY_SURFACE_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    routed_pair = is_routed_pair(source_language, target_language)
    if not routed_pair and not repository_execution_mode:
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    expected_lifecycle = repository_language_lifecycle_for_execution(
        source_language,
        target_language,
        repository_execution_mode=repository_execution_mode,
        supplied=repository_language_lifecycle,
    )
    output = safe_output(output)
    ir = analyze(source, source_language, function_name)
    if len(ir.functions) != 1:
        raise RouteError("EXACTLY_ONE_FUNCTION_REQUIRED")
    _enforce_specialized_semantic_domain(ir, source_language, target_language)
    _enforce_nodejs_semantic_domain(ir, source_language, target_language)
    function = ir.functions[0]
    cases = _load_cases(cases_path, len(function.parameters))
    _enforce_specialized_case_domain(function, cases, source_language, target_language)
    _enforce_nodejs_case_domain(function, cases, source_language, target_language)
    if identifier_unit_namespace.source_sha256 != _digest(source.read_bytes()):
        raise RouteError("IDENTIFIER_UNIT_NAMESPACE_SNAPSHOT_DIGEST_MISMATCH")
    identifier_plan = plan_identifiers(
        ir,
        target_language,
        unit_namespace=identifier_unit_namespace,
    )
    validate_identifier_plan(
        ir,
        identifier_plan,
        expected_unit_namespace=identifier_unit_namespace,
    )
    target_function = target_function_view(ir, function, identifier_plan)
    source_runtime_evidence: dict[str, Any] | None = None
    javascript_runtime_observation: dict[str, str] | None = None
    if routed_pair or repository_execution_mode:
        source_runtime_evidence = validate_source(
            source,
            source_language,
            function,
            cases,
            output / "source-runtime",
        )
    if javascript_descriptor is not None:
        if source_runtime_evidence is None or descriptor_snapshot is None:
            raise RouteError("JAVASCRIPT_ESM_RUNTIME_DESCRIPTOR_EVIDENCE_REQUIRED")
        javascript_runtime_observation = _bound_javascript_runtime_descriptor_observation(
            javascript_descriptor,
            descriptor_snapshot,
            [source_runtime_evidence],
        )
    emitted = emit(ir, target_language, identifier_plan=identifier_plan)
    evidence = validate(emitted, target_language, target_function, cases, output)
    identifier_plan_path = output / "identifier-plan.json"
    identifier_plan_path.write_bytes(identifier_plan_bytes(identifier_plan))
    identifier_plan_sha256 = sha256_bytes(identifier_plan_path.read_bytes())
    if identifier_plan_sha256 != identifier_plan.digest:
        raise RouteError("IDENTIFIER_PLAN_PERSISTED_DIGEST_MISMATCH")
    identifier_plan_reference = {
        "path": identifier_plan_path.name,
        "sha256": identifier_plan_sha256,
    }
    verify_content_reference(output, identifier_plan_reference)
    ir_path = output / "semantic-ir.json"
    source_ir_path = output / "source-semantic-ir.json"
    source_ir_bytes = canonical_json_bytes(ir.to_mapping())
    ir_path.write_bytes(source_ir_bytes)
    source_ir_path.write_bytes(source_ir_bytes)
    source_bytes = source.read_bytes()
    emitted_bytes = (output / emitted.relative_path).read_bytes()
    javascript_descriptor_report: dict[str, Any] | None = None
    if javascript_descriptor is not None and javascript_descriptor_bytes is not None:
        descriptor_artifact_path = output / "source-javascript-esm-package.json"
        descriptor_artifact_path.write_bytes(javascript_descriptor_bytes)
        descriptor_reference = _artifact_ref(
            output,
            descriptor_artifact_path,
            "source-javascript-esm-descriptor",
        )
        javascript_descriptor_report = {
            "logical_path": javascript_descriptor["logical_path"],
            "snapshot_path": javascript_descriptor["snapshot_path"],
            "artifact_path": descriptor_reference["path"],
            "sha256": descriptor_reference["sha256"],
            "bytes": descriptor_reference["bytes"],
            "type": "module",
        }
    layered_refs: dict[str, Any] | None = None
    semantic_summary: dict[str, Any] | None = None
    chunk_summary: dict[str, Any] | None = None
    behavior_summary: dict[str, Any] | None = None
    behavior_reference: dict[str, str] | None = None
    formal_summary: dict[str, Any] | None = None
    layered_summary: dict[str, Any] | None = None
    if repository_execution_mode:
        behavior_summary = behavior_equivalence(
            function,
            cases,
            list(source_runtime_evidence.get("observations", [])) if source_runtime_evidence else [],
            list(evidence.get("observations", [])),
        )
        behavior_artifact = output / "behavior-equivalence.json"
        behavior_reference = {
            "artifact_path": behavior_artifact.name,
            "artifact_sha256": write_json(behavior_artifact, behavior_summary),
        }
    if routed_pair and not repository_execution_mode:
        raw_target_ir = analyze(
            output / emitted.relative_path,
            target_language,
            target_function.name,
            emitted_target=True,
        )
        if len(raw_target_ir.functions) != 1:
            raise RouteError("TARGET_REANALYSIS_EXACTLY_ONE_FUNCTION_REQUIRED")
        raw_target_ir_path = output / "target-semantic-ir.raw.json"
        raw_target_ir_sha256 = write_json(raw_target_ir_path, raw_target_ir.to_mapping())
        raw_target_ir_reference = {
            "path": raw_target_ir_path.name,
            "sha256": raw_target_ir_sha256,
        }
        verify_content_reference(output, raw_target_ir_reference)
        target_ir = alpha_normalize_target(ir, raw_target_ir, identifier_plan)
        target_ir_path = output / "target-semantic-ir.normalized.json"
        target_ir_sha256 = write_json(target_ir_path, target_ir.to_mapping())
        source_ir_sha256 = sha256_bytes(source_ir_path.read_bytes())
        semantic_summary = semantic_equivalence(ir, target_ir)
        semantic_artifact = output / "semantic-equivalence.json"
        semantic_artifact_sha256 = write_json(semantic_artifact, semantic_summary)
        chunk_summary = chunk_equivalence(
            ir,
            target_ir,
            _digest(source_bytes),
            _digest(emitted_bytes),
            emitted,
            source_artifact_bytes=source_bytes,
            target_artifact_bytes=emitted_bytes,
            source_logical_file=source.name,
            target_logical_file=emitted.relative_path,
            require_concrete_spans=requires_concrete_source_spans(
                source_language,
                target_language,
                TYPED_PURE_FUNCTION_PROFILE,
            ),
        )
        chunk_artifact = output / "chunk-map.json"
        chunk_artifact_sha256 = write_json(chunk_artifact, chunk_summary)
        behavior_summary = behavior_equivalence(
            function,
            cases,
            list(source_runtime_evidence.get("observations", [])) if source_runtime_evidence else [],
            list(evidence.get("observations", [])),
        )
        behavior_artifact = output / "behavior-equivalence.json"
        behavior_artifact_sha256 = write_json(behavior_artifact, behavior_summary)
        behavior_reference = {
            "artifact_path": behavior_artifact.name,
            "artifact_sha256": behavior_artifact_sha256,
        }
        source_ir_reference = {
            "path": source_ir_path.name,
            "sha256": source_ir_sha256,
        }
        target_ir_reference = {
            "path": target_ir_path.name,
            "sha256": target_ir_sha256,
        }
        formal_input_path = output / "formal-input.json"
        formal_input_digest = write_json(
            formal_input_path,
            _formal_input_payload(
                source_language=source_language,
                target_language=target_language,
                source_path=source.name,
                source_bytes=source_bytes,
                target_path=emitted.relative_path,
                target_bytes=emitted_bytes,
                source_ir=ir,
                raw_target_ir=raw_target_ir,
                target_ir=target_ir,
                source_ir_reference=source_ir_reference,
                raw_target_ir_reference=raw_target_ir_reference,
                target_ir_reference=target_ir_reference,
                identifier_plan=identifier_plan,
                identifier_plan_reference=identifier_plan_reference,
                emitted=emitted,
            ),
        )
        formal_input_reference = {
            "path": formal_input_path.name,
            "sha256": formal_input_digest,
        }
        verify_formal_input_closure(output, formal_input_reference)
        formal_result, smt2 = formal_equivalence(
            function,
            target_ir.functions[0],
            source_language,
            target_language,
            formal_input_digest,
            formal_input_reference=formal_input_reference,
            input_domain=declared_formal_input_domain(source_language, target_language),
        )
        smt2_path = output / "formal-equivalence.smt2"
        smt2_path.write_text(smt2, encoding="utf-8")
        smt2_sha256 = sha256_bytes(smt2_path.read_bytes())
        formal_result["formal_input_digest"] = formal_input_digest
        formal_result["solver_input_digest"] = smt2_sha256
        proof_result_path = output / "formal-proof-result.json"
        proof_result_sha256 = write_json(proof_result_path, formal_result)
        formal_summary = {
            **formal_result,
            "proof_artifact_digests": [
                {
                    "property_id": formal_result["property_id"],
                    "path": smt2_path.name,
                    "sha256": smt2_sha256,
                    "strength": formal_result["proof_strength"],
                    "status": formal_result["property_status"],
                    "formal_input_sha256": formal_input_digest,
                },
                {
                    "property_id": formal_result["property_id"],
                    "path": proof_result_path.name,
                    "sha256": proof_result_sha256,
                    "strength": formal_result["proof_strength"],
                    "status": formal_result["property_status"],
                    "formal_input_sha256": formal_input_digest,
                },
            ],
        }
        verify_content_reference(
            output,
            {"path": smt2_path.name, "sha256": smt2_sha256},
        )
        verify_content_reference(
            output,
            {"path": proof_result_path.name, "sha256": proof_result_sha256},
        )
        formal_artifact = output / "formal-composition.json"
        formal_artifact_sha256 = write_json(formal_artifact, formal_summary)
        route_key = DirectedRouteKey(
            source_language=source_language,
            target_language=target_language,
            profile="typed-pure-function-v1",
            source_artifact_sha256=_digest(source_bytes),
            target_artifact_sha256=_digest(emitted_bytes),
            corpus_sha256=_digest(cases_path.read_bytes()),
            source_analyzer=ir.analyzer,
            source_analyzer_version=ir.analyzer_version,
            target_analyzer=target_ir.analyzer,
            target_analyzer_version=target_ir.analyzer_version,
        )
        layered_refs = {
            "identifier_hygiene": {
                "identifier_plan_path": identifier_plan_path.name,
                "identifier_plan_sha256": identifier_plan_sha256,
                "raw_target_ir_path": raw_target_ir_path.name,
                "raw_target_ir_sha256": raw_target_ir_sha256,
                "normalized_target_ir_path": target_ir_path.name,
                "normalized_target_ir_sha256": target_ir_sha256,
            },
            "semantic": {
                "artifact_path": semantic_artifact.name,
                "artifact_sha256": semantic_artifact_sha256,
                "source_ir_path": source_ir_path.name,
                "source_ir_sha256": source_ir_sha256,
                "target_ir_path": target_ir_path.name,
                "target_ir_sha256": target_ir_sha256,
            },
            "chunk": {
                "artifact_path": chunk_artifact.name,
                "artifact_sha256": chunk_artifact_sha256,
            },
            "behavior": {
                **behavior_reference,
            },
            "formal": {
                "artifact_path": formal_artifact.name,
                "artifact_sha256": formal_artifact_sha256,
                "formal_input_path": formal_input_path.name,
                "formal_input_sha256": formal_input_digest,
                "proof_artifact_digests": formal_summary["proof_artifact_digests"],
            },
        }
        layered_summary = compose_layered_report(
            route_key,
            semantic_summary,
            chunk_summary,
            behavior_summary,
            formal_summary,
            layered_refs,
        )
        layered_artifact = output / "layered-equivalence.json"
        layered_artifact_sha256 = write_json(layered_artifact, layered_summary)
        layered_refs["layered"] = {
            "artifact_path": layered_artifact.name,
            "artifact_sha256": layered_artifact_sha256,
        }
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "status": (
            "PASSED"
            if layered_summary is not None and layered_summary["status"] == "PASSED"
            else "PASSED_LOCAL_UNCERTIFIED"
            if repository_execution_mode
            and source_runtime_evidence is not None
            and source_runtime_evidence.get("status") == "PASSED"
            and evidence.get("status") == "PASSED"
            and behavior_summary is not None
            and behavior_summary.get("status") == "PASSED"
            else "BLOCKED"
            if layered_summary is None
            else "FAILED"
        ),
        "route": f"{source_language}-to-{target_language}",
        "route_pack_status": "DECLARED" if routed_pair else "NOT_AVAILABLE",
        "repository_execution_mode": repository_execution_mode,
        "repository_language_lifecycle": expected_lifecycle,
        "scope": "typed-pure-function-v1",
        "source": {
            "path": source.name,
            "sha256": _digest(source_bytes),
            "language": source_language,
            "function_name": function.name,
            "analyzer": ir.analyzer,
            "analyzer_version": ir.analyzer_version,
        },
        "target": {
            "path": emitted.relative_path,
            "sha256": _digest(emitted_bytes),
            "language": target_language,
            "function_name": target_function.name,
        },
        "identifier_hygiene": {
            "status": "PASSED",
            "policy_id": identifier_plan.policy_id,
            "policy_sha256": identifier_plan.policy_sha256,
            "unit_namespace": identifier_plan.unit_namespace.to_mapping(),
            "unit_namespace_sha256": identifier_plan.unit_namespace.digest,
            "plan_path": identifier_plan_path.name,
            "plan_sha256": identifier_plan_sha256,
            "source_function_name": function.name,
            "target_function_name": target_function.name,
            "renamed": function.name != target_function.name
            or tuple(parameter.name for parameter in function.parameters)
            != tuple(parameter.name for parameter in target_function.parameters),
            "raw_target_relift": (
                {
                    "status": "PASSED",
                    "path": layered_refs["identifier_hygiene"]["raw_target_ir_path"],
                    "sha256": layered_refs["identifier_hygiene"]["raw_target_ir_sha256"],
                }
                if layered_refs
                else {"status": "NOT_RUN", "reason": "repository-local-execution-mode"}
            ),
            "normalized_target_ir": (
                {
                    "status": "PASSED",
                    "path": layered_refs["identifier_hygiene"]["normalized_target_ir_path"],
                    "sha256": layered_refs["identifier_hygiene"]["normalized_target_ir_sha256"],
                }
                if layered_refs
                else {"status": "NOT_RUN", "reason": "repository-local-execution-mode"}
            ),
        },
        "semantic_ir_sha256": _digest(ir_path.read_bytes()),
        "source_map_coverage": chunk_summary["coverage"] if chunk_summary else 0.0,
        "behavior_case_count": len(cases),
        "behavior_pass_rate": (
            behavior_summary["pass_count"] / behavior_summary["case_count"]
            if behavior_summary and behavior_summary["case_count"]
            else 1.0
            if repository_execution_mode
            and source_runtime_evidence is not None
            and source_runtime_evidence.get("status") == "PASSED"
            and source_runtime_evidence.get("case_count") == len(cases)
            and evidence.get("status") == "PASSED"
            and evidence.get("case_count") == len(cases)
            else 0.0
        ),
        "critical_unknown_semantics": (
            0 if layered_summary is not None and layered_summary["status"] == "PASSED" else 1
        ),
        "limitations": [
            "Only typed, side-effect-free functions using return, if, literals, names, "
            "and supported binary operators are in scope.",
            "Object graphs, exceptions, async, reflection, I/O, framework, database, "
            "and concurrency semantics remain outside this route profile.",
        ],
        "validation": evidence,
        "source_validation": source_runtime_evidence
        if source_runtime_evidence
        else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"},
        "semantic_equivalence": (
            {
                "status": semantic_summary["status"],
                "difference_count": semantic_summary["difference_count"],
                **layered_refs["semantic"],
            }
            if layered_refs and semantic_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "chunk_equivalence": (
            {
                "status": chunk_summary["status"],
                "required_source_chunk_count": chunk_summary["required_source_chunk_count"],
                "mapped_source_chunk_count": chunk_summary["mapped_source_chunk_count"],
                "unexpected_target_chunk_count": chunk_summary["unexpected_target_chunk_count"],
                "coverage": chunk_summary["coverage"],
                **layered_refs["chunk"],
            }
            if layered_refs and chunk_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "behavior_equivalence": (
            {
                "status": behavior_summary["status"],
                "case_count": behavior_summary["case_count"],
                "pass_count": behavior_summary["pass_count"],
                "source_runtime_passed": behavior_summary["source_runtime_passed"],
                "target_runtime_passed": behavior_summary["target_runtime_passed"],
                "oracle_conflict_count": behavior_summary["oracle_conflict_count"],
                **behavior_reference,
            }
            if behavior_reference and behavior_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "formal_composition": (
            {
                "status": formal_summary["status"],
                "property_status": formal_summary["property_status"],
                "formal_input_digest": formal_summary["formal_input_digest"],
                "solver_input_digest": formal_summary["solver_input_digest"],
                "assumption_boundary": formal_summary["assumption_boundary"],
                "unsupported_semantics": formal_summary["unsupported_semantics"],
                **layered_refs["formal"],
            }
            if layered_refs and formal_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "layered_equivalence": (
            {"status": layered_summary["status"], **layered_refs["layered"]}
            if layered_refs and layered_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "certification_status": "EXPERIMENTAL",
        "external_certification_status": "NOT_RUN",
    }
    if javascript_descriptor_report is not None:
        assert javascript_descriptor is not None
        assert javascript_runtime_observation is not None
        report["javascript_esm_descriptor"] = javascript_descriptor_report
        report["javascript_esm_descriptor_observation"] = javascript_runtime_observation
        report["source"]["javascript_esm_descriptor"] = javascript_descriptor_report
    (output / "route-evidence.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if layered_summary is not None and layered_summary["status"] != "PASSED":
        raise RouteError(
            "LAYERED_EQUIVALENCE_FAILED:"
            f"semantic={semantic_summary['status'] if semantic_summary else 'NOT_RUN'}:"
            f"chunk={chunk_summary['status'] if chunk_summary else 'NOT_RUN'}:"
            f"behavior={behavior_summary['status'] if behavior_summary else 'NOT_RUN'}:"
            f"formal={formal_summary['status'] if formal_summary else 'NOT_RUN'}"
        )
    if repository_execution_mode and behavior_summary is not None and behavior_summary["status"] != "PASSED":
        raise RouteError(
            "REPOSITORY_BEHAVIOR_EQUIVALENCE_FAILED:"
            f"passed={behavior_summary['pass_count']}:"
            f"cases={behavior_summary['case_count']}:"
            f"oracle_conflicts={behavior_summary['oracle_conflict_count']}"
        )
    _require_javascript_descriptor_snapshot(
        javascript_descriptor,
        descriptor_snapshot,
        javascript_descriptor_bytes,
    )
    return report
