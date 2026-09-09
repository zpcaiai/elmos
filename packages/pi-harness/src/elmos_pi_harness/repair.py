"""Verification-gated repair proposals and self-healing loop controller."""

from __future__ import annotations

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


@dataclass
class SelfHealingAttempt:
    attempt_number: int
    executor_generation: int
    failure: FailureClassification
    shrunk_counterexample: str
    repair_prompt: str


class SelfHealingController:
    """Coordinates failure attribution, generation bumping, and bounded auto-repair."""

    def __init__(self, *, max_attempts: int = 3, initial_generation: int = 0) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.max_attempts = max_attempts
        self.current_generation = initial_generation
        self.attempts: list[SelfHealingAttempt] = []

    @property
    def remaining_budget(self) -> int:
        return max(0, self.max_attempts - len(self.attempts))

    @property
    def can_repair(self) -> bool:
        return self.remaining_budget > 0

    def record_failure(
        self,
        raw_output: str,
        objective: str,
        exit_code: int | None = None,
    ) -> SelfHealingAttempt:
        classification = FailureClassifier.classify(raw_output, exit_code=exit_code)
        shrunk = CounterexampleShrinker.shrink(raw_output)
        attempt_num = len(self.attempts) + 1

        self.current_generation += 1

        suspect_note = (
            f"\nSuspected files: {', '.join(classification.suspect_files)}"
            if classification.suspect_files
            else ""
        )
        repair_prompt = (
            f"=== Auto-Repair Attempt {attempt_num}/{self.max_attempts} (Gen {self.current_generation}) ===\n"
            f"Objective: {objective}\n"
            f"Failure Class: {classification.failure_class}\n"
            f"Summary: {classification.summary}{suspect_note}\n\n"
            f"Minimal Shrunk Counterexample:\n```\n{shrunk}\n```\n"
            f"Please address this specific root cause without modifying unaffected behavior."
        )

        attempt = SelfHealingAttempt(
            attempt_number=attempt_num,
            executor_generation=self.current_generation,
            failure=classification,
            shrunk_counterexample=shrunk,
            repair_prompt=repair_prompt,
        )
        self.attempts.append(attempt)
        return attempt

