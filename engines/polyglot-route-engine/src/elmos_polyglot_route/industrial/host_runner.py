"""Host compile/run for industrial emission. Python is mandatory; others optional."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class HostRunError(Exception):
    pass


def run_python(source: str, entrypoint: str, args: list[Any]) -> Any:
    """Run emitted Python out of process and return its JSON-compatible value."""
    marker = "__ELMOS_RESULT__="
    driver = f"""
import json as _elmos_json
import sys as _elmos_sys

_elmos_entrypoint = _elmos_sys.argv[1]
_elmos_args = _elmos_json.loads(_elmos_sys.argv[2])
_elmos_func = globals().get(_elmos_entrypoint)
if _elmos_func is None:
    raise RuntimeError(f"entrypoint {{_elmos_entrypoint}} missing from Python emission")
print({marker!r} + _elmos_json.dumps(_elmos_func(*_elmos_args), allow_nan=False))
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "emitted_program.py"
        path.write_text(source + "\n" + driver, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-I", str(path), entrypoint, json.dumps(args, allow_nan=False)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    if proc.returncode != 0:
        raise HostRunError(proc.stderr or proc.stdout)
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(marker):
            return json.loads(line.removeprefix(marker))
    raise HostRunError("Python emission did not produce a result")


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
    go_path = shutil.which("go")
    if not go_path:
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
            [go_path, "run", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise HostRunError(proc.stderr or proc.stdout)
        return int(proc.stdout.strip().splitlines()[-1])
