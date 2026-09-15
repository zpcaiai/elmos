"""Industrial-Grade Layered Hybrid Project Synthesizer.

Unifies all 5 layers:
Layer 1: Deterministic DDD Skeleton & Infrastructure Core (0 Tokens, microsecond speed)
Layer 2: Minimal-Context Domain Slot Extractor & Prompt Compiler (80%-95% token savings)
Layer 3: Agentic Slot Injector & AST Merger (Claude 3.5 Sonnet / Codex adapter)
Layer 4: Deterministic Verification & Non-Self-Certification Gate (E0-E5 Decision)
Layer 5: Commercial Telemetry & Cost-Efficiency Accounting
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from .agentic_slot_injector import AgenticSlotInjector, ModelDriver
from .deterministic_scaffold import DeterministicScaffoldGenerator
from .domain_slot import DomainSlotSpec, SlotSynthesisResult
from .models import PSIR, GeneratedProject
from .slot_context_compiler import SlotContextCompiler, SlotContextPackage
from .telemetry_economics import HybridSynthesisTelemetry, TelemetryEconomicsCalculator
from .verification_gate import DeterministicVerificationGate, VerificationReport


@dataclass
class HybridSynthesisOutcome:
    project: GeneratedProject
    telemetry: HybridSynthesisTelemetry
    verification_report: VerificationReport
    markdown_report: str

    def write_to_disk(self, target_dir: str) -> None:
        """Writes all generated project files and benchmark reports to disk."""
        os.makedirs(target_dir, exist_ok=True)
        for rel_path, content in self.project.files.items():
            dest = os.path.join(target_dir, rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(content)

        # Write evidence and benchmark report
        report_path = os.path.join(target_dir, "ELMOS_HYBRID_BENCHMARK_REPORT.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self.markdown_report)


class LayeredHybridProjectSynthesizer:
    """Master orchestrator for the industrial layered hybrid project generation."""

    def __init__(self, model_driver: Optional[ModelDriver] = None):
        self.scaffold_gen = DeterministicScaffoldGenerator()
        self.context_compiler = SlotContextCompiler()
        self.injector = AgenticSlotInjector(model_driver=model_driver)
        self.verifier = DeterministicVerificationGate()

    def synthesize(
        self,
        psir: PSIR,
        custom_slots: Optional[List[DomainSlotSpec]] = None,
        execute_unit_tests: bool = True
    ) -> HybridSynthesisOutcome:
        """Executes the complete 5-layer synthesis pipeline."""
        start_time = time.perf_counter()
        lang_str = psir.language.value.lower()

        # ---------------------------------------------------------------------
        # LAYER 1: Deterministic Scaffold & Infrastructure Generation (0 Token)
        # ---------------------------------------------------------------------
        base_project, target_slots = self.scaffold_gen.generate_scaffold(psir, custom_slots)
        current_files = dict(base_project.files)

        # ---------------------------------------------------------------------
        # LAYER 2: Minimal-Context Domain Slot Compilation
        # ---------------------------------------------------------------------
        context_packages: List[SlotContextPackage] = []
        for slot in target_slots:
            pkg = self.context_compiler.compile_slot_context(
                slot=slot,
                all_project_files=current_files,
                language=lang_str,
                model_family="claude"
            )
            context_packages.append(pkg)

        # ---------------------------------------------------------------------
        # LAYER 3: Agentic Slot Injection & AST Conformance Merging
        # ---------------------------------------------------------------------
        slot_results: List[SlotSynthesisResult] = []
        for slot, pkg in zip(target_slots, context_packages):
            current_files, res = self.injector.inject_slot(
                slot=slot,
                package=pkg,
                project_files=current_files
            )
            slot_results.append(res)

        final_project = GeneratedProject(
            project_root=base_project.project_root,
            files=current_files,
            build_command=base_project.build_command,
            run_command=base_project.run_command,
            test_command=base_project.test_command
        )

        # ---------------------------------------------------------------------
        # LAYER 4: Deterministic Verification & Non-Self-Certification Gate
        # ---------------------------------------------------------------------
        verification_report = self.verifier.verify_project(
            project_files=final_project.files,
            expected_slots=target_slots,
            execute_unit_tests=execute_unit_tests
        )

        wall_clock_seconds = time.perf_counter() - start_time

        # ---------------------------------------------------------------------
        # LAYER 5: Telemetry Economics & Cost-Benefit Benchmark
        # ---------------------------------------------------------------------
        telemetry = TelemetryEconomicsCalculator.compute_telemetry(
            project_name=psir.project_name,
            language=lang_str,
            project_files=final_project.files,
            slot_results=slot_results,
            context_packages=context_packages,
            verification_report=verification_report,
            wall_clock_seconds=wall_clock_seconds
        )

        markdown_report = telemetry.render_markdown_report()

        return HybridSynthesisOutcome(
            project=final_project,
            telemetry=telemetry,
            verification_report=verification_report,
            markdown_report=markdown_report
        )
