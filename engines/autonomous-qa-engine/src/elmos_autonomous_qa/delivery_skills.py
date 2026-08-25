"""Bounded project-output planning and deterministic test-source emission.

The functions in this module are deliberately pure.  They validate caller
objects and return canonical, content-addressed drafts; they never inspect or
write a repository, invoke a formatter/toolchain, or publish an artifact.
Those effects belong to an authorized ``ArtifactPublisher`` service.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .adapters import ADAPTER_REGISTRY, AdapterContractError, Capability, adapter_for
from .canonical import (
    CanonicalizationError,
    UnsafePathError,
    canonical_digest,
    canonical_json_bytes,
    normalize_relative_path,
    path_collision_key,
)
from .contracts import ContractError, require_resource_id, require_text, strict_json
from .domain import TEST_TYPES, validate_test_dsl


_SCHEMA_VERSION = "elmos.autonomous-qa.delivery-skills.v1"
_EMITTER_VERSION = "elmos.autonomous-qa.test-source-emitter.v1"
_RUN_MODES = frozenset(
    {"plan-only", "generate", "verify", "repair", "certify", "continuous"}
)
_OUTPUT_MODES = frozenset({"embedded", "sidecar", "both"})
_RETENTION_CLASSES = frozenset({"transient", "standard", "extended", "legal-hold"})
_MAX_ITEMS = 10_000


_DEFAULT_NATIVE_ROOTS: Mapping[str, str] = {
    "java-maven": "src/test/java/elmos/generated",
    "java-gradle": "src/test/java/elmos/generated",
    "kotlin-maven": "src/test/kotlin/elmos/generated",
    "kotlin-gradle": "src/test/kotlin/elmos/generated",
    "python": "tests/elmos_generated",
    "dotnet": "tests/Elmos.Generated",
    "go": "elmosqa_generated",
    "rust": "tests",
    "cmake-c-cpp": "tests",
    "php-composer": "tests/Generated",
    "javascript-node": "tests/generated",
    "typescript-node": "tests/generated",
    "react": "src/__tests__/generated",
    "vue": "src/__tests__/generated",
    "objective-c-xcode": "Tests/Generated",
    "swift-package": "Tests/ElmosGeneratedTests",
    "swift-xcode": "Tests/Generated",
    "flutter": "test/generated",
}


_SOURCE_SUFFIXES: Mapping[str, tuple[str, str]] = {
    "java-maven": ("Test", ".java"),
    "java-gradle": ("Test", ".java"),
    "kotlin-maven": ("Test", ".kt"),
    "kotlin-gradle": ("Test", ".kt"),
    "python": ("test_", ".py"),
    "dotnet": ("Tests", ".cs"),
    "go": ("_test", ".go"),
    "rust": ("", ".rs"),
    "cmake-c-cpp": ("_test", ".cpp"),
    "php-composer": ("Test", ".php"),
    "javascript-node": (".test", ".js"),
    "typescript-node": (".test", ".ts"),
    "react": (".test", ".tsx"),
    "vue": (".spec", ".ts"),
    "objective-c-xcode": ("Tests", ".m"),
    "swift-package": ("Tests", ".swift"),
    "swift-xcode": ("Tests", ".swift"),
    "flutter": ("_test", ".dart"),
}


_SOURCE_QUALITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TODO_MARKER", re.compile(r"\b(?:TODO|FIXME)\b", re.IGNORECASE)),
    (
        "EMPTY_ASSERTION",
        re.compile(
            r"\b(?:assert|assertTrue|assertEquals|XCTAssert\w*)\s*\(\s*\)",
            re.IGNORECASE,
        ),
    ),
    (
        "ASSERT_TRUE",
        re.compile(
            r"(?:\bassert\s+(?:true|True)\b|"
            r"\b(?:assert|assertTrue|XCTAssertTrue|Assert\.True)\s*\(\s*true\b|"
            r"\bexpect\s*\(\s*true\s*\)\s*\.toBe\s*\(\s*true\s*\))",
            re.IGNORECASE,
        ),
    ),
    (
        "DISABLED_TEST",
        re.compile(
            r"(?:@Disabled\b|\.skip\s*\(|\b(?:xit|xdescribe)\s*\(|"
            r"#\s*\[\s*ignore\s*\]|\[\s*Ignore\s*\]|\bXCTSkip\b|"
            r"\bunittest\.skip\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "FIXED_SLEEP",
        re.compile(
            r"(?:\b(?:Thread\.sleep|time\.sleep|Task\.Delay|setTimeout|"
            r"usleep|nanosleep|sleep)\s*\()",
            re.IGNORECASE,
        ),
    ),
    (
        "PLACEHOLDER_SOURCE",
        re.compile(
            r"(?:\bplaceholder\b|\bNotImplemented(?:Error|Exception)?\b|"
            r"UnsupportedOperationException|panic!\s*\(\s*['\"]not implemented)",
            re.IGNORECASE,
        ),
    ),
)


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "INLINE_SECRET_ASSIGNMENT",
        re.compile(
            r"(?:password|passwd|api[_-]?key|client[_-]?secret|access[_-]?token|"
            r"private[_-]?key)\s*['\"]?\s*[:=]\s*['\"][^'\"\r\n]{4,}['\"]",
            re.IGNORECASE,
        ),
    ),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}\b")),
    ("OPENAI_STYLE_TOKEN", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    (
        "BEARER_TOKEN",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE),
    ),
    ("PEM_PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


class DeliveryContractError(ContractError):
    """Raised when a delivery request is unsafe, ambiguous, or unsupported."""


def _exact_object(
    value: Any,
    *,
    label: str,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise DeliveryContractError(f"{label} must be an exact string-keyed object")
    unknown = sorted(set(value).difference(allowed))
    missing = sorted(required.difference(value))
    if unknown:
        raise DeliveryContractError(f"{label} has unsupported fields: {unknown}")
    if missing:
        raise DeliveryContractError(f"{label} is missing required fields: {missing}")
    return value


def _objects(value: Any, *, label: str, allow_empty: bool = False) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise DeliveryContractError(f"{label} must be {qualifier}")
    if len(value) > _MAX_ITEMS:
        raise DeliveryContractError(f"{label} exceeds the item limit")
    if any(not isinstance(item, Mapping) for item in value):
        raise DeliveryContractError(f"{label} items must be objects")
    return list(value)


def _strings(value: Any, *, label: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise DeliveryContractError(f"{label} must be {qualifier}")
    if len(value) > _MAX_ITEMS or any(not isinstance(item, str) for item in value):
        raise DeliveryContractError(f"{label} must be a bounded string array")
    return list(value)


def _resource(value: Any, label: str) -> str:
    try:
        return require_resource_id(value, label)
    except ContractError as exc:
        raise DeliveryContractError(str(exc)) from exc


def _runtime_context(request: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = request.get("_runtime_context")
    if raw is None:
        return {}
    context = _exact_object(
        raw,
        label="_runtime_context",
        allowed=frozenset(
            {
                "tenant_id",
                "project_id",
                "actor_id",
                "request_id",
                "idempotency_key",
            }
        ),
        required=frozenset(
            {
                "tenant_id",
                "project_id",
                "actor_id",
                "request_id",
                "idempotency_key",
            }
        ),
    )
    for field in ("tenant_id", "project_id", "actor_id", "request_id"):
        value = context.get(field)
        if value is not None:
            _resource(value, f"runtime.{field}")
    idempotency_key = context.get("idempotency_key")
    if idempotency_key is not None:
        _text(idempotency_key, "runtime.idempotency_key", maximum=200)
    return context


def _text(value: Any, label: str, *, maximum: int = 1024) -> str:
    try:
        return require_text(value, label, maximum=maximum)
    except ContractError as exc:
        raise DeliveryContractError(str(exc)) from exc


def _portable_json(value: Any, *, label: str) -> Any:
    try:
        bounded = strict_json(value, label)
        return json.loads(canonical_json_bytes(bounded))
    except (CanonicalizationError, ContractError, TypeError, ValueError) as exc:
        raise DeliveryContractError(f"{label} must be portable canonical JSON") from exc


def _path(value: Any, *, label: str) -> str:
    try:
        return normalize_relative_path(value)
    except (TypeError, UnsafePathError, ValueError) as exc:
        raise DeliveryContractError(f"{label} must be a safe canonical relative path") from exc


def _unique_paths(value: Any, *, label: str) -> tuple[str, ...]:
    raw = _strings(value, label=label, allow_empty=True)
    paths: list[str] = []
    seen: dict[str, str] = {}
    for index, item in enumerate(raw):
        path = _path(item, label=f"{label}[{index}]")
        key = path_collision_key(path)
        if key in seen:
            raise DeliveryContractError(
                f"{label} contains a portable path collision: {seen[key]!r} and {path!r}"
            )
        seen[key] = path
        paths.append(path)
    return tuple(paths)


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise DeliveryContractError(f"{label} must be a SHA-256 digest")
    raw = value.removeprefix("sha256:")
    if re.fullmatch(r"[0-9a-f]{64}", raw) is None:
        raise DeliveryContractError(f"{label} must be a lowercase SHA-256 digest")
    return raw


def _bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise DeliveryContractError(f"{label} must be boolean")
    return value


def _adapter(key: Any):
    normalized = _text(key, "adapter_key", maximum=128)
    try:
        return adapter_for(normalized)
    except AdapterContractError as exc:
        raise DeliveryContractError(str(exc)) from exc


def _native_root(adapter_key: str, value: Any | None) -> str:
    if set(_DEFAULT_NATIVE_ROOTS) != set(ADAPTER_REGISTRY):
        raise DeliveryContractError("test emitter profile registry is incomplete")
    root = _DEFAULT_NATIVE_ROOTS[adapter_key] if value is None else value
    return _path(root, label="native_root")


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    if not normalized:
        normalized = "case"
    if normalized[0].isdigit():
        normalized = "case_" + normalized
    suffix = canonical_digest(value)[:8]
    return f"{normalized[:72]}_{suffix}"


def _class_stem(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    stem = "".join(word[:1].upper() + word[1:] for word in words) or "Case"
    if stem[0].isdigit():
        stem = "Case" + stem
    return f"{stem[:72]}{canonical_digest(value)[:8].upper()}"


def _source_filename(adapter_key: str, test_case_id: str) -> str:
    marker, extension = _SOURCE_SUFFIXES[adapter_key]
    if adapter_key == "python":
        return f"{marker}{_slug(test_case_id)}{extension}"
    if adapter_key in {
        "java-maven",
        "java-gradle",
        "kotlin-maven",
        "kotlin-gradle",
        "dotnet",
        "php-composer",
        "objective-c-xcode",
        "swift-package",
        "swift-xcode",
    }:
        return f"{_class_stem(test_case_id)}{marker}{extension}"
    return f"{_slug(test_case_id)}{marker}{extension}"


def _join(root: str, name: str) -> str:
    return _path(f"{root}/{name}", label="generated path")


def _opaque_segment(prefix: str, value: str) -> str:
    return f"{prefix}_{canonical_digest(value)[:20]}"


def _target_plan(
    adapter_key: str,
    capability_value: Any,
    parameters_value: Any,
) -> Mapping[str, Any]:
    try:
        capability = Capability(capability_value)
    except (TypeError, ValueError) as exc:
        raise DeliveryContractError("target_capability is unsupported") from exc
    if not isinstance(parameters_value, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in parameters_value.items()
    ):
        raise DeliveryContractError("adapter_parameters must be a string-to-string object")
    try:
        proposal = adapter_for(adapter_key).plan(capability, parameters=parameters_value)
        commands = proposal.require_commands()
    except AdapterContractError as exc:
        raise DeliveryContractError("target has no exact repository command template") from exc
    return {
        "adapter_key": adapter_key,
        "capability": capability.value,
        "commands": [
            {"argv": list(command.argv), "cwd": command.cwd, "shell": command.shell}
            for command in commands
        ],
        "execution_status": "NOT_RUN",
        "adapter_qualification": "NOT_RUN",
    }


def _retention_policy(value: Any) -> Mapping[str, Any]:
    policy = _exact_object(
        value,
        label="retention_policy",
        allowed=frozenset(
            {
                "policy_id",
                "classification",
                "retention_days",
                "legal_hold",
                "deletion_mode",
            }
        ),
        required=frozenset(
            {"policy_id", "classification", "retention_days", "legal_hold", "deletion_mode"}
        ),
    )
    policy_id = _resource(policy["policy_id"], "retention_policy.policy_id")
    classification = _text(
        policy["classification"], "retention_policy.classification", maximum=64
    )
    if classification not in _RETENTION_CLASSES:
        raise DeliveryContractError("retention_policy.classification is unsupported")
    days = policy["retention_days"]
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 36_500:
        raise DeliveryContractError("retention_policy.retention_days is invalid")
    legal_hold = _bool(policy["legal_hold"], label="retention_policy.legal_hold")
    deletion_mode = _text(
        policy["deletion_mode"], "retention_policy.deletion_mode", maximum=64
    )
    if deletion_mode != "two-phase":
        raise DeliveryContractError("retention deletion must use two-phase cleanup")
    if classification == "legal-hold" and not legal_hold:
        raise DeliveryContractError("legal-hold retention requires legal_hold=true")
    if legal_hold and classification != "legal-hold":
        raise DeliveryContractError("legal_hold=true requires legal-hold classification")
    return {
        "policy_id": policy_id,
        "classification": classification,
        "retention_days": days,
        "legal_hold": legal_hold,
        "deletion_mode": deletion_mode,
        "cleanup_execution": "NOT_RUN",
    }


def _principal_list(value: Any, *, label: str, allow_empty: bool) -> list[str]:
    items = _strings(value, label=label, allow_empty=allow_empty)
    normalized = [_resource(item, f"{label}[]") for item in items]
    if len(normalized) != len(set(normalized)):
        raise DeliveryContractError(f"{label} may not contain duplicates")
    return sorted(normalized)


def _permission_policy(value: Any) -> Mapping[str, Any]:
    policy = _exact_object(
        value,
        label="permission_policy",
        allowed=frozenset(
            {
                "policy_id",
                "owner_principals",
                "reader_principals",
                "writer_principals",
                "publisher_service",
            }
        ),
        required=frozenset(
            {
                "policy_id",
                "owner_principals",
                "reader_principals",
                "writer_principals",
                "publisher_service",
            }
        ),
    )
    owners = _principal_list(
        policy["owner_principals"], label="permission_policy.owner_principals", allow_empty=False
    )
    readers = _principal_list(
        policy["reader_principals"], label="permission_policy.reader_principals", allow_empty=True
    )
    writers = _principal_list(
        policy["writer_principals"], label="permission_policy.writer_principals", allow_empty=True
    )
    if not set(writers).issubset(owners):
        raise DeliveryContractError("writer principals must be explicit output owners")
    publisher = _resource(policy["publisher_service"], "permission_policy.publisher_service")
    if publisher != "ArtifactPublisher":
        raise DeliveryContractError("only the trusted ArtifactPublisher service may publish")
    return {
        "policy_id": _resource(policy["policy_id"], "permission_policy.policy_id"),
        "owner_principals": owners,
        "reader_principals": readers,
        "writer_principals": writers,
        "publisher_service": publisher,
        "authorization_evaluation": "NOT_RUN",
        "caller_authorization_accepted": False,
    }


def _secret_policy(value: Any) -> Mapping[str, Any]:
    policy = _exact_object(
        value,
        label="secret_policy",
        allowed=frozenset(
            {
                "scan_required",
                "inline_secrets_allowed",
                "allowed_secret_refs",
                "redaction_required",
            }
        ),
        required=frozenset(
            {
                "scan_required",
                "inline_secrets_allowed",
                "allowed_secret_refs",
                "redaction_required",
            }
        ),
    )
    scan_required = _bool(policy["scan_required"], label="secret_policy.scan_required")
    inline_allowed = _bool(
        policy["inline_secrets_allowed"], label="secret_policy.inline_secrets_allowed"
    )
    redaction_required = _bool(
        policy["redaction_required"], label="secret_policy.redaction_required"
    )
    if not scan_required or inline_allowed or not redaction_required:
        raise DeliveryContractError(
            "secret policy must require scanning/redaction and forbid inline secrets"
        )
    refs = _principal_list(
        policy["allowed_secret_refs"],
        label="secret_policy.allowed_secret_refs",
        allow_empty=True,
    )
    return {
        "scan_required": True,
        "inline_secrets_allowed": False,
        "allowed_secret_refs": refs,
        "redaction_required": True,
        "secret_resolution": "NOT_RUN",
    }


def _planned_cases(value: Any) -> list[Mapping[str, Any]]:
    cases = _objects(value, label="test_cases")
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(cases):
        case = _exact_object(
            item,
            label=f"test_cases[{index}]",
            allowed=frozenset(
                {"test_case_id", "test_type", "required", "requirement_refs", "logical_path"}
            ),
            required=frozenset(
                {"test_case_id", "test_type", "required", "requirement_refs"}
            ),
        )
        case_id = _resource(case["test_case_id"], "test_case.test_case_id")
        if case_id in seen:
            raise DeliveryContractError(f"duplicate test_case_id: {case_id}")
        seen.add(case_id)
        test_type = _text(case["test_type"], "test_case.test_type", maximum=64)
        if test_type not in TEST_TYPES:
            raise DeliveryContractError(f"unsupported test_type: {test_type}")
        required = _bool(case["required"], label="test_case.required")
        requirement_refs = _principal_list(
            case["requirement_refs"], label="test_case.requirement_refs", allow_empty=False
        )
        logical_path = case.get(
            "logical_path", f"qa/test-cases/{test_type}/{_slug(case_id)}"
        )
        result.append(
            {
                "test_case_id": case_id,
                "test_type": test_type,
                "required": required,
                "requirement_refs": requirement_refs,
                "logical_path": _path(logical_path, label="test_case.logical_path"),
            }
        )
    return result


def plan_project_output_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Plan Skill 36 output identities and paths without touching the filesystem."""

    request = _exact_object(
        inputs,
        label="project output request",
        allowed=frozenset(
            {
                "tenant_id",
                "project_id",
                "revision_id",
                "run_id",
                "run_mode",
                "source_snapshot_digest",
                "output_mode",
                "adapter_key",
                "native_root",
                "target_capability",
                "adapter_parameters",
                "test_cases",
                "retention_policy",
                "permission_policy",
                "secret_policy",
                "existing_paths",
                "_runtime_context",
            }
        ),
        required=frozenset(
            {
                "tenant_id",
                "project_id",
                "revision_id",
                "run_id",
                "run_mode",
                "source_snapshot_digest",
                "output_mode",
                "adapter_key",
                "test_cases",
                "retention_policy",
                "permission_policy",
                "secret_policy",
            }
        ),
    )
    tenant_id = _resource(request["tenant_id"], "tenant_id")
    project_id = _resource(request["project_id"], "project_id")
    runtime_context = _runtime_context(request)
    if runtime_context:
        if runtime_context.get("tenant_id") != tenant_id:
            raise DeliveryContractError("tenant_id differs from the trusted runtime context")
        if runtime_context.get("project_id") != project_id:
            raise DeliveryContractError("project_id differs from the trusted runtime context")
    revision_id = _resource(request["revision_id"], "revision_id")
    run_id = _resource(request["run_id"], "run_id")
    run_mode = _text(request["run_mode"], "run_mode", maximum=32)
    if run_mode not in _RUN_MODES:
        raise DeliveryContractError("run_mode is unsupported")
    output_mode = _text(request["output_mode"], "output_mode", maximum=32)
    if output_mode not in _OUTPUT_MODES:
        raise DeliveryContractError("output_mode is unsupported")
    source_snapshot_digest = _sha256(
        request["source_snapshot_digest"], label="source_snapshot_digest"
    )
    adapter = _adapter(request["adapter_key"])
    native_root = _native_root(adapter.key, request.get("native_root"))
    target = _target_plan(
        adapter.key,
        request.get("target_capability", Capability.UNIT.value),
        request.get("adapter_parameters", {}),
    )
    cases = _planned_cases(request["test_cases"])
    retention = _retention_policy(request["retention_policy"])
    permissions = _permission_policy(request["permission_policy"])
    secrets = _secret_policy(request["secret_policy"])
    existing_paths = _unique_paths(
        request.get("existing_paths", []), label="existing_paths"
    )

    identity = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "revision_id": revision_id,
        "run_id": run_id,
        "source_snapshot_digest": source_snapshot_digest,
        "output_mode": output_mode,
        "run_mode": run_mode,
    }
    # This is byte-for-byte the identity and digest algorithm used by OutputPlan.
    output_id = f"out_{canonical_digest(identity)[:24]}"
    object_prefix = "/".join(
        (
            _opaque_segment("tenant", tenant_id),
            _opaque_segment("project", project_id),
            _opaque_segment("revision", revision_id),
            _opaque_segment("output", output_id),
        )
    )

    mappings: list[dict[str, Any]] = []
    planned_path_keys: dict[str, str] = {}
    logical_keys: dict[str, str] = {}
    for case in cases:
        filename = _source_filename(adapter.key, case["test_case_id"])
        native_path = _join(native_root, filename)
        logical_path = case["logical_path"]
        logical_key = path_collision_key(logical_path)
        native_key = path_collision_key(native_path)
        if logical_key in logical_keys:
            raise DeliveryContractError(
                f"logical path collision: {logical_keys[logical_key]!r} and {logical_path!r}"
            )
        if native_key in planned_path_keys:
            raise DeliveryContractError(
                f"native path collision: {planned_path_keys[native_key]!r} and {native_path!r}"
            )
        logical_keys[logical_key] = logical_path
        planned_path_keys[native_key] = native_path
        artifact_identity = {
            "output_id": output_id,
            "logical_path": logical_path,
            "native_path": native_path,
            "test_case_id": case["test_case_id"],
        }
        artifact_id = f"art_{canonical_digest(artifact_identity)[:24]}"
        mappings.append(
            {
                "logical_path": logical_path,
                "native_path": native_path,
                "target": {
                    "adapter_key": adapter.key,
                    "capability": target["capability"],
                    "native_root": native_root,
                },
                "artifact_id": artifact_id,
                "object_key": f"{object_prefix}/artifacts/{artifact_id}/{filename}",
                "category": "test",
                "role": "generated-test-source",
                "required": case["required"],
                "test_case_refs": [case["test_case_id"]],
                "requirement_refs": case["requirement_refs"],
                "content_state": "PLANNED",
            }
        )

    existing_by_key = {path_collision_key(path): path for path in existing_paths}
    conflicts = [
        {
            "planned_path": planned,
            "existing_path": existing_by_key[key],
            "collision_key": key,
            "decision": "BLOCKED_NO_OVERWRITE",
        }
        for key, planned in sorted(planned_path_keys.items())
        if key in existing_by_key
    ]
    collision_policy = {
        "identity": "NFC_CASEFOLD_PORTABLE_PATH",
        "intrinsic_collisions_allowed": False,
        "existing_path_collisions_allowed": False,
    }
    no_overwrite_policy = {
        "mode": "CREATE_ONLY",
        "overwrite_existing": False,
        "overwrite_unmanaged": False,
        "merge_existing": False,
    }
    manifest_body = {
        "schema_version": "elmos.autonomous-qa.project-output-manifest-draft.v1",
        "status": "DRAFT",
        "output_id": output_id,
        "revision_id": revision_id,
        "identity": identity,
        "adapter_key": adapter.key,
        "target": target,
        "logical_native_mappings": mappings,
        "retention_policy": retention,
        "permission_policy": permissions,
        "secret_policy": secrets,
        "collision_policy": collision_policy,
        "no_overwrite_policy": no_overwrite_policy,
        "publication_state": "NOT_RUN",
        "certification_state": "NOT_CERTIFIED",
    }
    manifest_draft = {
        **manifest_body,
        "draft_digest": f"sha256:{canonical_digest(manifest_body)}",
    }
    blocked = bool(conflicts)
    return {
        "state": "BLOCKED" if blocked else "PARTIAL",
        "code": (
            "PROJECT_OUTPUT_COLLISION_BLOCKED"
            if blocked
            else "PROJECT_OUTPUT_CONTRACT_PLANNED_PREFLIGHT_REQUIRED"
        ),
        "implementation_state": "LOCAL_EXECUTED",
        "outputs": {
            "contract_schema_version": _SCHEMA_VERSION,
            "output_id": output_id,
            "revision_id": revision_id,
            "output_plan_identity": identity,
            "output_plan_compatibility": {
                "compatible_with": "elmos_autonomous_qa.artifacts.OutputPlan",
                "identity_algorithm": "canonical_digest(canonical_json_bytes)-first-24",
                "compatible": True,
                "filesystem_bound_constructor_used": False,
            },
            "logical_native_mappings": mappings,
            "target": target,
            "manifest_draft": manifest_draft,
            "retention_policy": retention,
            "permission_policy": permissions,
            "secret_policy": secrets,
            "preflight": {
                "planned_path_validation": "LOCAL_EXECUTED",
                "planned_path_collision_check": "LOCAL_EXECUTED",
                "caller_existing_path_snapshot_check": "FAILED" if blocked else "PASSED",
                "filesystem_existing_path_check": "NOT_RUN",
                "permission_evaluation": "NOT_RUN",
                "secret_scan": "NOT_RUN",
                "conflicts": conflicts,
                "complete": False,
            },
            "collision_policy": collision_policy,
            "no_overwrite_policy": no_overwrite_policy,
            "execution_boundary": {
                "filesystem_access_performed": False,
                "staging": "NOT_RUN",
                "materialization": "NOT_RUN",
                "publication": "NOT_RUN",
                "trusted_artifact_publisher_service": "EXTERNAL_ADAPTER_REQUIRED",
                "trusted_artifact_publisher_service_required": True,
            },
        },
    }


def _payload(case: Mapping[str, Any], suite_id: str, dsl_digest: str) -> str:
    descriptor = {
        "schema_version": "elmos.autonomous-qa.runtime-test-case.v1",
        "suite_id": suite_id,
        "dsl_digest": dsl_digest,
        "test_case": case,
        "runtime_contract": {
            "operation": "execute_case",
            "side_effects_require_authorized_adapter": True,
            "oracle_results_must_be_observed": True,
            "synthetic_success_forbidden": True,
        },
    }
    raw = canonical_json_bytes(descriptor)
    return base64.b64encode(raw).decode("ascii")


def _oracle_ids(case: Mapping[str, Any]) -> list[str]:
    return [str(oracle["oracle_id"]) for oracle in case["oracles"]]


def _emit_java(case: Mapping[str, Any], payload: str) -> str:
    name = _class_stem(str(case["test_case_id"])) + "Test"
    assertions = "\n".join(
        f'        observation.assertOracle("{oracle_id}");'
        for oracle_id in _oracle_ids(case)
    )
    return (
        "import org.junit.jupiter.api.Test;\n"
        "import com.elmos.qa.runtime.ElmosQaRuntime;\n"
        "import com.elmos.qa.runtime.QaObservation;\n\n"
        f"final class {name} {{\n"
        "    @Test\n"
        "    void executesDeclaredContract() throws Exception {\n"
        f'        QaObservation observation = ElmosQaRuntime.executeCaseBase64("{payload}");\n'
        f"{assertions}\n"
        "    }\n"
        "}\n"
    )


def _emit_kotlin(case: Mapping[str, Any], payload: str) -> str:
    name = _class_stem(str(case["test_case_id"])) + "Test"
    assertions = "\n".join(
        f'        observation.assertOracle("{oracle_id}")'
        for oracle_id in _oracle_ids(case)
    )
    return (
        "import org.junit.jupiter.api.Test\n"
        "import com.elmos.qa.runtime.ElmosQaRuntime\n\n"
        f"class {name} {{\n"
        "    @Test\n"
        "    fun executesDeclaredContract() {\n"
        f'        val observation = ElmosQaRuntime.executeCaseBase64("{payload}")\n'
        f"{assertions}\n"
        "    }\n"
        "}\n"
    )


def _emit_python(case: Mapping[str, Any], payload: str) -> str:
    assertions = "\n".join(
        f'    observation.assert_oracle("{oracle_id}")'
        for oracle_id in _oracle_ids(case)
    )
    return (
        "from elmos_qa_runtime import execute_case_base64\n\n\n"
        f"def test_{_slug(str(case['test_case_id']))}() -> None:\n"
        f'    observation = execute_case_base64("{payload}")\n'
        f"{assertions}\n"
    )


def _emit_dotnet(case: Mapping[str, Any], payload: str) -> str:
    name = _class_stem(str(case["test_case_id"])) + "Tests"
    assertions = "\n".join(
        f'        await observation.AssertOracleAsync("{oracle_id}");'
        for oracle_id in _oracle_ids(case)
    )
    return (
        "using System.Threading.Tasks;\n"
        "using Elmos.Qa.Runtime;\n"
        "using Xunit;\n\n"
        f"public sealed class {name}\n{{\n"
        "    [Fact]\n"
        "    public async Task ExecutesDeclaredContract()\n    {\n"
        f'        var observation = await ElmosQaRuntime.ExecuteCaseBase64Async("{payload}");\n'
        f"{assertions}\n"
        "    }\n"
        "}\n"
    )


def _emit_go(case: Mapping[str, Any], payload: str) -> str:
    name = "Test" + _class_stem(str(case["test_case_id"]))
    assertions = "\n".join(
        f'\tobservation.AssertOracle(t, "{oracle_id}")'
        for oracle_id in _oracle_ids(case)
    )
    return (
        "package elmosqa_generated\n\n"
        "import (\n"
        '\t"testing"\n'
        '\telmosqa "github.com/elmos/qa-runtime-go"\n'
        ")\n\n"
        f"func {name}(t *testing.T) {{\n"
        f'\tobservation, err := elmosqa.ExecuteCaseBase64("{payload}")\n'
        '\tif err != nil {\n\t\tt.Fatalf("runtime execution failed: %v", err)\n\t}\n'
        f"{assertions}\n"
        "}\n"
    )


def _emit_rust(case: Mapping[str, Any], payload: str) -> str:
    assertions = "\n".join(
        f'    observation.assert_oracle("{oracle_id}").expect("oracle evaluation failed");'
        for oracle_id in _oracle_ids(case)
    )
    return (
        "#[test]\n"
        f"fn {_slug(str(case['test_case_id']))}() {{\n"
        f'    let observation = elmos_qa_runtime::execute_case_base64("{payload}")\n'
        '        .expect("runtime execution failed");\n'
        f"{assertions}\n"
        "}\n"
    )


def _emit_cpp(case: Mapping[str, Any], payload: str) -> str:
    assertions = "\n".join(
        f'    observation.assert_oracle("{oracle_id}");'
        for oracle_id in _oracle_ids(case)
    )
    return (
        "#include <elmos/qa/runtime.hpp>\n\n"
        "int main() {\n"
        f'    auto observation = elmos::qa::execute_case_base64("{payload}");\n'
        f"{assertions}\n"
        "    return 0;\n"
        "}\n"
    )


def _emit_php(case: Mapping[str, Any], payload: str) -> str:
    name = _class_stem(str(case["test_case_id"])) + "Test"
    assertions = "\n".join(
        f"        $observation->assertOracle($this, '{oracle_id}');"
        for oracle_id in _oracle_ids(case)
    )
    return (
        "<?php\n"
        "declare(strict_types=1);\n\n"
        "use PHPUnit\\Framework\\TestCase;\n"
        "use Elmos\\Qa\\Runtime;\n\n"
        f"final class {name} extends TestCase\n{{\n"
        "    public function testDeclaredContract(): void\n    {\n"
        f"        $observation = Runtime::executeCaseBase64('{payload}');\n"
        f"{assertions}\n"
        "    }\n"
        "}\n"
    )


def _emit_node(case: Mapping[str, Any], payload: str) -> str:
    assertions = "\n".join(
        f'  await observation.assertOracle("{oracle_id}");'
        for oracle_id in _oracle_ids(case)
    )
    return (
        'import test from "node:test";\n'
        'import { executeCaseBase64 } from "@elmos/qa-runtime";\n\n'
        f'test("{case["test_case_id"]}", async () => {{\n'
        f'  const observation = await executeCaseBase64("{payload}");\n'
        f"{assertions}\n"
        "});\n"
    )


def _emit_objc(case: Mapping[str, Any], payload: str) -> str:
    name = _class_stem(str(case["test_case_id"])) + "Tests"
    assertions = "\n".join(
        f'    [observation assertOracle:@"{oracle_id}" testCase:self];'
        for oracle_id in _oracle_ids(case)
    )
    return (
        "#import <XCTest/XCTest.h>\n"
        "#import <ELMOSQaRuntime/ELMOSQaRuntime.h>\n\n"
        f"@interface {name} : XCTestCase\n@end\n\n"
        f"@implementation {name}\n"
        "- (void)testDeclaredContract {\n"
        f'    ELMOSQaObservation *observation = [ELMOSQaRuntime executeCaseBase64:@"{payload}"];\n'
        f"{assertions}\n"
        "}\n"
        "@end\n"
    )


def _emit_swift(case: Mapping[str, Any], payload: str) -> str:
    name = _class_stem(str(case["test_case_id"])) + "Tests"
    assertions = "\n".join(
        f'        try observation.assertOracle("{oracle_id}")'
        for oracle_id in _oracle_ids(case)
    )
    return (
        "import XCTest\n"
        "import ELMOSQaRuntime\n\n"
        f"final class {name}: XCTestCase {{\n"
        "    func testDeclaredContract() throws {\n"
        f'        let observation = try ELMOSQaRuntime.executeCaseBase64("{payload}")\n'
        f"{assertions}\n"
        "    }\n"
        "}\n"
    )


def _emit_flutter(case: Mapping[str, Any], payload: str) -> str:
    assertions = "\n".join(
        f"    await observation.assertOracle('{oracle_id}');"
        for oracle_id in _oracle_ids(case)
    )
    return (
        "import 'package:flutter_test/flutter_test.dart';\n"
        "import 'package:elmos_qa_runtime/elmos_qa_runtime.dart';\n\n"
        "void main() {\n"
        f"  test('{case['test_case_id']}', () async {{\n"
        f"    final observation = await ElmosQaRuntime.executeCaseBase64('{payload}');\n"
        f"{assertions}\n"
        "  });\n"
        "}\n"
    )


_EMITTERS: Mapping[str, Callable[[Mapping[str, Any], str], str]] = {
    "java-maven": _emit_java,
    "java-gradle": _emit_java,
    "kotlin-maven": _emit_kotlin,
    "kotlin-gradle": _emit_kotlin,
    "python": _emit_python,
    "dotnet": _emit_dotnet,
    "go": _emit_go,
    "rust": _emit_rust,
    "cmake-c-cpp": _emit_cpp,
    "php-composer": _emit_php,
    "javascript-node": _emit_node,
    "typescript-node": _emit_node,
    "react": _emit_node,
    "vue": _emit_node,
    "objective-c-xcode": _emit_objc,
    "swift-package": _emit_swift,
    "swift-xcode": _emit_swift,
    "flutter": _emit_flutter,
}


def _scan_source(text: str) -> list[Mapping[str, Any]]:
    findings: list[Mapping[str, Any]] = []
    for code, pattern in _SOURCE_QUALITY_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            findings.append(
                {
                    "code": code,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "status": "REJECTED",
                }
            )
    return findings


def _scan_secrets(text: str) -> list[Mapping[str, Any]]:
    findings: list[Mapping[str, Any]] = []
    for code, pattern in _SECRET_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            findings.append(
                {
                    "code": code,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "status": "REJECTED",
                }
            )
    return findings


def _reject_unsafe_config_controls(value: Any, *, location: str = "config") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).casefold().replace("-", "_")
            if key in {
                "disable",
                "disabled",
                "skip",
                "skipped",
                "ignore",
                "ignored",
                "fixed_sleep_ms",
                "sleep_ms",
            } and not (item is False or item is None or item == 0 or item == ""):
                raise DeliveryContractError(
                    f"{location}.{raw_key} attempts to disable or delay generated tests"
                )
            _reject_unsafe_config_controls(item, location=f"{location}.{raw_key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_unsafe_config_controls(item, location=f"{location}[{index}]")


def _unified_new_file_diff(path: str, text: str) -> str:
    lines = text.splitlines()
    body = "\n".join("+" + line for line in lines)
    return f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}\n"


def _artifact(
    *,
    suite_id: str,
    adapter_key: str,
    path: str,
    text: str,
    category: str,
    role: str,
    test_case_refs: Sequence[str],
    requirement_refs: Sequence[str],
    dsl_digest: str,
    replay_commands: Sequence[Mapping[str, Any]],
    source_quality_scan: bool,
) -> Mapping[str, Any]:
    if not text.endswith("\n"):
        raise DeliveryContractError("emitted text artifacts must end with one newline")
    secret_findings = _scan_secrets(text)
    quality_findings = _scan_source(text) if source_quality_scan else []
    findings = [*quality_findings, *secret_findings]
    if findings:
        codes = sorted({str(finding["code"]) for finding in findings})
        raise DeliveryContractError(f"emitted artifact rejected by local scan: {codes}")
    content = text.encode("utf-8")
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    identity = {"suite_id": suite_id, "path": path, "sha256": digest}
    artifact_id = f"art_{canonical_digest(identity)[:24]}"
    replay = [dict(command) for command in replay_commands]
    return {
        "artifact_id": artifact_id,
        "path": path,
        "category": category,
        "role": role,
        "source_text": text,
        "content_base64": base64.b64encode(content).decode("ascii"),
        "encoding": "utf-8",
        "sha256": digest,
        "size_bytes": len(content),
        "producer": _EMITTER_VERSION,
        "required": True,
        "validation_status": "generated-unvalidated",
        "test_case_refs": sorted(set(test_case_refs)),
        "requirement_refs": sorted(set(requirement_refs)),
        "lineage": {
            "suite_id": suite_id,
            "dsl_digest": dsl_digest,
            "adapter_key": adapter_key,
            "emitter_version": _EMITTER_VERSION,
            "content_sha256": digest,
            "test_case_refs": sorted(set(test_case_refs)),
            "requirement_refs": sorted(set(requirement_refs)),
        },
        "quality_scan": {
            "status": "LOCAL_EXECUTED",
            "findings": [],
            "rules": [code for code, _pattern in _SOURCE_QUALITY_PATTERNS]
            if source_quality_scan
            else [],
            "secret_rules": [code for code, _pattern in _SECRET_PATTERNS],
        },
        "diff": _unified_new_file_diff(path, text),
        "replay_argv": replay[0]["argv"] if replay else [],
        "replay_commands": replay,
        "object_key_draft": f"pending-publication/{artifact_id}",
    }


def _data_artifacts(
    *,
    kind: str,
    values: Any,
    suite_id: str,
    adapter_key: str,
    root: str,
    dsl_digest: str,
    replay_commands: Sequence[Mapping[str, Any]],
    allowed_test_case_refs: frozenset[str],
    allowed_requirement_refs: frozenset[str],
) -> list[Mapping[str, Any]]:
    records = _objects(values, label=f"{kind}_records", allow_empty=True)
    artifacts: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(records):
        record = _exact_object(
            raw,
            label=f"{kind}_records[{index}]",
            allowed=frozenset(
                {"data_id", "content", "test_case_refs", "requirement_refs"}
            ),
            required=frozenset(
                {"data_id", "content", "test_case_refs", "requirement_refs"}
            ),
        )
        data_id = _resource(record["data_id"], f"{kind}.data_id")
        if data_id in seen:
            raise DeliveryContractError(f"duplicate {kind} data_id: {data_id}")
        seen.add(data_id)
        case_refs = _principal_list(
            record["test_case_refs"], label=f"{kind}.test_case_refs", allow_empty=False
        )
        requirement_refs = _principal_list(
            record["requirement_refs"],
            label=f"{kind}.requirement_refs",
            allow_empty=False,
        )
        unknown_cases = sorted(set(case_refs).difference(allowed_test_case_refs))
        unknown_requirements = sorted(
            set(requirement_refs).difference(allowed_requirement_refs)
        )
        if unknown_cases:
            raise DeliveryContractError(
                f"{kind} data has unknown test_case_refs: {unknown_cases}"
            )
        if unknown_requirements:
            raise DeliveryContractError(
                f"{kind} data has unknown requirement_refs: {unknown_requirements}"
            )
        content = _portable_json(record["content"], label=f"{kind}.content")
        text = canonical_json_bytes(
            {
                "schema_version": f"elmos.autonomous-qa.{kind}-data.v1",
                "data_id": data_id,
                "content": content,
            }
        ).decode("utf-8")
        secret_findings = _scan_secrets(text)
        if secret_findings:
            raise DeliveryContractError(f"{kind} data contains a possible inline secret")
        path = _join(f"{root}/{kind}", f"{_slug(data_id)}.json")
        artifacts.append(
            _artifact(
                suite_id=suite_id,
                adapter_key=adapter_key,
                path=path,
                text=text,
                category=f"{kind}-data",
                role=f"generated-{kind}-data",
                test_case_refs=case_refs,
                requirement_refs=requirement_refs,
                dsl_digest=dsl_digest,
                replay_commands=replay_commands,
                source_quality_scan=False,
            )
        )
    return artifacts


def _unique_command_plans(cases: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    commands: list[Mapping[str, Any]] = []
    identities: set[str] = set()
    for case in cases:
        for command in case["executor"]["command_plan_proposal"]:
            identity = canonical_digest(command)
            if identity not in identities:
                identities.add(identity)
                commands.append(dict(command))
    return commands


def emit_test_sources(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Emit Skill 37 source/data bytes in memory after strict DSL validation."""

    request = _exact_object(
        inputs,
        label="test source emission request",
        allowed=frozenset(
            {
                "suite_id",
                "adapter_key",
                "native_root",
                "test_cases",
                "fixture_records",
                "mock_records",
                "synthetic_data_records",
                "config",
                "existing_paths",
                "_runtime_context",
            }
        ),
        required=frozenset({"suite_id", "adapter_key", "test_cases"}),
    )
    suite_id = _resource(request["suite_id"], "suite_id")
    runtime_context = _runtime_context(request)
    adapter = _adapter(request["adapter_key"])
    if set(_EMITTERS) != set(ADAPTER_REGISTRY):
        raise DeliveryContractError("test source emitter registry is incomplete")
    native_root = _native_root(adapter.key, request.get("native_root"))
    existing_paths = _unique_paths(
        request.get("existing_paths", []), label="existing_paths"
    )
    try:
        validation = validate_test_dsl({"test_cases": request["test_cases"]})
    except ContractError as exc:
        raise DeliveryContractError(f"Test DSL validation failed: {exc}") from exc
    cases = list(validation["outputs"]["test_cases"])
    dsl_digest = str(validation["outputs"]["dsl_digest"])
    for case in cases:
        if case["executor"]["adapter_key"] != adapter.key:
            raise DeliveryContractError(
                "every Test DSL executor must match the requested adapter profile"
            )

    all_commands = _unique_command_plans(cases)
    allowed_test_case_refs = frozenset(str(case["test_case_id"]) for case in cases)
    allowed_requirement_refs = frozenset(
        str(item) for case in cases for item in case["requirement_refs"]
    )
    artifacts: list[Mapping[str, Any]] = []
    emitter = _EMITTERS[adapter.key]
    for case in cases:
        descriptor_text = base64.b64decode(
            _payload(case, suite_id, dsl_digest).encode("ascii"), validate=True
        ).decode("utf-8")
        if _scan_secrets(descriptor_text):
            raise DeliveryContractError(
                f"test {case['test_case_id']} contains a possible inline secret"
            )
        descriptor_findings = _scan_source(descriptor_text)
        if descriptor_findings:
            codes = sorted({str(finding["code"]) for finding in descriptor_findings})
            raise DeliveryContractError(
                f"test {case['test_case_id']} contains forbidden source semantics: {codes}"
            )
        payload = base64.b64encode(descriptor_text.encode("utf-8")).decode("ascii")
        text = emitter(case, payload)
        filename = _source_filename(adapter.key, str(case["test_case_id"]))
        path = _join(native_root, filename)
        replay_commands = [dict(command) for command in case["executor"]["command_plan_proposal"]]
        artifacts.append(
            _artifact(
                suite_id=suite_id,
                adapter_key=adapter.key,
                path=path,
                text=text,
                category="test-source",
                role="generated-test-source",
                test_case_refs=[str(case["test_case_id"])],
                requirement_refs=list(case["requirement_refs"]),
                dsl_digest=dsl_digest,
                replay_commands=replay_commands,
                source_quality_scan=True,
            )
        )

    data_root = _join("elmos-qa/generated", _slug(suite_id))
    for kind, field in (
        ("fixture", "fixture_records"),
        ("mock", "mock_records"),
        ("synthetic", "synthetic_data_records"),
    ):
        artifacts.extend(
            _data_artifacts(
                kind=kind,
                values=request.get(field, []),
                suite_id=suite_id,
                adapter_key=adapter.key,
                root=data_root,
                dsl_digest=dsl_digest,
                replay_commands=all_commands,
                allowed_test_case_refs=allowed_test_case_refs,
                allowed_requirement_refs=allowed_requirement_refs,
            )
        )

    config = request.get("config", {})
    if not isinstance(config, Mapping):
        raise DeliveryContractError("config must be an object")
    config_value = _portable_json(config, label="config")
    _reject_unsafe_config_controls(config_value)
    config_text = canonical_json_bytes(
        {
            "schema_version": "elmos.autonomous-qa.generated-test-config.v1",
            "suite_id": suite_id,
            "adapter_key": adapter.key,
            "dsl_digest": dsl_digest,
            "runtime_binding": {
                "contract": "ElmosQaRuntime.execute_case",
                "state": "EXTERNAL_ADAPTER_REQUIRED",
            },
            "config": config_value,
        }
    ).decode("utf-8")
    if _scan_secrets(config_text):
        raise DeliveryContractError("config contains a possible inline secret")
    config_quality_findings = _scan_source(config_text)
    if config_quality_findings:
        codes = sorted({str(finding["code"]) for finding in config_quality_findings})
        raise DeliveryContractError(f"config contains forbidden test controls: {codes}")
    all_case_refs = [str(case["test_case_id"]) for case in cases]
    all_requirement_refs = sorted(
        {str(item) for case in cases for item in case["requirement_refs"]}
    )
    artifacts.append(
        _artifact(
            suite_id=suite_id,
            adapter_key=adapter.key,
            path=_join(data_root, "config.json"),
            text=config_text,
            category="config",
            role="generated-runtime-config",
            test_case_refs=all_case_refs,
            requirement_refs=all_requirement_refs,
            dsl_digest=dsl_digest,
            replay_commands=all_commands,
            source_quality_scan=False,
        )
    )

    planned: dict[str, str] = {}
    for artifact in artifacts:
        key = path_collision_key(str(artifact["path"]))
        if key in planned:
            raise DeliveryContractError(
                f"generated path collision: {planned[key]!r} and {artifact['path']!r}"
            )
        planned[key] = str(artifact["path"])
    existing_by_key = {path_collision_key(path): path for path in existing_paths}
    collisions = [
        (planned_path, existing_by_key[key])
        for key, planned_path in sorted(planned.items())
        if key in existing_by_key
    ]
    if collisions:
        rendered = ", ".join(f"{planned!r}/{existing!r}" for planned, existing in collisions)
        raise DeliveryContractError(f"generated paths collide with existing paths: {rendered}")

    manifest_body = {
        "schema_version": "elmos.autonomous-qa.generated-test-manifest-draft.v1",
        "status": "DRAFT",
        "suite_id": suite_id,
        "adapter_key": adapter.key,
        "native_root": native_root,
        "dsl_digest": dsl_digest,
        "runtime_scope": {
            "binding_state": "BOUND" if runtime_context else "UNBOUND",
            "tenant_id": runtime_context.get("tenant_id"),
            "project_id": runtime_context.get("project_id"),
            "request_id": runtime_context.get("request_id"),
        },
        "files": [
            {
                "artifact_id": artifact["artifact_id"],
                "path": artifact["path"],
                "sha256": artifact["sha256"],
                "size_bytes": artifact["size_bytes"],
                "category": artifact["category"],
                "role": artifact["role"],
                "test_case_refs": artifact["test_case_refs"],
                "requirement_refs": artifact["requirement_refs"],
            }
            for artifact in artifacts
        ],
        "replay_commands": all_commands,
        "materialization_state": "NOT_RUN",
        "publication_state": "NOT_RUN",
        "certification_state": "NOT_CERTIFIED",
    }
    manifest_draft = {
        **manifest_body,
        "draft_digest": f"sha256:{canonical_digest(manifest_body)}",
    }
    return {
        "state": "PARTIAL",
        "code": "TEST_SOURCES_EMITTED_EXTERNAL_VALIDATION_REQUIRED",
        "implementation_state": "LOCAL_EXECUTED",
        "outputs": {
            "contract_schema_version": _SCHEMA_VERSION,
            "suite_id": suite_id,
            "adapter_key": adapter.key,
            "supported_adapter_profiles": sorted(ADAPTER_REGISTRY),
            "dsl_digest": dsl_digest,
            "dsl_validation_state": validation["code"],
            "artifacts": artifacts,
            "source_artifact_count": sum(
                artifact["category"] == "test-source" for artifact in artifacts
            ),
            "fixture_artifact_count": sum(
                artifact["category"] == "fixture-data" for artifact in artifacts
            ),
            "mock_artifact_count": sum(
                artifact["category"] == "mock-data" for artifact in artifacts
            ),
            "synthetic_data_artifact_count": sum(
                artifact["category"] == "synthetic-data" for artifact in artifacts
            ),
            "config_artifact_count": 1,
            "manifest_draft": manifest_draft,
            "quality_scan": {
                "state": "LOCAL_EXECUTED",
                "findings": [],
                "forbidden_rules": [code for code, _pattern in _SOURCE_QUALITY_PATTERNS],
                "secret_rules": [code for code, _pattern in _SECRET_PATTERNS],
            },
            "diff_state": "LOCAL_EXECUTED",
            "replay_commands": all_commands,
            "collision_policy": {
                "identity": "NFC_CASEFOLD_PORTABLE_PATH",
                "unsafe_paths_allowed": False,
                "collisions_allowed": False,
                "overwrite_allowed": False,
            },
            "execution_boundary": {
                "filesystem_access_performed": False,
                "staging": "NOT_RUN",
                "materialization": "NOT_RUN",
                "formatter": "NOT_RUN",
                "native_parser": "NOT_RUN",
                "native_linter": "NOT_RUN",
                "test_discovery": "NOT_RUN",
                "native_build": "NOT_RUN",
                "smoke_execution": "NOT_RUN",
                "parser": "NOT_RUN",
                "linter": "NOT_RUN",
                "discovery": "NOT_RUN",
                "build": "NOT_RUN",
                "smoke": "NOT_RUN",
                "runtime_binding": "EXTERNAL_ADAPTER_REQUIRED",
                "publisher_service": "EXTERNAL_ADAPTER_REQUIRED",
                "trusted_artifact_publisher_service_required": True,
                "materialization_authorized": False,
                "publication_authorized": False,
            },
        },
    }


__all__ = [
    "DeliveryContractError",
    "emit_test_sources",
    "plan_project_output_contract",
]
