"""Content identity for Project Synthesis execution evidence."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any


def source_identity(engine_root: Path) -> dict[str, Any]:
    root = engine_root.resolve(strict=True)
    candidates = [
        *sorted((root / "src").rglob("*.py")),
        *sorted((root / "scripts").glob("*.py")),
        root / "pyproject.toml",
        root / "uv.lock",
    ]
    files = [path for path in candidates if path.is_file() and not path.is_symlink()]
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return {
        "algorithm": "sha256-length-prefixed-path-and-content-v1",
        "sha256": digest.hexdigest(),
        "file_count": len(files),
    }


def git_identity(repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve(strict=True)
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("GIT_EXECUTABLE_NOT_FOUND")

    def git(*arguments: str) -> str:
        completed = subprocess.run(  # noqa: S603
            [git_executable, *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    return {
        "head_sha": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "tracked_worktree": "DIRTY" if git("status", "--porcelain", "--untracked-files=no") else "CLEAN",
    }
