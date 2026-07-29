from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .clang_analyzer import analyze_clang
from .models import Language, RouteError, SemanticIR
from .python_analyzer import analyze_python
from .toolchains import exact_toolchain

ENGINE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]


def _run(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["NO_COLOR"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{command[0]}:{detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RouteError(f"NATIVE_ANALYZER_INVALID_JSON:{command[0]}") from error
    if not isinstance(value, dict):
        raise RouteError("NATIVE_ANALYZER_OBJECT_REQUIRED")
    return value


def analyze(source: Path, language: Language, function_name: str) -> SemanticIR:
    source = source.resolve()
    if not source.is_file() or source.is_symlink() or source.stat().st_size > 2_000_000:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    toolchain = exact_toolchain(language)
    if language == "python":
        return analyze_python(source, function_name)
    if language in ("cpp", "objc"):
        return analyze_clang(source, language, function_name, toolchain.executable, toolchain.version)
    if language == "swift":
        # Swift source analysis needs a SwiftSyntax-backed helper, the same
        # shape as the Roslyn and TypeScript Compiler API helpers this engine
        # already shells out to. Until that helper exists and has been run
        # against a pinned toolchain, Swift is a *target* only: this fails
        # closed rather than falling back on a text-level parse.
        raise RouteError("SWIFT_SOURCE_ANALYZER_NOT_AVAILABLE")
    if language == "java":
        helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
        value = _run(
            [toolchain.executable, "--source", "21", str(helper), str(source), function_name],
            cwd=ENGINE_ROOT,
        )
    elif language == "csharp":
        project = REPOSITORY_ROOT / "engines" / "dotnet-engine" / "src" / "Elmos.Dotnet.SemanticCli"
        value = _run(
            [toolchain.executable, "run", "--project", str(project), "--", str(source), function_name],
            cwd=REPOSITORY_ROOT,
        )
    else:
        frontend = REPOSITORY_ROOT / "engines" / "frontend-client-engine"
        cli = frontend / "dist" / "src" / "polyglot-cli.js"
        if not cli.is_file():
            pnpm = shutil.which("pnpm")
            if pnpm is None:
                raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:pnpm")
            completed = subprocess.run(
                [pnpm, "run", "build"],
                cwd=frontend,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if completed.returncode != 0:
                raise RouteError("TYPESCRIPT_ANALYZER_BUILD_FAILED:" + completed.stderr[-2_000:])
        value = _run([toolchain.executable, str(cli), str(source), function_name], cwd=frontend)
    return SemanticIR.from_mapping(value)
