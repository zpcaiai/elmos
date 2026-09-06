"""Original bytes are canonical. Coordinate conversion is explicit at boundaries."""
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath

def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

def validate_path(path: str) -> None:
    if not path or path.startswith("/") or "\\" in path or any(ord(c)<32 or ord(c)==127 for c in path):
        raise ValueError("unsafe relative path")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError("unsafe path component")

def read_snapshot_file(root: Path, path: str) -> bytes:
    # Model only. A production worker needs immutable mounts + race-resistant openat2.
    validate_path(path)
    root = root.resolve(strict=True)
    current = root
    for part in PurePosixPath(path).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlinks are not allowed in this reference reader")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("snapshot escape")
    return resolved.read_bytes()

def extract(data: bytes, expected_digest: str, start: int, end: int) -> str:
    if digest(data) != expected_digest:
        raise ValueError("stale blob")
    if not (0 <= start <= end <= len(data)):
        raise ValueError("invalid range")
    # Validate start AND end boundaries, even an empty selection inside a codepoint.
    data[:start].decode("utf-8")
    data[:end].decode("utf-8")
    return data[start:end].decode("utf-8")

def _lines(data: bytes) -> list[str]:
    return data.decode("utf-8").split("\n")

def lsp_utf16_to_byte(data: bytes, line: int, column: int) -> int:
    """0-based line and UTF-16 code units. Reject positions inside surrogate pairs/CRLF."""
    lines = _lines(data)
    if line < 0 or line >= len(lines) or column < 0:
        raise ValueError("position out of range")
    text = lines[line]
    if text.endswith("\r") and line < len(lines)-1:
        text = text[:-1]
    units = 0
    prefix = ""
    for char in text:
        if units == column:
            break
        width = len(char.encode("utf-16-le"))//2
        if units + width > column:
            raise ValueError("position inside surrogate pair")
        units += width
        prefix += char
    if units != column:
        raise ValueError("column beyond line")
    preceding = "\n".join(lines[:line])
    offset = len(preceding.encode("utf-8")) + (1 if line else 0)
    return offset + len(prefix.encode("utf-8"))

def byte_to_lsp_utf16(data: bytes, offset: int) -> tuple[int,int]:
    if not 0 <= offset <= len(data):
        raise ValueError("offset out of range")
    prefix = data[:offset].decode("utf-8")
    line = prefix.count("\n")
    tail = prefix.rsplit("\n",1)[-1]
    if tail.endswith("\r") and offset < len(data) and data[offset:offset+1] == b"\n":
        raise ValueError("position inside CRLF")
    return line, len(tail.encode("utf-16-le"))//2
