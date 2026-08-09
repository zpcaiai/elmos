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


def _go() -> ExactToolchain:
    executable = shutil.which("go")
    if not executable:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:go")
    observed = _output([executable, "version"])
    parts = observed.split()
    supported_platforms = {"darwin/arm64", "linux/amd64"}
    if (
        len(parts) != 4
        or parts[:2] != ["go", "version"]
        or parts[2] != "go1.25.0"
        or parts[3] not in supported_platforms
    ):
        expected = "go version go1.25.0 {darwin/arm64|linux/amd64}"
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:go:expected={expected}:observed={observed}")
    return ExactToolchain("go", "1.25.0", executable)


def _rust() -> ExactToolchain:
    executable = shutil.which("rustc")
    cargo = shutil.which("cargo")
    if not executable or not cargo:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:rust")
    observed = _output([executable, "--version"])
    expected = "rustc 1.89.0 (29483883e 2025-08-04)"
    if observed != expected:
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:rust:expected={expected}:observed={observed}")
    return ExactToolchain("rust", "1.89.0", executable, cargo)


#: The clang and Swift builds ship with Xcode / the Linux toolchain rather
#: than being downloadable at a fixed URL the way the JDK and .NET SDK are, so
#: the exact build differs per machine. These stay pinned -- the engine still
#: refuses to run against an unverified toolchain -- but the pin is read from
#: the environment so a host can declare its own build without editing code.
#: Set them once per machine, e.g.
#:
#:   export ELMOS_CLANG_VERSION="$(clang --version | head -1)"
#:   export ELMOS_SWIFT_VERSION="$(swiftc --version | head -1)"
#:
#: An unset pin is a hard block, exactly like a version mismatch: this engine
#: never treats "whatever is installed" as evidence.
_CLANG_VERSION_VARIABLE = "ELMOS_CLANG_VERSION"
_SWIFT_VERSION_VARIABLE = "ELMOS_SWIFT_VERSION"


def _pinned(variable: str, language: Language) -> str:
    declared = os.environ.get(variable, "").strip()
    if not declared:
        raise RouteError(f"EXACT_TOOLCHAIN_PIN_MISSING:{language}:{variable}")
    return declared


def _clang(language: Language, executable_name: str) -> ExactToolchain:
    configured = os.environ.get("ELMOS_CLANG_HOME", "").strip()
    executable = (
        str(Path(configured) / "bin" / executable_name) if configured else shutil.which(executable_name)
    )
    if not executable or not Path(executable).is_file():
        raise RouteError(f"EXACT_TOOLCHAIN_UNAVAILABLE:{executable_name}")
    expected = _pinned(_CLANG_VERSION_VARIABLE, language)
    observed = _output([executable, "--version"]).splitlines()[0].strip()
    if observed != expected:
        raise RouteError(
            f"EXACT_TOOLCHAIN_MISMATCH:{language}:expected={expected}:observed={observed}"
        )
    return ExactToolchain(language, observed, executable)


def _cpp() -> ExactToolchain:
    return _clang("cpp", "clang++")


def _objc() -> ExactToolchain:
    # The same clang drives Objective-C; `-x objective-c` selects the mode
    # (see clang_analyzer.py), so the C driver is the right executable.
    return _clang("objc", "clang")


def _swift() -> ExactToolchain:
    executable = shutil.which("swiftc")
    if not executable:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:swiftc")
    expected = _pinned(_SWIFT_VERSION_VARIABLE, "swift")
    observed = _output([executable, "--version"]).splitlines()[0].strip()
    if observed != expected:
        raise RouteError(
            f"EXACT_TOOLCHAIN_MISMATCH:swift:expected={expected}:observed={observed}"
        )
    return ExactToolchain("swift", observed, executable)


def exact_toolchain(language: Language) -> ExactToolchain:
    return {
        "java": _java,
        "python": _python,
        "csharp": _csharp,
        "typescript": _typescript,
        "go": _go,
        "rust": _rust,
        "cpp": _cpp,
        "objc": _objc,
        "swift": _swift,
    }[language]()
