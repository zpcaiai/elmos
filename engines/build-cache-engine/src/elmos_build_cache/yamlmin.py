"""Minimal YAML-subset reader for ELMOS cache configuration files.

PyYAML is used when available. The fallback covers exactly the subset the
shipped configuration templates use: nested block mappings, block and flow
sequences of scalars, comments, and ``${VAR}`` expansion. Anything outside that
subset raises rather than guessing.
"""

from __future__ import annotations

import os
import re
from typing import Any

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _scalar(token: str) -> Any:
    token = token.strip()
    if token.startswith("#"):
        return None
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    lowered = token.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "~", ""):
        return None
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in inner.split(",")]
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    return _VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), token)


def _strip_comment(line: str) -> str:
    out: list[str] = []
    quote: str | None = None
    for index, char in enumerate(line):
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            continue
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            break
        out.append(char)
    return "".join(out).rstrip()


def _parse_block(lines: list[tuple[int, str]], start: int, indent: int) -> tuple[Any, int]:
    index = start
    mapping: dict[str, Any] = {}
    sequence: list[Any] = []
    kind: str | None = None

    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ValueError(f"unexpected indentation at line {index + 1}: {text!r}")

        if text.startswith("- "):
            if kind == "map":
                raise ValueError("mixed mapping and sequence at the same level")
            kind = "seq"
            sequence.append(_scalar(text[2:]))
            index += 1
            continue

        if ":" not in text:
            raise ValueError(f"unsupported YAML construct: {text!r}")
        if kind == "seq":
            raise ValueError("mixed sequence and mapping at the same level")
        kind = "map"
        key, _, rest = text.partition(":")
        key = key.strip()
        rest = rest.strip()
        index += 1
        if rest:
            mapping[key] = _scalar(rest)
            continue
        if index < len(lines) and lines[index][0] > indent:
            value, index = _parse_block(lines, index, lines[index][0])
            mapping[key] = value
        else:
            mapping[key] = None

    if kind == "seq":
        return sequence, index
    return mapping, index


def safe_load(text: str) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        pass
    else:
        loaded = yaml.safe_load(text)
        return _expand(loaded)

    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        if stripped.lstrip().startswith("---"):
            continue
        lines.append((len(stripped) - len(stripped.lstrip(" ")), stripped.strip()))
    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, lines[0][0])
    return value


def _expand(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, str):
        return _VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    return value
