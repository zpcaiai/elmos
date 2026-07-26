from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import Language, RouteError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class ExactToolchain:
    language: Language
    version: str
    executable: str
    auxiliary: str | None = None


def _output(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(f"EXACT_TOOLCHAIN_UNAVAILABLE:{command[0]}") from error
    if completed.returncode != 0:
        raise RouteError(f"EXACT_TOOLCHAIN_UNAVAILABLE:{command[0]}")
    return (completed.stdout + completed.stderr).strip()


def _java_candidates() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("ELMOS_JAVA21_HOME", "").strip()
    if configured:
        candidates.append(Path(configured))
    java_home = Path("/usr/libexec/java_home")
    if java_home.is_file():
        try:
            resolved = _output([str(java_home), "-v", "21"])
            candidates.append(Path(resolved))
        except RouteError:
            pass
    candidates.extend(
        [
            Path("/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"),
            Path("/usr/local/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"),
            Path("/opt/java/openjdk-21"),
        ]
    )
    return list(dict.fromkeys(candidates))


def _java() -> ExactToolchain:
    for home in _java_candidates():
        java = home / "bin" / "java"
        javac = home / "bin" / "javac"
        if not java.is_file() or not javac.is_file():
            continue
        observed = _output([str(java), "-version"])
        if 'version "21.0.11"' in observed:
            return ExactToolchain("java", "21.0.11", str(java), str(javac))
    raise RouteError("EXACT_TOOLCHAIN_MISMATCH:java:expected=21.0.11")


def _python() -> ExactToolchain:
    observed = platform.python_version()
    if observed != "3.12.12":
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:python:expected=3.12.12:observed={observed}")
    return ExactToolchain("python", observed, sys.executable)


def _csharp() -> ExactToolchain:
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:dotnet")
    observed = _output([dotnet, "--version"])
    if observed != "10.0.301":
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:csharp:expected=10.0.301:observed={observed}")
    return ExactToolchain("csharp", observed, dotnet)


def _typescript() -> ExactToolchain:
    node = shutil.which("node")
    tsc = REPOSITORY_ROOT / "engines" / "frontend-client-engine" / "node_modules" / ".bin" / "tsc"
    if not node or not tsc.is_file():
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:typescript")
    node_version = _output([node, "--version"])
    typescript_version = _output([str(tsc), "--version"])
    if node_version != "v26.0.0" or typescript_version != "Version 5.9.2":
        raise RouteError(
            "EXACT_TOOLCHAIN_MISMATCH:typescript:"
            f"expected=Node26.0.0/TypeScript5.9.2:observed={node_version}/{typescript_version}"
        )
    return ExactToolchain("typescript", "5.9.2 / Node 26.0.0", node, str(tsc))


def exact_toolchain(language: Language) -> ExactToolchain:
    return {
        "java": _java,
        "python": _python,
        "csharp": _csharp,
        "typescript": _typescript,
    }[language]()
