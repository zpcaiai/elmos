"""Durable v3 control-plane binding for Skill execution.

This module is the only HTTP-facing orchestration layer allowed to turn an
authenticated invocation into durable workflow, evidence, checkpoint and
terminal run state.  Caller-supplied evidence claims remain ordinary input;
only bytes re-read through :class:`EvidenceService` are trusted evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import multiprocessing
import threading
import time
from typing import Any, Callable, Mapping, Protocol
import uuid

from .canonical import canonical_json_bytes, digest_bytes, digest_object
from .contracts import EvidenceProducer, SecurityContext
from .errors import ConflictError, NotFoundError, ValidationError
from .evidence import EvidenceService
from .skills import SkillExecutionResult, SkillRuntime
from .storage import ControlPlaneReceipt, ControlPlaneStore
from .workflow import RunState, TERMINAL_STATES, WorkflowEngine


CONTROL_PLANE_TOOL_DIGEST = digest_bytes(
    b"elmos-proof-driven-harness-engine:3.0.0:durable-control-plane",
    domain="tool-identity",
)


class AuthenticatedPrincipal(Protocol):
    tenant_id: str
    project_id: str
    actor_id: str
    authority: tuple[str, ...]
    authentication_context_digest: str
    authority_id: str
    authority_revision: str
    environment_id: str
    environment_revision: str
    execution_epoch: int
    fencing_generation: int
    expires_at: datetime


class RunSnapshotLike(Protocol):
    run_id: str
    state: str
    sequence: int
    execution_epoch: int
    fencing_generation: int
    lease_expires_at: datetime | None
    deadline_at: datetime | None
    last_checkpoint_id: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class InvocationOutcome:
    result: Mapping[str, Any]
    run: RunSnapshotLike
    replay: bool
    completed: bool


@dataclass(frozen=True, slots=True)
class CancelOutcome:
    run: Mapping[str, Any]
    replay: bool


@dataclass(frozen=True, slots=True)
class _PersistedPrincipal:
    """Trusted principal projection persisted in the admission receipt.

    It contains no bearer credential.  Every field originated in verified
    authentication middleware and is included in the canonical request digest.
    """

    tenant_id: str
    project_id: str
    actor_id: str
    authority: tuple[str, ...]
    authentication_context_digest: str
    authority_id: str
    authority_revision: str
    environment_id: str
    environment_revision: str
    execution_epoch: int
    fencing_generation: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class _ActiveLease:
    context: SecurityContext
    token: str
    sequence: int


@dataclass(frozen=True, slots=True)
class _BoundedExecution:
    result: SkillExecutionResult
    elapsed_ms: int
    output_bytes: int
    cost_microunits: int
    timed_out: bool = False


def _isolated_skill_execute(
    connection: Any,
    skill: str,
    payload: Mapping[str, Any],
    context: Mapping[str, Any],
    workspace_roots: tuple[str, ...],
) -> None:
    """Execute a pure, effect-denied handler in a killable child process."""

    try:
        runtime = SkillRuntime(workspace_roots=workspace_roots)
        result = runtime.execute(skill, payload, context=context)
        connection.send_bytes(canonical_json_bytes(result.to_dict()))
    except Exception:
        failure = SkillExecutionResult(
            skill,
            "FAILED",
            {},
            reason="isolated Skill worker failed without a trustworthy result",
        )
        connection.send_bytes(canonical_json_bytes(failure.to_dict()))
    finally:
        connection.close()


class _LeaseHeartbeat:
    """Renew a same-owner lease while an in-process bounded handler runs."""

    def __init__(
        self,
        workflow: WorkflowEngine,
        context: SecurityContext,
        *,
        owner_id: str,
        sequence: int,
        lease_token: str,
        ttl_seconds: int,
    ) -> None:
        self._workflow = workflow
        self._context = context
        self._owner_id = owner_id
        self._sequence = sequence
        self._lease_token = lease_token
        self._ttl_seconds = ttl_seconds
        self._interval = max(0.25, ttl_seconds / 3)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._error: Exception | None = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"proof-harness-lease-{context.run_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> tuple[SecurityContext, str, int]:
        self._stop.set()
        self._thread.join()
        with self._lock:
            if self._error is not None:
                raise self._error
            return self._context, self._lease_token, self._sequence

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                with self._lock:
                    context = self._context
                    sequence = self._sequence
                grant = self._workflow.acquire(
                    context,
                    owner_id=self._owner_id,
                    expected_sequence=sequence,
                    ttl_seconds=self._ttl_seconds,
                )
                renewed_context = context.for_run(
                    str(context.run_id),
                    execution_epoch=grant.execution_epoch,
                    fencing_generation=grant.fencing_generation,
                )
                with self._lock:
                    self._context = renewed_context
                    self._sequence = grant.sequence
                    self._lease_token = grant.token
            except Exception as exc:
                with self._lock:
                    self._error = exc
                self._stop.set()
                return


class DurableControlPlane:
    """Bind exact canonical requests to durable core services."""

    def __init__(
        self,
        store: ControlPlaneStore,
        runtime: SkillRuntime,
        *,
        owner_id: str = "proof-harness-control-plane",
        lease_ttl_seconds: int = 300,
        auto_start_workers: bool = True,
        cost_meter: Callable[[str, int, int, int], int] | None = None,
    ) -> None:
        if not owner_id:
            raise ValueError("owner_id is required")
        if lease_ttl_seconds < 1 or lease_ttl_seconds > 86_400:
            raise ValueError("lease_ttl_seconds is outside the safe range")
        self.store = store
        self.runtime = runtime
        self.workflow = WorkflowEngine(store)
        self.evidence = EvidenceService(store)
        # A process incarnation must never impersonate a crashed predecessor.
        # Recovery, rather than a same-owner lease renewal, increments epoch and
        # fence after the old lease expires.
        self.owner_id = f"{owner_id}:{uuid.uuid4()}"
        self.lease_ttl_seconds = lease_ttl_seconds
        self.auto_start_workers = auto_start_workers
        self._cost_meter = cost_meter
        self._workers: dict[str, threading.Thread] = {}
        self._workers_lock = threading.Lock()
        self._stopping = threading.Event()

    def ready(self) -> tuple[bool, str]:
        try:
            storage = self.store.readiness()
            if not storage.ready:
                return False, storage.reason
            runtime_ready, reason = self.runtime.readiness()
            if not runtime_ready:
                return False, reason
            if not callable(
                getattr(self.store, "list_pending_control_plane_receipts", None)
            ):
                return False, "durable pending-invocation reconciliation is unavailable"
            return (
                True,
                f"{storage.backend} store, workflow, evidence, and Skill runtime are ready",
            )
        except Exception:
            return False, "durable control-plane readiness check failed"

    def register_scope(self, principal: AuthenticatedPrincipal) -> SecurityContext:
        context = SecurityContext(
            tenant_id=principal.tenant_id,
            project_id=principal.project_id,
            actor_id=principal.actor_id,
            execution_epoch=principal.execution_epoch,
            fencing_generation=principal.fencing_generation,
            authority_revision=principal.authority_revision,
        )
        self.store.register_scope(context)
        return context

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop admission workers before their durable store is closed."""

        self._stopping.set()
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            with self._workers_lock:
                workers = tuple(self._workers.values())
            if not workers:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            for worker in workers:
                worker.join(min(remaining, 0.1))

    def wait_for_run(self, run_id: str, timeout: float = 10.0) -> bool:
        """Wait for one local worker; intended for shutdown and bounded tests."""

        with self._workers_lock:
            worker = self._workers.get(run_id)
        if worker is None:
            return True
        worker.join(max(0.0, timeout))
        return not worker.is_alive()

    def invoke(
        self,
        principal: AuthenticatedPrincipal,
        request: Mapping[str, Any],
        *,
        input_bytes: int,
    ) -> InvocationOutcome:
        """Durably admit an invocation and return before Skill execution.

        The admission transaction chain ends in a byte-bound CHECKPOINTED
        state.  The asynchronous worker therefore always has a recovery point;
        a crash cannot turn an acknowledged request into an in-memory-only job.
        """

        self._validate_invoke_binding(principal, request)
        context = self.register_scope(principal)
        request_digest = digest_object(
            {
                "authenticated_scope": {
                    "tenant_id": principal.tenant_id,
                    "project_id": principal.project_id,
                    "actor_id": principal.actor_id,
                    "authentication_context_digest": (
                        principal.authentication_context_digest
                    ),
                    "authority_revision": principal.authority_revision,
                    "environment_revision": principal.environment_revision,
                    "execution_epoch": principal.execution_epoch,
                    "fencing_generation": principal.fencing_generation,
                },
                "request": request,
            },
            domain="v3-authenticated-invocation-request",
        )
        run_id = "run-" + request_digest.removeprefix("sha256:")
        idempotency_key = str(request["idempotencyKey"])
        job = _job_record(principal, request, request_digest, input_bytes)
        claimed, receipt = self._claim(
            context,
            operation="invoke",
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            run_id=run_id,
            request=job,
        )
        if not claimed:
            snapshot = self.store.get_run(context, receipt.run_id)
            if RunState(snapshot.state) in TERMINAL_STATES:
                result = self._replay_result(context, snapshot)
                if receipt.response is None:
                    self._complete(
                        context,
                        operation="invoke",
                        idempotency_key=idempotency_key,
                        request_digest=request_digest,
                        response=result,
                    )
                return InvocationOutcome(result, snapshot, True, True)
            self._schedule_worker(receipt)
            return InvocationOutcome(
                _admission_envelope(receipt), snapshot, True, False
            )

        deadline = _parse_datetime(request.get("deadline"), field="deadline")
        run_created = False
        try:
            run = self.workflow.create(
                context,
                run_id=run_id,
                revision_set_id=str(request["revisionSet"]["revisionSetId"]),
                deadline_at=deadline,
                idempotency_key=idempotency_key,
            )
            run_created = True
            run_context = context.for_run(run_id)
            lease = self.workflow.acquire(
                run_context,
                owner_id=self.owner_id,
                expected_sequence=run.sequence,
                ttl_seconds=self.lease_ttl_seconds,
            )
            active_context = run_context.for_run(
                run_id,
                execution_epoch=lease.execution_epoch,
                fencing_generation=lease.fencing_generation,
            )
            run = self.workflow.transition(
                active_context,
                RunState.ADMITTED,
                expected_sequence=lease.sequence,
                lease_token=lease.token,
            )
            run = self.workflow.transition(
                active_context,
                RunState.PLANNING,
                expected_sequence=run.sequence,
                lease_token=lease.token,
            )
            run = self.workflow.transition(
                active_context,
                RunState.EXECUTING,
                expected_sequence=run.sequence,
                lease_token=lease.token,
            )
            checkpoint = self.workflow.checkpoint(
                active_context,
                canonical_json_bytes(job),
                expected_sequence=run.sequence,
                lease_token=lease.token,
                checkpoint_id="admission-" + request_digest.removeprefix("sha256:"),
            )
            snapshot = self.store.get_run(active_context, run_id)
            self._schedule_worker(
                receipt,
                _ActiveLease(active_context, lease.token, checkpoint.sequence),
            )
            return InvocationOutcome(
                _admission_envelope(receipt), snapshot, False, False
            )
        except Exception:
            # A failure before run creation has no durable state to recover, so
            # release only that incomplete claim. Once a run exists, preserve
            # the claim: a retry must inspect/recover the fenced workflow and
            # must never silently start a second worker.
            if not run_created:
                self._abandon_incomplete_claim(
                    context,
                    operation="invoke",
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                )
            raise

    def reconcile_scope(self, principal: AuthenticatedPrincipal) -> int:
        """Schedule incomplete jobs visible to one authenticated actor scope."""

        context = self.register_scope(principal)
        receipts = self.store.list_pending_control_plane_receipts(context, limit=100)
        scheduled = 0
        for receipt in receipts:
            if receipt.operation != "invoke":
                continue
            if self._schedule_worker(receipt):
                scheduled += 1
        return scheduled

    def _schedule_worker(
        self,
        receipt: ControlPlaneReceipt,
        lease: _ActiveLease | None = None,
    ) -> bool:
        if not self.auto_start_workers or self._stopping.is_set():
            return False
        with self._workers_lock:
            existing = self._workers.get(receipt.run_id)
            if existing is not None and existing.is_alive():
                return False
            worker = threading.Thread(
                target=self._worker_entry,
                args=(receipt, lease),
                name=f"proof-harness-worker-{receipt.run_id[-12:]}",
                daemon=True,
            )
            self._workers[receipt.run_id] = worker
            worker.start()
        return True

    def _worker_entry(
        self,
        receipt: ControlPlaneReceipt,
        lease: _ActiveLease | None,
    ) -> None:
        try:
            while not self._stopping.is_set():
                try:
                    if self._process_receipt(receipt, lease):
                        return
                    lease = None
                except ConflictError as exc:
                    if exc.code not in {
                        "LEASE_HELD",
                        "OPTIMISTIC_CONFLICT",
                        "LEASE_CONFLICT",
                        "STALE_EPOCH",
                        "STALE_FENCE",
                    }:
                        raise
                    lease = None
                except Exception:
                    # The run remains at its last byte-bound recovery
                    # checkpoint and the receipt remains incomplete.  A later
                    # authenticated scope reconciliation fences this worker and
                    # retries; never manufacture a terminal result in memory.
                    return
                # Another live incarnation retains the lease.  Re-read and
                # compete after a bounded interval; CAS remains authoritative.
                if self._stopping.wait(min(1.0, self.lease_ttl_seconds / 3)):
                    return
        finally:
            with self._workers_lock:
                current = self._workers.get(receipt.run_id)
                if current is threading.current_thread():
                    self._workers.pop(receipt.run_id, None)

    def _process_receipt(
        self,
        receipt: ControlPlaneReceipt,
        supplied_lease: _ActiveLease | None,
    ) -> bool:
        principal, request, input_bytes, request_digest = _parse_job_record(receipt)
        base_context = self.register_scope(principal)
        snapshot = self.store.get_run(base_context, receipt.run_id)
        if RunState(snapshot.state) in TERMINAL_STATES:
            result = self._replay_result(base_context, snapshot)
            if receipt.response is None:
                self._complete(
                    base_context,
                    operation="invoke",
                    idempotency_key=receipt.idempotency_key,
                    request_digest=request_digest,
                    response=result,
                )
            return True

        lease = self._obtain_worker_lease(
            base_context,
            snapshot,
            supplied_lease,
        )
        snapshot = self.store.get_run(lease.context, receipt.run_id)
        if snapshot.last_checkpoint_id is not None:
            _, checkpoint_payload = self.store.get_checkpoint(
                lease.context, snapshot.last_checkpoint_id
            )
            completed_result = _checkpoint_result(checkpoint_payload)
            if completed_result is not None:
                self._finalize_checkpointed_result(
                    base_context,
                    receipt,
                    request_digest,
                    lease,
                    completed_result,
                )
                return True

        now = datetime.now(UTC)
        if now >= principal.expires_at.astimezone(UTC):
            execution = SkillExecutionResult(
                str(request["skill"]),
                "FAILED",
                {},
                reason="execution authority expired before worker execution",
            )
            bounded = _BoundedExecution(execution, 0, 0, 0, True)
            self._commit_execution(
                principal,
                request,
                input_bytes,
                request_digest,
                receipt,
                lease,
                bounded,
            )
            return True

        lease = self._prepare_recoverable_execution(
            lease, canonical_json_bytes(_execution_checkpoint(receipt.request))
        )
        heartbeat = _LeaseHeartbeat(
            self.workflow,
            lease.context,
            owner_id=self.owner_id,
            sequence=lease.sequence,
            lease_token=lease.token,
            ttl_seconds=self.lease_ttl_seconds,
        )
        heartbeat.start()
        try:
            bounded = self._execute_bounded(
                principal,
                request,
                lease.context,
                input_bytes,
            )
        finally:
            context, token, sequence = heartbeat.stop()
        self._commit_execution(
            principal,
            request,
            input_bytes,
            request_digest,
            receipt,
            _ActiveLease(context, token, sequence),
            bounded,
        )
        return True

    def _obtain_worker_lease(
        self,
        base_context: SecurityContext,
        snapshot: RunSnapshotLike,
        supplied: _ActiveLease | None,
    ) -> _ActiveLease:
        if (
            supplied is not None
            and supplied.context.run_id == snapshot.run_id
            and supplied.context.execution_epoch == snapshot.execution_epoch
            and supplied.context.fencing_generation == snapshot.fencing_generation
            and supplied.sequence == snapshot.sequence
        ):
            return supplied
        run_context = base_context.for_run(
            snapshot.run_id,
            execution_epoch=snapshot.execution_epoch,
            fencing_generation=snapshot.fencing_generation,
        )
        recoverable = snapshot.last_checkpoint_id is not None and snapshot.state in {
            RunState.CHECKPOINTED,
            RunState.BLOCKED,
            RunState.PAUSED,
            RunState.RESUMING,
            RunState.EXECUTING,
        }
        if recoverable:
            session = self.workflow.recover(
                run_context,
                owner_id=self.owner_id,
                expected_sequence=snapshot.sequence,
                ttl_seconds=self.lease_ttl_seconds,
            )
            return _ActiveLease(
                session.context,
                session.lease.token,
                session.lease.sequence,
            )
        grant = self.workflow.acquire(
            run_context,
            owner_id=self.owner_id,
            expected_sequence=snapshot.sequence,
            ttl_seconds=self.lease_ttl_seconds,
        )
        return _ActiveLease(
            run_context.for_run(
                snapshot.run_id,
                execution_epoch=grant.execution_epoch,
                fencing_generation=grant.fencing_generation,
            ),
            grant.token,
            grant.sequence,
        )

    def _prepare_recoverable_execution(
        self,
        lease: _ActiveLease,
        payload: bytes,
    ) -> _ActiveLease:
        snapshot = self.store.get_run(lease.context)
        state = RunState(snapshot.state)
        sequence = lease.sequence
        if state is RunState.CREATED:
            run = self.workflow.transition(
                lease.context,
                RunState.ADMITTED,
                expected_sequence=sequence,
                lease_token=lease.token,
            )
            state, sequence = run.state, run.sequence
        if state is RunState.ADMITTED:
            run = self.workflow.transition(
                lease.context,
                RunState.PLANNING,
                expected_sequence=sequence,
                lease_token=lease.token,
            )
            state, sequence = run.state, run.sequence
        if state in {RunState.PLANNING, RunState.RESUMING, RunState.CHECKPOINTED}:
            run = self.workflow.transition(
                lease.context,
                RunState.EXECUTING,
                expected_sequence=sequence,
                lease_token=lease.token,
            )
            sequence = run.sequence
        checkpoint = self.workflow.checkpoint(
            lease.context,
            payload,
            expected_sequence=sequence,
            lease_token=lease.token,
            checkpoint_id=(
                f"execution-start-{lease.context.run_id}-"
                f"{lease.context.execution_epoch}-{lease.context.fencing_generation}"
            ),
        )
        return _ActiveLease(lease.context, lease.token, checkpoint.sequence)

    def _execute_bounded(
        self,
        principal: AuthenticatedPrincipal,
        request: Mapping[str, Any],
        active_context: SecurityContext,
        input_bytes: int,
    ) -> _BoundedExecution:
        limits = request.get("limits")
        limit_map = limits if isinstance(limits, Mapping) else {}
        configured_wall_clock = limit_map.get("wallClockSeconds")
        wall_clock = float(configured_wall_clock or 86_400)
        deadline = _parse_datetime(request.get("deadline"), field="deadline")
        if deadline is not None:
            wall_clock = min(
                wall_clock,
                max(0.0, (deadline - datetime.now(UTC)).total_seconds()),
            )
        maximum_cost = limit_map.get("maxCostMicrounits")
        maximum_output = limit_map.get("maxOutputBytes")
        if isinstance(maximum_cost, int):
            estimate = self.runtime.estimate_cost_microunits(
                str(request["skill"]),
                input_bytes=input_bytes,
                max_output_bytes=(
                    maximum_output if isinstance(maximum_output, int) else None
                ),
                wall_clock_milliseconds=(
                    int(float(configured_wall_clock) * 1000)
                    if isinstance(configured_wall_clock, (int, float))
                    else None
                ),
            )
            if estimate is None:
                return _BoundedExecution(
                    SkillExecutionResult(
                        str(request["skill"]),
                        "NOT_RUN",
                        {},
                        reason=(
                            "BUDGET_UNAVAILABLE: maxCostMicrounits requires bounded "
                            "wallClockSeconds and maxOutputBytes"
                        ),
                    ),
                    0,
                    0,
                    0,
                )
            if estimate > maximum_cost:
                return _BoundedExecution(
                    SkillExecutionResult(
                        str(request["skill"]),
                        "NOT_RUN",
                        {},
                        reason="BUDGET_EXCEEDED: conservative cost bound exceeds limit",
                    ),
                    0,
                    0,
                    0,
                )
        started = time.monotonic()
        strict_timeout = configured_wall_clock is not None or deadline is not None
        if _effect_requested(request) or not strict_timeout:
            execution = self._execute_skill(principal, request, active_context)
            timed_out = False
        else:
            process_context = multiprocessing.get_context("spawn")
            receive, send = process_context.Pipe(duplex=False)
            process = process_context.Process(
                target=_isolated_skill_execute,
                args=(
                    send,
                    str(request["skill"]),
                    dict(request["input"]),
                    _runtime_context(principal, active_context),
                    tuple(
                        str(root) for root in self.runtime.dependencies.workspace_roots
                    ),
                ),
                name=f"proof-harness-isolated-{active_context.run_id}",
                daemon=True,
            )
            process.start()
            send.close()
            try:
                if not receive.poll(wall_clock):
                    _terminate_process(process)
                    raise TimeoutError
                maximum_transfer = min(
                    16 * 1024 * 1024,
                    (
                        maximum_output + 64 * 1024
                        if isinstance(maximum_output, int)
                        else 16 * 1024 * 1024
                    ),
                )
                raw_result = receive.recv_bytes(maxlength=max(64 * 1024, maximum_transfer))
                execution = _skill_result_from_bytes(raw_result, str(request["skill"]))
                process.join(1.0)
                if process.is_alive():
                    _terminate_process(process)
                timed_out = False
            except (EOFError, OSError):
                _terminate_process(process)
                channel_timed_out = time.monotonic() - started >= wall_clock
                execution = SkillExecutionResult(
                    str(request["skill"]),
                    "FAILED",
                    {},
                    reason=(
                        "Skill execution exceeded limits.wallClockSeconds"
                        if channel_timed_out
                        else "isolated Skill output exceeded its bounded channel"
                    ),
                )
                timed_out = channel_timed_out
            except TimeoutError:
                execution = SkillExecutionResult(
                    str(request["skill"]),
                    "FAILED",
                    {},
                    reason="Skill execution exceeded limits.wallClockSeconds",
                )
                timed_out = True
            finally:
                receive.close()
        if strict_timeout and wall_clock <= 0:
            execution = SkillExecutionResult(
                str(request["skill"]),
                "FAILED",
                {},
                reason="Skill execution exceeded limits.wallClockSeconds",
            )
            timed_out = True
        elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
        output_bytes = len(canonical_json_bytes(dict(execution.output)))
        if isinstance(maximum_output, int) and output_bytes > maximum_output:
            execution = SkillExecutionResult(
                str(request["skill"]),
                "FAILED",
                {},
                reason="Skill execution exceeded limits.maxOutputBytes",
            )
            output_bytes = 0
        try:
            if self._cost_meter is None:
                cost = self.runtime.actual_cost_microunits(
                    str(request["skill"]),
                    input_bytes=input_bytes,
                    output_bytes=output_bytes,
                    wall_clock_milliseconds=elapsed_ms,
                )
            else:
                cost = self._cost_meter(
                    str(request["skill"]), input_bytes, output_bytes, elapsed_ms
                )
        except Exception:
            cost = -1
        if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
            execution = SkillExecutionResult(
                str(request["skill"]),
                "FAILED",
                {},
                reason="trusted execution cost meter failed",
            )
            cost = 0
            output_bytes = 0
        if isinstance(maximum_cost, int) and cost > maximum_cost:
            execution = SkillExecutionResult(
                str(request["skill"]),
                "FAILED",
                {},
                reason="Skill execution exceeded limits.maxCostMicrounits",
            )
            output_bytes = 0
        return _BoundedExecution(
            execution,
            elapsed_ms,
            output_bytes,
            cost,
            timed_out,
        )

    def _commit_execution(
        self,
        principal: AuthenticatedPrincipal,
        request: Mapping[str, Any],
        input_bytes: int,
        request_digest: str,
        receipt: ControlPlaneReceipt,
        lease: _ActiveLease,
        bounded: _BoundedExecution,
    ) -> None:
        execution = bounded.result
        raw_execution = canonical_json_bytes(execution.to_dict())
        subject_revision = str(request["revisionSet"]["source"])
        evidence_id = "ev-" + digest_object(
            {
                "run_id": receipt.run_id,
                "request_digest": request_digest,
                "execution_digest": digest_bytes(
                    raw_execution, domain="skill-execution"
                ),
            },
            domain="execution-evidence-id",
        ).removeprefix("sha256:")
        record = self.evidence.record_bytes(
            lease.context,
            subject_revision=subject_revision,
            kind="skill-execution-result",
            evidence_class="operational",
            scope=str(request["skill"]),
            content=raw_execution,
            media_type="application/vnd.elmos.skill-execution+json",
            producer=EvidenceProducer(
                execution_id=receipt.run_id,
                source="ENGINE",
                tool_name="elmos-proof-driven-harness-engine",
                tool_digest=CONTROL_PLANE_TOOL_DIGEST,
                environment_revision=principal.environment_revision,
                independent=False,
            ),
            evidence_id=evidence_id,
            artifact_id="artifact-" + evidence_id.removeprefix("ev-"),
            idempotency_key=(
                receipt.idempotency_key
                + ":execution-evidence:"
                + digest_bytes(raw_execution, domain="skill-execution").removeprefix(
                    "sha256:"
                )
            ),
        )
        self.evidence.verify(lease.context, record.evidence_id)
        result = _result_envelope(
            request,
            execution,
            subject_revision=subject_revision,
            evidence_ids=(record.evidence_id,),
            wall_clock_ms=bounded.elapsed_ms,
            input_bytes=input_bytes,
            output_bytes=bounded.output_bytes,
            cost_microunits=bounded.cost_microunits,
            cache_hit=False,
        )
        checkpoint = self.workflow.checkpoint(
            lease.context,
            canonical_json_bytes(result),
            expected_sequence=lease.sequence,
            lease_token=lease.token,
            checkpoint_id="result-" + request_digest.removeprefix("sha256:"),
        )
        terminal = (
            RunState.TIMED_OUT
            if bounded.timed_out
            else _terminal_state_for_result(str(result["status"]))
        )
        self._transition_checkpoint_to_terminal(
            lease.context,
            lease.token,
            checkpoint.sequence,
            terminal,
        )
        self._complete(
            SecurityContext(
                tenant_id=principal.tenant_id,
                project_id=principal.project_id,
                actor_id=principal.actor_id,
                execution_epoch=principal.execution_epoch,
                fencing_generation=principal.fencing_generation,
                authority_revision=principal.authority_revision,
            ),
            operation="invoke",
            idempotency_key=receipt.idempotency_key,
            request_digest=request_digest,
            response=result,
        )

    def _finalize_checkpointed_result(
        self,
        base_context: SecurityContext,
        receipt: ControlPlaneReceipt,
        request_digest: str,
        lease: _ActiveLease,
        result: Mapping[str, Any],
    ) -> None:
        terminal = _terminal_state_for_result(str(result["status"]))
        self._transition_checkpoint_to_terminal(
            lease.context,
            lease.token,
            lease.sequence,
            terminal,
        )
        self._complete(
            base_context,
            operation="invoke",
            idempotency_key=receipt.idempotency_key,
            request_digest=request_digest,
            response=result,
        )

    def _transition_checkpoint_to_terminal(
        self,
        context: SecurityContext,
        lease_token: str,
        sequence: int,
        terminal: RunState,
    ) -> None:
        if terminal is RunState.TIMED_OUT:
            self.workflow.transition(
                context,
                RunState.TIMED_OUT,
                expected_sequence=sequence,
                lease_token=lease_token,
            )
            return
        run = self.workflow.transition(
            context,
            RunState.EXECUTING,
            expected_sequence=sequence,
            lease_token=lease_token,
        )
        run = self.workflow.transition(
            context,
            RunState.VERIFYING,
            expected_sequence=run.sequence,
            lease_token=lease_token,
        )
        if terminal is RunState.COMPLETED:
            run = self.workflow.transition(
                context,
                RunState.CERTIFYING,
                expected_sequence=run.sequence,
                lease_token=lease_token,
            )
        self.workflow.transition(
            context,
            terminal,
            expected_sequence=run.sequence,
            lease_token=lease_token,
        )

    def _execute_skill(
        self,
        principal: AuthenticatedPrincipal,
        request: Mapping[str, Any],
        active_context: SecurityContext,
    ) -> SkillExecutionResult:
        payload = request["input"]
        if not isinstance(payload, Mapping):
            return SkillExecutionResult(
                str(request["skill"]),
                "FAILED",
                {},
                reason="invocation input is not an object",
            )
        if _effect_requested(request):
            return SkillExecutionResult(
                str(request["skill"]),
                "BLOCKED",
                {
                    "external_effect": "NOT_RUN",
                    "durable_effect_journal": "NOT_CONFIGURED",
                },
                reason=(
                    "effectful execution is disabled until the provider or "
                    "workspace operation is bound to the durable effect journal"
                ),
            )
        try:
            return self.runtime.execute(
                str(request["skill"]),
                payload,
                context=_runtime_context(principal, active_context),
            )
        except PermissionError as exc:
            return SkillExecutionResult(
                str(request["skill"]), "BLOCKED", {}, reason=str(exc)
            )
        except (KeyError, TypeError, ValueError) as exc:
            return SkillExecutionResult(
                str(request["skill"]), "FAILED", {}, reason=str(exc)
            )
        except Exception:
            return SkillExecutionResult(
                str(request["skill"]),
                "FAILED",
                {},
                reason="Skill execution failed without a trustworthy result",
            )

    def _replay_result(
        self, context: SecurityContext, snapshot: RunSnapshotLike
    ) -> Mapping[str, Any]:
        if RunState(snapshot.state) not in TERMINAL_STATES:
            raise ConflictError(
                "invocation is not terminal and cannot be replayed",
                code="INVOCATION_IN_PROGRESS",
                details={"run_id": snapshot.run_id, "state": snapshot.state},
            )
        if snapshot.last_checkpoint_id is None:
            raise ConflictError(
                "terminal invocation has no replay checkpoint",
                code="REPLAY_CHECKPOINT_MISSING",
            )
        _, payload = self.store.get_checkpoint(context, snapshot.last_checkpoint_id)
        try:
            result = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ConflictError(
                "replay checkpoint is not valid JSON", code="REPLAY_CHECKPOINT_INVALID"
            ) from exc
        if not isinstance(result, dict):
            raise ConflictError(
                "replay checkpoint is not a result object",
                code="REPLAY_CHECKPOINT_INVALID",
            )
        metrics = result.get("metrics")
        if not isinstance(metrics, dict):
            raise ConflictError(
                "replay checkpoint has no metrics", code="REPLAY_CHECKPOINT_INVALID"
            )
        result = dict(result)
        result["metrics"] = {**metrics, "cacheHit": True}
        return result

    def get_run(
        self, principal: AuthenticatedPrincipal, run_id: str
    ) -> Mapping[str, Any]:
        context = self.register_scope(principal)
        return _run_envelope(self.store.get_run(context, run_id))

    def cancel(
        self,
        principal: AuthenticatedPrincipal,
        run_id: str,
        *,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> CancelOutcome:
        if "proof-harness.cancel" not in principal.authority:
            raise ValidationError(
                "proof-harness.cancel authority is required",
                code="AUTHORITY_DENIED",
            )
        context = self.register_scope(principal)
        request = {
            "runId": run_id,
            "expectedVersion": expected_version,
            "reason": reason,
            "identity": {
                "tenantId": principal.tenant_id,
                "projectId": principal.project_id,
                "actorId": principal.actor_id,
            },
        }
        request_digest = digest_object(request, domain="cancel-run-request")
        exists, stored = self._lookup_receipt(
            context,
            operation="cancel",
            idempotency_key=idempotency_key,
            request_digest=request_digest,
        )
        if exists:
            if stored is None:
                raise ConflictError(
                    "cancellation is still in progress", code="CANCEL_IN_PROGRESS"
                )
            return CancelOutcome(stored, True)
        snapshot = self.store.get_run(context, run_id)
        if snapshot.sequence != expected_version:
            raise ConflictError(
                "run version is stale",
                code="OPTIMISTIC_CONFLICT",
                details={"expected": expected_version, "actual": snapshot.sequence},
            )
        if RunState(snapshot.state) in TERMINAL_STATES:
            raise ConflictError(
                "terminal run cannot be cancelled",
                code="RUN_TERMINAL",
                details={"state": snapshot.state},
            )
        claimed, _ = self._claim(
            context,
            operation="cancel",
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            run_id=run_id,
            request=request,
        )
        if not claimed:
            stored = self._receipt_response(
                context, "cancel", idempotency_key, request_digest
            )
            if stored is None:
                raise ConflictError(
                    "cancellation is still in progress", code="CANCEL_IN_PROGRESS"
                )
            return CancelOutcome(stored, True)
        run_context = context.for_run(
            run_id,
            execution_epoch=snapshot.execution_epoch,
            fencing_generation=snapshot.fencing_generation,
        )
        lease = self.workflow.acquire(
            run_context,
            owner_id=self.owner_id,
            expected_sequence=snapshot.sequence,
            ttl_seconds=self.lease_ttl_seconds,
        )
        active_context = run_context.for_run(
            run_id,
            execution_epoch=lease.execution_epoch,
            fencing_generation=lease.fencing_generation,
        )
        self.workflow.cancel(
            active_context,
            expected_sequence=lease.sequence,
            lease_token=lease.token,
        )
        envelope = _run_envelope(self.store.get_run(active_context, run_id))
        self._complete(
            context,
            operation="cancel",
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            response=envelope,
        )
        return CancelOutcome(envelope, False)

    @staticmethod
    def _validate_invoke_binding(
        principal: AuthenticatedPrincipal,
        request: Mapping[str, Any],
    ) -> None:
        if "proof-harness.invoke" not in principal.authority:
            raise ValidationError(
                "proof-harness.invoke authority is required",
                code="AUTHORITY_DENIED",
            )
        if datetime.now(UTC) >= principal.expires_at.astimezone(UTC):
            raise ValidationError(
                "execution authority has expired",
                code="AUTHORITY_EXPIRED",
            )
        identity = request.get("identity")
        expected_identity = {
            "tenantId": principal.tenant_id,
            "projectId": principal.project_id,
            "actorId": principal.actor_id,
            "authenticationContextDigest": principal.authentication_context_digest,
        }
        if not isinstance(identity, Mapping) or dict(identity) != expected_identity:
            raise ValidationError(
                "identity must exactly match the authenticated principal",
                code="IDENTITY_MISMATCH",
            )
        authority = request.get("authority")
        if not isinstance(authority, Mapping):
            raise ValidationError("authority must be an object")
        expected_authority = {
            "authorityId": principal.authority_id,
            "revision": principal.authority_revision,
            "environmentId": principal.environment_id,
            "executionEpoch": principal.execution_epoch,
            "fencingGeneration": principal.fencing_generation,
        }
        for name, expected in expected_authority.items():
            if authority.get(name) != expected:
                code = (
                    "STALE_EPOCH"
                    if name == "executionEpoch"
                    else "STALE_FENCE"
                    if name == "fencingGeneration"
                    else "AUTHORITY_MISMATCH"
                )
                raise ValidationError(
                    f"authority.{name} is not server-bound",
                    code=code,
                )
        expires_at = _parse_datetime(authority.get("expiresAt"), field="authority.expiresAt")
        if expires_at != principal.expires_at.astimezone(UTC):
            raise ValidationError(
                "authority expiry is not server-bound",
                code="AUTHORITY_MISMATCH",
            )
        revision_set = request.get("revisionSet")
        if (
            not isinstance(revision_set, Mapping)
            or revision_set.get("environment") != principal.environment_revision
        ):
            raise ValidationError(
                "revisionSet.environment is not server-bound",
                code="ENVIRONMENT_MISMATCH",
            )

    def get_evidence_metadata(
        self, principal: AuthenticatedPrincipal, evidence_id: str
    ) -> Mapping[str, Any]:
        context = self.register_scope(principal)
        record = self.evidence.verify(context, evidence_id)
        return {
            "evidenceId": record.evidence_id,
            "tenantId": record.tenant_id,
            "projectId": record.project_id,
            "subjectRevision": record.subject_revision,
            "kind": record.kind,
            "contentDigest": record.content.sha256,
            "size": record.content.byte_length,
            "mediaType": record.content.media_type,
            "producer": {
                "executionId": record.producer.execution_id,
                "source": record.producer.source,
                "toolDigest": record.producer.tool_digest,
            },
            "environmentDigest": record.producer.environment_revision,
            "createdAt": _format_datetime(record.created_at),
            "expiresAt": _format_datetime(record.expires_at)
            if record.expires_at
            else None,
            "lineage": list(record.lineage),
            "classification": "INTERNAL",
        }

    def _claim(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_digest: str,
        run_id: str,
        request: Mapping[str, Any],
    ) -> tuple[bool, ControlPlaneReceipt]:
        claimed, receipt = self.store.claim_control_plane_receipt(
            context,
            operation=operation,
            idempotency_key=idempotency_key,
            request_sha256=request_digest,
            run_id=run_id,
            request=request,
        )
        return claimed, receipt

    def _complete(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_digest: str,
        response: Mapping[str, Any],
    ) -> None:
        self.store.complete_control_plane_receipt(
            context,
            operation=operation,
            idempotency_key=idempotency_key,
            request_sha256=request_digest,
            response=response,
        )

    def _receipt_response(
        self,
        context: SecurityContext,
        operation: str,
        idempotency_key: str,
        request_digest: str,
    ) -> Mapping[str, Any] | None:
        receipt = self.store.get_control_plane_receipt(
            context,
            operation=operation,
            idempotency_key=idempotency_key,
            request_sha256=request_digest,
        )
        if receipt is None:
            raise NotFoundError("control-plane receipt was not found")
        return receipt.response

    def _lookup_receipt(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_digest: str,
    ) -> tuple[bool, Mapping[str, Any] | None]:
        receipt = self.store.get_control_plane_receipt(
            context,
            operation=operation,
            idempotency_key=idempotency_key,
            request_sha256=request_digest,
        )
        if receipt is None:
            return False, None
        if receipt.response is None:
            return True, None
        value = receipt.response
        if not isinstance(value, dict):
            raise ConflictError(
                "control-plane receipt is invalid",
                code="RECEIPT_INVALID",
            )
        return True, value

    def _abandon_incomplete_claim(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_digest: str,
    ) -> None:
        self.store.abandon_control_plane_receipt(
            context,
            operation=operation,
            idempotency_key=idempotency_key,
            request_sha256=request_digest,
        )


def _job_record(
    principal: AuthenticatedPrincipal,
    request: Mapping[str, Any],
    request_digest: str,
    input_bytes: int,
) -> dict[str, Any]:
    return {
        "checkpointKind": "ADMISSION",
        "requestDigest": request_digest,
        "inputBytes": input_bytes,
        "request": dict(request),
        "authenticatedPrincipal": {
            "tenantId": principal.tenant_id,
            "projectId": principal.project_id,
            "actorId": principal.actor_id,
            "authority": list(principal.authority),
            "authenticationContextDigest": principal.authentication_context_digest,
            "authorityId": principal.authority_id,
            "authorityRevision": principal.authority_revision,
            "environmentId": principal.environment_id,
            "environmentRevision": principal.environment_revision,
            "executionEpoch": principal.execution_epoch,
            "fencingGeneration": principal.fencing_generation,
            "expiresAt": _format_datetime(principal.expires_at),
        },
    }


def _effect_requested(request: Mapping[str, Any]) -> bool:
    payload = request.get("input")
    if not isinstance(payload, Mapping):
        return False
    return (
        str(request.get("skill")) == "elmos-transformation-kernel"
        and payload.get("apply") is True
    ) or (
        str(request.get("skill")) == "elmos-harness-runtime-kernel"
        and payload.get("execute") is True
    )


def _runtime_context(
    principal: AuthenticatedPrincipal,
    active_context: SecurityContext,
) -> dict[str, Any]:
    safe_authority = tuple(
        capability
        for capability in principal.authority
        if capability not in {"workspace.write", "adapter.execute"}
    )
    return {
        "tenant_id": principal.tenant_id,
        "project_id": principal.project_id,
        "actor_id": principal.actor_id,
        "run_id": active_context.run_id,
        "execution_epoch": active_context.execution_epoch,
        "fencing_generation": active_context.fencing_generation,
        "authority": list(safe_authority),
        "authority_revision": principal.authority_revision,
        "environment_id": principal.environment_id,
        "environment_revision": principal.environment_revision,
    }


def _terminate_process(process: multiprocessing.Process) -> None:
    if not process.is_alive():
        process.join(0.1)
        return
    process.terminate()
    process.join(1.0)
    if process.is_alive():
        process.kill()
        process.join(1.0)


def _skill_result_from_bytes(payload: bytes, expected_skill: str) -> SkillExecutionResult:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("isolated Skill result is invalid JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "skill",
        "status",
        "output",
        "evidence_refs",
        "reason",
        "certified",
    }:
        raise ValueError("isolated Skill result shape is invalid")
    if value["skill"] != expected_skill or not isinstance(value["output"], dict):
        raise ValueError("isolated Skill result binding is invalid")
    if not isinstance(value["evidence_refs"], list) or any(
        not isinstance(item, str) for item in value["evidence_refs"]
    ):
        raise ValueError("isolated Skill evidence references are invalid")
    if (
        not isinstance(value["status"], str)
        or not isinstance(value["reason"], str)
        or not isinstance(value["certified"], bool)
    ):
        raise ValueError("isolated Skill result fields are invalid")
    return SkillExecutionResult(
        expected_skill,
        value["status"],
        value["output"],
        tuple(value["evidence_refs"]),
        value["reason"],
        value["certified"],
    )


def _execution_checkpoint(job: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(job)
    value["checkpointKind"] = "EXECUTION_READY"
    return value


def _parse_job_record(
    receipt: ControlPlaneReceipt,
) -> tuple[_PersistedPrincipal, Mapping[str, Any], int, str]:
    job = receipt.request
    if set(job) != {
        "checkpointKind",
        "requestDigest",
        "inputBytes",
        "request",
        "authenticatedPrincipal",
    }:
        raise ConflictError("admission job is malformed", code="ADMISSION_INVALID")
    if job.get("checkpointKind") not in {"ADMISSION", "EXECUTION_READY"}:
        raise ConflictError("admission checkpoint kind is invalid", code="ADMISSION_INVALID")
    request = job.get("request")
    trusted = job.get("authenticatedPrincipal")
    input_bytes = job.get("inputBytes")
    request_digest = job.get("requestDigest")
    if not isinstance(request, Mapping) or not isinstance(trusted, Mapping):
        raise ConflictError("admission job payload is invalid", code="ADMISSION_INVALID")
    if not isinstance(input_bytes, int) or isinstance(input_bytes, bool) or input_bytes < 0:
        raise ConflictError("admission input size is invalid", code="ADMISSION_INVALID")
    if not isinstance(request_digest, str) or request_digest != receipt.request_sha256:
        raise ConflictError("admission digest binding is invalid", code="ADMISSION_INVALID")
    required = {
        "tenantId",
        "projectId",
        "actorId",
        "authority",
        "authenticationContextDigest",
        "authorityId",
        "authorityRevision",
        "environmentId",
        "environmentRevision",
        "executionEpoch",
        "fencingGeneration",
        "expiresAt",
    }
    if set(trusted) != required:
        raise ConflictError("persisted principal is malformed", code="ADMISSION_INVALID")
    authority = trusted["authority"]
    if not isinstance(authority, list) or any(
        not isinstance(item, str) or not item for item in authority
    ):
        raise ConflictError("persisted authority is malformed", code="ADMISSION_INVALID")
    principal = _PersistedPrincipal(
        tenant_id=str(trusted["tenantId"]),
        project_id=str(trusted["projectId"]),
        actor_id=str(trusted["actorId"]),
        authority=tuple(authority),
        authentication_context_digest=str(trusted["authenticationContextDigest"]),
        authority_id=str(trusted["authorityId"]),
        authority_revision=str(trusted["authorityRevision"]),
        environment_id=str(trusted["environmentId"]),
        environment_revision=str(trusted["environmentRevision"]),
        execution_epoch=int(trusted["executionEpoch"]),
        fencing_generation=int(trusted["fencingGeneration"]),
        expires_at=_parse_datetime(trusted["expiresAt"], field="principal.expiresAt")
        or datetime.min.replace(tzinfo=UTC),
    )
    if principal.actor_id != receipt.actor_id:
        raise ConflictError("persisted principal scope is invalid", code="ADMISSION_INVALID")
    return principal, request, input_bytes, request_digest


def _admission_envelope(receipt: ControlPlaneReceipt) -> dict[str, Any]:
    _, request, _, request_digest = _parse_job_record(receipt)
    return {
        "apiVersion": "elmos.ai/proof-harness/v3",
        "requestId": str(request["requestId"]),
        "skill": str(request["skill"]),
        "runId": receipt.run_id,
        "status": "ADMITTED",
        "resultAvailable": False,
        "requestDigest": request_digest,
        "acceptedAt": _format_datetime(receipt.created_at),
    }


def _checkpoint_result(payload: bytes) -> Mapping[str, Any] | None:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("apiVersion") != "elmos.ai/proof-harness/v3":
        return None
    if value.get("status") not in {
        "SUCCEEDED",
        "PARTIAL",
        "BLOCKED",
        "FAILED",
        "CANCELLED",
        "UNSUPPORTED",
    }:
        return None
    return value


def _result_envelope(
    request: Mapping[str, Any],
    execution: SkillExecutionResult,
    *,
    subject_revision: str,
    evidence_ids: tuple[str, ...],
    wall_clock_ms: int,
    input_bytes: int,
    output_bytes: int,
    cost_microunits: int,
    cache_hit: bool,
) -> dict[str, Any]:
    status = _public_result_status(execution.status)
    error_items: list[dict[str, Any]] = []
    if execution.reason and status != "SUCCEEDED":
        error_items.append(
            {
                "code": "LOCAL_EXECUTION_" + status,
                "message": execution.reason[:4096],
                "retryable": False,
                "provenance": {"source": "local-skill-runtime"},
            }
        )
    return {
        "apiVersion": "elmos.ai/proof-harness/v3",
        "requestId": str(request["requestId"]),
        "skill": str(request["skill"]),
        "status": status,
        "subjectRevision": subject_revision,
        "output": dict(execution.output),
        "evidenceIds": list(evidence_ids),
        "runtimeEvidence": (
            "FAILED"
            if status == "FAILED"
            else "BLOCKED"
            if status == "BLOCKED"
            else "NOT_RUN"
            if status == "UNSUPPORTED"
            else "LOCAL_EXECUTED_SELF_ATTESTED"
        ),
        "externalEvidence": "NOT_RUN",
        "certification": (
            "BLOCKED"
            if status == "BLOCKED"
            else "REJECTED"
            if status == "FAILED"
            else "NOT_CERTIFIED"
        ),
        "metrics": {
            "wallClockMilliseconds": wall_clock_ms,
            "inputBytes": input_bytes,
            "outputBytes": output_bytes,
            "cacheHit": cache_hit,
            "costMicrounits": cost_microunits,
        },
        "errors": error_items,
    }


def _public_result_status(status: str) -> str:
    if status in {"BLOCKED", "DENIED"}:
        return "BLOCKED"
    if status in {"FAILED", "NOT_RUN"}:
        return "FAILED"
    if status == "CANCELLED":
        return "CANCELLED"
    if status == "UNSUPPORTED":
        return "UNSUPPORTED"
    if status in {
        "PARTIAL",
        "PLANNED",
        "DRY_RUN",
        "READY_FOR_EXTERNAL_GATE",
        "READY_FOR_HUMAN_DECISION",
        "LOCAL_INPUT_VALIDATED",
    }:
        return "PARTIAL"
    return "SUCCEEDED"


def _terminal_state_for_result(status: str) -> RunState:
    if status == "SUCCEEDED":
        return RunState.COMPLETED
    if status == "FAILED":
        return RunState.FAILED
    if status == "CANCELLED":
        return RunState.CANCELLED
    # BLOCKED is a recoverable workflow state, but a synchronous API result
    # must have a stable replay checkpoint. PARTIAL preserves the blocking
    # result without falsely claiming completion.
    return RunState.PARTIAL


def _run_envelope(snapshot: RunSnapshotLike) -> dict[str, Any]:
    return {
        "runId": snapshot.run_id,
        "state": snapshot.state,
        "version": max(1, snapshot.sequence),
        "executionEpoch": snapshot.execution_epoch,
        "fencingGeneration": snapshot.fencing_generation,
        "updatedAt": _format_datetime(snapshot.updated_at),
    }


def _parse_datetime(value: Any, *, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be an RFC 3339 date-time")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} must be an RFC 3339 date-time") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValidationError(f"{field} must include a timezone")
    return result.astimezone(UTC)


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


__all__ = [
    "CONTROL_PLANE_TOOL_DIGEST",
    "CancelOutcome",
    "DurableControlPlane",
    "InvocationOutcome",
]
