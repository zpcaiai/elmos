"""Physical compiler diagnostic runner and parser for 15 languages."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..legacy_env.vb6_validator import Vb6StrictSemanticValidator
from ..legacy_env.kotlin_validator import KotlinStrictSemanticValidator


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

    _CSC_DLL: Optional[str] = None
    _CORE_LIB: Optional[str] = None
    _RUNTIME_LIB: Optional[str] = None

    @classmethod
    def _init_dotnet_paths(cls) -> None:
        if cls._CSC_DLL is not None:
            return
        cscs = glob.glob("/opt/homebrew/Cellar/dotnet/**/Roslyn/bincore/csc.dll", recursive=True)
        corelibs = glob.glob("/opt/homebrew/Cellar/dotnet/**/shared/Microsoft.NETCore.App/**/System.Private.CoreLib.dll", recursive=True)
        runtimes = glob.glob("/opt/homebrew/Cellar/dotnet/**/shared/Microsoft.NETCore.App/**/System.Runtime.dll", recursive=True)
        if cscs:
            cls._CSC_DLL = cscs[0]
        if corelibs:
            cls._CORE_LIB = corelibs[0]
        if runtimes:
            cls._RUNTIME_LIB = runtimes[0]

    @classmethod
    def detect_available_compilers(cls) -> list[str]:
        compilers = ["clang++", "swiftc", "python3", "php", "rustc", "go", "tsc", "dart", "javac", "dotnet", "clang"]
        found = []
        for c in compilers:
            if shutil.which(c) is not None:
                found.append(c)
        return found

    @classmethod
    def check_syntax(cls, code: str, language: str) -> tuple[int, list[NativeCompilerDiagnostic], str]:
        """Runs the native toolchain against temporary source file and collects diagnostics."""
        lang = language.lower().strip()

        # In-tree strict validators
        if lang in ("vb6", "vb"):
            ret_code, diags = Vb6StrictSemanticValidator.validate(code)
            native_diags = [
                NativeCompilerDiagnostic(
                    language="vb6",
                    severity="error",
                    line_number=d.line,
                    column=d.column,
                    message=d.message,
                    category=d.category
                ) for d in diags
            ]
            return ret_code, native_diags, f"VB6 Strict Validation: {len(diags)} diagnostics"

        if lang in ("kotlin", "kt"):
            ret_code, diags = KotlinStrictSemanticValidator.validate(code)
            native_diags = [
                NativeCompilerDiagnostic(
                    language="kotlin",
                    severity="error",
                    line_number=d.line,
                    column=d.column,
                    message=d.message,
                    category=d.category
                ) for d in diags
            ]
            return ret_code, native_diags, f"Kotlin Strict Validation: {len(diags)} diagnostics"

        with tempfile.TemporaryDirectory(prefix="elmos_diag_") as tmpdir:
            tmppath = Path(tmpdir)

            if lang in ("cpp", "c++"):
                src_file = tmppath / "test.cpp"
                src_file.write_text(code, encoding="utf-8")
                clang_bin = shutil.which("clang++") or "/usr/bin/clang++"
                cmd = [clang_bin, "-std=c++20", "-fsyntax-only", "-I.", str(src_file)]

            elif lang in ("vcpp6", "mfc"):
                src_file = tmppath / "test.cpp"
                src_file.write_text(code, encoding="utf-8")
                clang_bin = shutil.which("clang++") or "/usr/bin/clang++"
                mfc_dir = Path(__file__).resolve().parent.parent / "legacy_env" / "mfc_headers"
                cmd = [clang_bin, "-std=c++20", "-fsyntax-only", f"-I{mfc_dir}", "-x", "c++", str(src_file)]

            elif lang in ("objc", "objective-c"):
                src_file = tmppath / "test.m"
                src_file.write_text(code, encoding="utf-8")
                clang_bin = shutil.which("clang") or "/usr/bin/clang"
                cmd = [clang_bin, "-fsyntax-only", "-fobjc-arc", "-x", "objective-c", str(src_file)]

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

            elif lang in ("typescript", "ts", "react"):
                src_file = tmppath / ("test.tsx" if lang == "react" else "test.ts")
                src_file.write_text(code, encoding="utf-8")
                tsc_bin = shutil.which("tsc") or "/opt/homebrew/bin/tsc"
                cmd = [tsc_bin, "--noEmit", "--skipLibCheck", str(src_file)] if os.path.exists(tsc_bin) else ["node", "--check", str(src_file)]

            elif lang in ("flutter", "dart"):
                src_file = tmppath / "test.dart"
                src_file.write_text(code, encoding="utf-8")
                # Configure hermetic package_config for flutter package resolution
                dart_tool = tmppath / ".dart_tool"
                dart_tool.mkdir(exist_ok=True)
                shim_root = Path(__file__).resolve().parent.parent / "legacy_env" / "flutter_shim"
                pkg_cfg = {
                    "configVersion": 2,
                    "packages": [
                        {
                            "name": "flutter",
                            "rootUri": shim_root.as_uri(),
                            "packageUri": "lib/",
                            "languageVersion": "3.0"
                        }
                    ]
                }
                import json
                (dart_tool / "package_config.json").write_text(json.dumps(pkg_cfg), encoding="utf-8")
                dart_bin = shutil.which("dart") or "/opt/homebrew/bin/dart"
                cmd = [dart_bin, "analyze", str(src_file)]

            elif lang == "java":
                src_file = tmppath / "OrderProcessor.java"
                src_file.write_text(code, encoding="utf-8")
                javac_bin = shutil.which("javac") or "/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home/bin/javac"
                cmd = [javac_bin, "-d", str(tmppath), str(src_file)]

            elif lang in ("csharp", "cs"):
                src_file = tmppath / "Test.cs"
                src_file.write_text(code, encoding="utf-8")
                cls._init_dotnet_paths()
                if cls._CSC_DLL and cls._CORE_LIB:
                    cmd = [
                        "dotnet", "exec", cls._CSC_DLL,
                        "-target:library", "-nologo",
                        f"-r:{cls._CORE_LIB}",
                        f"-r:{cls._RUNTIME_LIB}" if cls._RUNTIME_LIB else "",
                        str(src_file)
                    ]
                    cmd = [arg for arg in cmd if arg]
                else:
                    cmd = ["dotnet", "build"]

            else:
                return 0, [], f"Unsupported language: {lang}"

            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                raw_out = proc.stdout + proc.stderr
                diags = cls._parse_raw_output(raw_out, lang, ret_code=proc.returncode)
                return proc.returncode, diags, raw_out
            except Exception as e:
                return 0, [], f"Diagnostic runner warning: {e}"

    @classmethod
    def _parse_raw_output(cls, raw: str, lang: str, ret_code: int = 0) -> list[NativeCompilerDiagnostic]:
        diags: list[NativeCompilerDiagnostic] = []
        for line in raw.splitlines():
            line_str = line.strip()

            # 1. Standard clang/gcc/rustc/swiftc format: file:line:col: error: message
            match1 = re.search(r':(\d+):(\d+):\s*(error|warning):\s*(.+)', line_str)
            if match1:
                line_no = int(match1.group(1))
                col_no = int(match1.group(2))
                sev = match1.group(3)
                msg = match1.group(4)
                cat = cls._categorize_message(msg)
                diags.append(NativeCompilerDiagnostic(lang, sev, line_no, col_no, msg, cat))
                continue

            # 2. Rustc error format: error[E0412]: message or error: message
            match_rust = re.match(r'error(?:\[[A-Za-z0-9]+\])?:\s*(.+)', line_str)
            if match_rust:
                msg = match_rust.group(1)
                line_no, col_no = 1, 1
                raw_lines = raw.splitlines()
                idx_in_raw = raw_lines.index(line) if line in raw_lines else -1
                if idx_in_raw != -1:
                    for n_i in range(idx_in_raw + 1, min(idx_in_raw + 4, len(raw_lines))):
                        loc_m = re.search(r'-->\s*[^:]+:(\d+):(\d+)', raw_lines[n_i])
                        if loc_m:
                            line_no = int(loc_m.group(1))
                            col_no = int(loc_m.group(2))
                            break
                cat = cls._categorize_message(msg)
                diags.append(NativeCompilerDiagnostic(lang, "error", line_no, col_no, msg, cat))
                continue

            # 3. Go vet format: [vet: ]file:line:col: message
            match_go = re.search(r'(?:vet:\s*)?[^:\s]+:(\d+):(\d+):\s*(.+)', line_str)
            if match_go and not line_str.startswith("#"):
                line_no = int(match_go.group(1))
                col_no = int(match_go.group(2))
                msg = match_go.group(3)
                cat = cls._categorize_message(msg)
                diags.append(NativeCompilerDiagnostic(lang, "error", line_no, col_no, msg, cat))
                continue

            # 4. Javac format: file:line: error: message
            match2 = re.search(r':(\d+):\s*(error|warning):\s*(.+)', line_str)
            if match2:
                line_no = int(match2.group(1))
                sev = match2.group(2)
                msg = match2.group(3)
                # Lookahead for symbol details
                raw_lines = raw.splitlines()
                idx_in_raw = raw_lines.index(line) if line in raw_lines else -1
                if idx_in_raw != -1:
                    for next_idx in range(idx_in_raw + 1, min(idx_in_raw + 4, len(raw_lines))):
                        if "symbol:" in raw_lines[next_idx]:
                            msg += " " + raw_lines[next_idx].strip()
                            break
                cat = cls._categorize_message(msg)
                diags.append(NativeCompilerDiagnostic(lang, sev, line_no, 1, msg, cat))
                continue

            # 5. Roslyn C# csc format: file(line,col): error CODE: message
            match3 = re.search(r'\((\d+),(\d+)\):\s*(error|warning)\s+[A-Za-z0-9]+:\s*(.+)', line_str)
            if match3:
                line_no = int(match3.group(1))
                col_no = int(match3.group(2))
                sev = match3.group(3)
                msg = match3.group(4)
                cat = cls._categorize_message(msg)
                diags.append(NativeCompilerDiagnostic(lang, sev, line_no, col_no, msg, cat))
                continue

            # 6. Dart analyze format: error • message • file:line:col
            match4 = re.search(r'(error|warning)\s*•\s*(.+?)\s*•\s*[^:]+:(\d+):(\d+)', line_str)
            if match4:
                sev = match4.group(1)
                msg = match4.group(2)
                line_no = int(match4.group(3))
                col_no = int(match4.group(4))
                cat = cls._categorize_message(msg)
                diags.append(NativeCompilerDiagnostic(lang, sev, line_no, col_no, msg, cat))
                continue

            # 7. PHP lint format: Parse error: message in file on line X
            match5 = re.search(r'Parse error:\s*(.+?)\s*in\s+.+?\s+on line\s*(\d+)', line_str)
            if match5:
                msg = match5.group(1)
                line_no = int(match5.group(2))
                cat = "syntax_error"
                diags.append(NativeCompilerDiagnostic(lang, "error", line_no, 1, msg, cat))
                continue

        # Fallback for unparsed error output when compiler returned non-zero
        if ret_code != 0 and not diags and raw.strip():
            for line in raw.splitlines():
                l_s = line.strip()
                if not l_s or l_s.startswith("#") or l_s.startswith("-->") or l_s.startswith("|") or "no syntax error" in l_s.lower():
                    continue
                cat = cls._categorize_message(l_s)
                diags.append(NativeCompilerDiagnostic(lang, "error", 1, 1, l_s, cat))
                break
            if not diags and "no syntax error" not in raw.lower():
                cat = cls._categorize_message(raw)
                diags.append(NativeCompilerDiagnostic(lang, "error", 1, 1, raw.strip()[:300], cat))

        return diags

    @classmethod
    def _categorize_message(cls, msg: str) -> str:
        low = msg.lower()
        if "unknown type" in low or "not found" in low or "undeclared" in low or "no member named" in low or "cannot find symbol" in low or "cannot find type" in low or "undefined" in low:
            return "undefined_symbol"
        elif "cannot convert" in low or "mismatched types" in low or "type mismatch" in low or "incompatible types" in low:
            return "type_mismatch"
        elif "include" in low or "import" in low or "using directive" in low or "package does not exist" in low:
            return "missing_import"
        elif "expected" in low or "syntax error" in low or "semicolon" in low:
            return "syntax_error"
        return "general"

