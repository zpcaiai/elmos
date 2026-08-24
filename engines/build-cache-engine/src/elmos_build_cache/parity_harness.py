"""Executable, evidence-bound harness for the cache-parity scenario corpus.

The harness deliberately accepts Python callables rather than command strings;
repository content therefore cannot choose a shell command to execute. Each
callable runs behind a disposable process boundary. The parent owns the hard
monotonic deadline and kills/reaps an executor that ignores its cooperative
deadline. Platforms that cannot create a reclaimable process, or cannot
transport the configured callable to one, fail closed without invoking it.

Raw evidence is written to the content-addressable store before it is
referenced.  The resulting report is produced exclusively by
``parity.evaluate_parity`` and can reach at most ``READY_FOR_EXTERNAL_GATE``.
Synthetic executors are explicitly labelled engineering evidence throughout
the CAS manifests and scenario details and are never described as external
evidence.
"""

from __future__ import annotations

import multiprocessing
import os
import pickle
import signal
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any, Protocol, cast

from .canonical import digest_of, require_digest
from .cas import ContentAddressableStore
from .errors import ContractViolation
from .parity import (
    MANDATORY_SCENARIOS,
    EvidenceBinding,
    ParityDecision,
    ParityReport,
    ParityThresholds,
    ScenarioResult,
    ScenarioStatus,
    evaluate_parity,
)
from .security import ProvenanceSigner, SignedStatement


class EvidenceClass(StrEnum):
    """Origin of local evidence; neither value means externally verified."""

    RUNTIME_ENGINEERING = "RUNTIME_ENGINEERING"
    SYNTHETIC_ENGINEERING = "SYNTHETIC_ENGINEERING"


@dataclass(frozen=True)
class RawEvidence:
    """One non-empty evidence payload supplied by an in-process executor."""

    role: str
    media_type: str
    content: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not self.role or not self.media_type:
            raise ContractViolation("raw evidence role and media type are required")
        if not isinstance(self.content, bytes) or not self.content:
            raise ContractViolation("raw evidence content must be non-empty bytes", role=self.role)


@dataclass(frozen=True)
class ReplayMetadata:
    """Opaque runner metadata, intentionally not an executable command."""

    replay_id: str
    runner: str
    runner_version: str
    request_digest: str
    attempt: int = 1

    def __post_init__(self) -> None:
        if not self.replay_id or not self.runner or not self.runner_version:
            raise ContractViolation("replay metadata is incomplete")
        require_digest(self.request_digest)
        if self.attempt < 1:
            raise ContractViolation("replay attempt must be positive", attempt=self.attempt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": "elmos.cache-parity-replay/v1.2",
            "replay_id": self.replay_id,
            "runner": self.runner,
            "runner_version": self.runner_version,
            "request_digest": self.request_digest,
            "attempt": self.attempt,
        }


@dataclass(frozen=True)
class ScenarioCase:
    """One immutable member of the exact parity corpus."""

    scenario_id: str
    input_digest: str
    timeout_seconds: float
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.scenario_id not in MANDATORY_SCENARIOS:
            raise ContractViolation("unknown parity scenario", scenario_id=self.scenario_id)
        require_digest(self.input_digest)
        if self.timeout_seconds <= 0.0:
            raise ContractViolation(
                "scenario timeout must be positive",
                scenario_id=self.scenario_id,
                timeout_seconds=self.timeout_seconds,
            )
        try:
            digest_of(dict(self.parameters))
        except (TypeError, ValueError) as exc:
            raise ContractViolation(
                "scenario parameters must be canonical",
                scenario_id=self.scenario_id,
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "input_digest": self.input_digest,
            "timeout_seconds": self.timeout_seconds,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True)
class ScenarioCorpus:
    """The complete, canonical-order 20-scenario corpus."""

    cases: tuple[ScenarioCase, ...]

    def __post_init__(self) -> None:
        scenario_ids = tuple(case.scenario_id for case in self.cases)
        if len(set(scenario_ids)) != len(scenario_ids):
            duplicates = sorted({item for item in scenario_ids if scenario_ids.count(item) > 1})
            raise ContractViolation("duplicate parity corpus scenarios", duplicates=duplicates)
        missing = sorted(set(MANDATORY_SCENARIOS) - set(scenario_ids))
        unexpected = sorted(set(scenario_ids) - set(MANDATORY_SCENARIOS))
        if len(self.cases) != len(MANDATORY_SCENARIOS) or missing or unexpected:
            raise ContractViolation(
                "parity corpus must contain exactly the 20 mandatory scenarios",
                expected=len(MANDATORY_SCENARIOS),
                actual=len(self.cases),
                missing=missing,
                unexpected=unexpected,
            )
        if scenario_ids != MANDATORY_SCENARIOS:
            raise ContractViolation("parity corpus must use canonical mandatory-scenario order")

    @classmethod
    def from_cases(cls, cases: Sequence[ScenarioCase]) -> ScenarioCorpus:
        return cls(tuple(cases))

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-scenario-corpus/v1.2",
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class ScenarioRequest:
    """Typed executor input.  ``deadline_monotonic`` is cooperative runtime state."""

    run_id: str
    case: ScenarioCase
    binding: EvidenceBinding
    measurement_bundle_digest: str
    deadline_monotonic: float

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ContractViolation("parity run_id is required")
        require_digest(self.measurement_bundle_digest)

    def statement(self) -> dict[str, Any]:
        # The monotonic deadline is process-local and intentionally excluded
        # from the replay identity.  The bounded duration remains in ``case``.
        return {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-scenario-request/v1.2",
            "run_id": self.run_id,
            "case": self.case.to_dict(),
            "binding": self.binding.to_dict(),
            "measurement_bundle_digest": self.measurement_bundle_digest,
        }

    @property
    def request_digest(self) -> str:
        return digest_of(self.statement())


@dataclass(frozen=True)
class ScenarioExecution:
    """Outcome returned by a scenario callable before CAS persistence."""

    status: ScenarioStatus
    raw_evidence: tuple[RawEvidence, ...] = ()
    replay: ReplayMetadata | None = None
    reason: str = ""
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        roles = tuple(item.role for item in self.raw_evidence)
        if len(set(roles)) != len(roles):
            raise ContractViolation("raw evidence roles must be unique", roles=roles)
        if self.status is ScenarioStatus.PASS:
            if not self.raw_evidence:
                raise ContractViolation("a passed execution requires non-empty raw evidence")
            if self.replay is None:
                raise ContractViolation("a passed execution requires replay metadata")
        elif not self.reason:
            raise ContractViolation("a non-pass execution requires a reason", status=str(self.status))
        try:
            digest_of(dict(self.detail))
        except (TypeError, ValueError) as exc:
            raise ContractViolation("scenario execution detail must be canonical") from exc


class ScenarioExecutor(Protocol):
    """Process-isolated execution boundary with a cooperative deadline hint."""

    @property
    def identity(self) -> str: ...

    @property
    def evidence_class(self) -> EvidenceClass: ...

    def __call__(self, request: ScenarioRequest) -> ScenarioExecution: ...


class _IsolationContext(Protocol):
    """Subset of multiprocessing contexts used by the hard-deadline boundary."""

    def Pipe(self, *, duplex: bool) -> tuple[Connection, Connection]: ...  # noqa: N802

    def Process(  # noqa: N802
        self,
        *,
        target: Callable[..., Any],
        args: tuple[Any, ...],
        name: str,
    ) -> BaseProcess: ...

    def get_start_method(self) -> str: ...


ScenarioCallable = Callable[[ScenarioRequest], ScenarioExecution]


@dataclass(frozen=True)
class CallableScenarioExecutor:
    """Explicit metadata wrapper for a plain Python callable."""

    identity: str
    evidence_class: EvidenceClass
    callback: ScenarioCallable = field(repr=False)

    def __post_init__(self) -> None:
        if not self.identity:
            raise ContractViolation("scenario executor identity is required")
        if not callable(self.callback):
            raise ContractViolation("scenario executor callback must be callable")

    def __call__(self, request: ScenarioRequest) -> ScenarioExecution:
        return self.callback(request)


@dataclass(frozen=True)
class _WorkerEnvelope:
    """Small typed result transported from the disposable worker."""

    kind: str
    completed_monotonic: float
    execution: ScenarioExecution | None = None
    exception_type: str | None = None
    exception_digest: str | None = None


def _scenario_worker(
    connection: Connection,
    executor: ScenarioExecutor,
    request: ScenarioRequest,
) -> None:
    """Execute one scenario in a fresh process and return a typed envelope."""

    if os.name == "posix":
        try:
            os.setsid()
        except OSError:
            # The parent still owns the direct process handle and can kill it.
            pass
    try:
        try:
            candidate = executor(request)
        except TimeoutError:
            envelope = _WorkerEnvelope("TIMEOUT", time.monotonic())
        except BaseException as exc:  # executor is the untrusted isolation boundary
            envelope = _WorkerEnvelope(
                "EXCEPTION",
                time.monotonic(),
                exception_type=type(exc).__name__,
                exception_digest=digest_of(str(exc)),
            )
        else:
            if isinstance(candidate, ScenarioExecution):
                envelope = _WorkerEnvelope(
                    "RESULT",
                    time.monotonic(),
                    execution=candidate,
                )
            else:
                envelope = _WorkerEnvelope("INVALID_RESULT", time.monotonic())
        try:
            connection.send(envelope)
        except BaseException as exc:
            # A result that cannot cross the isolation boundary cannot count as
            # execution evidence. This fallback contains no executor payload.
            fallback = _WorkerEnvelope(
                "TRANSPORT_ERROR",
                time.monotonic(),
                exception_type=type(exc).__name__,
                exception_digest=digest_of(str(exc)),
            )
            try:
                connection.send(fallback)
            except BaseException:
                return
    finally:
        connection.close()


def _isolation_context(
    executor: ScenarioExecutor,
    request: ScenarioRequest,
) -> tuple[_IsolationContext | None, str]:
    """Select a reclaimable stdlib process context or explain why none is safe."""

    methods = tuple(multiprocessing.get_all_start_methods())
    if "fork" in methods:
        # Fork transports configured callables without inventing a command
        # surface. The child immediately enters its own POSIX session.
        return cast(_IsolationContext, multiprocessing.get_context("fork")), ""
    for method in ("spawn", "forkserver"):
        if method not in methods:
            continue
        try:
            pickle.dumps((executor, request), protocol=pickle.HIGHEST_PROTOCOL)
        except (pickle.PickleError, TypeError, AttributeError) as exc:
            limitation = f"{method}:{type(exc).__name__}"
            continue
        return cast(_IsolationContext, multiprocessing.get_context(method)), ""
    if not methods:
        return None, "NO_MULTIPROCESSING_START_METHOD"
    return None, locals().get("limitation", "EXECUTOR_NOT_TRANSPORTABLE")


def _reclaim_process(process: BaseProcess) -> bool:
    """Kill the worker (and its POSIX process group) and reap it promptly."""

    if not process.is_alive():
        process.join(0)
        return True
    killed = False
    if os.name == "posix" and process.pid is not None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            killed = True
        except (OSError, ProcessLookupError):
            pass
    if not killed:
        try:
            process.kill()
        except (AttributeError, OSError):
            try:
                process.terminate()
            except OSError:
                pass
    process.join(0.25)
    if process.is_alive():
        try:
            process.terminate()
        except OSError:
            pass
        process.join(0.1)
    return not process.is_alive()


@dataclass(frozen=True)
class MeasurementBundle:
    """Measured global/cohort values with raw evidence and no default values."""

    measurement_id: str
    producer_identity: str
    evidence_class: EvidenceClass
    global_metrics: Mapping[str, float | int]
    cohorts: Mapping[str, Mapping[str, float | int]]
    raw_evidence: tuple[RawEvidence, ...]
    replay: ReplayMetadata

    def __post_init__(self) -> None:
        if not self.measurement_id or not self.producer_identity:
            raise ContractViolation("measurement identity and producer are required")
        if not self.raw_evidence:
            raise ContractViolation("measurement bundle requires non-empty raw evidence")
        roles = tuple(item.role for item in self.raw_evidence)
        if len(set(roles)) != len(roles):
            raise ContractViolation("measurement evidence roles must be unique", roles=roles)


@dataclass(frozen=True)
class ParityHarnessResult:
    """Report plus immutable local artifacts produced by one harness run."""

    report: ParityReport
    evidence_class: EvidenceClass
    measurement_manifest_digest: str
    scenario_manifest_digests: Mapping[str, str]
    report_artifact_digest: str
    signed_report: SignedStatement | None = None
    signature_artifact_digest: str | None = None

    def __post_init__(self) -> None:
        require_digest(self.measurement_manifest_digest)
        require_digest(self.report_artifact_digest)
        for scenario_id, digest in self.scenario_manifest_digests.items():
            if scenario_id not in MANDATORY_SCENARIOS:
                raise ContractViolation("unknown scenario manifest", scenario_id=scenario_id)
            require_digest(digest)
        if (self.signed_report is None) != (self.signature_artifact_digest is None):
            raise ContractViolation("signed report and signature artifact must be present together")
        if self.signature_artifact_digest is not None:
            require_digest(self.signature_artifact_digest)
        if self.report.decision not in {
            ParityDecision.NOT_RUN,
            ParityDecision.FAILED,
            ParityDecision.READY_FOR_EXTERNAL_GATE,
        }:
            raise ContractViolation("parity harness cannot emit a certification decision")

    @property
    def external_evidence_state(self) -> str:
        return "NOT_RUN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.to_dict(),
            "evidence_class": str(self.evidence_class),
            "measurement_manifest_digest": self.measurement_manifest_digest,
            "scenario_manifest_digests": dict(sorted(self.scenario_manifest_digests.items())),
            "report_artifact_digest": self.report_artifact_digest,
            "signed_report": self.signed_report.to_dict() if self.signed_report else None,
            "signature_artifact_digest": self.signature_artifact_digest,
            "external_evidence_state": self.external_evidence_state,
            "maximum_local_decision": str(ParityDecision.READY_FOR_EXTERNAL_GATE),
        }


class ParityScenarioHarness:
    """Run the exact corpus and persist every evidence relationship in CAS."""

    def __init__(
        self,
        *,
        cas: ContentAddressableStore,
        corpus: ScenarioCorpus,
        executors: Mapping[str, ScenarioExecutor],
    ) -> None:
        self.cas = cas
        self.corpus = corpus
        self.executors = dict(executors)
        keys = set(self.executors)
        expected = set(MANDATORY_SCENARIOS)
        if keys != expected:
            raise ContractViolation(
                "exactly one executor is required for every mandatory scenario",
                missing=sorted(expected - keys),
                unexpected=sorted(keys - expected),
            )
        for scenario_id, executor in self.executors.items():
            if not executor.identity or not callable(executor):
                raise ContractViolation("invalid scenario executor", scenario_id=scenario_id)

    def run(
        self,
        *,
        report_id: str,
        binding: EvidenceBinding,
        measurements: MeasurementBundle,
        thresholds: ParityThresholds | None = None,
        signer: ProvenanceSigner | None = None,
    ) -> ParityHarnessResult:
        if binding.corpus_digest != self.corpus.digest:
            raise ContractViolation(
                "evidence binding does not identify the exact scenario corpus",
                expected=self.corpus.digest,
                actual=binding.corpus_digest,
            )
        if measurements.producer_identity != binding.executor_identity:
            raise ContractViolation(
                "measurement producer does not match the bound executor",
                expected=binding.executor_identity,
                actual=measurements.producer_identity,
            )
        for scenario_id, executor in self.executors.items():
            if executor.identity != binding.executor_identity:
                raise ContractViolation(
                    "scenario executor does not match the evidence binding",
                    scenario_id=scenario_id,
                    expected=binding.executor_identity,
                    actual=executor.identity,
                )
            if executor.evidence_class is not measurements.evidence_class:
                raise ContractViolation(
                    "scenario and measurement evidence classes cannot be mixed",
                    scenario_id=scenario_id,
                    scenario_class=str(executor.evidence_class),
                    measurement_class=str(measurements.evidence_class),
                )

        measurement_digest = self._persist_measurements(binding, measurements)
        scenario_results: list[ScenarioResult] = []
        scenario_manifests: dict[str, str] = {}
        for case in self.corpus.cases:
            request = ScenarioRequest(
                run_id=report_id,
                case=case,
                binding=binding,
                measurement_bundle_digest=measurement_digest,
                deadline_monotonic=time.monotonic() + case.timeout_seconds,
            )
            execution = self._execute(self.executors[case.scenario_id], request)
            result, manifest_digest = self._persist_execution(
                request=request,
                executor=self.executors[case.scenario_id],
                execution=execution,
            )
            scenario_results.append(result)
            scenario_manifests[case.scenario_id] = manifest_digest

        report = evaluate_parity(
            report_id=report_id,
            metrics=measurements.global_metrics,
            cohorts=measurements.cohorts,
            scenarios=scenario_results,
            binding=binding,
            thresholds=thresholds,
        )
        report_envelope = {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-harness-report/v1.2",
            "report": report.to_dict(),
            "evidence_class": str(measurements.evidence_class),
            "measurement_manifest_digest": measurement_digest,
            "scenario_manifest_digests": dict(sorted(scenario_manifests.items())),
            "external_evidence_state": "NOT_RUN",
            "maximum_local_decision": str(ParityDecision.READY_FOR_EXTERNAL_GATE),
        }
        report_artifact_digest = self.cas.put_document(
            report_envelope,
            artifact_kind="cache-parity-harness-report",
        )

        signed_report: SignedStatement | None = None
        signature_digest: str | None = None
        if signer is not None:
            signed_report = report.sign(signer)
            signature_digest = self.cas.put_document(
                signed_report.to_dict(),
                artifact_kind="cache-parity-report-signature",
            )

        return ParityHarnessResult(
            report=report,
            evidence_class=measurements.evidence_class,
            measurement_manifest_digest=measurement_digest,
            scenario_manifest_digests=scenario_manifests,
            report_artifact_digest=report_artifact_digest,
            signed_report=signed_report,
            signature_artifact_digest=signature_digest,
        )

    def _persist_measurements(
        self,
        binding: EvidenceBinding,
        measurements: MeasurementBundle,
    ) -> str:
        evidence = self._persist_raw_evidence(measurements.raw_evidence, artifact_kind="parity-measurement")
        manifest = {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-measurement-bundle/v1.2",
            "measurement_id": measurements.measurement_id,
            "producer_identity": measurements.producer_identity,
            "evidence_class": str(measurements.evidence_class),
            "external_evidence_state": "NOT_RUN",
            "binding": binding.to_dict(),
            "global_metrics": dict(measurements.global_metrics),
            "cohorts": {name: dict(values) for name, values in sorted(measurements.cohorts.items())},
            "raw_evidence": evidence,
            "replay": measurements.replay.to_dict(),
        }
        return self.cas.put_document(manifest, artifact_kind="cache-parity-measurement-manifest")

    def _execute(self, executor: ScenarioExecutor, request: ScenarioRequest) -> ScenarioExecution:
        context, limitation = _isolation_context(executor, request)
        if context is None:
            return ScenarioExecution(
                ScenarioStatus.BLOCKED,
                reason="hard-deadline process isolation is unavailable",
                detail={
                    "failure_kind": "HARD_DEADLINE_ISOLATION_UNAVAILABLE",
                    "platform_limitation": limitation,
                    "hard_deadline_enforced": False,
                },
            )

        parent_connection, child_connection = context.Pipe(duplex=False)
        process = context.Process(
            target=_scenario_worker,
            args=(child_connection, executor, request),
            name=f"elmos-parity-{request.case.scenario_id.lower()}",
        )
        try:
            process.start()
        except BaseException as exc:
            parent_connection.close()
            child_connection.close()
            return ScenarioExecution(
                ScenarioStatus.BLOCKED,
                reason="hard-deadline worker could not be started",
                detail={
                    "failure_kind": "HARD_DEADLINE_ISOLATION_START_FAILED",
                    "isolation_start_method": context.get_start_method(),
                    "exception_type": type(exc).__name__,
                    "exception_digest": digest_of(str(exc)),
                    "hard_deadline_enforced": False,
                },
            )
        child_connection.close()

        envelope: _WorkerEnvelope | None = None
        receive_failure: BaseException | None = None
        try:
            while True:
                remaining = request.deadline_monotonic - time.monotonic()
                if remaining <= 0:
                    break
                if parent_connection.poll(min(remaining, 0.01)):
                    try:
                        received = parent_connection.recv()
                    except BaseException as exc:
                        receive_failure = exc
                    else:
                        if isinstance(received, _WorkerEnvelope):
                            envelope = received
                        else:
                            receive_failure = TypeError("worker returned an invalid envelope")
                    break
                if not process.is_alive():
                    if parent_connection.poll(0):
                        continue
                    break
        finally:
            parent_connection.close()

        deadline_exceeded = (
            envelope is None and time.monotonic() >= request.deadline_monotonic
        ) or (
            envelope is not None
            and envelope.completed_monotonic > request.deadline_monotonic
        )
        if deadline_exceeded:
            worker_pid = process.pid
            reclaimed = _reclaim_process(process)
            if reclaimed:
                process.close()
            return ScenarioExecution(
                ScenarioStatus.BLOCKED,
                reason="scenario executor exceeded its hard deadline",
                detail={
                    "failure_kind": "HARD_DEADLINE_EXCEEDED",
                    "hard_deadline_enforced": True,
                    "worker_reclaimed": reclaimed,
                    "worker_pid": worker_pid,
                    "isolation_start_method": context.get_start_method(),
                },
            )

        remaining = max(0.0, request.deadline_monotonic - time.monotonic())
        process.join(remaining)
        if process.is_alive():
            worker_pid = process.pid
            reclaimed = _reclaim_process(process)
            if reclaimed:
                process.close()
            return ScenarioExecution(
                ScenarioStatus.BLOCKED,
                reason="scenario worker did not exit inside its hard deadline",
                detail={
                    "failure_kind": "HARD_DEADLINE_RECLAIM_REQUIRED",
                    "hard_deadline_enforced": True,
                    "worker_reclaimed": reclaimed,
                    "worker_pid": worker_pid,
                    "isolation_start_method": context.get_start_method(),
                },
            )
        worker_exit_code = process.exitcode
        process.close()

        isolation_detail = {
            "hard_deadline_enforced": True,
            "worker_reclaimed": True,
            "isolation_start_method": context.get_start_method(),
        }
        if receive_failure is not None:
            return ScenarioExecution(
                ScenarioStatus.FAIL,
                reason="scenario worker result could not be received",
                detail={
                    **isolation_detail,
                    "failure_kind": "WORKER_TRANSPORT_ERROR",
                    "exception_type": type(receive_failure).__name__,
                    "exception_digest": digest_of(str(receive_failure)),
                },
            )
        if envelope is None:
            return ScenarioExecution(
                ScenarioStatus.FAIL,
                reason="scenario worker exited without a result",
                detail={
                    **isolation_detail,
                    "failure_kind": "WORKER_NO_RESULT",
                    "worker_exit_code": worker_exit_code,
                },
            )
        if envelope.kind == "TIMEOUT":
            return ScenarioExecution(
                ScenarioStatus.BLOCKED,
                reason="scenario executor timed out",
                detail={**isolation_detail, "failure_kind": "TIMEOUT"},
            )
        if envelope.kind == "EXCEPTION":
            return ScenarioExecution(
                ScenarioStatus.FAIL,
                reason=f"scenario executor raised {envelope.exception_type}",
                detail={
                    **isolation_detail,
                    "failure_kind": "EXECUTOR_EXCEPTION",
                    "exception_type": envelope.exception_type,
                    "exception_digest": envelope.exception_digest,
                },
            )
        if envelope.kind == "TRANSPORT_ERROR":
            return ScenarioExecution(
                ScenarioStatus.FAIL,
                reason="scenario executor returned an untransportable result",
                detail={
                    **isolation_detail,
                    "failure_kind": "WORKER_TRANSPORT_ERROR",
                    "exception_type": envelope.exception_type,
                    "exception_digest": envelope.exception_digest,
                },
            )
        if envelope.kind != "RESULT" or envelope.execution is None:
            return ScenarioExecution(
                ScenarioStatus.FAIL,
                reason="scenario executor returned an invalid result type",
                detail={**isolation_detail, "failure_kind": "INVALID_RESULT_TYPE"},
            )
        execution = ScenarioExecution(
            status=envelope.execution.status,
            raw_evidence=envelope.execution.raw_evidence,
            replay=envelope.execution.replay,
            reason=envelope.execution.reason,
            detail={**dict(envelope.execution.detail), **isolation_detail},
        )
        if execution.status is ScenarioStatus.PASS:
            assert execution.replay is not None  # guaranteed by ScenarioExecution
            if execution.replay.request_digest != request.request_digest:
                return ScenarioExecution(
                    ScenarioStatus.FAIL,
                    raw_evidence=execution.raw_evidence,
                    replay=execution.replay,
                    reason="scenario replay metadata does not bind the exact request",
                    detail={"failure_kind": "REPLAY_BINDING_MISMATCH"},
                )
        return execution

    def _persist_execution(
        self,
        *,
        request: ScenarioRequest,
        executor: ScenarioExecutor,
        execution: ScenarioExecution,
    ) -> tuple[ScenarioResult, str]:
        raw_evidence = self._persist_raw_evidence(
            execution.raw_evidence,
            artifact_kind=f"parity-scenario-{request.case.scenario_id.lower()}",
        )
        manifest = {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-scenario-execution/v1.2",
            "scenario_id": request.case.scenario_id,
            "request": request.statement(),
            "request_digest": request.request_digest,
            "executor_identity": executor.identity,
            "evidence_class": str(executor.evidence_class),
            "external_evidence_state": "NOT_RUN",
            "status": str(execution.status),
            "reason": execution.reason,
            "detail": dict(execution.detail),
            "raw_evidence": raw_evidence,
            "replay": execution.replay.to_dict() if execution.replay else None,
        }
        manifest_digest = self.cas.put_document(
            manifest,
            artifact_kind="cache-parity-scenario-manifest",
        )
        evidence_digests = tuple(item["digest"] for item in raw_evidence) + (manifest_digest,)
        result_detail = {
            **dict(execution.detail),
            "reason": execution.reason,
            "execution_manifest_digest": manifest_digest,
            "measurement_bundle_digest": request.measurement_bundle_digest,
            "evidence_class": str(executor.evidence_class),
            "external_evidence_state": "NOT_RUN",
            "replay": execution.replay.to_dict() if execution.replay else None,
        }
        return (
            ScenarioResult(
                scenario_id=request.case.scenario_id,
                status=execution.status,
                evidence_digests=evidence_digests,
                detail=result_detail,
            ),
            manifest_digest,
        )

    def _persist_raw_evidence(
        self,
        evidence: Sequence[RawEvidence],
        *,
        artifact_kind: str,
    ) -> list[dict[str, Any]]:
        persisted: list[dict[str, Any]] = []
        for item in evidence:
            digest = self.cas.put_bytes(item.content, artifact_kind=artifact_kind)
            if not self.cas.verify(digest):
                raise ContractViolation("raw evidence failed CAS verification", role=item.role)
            persisted.append(
                {
                    "role": item.role,
                    "media_type": item.media_type,
                    "digest": digest,
                    "size": len(item.content),
                }
            )
        return persisted


__all__ = [
    "CallableScenarioExecutor",
    "EvidenceClass",
    "MeasurementBundle",
    "ParityHarnessResult",
    "ParityScenarioHarness",
    "RawEvidence",
    "ReplayMetadata",
    "ScenarioCallable",
    "ScenarioCase",
    "ScenarioCorpus",
    "ScenarioExecution",
    "ScenarioExecutor",
    "ScenarioRequest",
]
