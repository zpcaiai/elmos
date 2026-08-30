"""Repository-owned operation families for the 300 exact Skill bindings.

Every exact Skill receives a distinct runtime callable.  Families share typed
primitives, but source package text, commands, scripts, and prompts are never
dispatched.  External execution families emit bounded plans until a trusted
adapter and exact evidence are supplied by the host.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from typing import Any, Mapping, Sequence

from .catalog import CompiledCatalog
from .contracts import ContractError, ExecutionAuthority, RuntimeRequest, digest_json, require_digest
from .evidence import evaluate_evidence_set
from .models import (
    CertificationState,
    EvidenceState,
    ExecutionState,
    ObligationStatus,
    SkillDefinition,
    VerdictStatus,
)


_FAMILY_INPUTS: Mapping[str, frozenset[str]] = {
    "repository-intelligence": frozenset(
        {"goal", "model", "repository_snapshot", "requested_skills", "route_id"}
    ),
    "transformation-plan": frozenset(
        {
            "route_id",
            "source_artifact",
            "target_profile",
            "transformation_rules",
            "evidence_receipts",
        }
    ),
    "verification-delivery": frozenset(
        {
            "route_id",
            "source_model",
            "target_model",
            "source_observation",
            "target_observation",
            "evidence_receipts",
        }
    ),
    "technology-adapter": frozenset(
        {"technology", "version", "source_artifact", "target_profile", "evidence_receipts"}
    ),
    "legacy-intelligence": frozenset(
        {"goal", "model", "repository_snapshot", "requested_skills", "route_id"}
    ),
    "legacy-adapter": frozenset(
        {"technology", "version", "source_artifact", "target_profile", "evidence_receipts"}
    ),
    "legacy-transformation": frozenset(
        {"route_id", "source_artifact", "target_profile", "model", "evidence_receipts"}
    ),
    "route-execution": frozenset(
        {"route_id", "source_artifact", "target_profile", "evidence_receipts"}
    ),
    "legacy-validation": frozenset(
        {"route_id", "source_model", "target_model", "evidence_receipts"}
    ),
    "frontend-semantics": frozenset(
        {"route_id", "source_model", "target_model", "evidence_receipts"}
    ),
    "type-semantics": frozenset(
        {"route_id", "source_model", "target_model", "evidence_receipts"}
    ),
    "control-dataflow": frozenset(
        {"route_id", "source_model", "target_model", "evidence_receipts"}
    ),
    "runtime-semantics": frozenset(
        {"route_id", "source_model", "target_model", "evidence_receipts"}
    ),
    "behavior-oracle": frozenset(
        {
            "route_id",
            "source_observation",
            "target_observation",
            "evidence_receipts",
        }
    ),
    "corpus-governance": frozenset({"fixtures", "coverage", "evidence_receipts"}),
    "native-runtime-lab": frozenset({"lab_profile", "evidence_receipts"}),
    "formal-assurance": frozenset(
        {"formula", "assumptions", "solver", "timeout_ms", "evidence_receipts"}
    ),
    "semantic-fuzzing": frozenset(
        {"route_id", "campaign", "results", "evidence_receipts"}
    ),
    "quality-gate": frozenset(
        {"route_id", "evidence_receipts", "required_evidence_types"}
    ),
}

_NATIVE_EVIDENCE_TYPES = frozenset(
    {
        "native-build",
        "native-runtime-observation",
        "runtime-exit-clean",
        "independent-verification",
    }
)
_FORMAL_EVIDENCE_TYPES = frozenset(
    {
        "solver-transcript",
        "proof-result",
        "counterexample-replay",
        "independent-verification",
    }
)
_FUZZ_EVIDENCE_TYPES = frozenset(
    {
        "differential-fuzz-results",
        "counterexample-replay",
        "independent-verification",
    }
)
_GATE_EVIDENCE_TYPES: Mapping[str, frozenset[str]] = {
    "elmos-production-readiness-gate": frozenset(
        {
            "source-native-build",
            "target-native-build",
            "representative-runtime",
            "negative-security",
            "rollback-recovery",
            "supply-chain-provenance",
            "independent-verification",
        }
    ),
    "elmos-legacy-production-certification-gate": frozenset(
        {
            "source-native-build",
            "target-native-build",
            "data-reconciliation",
            "dual-run-reconciliation",
            "security-authority-equivalence",
            "rollback-recovery",
            "independent-verification",
        }
    ),
    "elmos-frontend-consistency-gate": frozenset(
        {
            "source-browser-journey",
            "target-browser-journey",
            "interaction-equivalence",
            "accessibility",
            "visual-regression",
            "independent-verification",
        }
    ),
    "elmos-type-semantic-loss-gate": frozenset(
        {
            "type-algebra",
            "nullability-boundary",
            "numeric-boundary",
            "serialization-boundary",
            "independent-verification",
        }
    ),
    "elmos-control-data-effect-equivalence-gate": frozenset(
        {
            "cfg-equivalence",
            "dataflow-equivalence",
            "exception-equivalence",
            "side-effect-equivalence",
            "independent-verification",
        }
    ),
    "elmos-runtime-edge-semantics-gate": frozenset(
        {
            "native-runtime-observation",
            "memory-model",
            "concurrency-stress",
            "sanitizer-results",
            "independent-verification",
        }
    ),
    "elmos-behavior-equivalence-verdict-aggregator": frozenset(
        {
            "differential-behavior",
            "state-snapshot",
            "side-effect-observation",
            "deterministic-replay",
            "independent-verification",
        }
    ),
    "elmos-certification-corpus-readiness-gate": frozenset(
        {
            "corpus-provenance",
            "license-review",
            "negative-corpus",
            "holdout-corpus",
            "coverage-analysis",
            "independent-verification",
        }
    ),
    "elmos-native-runtime-lab-evidence-attestor": _NATIVE_EVIDENCE_TYPES,
    "elmos-formal-assurance-gate": _FORMAL_EVIDENCE_TYPES,
    "elmos-semantic-stress-certification-gate": frozenset(
        {
            "differential-fuzz-results",
            "metamorphic-results",
            "mutation-results",
            "deterministic-replay",
            "holdout-corpus",
            "independent-verification",
        }
    ),
}


def _operation(
    *,
    state: ExecutionState,
    code: str,
    definition: SkillDefinition,
    outputs: Mapping[str, Any],
    unavailable: Sequence[str] = (),
    warnings: Sequence[str] = (),
    evidence_state: EvidenceState = EvidenceState.LOCAL_EXECUTED_SELF_ATTESTED,
    certification: CertificationState = CertificationState.NOT_CERTIFIED,
) -> dict[str, Any]:
    return {
        "state": state.value,
        "code": code,
        "implementation_state": definition.capability_mode.value,
        "outputs": dict(outputs),
        "unavailable": list(unavailable),
        "warnings": list(warnings),
        "external_effects_performed": False,
        "external_evidence": evidence_state.value,
        "certification": certification.value,
    }


def _validate_inputs(definition: SkillDefinition, inputs: Mapping[str, Any]) -> None:
    allowed = _FAMILY_INPUTS.get(definition.operation_family)
    if allowed is None:
        raise ContractError(f"unsupported compiled operation family: {definition.operation_family}")
    unknown = set(inputs) - allowed
    if unknown:
        raise ContractError(
            f"inputs contain fields outside the {definition.operation_family} contract: {sorted(unknown)}"
        )


def _evidence(
    inputs: Mapping[str, Any],
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    *,
    subject: Any,
    required_types: frozenset[str] = frozenset(),
) -> dict[str, Any] | None:
    receipts = inputs.get("evidence_receipts")
    if receipts is None:
        return None
    if not isinstance(receipts, list):
        raise ContractError("evidence_receipts must be an array")
    evaluation = evaluate_evidence_set(
        receipts,
        request=request,
        authority=authority,
        expected_subject_digest=digest_json(subject),
    )
    observed = [str(item["evidence_type"]) for item in evaluation["receipts"]]
    duplicates = sorted({item for item in observed if observed.count(item) > 1})
    missing = sorted(required_types - set(observed))
    evaluation["required_evidence_types"] = sorted(required_types)
    evaluation["missing_evidence_types"] = missing
    evaluation["duplicate_evidence_types"] = duplicates
    evaluation["all_required_independently_verified"] = bool(required_types) and (
        evaluation["all_independently_verified"] and not missing and not duplicates
    )
    return evaluation


def _artifact_digest(value: Any, label: str) -> str:
    if isinstance(value, str):
        return require_digest(value, label)
    if isinstance(value, Mapping):
        digest = value.get("digest")
        return require_digest(digest, f"{label}.digest")
    raise ContractError(f"{label} must be a digest or artifact reference")


def _scan_repository(root: Path, revision_digest: str) -> dict[str, Any]:
    """Build a bounded immutable file inventory without executing repository content."""

    max_files = 20_000
    max_bytes = 128 * 1024 * 1024
    skip = {".git", ".gradle", "node_modules", "target", "build", "dist", "__pycache__"}
    files: list[dict[str, Any]] = []
    total_bytes = 0
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

    def stable_identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_nlink,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    expected_root = root.stat(follow_symlinks=False)
    if not stat.S_ISDIR(expected_root.st_mode):
        raise ContractError("repository snapshot root is not a real directory")
    root_fd = os.open(root, directory_flags)
    if stable_identity(os.fstat(root_fd)) != stable_identity(expected_root):
        os.close(root_fd)
        raise ContractError("repository snapshot root changed while opening")

    stack: list[tuple[tuple[str, ...], int]] = [((), root_fd)]
    try:
        while stack:
            relative_parent, directory_fd = stack.pop()
            try:
                directory_before = os.fstat(directory_fd)
                with os.scandir(directory_fd) as entries:
                    ordered = sorted(entries, key=lambda item: item.name, reverse=True)
                    for entry in ordered:
                        if entry.name in skip:
                            continue
                        relative_parts = (*relative_parent, entry.name)
                        relative = "/".join(relative_parts)
                        metadata = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(metadata.st_mode):
                            raise ContractError(
                                f"repository snapshot encountered a symlink: {relative}"
                            )
                        if stat.S_ISDIR(metadata.st_mode):
                            child_fd = os.open(entry.name, directory_flags, dir_fd=directory_fd)
                            try:
                                if stable_identity(os.fstat(child_fd)) != stable_identity(metadata):
                                    raise ContractError(
                                        f"repository directory changed while opening: {relative}"
                                    )
                            except Exception:
                                os.close(child_fd)
                                raise
                            stack.append((relative_parts, child_fd))
                            continue
                        if not stat.S_ISREG(metadata.st_mode):
                            raise ContractError(
                                f"repository snapshot encountered a special file: {relative}"
                            )
                        if (
                            metadata.st_size < 0
                            or len(files) >= max_files
                            or total_bytes + metadata.st_size > max_bytes
                        ):
                            raise ContractError(
                                "repository snapshot exceeded its bounded file or byte budget"
                            )
                        file_fd = os.open(entry.name, file_flags, dir_fd=directory_fd)
                        try:
                            opened = os.fstat(file_fd)
                            if (
                                not stat.S_ISREG(opened.st_mode)
                                or stable_identity(opened) != stable_identity(metadata)
                            ):
                                raise ContractError(
                                    f"repository file changed while opening: {relative}"
                                )
                            content_hash = hashlib.sha256()
                            bytes_read = 0
                            while True:
                                chunk = os.read(file_fd, 1024 * 1024)
                                if not chunk:
                                    break
                                bytes_read += len(chunk)
                                if total_bytes + bytes_read > max_bytes:
                                    raise ContractError(
                                        "repository snapshot exceeded its bounded byte budget"
                                    )
                                content_hash.update(chunk)
                            after = os.fstat(file_fd)
                            if (
                                stable_identity(after) != stable_identity(opened)
                                or bytes_read != opened.st_size
                            ):
                                raise ContractError(
                                    f"repository file changed during read: {relative}"
                                )
                        finally:
                            os.close(file_fd)
                        files.append(
                            {
                                "path": relative,
                                "bytes": metadata.st_size,
                                "sha256": "sha256:" + content_hash.hexdigest(),
                            }
                        )
                        total_bytes += metadata.st_size
                if stable_identity(os.fstat(directory_fd)) != stable_identity(directory_before):
                    raise ContractError(
                        f"repository directory changed during scan: {'/'.join(relative_parent) or '.'}"
                    )
            finally:
                os.close(directory_fd)
    finally:
        for _, descriptor in stack:
            os.close(descriptor)
    files.sort(key=lambda item: item["path"])
    snapshot = {
        "schema_version": "1.0",
        "revision_digest": revision_digest,
        "files": files,
        "file_count": len(files),
        "total_bytes": total_bytes,
    }
    snapshot["snapshot_digest"] = digest_json(snapshot)
    return snapshot


def _repository_intelligence(
    definition: SkillDefinition,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    catalog: CompiledCatalog,
) -> dict[str, Any]:
    inputs = request.inputs
    if definition.name == "elmos-scope-authorization-controller":
        return _operation(
            state=ExecutionState.SUCCEEDED,
            code="AUTHORITY_SCOPE_BOUND",
            definition=definition,
            outputs={
                "scope_digest": digest_json(
                    {
                        "tenant_id": request.tenant_id,
                        "project_id": request.project_id,
                        "actor_id": request.actor_id,
                        "revision_digest": request.revision_digest,
                        "environment_authority_id": request.environment_authority_id,
                    }
                )
            },
        )
    if definition.name == "elmos-immutable-repository-snapshot":
        if authority.repository_root is None:
            return _operation(
                state=ExecutionState.BLOCKED,
                code="REPOSITORY_ROOT_AUTHORITY_MISSING",
                definition=definition,
                outputs={},
                unavailable=("host-minted repository_root",),
                evidence_state=EvidenceState.NOT_RUN,
            )
        snapshot = _scan_repository(authority.repository_root, request.revision_digest)
        return _operation(
            state=ExecutionState.SUCCEEDED,
            code="IMMUTABLE_SNAPSHOT_COMPILED",
            definition=definition,
            outputs={"repository_snapshot": snapshot},
        )
    if "orchestrator" in definition.name or definition.layer in {"planning", "orchestration"}:
        requested = inputs.get("requested_skills")
        if requested is None:
            requested = [definition.name]
        if not isinstance(requested, list) or not requested or any(
            not isinstance(item, str) for item in requested
        ):
            raise ContractError("requested_skills must be a non-empty string array")
        plan = catalog.dependency_closure(requested)
        return _operation(
            state=ExecutionState.READY_FOR_HUMAN_DECISION,
            code="DEPENDENCY_CLOSED_PLAN_COMPILED",
            definition=definition,
            outputs={
                "execution_plan": [
                    {
                        "ordinal": item.ordinal,
                        "source_id": item.source_id,
                        "skill": item.name,
                        "batch": item.batch.value,
                        "capability_mode": item.capability_mode.value,
                    }
                    for item in plan
                ],
                "catalog_digest": catalog.digest,
            },
        )
    model = inputs.get("model") or inputs.get("repository_snapshot")
    if model is None:
        return _operation(
            state=ExecutionState.BLOCKED,
            code="SOURCE_FACTS_MISSING",
            definition=definition,
            outputs={},
            unavailable=("model or repository_snapshot",),
            evidence_state=EvidenceState.NOT_RUN,
        )
    return _operation(
        state=ExecutionState.SUCCEEDED,
        code="TYPED_SOURCE_FACTS_COMPILED",
        definition=definition,
        outputs={
            "model_digest": digest_json(model),
            "declared_outputs": list(definition.outputs),
            "semantic_gaps": list(inputs.get("model", {}).get("semantic_gaps", ()))
            if isinstance(inputs.get("model"), Mapping)
            else [],
        },
    )


def _external_plan(
    definition: SkillDefinition,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    catalog: CompiledCatalog,
) -> dict[str, Any]:
    inputs = request.inputs
    source_artifact = inputs.get("source_artifact")
    target_profile = inputs.get("target_profile")
    route_id = inputs.get("route_id")
    missing = []
    if source_artifact is None:
        missing.append("source_artifact")
    if target_profile is None and definition.operation_family not in {
        "verification-delivery",
        "native-runtime-lab",
    }:
        missing.append("target_profile")
    if missing:
        return _operation(
            state=ExecutionState.BLOCKED,
            code="EXECUTION_INPUTS_MISSING",
            definition=definition,
            outputs={},
            unavailable=missing,
            evidence_state=EvidenceState.NOT_RUN,
        )
    source_digest = _artifact_digest(source_artifact, "source_artifact") if source_artifact else None
    if route_id is not None and not isinstance(route_id, str):
        raise ContractError("route_id must be a string")
    route = None
    if isinstance(route_id, str):
        route = catalog.routes_by_id.get(route_id) or catalog.reference_routes_by_id.get(route_id)
        if route is None:
            raise ContractError("route_id is not present in the compiled catalog")
    return _operation(
        state=ExecutionState.READY_FOR_EXTERNAL_GATE,
        code="EXTERNAL_EXECUTION_PLAN_READY",
        definition=definition,
        outputs={
            "source_artifact_digest": source_digest,
            "target_profile_digest": digest_json(target_profile) if target_profile is not None else None,
            "route_id": route_id,
            "route_readiness": getattr(route, "readiness", getattr(route, "status", None)),
            "declared_outputs": list(definition.outputs),
            "required_dependencies": list(definition.dependencies),
        },
        unavailable=("trusted native/provider adapter", "executed external evidence"),
        evidence_state=EvidenceState.NOT_RUN,
    )


def _native_runtime_lab(
    definition: SkillDefinition,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    catalog: CompiledCatalog,
) -> dict[str, Any]:
    """Bind an exact native-lab profile without pretending to execute it."""

    del catalog
    profile = request.inputs.get("lab_profile")
    if not isinstance(profile, Mapping) or not profile:
        return _operation(
            state=ExecutionState.BLOCKED,
            code="NATIVE_LAB_PROFILE_MISSING",
            definition=definition,
            outputs={},
            unavailable=("exact native lab profile",),
            evidence_state=EvidenceState.NOT_RUN,
        )
    evidence = _evidence(
        request.inputs,
        request,
        authority,
        subject={"lab_profile": profile, "required_evidence_types": sorted(_NATIVE_EVIDENCE_TYPES)},
        required_types=_NATIVE_EVIDENCE_TYPES,
    )
    output = {
        "lab_profile_digest": digest_json(profile),
        "evidence_evaluation": evidence,
        "declared_outputs": list(definition.outputs),
    }
    if not evidence or not evidence["all_required_independently_verified"]:
        return _operation(
            state=ExecutionState.BLOCKED,
            code="NATIVE_RUNTIME_NOT_VERIFIED",
            definition=definition,
            outputs=output,
            unavailable=("native runner execution", "host-verified independent evidence"),
            evidence_state=(
                EvidenceState.NOT_RUN
                if evidence is None
                else EvidenceState.EXTERNAL_EXECUTED_UNVERIFIED
            ),
        )
    return _operation(
        state=ExecutionState.READY_FOR_EXTERNAL_GATE,
        code="NATIVE_RUNTIME_EVIDENCE_BOUND",
        definition=definition,
        outputs=output,
        evidence_state=EvidenceState.INDEPENDENTLY_VERIFIED,
        certification=CertificationState.READY_FOR_EXTERNAL_GATE,
    )


def _compare_models(
    definition: SkillDefinition,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    catalog: CompiledCatalog,
) -> dict[str, Any]:
    del catalog
    inputs = request.inputs
    source = inputs.get("source_model", inputs.get("source_observation"))
    target = inputs.get("target_model", inputs.get("target_observation"))
    if source is None or target is None:
        return _operation(
            state=ExecutionState.BLOCKED,
            code="COMPARISON_INPUTS_MISSING",
            definition=definition,
            outputs={},
            unavailable=("source_model/source_observation", "target_model/target_observation"),
            evidence_state=EvidenceState.NOT_RUN,
        )
    source_digest = digest_json(source)
    target_digest = digest_json(target)
    canonical_equal = source_digest == target_digest
    evidence = _evidence(
        inputs,
        request,
        authority,
        subject={"source_digest": source_digest, "target_digest": target_digest},
    )
    evidence_state = (
        EvidenceState.INDEPENDENTLY_VERIFIED
        if evidence and evidence["all_independently_verified"]
        else EvidenceState.LOCAL_EXECUTED_SELF_ATTESTED
    )
    return _operation(
        state=ExecutionState.SUCCEEDED,
        code="CANONICAL_MODELS_COMPARED",
        definition=definition,
        outputs={
            "verdict": (
                VerdictStatus.UNDETERMINED.value
                if canonical_equal
                else VerdictStatus.DIVERGENT.value
            ),
            "canonical_equal": canonical_equal,
            "source_digest": source_digest,
            "target_digest": target_digest,
            "evidence_evaluation": evidence,
        },
        warnings=(
            "Canonical equality is bounded local evidence and does not prove semantic equivalence.",
        ),
        evidence_state=evidence_state,
    )


def _corpus(
    definition: SkillDefinition,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    catalog: CompiledCatalog,
) -> dict[str, Any]:
    del catalog
    fixtures = request.inputs.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        return _operation(
            state=ExecutionState.BLOCKED,
            code="FIXTURE_CORPUS_NOT_RUN",
            definition=definition,
            outputs={"fixture_count": 0},
            unavailable=("non-empty independent fixture corpus",),
            evidence_state=EvidenceState.NOT_RUN,
        )
    seen: set[str] = set()
    normalized = []
    for index, fixture in enumerate(fixtures):
        if not isinstance(fixture, Mapping):
            raise ContractError(f"fixtures[{index}] must be an object")
        fixture_id = fixture.get("fixture_id")
        content_digest = fixture.get("content_digest")
        provenance = fixture.get("provenance")
        license_id = fixture.get("license")
        if not isinstance(fixture_id, str) or not fixture_id or fixture_id in seen:
            raise ContractError("fixture IDs must be unique non-empty strings")
        require_digest(content_digest, f"fixtures[{index}].content_digest")
        if not isinstance(provenance, str) or not provenance:
            raise ContractError("fixture provenance is required")
        if not isinstance(license_id, str) or not license_id:
            raise ContractError("fixture license is required")
        seen.add(fixture_id)
        normalized.append(
            {
                "fixture_id": fixture_id,
                "content_digest": content_digest,
                "provenance": provenance,
                "license": license_id,
            }
        )
    evidence = _evidence(
        request.inputs,
        request,
        authority,
        subject={"fixtures": normalized, "coverage": request.inputs.get("coverage")},
    )
    return _operation(
        state=ExecutionState.SUCCEEDED,
        code="FIXTURE_CORPUS_VALIDATED",
        definition=definition,
        outputs={
            "fixture_count": len(normalized),
            "corpus_digest": digest_json(normalized),
            "evidence_evaluation": evidence,
        },
        warnings=("Corpus structure validation is not representative-route execution.",),
    )


def _formal(
    definition: SkillDefinition,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    catalog: CompiledCatalog,
) -> dict[str, Any]:
    del catalog
    formula = request.inputs.get("formula")
    if not isinstance(formula, str) or not formula.strip():
        return _operation(
            state=ExecutionState.BLOCKED,
            code="PROOF_OBLIGATION_MISSING",
            definition=definition,
            outputs={},
            unavailable=("non-empty formal obligation",),
            evidence_state=EvidenceState.NOT_RUN,
        )
    if len(formula.encode("utf-8")) > 1_048_576:
        raise ContractError("formal obligation is oversized")
    assumptions = request.inputs.get("assumptions", [])
    if not isinstance(assumptions, list) or any(not isinstance(item, str) for item in assumptions):
        raise ContractError("assumptions must be a string array")
    solver = request.inputs.get("solver", "UNBOUND")
    if not isinstance(solver, str) or not solver:
        raise ContractError("solver must be a non-empty string")
    obligation = {
        "proof_id": "proof:" + hashlib.sha256(formula.encode("utf-8")).hexdigest(),
        "formula_digest": "sha256:" + hashlib.sha256(formula.encode("utf-8")).hexdigest(),
        "assumptions_digest": digest_json(assumptions),
        "solver": solver,
        "status": ObligationStatus.NOT_RUN.value,
    }
    evidence = _evidence(
        request.inputs,
        request,
        authority,
        subject={
            "formula_digest": obligation["formula_digest"],
            "assumptions_digest": obligation["assumptions_digest"],
            "solver": solver,
            "timeout_ms": request.inputs.get("timeout_ms", 5_000),
            "required_evidence_types": sorted(_FORMAL_EVIDENCE_TYPES),
        },
        required_types=_FORMAL_EVIDENCE_TYPES,
    )
    if evidence and evidence["all_required_independently_verified"]:
        obligation["status"] = ObligationStatus.PROVED_UNDER_ASSUMPTIONS.value
        return _operation(
            state=ExecutionState.READY_FOR_EXTERNAL_GATE,
            code="INDEPENDENT_PROOF_EVIDENCE_BOUND",
            definition=definition,
            outputs={"proof_obligation": obligation, "evidence_evaluation": evidence},
            evidence_state=EvidenceState.INDEPENDENTLY_VERIFIED,
            certification=CertificationState.READY_FOR_EXTERNAL_GATE,
        )
    return _operation(
        state=ExecutionState.BLOCKED,
        code="PROOF_EXECUTION_NOT_RUN",
        definition=definition,
        outputs={"proof_obligation": obligation, "evidence_evaluation": evidence},
        unavailable=("trusted solver execution", "independent proof verification"),
        evidence_state=EvidenceState.NOT_RUN if evidence is None else EvidenceState.EXTERNAL_EXECUTED_UNVERIFIED,
    )


def _fuzz(
    definition: SkillDefinition,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    catalog: CompiledCatalog,
) -> dict[str, Any]:
    route_id = request.inputs.get("route_id")
    if not isinstance(route_id, str) or (
        route_id not in catalog.routes_by_id
        and route_id not in catalog.reference_routes_by_id
    ):
        raise ContractError("fuzz route_id is absent from the compiled catalog")
    campaign = request.inputs.get("campaign")
    if not isinstance(campaign, Mapping) or not campaign:
        raise ContractError("fuzz campaign must be a non-empty exact profile object")
    results = request.inputs.get("results")
    if not isinstance(results, list) or not results:
        return _operation(
            state=ExecutionState.BLOCKED,
            code="FUZZ_CAMPAIGN_NOT_RUN",
            definition=definition,
            outputs={
                "cases_run": 0,
                "verdict": VerdictStatus.UNDETERMINED.value,
                "required_evidence_types": sorted(_FUZZ_EVIDENCE_TYPES),
            },
            unavailable=("executed differential fuzz results",),
            evidence_state=EvidenceState.NOT_RUN,
        )
    seen: set[str] = set()
    divergences = 0
    normalized = []
    for index, result in enumerate(results):
        if not isinstance(result, Mapping):
            raise ContractError(f"results[{index}] must be an object")
        if set(result) != {"case_id", "source_digest", "target_digest", "verdict"}:
            raise ContractError("fuzz result fields differ from the exact contract")
        case_id = result.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ContractError("fuzz case IDs must be unique non-empty strings")
        source_digest = require_digest(result.get("source_digest"), "fuzz source_digest")
        target_digest = require_digest(result.get("target_digest"), "fuzz target_digest")
        verdict = result.get("verdict")
        if verdict not in {"EQUIVALENT", "DIVERGENT", "INCONCLUSIVE"}:
            raise ContractError("fuzz verdict is unsupported")
        if verdict != "EQUIVALENT" or source_digest != target_digest:
            divergences += 1
        seen.add(case_id)
        normalized.append(dict(result))
    evidence = _evidence(
        request.inputs,
        request,
        authority,
        subject={
            "route_id": route_id,
            "campaign": campaign,
            "results_digest": digest_json(normalized),
            "required_evidence_types": sorted(_FUZZ_EVIDENCE_TYPES),
        },
        required_types=_FUZZ_EVIDENCE_TYPES,
    )
    evidence_verified = bool(evidence and evidence["all_required_independently_verified"])
    verdict = (
        VerdictStatus.EQUIVALENT
        if divergences == 0 and evidence_verified
        else VerdictStatus.DIVERGENT
        if divergences
        else VerdictStatus.UNDETERMINED
    )
    gate_ready = evidence_verified and divergences == 0
    return _operation(
        state=(
            ExecutionState.READY_FOR_EXTERNAL_GATE
            if gate_ready
            else ExecutionState.BLOCKED
        ),
        code=(
            "FUZZ_RESULTS_INDEPENDENTLY_VERIFIED"
            if gate_ready
            else "FUZZ_DIVERGENCE_OR_INCONCLUSIVE_VERIFIED"
            if evidence_verified
            else "FUZZ_RESULTS_UNVERIFIED"
        ),
        definition=definition,
        outputs={
            "cases_run": len(normalized),
            "divergences_found": divergences,
            "verdict": verdict.value,
            "results_digest": digest_json(normalized),
            "evidence_evaluation": evidence,
            "required_evidence_types": sorted(_FUZZ_EVIDENCE_TYPES),
        },
        unavailable=(
            ()
            if gate_ready
            else ("zero verified divergent or inconclusive fuzz cases",)
            if evidence_verified
            else ("complete host-verified independent fuzz evidence",)
        ),
        warnings=("Submitted fuzz results are not a representative corpus certification.",),
        evidence_state=(
            EvidenceState.INDEPENDENTLY_VERIFIED
            if evidence_verified
            else EvidenceState.EXTERNAL_EXECUTED_UNVERIFIED
        ),
        certification=(
            CertificationState.READY_FOR_EXTERNAL_GATE
            if gate_ready
            else CertificationState.NOT_CERTIFIED
        ),
    )


def _quality_gate(
    definition: SkillDefinition,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    catalog: CompiledCatalog,
) -> dict[str, Any]:
    route_id = request.inputs.get("route_id")
    if not isinstance(route_id, str) or (
        route_id not in catalog.routes_by_id
        and route_id not in catalog.reference_routes_by_id
    ):
        raise ContractError("quality gate route_id is absent from the compiled catalog")
    server_required = _GATE_EVIDENCE_TYPES.get(definition.name)
    if server_required is None:
        raise ContractError("quality gate has no repository-owned evidence policy")
    caller_required = request.inputs.get("required_evidence_types", [])
    if (
        not isinstance(caller_required, list)
        or any(not isinstance(item, str) or not item for item in caller_required)
        or len(set(caller_required)) != len(caller_required)
    ):
        raise ContractError("required_evidence_types must be a unique string array")
    required_types = server_required | frozenset(caller_required)
    required_type_list = sorted(required_types)
    receipts = request.inputs.get("evidence_receipts")
    if not isinstance(receipts, list) or not receipts:
        return _operation(
            state=ExecutionState.BLOCKED,
            code="REQUIRED_EVIDENCE_NOT_RUN",
            definition=definition,
            outputs={
                "decision": "BLOCK",
                "required_evidence_types": required_type_list,
                "missing_evidence_types": required_type_list,
            },
            unavailable=("independently verified evidence receipts",),
            evidence_state=EvidenceState.NOT_RUN,
        )
    evidence = evaluate_evidence_set(
        receipts,
        request=request,
        authority=authority,
        expected_subject_digest=digest_json(
            {
                "route_id": request.inputs.get("route_id"),
                "required_evidence_types": required_type_list,
            }
        ),
    )
    observed_list = [str(item["evidence_type"]) for item in evidence["receipts"]]
    observed_types = set(observed_list)
    missing_types = sorted(required_types - observed_types)
    duplicate_types = sorted({item for item in observed_list if observed_list.count(item) > 1})
    if not evidence["all_independently_verified"] or missing_types or duplicate_types:
        return _operation(
            state=ExecutionState.BLOCKED,
            code="EVIDENCE_GATE_BLOCKED",
            definition=definition,
            outputs={
                "decision": "BLOCK",
                "evidence_evaluation": evidence,
                "missing_evidence_types": missing_types,
                "duplicate_evidence_types": duplicate_types,
                "required_evidence_types": required_type_list,
            },
            unavailable=("complete host-verified independent evidence",),
            evidence_state=EvidenceState.EXTERNAL_EXECUTED_UNVERIFIED,
        )
    return _operation(
        state=ExecutionState.READY_FOR_EXTERNAL_GATE,
        code="READY_FOR_EXTERNAL_CERTIFICATION_GATE",
        definition=definition,
        outputs={
            "decision": "READY_FOR_EXTERNAL_GATE",
            "evidence_evaluation": evidence,
            "required_evidence_types": required_type_list,
        },
        evidence_state=EvidenceState.INDEPENDENTLY_VERIFIED,
        certification=CertificationState.READY_FOR_EXTERNAL_GATE,
    )


def execute_compiled_skill(
    definition: SkillDefinition,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    catalog: CompiledCatalog,
) -> dict[str, Any]:
    _validate_inputs(definition, request.inputs)
    family = definition.operation_family
    if family in {"repository-intelligence", "legacy-intelligence"}:
        return _repository_intelligence(definition, request, authority, catalog)
    if family in {
        "transformation-plan",
        "technology-adapter",
        "legacy-adapter",
        "legacy-transformation",
        "route-execution",
    }:
        return _external_plan(definition, request, authority, catalog)
    if family == "native-runtime-lab":
        return _native_runtime_lab(definition, request, authority, catalog)
    if family in {
        "verification-delivery",
        "legacy-validation",
        "frontend-semantics",
        "type-semantics",
        "control-dataflow",
        "runtime-semantics",
        "behavior-oracle",
    }:
        return _compare_models(definition, request, authority, catalog)
    if family == "corpus-governance":
        return _corpus(definition, request, authority, catalog)
    if family == "formal-assurance":
        return _formal(definition, request, authority, catalog)
    if family == "semantic-fuzzing":
        return _fuzz(definition, request, authority, catalog)
    if family == "quality-gate":
        return _quality_gate(definition, request, authority, catalog)
    raise ContractError(f"no repository-owned operation for family: {family}")
