"""Level 4 Autonomous Self-Healing and Repair Loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Any
from .compiler_diagnostics import CompilerDiagnosticParser, NativeCompilerDiagnostic


@dataclass
class RepairFix:
    iteration: int
    rule: str
    description: str
    diff_summary: str


@dataclass
class RepairResult:
    status: str  # clean, auto_repaired, blocked
    iterations: int
    final_code: str
    fixes: list[RepairFix] = field(default_factory=list)
    remaining_diagnostics: list[NativeCompilerDiagnostic] = field(default_factory=list)


class AutonomousRepairLoop:
    """Iterative compiler-driven diagnostic and self-repair loop."""

    MAX_ITERATIONS = 3

    @classmethod
    def run(cls, initial_code: str, target_lang: str) -> RepairResult:
        current_code = initial_code
        fixes: list[RepairFix] = []

        for i in range(1, cls.MAX_ITERATIONS + 1):
            ret_code, diags, raw_out = CompilerDiagnosticParser.check_syntax(current_code, target_lang)
            if ret_code == 0 and not any(d.severity == "error" for d in diags):
                # Clean compilation
                return RepairResult(
                    status="clean" if i == 1 else "auto_repaired",
                    iterations=i - 1,
                    final_code=current_code,
                    fixes=fixes,
                    remaining_diagnostics=[]
                )

            # Analyze errors and apply automated repair heuristic
            repaired = False
            new_code = current_code
            for d in diags:
                if d.category == "undefined_symbol" or "header" in d.message.lower():
                    # Check missing standard header in C++
                    if target_lang in ("cpp", "c++") and "#include <algorithm>" not in new_code and "std::min" in d.message:
                        new_code = "#include <algorithm>\n" + new_code
                        fixes.append(RepairFix(
                            iteration=i,
                            rule="missing_header_injection",
                            description="Automatically injected missing <algorithm> header",
                            diff_summary="+ #include <algorithm>"
                        ))
                        repaired = True
                        break
                    elif target_lang in ("cpp", "c++") and "#include <cmath>" not in new_code and "abs" in d.message:
                        new_code = "#include <cmath>\n" + new_code
                        fixes.append(RepairFix(
                            iteration=i,
                            rule="missing_header_injection",
                            description="Automatically injected missing <cmath> header",
                            diff_summary="+ #include <cmath>"
                        ))
                        repaired = True
                        break

                elif d.category == "type_mismatch":
                    # Fix return mismatch if return has wrong default
                    if target_lang in ("cpp", "c++") and "return {};" in new_code and "std::future" in d.message:
                        new_code = new_code.replace("return {};", "return std::async(std::launch::deferred, [] { return {}; });")
                        fixes.append(RepairFix(
                            iteration=i,
                            rule="async_return_wrapping",
                            description="Wrapped return in std::async deferred future",
                            diff_summary="return {} -> return std::async(...)"
                        ))
                        repaired = True
                        break

            if repaired:
                current_code = new_code
            else:
                # Cannot automatically resolve further, break to fail closed
                break

        # Final check
        ret_code, diags, raw_out = CompilerDiagnosticParser.check_syntax(current_code, target_lang)
        final_status = "auto_repaired" if (ret_code == 0 and not any(d.severity == "error" for d in diags)) else "blocked"
        return RepairResult(
            status=final_status,
            iterations=len(fixes),
            final_code=current_code,
            fixes=fixes,
            remaining_diagnostics=diags
        )
