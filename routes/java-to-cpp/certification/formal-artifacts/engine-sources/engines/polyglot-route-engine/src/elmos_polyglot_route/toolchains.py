from __future__ import annotations

import hashlib
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
    profile: tuple[str, ...] = ()
    executable_sha256: str | None = None


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


#: Native evidence is pinned to the exact Xcode toolchain used to qualify this
#: engine.  Environment variables may repeat these values for CI clarity, but
#: cannot replace them with a host-local declaration.  A different Xcode,
#: SDK, architecture, binary digest, or language profile fails closed.
_CLANG_VERSION_VARIABLE = "ELMOS_CLANG_VERSION"
_SWIFT_VERSION_VARIABLE = "ELMOS_SWIFT_VERSION"
_EXPECTED_CLANG_VERSION = "Apple clang version 21.0.0 (clang-2100.1.1.101)"
_EXPECTED_SWIFT_VERSION = "Apple Swift version 6.3.3 (swiftlang-6.3.3.1.3 clang-2100.1.1.101)"
_EXPECTED_SWIFT_TARGET = "Target: arm64-apple-macosx26.0"
_EXPECTED_XCODE = "Xcode 26.6\nBuild version 17F113"
_EXPECTED_MACOS_SDK = "26.5"
_EXPECTED_CLANG_SHA256 = "7def90dd8829726686213a747fc5bff1583df933dae5edc55d755479e0bfe00a"
_EXPECTED_SWIFTC_SHA256 = "2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb"


def _pinned(variable: str, language: Language, repository_pin: str) -> str:
    declared = os.environ.get(variable, repository_pin).strip()
    if declared != repository_pin:
        raise RouteError(
            f"EXACT_TOOLCHAIN_DECLARED_PIN_MISMATCH:{language}:expected={repository_pin}:declared={declared}"
        )
    return repository_pin


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _apple_profile(language: Language) -> tuple[str, ...]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            f"EXACT_TOOLCHAIN_PLATFORM_MISMATCH:{language}:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    xcodebuild = shutil.which("xcodebuild")
    xcrun = shutil.which("xcrun")
    if not xcodebuild or not xcrun:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:xcodebuild/xcrun")
    observed_xcode = _output([xcodebuild, "-version"])
    sdk_version = _output([xcrun, "--sdk", "macosx", "--show-sdk-version"])
    sdk_path = Path(_output([xcrun, "--sdk", "macosx", "--show-sdk-path"]))
    if observed_xcode != _EXPECTED_XCODE or sdk_version != _EXPECTED_MACOS_SDK:
        raise RouteError(
            f"EXACT_TOOLCHAIN_APPLE_PROFILE_MISMATCH:{language}:"
            f"expected={_EXPECTED_XCODE.replace(chr(10), '/')}/sdk={_EXPECTED_MACOS_SDK}:"
            f"observed={observed_xcode.replace(chr(10), '/')}/sdk={sdk_version}"
        )
    foundation = sdk_path / "System/Library/Frameworks/Foundation.framework/Headers/Foundation.h"
    objc_runtime = sdk_path / "usr/include/objc/objc.h"
    if sdk_path.name != "MacOSX26.5.sdk" or not foundation.is_file() or not objc_runtime.is_file():
        raise RouteError(f"EXACT_TOOLCHAIN_APPLE_SDK_INCOMPLETE:{language}:{sdk_path}")
    return (
        "platform=Darwin/arm64",
        "xcode=26.6/17F113",
        "macosx-sdk=26.5",
        f"sdk-path={sdk_path}",
    )


def _clang(language: Language, executable_name: str) -> ExactToolchain:
    configured = os.environ.get("ELMOS_CLANG_HOME", "").strip()
    executable: str | None
    if configured:
        executable = str(Path(configured) / "bin" / executable_name)
    else:
        xcrun = shutil.which("xcrun")
        executable = _output([xcrun, "--find", executable_name]) if xcrun else None
    if not executable or not Path(executable).is_file():
        raise RouteError(f"EXACT_TOOLCHAIN_UNAVAILABLE:{executable_name}")
    expected = _pinned(_CLANG_VERSION_VARIABLE, language, _EXPECTED_CLANG_VERSION)
    observed = _output([executable, "--version"]).splitlines()[0].strip()
    executable_digest = _sha256(Path(executable).resolve())
    if observed != expected or executable_digest != _EXPECTED_CLANG_SHA256:
        raise RouteError(
            f"EXACT_TOOLCHAIN_MISMATCH:{language}:expected={expected}/sha256={_EXPECTED_CLANG_SHA256}:"
            f"observed={observed}/sha256={executable_digest}"
        )
    standard = "c++20" if language == "cpp" else "c17/objc-arc/Foundation/Apple-runtime"
    return ExactToolchain(
        language,
        observed,
        executable,
        profile=(*_apple_profile(language), standard),
        executable_sha256=executable_digest,
    )


def _cpp() -> ExactToolchain:
    return _clang("cpp", "clang++")


def _objc() -> ExactToolchain:
    # The same clang drives Objective-C; `-x objective-c` selects the mode
    # (see clang_analyzer.py), so the C driver is the right executable.
    return _clang("objc", "clang")


def _swift() -> ExactToolchain:
    xcrun = shutil.which("xcrun")
    executable = _output([xcrun, "--find", "swiftc"]) if xcrun else None
    if not executable:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:swiftc")
    expected = _pinned(_SWIFT_VERSION_VARIABLE, "swift", _EXPECTED_SWIFT_VERSION)
    version_lines = _output([executable, "--version"]).splitlines()
    observed = version_lines[0].strip() if version_lines else ""
    observed_target = version_lines[1].strip() if len(version_lines) > 1 else ""
    executable_digest = _sha256(Path(executable).resolve())
    if (
        observed != expected
        or observed_target != _EXPECTED_SWIFT_TARGET
        or executable_digest != _EXPECTED_SWIFTC_SHA256
    ):
        raise RouteError(
            f"EXACT_TOOLCHAIN_MISMATCH:swift:expected={expected}/{_EXPECTED_SWIFT_TARGET}/"
            f"sha256={_EXPECTED_SWIFTC_SHA256}:observed={observed}/{observed_target}/"
            f"sha256={executable_digest}"
        )
    return ExactToolchain(
        "swift",
        observed,
        executable,
        profile=(*_apple_profile("swift"), "swift-language-mode=6", "integer=Int64"),
        executable_sha256=executable_digest,
    )


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
