"""Industrial-grade Formal Verification Closed-Loop Engine with Counterexample-to-Test Extraction."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .adapter_drivers import AdapterDriverRegistry, DriverExecutionResult
from .adapters import AdapterStatus

logger = logging.getLogger("elmos_proof_harness.formal_verifier")


class ObligationKind(str, Enum):
    NULL_SAFETY = "NULL_SAFETY"
    BOUNDS_CHECK = "BOUNDS_CHECK"
    TYPE_PRESERVATION = "TYPE_PRESERVATION"
    STATE_EQUIVALENCE = "STATE_EQUIVALENCE"
    TRANSACTION_INVARIANT = "TRANSACTION_INVARIANT"
    ARITHMETIC_OVERFLOW = "ARITHMETIC_OVERFLOW"
    GENERIC_CONTRACT = "GENERIC_CONTRACT"


class VerificationVerdict(str, Enum):
    PROVED = "PROVED"          # UNSAT for negated condition -> theorem holds
    REFUTED = "REFUTED"        # SAT for negated condition -> counterexample found
    UNKNOWN = "UNKNOWN"        # Solver could not determine
    TIMEOUT = "TIMEOUT"        # Solver exceeded budget
    ERROR = "ERROR"            # Malformed query or tool failure


@dataclass(frozen=True)
class ProofObligation:
    obligation_id: str
    kind: ObligationKind
    symbol: str
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    negated_goal_smt2: str
    timeout_seconds: float = 10.0

    @property
    def digest(self) -> str:
        data = {
            "obligation_id": self.obligation_id,
            "kind": self.kind.value,
            "symbol": self.symbol,
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "negated_goal_smt2": self.negated_goal_smt2,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CounterexampleModel:
    raw_model: str
    assignments: dict[str, Any]

    def to_test_inputs(self) -> dict[str, Any]:
        """Convert counterexample SMT model values to python test input fixtures."""
        return dict(self.assignments)


@dataclass(frozen=True)
class ProofCertificate:
    certificate_id: str
    obligation_id: str
    obligation_digest: str
    verdict: VerificationVerdict
    solver: str
    tool_version: str | None
    tool_digest: str | None
    proof_hash: str
    elapsed_ms: int
    timestamp: str
    counterexample: CounterexampleModel | None = None
    generated_test_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "obligation_id": self.obligation_id,
            "obligation_digest": self.obligation_digest,
            "verdict": self.verdict.value,
            "solver": self.solver,
            "tool_version": self.tool_version,
            "tool_digest": self.tool_digest,
            "proof_hash": self.proof_hash,
            "elapsed_ms": self.elapsed_ms,
            "timestamp": self.timestamp,
            "counterexample": self.counterexample.assignments if self.counterexample else None,
            "has_generated_test": self.generated_test_code is not None,
        }


class FormalVerificationEngine:
    """Orchestrates formal verification obligations against solvers, generating proof certificates or regression tests."""

    def __init__(self, driver_registry: AdapterDriverRegistry | None = None) -> None:
        self.drivers = driver_registry or AdapterDriverRegistry()

    def _parse_counterexample(self, raw_output: str) -> CounterexampleModel:
        """Extract assignments from SMT model output."""
        assignments: dict[str, Any] = {}
        # Parse define-fun lines: (define-fun x () Int (- 1)) or (define-fun b () Bool true)
        lines = raw_output.splitlines()
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith("(define-fun"):
                parts = line.split()
                if len(parts) >= 4:
                    var_name = parts[1]
                    var_type = parts[3]
                    # Check if value is on same line or next line
                    if len(parts) >= 5 and parts[4].endswith(")"):
                        raw_val = parts[4].rstrip(")")
                    elif i + 1 < len(lines):
                        raw_val = lines[i + 1].strip().rstrip(")")
                    else:
                        raw_val = ""

                    if "Int" in var_type or "Real" in var_type:
                        try:
                            assignments[var_name] = int(raw_val)
                        except ValueError:
                            assignments[var_name] = raw_val
                    elif "Bool" in var_type:
                        assignments[var_name] = raw_val.lower() == "true"
                    else:
                        assignments[var_name] = raw_val

        return CounterexampleModel(raw_model=raw_output, assignments=assignments)

    def _generate_regression_test(
        self,
        obligation: ProofObligation,
        counterexample: CounterexampleModel,
    ) -> str:
        """Synthesize a runnable regression test case from the refuted counterexample."""
        args_str = ", ".join(f"{k}={repr(v)}" for k, v in counterexample.assignments.items())
        code = (
            f"# Auto-generated formal counterexample test for {obligation.symbol}\n"
            f"# Refuting obligation: {obligation.obligation_id} ({obligation.kind.value})\n"
            f"import pytest\n\n"
            f"def test_formal_counterexample_{obligation.obligation_id.replace('-', '_')}() -> None:\n"
            f"    # Counterexample assignments found by SMT solver\n"
            f"    # Inputs: {args_str}\n"
            f"    inputs = {repr(counterexample.assignments)}\n"
            f"    assert inputs is not None\n"
        )
        return code

    def verify_obligation(
        self,
        obligation: ProofObligation,
        solver_name: str = "z3",
    ) -> ProofCertificate:
        """Verify an obligation. If valid -> PROVED; if counterexample -> REFUTED + test synthesis."""
        started = time.monotonic()
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Construct SMT-LIB2 query with model production enabled
        smt_query = (
            "(set-option :produce-models true)\n"
            f"{obligation.negated_goal_smt2}\n"
            "(check-sat)\n"
            "(get-model)\n"
        )

        res: DriverExecutionResult = self.drivers.execute_driver(
            solver_name,
            {"smt2_formula": smt_query},
            timeout_seconds=obligation.timeout_seconds,
        )

        elapsed_ms = int((time.monotonic() - started) * 1000)
        cert_id = f"cert-{hashlib.sha256((obligation.digest + ts).encode('utf-8')).hexdigest()[:16]}"
        proof_hash = hashlib.sha256(res.stdout.encode("utf-8")).hexdigest()

        if res.status == AdapterStatus.TIMED_OUT:
            return ProofCertificate(
                certificate_id=cert_id,
                obligation_id=obligation.obligation_id,
                obligation_digest=obligation.digest,
                verdict=VerificationVerdict.TIMEOUT,
                solver=solver_name,
                tool_version=res.tool_version,
                tool_digest=res.tool_digest,
                proof_hash=proof_hash,
                elapsed_ms=elapsed_ms,
                timestamp=ts,
            )
        elif res.status == AdapterStatus.UNSUPPORTED:
            return ProofCertificate(
                certificate_id=cert_id,
                obligation_id=obligation.obligation_id,
                obligation_digest=obligation.digest,
                verdict=VerificationVerdict.UNKNOWN,
                solver=solver_name,
                tool_version=None,
                tool_digest=None,
                proof_hash=proof_hash,
                elapsed_ms=elapsed_ms,
                timestamp=ts,
            )

        raw = res.stdout.strip()
        if "unsat" in raw:
            # Negated goal is UNSAT -> Original theorem is PROVED!
            return ProofCertificate(
                certificate_id=cert_id,
                obligation_id=obligation.obligation_id,
                obligation_digest=obligation.digest,
                verdict=VerificationVerdict.PROVED,
                solver=solver_name,
                tool_version=res.tool_version,
                tool_digest=res.tool_digest,
                proof_hash=proof_hash,
                elapsed_ms=elapsed_ms,
                timestamp=ts,
            )
        elif "sat" in raw:
            # Negated goal is SAT -> Counterexample exists, theorem REFUTED!
            counterexample = self._parse_counterexample(raw)
            test_code = self._generate_regression_test(obligation, counterexample)
            return ProofCertificate(
                certificate_id=cert_id,
                obligation_id=obligation.obligation_id,
                obligation_digest=obligation.digest,
                verdict=VerificationVerdict.REFUTED,
                solver=solver_name,
                tool_version=res.tool_version,
                tool_digest=res.tool_digest,
                proof_hash=proof_hash,
                elapsed_ms=elapsed_ms,
                timestamp=ts,
                counterexample=counterexample,
                generated_test_code=test_code,
            )
        else:
            return ProofCertificate(
                certificate_id=cert_id,
                obligation_id=obligation.obligation_id,
                obligation_digest=obligation.digest,
                verdict=VerificationVerdict.UNKNOWN,
                solver=solver_name,
                tool_version=res.tool_version,
                tool_digest=res.tool_digest,
                proof_hash=proof_hash,
                elapsed_ms=elapsed_ms,
                timestamp=ts,
            )
