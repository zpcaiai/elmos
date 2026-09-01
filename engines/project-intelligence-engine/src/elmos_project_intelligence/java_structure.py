"""Parser-backed Java declarations and imports for graph projection.

This module lifts package declarations, imports, types (classes, interfaces,
enums, records, @interfaces), and methods out of Java source text without
external native dependencies.

Properties:
* Pure Python and effect-free (no I/O, no subprocesses, safe in sandboxed dispatchers).
* Accurate line-number tracking and scope nesting for inner types and methods.
* Strips comments and string literals to prevent spurious matches.
"""

from __future__ import annotations

import re
from typing import Any, Final

#: Marker recorded on facts a real parser/structural analyzer produced.
ORIGIN_PARSED: Final[str] = "PARSED"

#: Marker recorded on facts the fallback line-regex scan produced.
ORIGIN_REGEX: Final[str] = "REGEX"

_JAVA_SUFFIXES: Final[tuple[str, ...]] = (".java",)


def is_java_path(path: str) -> bool:
    """Return whether *path* names a Java source file."""
    return path.lower().endswith(_JAVA_SUFFIXES)


def _mask_comments_and_strings(source: str) -> tuple[str, list[int]]:
    """Replace comments and string literal contents with whitespace while
    preserving newlines and exact character offsets. Returns masked text and
    line start offsets."""
    chars = list(source)
    length = len(chars)
    i = 0
    in_line_comment = False
    in_block_comment = False
    in_string = False
    in_char = False
    in_text_block = False

    while i < length:
        # Check text block opener triple quotes
        if not in_line_comment and not in_block_comment and not in_char:
            if not in_string and not in_text_block and i + 2 < length and chars[i:i+3] == [chr(34), chr(34), chr(34)]:
                in_text_block = True
                chars[i] = " "
                chars[i+1] = " "
                chars[i+2] = " "
                i += 3
                continue
            if in_text_block and i + 2 < length and chars[i:i+3] == [chr(34), chr(34), chr(34)]:
                in_text_block = False
                chars[i] = " "
                chars[i+1] = " "
                chars[i+2] = " "
                i += 3
                continue

        if in_text_block:
            if chars[i] != chr(10):
                chars[i] = " "
            i += 1
            continue

        if in_line_comment:
            if chars[i] == chr(10):
                in_line_comment = False
            else:
                chars[i] = " "
            i += 1
            continue

        if in_block_comment:
            if chars[i] == "*" and i + 1 < length and chars[i + 1] == "/":
                chars[i] = " "
                chars[i + 1] = " "
                in_block_comment = False
                i += 2
                continue
            if chars[i] != chr(10):
                chars[i] = " "
            i += 1
            continue

        if in_string:
            if chars[i] == chr(92) and i + 1 < length:
                chars[i] = " "
                if chars[i + 1] != chr(10):
                    chars[i + 1] = " "
                i += 2
                continue
            if chars[i] == chr(34):
                in_string = False
                chars[i] = " "
                i += 1
                continue
            if chars[i] != chr(10):
                chars[i] = " "
            i += 1
            continue

        if in_char:
            if chars[i] == chr(92) and i + 1 < length:
                chars[i] = " "
                if chars[i + 1] != chr(10):
                    chars[i + 1] = " "
                i += 2
                continue
            if chars[i] == chr(39):
                in_char = False
                chars[i] = " "
                i += 1
                continue
            if chars[i] != chr(10):
                chars[i] = " "
            i += 1
            continue

        # Check comment openers
        if chars[i] == "/" and i + 1 < length:
            if chars[i + 1] == "/":
                chars[i] = " "
                chars[i + 1] = " "
                in_line_comment = True
                i += 2
                continue
            if chars[i + 1] == "*":
                chars[i] = " "
                chars[i + 1] = " "
                in_block_comment = True
                i += 2
                continue

        if chars[i] == chr(34):
            chars[i] = " "
            in_string = True
            i += 1
            continue

        if chars[i] == chr(39):
            chars[i] = " "
            in_char = True
            i += 1
            continue

        i += 1

    masked_text = "".join(chars)
    line_offsets = [0]
    for idx, ch in enumerate(source):
        if ch == chr(10):
            line_offsets.append(idx + 1)

    return masked_text, line_offsets


def _get_line_number(offset: int, line_offsets: list[int]) -> int:
    """Binary search for 1-based line number given character offset."""
    low = 0
    high = len(line_offsets) - 1
    while low <= high:
        mid = (low + high) // 2
        if line_offsets[mid] <= offset:
            if mid == len(line_offsets) - 1 or line_offsets[mid + 1] > offset:
                return mid + 1
            low = mid + 1
        else:
            high = mid - 1
    return 1


_PACKAGE_RE = re.compile(r"\bpackage\s+([a-zA-Z0-9_.]+)\s*;", re.MULTILINE)
_IMPORT_RE = re.compile(r"\bimport\s+(?:static\s+)?([a-zA-Z0-9_.*]+)\s*;", re.MULTILINE)

_TYPE_DECL_RE = re.compile(
    r"\b(?:(class|interface|enum|record)|(@interface))\s+([a-zA-Z0-9_]+)",
    re.MULTILINE,
)

_METHOD_DECL_RE = re.compile(
    r"(?:public|protected|private|static|final|abstract|synchronized|default|native|\s)+"
    r"(?:<[^>]+>\s+)?"
    r"(?:[a-zA-Z0-9_<>\[\],\s\?]+)\s+"
    r"([a-zA-Z0-9_]+)\s*\(([^)]*)\)\s*(?:throws\s+[a-zA-Z0-9_,\s]+)?\s*[{;]",
    re.MULTILINE,
)

_RESERVED_WORDS = {
    "if", "else", "while", "for", "do", "switch", "catch", "synchronized",
    "return", "throw", "new", "assert", "case", "default"
}


def java_structure(text: str, path: str) -> dict[str, Any] | None:
    """Return parsed declarations and imports for Java source *text*."""
    if not text.strip():
        return None

    try:
        masked, line_offsets = _mask_comments_and_strings(text)
    except Exception:
        return None

    pkg_match = _PACKAGE_RE.search(masked)
    package_name = pkg_match.group(1) if pkg_match else ""

    imports: list[dict[str, Any]] = []
    for match in _IMPORT_RE.finditer(masked):
        target = match.group(1)
        line = _get_line_number(match.start(), line_offsets)
        imports.append({"to": target, "line": line})

    symbols: list[dict[str, Any]] = [
        {
            "kind": "file",
            "name": path,
            "qualified_name": path,
            "line": 1,
        }
    ]

    type_matches: list[tuple[int, str, str]] = []
    for m in _TYPE_DECL_RE.finditer(masked):
        kind = m.group(1) or m.group(2)
        if kind == "@interface":
            kind = "annotation"
        name = m.group(3)
        type_matches.append((m.start(), kind, name))

    type_matches.sort(key=lambda x: x[0])

    for pos, kind, name in type_matches:
        line = _get_line_number(pos, line_offsets)
        qual_prefix = f"{package_name}." if package_name else ""
        qual_name = f"{qual_prefix}{name}"
        symbols.append({
            "kind": kind,
            "name": name,
            "qualified_name": qual_name,
            "line": line,
        })

    for m in _METHOD_DECL_RE.finditer(masked):
        name = m.group(1)
        if name in _RESERVED_WORDS:
            continue
        line = _get_line_number(m.start(), line_offsets)
        parent_class = None
        for pos, kind, tname in reversed(type_matches):
            if pos < m.start():
                parent_class = tname
                break
        qual_prefix = f"{package_name}." if package_name else ""
        if parent_class:
            qual_name = f"{qual_prefix}{parent_class}.{name}"
        else:
            qual_name = f"{qual_prefix}{name}"

        symbols.append({
            "kind": "function",
            "name": name,
            "qualified_name": qual_name,
            "line": line,
        })

    return {"symbols": symbols, "imports": imports}
