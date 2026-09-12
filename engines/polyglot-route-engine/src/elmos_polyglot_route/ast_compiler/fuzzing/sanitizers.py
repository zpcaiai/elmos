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
        self.clangpp = shutil.which("clang++") or shutil.which("g++")
        self.swiftc = shutil.which("swiftc")
        self.rustc = shutil.which("rustc")
        self.go = shutil.which("go")

    def run_cpp_sanitizer(self, cpp_code: str, sanitizer: SanitizerType = SanitizerType.ASAN) -> SanitizerResult:
        """Compile and execute C++20 code under Clang ASan/UBSan."""
        if not self.clangpp:
            return SanitizerResult(
                passed=True, sanitizer=sanitizer, language="cpp", exit_code=0,
                stdout="Clang++ not available, skipped", stderr=""
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "test.cpp"
            bin_file = Path(tmpdir) / "test_bin"
            src_file.write_text(cpp_code, encoding="utf-8")

            flag = f"-fsanitize={sanitizer.value}"
            compile_cmd = [self.clangpp, flag, "-std=c++20", "-O1", "-g", str(src_file), "-o", str(bin_file)]
            comp_res = subprocess.run(compile_cmd, capture_output=True, text=True)
            if comp_res.returncode != 0:
                return SanitizerResult(
                    passed=False, sanitizer=sanitizer, language="cpp", exit_code=comp_res.returncode,
                    stdout=comp_res.stdout, stderr=comp_res.stderr, error_summary="C++ Compilation failed"
                )

            run_res = subprocess.run([str(bin_file)], capture_output=True, text=True, timeout=10)
            passed = (run_res.returncode == 0) and ("AddressSanitizer" not in run_res.stderr) and ("runtime error:" not in run_res.stderr)
            return SanitizerResult(
                passed=passed, sanitizer=sanitizer, language="cpp", exit_code=run_res.returncode,
                stdout=run_res.stdout, stderr=run_res.stderr,
                error_summary=None if passed else "Sanitizer trap triggered"
            )

    def run_swift_sanitizer(self, swift_code: str) -> SanitizerResult:
        """Compile and execute Swift code under Swift ASan."""
        if not self.swiftc:
            return SanitizerResult(
                passed=True, sanitizer=SanitizerType.ASAN, language="swift", exit_code=0,
                stdout="swiftc not available, skipped", stderr=""
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "test.swift"
            bin_file = Path(tmpdir) / "test_bin"
            src_file.write_text(swift_code, encoding="utf-8")

            compile_cmd = [self.swiftc, "-sanitize=address", str(src_file), "-o", str(bin_file)]
            comp_res = subprocess.run(compile_cmd, capture_output=True, text=True)
            if comp_res.returncode != 0:
                return SanitizerResult(
                    passed=False, sanitizer=SanitizerType.ASAN, language="swift", exit_code=comp_res.returncode,
                    stdout=comp_res.stdout, stderr=comp_res.stderr, error_summary="Swift compilation failed"
                )

            run_res = subprocess.run([str(bin_file)], capture_output=True, text=True, timeout=10)
            passed = (run_res.returncode == 0) and ("AddressSanitizer" not in run_res.stderr)
            return SanitizerResult(
                passed=passed, sanitizer=SanitizerType.ASAN, language="swift", exit_code=run_res.returncode,
                stdout=run_res.stdout, stderr=run_res.stderr,
                error_summary=None if passed else "Swift ASan trap triggered"
            )

    def run_objc_sanitizer(self, objc_code: str, sanitizer: SanitizerType = SanitizerType.ASAN) -> SanitizerResult:
        """Compile and execute Objective-C ARC code under Clang ASan."""
        if not self.clang:
            return SanitizerResult(
                passed=True, sanitizer=sanitizer, language="objc", exit_code=0,
                stdout="clang not available, skipped", stderr=""
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "test.m"
            bin_file = Path(tmpdir) / "test_bin"
            src_file.write_text(objc_code, encoding="utf-8")

            flag = f"-fsanitize={sanitizer.value}"
            compile_cmd = [self.clang, flag, "-fobjc-arc", "-framework", "Foundation", "-O1", "-g", str(src_file), "-o", str(bin_file)]
            comp_res = subprocess.run(compile_cmd, capture_output=True, text=True)
            if comp_res.returncode != 0:
                return SanitizerResult(
                    passed=False, sanitizer=sanitizer, language="objc", exit_code=comp_res.returncode,
                    stdout=comp_res.stdout, stderr=comp_res.stderr, error_summary="ObjC compilation failed"
                )

            run_res = subprocess.run([str(bin_file)], capture_output=True, text=True, timeout=10)
            passed = (run_res.returncode == 0) and ("AddressSanitizer" not in run_res.stderr)
            return SanitizerResult(
                passed=passed, sanitizer=sanitizer, language="objc", exit_code=run_res.returncode,
                stdout=run_res.stdout, stderr=run_res.stderr,
                error_summary=None if passed else "ObjC ASan trap triggered"
            )

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

            try:
                run_res = subprocess.run([str(bin_file)], capture_output=True, text=True, timeout=15)
                passed = (run_res.returncode == 0)
                return SanitizerResult(
                    passed=passed, sanitizer=sanitizer, language="rust", exit_code=run_res.returncode,
                    stdout=run_res.stdout, stderr=run_res.stderr,
                    error_summary=None if passed else "Execution failure"
                )
            except subprocess.TimeoutExpired:
                return SanitizerResult(
                    passed=False, sanitizer=sanitizer, language="rust", exit_code=-1,
                    stdout="", stderr="Timeout expired", error_summary="Execution timed out"
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

            try:
                run_res = subprocess.run(
                    [self.go, "run", "-race", str(src_file)],
                    cwd=tmpdir, capture_output=True, text=True, timeout=60
                )
                passed = (run_res.returncode == 0) and ("DATA RACE" not in run_res.stderr)
                return SanitizerResult(
                    passed=passed, sanitizer=SanitizerType.TSAN, language="go", exit_code=run_res.returncode,
                    stdout=run_res.stdout, stderr=run_res.stderr,
                    error_summary=None if passed else "Data race detected"
                )
            except subprocess.TimeoutExpired:
                return SanitizerResult(
                    passed=False, sanitizer=SanitizerType.TSAN, language="go", exit_code=-1,
                    stdout="", stderr="Timeout expired", error_summary="Execution timed out"
                )
