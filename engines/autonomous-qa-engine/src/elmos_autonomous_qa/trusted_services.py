"""Trusted service binders for stateful and filesystem-backed QA Skills.

Generic Skill dispatch accepts only bounded JSON and therefore cannot safely
select a database or project root.  ``QaApi`` owns this binder and supplies the
authenticated tenant/project/actor plus administrator-configured project roots.
The pure contract functions remain useful to CLI callers while making the
missing trusted binder explicit.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from collections.abc import Mapping
from typing import Any

from .contracts import ContractError, RuntimeRequest, digest_json, require_resource_id, require_text, strict_json
from .canonical import require_sha256
from .control_plane import QaControlPlane
from .project import build_project_snapshot


CONTROL_OPERATIONS = frozenset(
    {
        "create",
        "get",
        "transition",
        "retry",
        "recover",
        "events",
        "audit",
        "heartbeat",
        "shard_submit",
        "progress",
        "budget",
        "eta",
        "checkpoint",
    }
)
OBSERVATION_OPERATION_KINDS = MappingProxyType(
    {
        "heartbeat": "worker-heartbeat",
        "shard_submit": "shard-result",
        "progress": "progress",
        "budget": "budget",
        "eta": "eta",
        "checkpoint": "checkpoint",
    }
)
MAX_HISTORY_LIMIT = 500
RUN_PHASES = frozenset(
    {
        "context",
        "planning",
        "generation",
        "materializing_test_artifacts",
        "execution",
        "evidence",
        "repair",
        "gate",
        "reporting",
        "publishing_output",
        "lifecycle",
    }
)


def _exact_fields(
    value: Mapping[str, Any],
    *,
    field: str,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> None:
    if any(type(key) is not str for key in value):
        raise ContractError(f"{field} keys must be exact strings")
    unexpected = sorted(set(value).difference(allowed))
    missing = sorted(required.difference(value))
    if unexpected:
        raise ContractError(f"{field} contains unsupported fields: {unexpected}")
    if missing:
        raise ContractError(f"{field} is missing required fields: {missing}")


def _operation(inputs: Mapping[str, Any], *, allowed: frozenset[str]) -> str:
    operation = require_resource_id(inputs.get("operation"), "operation")
    if operation not in allowed:
        raise ContractError(f"unsupported operation: {operation}")
    return operation


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _bounded_number(value: Any, field: str, *, minimum: float = 0.0) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or float(value) < minimum
        or float(value) != float(value)
        or float(value) in {float("inf"), float("-inf")}
    ):
        raise ContractError(f"{field} must be a finite number >= {minimum}")
    return float(value)


def _observation_payload(operation: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError("observation payload must be an object")
    payload = strict_json(value, "observation payload")
    assert isinstance(payload, dict)
    if operation == "heartbeat":
        _exact_fields(
            payload,
            field="heartbeat",
            allowed=frozenset({"worker_id", "lease_epoch", "shard_id", "checkpoint_ref"}),
            required=frozenset({"worker_id", "lease_epoch"}),
        )
        require_resource_id(payload.get("worker_id"), "heartbeat.worker_id")
        if type(payload.get("lease_epoch")) is not int or payload["lease_epoch"] < 0:
            raise ContractError("heartbeat.lease_epoch must be a non-negative integer")
        for field in ("shard_id", "checkpoint_ref"):
            if field in payload:
                require_resource_id(payload[field], f"heartbeat.{field}")
    elif operation == "shard_submit":
        _exact_fields(
            payload,
            field="shard result",
            allowed=frozenset({"shard_id", "attempt", "terminal_status", "result_digest", "worker_id"}),
            required=frozenset({"shard_id", "attempt", "terminal_status", "result_digest", "worker_id"}),
        )
        require_resource_id(payload.get("shard_id"), "shard.shard_id")
        require_resource_id(payload.get("worker_id"), "shard.worker_id")
        if type(payload.get("attempt")) is not int or payload["attempt"] < 1:
            raise ContractError("shard.attempt must be a positive integer")
        if payload.get("terminal_status") not in {"PASSED", "FAILED", "BLOCKED"}:
            raise ContractError("shard.terminal_status is invalid")
        require_sha256(payload.get("result_digest"), field="shard.result_digest")
    elif operation == "progress":
        _exact_fields(
            payload,
            field="progress",
            allowed=frozenset({"phase", "completed_units", "total_units", "blocking_reasons"}),
            required=frozenset({"phase", "completed_units", "total_units"}),
        )
        phase = require_resource_id(payload.get("phase"), "progress.phase")
        if phase not in RUN_PHASES:
            raise ContractError("progress.phase is invalid")
        completed = _bounded_number(payload.get("completed_units"), "progress.completed_units")
        total = _bounded_number(payload.get("total_units"), "progress.total_units")
        if completed > total:
            raise ContractError("progress.completed_units may not exceed total_units")
        reasons = payload.get("blocking_reasons", [])
        if not isinstance(reasons, list) or any(type(item) is not str for item in reasons):
            raise ContractError("progress.blocking_reasons must be a string array")
    elif operation == "budget":
        _exact_fields(
            payload,
            field="budget",
            allowed=frozenset({"wall_seconds", "compute_seconds", "repair_attempts", "cost_amount", "currency"}),
            required=frozenset({"wall_seconds", "compute_seconds", "repair_attempts"}),
        )
        _bounded_number(payload.get("wall_seconds"), "budget.wall_seconds")
        _bounded_number(payload.get("compute_seconds"), "budget.compute_seconds")
        if type(payload.get("repair_attempts")) is not int or payload["repair_attempts"] < 0:
            raise ContractError("budget.repair_attempts must be a non-negative integer")
        if "cost_amount" in payload:
            amount = require_text(payload.get("cost_amount"), "budget.cost_amount")
            if not amount.replace(".", "", 1).isdigit():
                raise ContractError("budget.cost_amount must be a non-negative decimal string")
            require_resource_id(payload.get("currency"), "budget.currency")
    elif operation == "eta":
        _exact_fields(
            payload,
            field="eta",
            allowed=frozenset({"estimated_seconds", "confidence", "assumptions", "calibration_error"}),
            required=frozenset({"estimated_seconds", "confidence", "assumptions"}),
        )
        _bounded_number(payload.get("estimated_seconds"), "eta.estimated_seconds")
        confidence = _bounded_number(payload.get("confidence"), "eta.confidence")
        if confidence > 1:
            raise ContractError("eta.confidence must be <= 1")
        if not isinstance(payload.get("assumptions"), list) or any(
            type(item) is not str for item in payload["assumptions"]
        ):
            raise ContractError("eta.assumptions must be a string array")
        if "calibration_error" in payload:
            _bounded_number(payload["calibration_error"], "eta.calibration_error")
    elif operation == "checkpoint":
        _exact_fields(
            payload,
            field="checkpoint",
            allowed=frozenset({"checkpoint_id", "sequence", "state_digest", "evidence_refs", "phase"}),
            required=frozenset({"checkpoint_id", "sequence", "state_digest", "phase"}),
        )
        require_resource_id(payload.get("checkpoint_id"), "checkpoint.checkpoint_id")
        if type(payload.get("sequence")) is not int or payload["sequence"] < 1:
            raise ContractError("checkpoint.sequence must be a positive integer")
        require_sha256(payload.get("state_digest"), field="checkpoint.state_digest")
        phase = require_resource_id(payload.get("phase"), "checkpoint.phase")
        if phase not in RUN_PHASES:
            raise ContractError("checkpoint.phase is invalid")
        refs = payload.get("evidence_refs", [])
        if not isinstance(refs, list):
            raise ContractError("checkpoint.evidence_refs must be an array")
        for item in refs:
            require_resource_id(item, "checkpoint.evidence_refs[]")
    else:
        raise ContractError(f"unsupported observation operation: {operation}")
    return payload


def control_plane_operation_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the exact public operation without accepting caller storage."""

    operation = _operation(inputs, allowed=CONTROL_OPERATIONS)
    allowed_fields = {
        "create": frozenset({"operation", "run_id", "mode", "payload", "_runtime_context"}),
        "get": frozenset({"operation", "run_id", "_runtime_context"}),
        "transition": frozenset({"operation", "run_id", "action", "details", "_runtime_context"}),
        "retry": frozenset({"operation", "source_run_id", "new_run_id", "_runtime_context"}),
        "recover": frozenset({"operation", "limit", "_runtime_context"}),
        "events": frozenset({"operation", "run_id", "after_sequence", "limit", "_runtime_context"}),
        "audit": frozenset({"operation", "run_id", "after_audit_id", "limit", "_runtime_context"}),
        **{
            name: frozenset({"operation", "run_id", "payload", "_runtime_context"})
            for name in OBSERVATION_OPERATION_KINDS
        },
    }[operation]
    _exact_fields(inputs, field="control-plane operation", allowed=allowed_fields)
    if operation in {"create", "get", "transition", "events", "audit"}:
        require_resource_id(inputs.get("run_id"), "run_id")
    if operation == "retry":
        require_resource_id(inputs.get("source_run_id"), "source_run_id")
        require_resource_id(inputs.get("new_run_id"), "new_run_id")
    if operation in OBSERVATION_OPERATION_KINDS:
        require_resource_id(inputs.get("run_id"), "run_id")
        _observation_payload(operation, inputs.get("payload"))
    return {
        "state": "PARTIAL",
        "code": "TRUSTED_CONTROL_PLANE_BINDER_REQUIRED",
        "outputs": {
            "operation": operation,
            "validated": True,
            "persisted": False,
            "durable_control_plane": "NOT_RUN",
            "caller_database_path_accepted": False,
        },
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED",
    }


def project_context_operation_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    operation = _operation(inputs, allowed=frozenset({"snapshot"}))
    _exact_fields(
        inputs,
        field="project-context operation",
        allowed=frozenset({"operation", "required_paths", "_runtime_context"}),
    )
    required_paths = inputs.get("required_paths", [])
    if not isinstance(required_paths, list) or any(type(item) is not str for item in required_paths):
        raise ContractError("required_paths must be a string array")
    strict_json(required_paths, "required_paths")
    return {
        "state": "PARTIAL",
        "code": "TRUSTED_PROJECT_ROOT_BINDER_REQUIRED",
        "outputs": {
            "operation": operation,
            "snapshot": "NOT_RUN",
            "caller_project_root_accepted": False,
            "trusted_project_binding": "NOT_RUN",
        },
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED",
    }


class TrustedProjectRoots:
    """Immutable tenant/project to administrator-configured root bindings."""

    def __init__(self, bindings: Mapping[tuple[str, str], str | Path] | None = None) -> None:
        normalized: dict[tuple[str, str], Path] = {}
        for raw_key, raw_root in ({} if bindings is None else bindings).items():
            if (
                not isinstance(raw_key, tuple)
                or len(raw_key) != 2
                or any(type(item) is not str for item in raw_key)
            ):
                raise TypeError("project-root bindings require exact (tenant_id, project_id) keys")
            tenant_id = require_resource_id(raw_key[0], "binding.tenant_id")
            project_id = require_resource_id(raw_key[1], "binding.project_id")
            root = Path(raw_root)
            if not root.is_absolute():
                raise ValueError("trusted project roots must be absolute")
            normalized[(tenant_id, project_id)] = root
        self._bindings = MappingProxyType(normalized)

    def root_for(self, *, tenant_id: str, project_id: str) -> Path:
        key = (
            require_resource_id(tenant_id, "tenant_id"),
            require_resource_id(project_id, "project_id"),
        )
        try:
            return self._bindings[key]
        except KeyError as exc:
            raise ContractError("trusted project root binding is unavailable") from exc


class TrustedSkillServices:
    """Execute exact Skill operations against API-owned trusted resources."""

    def __init__(
        self,
        control_plane: QaControlPlane,
        *,
        project_roots: TrustedProjectRoots | None = None,
    ) -> None:
        if type(control_plane) is not QaControlPlane:
            raise TypeError("control_plane must be an exact QaControlPlane")
        self.control_plane = control_plane
        self.project_roots = project_roots or TrustedProjectRoots()

    @staticmethod
    def _idempotency(request: RuntimeRequest) -> str:
        if request.idempotency_key is None:
            raise ContractError("idempotency_key is required for this operation")
        return request.idempotency_key

    def _project_run(self, request: RuntimeRequest, run_id: str):
        run = self.control_plane.get_run(tenant_id=request.tenant_id, run_id=run_id)
        if run.project_id != request.project_id:
            raise ContractError("run is not bound to the authenticated project")
        return run

    def execute_control_plane(self, request: RuntimeRequest) -> Mapping[str, Any]:
        inputs = request.inputs
        operation = _operation(inputs, allowed=CONTROL_OPERATIONS)
        # Reuse the pure validator with a trusted context-shaped sentinel.  It
        # validates the public field set but never supplies storage authority.
        control_plane_operation_contract({**dict(inputs), "_runtime_context": {}})
        actor = request.actor_id
        if operation == "create":
            if actor is None:
                raise ContractError("actor_id is required for create")
            raw_payload = inputs.get("payload", {})
            if not isinstance(raw_payload, Mapping):
                raise ContractError("payload must be an object")
            run = self.control_plane.create_run(
                tenant_id=request.tenant_id,
                run_id=require_resource_id(inputs.get("run_id"), "run_id"),
                project_id=request.project_id,
                mode=require_text(inputs.get("mode"), "mode"),
                payload=strict_json(raw_payload, "payload"),
                idempotency_key=self._idempotency(request),
                actor=actor,
            )
            return self._control_result(operation, run=run)
        if operation == "get":
            run = self._project_run(
                request, require_resource_id(inputs.get("run_id"), "run_id")
            )
            return self._control_result(operation, run=run)
        if operation == "transition":
            if actor is None:
                raise ContractError("actor_id is required for transition")
            run_id = require_resource_id(inputs.get("run_id"), "run_id")
            self._project_run(request, run_id)
            raw_details = inputs.get("details", {})
            if not isinstance(raw_details, Mapping):
                raise ContractError("transition details must be an object")
            run = self.control_plane.transition(
                tenant_id=request.tenant_id,
                run_id=run_id,
                action=require_resource_id(inputs.get("action"), "action"),
                idempotency_key=self._idempotency(request),
                actor=actor,
                details=strict_json(raw_details, "transition details"),
            )
            return self._control_result(operation, run=run)
        if operation == "retry":
            if actor is None:
                raise ContractError("actor_id is required for retry")
            source_run_id = require_resource_id(inputs.get("source_run_id"), "source_run_id")
            self._project_run(request, source_run_id)
            run = self.control_plane.retry_run(
                tenant_id=request.tenant_id,
                source_run_id=source_run_id,
                new_run_id=require_resource_id(inputs.get("new_run_id"), "new_run_id"),
                idempotency_key=self._idempotency(request),
                actor=actor,
            )
            return self._control_result(operation, run=run)
        if operation == "recover":
            limit = inputs.get("limit", MAX_HISTORY_LIMIT)
            if type(limit) is not int or not 1 <= limit <= MAX_HISTORY_LIMIT:
                raise ContractError("recover limit is invalid")
            runs = [
                run
                for run in self.control_plane.recover_active_runs(
                    tenant_id=request.tenant_id,
                    limit=limit,
                )
                if run.project_id == request.project_id
            ]
            return self._control_result(operation, runs=runs)
        if operation in {"events", "audit"}:
            run_id = require_resource_id(inputs.get("run_id"), "run_id")
            self._project_run(request, run_id)
            limit = inputs.get("limit", 100)
            if type(limit) is not int or not 1 <= limit <= MAX_HISTORY_LIMIT:
                raise ContractError("history limit is invalid")
            if operation == "events":
                after = inputs.get("after_sequence", 0)
                if type(after) is not int or after < 0:
                    raise ContractError("after_sequence is invalid")
                records = self.control_plane.list_events(
                    tenant_id=request.tenant_id,
                    run_id=run_id,
                    after_sequence=after,
                    limit=limit,
                )
            else:
                after = inputs.get("after_audit_id", 0)
                if type(after) is not int or after < 0:
                    raise ContractError("after_audit_id is invalid")
                records = self.control_plane.list_audit(
                    tenant_id=request.tenant_id,
                    run_id=run_id,
                    after_audit_id=after,
                    limit=limit,
                )
            return self._control_result(operation, records=records)
        if actor is None:
            raise ContractError("actor_id is required for observations")
        run_id = require_resource_id(inputs.get("run_id"), "run_id")
        self._project_run(request, run_id)
        raw_observation = _observation_payload(operation, inputs.get("payload"))
        run = self.control_plane.record_observation(
            tenant_id=request.tenant_id,
            run_id=run_id,
            kind=OBSERVATION_OPERATION_KINDS[operation],
            payload=raw_observation,
            idempotency_key=self._idempotency(request),
            actor=actor,
        )
        return self._control_result(operation, run=run)

    def _control_result(
        self,
        operation: str,
        *,
        run: Any | None = None,
        runs: Any | None = None,
        records: Any | None = None,
    ) -> Mapping[str, Any]:
        outputs: dict[str, Any] = {
            "operation": operation,
            "persisted": True,
            "durable_control_plane": "LOCAL_EXECUTED",
            "independent_evidence": "NOT_RUN",
        }
        if run is not None:
            outputs["run"] = _jsonable(run)
            outputs["view"] = self._run_view(run)
        if runs is not None:
            outputs["runs"] = _jsonable(runs)
            outputs["views"] = [self._run_view(item) for item in runs]
        if records is not None:
            outputs["records"] = _jsonable(records)
        outputs["result_digest"] = digest_json(outputs)
        return {
            "state": "SUCCEEDED",
            "code": f"CONTROL_PLANE_{operation.upper()}_PERSISTED",
            "outputs": outputs,
            "implementation_state": "LOCAL_EXECUTED",
        }

    def _run_view(self, run: Any) -> Mapping[str, Any]:
        events: list[Any] = []
        after = 0
        while True:
            page = self.control_plane.list_events(
                tenant_id=run.tenant_id,
                run_id=run.run_id,
                after_sequence=after,
                limit=MAX_HISTORY_LIMIT,
            )
            events.extend(page)
            if len(page) < MAX_HISTORY_LIMIT:
                break
            after = page[-1].sequence
        latest: dict[str, Any] = {}
        phase = "control"
        for event in events:
            if event.kind == "run.begin_materialization":
                phase = "materializing_test_artifacts"
            elif event.kind == "run.begin_publishing":
                phase = "publishing_output"
            elif event.kind == "run.complete":
                phase = "complete"
            elif event.kind.startswith("run.observation."):
                kind = event.kind.removeprefix("run.observation.")
                observation = event.payload.get("observation", {})
                latest[kind] = observation
                if kind == "progress" and observation.get("phase") in RUN_PHASES:
                    phase = observation["phase"]
        return {
            "run_id": run.run_id,
            "status": run.status.value,
            "phase": phase,
            "progress": latest.get("progress"),
            "eta": latest.get("eta"),
            "budget": latest.get("budget"),
            "checkpoint": latest.get("checkpoint"),
            "worker_heartbeat": latest.get("worker-heartbeat"),
            "latest_shard_result": latest.get("shard-result"),
            "observation_count": sum(
                event.kind.startswith("run.observation.") for event in events
            ),
            "external_evidence": "NOT_RUN",
        }

    def execute_project_context(self, request: RuntimeRequest) -> Mapping[str, Any]:
        inputs = request.inputs
        project_context_operation_contract({**dict(inputs), "_runtime_context": {}})
        root = self.project_roots.root_for(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
        )
        raw_required = inputs.get("required_paths", [])
        assert isinstance(raw_required, list)
        required_paths = tuple(raw_required)
        snapshot = build_project_snapshot(root, required_paths=required_paths)
        files = snapshot["files"]
        module_roots = sorted(
            {
                PurePosixPath(item["path"]).parts[0]
                if len(PurePosixPath(item["path"]).parts) > 1
                else "."
                for item in files
            }
        )
        entry_names = {
            "main.py",
            "app.py",
            "server.py",
            "main.go",
            "main.rs",
            "Program.cs",
            "Application.java",
            "index.ts",
            "index.js",
        }
        entrypoints = sorted(
            item["path"]
            for item in files
            if PurePosixPath(item["path"]).name in entry_names
        )
        build_markers = {
            "pyproject.toml": "python",
            "requirements.txt": "python",
            "package.json": "node",
            "pom.xml": "maven",
            "build.gradle": "gradle",
            "build.gradle.kts": "gradle",
            "Cargo.toml": "cargo",
            "go.mod": "go",
            "Package.swift": "swift",
            "CMakeLists.txt": "cmake",
            "pubspec.yaml": "flutter",
        }
        environment_names = {
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            ".tool-versions",
            ".python-version",
            ".node-version",
        }
        build_systems = sorted(
            {
                build_markers[PurePosixPath(item["path"]).name]
                for item in files
                if PurePosixPath(item["path"]).name in build_markers
            }
        )
        environment_dependencies = sorted(
            item["path"]
            for item in files
            if PurePosixPath(item["path"]).name in environment_names
            or PurePosixPath(item["path"]).name.endswith((".lock", "lock.json"))
        )
        source_locations = [
            {
                "path": item["path"],
                "kind": item["kind"],
                "sha256": item["sha256"],
                "parser_version": "elmos-project-snapshot-hash-v1",
                "content_exposed": False,
            }
            for item in files
        ]
        outputs = {
            "snapshot": snapshot,
            "source_locations": source_locations,
            "module_roots": module_roots,
            "entrypoints": entrypoints,
            "build_systems": build_systems,
            "build_command_execution": "NOT_RUN",
            "environment_dependencies": environment_dependencies,
            "trusted_project_binding": "LOCAL_EXECUTED",
            "caller_project_root_accepted": False,
            "parser_version": "elmos-project-snapshot-hash-v1",
            "omission_count": snapshot["inventory_omission_count"],
        }
        outputs["context_digest"] = digest_json(outputs)
        complete = bool(snapshot["complete"])
        return {
            "state": "SUCCEEDED" if complete else "PARTIAL",
            "code": "TRUSTED_PROJECT_CONTEXT_INGESTED"
            if complete
            else "PROJECT_CONTEXT_INGESTED_WITH_OMISSIONS",
            "outputs": outputs,
            "implementation_state": "LOCAL_EXECUTED",
        }
