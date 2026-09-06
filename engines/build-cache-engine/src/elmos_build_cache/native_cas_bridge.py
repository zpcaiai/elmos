"""Python ctypes bridge to the native Rust CAS implementation."""

from __future__ import annotations

import ctypes
import json
import os
import threading
from pathlib import Path

_NATIVE_LIB = None
_INIT_ATTEMPTED = False
_INIT_LOCK = threading.Lock()


def _find_library() -> str | None:
    custom_path = os.environ.get("ELMOS_NATIVE_LIB")
    if custom_path and os.path.exists(custom_path):
        return custom_path

    repo_root = Path(__file__).resolve().parents[4]
    candidates = [
        repo_root / "native" / "rust-core" / "target" / "release" / "libelmos_native.dylib",
        repo_root / "native" / "rust-core" / "target" / "release" / "libelmos_native.so",
        repo_root / "native" / "rust-core" / "target" / "debug" / "libelmos_native.dylib",
        repo_root / "native" / "rust-core" / "target" / "debug" / "libelmos_native.so",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def get_native_lib():
    with _INIT_LOCK:
        return _load_native_lib()


def _load_native_lib():
    global _NATIVE_LIB, _INIT_ATTEMPTED
    if _NATIVE_LIB is not None:
        return _NATIVE_LIB
    if _INIT_ATTEMPTED:
        return None

    _INIT_ATTEMPTED = True
    lib_path = _find_library()
    if not lib_path:
        return None

    try:
        lib = ctypes.CDLL(lib_path)

        # void elmos_free_string(void*)
        lib.elmos_free_string.argtypes = [ctypes.c_void_p]
        lib.elmos_free_string.restype = None

        # void elmos_free_bytes(void*, size_t)
        lib.elmos_free_bytes.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.elmos_free_bytes.restype = None

        # void* elmos_cas_put_bytes(char* root, uint8_t* data, size_t len, char* expected, char* kind)
        lib.elmos_cas_put_bytes.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_char_p,
        ]
        lib.elmos_cas_put_bytes.restype = ctypes.c_void_p
        if hasattr(lib, "elmos_cas_put_fd"):
            lib.elmos_cas_put_fd.argtypes = [
                ctypes.c_char_p, ctypes.c_int, ctypes.c_uint64, ctypes.c_char_p, ctypes.c_char_p,
            ]
            lib.elmos_cas_put_fd.restype = ctypes.c_void_p

        # void* elmos_cas_get_bytes(char* root, char* digest, int verify, size_t* out_len)
        lib.elmos_cas_get_bytes.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.elmos_cas_get_bytes.restype = ctypes.c_void_p

        # int elmos_cas_contains(char* root, char* digest)
        lib.elmos_cas_contains.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        lib.elmos_cas_contains.restype = ctypes.c_int

        # int elmos_cas_is_quarantined(char* root, char* digest)
        lib.elmos_cas_is_quarantined.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        lib.elmos_cas_is_quarantined.restype = ctypes.c_int

        # int elmos_cas_quarantine(char* root, char* digest, char* reason)
        lib.elmos_cas_quarantine.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        lib.elmos_cas_quarantine.restype = ctypes.c_int

        # void* elmos_cas_info(char* root, char* digest)
        lib.elmos_cas_info.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        lib.elmos_cas_info.restype = ctypes.c_void_p

        # void* elmos_cas_accounting(char* root)
        lib.elmos_cas_accounting.argtypes = [ctypes.c_char_p]
        lib.elmos_cas_accounting.restype = ctypes.c_void_p

        _NATIVE_LIB = lib
        return _NATIVE_LIB
    except Exception:
        return None


def is_native_available() -> bool:
    return get_native_lib() is not None


def native_put_bytes(
    root: Path | str,
    data: bytes,
    expected_digest: str | None = None,
    artifact_kind: str = "blob",
) -> str | None:
    lib = get_native_lib()
    if lib is None:
        return None

    root_bytes = str(root).encode("utf-8")
    expected_bytes = expected_digest.encode("utf-8") if expected_digest else None
    kind_bytes = artifact_kind.encode("utf-8")

    # Immutable bytes stay strongly referenced throughout the synchronous native borrow.
    # The C ABI never writes through this pointer; CDLL releases the GIL while Rust runs.
    data_buffer = ctypes.cast(ctypes.c_char_p(data), ctypes.POINTER(ctypes.c_uint8))
    res_ptr = lib.elmos_cas_put_bytes(
        root_bytes,
        data_buffer,
        len(data),
        expected_bytes,
        kind_bytes,
    )
    if not res_ptr:
        return None

    try:
        res_str = ctypes.string_at(res_ptr).decode("utf-8")
        parsed = json.loads(res_str)
        if "error" in parsed:
            return None
        return parsed.get("digest")
    finally:
        lib.elmos_free_string(res_ptr)


def native_get_bytes(root: Path | str, digest: str, verify: bool = True) -> bytes | None:
    lib = get_native_lib()
    if lib is None:
        return None

    root_bytes = str(root).encode("utf-8")
    digest_bytes = digest.encode("utf-8")
    out_len = ctypes.c_size_t(0)

    ptr = lib.elmos_cas_get_bytes(
        root_bytes,
        digest_bytes,
        1 if verify else 0,
        ctypes.byref(out_len),
    )
    if not ptr:
        return None

    try:
        length = out_len.value
        data = ctypes.string_at(ptr, length)
        return data
    finally:
        lib.elmos_free_bytes(ptr, out_len.value)


def native_put_file_descriptor(
    root: Path, descriptor: int, max_bytes: int, expected_digest: str | None, artifact_kind: str,
) -> str | None:
    """None means unsupported ABI only. Native execution errors never silently fall back."""
    from .canonical import require_digest
    from .errors import DigestMismatch, QuotaExceeded

    lib = get_native_lib()
    if lib is None or not hasattr(lib, "elmos_cas_put_fd"):
        return None
    encoded_root = os.fsencode(root)
    if (max_bytes < 0 or max_bytes > 2**64 - 1 or "\0" in artifact_kind
            or b"\0" in encoded_root or descriptor < 0 or descriptor > 2**31 - 1):
        raise ValueError("invalid native CAS stream argument")
    if expected_digest is not None:
        require_digest(expected_digest)
    pointer = lib.elmos_cas_put_fd(
        encoded_root, descriptor, max_bytes,
        expected_digest.encode() if expected_digest is not None else None, artifact_kind.encode(),
    )
    if not pointer:
        raise OSError("native CAS stream returned no result")
    try:
        result = json.loads(ctypes.string_at(pointer))
        if "error" in result:
            message = str(result["error"])
            if message == "QuotaExceeded":
                raise QuotaExceeded("object exceeds the configured CAS budget", size=max_bytes)
            if message.startswith("digest mismatch:"):
                raise DigestMismatch(message, expected=expected_digest)
            raise OSError(message)
        return require_digest(result["digest"])
    finally:
        lib.elmos_free_string(pointer)


def native_contains(root: Path | str, digest: str) -> bool | None:
    lib = get_native_lib()
    if lib is None:
        return None
    res = lib.elmos_cas_contains(str(root).encode("utf-8"), digest.encode("utf-8"))
    return res == 1


def native_is_quarantined(root: Path | str, digest: str) -> bool | None:
    lib = get_native_lib()
    if lib is None:
        return None
    res = lib.elmos_cas_is_quarantined(str(root).encode("utf-8"), digest.encode("utf-8"))
    return res == 1


def native_quarantine(root: Path | str, digest: str, reason: str) -> bool | None:
    lib = get_native_lib()
    if lib is None:
        return None
    res = lib.elmos_cas_quarantine(
        str(root).encode("utf-8"),
        digest.encode("utf-8"),
        reason.encode("utf-8"),
    )
    return res == 0
