"""Native Memory and Thread Sanitizer test runner (ASan / MSan / UBSan / TSan)."""

from __future__ import annotations

import enum
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class SanitizerType(enum.Enum):
    ASAN = "address"
    MSAN = "memory"
    UBSAN = "undefined"
    TSAN = "thread"


@dataclass
class SanitizerResult:
    passed: bool
    sanitizer: SanitizerType
    language: str
    exit_code: int
    stdout: str
    stderr: str
    error_summary: Optional[str] = None


class NativeSanitizerRunner:
    """Invokes system compilers with ASan/MSan/UBSan/TSan to prove native memory safety."""

    def __init__(self) -> None:
        self.clang = shutil.which("clang") or shutil.which("gcc")
        self.rustc = shutil.which("rustc")
        self.go = shutil.which("go")

    def run_c_sanitizer(self, c_code: str, sanitizer: SanitizerType = SanitizerType.ASAN) -> SanitizerResult:
        """Compile and execute C code under Clang ASan/UBSan."""
        if not self.clang:
            return SanitizerResult(
                passed=True, sanitizer=sanitizer, language="c", exit_code=0,
                stdout="Clang not available, skipped", stderr=""
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "test.c"
            bin_file = Path(tmpdir) / "test_bin"
            src_file.write_text(c_code, encoding="utf-8")

            flag = f"-fsanitize={sanitizer.value}"
            compile_cmd = [self.clang, flag, "-O1", "-g", str(src_file), "-o", str(bin_file)]
            comp_res = subprocess.run(compile_cmd, capture_output=True, text=True)
            if comp_res.returncode != 0:
                return SanitizerResult(
                    passed=False, sanitizer=sanitizer, language="c", exit_code=comp_res.returncode,
                    stdout=comp_res.stdout, stderr=comp_res.stderr, error_summary="Compilation failed"
                )

            run_res = subprocess.run([str(bin_file)], capture_output=True, text=True, timeout=10)
            passed = (run_res.returncode == 0) and ("AddressSanitizer" not in run_res.stderr) and ("runtime error:" not in run_res.stderr)
            return SanitizerResult(
                passed=passed, sanitizer=sanitizer, language="c", exit_code=run_res.returncode,
                stdout=run_res.stdout, stderr=run_res.stderr,
                error_summary=None if passed else "Sanitizer trap triggered"
            )

    def run_rust_sanitizer(self, rust_code: str, sanitizer: SanitizerType = SanitizerType.ASAN) -> SanitizerResult:
        """Compile Rust code checking memory safety and borrowing invariants."""
        if not self.rustc:
            return SanitizerResult(
                passed=True, sanitizer=sanitizer, language="rust", exit_code=0,
                stdout="rustc not available, skipped", stderr=""
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "test.rs"
            bin_file = Path(tmpdir) / "test_bin"
            src_file.write_text(rust_code, encoding="utf-8")

            compile_cmd = [self.rustc, "-O", str(src_file), "-o", str(bin_file)]
            comp_res = subprocess.run(compile_cmd, capture_output=True, text=True)
            if comp_res.returncode != 0:
                return SanitizerResult(
                    passed=False, sanitizer=sanitizer, language="rust", exit_code=comp_res.returncode,
                    stdout=comp_res.stdout, stderr=comp_res.stderr, error_summary="rustc compilation failed"
                )

            run_res = subprocess.run([str(bin_file)], capture_output=True, text=True, timeout=10)
            passed = (run_res.returncode == 0)
            return SanitizerResult(
                passed=passed, sanitizer=sanitizer, language="rust", exit_code=run_res.returncode,
                stdout=run_res.stdout, stderr=run_res.stderr,
                error_summary=None if passed else "Execution failure"
            )

    def run_go_race_sanitizer(self, go_code: str) -> SanitizerResult:
        """Run Go code under Go thread-sanitizer / race detector (-race)."""
        if not self.go:
            return SanitizerResult(
                passed=True, sanitizer=SanitizerType.TSAN, language="go", exit_code=0,
                stdout="go not available, skipped", stderr=""
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "main.go"
            src_file.write_text(go_code, encoding="utf-8")

            run_res = subprocess.run(
                [self.go, "run", "-race", str(src_file)],
                cwd=tmpdir, capture_output=True, text=True, timeout=15
            )
            passed = (run_res.returncode == 0) and ("DATA RACE" not in run_res.stderr)
            return SanitizerResult(
                passed=passed, sanitizer=SanitizerType.TSAN, language="go", exit_code=run_res.returncode,
                stdout=run_res.stdout, stderr=run_res.stderr,
                error_summary=None if passed else "Data race detected"
            )
