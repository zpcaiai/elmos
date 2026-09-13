"""Host compile/run for industrial emission. Python is mandatory; others optional."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class HostRunError(Exception):
    pass


def run_python(source: str, entrypoint: str, args: list[Any]) -> Any:
    namespace: dict[str, Any] = {}
    exec(compile(source, "<industrial-python>", "exec"), namespace, namespace)
    func = namespace.get(entrypoint)
    if func is None:
        # Controller methods are emitted as free functions in Python.
        raise HostRunError(f"entrypoint {entrypoint} missing from Python emission")
    return func(*args)


def toolchain_available(language: str) -> bool:
    mapping = {
        "python": "python3",
        "go": "go",
        "php": "php",
        "java": "javac",
        "rust": "rustc",
        "typescript": "node",
        "react": "node",
    }
    binary = mapping.get(language)
    return bool(binary and shutil.which(binary))


def run_go(source: str, entrypoint: str, args: list[Any]) -> Any:
    if not shutil.which("go"):
        raise HostRunError("go toolchain not available")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "main.go"
        call = ", ".join(str(int(a)) for a in args)
        wrapped = (
            source.replace("package industrial", "package main", 1)
            + "\nfunc main() {\n"
            + f"    fmt.Println({entrypoint}({call}))\n"
            + "}\n"
        )
        path.write_text(wrapped, encoding="utf-8")
        proc = subprocess.run(
            ["go", "run", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise HostRunError(proc.stderr or proc.stdout)
        return int(proc.stdout.strip().splitlines()[-1])
