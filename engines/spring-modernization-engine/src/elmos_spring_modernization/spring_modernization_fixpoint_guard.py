"""
Industrial-grade AST State Fixpoint Guard & Doom-Loop Circuit Breaker for Automated Spring Modernization.

Detects rule oscillation (Rule A converts X -> Y, Rule B reverts Y -> X),
prevents infinite repair loops, tracks state hashes, triggers circuit breakers,
and generates structured Human Escalation Dossiers.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class TransformationStep:
    step_index: int
    file_path: str
    rule_name: str
    before_hash: str
    after_hash: str


@dataclass
class HumanEscalationDossier:
    file_path: str
    oscillation_detected: bool
    cycle_length: int
    conflicting_rules: List[str]
    state_hashes: List[str]
    recommendation: str

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "oscillation_detected": self.oscillation_detected,
            "cycle_length": self.cycle_length,
            "conflicting_rules": self.conflicting_rules,
            "state_hashes": self.state_hashes,
            "recommendation": self.recommendation,
        }


@dataclass
class GuardVerdict:
    allowed: bool
    circuit_open: bool
    reason: str
    escalation: Optional[HumanEscalationDossier] = None


class SpringModernizationFixpointGuard:
    """
    Guards automated rule application against infinite loops, oscillation,
    and diverging AST rewrites.
    """

    def __init__(self, max_iterations_per_file: int = 5, max_cycle_detection: int = 2):
        self.max_iterations_per_file = max_iterations_per_file
        self.max_cycle_detection = max_cycle_detection
        self.file_history: Dict[str, List[TransformationStep]] = {}
        self.file_hashes: Dict[str, List[str]] = {}
        self.circuit_open_files: Set[str] = set()

    @staticmethod
    def compute_content_hash(content: str) -> str:
        return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

    def record_step(
        self,
        file_path: str,
        rule_name: str,
        before_content: str,
        after_content: str,
    ) -> GuardVerdict:
        """
        Record a proposed code modification and determine whether it should be permitted
        or aborted due to fixpoint divergence/oscillation.
        """
        if file_path in self.circuit_open_files:
            return GuardVerdict(
                allowed=False,
                circuit_open=True,
                reason=f"Circuit breaker is OPEN for {file_path} due to previous oscillation.",
            )

        before_hash = self.compute_content_hash(before_content)
        after_hash = self.compute_content_hash(after_content)

        if file_path not in self.file_hashes:
            self.file_hashes[file_path] = [before_hash]
            self.file_history[file_path] = []

        history = self.file_history[file_path]
        hashes = self.file_hashes[file_path]

        step_index = len(history) + 1

        # 1. Check max iterations budget
        if step_index > self.max_iterations_per_file:
            self.circuit_open_files.add(file_path)
            conflicting_rules = [step.rule_name for step in history] + [rule_name]
            dossier = HumanEscalationDossier(
                file_path=file_path,
                oscillation_detected=False,
                cycle_length=0,
                conflicting_rules=conflicting_rules,
                state_hashes=hashes + [after_hash],
                recommendation=f"Exceeded max iteration budget ({self.max_iterations_per_file} steps). Manual human review required.",
            )
            return GuardVerdict(
                allowed=False,
                circuit_open=True,
                reason="MAX_ITERATIONS_EXCEEDED",
                escalation=dossier,
            )

        # 2. Check direct cycle / oscillation (after_hash equals any previous hash in this session)
        if after_hash in hashes:
            cycle_start = hashes.index(after_hash)
            cycle_length = len(hashes) - cycle_start
            self.circuit_open_files.add(file_path)

            conflicting_rules = [step.rule_name for step in history[cycle_start:]] + [rule_name]
            dossier = HumanEscalationDossier(
                file_path=file_path,
                oscillation_detected=True,
                cycle_length=cycle_length,
                conflicting_rules=conflicting_rules,
                state_hashes=hashes + [after_hash],
                recommendation=(
                    f"Oscillation cycle of length {cycle_length} detected between rules "
                    f"{conflicting_rules}. Hard circuit breaker tripped to prevent doom-loop."
                ),
            )
            return GuardVerdict(
                allowed=False,
                circuit_open=True,
                reason="OSCILLATION_DOOM_LOOP_DETECTED",
                escalation=dossier,
            )

        # Step is valid: record and permit
        step = TransformationStep(
            step_index=step_index,
            file_path=file_path,
            rule_name=rule_name,
            before_hash=before_hash,
            after_hash=after_hash,
        )
        history.append(step)
        hashes.append(after_hash)

        return GuardVerdict(
            allowed=True,
            circuit_open=False,
            reason="STEP_ACCEPTED_CONVERGING",
        )

    def is_healthy(self) -> bool:
        return len(self.circuit_open_files) == 0
