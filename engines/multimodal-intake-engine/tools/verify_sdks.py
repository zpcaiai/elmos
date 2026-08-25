#!/usr/bin/env python3
"""Compile the checked-in multimodal SDKs with bounded local toolchains.

This verifier performs no provider, network, upload, or production operation.
It compiles the public TypeScript and Java clients in an isolated temporary
directory so the release target cannot pass while either SDK has drifted away
from its declared language contract.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]
TYPESCRIPT_CLIENT = REPOSITORY_ROOT / "sdk" / "multimodal-intake" / "typescript" / "client.ts"
JAVA_SOURCE_ROOT = (
    REPOSITORY_ROOT / "sdk" / "multimodal-intake" / "java" / "src" / "main" / "java"
)


def _required_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"{label} must be a regular non-symlink file: {path}")
    return path


def _executable(candidate: str | None, label: str) -> Path:
    if not candidate:
        raise SystemExit(f"required {label} executable is unavailable")
    path = Path(candidate).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise SystemExit(f"required {label} executable is not executable: {path}")
    return path


def _run(command: list[str]) -> None:
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        output = result.stdout[-16_384:]
        raise SystemExit(
            f"SDK compiler failed with exit {result.returncode}: {command[0]}\n{output}"
        )


def _typescript_compiler() -> Path:
    configured = os.environ.get("ELMOS_MULTIMODAL_TSC")
    if configured:
        return _executable(configured, "TypeScript compiler")
    repository_compiler = REPOSITORY_ROOT / "apps" / "web-console" / "node_modules" / ".bin" / "tsc"
    if repository_compiler.is_file():
        return _executable(str(repository_compiler), "TypeScript compiler")
    return _executable(shutil.which("tsc"), "TypeScript compiler")


def _java_compiler() -> Path:
    configured = os.environ.get("ELMOS_MULTIMODAL_JAVAC")
    if configured:
        return _executable(configured, "Java compiler")
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / "javac"
        if candidate.is_file():
            return _executable(str(candidate), "Java compiler")
    return _executable(shutil.which("javac"), "Java compiler")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()

    typescript_client = _required_file(TYPESCRIPT_CLIENT, "TypeScript SDK")
    java_sources = sorted(JAVA_SOURCE_ROOT.rglob("*.java"))
    if not java_sources:
        raise SystemExit(f"Java SDK contains no source files: {JAVA_SOURCE_ROOT}")
    for source in java_sources:
        _required_file(source, "Java SDK source")

    tsc = _typescript_compiler()
    javac = _java_compiler()
    _run(
        [
            str(tsc),
            "--strict",
            "--noEmit",
            "--target",
            "ES2022",
            "--module",
            "NodeNext",
            "--moduleResolution",
            "NodeNext",
            "--lib",
            "ES2022,DOM,DOM.Iterable",
            str(typescript_client),
        ]
    )
    with tempfile.TemporaryDirectory(prefix="elmos-multimodal-java-sdk-") as output_root:
        _run(
            [
                str(javac),
                "--release",
                "17",
                "-d",
                output_root,
                *(str(source) for source in java_sources),
            ]
        )

    print(
        json.dumps(
            {
                "java_source_count": len(java_sources),
                "status": "LOCAL_EXECUTED",
                "typescript_source_count": 1,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
