"""Resolve repository and installed-distribution data without cwd assumptions."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path, PurePosixPath

_DISTRIBUTION_NAME = "elmos-execution-intelligence"
_SHARE_ROOT = PurePosixPath("share") / _DISTRIBUTION_NAME


def resource_dir(name: str) -> Path:
    """Return a checked-in or wheel-installed resource directory.

    Source-tree execution remains the development default.  A regular wheel
    installs the same files through ``data-files``; resolving them through the
    distribution RECORD also works for user and virtual-environment installs,
    where a process-wide ``sysconfig`` prefix can be misleading.

    If neither location exists, return the expected source location.  Callers
    then fail on the exact missing file instead of silently switching to an
    untrusted current-working-directory path.
    """
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError(f"invalid resource directory name: {name!r}")

    source = Path(__file__).resolve().parents[2] / name
    if source.is_dir():
        return source

    marker = _SHARE_ROOT / name
    try:
        installed = distribution(_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return source

    for entry in installed.files or ():
        relative = PurePosixPath(str(entry))
        marker_parts = marker.parts
        if (
            len(relative.parts) <= len(marker_parts)
            or relative.parts[-len(marker_parts) - 1:-1] != marker_parts
        ):
            continue
        candidate = Path(str(installed.locate_file(entry))).resolve().parent
        if candidate.is_dir():
            return candidate
    return source


SCHEMA_DIR = resource_dir("schemas")
CONFIG_DIR = resource_dir("config")
TEMPLATE_DIR = resource_dir("templates")

__all__ = ["CONFIG_DIR", "SCHEMA_DIR", "TEMPLATE_DIR", "resource_dir"]
