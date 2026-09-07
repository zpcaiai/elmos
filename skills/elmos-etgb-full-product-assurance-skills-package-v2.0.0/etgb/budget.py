from __future__ import annotations

import datetime as dt
import json
import math
import os
import statistics
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

try:  # pragma: no cover - Windows fallback is lock-free.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None


class BudgetExceeded(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class BudgetLedger:
    """Idempotent token/credit/compute/wall-clock reservation ledger.

    The local implementation uses an OS file lock and atomic replace. The
    production mapping is one serializable PostgreSQL transaction plus an
    outbox row for every accepted usage event.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._thread_lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            if not self.path.exists():
                _atomic_write(self.path, {"schema_version": "1.1", "reservations": {}, "events": {}})

    @contextmanager
    def _lock(self) -> Iterator[None]:
        # flock is process-scoped on some platforms, so serialize threads first.
        with self._thread_lock:
            with self.lock_path.open("a+") as fh:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _load(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def reserve(
        self,
        *,
        run_id: str,
        tenant_id: str,
        owner_id: str,
        max_input_tokens: int,
        max_output_tokens: int,
        max_credit_usd: float,
        max_wall_clock_ms: int,
    ) -> dict[str, Any]:
        if min(max_input_tokens, max_output_tokens, max_wall_clock_ms) < 0 or max_credit_usd < 0:
            raise ValueError("budget values must be non-negative")
        requested_limits = {
            "input_tokens": max_input_tokens,
            "output_tokens": max_output_tokens,
            "credit_usd": round(max_credit_usd, 8),
            "wall_clock_ms": max_wall_clock_ms,
        }
        with self._lock():
            ledger = self._load()
            if run_id in ledger["reservations"]:
                existing = ledger["reservations"][run_id]
                if (
                    existing["tenant_id"] != tenant_id
                    or existing["owner_id"] != owner_id
                    or existing["limits"] != requested_limits
                ):
                    raise ValueError("run budget reservation already exists with different terms")
                return existing
            record = {
                "run_id": run_id,
                "tenant_id": tenant_id,
                "owner_id": owner_id,
                "state": "RESERVED",
                "limits": requested_limits,
                "used": {"input_tokens": 0, "output_tokens": 0, "credit_usd": 0.0, "wall_clock_ms": 0},
                "reserved_at": utc_now(),
                "updated_at": utc_now(),
            }
            ledger["reservations"][run_id] = record
            _atomic_write(self.path, ledger)
            return record

    def consume(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        phase: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        credit_usd: float = 0.0,
        wall_clock_ms: int = 0,
        allow_overage: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        if min(input_tokens, output_tokens, wall_clock_ms) < 0 or credit_usd < 0:
            raise ValueError("usage values must be non-negative")
        with self._lock():
            ledger = self._load()
            if idempotency_key in ledger["events"]:
                event = ledger["events"][idempotency_key]
                if event["run_id"] != run_id:
                    raise ValueError("idempotency key is already bound to another run")
                return event
            if run_id not in ledger["reservations"]:
                raise KeyError(f"missing reservation: {run_id}")
            reservation = ledger["reservations"][run_id]
            if reservation["state"] not in {"RESERVED", "ACTIVE", "EXHAUSTED"}:
                raise BudgetExceeded(f"budget not consumable in state {reservation['state']}")
            delta = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "credit_usd": round(credit_usd, 8),
                "wall_clock_ms": wall_clock_ms,
            }
            projected = {
                key: round(reservation["used"][key] + delta[key], 8)
                if key == "credit_usd"
                else reservation["used"][key] + delta[key]
                for key in delta
            }
            exceeded = [key for key, value in projected.items() if value > reservation["limits"][key]]
            if exceeded and not allow_overage:
                reservation["state"] = "EXHAUSTED"
                reservation["updated_at"] = utc_now()
                _atomic_write(self.path, ledger)
                raise BudgetExceeded("budget exceeded: " + ", ".join(exceeded))
            reservation["used"] = projected
            reservation["state"] = "EXHAUSTED" if exceeded else "ACTIVE"
            reservation["updated_at"] = utc_now()
            event = {
                "idempotency_key": idempotency_key,
                "run_id": run_id,
                "phase": phase,
                "usage": delta,
                "projected_usage": projected,
                "overage_dimensions": exceeded,
                "created_at": utc_now(),
                "metadata": metadata or {},
            }
            ledger["events"][idempotency_key] = event
            _atomic_write(self.path, ledger)
            return event

    def close(self, run_id: str, *, state: str = "CLOSED") -> dict[str, Any]:
        with self._lock():
            ledger = self._load()
            if run_id not in ledger["reservations"]:
                raise KeyError(run_id)
            reservation = ledger["reservations"][run_id]
            reservation["state"] = state
            reservation["updated_at"] = utc_now()
            _atomic_write(self.path, ledger)
            return reservation

    def reconcile(self, run_id: str) -> dict[str, Any]:
        with self._lock():
            ledger = self._load()
            reservation = ledger["reservations"][run_id]
            summed = {"input_tokens": 0, "output_tokens": 0, "credit_usd": 0.0, "wall_clock_ms": 0}
            for event in ledger["events"].values():
                if event["run_id"] != run_id:
                    continue
                for key in summed:
                    summed[key] += event["usage"][key]
            summed["credit_usd"] = round(summed["credit_usd"], 8)
            return {
                "run_id": run_id,
                "valid": summed == reservation["used"],
                "summed": summed,
                "recorded": reservation["used"],
                "remaining": {
                    key: round(reservation["limits"][key] - reservation["used"][key], 8)
                    if key == "credit_usd"
                    else reservation["limits"][key] - reservation["used"][key]
                    for key in reservation["limits"]
                },
            }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * p
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - index) + ordered[high] * (index - low)


def estimate_machine_eta(
    cases: Iterable[dict[str, Any]],
    history: Iterable[dict[str, Any]],
    *,
    concurrency: int = 3,
    fallback_duration_ms: int = 300_000,
    setup_overhead_ms: int = 60_000,
) -> dict[str, Any]:
    """Estimate machine wall-clock only; no human-effort conversion is used."""

    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    history_by_capability: dict[str, list[float]] = {}
    history_by_line: dict[str, list[float]] = {}
    credit_per_ms: list[float] = []
    tokens_per_ms: list[float] = []
    for row in history:
        duration = float(row.get("duration_ms", 0) or 0)
        if duration <= 0 or row.get("status") in {"skipped", "unavailable"}:
            continue
        capability = row.get("capability_id") or row.get("coverage", {}).get("capability_id")
        line = row.get("business_line", "unknown")
        if capability:
            history_by_capability.setdefault(capability, []).append(duration)
        history_by_line.setdefault(line, []).append(duration)
        cost = row.get("cost", {})
        if float(cost.get("credit_usd", 0) or 0) > 0:
            credit_per_ms.append(float(cost["credit_usd"]) / duration)
        tokens = float(cost.get("token_input", 0) or 0) + float(cost.get("token_output", 0) or 0)
        if tokens > 0:
            tokens_per_ms.append(tokens / duration)

    predictions: list[dict[str, Any]] = []
    for case in cases:
        capability = case.get("coverage", {}).get("capability_id") or case.get("capability_id")
        line = case.get("business_line", "unknown")
        samples = history_by_capability.get(capability or "", []) or history_by_line.get(line, [])
        source = "capability-history" if history_by_capability.get(capability or "") else "business-line-history" if samples else "fallback"
        p50 = _percentile(samples, 0.50) if samples else float(fallback_duration_ms)
        p90 = _percentile(samples, 0.90) if samples else float(fallback_duration_ms) * 1.6
        predictions.append(
            {
                "case_id": case.get("id") or case.get("case_id"),
                "capability_id": capability,
                "source": source,
                "p50_ms": int(p50),
                "p90_ms": int(p90),
                "sample_count": len(samples),
            }
        )

    total_p50 = sum(x["p50_ms"] for x in predictions)
    total_p90 = sum(x["p90_ms"] for x in predictions)
    eta_p50 = math.ceil(total_p50 / concurrency) + setup_overhead_ms
    eta_p90 = math.ceil(total_p90 / concurrency) + setup_overhead_ms
    avg_credit_rate = statistics.fmean(credit_per_ms) if credit_per_ms else 0.0
    avg_token_rate = statistics.fmean(tokens_per_ms) if tokens_per_ms else 0.0
    return {
        "schema_version": "1.1",
        "case_count": len(predictions),
        "concurrency": concurrency,
        "machine_eta_ms": {"p50": eta_p50, "p90": eta_p90},
        "predicted_credit_usd": {
            "p50": round(total_p50 * avg_credit_rate, 6),
            "p90": round(total_p90 * avg_credit_rate, 6),
        },
        "predicted_tokens": {
            "p50": int(total_p50 * avg_token_rate),
            "p90": int(total_p90 * avg_token_rate),
        },
        "prediction_basis": predictions,
        "note": "ETA is Elmos machine wall-clock, excluding human review or engineering time.",
    }
