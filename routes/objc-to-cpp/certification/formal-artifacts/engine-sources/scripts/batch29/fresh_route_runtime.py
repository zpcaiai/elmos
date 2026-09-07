#!/usr/bin/env python3
"""Launch authoritative Batch 29 route commands in a fresh locked uv venv."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PINNED_UV_PATH = Path("/opt/homebrew/Cellar/uv/0.11.16/bin/uv")
PINNED_UV_SHA256 = (
    "sha256:d4182a7bba32f331b2c5a74568cf1c88aa50f31fe643a2c56118c6610db0aff0"
)
PINNED_UV_BYTES = 46_541_136
PINNED_UV_VERSION = "uv 0.11.16 (Homebrew 2026-05-21 aarch64-apple-darwin)"
PROJECT_ENVIRONMENT_ENV = "UV_PROJECT_ENVIRONMENT"
CHILD_PROGRAM = r"""
import runpy
import sys
from pathlib import Path

script = Path(sys.argv[1]).resolve(strict=True)
arguments = sys.argv[2:]
sys.path.insert(0, str(script.parent))
sys.argv = [str(script), *arguments]
namespace = runpy.run_path(str(script), run_name="__elmos_batch29_fresh_child__")
main = namespace.get("main")
if not callable(main):
    raise SystemExit("Batch29 fresh child target has no callable main")
result = main()
raise SystemExit(result if isinstance(result, int) else 0)
"""


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _repository_root(script: Path) -> Path:
    resolved = script.resolve(strict=True)
    candidate = resolved.parents[2]
    project = candidate / "engines" / "polyglot-route-engine"
    if not (project / "pyproject.toml").is_file() or not (project / "uv.lock").is_file():
        raise RuntimeError("Batch29 repository route-engine project is missing")
    return candidate


def _pinned_uv() -> Path:
    ambient = shutil.which("uv")
    if ambient is None:
        raise RuntimeError("Batch29 pinned uv is unavailable")
    observed = Path(ambient).resolve(strict=True)
    expected = PINNED_UV_PATH.resolve(strict=True)
    if observed != expected:
        raise RuntimeError(f"Batch29 pinned uv origin mismatch: {observed}")
    if observed.stat().st_size != PINNED_UV_BYTES or _digest(observed) != PINNED_UV_SHA256:
        raise RuntimeError("Batch29 pinned uv bytes/digest mismatch")
    environment = {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": str(expected.parent) + os.pathsep + os.defpath,
        "UV_NO_CONFIG": "1",
    }
    result = subprocess.run(
        [str(expected), "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env=environment,
    )
    if result.returncode != 0 or result.stdout.strip() != PINNED_UV_VERSION:
        raise RuntimeError("Batch29 pinned uv version mismatch")
    return expected


def run_in_fresh_locked_runtime(script: Path, argv: list[str]) -> int:
    """Always execute ``script.main`` inside a newly resolved locked venv."""

    repository = _repository_root(script)
    project = repository / "engines" / "polyglot-route-engine"
    uv = _pinned_uv()
    with tempfile.TemporaryDirectory(
        prefix="elmos-batch29-fresh-route-runtime-"
    ) as temporary:
        runtime_root = Path(temporary).resolve(strict=True)
        runtime_root.chmod(0o700)
        project_environment = runtime_root / ".venv"
        environment = {
            key: os.environ[key]
            for key in ("HOME", "TMPDIR", "TZ")
            if key in os.environ
        }
        environment.update(
            {
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": str(uv.parent) + os.pathsep + os.defpath,
                "PYTHONNOUSERSITE": "1",
                "UV_NO_CONFIG": "1",
                PROJECT_ENVIRONMENT_ENV: str(project_environment),
            }
        )
        completed = subprocess.run(
            [
                str(uv),
                "--project",
                str(project),
                "run",
                "--locked",
                "python",
                "-c",
                CHILD_PROGRAM,
                str(script.resolve(strict=True)),
                *argv,
            ],
            cwd=Path.cwd(),
            env=environment,
            check=False,
        )
        return completed.returncode
