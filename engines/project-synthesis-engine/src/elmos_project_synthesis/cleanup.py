from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path


def _make_tree_writable(root: Path) -> None:
    """Ensure directory and file permissions permit recursive deletion."""
    try:
        os.chmod(root, 0o700, follow_symlinks=False)
    except OSError:
        pass
    try:
        for current, dirs, files in os.walk(root, followlinks=False):
            for name in dirs:
                dir_path = os.path.join(current, name)
                if not os.path.islink(dir_path):
                    try:
                        os.chmod(dir_path, 0o700, follow_symlinks=False)
                    except OSError:
                        pass
            for name in files:
                file_path = os.path.join(current, name)
                if not os.path.islink(file_path):
                    try:
                        os.chmod(file_path, 0o600, follow_symlinks=False)
                    except OSError:
                        pass
    except OSError:
        pass


def cleanup_acceptance_directory(
    directory: Path,
    *,
    expected_prefix: str,
    attempts: int = 5,
) -> str | None:
    """Remove one engine-owned temporary directory with bounded retries."""
    resolved = directory.resolve(strict=False)
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    if (
        temporary_root not in resolved.parents
        or not resolved.name.startswith(expected_prefix)
        or not 1 <= attempts <= 10
    ):
        raise ValueError("ACCEPTANCE_CLEANUP_PATH_UNSAFE")
    for attempt in range(attempts):
        try:
            _make_tree_writable(resolved)
            shutil.rmtree(resolved)
            return None
        except FileNotFoundError:
            return None
        except OSError as error:
            if attempt == attempts - 1:
                return f"{type(error).__name__}:{error.errno or 'UNKNOWN'}"
            time.sleep(0.1 * (2**attempt))
    return "ACCEPTANCE_CLEANUP_FAILED"
