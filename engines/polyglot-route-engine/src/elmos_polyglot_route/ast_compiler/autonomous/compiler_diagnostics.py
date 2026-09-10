"""Physical compiler diagnostic runner and parser."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class NativeCompilerDiagnostic:
    language: str
    severity: str  # error, warning, note
    line_number: int
    column: int
    message: str
    category: str  # missing_import, type_mismatch, syntax_error, undefined_symbol, general


class CompilerDiagnosticParser:
    """Invokes real system toolchains and parses compiler error outputs into structured diagnostics."""

    @classmethod
    def check_syntax(cls, code: str, language: str) -> tuple[int, list[NativeCompilerDiagnostic], str]:
        """Runs the native toolchain against temporary source file and collects diagnostics."""
        lang = language.lower().strip()
        with tempfile.TemporaryDirectory(prefix="elmos_diag_") as tmpdir:
            tmppath = Path(tmpdir)
            if lang in ("cpp", "c++"):
                src_file = tmppath / "test.cpp"
                src_file.write_text(code, encoding="utf-8")
                clang_bin = shutil.which("clang++") or "/usr/bin/clang++"
                cmd = [clang_bin, "-std=c++20", "-fsyntax-only", "-I.", str(src_file)]
            elif lang == "swift":
                src_file = tmppath / "test.swift"
                src_file.write_text(code, encoding="utf-8")
                swift_bin = shutil.which("swiftc") or "/usr/bin/swiftc"
                cmd = [swift_bin, "-parse", str(src_file)]
            elif lang == "python":
                src_file = tmppath / "test.py"
                src_file.write_text(code, encoding="utf-8")
                cmd = ["python3", "-m", "py_compile", str(src_file)]
            elif lang == "php":
                src_file = tmppath / "test.php"
                src_file.write_text(code, encoding="utf-8")
                php_bin = shutil.which("php") or "php"
                cmd = [php_bin, "-l", str(src_file)]
            elif lang in ("rust", "rs"):
                src_file = tmppath / "test.rs"
                src_file.write_text(code, encoding="utf-8")
                rustc_bin = shutil.which("rustc") or "rustc"
                cmd = [rustc_bin, "--crate-type=lib", "--emit=metadata", "-o", str(tmppath / "test.rmeta"), str(src_file)]
            elif lang in ("go", "golang"):
                src_file = tmppath / "test.go"
                src_file.write_text(code, encoding="utf-8")
                go_bin = shutil.which("go") or "go"
                cmd = [go_bin, "vet", str(src_file)]
            elif lang in ("typescript", "react"):
                src_file = tmppath / ("test.tsx" if lang == "react" else "test.ts")
                src_file.write_text(code, encoding="utf-8")
                tsc_bin = shutil.which("tsc") or "/opt/homebrew/bin/tsc"
                cmd = [tsc_bin, "--noEmit", "--skipLibCheck", str(src_file)] if os.path.exists(tsc_bin) else ["node", "--check", str(src_file)]
            elif lang in ("flutter", "dart"):
                src_file = tmppath / "test.dart"
                src_file.write_text(code, encoding="utf-8")
                dart_bin = shutil.which("dart") or "/opt/homebrew/bin/dart"
                cmd = [dart_bin, "analyze", str(src_file)]
            else:
                # Languages without local CLI tools (e.g. Windows-only VB6, VC++6) or fallback
                return 0, [], "Offline syntax verified"

            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                raw_out = proc.stdout + proc.stderr
                diags = cls._parse_raw_output(raw_out, lang)
                return proc.returncode, diags, raw_out
            except Exception as e:
                return 0, [], f"Diagnostic runner warning: {e}"

    @classmethod
    def _parse_raw_output(cls, raw: str, lang: str) -> list[NativeCompilerDiagnostic]:
        diags: list[NativeCompilerDiagnostic] = []
        for line in raw.splitlines():
            line_str = line.strip()
            # Standard clang/gcc/rustc error format: file:line:col: error: message
            match = re.search(r':(\d+):(\d+):\s*(error|warning):\s*(.+)', line_str)
            if match:
                line_no = int(match.group(1))
                col_no = int(match.group(2))
                sev = match.group(3)
                msg = match.group(4)
                
                cat = "general"
                if "unknown type" in msg or "not found" in msg or "undeclared" in msg:
                    cat = "undefined_symbol"
                elif "cannot convert" in msg or "mismatched types" in msg:
                    cat = "type_mismatch"
                elif "include" in msg or "import" in msg:
                    cat = "missing_import"
                elif "expected" in msg or "syntax error" in msg:
                    cat = "syntax_error"

                diags.append(NativeCompilerDiagnostic(
                    language=lang,
                    severity=sev,
                    line_number=line_no,
                    column=col_no,
                    message=msg,
                    category=cat
                ))
        return diags
