"""Verification-gated repair proposals and self-healing loop controller."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence



@dataclass(frozen=True)
class RepairProposal:
    proposal_id: str
    failure_class: str
    target_paths: tuple[str, ...]
    patch_digest: str
    requires_approval: bool = True


def admit_repair(proposal: RepairProposal, *, verification_passed: bool, approved: bool) -> dict[str, object]:
    blockers = []
    if not proposal.target_paths:
        blockers.append("no_target_paths")
    if proposal.requires_approval and not approved:
        blockers.append("approval_required")
    if not verification_passed:
        blockers.append("verification_not_passed")
    return {"admitted": not blockers, "blockers": blockers, "proposal_id": proposal.proposal_id}


@dataclass(frozen=True)
class FailureClassification:
    failure_class: str
    summary: str
    suspect_files: tuple[str, ...]
    is_retryable: bool


class FailureClassifier:
    """Classifies compiler, test, runtime, or policy failures to guide bounded repair."""

    _SYNTAX_PATTERNS = (
        re.compile(r"SyntaxError: (.+)", re.IGNORECASE),
        re.compile(r"(?:^|\s)syntax error:? (.+)", re.IGNORECASE),
        re.compile(r"IndentationError: (.+)", re.IGNORECASE),
    )
    _TEST_PATTERNS = (
        re.compile(r"AssertionError: (.+)", re.IGNORECASE),
        re.compile(r"FAILED \((failures=\d+|errors=\d+)\)", re.IGNORECASE),
        re.compile(r"FAIL: (.+)", re.IGNORECASE),
        re.compile(r"assert .+ == .+", re.IGNORECASE),
    )
    _POLICY_PATTERNS = (
        re.compile(r"PolicyDeniedError: (.+)", re.IGNORECASE),
        re.compile(r"permission denied", re.IGNORECASE),
        re.compile(r"policy denied capability", re.IGNORECASE),
    )
    _FENCING_PATTERNS = (
        re.compile(r"StaleGenerationError: (.+)", re.IGNORECASE),
        re.compile(r"stale generation", re.IGNORECASE),
        re.compile(r"lease expired|lease conflict", re.IGNORECASE),
    )
    _TIMEOUT_PATTERNS = (
        re.compile(r"TimeoutError: (.+)", re.IGNORECASE),
        re.compile(r"timed out after \d+", re.IGNORECASE),
    )
    _FILE_PATTERN = re.compile(r'(?:File "([^"]+)", line \d+|([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+):\d+)')

    @classmethod
    def classify(cls, error_text: str, exit_code: int | None = None) -> FailureClassification:
        suspect_files: list[str] = []
        for match in cls._FILE_PATTERN.finditer(error_text):
            path = match.group(1) or match.group(2)
            if path and path not in suspect_files and not path.startswith(("/usr/", "/opt/", "<")):
                suspect_files.append(path)

        for pattern in cls._POLICY_PATTERNS:
            match = pattern.search(error_text)
            if match:
                return FailureClassification(
                    failure_class="POLICY_DENIAL",
                    summary=match.group(0),
                    suspect_files=tuple(suspect_files),
                    is_retryable=False,
                )

        for pattern in cls._FENCING_PATTERNS:
            match = pattern.search(error_text)
            if match:
                return FailureClassification(
                    failure_class="STALE_GENERATION",
                    summary=match.group(0),
                    suspect_files=tuple(suspect_files),
                    is_retryable=False,
                )

        for pattern in cls._SYNTAX_PATTERNS:
            match = pattern.search(error_text)
            if match:
                return FailureClassification(
                    failure_class="SYNTAX_ERROR",
                    summary=match.group(0),
                    suspect_files=tuple(suspect_files),
                    is_retryable=True,
                )

        for pattern in cls._TEST_PATTERNS:
            match = pattern.search(error_text)
            if match:
                return FailureClassification(
                    failure_class="TEST_FAILURE",
                    summary=match.group(0),
                    suspect_files=tuple(suspect_files),
                    is_retryable=True,
                )

        for pattern in cls._TIMEOUT_PATTERNS:
            match = pattern.search(error_text)
            if match:
                return FailureClassification(
                    failure_class="TIMEOUT",
                    summary=match.group(0),
                    suspect_files=tuple(suspect_files),
                    is_retryable=True,
                )

        summary = (
            error_text.strip().splitlines()[-1]
            if error_text.strip()
            else f"Process exited with code {exit_code}"
        )
        return FailureClassification(
            failure_class="UNHANDLED_ERROR",
            summary=summary,
            suspect_files=tuple(suspect_files),
            is_retryable=True,
        )


class CounterexampleShrinker:
    """Shrinks test/compiler output to the minimal salient failure context."""

    @staticmethod
    def shrink(raw_output: str, max_lines: int = 30) -> str:
        if not raw_output or not raw_output.strip():
            return "No failure output recorded."

        lines = [line.rstrip() for line in raw_output.strip().splitlines()]
        if len(lines) <= max_lines:
            return "\n".join(lines)

        salient_indices: set[int] = set()
        error_keywords = ("error", "fail", "traceback", "exception", "assert", "denied", "mismatch")

        for idx, line in enumerate(lines):
            lower = line.lower()
            if any(k in lower for k in error_keywords):
                for offset in range(-2, 3):
                    c_idx = idx + offset
                    if 0 <= c_idx < len(lines):
                        salient_indices.add(c_idx)

        for idx in range(max(0, len(lines) - 8), len(lines)):
            salient_indices.add(idx)

        selected_indices = sorted(salient_indices)[:max_lines]
        if not selected_indices:
            selected_indices = list(range(len(lines) - max_lines, len(lines)))

        result: list[str] = []
        last_idx = -1
        for idx in selected_indices:
            if last_idx != -1 and idx > last_idx + 1:
                result.append(f"... [{idx - last_idx - 1} lines truncated] ...")
            result.append(lines[idx])
            last_idx = idx

        return "\n".join(result)


@dataclass(frozen=True)
class RepairStrategy:
    action: str
    repair_recipe: str
    confidence: float
    requires_human_approval: bool


class DeterministicRepairStrategy:
    """Derives bounded deterministic repair actions based on failure classification."""

    @staticmethod
    def recommend(classification: FailureClassification) -> RepairStrategy:
        fclass = classification.failure_class
        if fclass == "POLICY_DENIAL":
            return RepairStrategy(
                action="VERIFY_UPPER_POLICY_PERMISSION",
                repair_recipe="Check upper_policy allowed capabilities or remove unauthorized tool invocation from execution plan.",
                confidence=0.95,
                requires_human_approval=True,
            )
        elif fclass == "STALE_GENERATION":
            return RepairStrategy(
                action="SYNC_EXECUTOR_GENERATION_AND_LEASE",
                repair_recipe="Refresh authority snapshot, synchronize executor generation, and acquire a new capability lease.",
                confidence=0.98,
                requires_human_approval=False,
            )
        elif fclass == "SYNTAX_ERROR":
            return RepairStrategy(
                action="APPLY_AST_PARSER_AUTODETECTION",
                repair_recipe="Pinpoint precise syntax defect line/col from diagnostic and apply targeted formatting or syntax patch.",
                confidence=0.90,
                requires_human_approval=False,
            )
        elif fclass == "TEST_FAILURE":
            return RepairStrategy(
                action="COUNTEREXAMPLE_DRIVEN_TEST_FIX",
                repair_recipe="Isolate failing assertion delta, check input domain assumptions, and adjust implementation without altering test semantics.",
                confidence=0.85,
                requires_human_approval=False,
            )
        elif fclass == "TIMEOUT":
            return RepairStrategy(
                action="EXPONENTIAL_TIMEOUT_BACKOFF_OR_SHARD",
                repair_recipe="Increase task timeout by 1.5x backoff factor or shard input batch into smaller granular units.",
                confidence=0.80,
                requires_human_approval=False,
            )
        return RepairStrategy(
            action="DIAGNOSTIC_LOG_INSPECTION",
            repair_recipe="Inspect runtime diagnostic traces and review suspect source files.",
            confidence=0.60,
            requires_human_approval=True,
        )


class OscillationDetector:
    """Detects repeating error cycles (doom loops) across repair generations."""

    def __init__(self, history_window: int = 5) -> None:
        self.history_window = history_window
        self.signatures: list[str] = []

    @staticmethod
    def compute_signature(classification: FailureClassification) -> str:
        norm_summary = re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "<UUID>", classification.summary)
        norm_summary = re.sub(r"0x[0-9a-fA-F]+", "<ADDR>", norm_summary)
        norm_summary = re.sub(r"\d+", "<NUM>", norm_summary)
        payload = f"{classification.failure_class}:{norm_summary}:{sorted(classification.suspect_files)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def record_and_check(self, classification: FailureClassification) -> tuple[bool, str]:
        sig = self.compute_signature(classification)
        if sig in self.signatures:
            idx = self.signatures.index(sig)
            cycle_length = len(self.signatures) - idx
            self.signatures.append(sig)
            return True, f"Oscillation detected: repeated failure signature {sig} with period {cycle_length}"
        self.signatures.append(sig)
        if len(self.signatures) > self.history_window:
            self.signatures.pop(0)
        return False, ""


@dataclass(frozen=True)
class RollbackRecommendation:
    should_rollback: bool
    recommended_generation: int
    reason: str


class RollbackAdvisor:
    """Advises on rolling back when subsequent generations introduce regressions."""

    @staticmethod
    def evaluate(attempts: Sequence[SelfHealingAttempt]) -> RollbackRecommendation:
        if len(attempts) < 2:
            return RollbackRecommendation(False, 0, "Insufficient generation history")
        curr = attempts[-1].failure
        prev = attempts[-2].failure
        severity = {"POLICY_DENIAL": 5, "STALE_GENERATION": 4, "SYNTAX_ERROR": 3, "TEST_FAILURE": 2, "TIMEOUT": 2, "UNHANDLED_ERROR": 1}
        if severity.get(curr.failure_class, 1) > severity.get(prev.failure_class, 1):
            return RollbackRecommendation(
                should_rollback=True,
                recommended_generation=attempts[-2].executor_generation,
                reason=f"Degradation detected: severity rose from {prev.failure_class} to {curr.failure_class}",
            )
        return RollbackRecommendation(False, attempts[-1].executor_generation, "No severe degradation detected")


@dataclass
class SelfHealingAttempt:
    attempt_number: int
    executor_generation: int
    failure: FailureClassification
    shrunk_counterexample: str
    repair_prompt: str
    strategy: RepairStrategy | None = None
    signature: str = ""
    cycle_detected: bool = False


class SelfHealingController:
    """Coordinates failure attribution, generation bumping, doom-loop prevention, and bounded auto-repair."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        initial_generation: int = 0,
        oscillation_detector: OscillationDetector | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.max_attempts = max_attempts
        self.current_generation = initial_generation
        self.attempts: list[SelfHealingAttempt] = []
        self.detector = oscillation_detector or OscillationDetector()
        self.cycle_detected: bool = False

    @property
    def remaining_budget(self) -> int:
        return max(0, self.max_attempts - len(self.attempts))

    @property
    def can_repair(self) -> bool:
        return self.remaining_budget > 0 and not self.cycle_detected

    def record_failure(
        self,
        raw_output: str,
        objective: str,
        exit_code: int | None = None,
    ) -> SelfHealingAttempt:
        classification = FailureClassifier.classify(raw_output, exit_code=exit_code)
        shrunk = CounterexampleShrinker.shrink(raw_output)
        strategy = DeterministicRepairStrategy.recommend(classification)
        is_cycle, cycle_reason = self.detector.record_and_check(classification)
        if is_cycle:
            self.cycle_detected = True

        attempt_num = len(self.attempts) + 1
        self.current_generation += 1
        sig = OscillationDetector.compute_signature(classification)

        suspect_note = (
            f"\nSuspected files: {', '.join(classification.suspect_files)}"
            if classification.suspect_files
            else ""
        )
        cycle_note = f"\nWARNING: {cycle_reason}\n" if is_cycle else ""

        repair_prompt = (
            f"=== Auto-Repair Attempt {attempt_num}/{self.max_attempts} (Gen {self.current_generation}) ===\n"
            f"Objective: {objective}\n"
            f"Failure Class: {classification.failure_class}\n"
            f"Summary: {classification.summary}{suspect_note}\n"
            f"Recommended Strategy: {strategy.action} ({strategy.repair_recipe}){cycle_note}\n\n"
            f"Minimal Shrunk Counterexample:\n```\n{shrunk}\n```\n"
            f"Please address this specific root cause without modifying unaffected behavior."
        )

        attempt = SelfHealingAttempt(
            attempt_number=attempt_num,
            executor_generation=self.current_generation,
            failure=classification,
            shrunk_counterexample=shrunk,
            repair_prompt=repair_prompt,
            strategy=strategy,
            signature=sig,
            cycle_detected=is_cycle,
        )
        self.attempts.append(attempt)
        return attempt

    def suggest_rollback(self) -> RollbackRecommendation:
        return RollbackAdvisor.evaluate(self.attempts)

    def export_repair_evidence(self, final_status: str) -> dict[str, Any]:
        records = []
        for att in self.attempts:
            records.append({
                "attempt": att.attempt_number,
                "generation": att.executor_generation,
                "failure_class": att.failure.failure_class,
                "summary": att.failure.summary,
                "signature": att.signature,
                "strategy": att.strategy.action if att.strategy else None,
                "cycle_detected": att.cycle_detected,
            })
        data = {
            "schema_version": "1.0.0",
            "total_attempts": len(self.attempts),
            "max_attempts": self.max_attempts,
            "final_status": final_status,
            "cycle_detected": self.cycle_detected,
            "attempts": records,
        }
        digest = f"sha256:{hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()}"
        data["evidence_digest"] = digest
        return data


