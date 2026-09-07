from __future__ import annotations
from dataclasses import asdict
from .models import ProofRun, ProofRunState, ProofResult, TERMINAL_STATES

class OrchestrationError(RuntimeError):
    pass

_ALLOWED = {
    ProofRunState.QUEUED: {ProofRunState.LEASED, ProofRunState.CANCELLED},
    ProofRunState.LEASED: {ProofRunState.RUNNING, ProofRunState.QUEUED, ProofRunState.CANCEL_REQUESTED},
    ProofRunState.RUNNING: {ProofRunState.PAUSED, ProofRunState.CANCEL_REQUESTED, ProofRunState.SUCCEEDED, ProofRunState.FAILED, ProofRunState.TIMED_OUT},
    ProofRunState.PAUSED: {ProofRunState.LEASED, ProofRunState.CANCELLED},
    ProofRunState.CANCEL_REQUESTED: {ProofRunState.CANCELLED, ProofRunState.FAILED},
    ProofRunState.SUCCEEDED: set(), ProofRunState.FAILED: set(),
    ProofRunState.CANCELLED: set(), ProofRunState.TIMED_OUT: set(),
}

class InMemoryOrchestrator:
    """Reference state machine; production uses PostgreSQL + durable workflow."""

    def __init__(self, account_concurrency: int = 3):
        if account_concurrency < 1:
            raise ValueError("account_concurrency must be positive")
        self.account_concurrency = account_concurrency
        self.runs: dict[str, ProofRun] = {}

    def submit(self, run: ProofRun) -> None:
        if run.id in self.runs:
            raise OrchestrationError(f"duplicate run {run.id}")
        active = sum(
            1 for r in self.runs.values()
            if r.account_id == run.account_id and r.state not in TERMINAL_STATES
        )
        if active >= self.account_concurrency:
            raise OrchestrationError("top-level account concurrency limit exceeded")
        run.events.append({"event":"submitted","token":run.fencing_token})
        self.runs[run.id] = run

    def transition(self, run_id: str, new_state: ProofRunState) -> ProofRun:
        run = self._get(run_id)
        if new_state not in _ALLOWED[run.state]:
            raise OrchestrationError(f"invalid transition {run.state}->{new_state}")
        run.state = new_state
        run.events.append({"event":"state","state":new_state.value,"token":run.fencing_token})
        return run

    def acquire(self, run_id: str, worker_id: str, expected_token: int) -> int:
        run = self._get(run_id)
        if run.state not in {ProofRunState.QUEUED, ProofRunState.PAUSED, ProofRunState.LEASED}:
            raise OrchestrationError("run is not leasable")
        if expected_token != run.fencing_token:
            raise OrchestrationError("fencing token mismatch")
        run.fencing_token += 1
        run.owner_id = worker_id
        run.state = ProofRunState.LEASED
        run.events.append({"event":"leased","owner":worker_id,"token":run.fencing_token})
        return run.fencing_token

    def start(self, run_id: str, worker_id: str, token: int) -> None:
        run = self._authorize(run_id, worker_id, token)
        self.transition(run.id, ProofRunState.RUNNING)

    def commit(self, run_id: str, worker_id: str, token: int, result: ProofResult) -> None:
        run = self._authorize(run_id, worker_id, token)
        if run.state != ProofRunState.RUNNING:
            raise OrchestrationError("only a running owner may commit")
        if result.obligation_id != run.obligation_id:
            raise OrchestrationError("result obligation mismatch")
        run.result = result
        self.transition(run.id, ProofRunState.SUCCEEDED)
        run.events.append({"event":"evidence-committed","token":token})

    def _authorize(self, run_id: str, worker_id: str, token: int) -> ProofRun:
        run = self._get(run_id)
        if run.owner_id != worker_id or run.fencing_token != token:
            raise OrchestrationError("stale or non-owner worker")
        return run

    def _get(self, run_id: str) -> ProofRun:
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise OrchestrationError(f"unknown run {run_id}") from exc

    def snapshot(self) -> list[dict]:
        return [asdict(r) for r in self.runs.values()]
