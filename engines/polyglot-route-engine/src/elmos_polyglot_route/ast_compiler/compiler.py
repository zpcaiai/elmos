"""Universal AST Compiler orchestrating Parsing, IR Transformation, Lowering, Shimming, Emitting, and L4 Autonomous Self-Repair."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from .ir import UniversalModule
from .parsers import get_parser
from .lowering import SemanticLoweringEngine
from .shims import ShimRegistry
from .emitters import get_emitter
from .autonomous import AutonomousRepairLoop, RepairResult


class UniversalAstCompiler:
    """Production Universal AST Semantic Compiler supporting all 210 bidirectional polyglot routes (15 languages) with L4 self-repair."""

    def __init__(self) -> None:
        self.lowering_engine = SemanticLoweringEngine()
        self.shim_registry = ShimRegistry()

    def parse_to_ir(self, source_code: str, source_lang: str) -> UniversalModule:
        """Parse source code into the canonical Universal AST IR."""
        parser = get_parser(source_lang)
        return parser.parse(source_code)

    def lower_module(self, module: UniversalModule, source_lang: str, target_lang: str) -> UniversalModule:
        """Apply semantic hazard lowering across object lifecycle, concurrency, exceptions, frameworks, and UI."""
        return self.lowering_engine.lower(module, source_lang, target_lang)

    def emit_from_ir(self, module: UniversalModule, target_lang: str) -> str:
        """Emit idiomatic, production-grade target language source code."""
        emitter = get_emitter(target_lang)
        return emitter.emit_module(module)

    def compile(
        self,
        source_code: str,
        source_lang: str,
        target_lang: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Full multi-stage AST compilation pipeline from source to target language."""
        opts = options or {}

        # Stage 1: Parse to Universal AST IR
        ir_module = self.parse_to_ir(source_code, source_lang)

        # Stage 2: Semantic Hazard Lowering
        lowered_ir = self.lower_module(ir_module, source_lang, target_lang)

        # Stage 3: Code Emission
        emitted_code = self.emit_from_ir(lowered_ir, target_lang)

        # Stage 4: Optional L4 Autonomous Self-Repair Loop
        if opts.get("auto_repair", False):
            repair_result = AutonomousRepairLoop.run(emitted_code, target_lang)
            return repair_result.final_code

        return emitted_code

    def compile_with_diagnostics(
        self,
        source_code: str,
        source_lang: str,
        target_lang: str,
    ) -> Tuple[str, RepairResult]:
        """Compile and execute physical compiler diagnostics and autonomous self-repair."""
        emitted_code = self.compile(source_code, source_lang, target_lang, options={"auto_repair": False})
        repair_res = AutonomousRepairLoop.run(emitted_code, target_lang)
        return repair_res.final_code, repair_res


# Global shared instance
default_compiler = UniversalAstCompiler()


def compile_polyglot_ast(source_code: str, source_lang: str, target_lang: str, auto_repair: bool = False) -> str:
    """Convenience functional API for AST compilation."""
    return default_compiler.compile(source_code, source_lang, target_lang, options={"auto_repair": auto_repair})

