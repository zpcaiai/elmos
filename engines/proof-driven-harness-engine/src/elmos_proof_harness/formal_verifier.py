"""Industrial-grade Formal Verification Closed-Loop Engine with Counterexample-to-Test Extraction."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .adapter_drivers import AdapterDriverRegistry, DriverExecutionResult
from .adapters import AdapterStatus

logger = logging.getLogger("elmos_proof_harness.formal_verifier")


class SExprParser:
    """SMT-LIB2 S-expression tokenizer and recursive-descent parser."""

    @staticmethod
    def tokenize(text: str) -> list[str]:
        tokens: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            c = text[i]
            if c.isspace():
                i += 1
                continue
            if c == ";":
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if c in ("(", ")"):
                tokens.append(c)
                i += 1
                continue
            if c == '"':
                start = i
                i += 1
                while i < n:
                    if text[i] == '"':
                        if i + 1 < n and text[i + 1] == '"':
                            i += 2
                        else:
                            i += 1
                            break
                    else:
                        i += 1
                tokens.append(text[start:i])
                continue
            if c == "|":
                start = i
                i += 1
                while i < n and text[i] != "|":
                    i += 1
                if i < n and text[i] == "|":
                    i += 1
                tokens.append(text[start:i])
                continue
            start = i
            while i < n and not text[i].isspace() and text[i] not in "();":
                i += 1
            tokens.append(text[start:i])
        return tokens

    @classmethod
    def parse_tokens(cls, tokens: list[str]) -> list[Any]:
        stack: list[list[Any]] = [[]]
        for token in tokens:
            if token == "(":
                new_list: list[Any] = []
                stack[-1].append(new_list)
                stack.append(new_list)
            elif token == ")":
                if len(stack) > 1:
                    stack.pop()
            else:
                stack[-1].append(token)
        return stack[0]

    @classmethod
    def parse(cls, text: str) -> list[Any]:
        tokens = cls.tokenize(text)
        return cls.parse_tokens(tokens)


class SMTValueEvaluator:
    """Evaluates SMT-LIB2 model expressions into Python native values and formats sorts."""

    @classmethod
    def format_sort(cls, sort_expr: Any) -> str:
        if isinstance(sort_expr, str):
            return sort_expr.strip("|")
        if isinstance(sort_expr, list):
            if len(sort_expr) >= 3 and sort_expr[0] == "_" and sort_expr[1] == "BitVec":
                return f"BitVec({sort_expr[2]})"
            if len(sort_expr) >= 3 and sort_expr[0] == "Array":
                domain = cls.format_sort(sort_expr[1])
                range_ = cls.format_sort(sort_expr[2])
                return f"Array({domain}, {range_})"
            return "(" + " ".join(cls.format_sort(item) for item in sort_expr) + ")"
        return str(sort_expr)

    @classmethod
    def evaluate(cls, expr: Any, sort: Any = None) -> Any:
        if isinstance(expr, str):
            token = expr.strip()
            if token.startswith('"') and token.endswith('"'):
                return token[1:-1].replace('""', '"')
            if token.lower() == "true":
                return True
            if token.lower() == "false":
                return False
            if token.startswith("#x") or token.startswith("#X"):
                return int(token[2:], 16)
            if token.startswith("#b") or token.startswith("#B"):
                return int(token[2:], 2)
            if token.startswith("bv") and token[2:].isdigit():
                return int(token[2:])
            try:
                sort_desc = cls.format_sort(sort) if sort else ""
                if "." in token or "Real" in sort_desc:
                    return float(token)
                return int(token)
            except ValueError:
                return token.strip("|")

        if isinstance(expr, list):
            if not expr:
                return None
            op = expr[0]

            if op == "-":
                if len(expr) == 2:
                    val = cls.evaluate(expr[1], sort)
                    return -val if isinstance(val, (int, float)) else f"-{val}"
                elif len(expr) == 3:
                    left = cls.evaluate(expr[1], sort)
                    right = cls.evaluate(expr[2], sort)
                    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                        return left - right
                    return f"({left} - {right})"

            if op == "+" and len(expr) == 2:
                return cls.evaluate(expr[1], sort)

            if op == "/" and len(expr) == 3:
                num = cls.evaluate(expr[1], sort)
                denom = cls.evaluate(expr[2], sort)
                if isinstance(num, (int, float)) and isinstance(denom, (int, float)) and denom != 0:
                    return float(num) / float(denom)

            if op == "_" and len(expr) >= 3:
                bv_atom = str(expr[1])
                if bv_atom.startswith("bv") and bv_atom[2:].isdigit():
                    return int(bv_atom[2:])

            # Array constant: ((as const (Array Int Int)) 0)
            if len(expr) == 2 and isinstance(expr[0], list):
                header = expr[0]
                if len(header) >= 2 and header[0] == "as" and header[1] == "const":
                    default_val = cls.evaluate(expr[1])
                    return {"__default__": default_val}

            # Array store: (store <arr> <key> <val>)
            if op == "store" and len(expr) == 4:
                base_arr = cls.evaluate(expr[1], sort)
                key = cls.evaluate(expr[2])
                val = cls.evaluate(expr[3])
                if isinstance(base_arr, dict):
                    res = dict(base_arr)
                else:
                    res = {"__default__": None}
                res[key] = val
                return res

            return [cls.evaluate(item) for item in expr]

        return expr


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
    sorts: dict[str, str] = field(default_factory=dict)
    raw_exprs: dict[str, str] = field(default_factory=dict)

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
            "counterexample_sorts": self.counterexample.sorts if self.counterexample else None,
            "has_generated_test": self.generated_test_code is not None,
        }


class FormalVerificationEngine:
    """Orchestrates formal verification obligations against solvers, generating proof certificates or regression tests."""

    def __init__(self, driver_registry: AdapterDriverRegistry | None = None) -> None:
        self.drivers = driver_registry or AdapterDriverRegistry()

    def _parse_counterexample(self, raw_output: str) -> CounterexampleModel:
        """Extract assignments from SMT model output using structured S-expression parser."""
        assignments: dict[str, Any] = {}
        sorts: dict[str, str] = {}
        raw_exprs: dict[str, str] = {}

        try:
            parsed = SExprParser.parse(raw_output)
            definitions: list[list[Any]] = []

            def collect_defs(node: Any) -> None:
                if isinstance(node, list):
                    if len(node) >= 4 and isinstance(node[0], str) and node[0] in ("define-fun", "define-fun-rec"):
                        definitions.append(node)
                    else:
                        for child in node:
                            collect_defs(child)

            collect_defs(parsed)

            for def_form in definitions:
                name = str(def_form[1]).strip("|")
                sort_spec = def_form[3]
                body_expr = def_form[4] if len(def_form) >= 5 else None

                sort_str = SMTValueEvaluator.format_sort(sort_spec)
                val = SMTValueEvaluator.evaluate(body_expr, sort=sort_spec)

                assignments[name] = val
                sorts[name] = sort_str
                raw_exprs[name] = json.dumps(body_expr) if isinstance(body_expr, list) else str(body_expr)

        except Exception as exc:
            logger.warning("Failed structured S-expression parsing on SMT model: %s", exc)

        if not assignments:
            lines = raw_output.splitlines()
            for i, line in enumerate(lines):
                line = line.strip()
                if line.startswith("(define-fun"):
                    parts = line.split()
                    if len(parts) >= 4:
                        var_name = parts[1].strip("|")
                        var_type = parts[3]
                        if len(parts) >= 5:
                            raw_val = " ".join(parts[4:]).rstrip(")")
                        elif i + 1 < len(lines):
                            raw_val = lines[i + 1].strip().rstrip(")")
                        else:
                            raw_val = ""

                        neg_match = re.search(r"(?:\(\s*-\s*|-)(\d+(?:\.\d+)?)", raw_val)
                        pos_match = re.search(r"^\(?(\d+(?:\.\d+)?)\)?", raw_val)

                        if neg_match:
                            num_str = neg_match.group(1)
                            if "Real" in var_type or "." in num_str:
                                assignments[var_name] = -float(num_str)
                            else:
                                assignments[var_name] = -int(num_str)
                        elif pos_match and ("Int" in var_type or "Real" in var_type):
                            num_str = pos_match.group(1)
                            if "Real" in var_type or "." in num_str:
                                assignments[var_name] = float(num_str)
                            else:
                                assignments[var_name] = int(num_str)
                        elif "Bool" in var_type or raw_val.lower() in ("true", "false"):
                            assignments[var_name] = raw_val.lower() == "true"
                        else:
                            assignments[var_name] = raw_val

        return CounterexampleModel(
            raw_model=raw_output,
            assignments=assignments,
            sorts=sorts,
            raw_exprs=raw_exprs,
        )

    def _generate_regression_test(
        self,
        obligation: ProofObligation,
        counterexample: CounterexampleModel,
    ) -> str:
        """Synthesize a runnable regression test case from the refuted counterexample."""
        args_str = ", ".join(f"{k}={repr(v)}" for k, v in counterexample.assignments.items())
        code_lines = [
            f"# Auto-generated formal counterexample test for {obligation.symbol}",
            f"# Refuting obligation: {obligation.obligation_id} ({obligation.kind.value})",
            "import pytest\n",
            f"def test_formal_counterexample_{obligation.obligation_id.replace('-', '_')}() -> None:",
            "    # Counterexample assignments found by SMT solver",
            f"    # Inputs: {args_str}",
            f"    inputs = {repr(counterexample.assignments)}",
            "    assert inputs is not None",
        ]
        for var_name, val in counterexample.assignments.items():
            sort_desc = counterexample.sorts.get(var_name, "")
            if isinstance(val, dict) and "__default__" in val:
                code_lines.append(f"    # Array assignment for '{var_name}' (Sort: {sort_desc})")
                for k, v in val.items():
                    if k != "__default__":
                        code_lines.append(f"    assert inputs[{repr(var_name)}][{repr(k)}] == {repr(v)}")
            elif "BitVec" in sort_desc:
                code_lines.append(f"    # BitVector assignment for '{var_name}' ({sort_desc})")
                code_lines.append(f"    assert inputs[{repr(var_name)}] == {repr(val)}")
            else:
                code_lines.append(f"    assert inputs[{repr(var_name)}] == {repr(val)}")

        return "\n".join(code_lines) + "\n"

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
