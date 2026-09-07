"""Production adapter contract and durable local reference harness."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from .budget import BudgetLedger
from .canonical import canonical_json, digest_json
from .checkpoint import CheckpointStore
from .evidence import EvidenceStore
from .policy import authorize
from .state import JsonRunStateStore, RunState


PHASE_ORDER = (
    "prepare",
    "baseline",
    "transform_or_generate",
    "build",
    "validate",
    "score",
    "publish",
)
RECOVERY_PHASES = ("compensate", "cleanup")
REQUIRED_PHASES = PHASE_ORDER + RECOVERY_PHASES
REQUIRED_CONTEXT = (
    "tenant_id",
    "project_id",
    "task_id",
    "run_id",
    "case_run_id",
    "candidate_digest",
    "plan_digest",
    "case_digest",
    "environment_id",
    "authority_id",
    "owner_id",
    "fencing_token",
    "idempotency_key",
    "checkpoint_digest",
)
REQUIRED_OUTPUTS = {
    "prepare": ("workspace_digest", "toolchain_digest", "dependency_lock_digest"),
    "baseline": ("source_build", "source_contract", "source_state", "source_trace", "source_flake_report"),
    "transform_or_generate": ("target_repository_digest", "adaptation_manifest", "unsupported_manifest", "machine_usage"),
    "build": ("clean_build_result", "sbom_digest", "provenance_digest", "artifact_digests"),
    "validate": ("public_test_results", "hidden_test_results", "oracle_results", "mutation_results", "performance_results"),
    "score": ("score_document", "failure_classifications", "silent_semantic_error_claims"),
    "publish": ("evidence_manifest_digest", "evidence_signature", "report_uris"),
    "compensate": ("compensation_receipts", "unresolved_side_effects"),
    "cleanup": ("workspace_cleanup_receipt", "retained_artifact_refs"),
}
_DIGEST_OUTPUTS = frozenset(
    {
        "workspace_digest",
        "toolchain_digest",
        "dependency_lock_digest",
        "target_repository_digest",
        "sbom_digest",
        "provenance_digest",
        "evidence_manifest_digest",
    }
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_VALID_PHASE_STATUSES = frozenset({"passed", "failed", "blocked", "error", "unavailable"})


class HarnessContractError(RuntimeError):
    """Raised when an adapter or phase result violates the ETGB contract."""


def _contract_document() -> dict[str, Any]:
    """Return the immutable contract shape enforced by the runtime.

    The package's YAML contract is declarative input.  Keeping this minimal
    shape in the runtime means a malformed or drifted package contract cannot
    silently weaken the execution path.
    """

    return {
        "schema_version": "1.1",
        "contract_id": "elmos.etgb.harness-adapter",
        "context_required": list(REQUIRED_CONTEXT),
        "phases": [{"name": name, "response": list(REQUIRED_OUTPUTS[name])} for name in REQUIRED_PHASES],
        "idempotency": {
            "key_format": "{tenant_id}:{run_id}:{case_run_id}:{phase}:{phase_revision}",
            "duplicate_policy": "return_original_response",
        },
        "fencing": {
            "required_on": [
                "workspace mutation",
                "checkpoint write",
                "artifact publication",
                "external side effect",
                "billing usage write",
            ],
            "stale_token_policy": "reject_without_side_effect",
        },
        "checkpoint": {
            "required_after_each_phase": True,
            "verify": [
                "candidate_digest",
                "plan_digest",
                "environment_digest",
                "workspace_digest",
                "artifact_digests",
                "side_effect_receipts",
            ],
        },
    }


def harness_contract_report(contract_path: Path | None = None) -> dict[str, Any]:
    """Validate the package contract against the executable runtime contract."""

    errors: list[str] = []
    source = "runtime-default"
    document: dict[str, Any] = _contract_document()
    if contract_path is not None:
        source = str(contract_path)
        path = Path(contract_path)
        if path.is_symlink() or not path.is_file():
            errors.append("Harness contract must be a regular file")
        else:
            try:
                loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, yaml.YAMLError) as exc:
                loaded = None
                errors.append(f"Harness contract is unreadable: {exc}")
            if isinstance(loaded, Mapping):
                document = dict(loaded)
            elif loaded is not None:
                errors.append("Harness contract must be a YAML object")
    if document.get("schema_version") != "1.1":
        errors.append("contract schema_version must be 1.1")
    if document.get("contract_id") != "elmos.etgb.harness-adapter":
        errors.append("contract_id does not identify the ETGB adapter contract")
    if tuple(document.get("context_required", [])) != REQUIRED_CONTEXT:
        errors.append("contract context_required does not match the runtime binding")
    phases = document.get("phases")
    phase_names = tuple(item.get("name") for item in phases) if isinstance(phases, list) and all(isinstance(item, Mapping) for item in phases) else ()
    if phase_names != REQUIRED_PHASES:
        errors.append("contract phases do not match the required prepare-to-publish and recovery order")
    else:
        for item in phases:
            expected = tuple(REQUIRED_OUTPUTS[str(item["name"])])
            actual = tuple(item.get("response", []))
            if actual != expected:
                errors.append(f"contract response fields drifted for phase {item['name']}")
    expected_contract = _contract_document()
    if document.get("idempotency") != expected_contract["idempotency"]:
        errors.append("contract idempotency requirements are incomplete")
    if document.get("fencing") != expected_contract["fencing"]:
        errors.append("contract fencing requirements are incomplete")
    checkpoint = document.get("checkpoint")
    if checkpoint != expected_contract["checkpoint"]:
        errors.append("contract checkpoint requirements are incomplete")
    return {
        "schema_version": "1.1",
        "contract_id": "elmos.etgb.harness-adapter",
        "valid": not errors,
        "source": source,
        "contract_digest": "sha256:" + digest_json(document),
        "required_context": list(REQUIRED_CONTEXT),
        "required_phases": list(REQUIRED_PHASES),
        "required_outputs": {phase: list(fields) for phase, fields in REQUIRED_OUTPUTS.items()},
        "errors": errors,
    }


def adapter_conformance_report(adapter: Any) -> dict[str, Any]:
    """Check implementation shape before any state or external side effect."""

    missing = [phase for phase in REQUIRED_PHASES if not callable(getattr(adapter, phase, None))]
    return {
        "schema_version": "1.1",
        "valid": not missing,
        "required_phases": list(REQUIRED_PHASES),
        "implemented_phases": [phase for phase in REQUIRED_PHASES if phase not in missing],
        "missing_phases": missing,
        "status": "CONFORMANT" if not missing else "BLOCKED",
        "certification_status": "NOT_CERTIFIED",
    }


def _validate_phase_result(phase: str, result: Any, *, require_outputs: bool = True) -> None:
    if not isinstance(result, PhaseResult):
        raise HarnessContractError(f"{phase} must return PhaseResult")
    if result.status not in _VALID_PHASE_STATUSES:
        raise HarnessContractError(f"{phase} returned unsupported status: {result.status}")
    if not isinstance(result.outputs, dict):
        raise HarnessContractError(f"{phase}.outputs must be an object")
    if require_outputs and result.status == "passed":
        missing = [field for field in REQUIRED_OUTPUTS[phase] if field not in result.outputs or result.outputs[field] is None]
        if missing:
            raise HarnessContractError(f"{phase} is missing required outputs: {', '.join(missing)}")
    for output_field in _DIGEST_OUTPUTS.intersection(result.outputs):
        if not isinstance(result.outputs[output_field], str) or not _DIGEST.fullmatch(result.outputs[output_field]):
            raise HarnessContractError(f"{phase}.{output_field} must be sha256:<64 hex>")
    artifact_digests = result.outputs.get("artifact_digests")
    if artifact_digests is not None and (not isinstance(artifact_digests, list) or any(not isinstance(value, str) or not _DIGEST.fullmatch(value) for value in artifact_digests)):
        raise HarnessContractError(f"{phase}.artifact_digests must contain only sha256 digests")
    if not isinstance(result.artifacts, list) or any(not isinstance(path, Path) for path in result.artifacts):
        raise HarnessContractError(f"{phase}.artifacts must contain pathlib.Path values")
    for path in result.artifacts:
        if path.is_symlink() or not path.is_file():
            raise HarnessContractError(f"{phase} artifact must be a regular file: {path}")
    if not isinstance(result.side_effects, list) or any(not isinstance(effect, Mapping) for effect in result.side_effects):
        raise HarnessContractError(f"{phase}.side_effects must contain objects")
    if not isinstance(result.usage, Mapping):
        raise HarnessContractError(f"{phase}.usage must be an object")
    allowed_usage = {"input_tokens", "output_tokens", "credit_usd", "wall_clock_ms"}
    if set(result.usage) - allowed_usage:
        raise HarnessContractError(f"{phase}.usage contains unsupported fields")
    for key, value in result.usage.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise HarnessContractError(f"{phase}.usage.{key} must be non-negative numeric")


def _raw_phase_result(result: PhaseResult) -> dict[str, Any]:
    """Create a JSON-safe representation without dropping raw adapter data."""

    raw = {
        "status": result.status,
        "outputs": result.outputs,
        "artifacts": [str(path) for path in result.artifacts],
        "side_effects": [dict(effect) for effect in result.side_effects],
        "usage": dict(result.usage),
        "message": result.message,
    }
    # Fail before the phase can be checkpointed if a provider returned a value
    # that cannot be represented in the evidence ledger.
    canonical_json(raw)
    return raw


@dataclass
class PhaseResult:
    status: str
    outputs: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Path] = field(default_factory=list)
    side_effects: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    message: str | None = None


class HarnessAdapter(Protocol):
    def prepare(self, context: dict[str, Any]) -> PhaseResult: ...
    def baseline(self, context: dict[str, Any]) -> PhaseResult: ...
    def transform_or_generate(self, context: dict[str, Any]) -> PhaseResult: ...
    def build(self, context: dict[str, Any]) -> PhaseResult: ...
    def validate(self, context: dict[str, Any]) -> PhaseResult: ...
    def score(self, context: dict[str, Any]) -> PhaseResult: ...
    def publish(self, context: dict[str, Any]) -> PhaseResult: ...
    def compensate(self, context: dict[str, Any]) -> PhaseResult: ...
    def cleanup(self, context: dict[str, Any]) -> PhaseResult: ...


def phase_plan(context: dict[str, Any]) -> list[tuple[RunState, str, RunState]]:
    work = RunState.GENERATING if context.get("business_line") == "project-generation" else RunState.TRANSFORMING
    return [(RunState.PLANNED, "prepare", RunState.PREPARING), (RunState.PREPARING, "baseline", RunState.BASELINING), (RunState.BASELINING, "transform_or_generate", work), (work, "build", RunState.BUILDING), (RunState.BUILDING, "validate", RunState.VALIDATING), (RunState.VALIDATING, "score", RunState.SCORING), (RunState.SCORING, "publish", RunState.PUBLISHING)]


class HarnessRuntime:
    """Reference orchestration enforcing ownership, contract, evidence and CAS."""

    def __init__(self, *, state_store: JsonRunStateStore, checkpoint_store: CheckpointStore, budget_ledger: BudgetLedger, evidence_store: EvidenceStore):
        self.state_store = state_store; self.checkpoint_store = checkpoint_store; self.budget_ledger = budget_ledger; self.evidence_store = evidence_store

    def execute(self, *, run_id: str, adapter: HarnessAdapter, context: dict[str, Any], authority: dict[str, Any], owner_id: str, fencing_token: int) -> dict[str, Any]:
        run = self.state_store.load(run_id)
        if run.get("fencing_token") != fencing_token or run.get("owner_id") != owner_id: raise PermissionError("runtime ownership/fencing mismatch")
        context = {**context, "run_id": run_id, "owner_id": owner_id, "fencing_token": fencing_token}
        missing_context = [field for field in REQUIRED_CONTEXT if field not in context]
        if missing_context:
            raise HarnessContractError("execution context is missing: " + ", ".join(missing_context))
        conformance = adapter_conformance_report(adapter)
        if not conformance["valid"]:
            raise HarnessContractError("adapter is not conformant: " + ", ".join(conformance["missing_phases"]))
        records: list[dict[str, Any]] = []

        def authorize_phase(method_name: str) -> None:
            decision = authorize(authority, {"environment_id": authority.get("environment_id"), "authority_id": authority.get("authority_id"), "owner_id": owner_id, "tenant_id": authority.get("tenant_id"), "action": f"harness.{method_name}", "fencing_token": fencing_token})
            if not decision.allowed:
                raise PermissionError(decision.reason)

        try:
            for expected, method_name, target in phase_plan(context):
                current = self.state_store.load(run_id)
                if RunState(current["state"]) == expected:
                    current = self.state_store.transition(run_id=run_id, expected_state=expected, target_state=target, owner_id=owner_id, fencing_token=fencing_token, expected_revision=current["revision"], reason=f"enter {method_name}")
                elif RunState(current["state"]) != target:
                    raise RuntimeError(f"unexpected run state before {method_name}: {current['state']}")
                authorize_phase(method_name)
                started = time.perf_counter(); result = getattr(adapter, method_name)(context); duration_ms = int((time.perf_counter() - started) * 1000)
                _validate_phase_result(method_name, result)
                if result.status != "passed": raise RuntimeError(result.message or f"phase failed: {method_name}")
                raw_result = _raw_phase_result(result)
                raw_artifact = self.evidence_store.add_json(logical_name=f"phases/{method_name}/raw-result.json", value=raw_result, producer_environment=str(authority["environment_id"]))
                usage = {"input_tokens": int(result.usage.get("input_tokens", 0)), "output_tokens": int(result.usage.get("output_tokens", 0)), "credit_usd": float(result.usage.get("credit_usd", 0.0)), "wall_clock_ms": int(result.usage.get("wall_clock_ms", duration_ms))}
                self.budget_ledger.consume(run_id=run_id, idempotency_key=f"{run_id}:{method_name}:{current['revision']}", phase=method_name, **usage)
                artifacts = []
                for index, artifact_path in enumerate(result.artifacts):
                    artifact = self.evidence_store.add_file(artifact_path, logical_name=f"phases/{method_name}/{index:03d}-{artifact_path.name}", producer_environment=str(authority["environment_id"]), redact=artifact_path.suffix.lower() in {".txt", ".log", ".json", ".yaml", ".yml"})
                    artifacts.append({"path": str(artifact_path), "logical_name": artifact["logical_name"], "sha256": artifact["sha256"]})
                checkpoint_payload = {**result.outputs, "artifact_digests": result.outputs.get("artifact_digests", []), "side_effect_receipts": result.side_effects, "raw_result_artifact": raw_artifact}
                workspace_digest = str(result.outputs.get("workspace_digest") or context.get("workspace_digest") or "")
                checkpoint = self.checkpoint_store.save(run_id=run_id, phase=target.value, candidate_digest=run["candidate_digest"], plan_digest=run["plan_digest"], environment_digest=authority.get("digest") or digest_json(authority), workspace_digest=workspace_digest or None, fencing_token=fencing_token, artifacts=artifacts, side_effects=result.side_effects, resume_payload=checkpoint_payload)
                latest = self.state_store.load(run_id)
                self.state_store.record_checkpoint(run_id=run_id, checkpoint_digest=checkpoint["checkpoint_digest"], owner_id=owner_id, fencing_token=fencing_token, expected_revision=latest["revision"], phase=method_name)
                records.append({"phase": method_name, "state": target.value, "duration_ms": duration_ms, "usage": usage, "checkpoint_digest": checkpoint["checkpoint_digest"], "outputs_digest": digest_json(result.outputs), "raw_result_artifact": raw_artifact, "artifact_digests": list(result.outputs.get("artifact_digests", [])), "side_effect_receipts": list(result.side_effects)})
                context[method_name] = result.outputs
                context.update(result.outputs)
            current = self.state_store.load(run_id)
            current = self.state_store.transition(run_id=run_id, expected_state=RunState.PUBLISHING, target_state=RunState.COMPLETED, owner_id=owner_id, fencing_token=fencing_token, expected_revision=current["revision"], reason="all phases completed")
            self.evidence_store.add_json(logical_name="run/phase-records.json", value=records, producer_environment=str(authority["environment_id"]))
            self.evidence_store.seal({"run_id": run_id, "tenant_id": authority["tenant_id"], "candidate_digest": run["candidate_digest"], "plan_digest": run["plan_digest"], "final_state": current["state"]})
            self.budget_ledger.close(run_id)
            return {"status": "COMPLETED", "phases": records, "evidence": self.evidence_store.verify()}
        except Exception as exc:
            current = self.state_store.load(run_id); state = RunState(current["state"])
            if state not in {RunState.COMPLETED, RunState.CANCELLED, RunState.FAILED, RunState.BLOCKED}:
                try:
                    self.state_store.transition(run_id=run_id, expected_state=state, target_state=RunState.FAILED, owner_id=owner_id, fencing_token=fencing_token, expected_revision=current["revision"], reason=f"runtime failure: {type(exc).__name__}")
                except Exception: pass
            recovery_errors: list[str] = []
            for method_name in RECOVERY_PHASES:
                try:
                    authorize_phase(method_name)
                    recovery_result = getattr(adapter, method_name)(context)
                    _validate_phase_result(method_name, recovery_result)
                    if recovery_result.status != "passed":
                        raise HarnessContractError(recovery_result.message or f"{method_name} did not pass")
                    raw_recovery = _raw_phase_result(recovery_result)
                    self.evidence_store.add_json(logical_name=f"recovery/{method_name}/raw-result.json", value=raw_recovery, producer_environment=str(authority["environment_id"]))
                except Exception as recovery_exc:
                    recovery_errors.append(f"{method_name}: {type(recovery_exc).__name__}: {recovery_exc}")
            if recovery_errors:
                raise HarnessContractError("original Harness failure retained; recovery failed: " + "; ".join(recovery_errors)) from exc
            raise
