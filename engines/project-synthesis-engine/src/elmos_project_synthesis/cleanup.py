from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path


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
            shutil.rmtree(resolved)
            return None
        except FileNotFoundError:
            return None
        except OSError as error:
            if attempt == attempts - 1:
                return f"{type(error).__name__}:{error.errno or 'UNKNOWN'}"
            time.sleep(0.1 * (2**attempt))
    return "ACCEPTANCE_CLEANUP_FAILED"
