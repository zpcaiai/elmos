"""Exact allowlisted dispatcher for 46 conservative plan-skeleton handlers."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Final

from .bootstrap import (
    BootstrapError,
    VerificationReceipt,
    assert_repository_runtime_unchanged,
    manifest_document,
)
from .canonical import canonical_digest, canonical_value
from .catalog import (
    BLOCKER_DEFINITIONS,
    SKILL_CONTRACTS,
    SkillContract,
    repository_root,
    validate_catalog,
)
from .contracts import RESULT_SCHEMA, ContractError, RuntimeRequest
from .handlers import bigdata_core, database_intelligence, orchestration, templates


class RuntimeError(ValueError):
    """Raised when the exact Skill registry or dispatch contract is invalid."""


SkillHandler = Callable[[RuntimeRequest, Mapping[str, Any]], dict[str, Any]]

_OUTCOME_KEYS: Final[frozenset[str]] = frozenset(
    {
        "state",
        "code",
        "planning_state",
        "plan_skeleton_scope",
        "local_primitives",
        "focus",
        "input_digest",
        "request_binding_digest",
        "decision_policy",
        "artifacts",
        "task_ledger",
        "unresolved_evidence_gates",
        "context_assurance",
        "idempotency_semantics",
        "external_effects_performed",
        "skill_implementation_state",
        "repository_handler_runtime_evidence",
        "provider_runtime_evidence",
        "external_evidence_status",
        "production_certification",
    }
)
_TASK_KEYS: Final[frozenset[str]] = frozenset(
    {
        "task_id",
        "planning_state",
        "skill_implementation_state",
        "runtime_evidence",
        "provider_runtime_evidence",
        "external_evidence_status",
        "production_certification",
        "blocker_codes",
    }
)
_ARTIFACT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "declared_output",
        "artifact_state",
        "content_state",
        "skill_implementation_state",
        "runtime_evidence",
        "provider_runtime_evidence",
        "external_evidence_status",
        "production_certification",
    }
)


@dataclass(frozen=True, slots=True)
class HandlerBinding:
    ordinal: int
    skill: str
    group: str
    handler_id: str
    handler: SkillHandler
    contract: SkillContract


_MODULE_BY_GROUP: Final[Mapping[str, ModuleType]] = {
    "bigdata-core": bigdata_core,
    "bigdata-templates": templates,
    "database-intelligence": database_intelligence,
    "orchestration": orchestration,
}


def _build_registry() -> dict[str, HandlerBinding]:
    registry: dict[str, HandlerBinding] = {}
    for contract in SKILL_CONTRACTS:
        module = _MODULE_BY_GROUP[contract.group]
        handler = getattr(module, contract.handler_id, None)
        if not callable(handler):
            raise RuntimeError(
                f"missing exact handler {contract.handler_id} for {contract.name}"
            )
        registry[contract.name] = HandlerBinding(
            ordinal=contract.ordinal,
            skill=contract.name,
            group=contract.group,
            handler_id=contract.handler_id,
            handler=handler,
            contract=contract,
        )
    return registry


SKILL_REGISTRY: Final[Mapping[str, HandlerBinding]] = _build_registry()


def _tree_digest(files: Mapping[str, bytes]) -> str:
    value = hashlib.sha256()
    value.update(b"elmos-tree-digest-v2\0")

    def update_framed(content: bytes) -> None:
        value.update(len(content).to_bytes(8, "big"))
        value.update(content)

    value.update((1).to_bytes(8, "big"))
    update_framed(b"database-bigdata-engine")
    value.update(len(files).to_bytes(8, "big"))
    for relative in sorted(files):
        update_framed(relative.encode("utf-8"))
        update_framed(files[relative])
    return "sha256:" + value.hexdigest()


def _runtime_receipt() -> VerificationReceipt:
    try:
        return assert_repository_runtime_unchanged()
    except BootstrapError as exc:
        raise RuntimeError(f"repository runtime snapshot drifted: {exc}") from exc


def _validate_runtime_snapshot(
    root: Path,
    manifest: Mapping[str, Any],
    receipt: VerificationReceipt,
) -> dict[str, Any]:
    if manifest.get("repository_runtime_path") != "engines/database-bigdata-engine":
        raise RuntimeError("repository runtime path drifted")
    engine_root = root / str(manifest["repository_runtime_path"])
    try:
        resolved_engine_root = engine_root.resolve(strict=True)
        resolved_engine_root.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RuntimeError("repository runtime root escapes or is missing") from exc
    if engine_root.is_symlink() or not resolved_engine_root.is_dir():
        raise RuntimeError("repository runtime root is not a regular directory")
    files = dict(receipt.files)
    digests = dict(receipt.file_digests)
    actual_paths = sorted(files)
    file_records = manifest.get("repository_runtime_files")
    if not isinstance(file_records, list) or not file_records:
        raise RuntimeError("repository runtime file inventory is missing")
    declared_paths = [
        item.get("path") for item in file_records if isinstance(item, Mapping)
    ]
    if (
        len(declared_paths) != len(file_records)
        or not all(isinstance(relative, str) for relative in declared_paths)
        or declared_paths != sorted(declared_paths)
        or actual_paths != declared_paths
        or manifest.get("repository_runtime_file_count") != len(file_records)
    ):
        raise RuntimeError("repository runtime file inventory drifted")

    for item in file_records:
        if set(item) != {"path", "bytes", "sha256"}:
            raise RuntimeError("repository runtime file fields are not exact")
        relative = item["path"]
        pure = PurePosixPath(relative)
        if (
            pure.is_absolute()
            or str(pure) != relative
            or ".." in pure.parts
            or "\\" in relative
        ):
            raise RuntimeError(f"repository runtime file is not confined: {relative}")
        content = files[relative]
        actual_digest = digests[relative]
        if item["bytes"] != len(content) or item["sha256"] != actual_digest:
            raise RuntimeError(f"repository runtime file digest drifted: {relative}")
    actual_tree_digest = _tree_digest(files)
    if actual_tree_digest != receipt.runtime_tree_sha256:
        raise RuntimeError("process runtime receipt tree digest is inconsistent")
    if manifest.get("repository_runtime_digest_algorithm") != "elmos-tree-digest-v2":
        raise RuntimeError("repository runtime digest algorithm drifted")
    if manifest.get("repository_runtime_tree_sha256") != actual_tree_digest:
        raise RuntimeError("repository runtime tree digest drifted")
    catalog_relative = "src/elmos_database_bigdata/catalog.py"
    if manifest.get("repository_runtime_catalog_path") != (
        "engines/database-bigdata-engine/" + catalog_relative
    ):
        raise RuntimeError("repository runtime catalog path drifted")
    if manifest.get("repository_runtime_catalog_sha256") != digests[catalog_relative]:
        raise RuntimeError("repository runtime catalog digest drifted")
    return {
        "engine_root": resolved_engine_root,
        "files": files,
        "digests": digests,
        "tree_sha256": actual_tree_digest,
        "installed_manifest_sha256": receipt.manifest_sha256,
        "launch_assurance": receipt.launch_assurance,
    }


def _validate_registry_context() -> tuple[
    dict[str, Mapping[str, Any]],
    Mapping[str, Any],
    dict[str, Any],
    VerificationReceipt,
]:
    receipt = _runtime_receipt()
    manifest = manifest_document(receipt)
    root = repository_root().resolve(strict=True)
    records = validate_catalog(root, manifest)
    runtime_validation = _validate_runtime_snapshot(root, manifest, receipt)
    bindings = list(SKILL_REGISTRY.values())
    if len(bindings) != 46 or list(SKILL_REGISTRY) != [
        item.name for item in SKILL_CONTRACTS
    ]:
        raise RuntimeError(
            "registry must preserve all 46 exact catalog identities and order"
        )
    if [item.ordinal for item in bindings] != list(range(46)):
        raise RuntimeError("registry ordinals must be the exact 0..45 sequence")
    if len({item.handler_id for item in bindings}) != 46:
        raise RuntimeError("every Skill must have a unique handler identity")
    if len({id(item.handler) for item in bindings}) != 46:
        raise RuntimeError("every Skill must have a unique handler callable")
    if Counter(item.group for item in bindings) != {
        "bigdata-core": 22,
        "bigdata-templates": 10,
        "database-intelligence": 13,
        "orchestration": 1,
    }:
        raise RuntimeError("registry group counts changed")
    for binding in bindings:
        if binding.handler.__name__ != binding.handler_id:
            raise RuntimeError(f"handler function identity drifted for {binding.skill}")
        if binding.handler.__module__ != _MODULE_BY_GROUP[binding.group].__name__:
            raise RuntimeError(f"handler module identity drifted for {binding.skill}")
        record = records[binding.skill]
        declared_path = repository_root() / str(record["repository_handler_path"])
        try:
            declared_resolved = declared_path.resolve(strict=True)
            loaded_resolved = Path(_MODULE_BY_GROUP[binding.group].__file__).resolve(
                strict=True
            )
        except OSError as exc:
            raise RuntimeError(
                f"handler source cannot be resolved for {binding.skill}"
            ) from exc
        if declared_path.is_symlink() or declared_resolved != loaded_resolved:
            raise RuntimeError(f"handler source path drifted for {binding.skill}")
        relative = declared_resolved.relative_to(
            runtime_validation["engine_root"]
        ).as_posix()
        actual_digest = runtime_validation["digests"].get(relative)
        if actual_digest is None:
            raise RuntimeError(
                f"handler source is absent from runtime inventory: {binding.skill}"
            )
        if record.get("repository_handler_file_sha256") != actual_digest:
            raise RuntimeError(f"handler source digest drifted for {binding.skill}")
    return records, manifest, runtime_validation, receipt


def validate_registry() -> dict[str, Mapping[str, Any]]:
    records, _, _, _ = _validate_registry_context()
    return records


def _provenance(
    manifest: Mapping[str, Any],
    runtime_validation: Mapping[str, Any],
    record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = {
        "digest_binding_state": "LOCAL_BYTE_IDENTITY_ONLY",
        "source_archive_sha256": manifest["source_archive_sha256"],
        "canonical_source_tree_sha256": manifest["canonical_source_tree_sha256"],
        "canonical_manifest_sha256": manifest["canonical_manifest_sha256"],
        "installed_manifest_sha256": runtime_validation["installed_manifest_sha256"],
        "repository_runtime_tree_sha256": runtime_validation["tree_sha256"],
        "repository_runtime_catalog_sha256": manifest[
            "repository_runtime_catalog_sha256"
        ],
        "launch_assurance": runtime_validation["launch_assurance"],
        "signature_status": "ABSENT",
        "provenance_attestation_status": "ABSENT",
        "independent_verification": "NOT_RUN",
    }
    if record is not None:
        value.update(
            {
                "source_skill_sha256": record["source_sha256"],
                "repository_handler_file_sha256": record[
                    "repository_handler_file_sha256"
                ],
            }
        )
    return value


def _validate_handler_outcome(
    binding: HandlerBinding,
    request: RuntimeRequest,
    record: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(outcome, Mapping) or set(outcome) != _OUTCOME_KEYS:
        raise RuntimeError("handler outcome fields are not exact")
    normalized = canonical_value(dict(outcome), label="handler outcome")
    required_values = {
        "state": "BLOCKED",
        "code": "DECLARED_SKILL_PLAN_SKELETON",
        "planning_state": "SKELETON_ONLY",
        "plan_skeleton_scope": "IDENTITIES_OUTPUTS_AND_EVIDENCE_GAPS_ONLY",
        "context_assurance": "CALLER_ASSERTED_UNVERIFIED",
        "idempotency_semantics": "DIGEST_BINDING_ONLY_NO_REPLAY_STORE",
        "external_effects_performed": False,
        "skill_implementation_state": "DECLARED",
        "repository_handler_runtime_evidence": "NOT_RUN",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
    for field, expected in required_values.items():
        if normalized.get(field) != expected or (
            field == "external_effects_performed" and normalized.get(field) is not False
        ):
            raise RuntimeError(f"handler outcome raised or changed state: {field}")
    if normalized.get("local_primitives") != list(binding.contract.local_primitives):
        raise RuntimeError("handler outcome local primitives drifted")
    focus = normalized.get("focus")
    if (
        not isinstance(focus, list)
        or not focus
        or not all(isinstance(item, str) and item for item in focus)
    ):
        raise RuntimeError("handler outcome focus is invalid")
    if normalized.get("input_digest") != canonical_digest(request.inputs):
        raise RuntimeError("handler outcome input digest drifted")
    if normalized.get("request_binding_digest") != request.binding_digest():
        raise RuntimeError("handler outcome request binding digest drifted")

    policy = normalized.get("decision_policy")
    if not isinstance(policy, dict) or set(policy) != {
        "hard_constraints",
        "hard_constraints_present",
        "hard_constraints_digest",
        "unknowns",
        "unknowns_present",
        "unknowns_digest",
        "recommendation_state",
        "constraint_relaxation_performed",
    }:
        raise RuntimeError("handler outcome decision policy fields are not exact")
    if policy != {
        "hard_constraints": "PRESERVED_UNEVALUATED",
        "hard_constraints_present": "hard_constraints" in request.inputs,
        "hard_constraints_digest": canonical_digest(
            request.inputs.get("hard_constraints")
        ),
        "unknowns": "PRESERVED_UNRESOLVED",
        "unknowns_present": "unknowns" in request.inputs,
        "unknowns_digest": canonical_digest(request.inputs.get("unknowns")),
        "recommendation_state": "BLOCKED_PENDING_EXACT_EVIDENCE",
        "constraint_relaxation_performed": False,
    }:
        raise RuntimeError("handler outcome decision policy drifted")

    tasks = normalized.get("task_ledger")
    if (
        not isinstance(tasks, list)
        or not all(isinstance(item, dict) for item in tasks)
        or [item.get("task_id") for item in tasks] != list(binding.contract.task_ids)
    ):
        raise RuntimeError("handler outcome task ledger identity drifted")
    expected_task_status = {
        "planning_state": "NOT_RUN",
        "skill_implementation_state": "DECLARED",
        "runtime_evidence": "NOT_RUN",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "blocker_codes": list(binding.contract.blockers),
    }
    for task in tasks:
        if not isinstance(task, dict) or set(task) != _TASK_KEYS:
            raise RuntimeError("handler outcome task fields are not exact")
        if any(
            task.get(field) != expected
            for field, expected in expected_task_status.items()
        ):
            raise RuntimeError("handler outcome task state drifted")

    artifacts = normalized.get("artifacts")
    expected_outputs = record.get("source_outputs")
    if (
        not isinstance(artifacts, list)
        or not all(isinstance(item, dict) for item in artifacts)
        or [item.get("declared_output") for item in artifacts] != expected_outputs
    ):
        raise RuntimeError("handler outcome artifact identity drifted")
    expected_artifact_status = {
        "artifact_state": "DECLARED_OUTPUT",
        "content_state": "NOT_GENERATED",
        "skill_implementation_state": "DECLARED",
        "runtime_evidence": "NOT_RUN",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != _ARTIFACT_KEYS:
            raise RuntimeError("handler outcome artifact fields are not exact")
        if any(
            artifact.get(field) != expected
            for field, expected in expected_artifact_status.items()
        ):
            raise RuntimeError("handler outcome artifact state drifted")

    expected_gates = [
        {"code": code, "reason": BLOCKER_DEFINITIONS[code]}
        for code in binding.contract.blockers
    ]
    if normalized.get("unresolved_evidence_gates") != expected_gates:
        raise RuntimeError("handler outcome evidence gates drifted")
    return normalized


def _validate_authoritative_result(result: Mapping[str, Any]) -> None:
    required = {
        "state": "BLOCKED",
        "code": "DECLARED_SKILL_PLAN_SKELETON",
        "planning_state": "SKELETON_ONLY",
        "context_assurance": "CALLER_ASSERTED_UNVERIFIED",
        "external_effects_performed": False,
        "skill_implementation_state": "DECLARED",
        "repository_handler_runtime_evidence": "NOT_RUN",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
    if any(result.get(field) != expected for field, expected in required.items()):
        raise RuntimeError("authoritative result postcondition failed")


def execute_skill(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and emit a blocked plan skeleton; never run a source task."""

    request = RuntimeRequest.parse(document)
    binding = SKILL_REGISTRY.get(request.skill)
    if binding is None:
        raise RuntimeError(f"unknown database/Big Data Skill: {request.skill}")
    records, manifest, runtime_validation, receipt = _validate_registry_context()
    record = records[request.skill]
    outcome = _validate_handler_outcome(
        binding, request, record, binding.handler(request, record)
    )
    if _runtime_receipt() != receipt:
        raise RuntimeError("repository runtime changed while the handler was running")
    result = {
        **outcome,
        "schema_version": RESULT_SCHEMA,
        "skill": binding.skill,
        "handler_id": binding.handler_id,
        "handler_ordinal": binding.ordinal,
        "source_group": binding.group,
        "request_id": request.request_id,
        "tenant_id": request.tenant_id,
        "project_id": request.project_id,
        "actor_id": request.actor_id,
        "idempotency_key": request.idempotency_key,
        "provenance": _provenance(manifest, runtime_validation, record),
    }
    _validate_authoritative_result(result)
    copied = canonical_value(result, label="result")
    copied["result_digest"] = canonical_digest(copied)
    return copied


def dispatch_skill(skill: str, document: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise ContractError("request must be an object")
    if document.get("skill") != skill:
        raise ContractError("dispatch Skill and request Skill must be identical")
    return execute_skill(document)


def capability_manifest() -> dict[str, Any]:
    _, manifest, runtime_validation, receipt = _validate_registry_context()
    value = {
        "schema_version": "elmos.database-bigdata.capabilities.v1",
        "source_package": "elmos-database-bigdata-skills",
        "source_version": "1.0.0",
        "skill_count": 46,
        "stable_task_id_count": 554,
        "group_counts": {
            "bigdata-core": 22,
            "bigdata-templates": 10,
            "database-intelligence": 13,
            "orchestration": 1,
        },
        "runtime_kind": "BOUNDED_PLAN_SKELETON",
        "external_effects_declared": False,
        "static_safety_validation": "BEST_EFFORT_AST_ALLOWLIST",
        "preimport_integrity_check": receipt.launch_assurance,
        "context_assurance": "CALLER_ASSERTED_UNVERIFIED",
        "idempotency_semantics": "DIGEST_BINDING_ONLY_NO_REPLAY_STORE",
        "provenance": _provenance(manifest, runtime_validation),
        "skill_implementation_state": "DECLARED",
        "repository_handler_runtime_evidence": "NOT_RUN",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "capabilities": [
            {
                "ordinal": binding.ordinal,
                "skill": binding.skill,
                "group": binding.group,
                "handler_id": binding.handler_id,
                "task_ids": list(binding.contract.task_ids),
                "local_primitives": list(binding.contract.local_primitives),
                "blocker_codes": list(binding.contract.blockers),
                "skill_implementation_state": "DECLARED",
                "runtime_evidence": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            }
            for binding in SKILL_REGISTRY.values()
        ],
    }
    if _runtime_receipt() != receipt:
        raise RuntimeError("repository runtime changed while capabilities were built")
    value["manifest_digest"] = canonical_digest(value)
    return value


__all__ = [
    "SKILL_REGISTRY",
    "HandlerBinding",
    "RuntimeError",
    "capability_manifest",
    "dispatch_skill",
    "execute_skill",
    "validate_registry",
]
