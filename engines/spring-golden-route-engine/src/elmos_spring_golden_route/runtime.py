"""Distinct per-Skill bounded dispatch for describe and draft planning."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .canonical import canonical_bytes, parse_json_strict, sha256_digest, validate_json_value
from .catalog import Catalog, EXPECTED_SKILL_COUNT, SkillContract, load_catalog
from .errors import ExternalAdapterRequired, RequestValidationError, UnknownSkillError

REQUEST_SCHEMA_VERSION = "elmos.spring-golden-route.request.v1"
RESPONSE_SCHEMA_VERSION = "elmos.spring-golden-route.response.v2"
LOCAL_EXECUTED_SELF_ATTESTED = "LOCAL_EXECUTED_SELF_ATTESTED"
NOT_RUN = "NOT_RUN"
NOT_CERTIFIED = "NOT_CERTIFIED"

_REQUEST_KEYS = {
    "schema_version",
    "operation",
    "skill_name",
    "tenant_id",
    "project_id",
    "run_id",
    "task_id",
    "actor_id",
    "idempotency_key",
    "input",
}
_PLAN_KEYS = {"objective", "source", "target", "constraints", "requested_outputs"}
_PROFILE_KEYS = {"framework", "version", "commit"}
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}\Z")
_SKILL_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_OUTPUT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}\Z")
_FRAMEWORK_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+/-]{0,127}\Z")
_EXACT_VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.-]+)?\Z")
_IMMUTABLE_COMMIT_RE = re.compile(r"(?:(?:sha1:)?[0-9a-f]{40}|(?:sha256:)?[0-9a-f]{64})\Z")

DOMAIN_PHASES = (
    "source_fingerprint",
    "framework_contract_model",
    "target_profile",
    "recipe_selection",
    "target_generation",
    "source_build",
    "source_startup",
    "target_build",
    "target_startup",
    "behavior_equivalence",
    "security_validation",
    "persistence_validation",
    "transaction_validation",
    "integration_validation",
    "negative_corpus",
    "holdout_corpus",
    "representative_repository",
    "customer_acceptance",
    "external_verification",
    "certification_gate",
)

FORBIDDEN_OPERATIONS = frozenset(
    {
        "execute",
        "build",
        "start",
        "migrate",
        "deploy",
        "provider-call",
        "repository-write",
        "certify",
    }
)


@dataclass(frozen=True, slots=True)
class ValidatedRequest:
    schema_version: str
    operation: str
    skill_name: str
    tenant_id: str
    project_id: str
    run_id: str
    task_id: str
    actor_id: str
    idempotency_key: str
    input: Mapping[str, object]
    canonical: bytes
    digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "skill_name": self.skill_name,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "actor_id": self.actor_id,
            "idempotency_key": self.idempotency_key,
            "input": _thaw(self.input),
        }


SkillHandler = Callable[[ValidatedRequest], dict[str, object]]


def output_media_type(name: str) -> str:
    """Return a conservative media type from an explicitly named blueprint."""

    lowered = name.lower()
    if lowered.endswith(".json"):
        return "application/json"
    if lowered.endswith(".jsonl"):
        return "application/x-ndjson"
    if lowered.endswith((".yaml", ".yml")):
        return "application/yaml"
    if lowered.endswith(".md"):
        return "text/markdown"
    if lowered.endswith(".csv"):
        return "text/csv"
    if lowered.endswith(".txt"):
        return "text/plain"
    if lowered.endswith(".xml"):
        return "application/xml"
    if lowered.endswith(".html"):
        return "text/html"
    if lowered.endswith(".sarif"):
        return "application/sarif+json"
    if lowered.endswith(".zip"):
        return "application/zip"
    if lowered.endswith((".tar.gz", ".tgz")):
        return "application/gzip"
    return "application/octet-stream"


def _fail(message: str, **details: object) -> None:
    raise RequestValidationError(message, details=details)


def _exact_fields(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        _fail(
            f"{label} has an invalid field set",
            missing=sorted(expected - actual),
            extra=sorted(actual - expected),
        )
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        _fail(f"{label} is not a valid bounded identifier")
    return value


def _bounded_string(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail(f"{label} must be a non-empty string of at most {maximum} characters")
    return value


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _profile(value: object, label: str) -> dict[str, str]:
    profile = _exact_fields(value, _PROFILE_KEYS, label)
    framework = _bounded_string(profile["framework"], f"{label}.framework", maximum=128)
    version = _bounded_string(profile["version"], f"{label}.version", maximum=128)
    commit = _bounded_string(profile["commit"], f"{label}.commit", maximum=128)
    if not _FRAMEWORK_RE.fullmatch(framework):
        _fail(f"{label}.framework is not an exact framework identifier")
    if not _EXACT_VERSION_RE.fullmatch(version):
        _fail(f"{label}.version must be an exact version, not a floating version or range")
    if not _IMMUTABLE_COMMIT_RE.fullmatch(commit):
        _fail(f"{label}.commit must be a full immutable SHA-1 or SHA-256 digest")
    return {"framework": framework, "version": version, "commit": commit}


def _bounded_string_list(
    value: object,
    label: str,
    *,
    maximum_items: int,
    maximum_length: int,
    output_names: bool = False,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        _fail(f"{label} must be an array of at most {maximum_items} items")
    result = [
        _bounded_string(item, f"{label}[{index}]", maximum=maximum_length)
        for index, item in enumerate(value)
    ]
    if len(result) != len(set(result)):
        _fail(f"{label} contains duplicate values")
    if output_names and any(not _OUTPUT_RE.fullmatch(item) or ".." in item.split("/") for item in result):
        _fail(f"{label} contains an unsafe output name")
    return result


def validate_request(value: object) -> ValidatedRequest:
    validate_json_value(value)
    request = _exact_fields(value, _REQUEST_KEYS, "request")
    if request["schema_version"] != REQUEST_SCHEMA_VERSION:
        _fail("unsupported request schema_version")
    operation = _bounded_string(request["operation"], "request.operation", maximum=32)
    if operation not in {"describe", "plan"} | FORBIDDEN_OPERATIONS:
        _fail("unsupported operation", operation=operation)
    skill_name = _bounded_string(request["skill_name"], "request.skill_name", maximum=64)
    if not _SKILL_RE.fullmatch(skill_name):
        _fail("request.skill_name is invalid")

    raw_input = request["input"]
    if not isinstance(raw_input, dict):
        _fail("request.input must be an object")
    normalized_input: dict[str, object]
    if operation == "describe":
        normalized_input = _exact_fields(raw_input, set(), "request.input")
    elif operation == "plan":
        plan_input = _exact_fields(raw_input, _PLAN_KEYS, "request.input")
        normalized_input = {
            "objective": _bounded_string(plan_input["objective"], "request.input.objective", maximum=4096),
            "source": _profile(plan_input["source"], "request.input.source"),
            "target": _profile(plan_input["target"], "request.input.target"),
            "constraints": _bounded_string_list(
                plan_input["constraints"],
                "request.input.constraints",
                maximum_items=64,
                maximum_length=512,
            ),
            "requested_outputs": _bounded_string_list(
                plan_input["requested_outputs"],
                "request.input.requested_outputs",
                maximum_items=64,
                maximum_length=256,
                output_names=True,
            ),
        }
    else:
        # Forbidden side-effecting operations are deliberately parseable so the
        # dispatcher can return the stronger EXTERNAL_ADAPTER_REQUIRED result.
        normalized_input = copy.deepcopy(raw_input)

    normalized = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "operation": operation,
        "skill_name": skill_name,
        "tenant_id": _identifier(request["tenant_id"], "request.tenant_id"),
        "project_id": _identifier(request["project_id"], "request.project_id"),
        "run_id": _identifier(request["run_id"], "request.run_id"),
        "task_id": _identifier(request["task_id"], "request.task_id"),
        "actor_id": _identifier(request["actor_id"], "request.actor_id"),
        "idempotency_key": _identifier(request["idempotency_key"], "request.idempotency_key"),
        "input": normalized_input,
    }
    canonical = canonical_bytes(normalized)
    if len(canonical) > 65_536:
        _fail("canonical request exceeds 65536 bytes")
    return ValidatedRequest(
        schema_version=REQUEST_SCHEMA_VERSION,
        operation=operation,
        skill_name=skill_name,
        tenant_id=str(normalized["tenant_id"]),
        project_id=str(normalized["project_id"]),
        run_id=str(normalized["run_id"]),
        task_id=str(normalized["task_id"]),
        actor_id=str(normalized["actor_id"]),
        idempotency_key=str(normalized["idempotency_key"]),
        input=_freeze(normalized_input),
        canonical=canonical,
        digest=sha256_digest(canonical),
    )


def parse_request(raw: str | bytes) -> ValidatedRequest:
    return validate_request(parse_json_strict(raw))


def _base_response(
    contract: SkillContract,
    request: ValidatedRequest,
    catalog: Catalog,
) -> dict[str, object]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "decision": "DRAFT_ONLY",
        "operation": request.operation,
        "skill_name": contract.name,
        "batch": contract.batch,
        "batch_dependencies": [
            {"batch": dependency, "status": NOT_RUN}
            for dependency in catalog.batch_dependencies[contract.batch]
        ],
        "source_id": contract.source_id,
        "source_contract_sha256": contract.source_contract_sha256,
        "catalog": {
            "source_archive_sha256": catalog.source_archive_sha256,
            "compiled_contracts_sha256": catalog.compiled_contracts_sha256,
            "skill_count": catalog.skill_count,
        },
        "request_sha256": request.digest,
        "tenant_id": request.tenant_id,
        "project_id": request.project_id,
        "run_id": request.run_id,
        "task_id": request.task_id,
        "actor_id": request.actor_id,
        "control_plane_execution_status": LOCAL_EXECUTED_SELF_ATTESTED,
        "domain_phase_status": {phase: NOT_RUN for phase in DOMAIN_PHASES},
        "runtime_evidence_status": NOT_RUN,
        "customer_evidence_status": NOT_RUN,
        "external_evidence_status": NOT_RUN,
        "certification": NOT_CERTIFIED,
        "side_effects_performed": False,
        "external_adapter_required": True,
    }


def _handle(contract: SkillContract, request: ValidatedRequest, catalog: Catalog) -> dict[str, object]:
    response = _base_response(contract, request, catalog)
    if request.operation == "describe":
        response["contract"] = contract.as_dict()
        response["allowed_operations"] = ["describe", "plan"]
        return response
    if request.operation != "plan":
        raise ExternalAdapterRequired(
            "Spring builds, provider calls, repository writes, migrations, deployment, and certification require an external authorized adapter",
            details={"operation": request.operation, "skill_name": contract.name},
        )

    requested_outputs = list(request.input["requested_outputs"])
    declared = set(contract.required_outputs)
    if requested_outputs and any(output not in declared for output in requested_outputs):
        _fail(
            "requested_outputs must be declared by the imported contract",
            requested=requested_outputs,
            declared=list(contract.required_outputs),
        )
    selected_outputs = requested_outputs or list(contract.required_outputs)
    response.update(
        {
            "objective": request.input["objective"],
            "source": _thaw(request.input["source"]),
            "target": _thaw(request.input["target"]),
            "constraints": list(request.input["constraints"]),
            "dependencies": [
                {
                    "skill_name": dependency,
                    "dependency_kinds": [
                        kind
                        for kind, selected in (
                            ("declared", dependency in contract.dependencies),
                            ("foundation-critical", dependency in contract.critical_dependencies),
                        )
                        if selected
                    ],
                    "status": NOT_RUN,
                }
                for dependency in contract.effective_dependencies
            ],
            "output_blueprints": [
                {
                    "name": output,
                    "media_type": output_media_type(output),
                    "materialized": False,
                    "status": NOT_RUN,
                    "producer": "EXTERNAL_ADAPTER_REQUIRED",
                }
                for output in selected_outputs
            ],
            "limitations": [
                "No repository content was read or written.",
                "No Spring, JVM, build, container, provider, or deployment command was executed.",
                "No migration, behavior-equivalence, customer, external, or certification evidence was produced.",
            ],
        }
    )
    return response


def _make_handler(contract: SkillContract, catalog: Catalog) -> SkillHandler:
    def handler(request: ValidatedRequest) -> dict[str, object]:
        if request.skill_name != contract.name:
            _fail("request was routed to the wrong Skill handler")
        return _handle(contract, request, catalog)

    handler.__name__ = f"handle_{contract.name.replace('-', '_')}"
    handler.__qualname__ = handler.__name__
    handler.__doc__ = f"Bounded describe/plan handler for {contract.name}."
    return handler


class SkillRegistry:
    """Exact immutable one-handler-per-Skill registry."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        handlers = {
            name: _make_handler(catalog.contracts[name], catalog) for name in catalog.topological_order
        }
        if (
            len(handlers) != EXPECTED_SKILL_COUNT
            or len({id(handler) for handler in handlers.values()}) != EXPECTED_SKILL_COUNT
        ):
            raise RuntimeError("registry must contain 196 distinct callable objects")
        self.handlers: Mapping[str, SkillHandler] = MappingProxyType(handlers)

    def dispatch(self, request: ValidatedRequest | Mapping[str, object]) -> dict[str, object]:
        # Revalidation makes even hand-constructed or stale request objects
        # subject to the exact same digest and Schema boundary.
        validated = validate_request(request.as_dict()) if isinstance(request, ValidatedRequest) else validate_request(dict(request))
        handler = self.handlers.get(validated.skill_name)
        if handler is None:
            raise UnknownSkillError(
                "Skill is not present in the exact v2.0.0 registry",
                details={"skill_name": validated.skill_name},
            )
        return handler(validated)


def build_registry(catalog: Catalog) -> SkillRegistry:
    return SkillRegistry(catalog)


def dispatch_skill(
    catalog_or_registry: Catalog | SkillRegistry,
    request: ValidatedRequest | Mapping[str, object],
) -> dict[str, object]:
    """Stable dispatcher used by repository integration bindings."""

    registry = catalog_or_registry if isinstance(catalog_or_registry, SkillRegistry) else SkillRegistry(catalog_or_registry)
    return registry.dispatch(request)


__all__ = [
    "DOMAIN_PHASES",
    "LOCAL_EXECUTED_SELF_ATTESTED",
    "NOT_CERTIFIED",
    "NOT_RUN",
    "REQUEST_SCHEMA_VERSION",
    "RESPONSE_SCHEMA_VERSION",
    "SkillRegistry",
    "ValidatedRequest",
    "build_registry",
    "dispatch_skill",
    "load_catalog",
    "output_media_type",
    "parse_request",
    "validate_request",
]
