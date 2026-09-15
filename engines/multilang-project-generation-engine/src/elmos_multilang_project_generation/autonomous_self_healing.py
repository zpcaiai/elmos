"""Autonomous Closed-Loop Self-Healing Engine (Layer 5 Industrial Self-Healing).

Connects real compiler stderr and test diagnostics back into the agentic injection
repair loop to automatically fix code until native test runners pass.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .agentic_slot_injector import AgenticSlotInjector, ModelDriver
from .domain_slot import DomainSlotSpec
from .models import LanguageTarget
from .native_toolchain_runner import HermeticWorkspace, NativeToolchainRunner, ToolchainExecutionReport


@dataclass
class HealingAttempt:
    attempt_number: int
    diagnostic_input: str
    repaired_code: str
    exit_code: int
    passed: bool
    duration_ms: float
    stderr: str


@dataclass
class SelfHealingReport:
    success: bool
    total_attempts: int
    initial_exit_code: int
    final_exit_code: int
    attempts: List[HealingAttempt] = field(default_factory=list)
    repaired_files: Dict[str, str] = field(default_factory=dict)
    summary: str = ""


class AutonomousSelfHealingEngine:
    """Orchestrates closed-loop repair using real native compiler/test feedback."""

    def __init__(
        self,
        slot_injector: AgenticSlotInjector,
        toolchain_runner: Optional[NativeToolchainRunner] = None,
        max_attempts: int = 3
    ):
        self.slot_injector = slot_injector
        self.toolchain_runner = toolchain_runner or NativeToolchainRunner()
        self.max_attempts = max_attempts

    def heal(
        self,
        language: LanguageTarget,
        workspace: HermeticWorkspace,
        slot: DomainSlotSpec,
        initial_report: ToolchainExecutionReport,
        target_rel_path: str,
        slot_context_package
    ) -> SelfHealingReport:
        """Executes iterative self-healing loop in workspace."""
        attempts: List[HealingAttempt] = []
        current_report = initial_report
        success = False

        for attempt_idx in range(1, self.max_attempts + 1):
            start_t = time.perf_counter()

            # 1. Synthesize targeted repair diagnostic
            diag_text = (
                f"Native toolchain execution failed with exit code {current_report.exit_code}.\n"
                f"Error Diagnostics:\n{chr(10).join(current_report.diagnostics)}\n"
                f"Compiler/Test stderr:\n{current_report.stderr}\n"
                f"Compiler/Test stdout:\n{current_report.stdout[:1000]}"
            )

            # 2. Invoke slot injector to generate repaired implementation
            repair_res = self.slot_injector.inject_slot(
                slot=slot,
                context_package=slot_context_package,
                target_file_content=workspace.read_file(target_rel_path),
                diagnostics_feedback=diag_text
            )

            if not repair_res.success:
                attempts.append(HealingAttempt(
                    attempt_number=attempt_idx,
                    diagnostic_input=diag_text,
                    repaired_code="",
                    exit_code=-1,
                    passed=False,
                    duration_ms=(time.perf_counter() - start_t) * 1000.0,
                    stderr="Failed to generate valid AST during slot repair"
                ))
                continue

            # 3. Apply repaired file into hermetic workspace
            workspace.update_file(target_rel_path, repair_res.modified_file_content)

            # 4. Re-execute native compiler / test runner
            re_run_report = self.toolchain_runner.execute(language, workspace.root_path)
            duration_ms = (time.perf_counter() - start_t) * 1000.0

            attempt = HealingAttempt(
                attempt_number=attempt_idx,
                diagnostic_input=diag_text,
                repaired_code=repair_res.slot_result.generated_code if repair_res.slot_result else "",
                exit_code=re_run_report.exit_code,
                passed=re_run_report.passed,
                duration_ms=duration_ms,
                stderr=re_run_report.stderr
            )
            attempts.append(attempt)

            current_report = re_run_report
            if re_run_report.passed:
                success = True
                break

        final_files: Dict[str, str] = {}
        for f in workspace.list_files():
            final_files[f] = workspace.read_file(f)

        summary = (
            f"Self-healing {'SUCCEEDED' if success else 'FAILED'} after {len(attempts)} attempt(s). "
            f"Initial exit={initial_report.exit_code}, Final exit={current_report.exit_code}."
        )

        return SelfHealingReport(
            success=success,
            total_attempts=len(attempts),
            initial_exit_code=initial_report.exit_code,
            final_exit_code=current_report.exit_code,
            attempts=attempts,
            repaired_files=final_files,
            summary=summary
        )
