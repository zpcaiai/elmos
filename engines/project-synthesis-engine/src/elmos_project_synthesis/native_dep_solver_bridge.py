from __future__ import annotations

import ctypes
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, cast

_LIB: ctypes.CDLL | None = None
_LIB_PATH: Path | None = None


def _library_filename() -> str | None:
    if sys.platform == "darwin":
        return "libelmos_native.dylib"
    if sys.platform == "win32":
        return "elmos_native.dll"
    if sys.platform.startswith("linux"):
        return "libelmos_native.so"
    return None


def _repository_candidates() -> tuple[Path, ...]:
    repo_root = Path(__file__).resolve().parents[4]
    filename = _library_filename()
    if filename is None:
        return ()
    return (
        repo_root / "native" / "rust-core" / "target" / "release" / filename,
        repo_root / "native" / "rust-core" / "target" / "debug" / filename,
    )


def _safe_repository_artifact(candidate: Path) -> Path | None:
    """Return only an owned build output from the repository's Rust target.

    Loading through ``ctypes`` executes the selected file, so an environment
    variable is a selection hint and never authority for an arbitrary library.
    """

    if not candidate.is_absolute() or candidate != Path(os.path.abspath(candidate)):
        return None
    try:
        info = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        allowed = {path.resolve(strict=False) for path in _repository_candidates()}
    except OSError:
        return None
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o022
        or resolved not in allowed
    ):
        return None
    return resolved


def _find_library() -> Path | None:
    env_path = os.environ.get("ELMOS_NATIVE_LIB")
    if env_path:
        return _safe_repository_artifact(Path(env_path))

    for candidate in _repository_candidates():
        artifact = _safe_repository_artifact(candidate)
        if artifact is not None:
            return artifact
    return None


def _get_lib() -> ctypes.CDLL | None:
    global _LIB, _LIB_PATH
    lib_path = _find_library()
    if not lib_path:
        _LIB = None
        _LIB_PATH = None
        return None
    try:
        resolved_path = lib_path.resolve(strict=True)
    except OSError:
        _LIB = None
        _LIB_PATH = None
        return None
    if _LIB is not None and _LIB_PATH == resolved_path:
        return _LIB
    _LIB = None
    _LIB_PATH = resolved_path
    try:
        lib = ctypes.CDLL(str(resolved_path))
        lib.elmos_solve_dependencies.argtypes = [ctypes.c_char_p]
        lib.elmos_solve_dependencies.restype = ctypes.c_void_p
        lib.elmos_free_string.argtypes = [ctypes.c_void_p]
        lib.elmos_free_string.restype = None
        _LIB = lib
    except (AttributeError, OSError):
        _LIB = None
    return _LIB


def native_solve_dependencies(
    root_dependencies: list[dict[str, str]],
    available_packages: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return None
    try:
        payload = json.dumps(
            {
                "root_dependencies": root_dependencies,
                "available_packages": available_packages,
            }
        ).encode("utf-8")
        ptr = lib.elmos_solve_dependencies(payload)
        if not ptr:
            return None
        try:
            raw_str = ctypes.string_at(ptr).decode("utf-8")
        finally:
            lib.elmos_free_string(ptr)
        result = json.loads(raw_str)
        if not isinstance(result, dict):
            return None
        return cast(dict[str, Any], result)
    except Exception:
        return None
