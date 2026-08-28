"""Deterministic, syntax-aware transformation primitives.

The engine deliberately does not execute repository build plugins or source
package recipes.  These helpers parse the bounded source forms they modify,
emit preconditioned change operations, and fail closed for unsupported or
secret-bearing inputs.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree

from .canonical import canonical_digest, redact_text
from .snapshot import RepositorySnapshot

JAVA_NAMESPACE_MAP: tuple[tuple[str, str], ...] = (
    ("javax.servlet", "jakarta.servlet"),
    ("javax.validation", "jakarta.validation"),
    ("javax.annotation", "jakarta.annotation"),
    ("javax.persistence", "jakarta.persistence"),
)

_TOKEN_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.$"
)
_SECRET_LINE = re.compile(
    r"(?im)^\s*[^#\n]*(?:password|passwd|secret|token|api[-_.]?key|private[-_.]?key)\s*[:=]"
)
_QUALIFIED_NAME = re.compile(
    r"^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+$"
)


class TransformationError(ValueError):
    """The requested transformation cannot be proven safe."""


def validated_mappings(value: Any) -> tuple[tuple[str, str], ...]:
    """Validate an exact bounded qualified-name rewrite map."""

    if value is None:
        return JAVA_NAMESPACE_MAP
    if not isinstance(value, list) or not 1 <= len(value) <= 64:
        raise TransformationError("rewrite_mappings must be a bounded non-empty array")
    mappings: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise TransformationError("each rewrite mapping must be an object")
        old = item.get("from")
        new = item.get("to")
        if (
            not isinstance(old, str)
            or not isinstance(new, str)
            or not _QUALIFIED_NAME.fullmatch(old)
            or not _QUALIFIED_NAME.fullmatch(new)
        ):
            raise TransformationError(
                "rewrite mappings must contain qualified from/to names"
            )
        if old in seen or old == new:
            raise TransformationError(
                "rewrite mappings must be unique and non-identity"
            )
        seen.add(old)
        mappings.append((old, new))
    # Longest prefixes first makes parent/child mappings deterministic.
    return tuple(sorted(mappings, key=lambda item: (-len(item[0]), item[0], item[1])))


@dataclass(frozen=True, slots=True)
class RewriteResult:
    content: str
    parser: str
    operations: tuple[dict[str, str], ...]


def _replace_qualified_token(
    token: str, mappings: Iterable[tuple[str, str]]
) -> tuple[str, tuple[dict[str, str], ...]]:
    for old, new in mappings:
        if token == old or token.startswith(old + "."):
            changed = new + token[len(old) :]
            return changed, (
                {"kind": "replace-qualified-name", "from": token, "to": changed},
            )
    return token, ()


def rewrite_java(
    source: str, mappings: Iterable[tuple[str, str]] = JAVA_NAMESPACE_MAP
) -> RewriteResult:
    """Rewrite qualified Java names without touching comments or literals.

    This is a bounded Java lexical transformation rather than a text replace:
    comments, string literals and character literals are copied byte-for-byte.
    Unsupported unterminated lexical constructs fail closed.
    """

    output: list[str] = []
    operations: list[dict[str, str]] = []
    index = 0
    state = "code"
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and following == "/":
                output.extend((char, following))
                index += 2
                state = "line-comment"
                continue
            if char == "/" and following == "*":
                output.extend((char, following))
                index += 2
                state = "block-comment"
                continue
            if char == '"':
                output.append(char)
                index += 1
                state = "string"
                continue
            if char == "'":
                output.append(char)
                index += 1
                state = "character"
                continue
            if char in _TOKEN_CHARS and (char.isalpha() or char in "_$"):
                end = index + 1
                while end < len(source) and source[end] in _TOKEN_CHARS:
                    end += 1
                token, applied = _replace_qualified_token(source[index:end], mappings)
                output.append(token)
                operations.extend(applied)
                index = end
                continue
            output.append(char)
            index += 1
            continue
        output.append(char)
        if state == "line-comment" and char in "\r\n":
            state = "code"
        elif state == "block-comment" and char == "*" and following == "/":
            output.append(following)
            index += 1
            state = "code"
        elif state in {"string", "character"} and char == "\\":
            if following:
                output.append(following)
                index += 1
        elif (state == "string" and char == '"') or (
            state == "character" and char == "'"
        ):
            state = "code"
        index += 1
    if state in {"block-comment", "string", "character"}:
        raise TransformationError(f"unterminated Java {state}")
    return RewriteResult(
        "".join(output), "java-lexical-qualified-name", tuple(operations)
    )


def _replace_scalar(
    value: str | None,
    mappings: Iterable[tuple[str, str]],
    operations: list[dict[str, str]],
) -> str | None:
    if value is None:
        return None
    changed = value
    for old, new in mappings:
        if old in changed:
            changed = changed.replace(old, new)
            operations.append({"kind": "replace-xml-scalar", "from": old, "to": new})
    return changed


def rewrite_xml(
    source: str, mappings: Iterable[tuple[str, str]] = JAVA_NAMESPACE_MAP
) -> RewriteResult:
    """Parse XML and rewrite only element text, tails and attribute values."""

    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError as exc:
        raise TransformationError("XML is not well formed") from exc
    operations: list[dict[str, str]] = []
    for node in root.iter():
        node.text = _replace_scalar(node.text, mappings, operations)
        node.tail = _replace_scalar(node.tail, mappings, operations)
        for key, value in tuple(node.attrib.items()):
            node.attrib[key] = _replace_scalar(value, mappings, operations) or ""
    content = ElementTree.tostring(root, encoding="unicode", short_empty_elements=True)
    if source.endswith("\n"):
        content += "\n"
    return RewriteResult(content, "xml-element-tree", tuple(operations))


def rewrite_key_value(
    source: str, mappings: Iterable[tuple[str, str]] = JAVA_NAMESPACE_MAP
) -> RewriteResult:
    """Rewrite bounded properties/YAML scalars while preserving comments."""

    if _SECRET_LINE.search(source):
        raise TransformationError(
            "secret-bearing config is excluded from persisted rewrites"
        )
    operations: list[dict[str, str]] = []
    lines: list[str] = []
    for line in source.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith(("#", "!")) or not stripped.strip():
            lines.append(line)
            continue
        changed = line
        for old, new in mappings:
            if old in changed:
                changed = changed.replace(old, new)
                operations.append(
                    {"kind": "replace-config-scalar", "from": old, "to": new}
                )
        lines.append(changed)
    return RewriteResult("".join(lines), "bounded-key-value", tuple(operations))


def namespace_change_set(
    snapshot: RepositorySnapshot,
    *,
    jakarta: bool,
    mappings: tuple[tuple[str, str], ...] | None = None,
) -> dict[str, Any]:
    """Create deterministic, reversible, preconditioned file changes."""

    selected_mappings = mappings or JAVA_NAMESPACE_MAP
    if not jakarta and mappings is None:
        return {"files": {}, "blockedFiles": [], "operationCount": 0}
    files: dict[str, Any] = {}
    blocked: list[dict[str, str]] = []
    operation_count = 0
    for item in snapshot.files:
        if item.kind != "file" or item.text is None:
            continue
        try:
            if item.path.endswith(".java"):
                result = rewrite_java(item.text, selected_mappings)
            elif item.path.endswith(".xml"):
                result = rewrite_xml(item.text, selected_mappings)
            elif item.path.endswith((".properties", ".yml", ".yaml")):
                result = rewrite_key_value(item.text, selected_mappings)
            else:
                continue
        except TransformationError as exc:
            if any(old in item.text for old, _ in selected_mappings):
                blocked.append({"path": item.path, "reason": str(exc)})
            continue
        if result.content == item.text:
            continue
        # Persisted transformation payloads may never contain an unredacted
        # credential.  Exclusion is safer than silently corrupting source.
        if redact_text(result.content) != result.content:
            blocked.append({"path": item.path, "reason": "redaction-required"})
            continue
        inverse = tuple(
            {"kind": op["kind"], "from": op["to"], "to": op["from"]}
            for op in reversed(result.operations)
        )
        files[item.path] = {
            "preconditionDigest": item.digest,
            "afterDigest": canonical_digest(result.content),
            "content": result.content,
            "parser": result.parser,
            "operations": list(result.operations),
            "inverseOperations": list(inverse),
        }
        operation_count += len(result.operations)
    return {"files": files, "blockedFiles": blocked, "operationCount": operation_count}


def validate_generated_files(files: Mapping[str, Any]) -> dict[str, str]:
    """Validate the materializable subset of a generated file map."""

    if len(files) > 2_000:
        raise TransformationError("change set exceeds the file-count policy")
    result: dict[str, str] = {}
    total = 0
    for path, value in files.items():
        if not isinstance(path, str) or not isinstance(value, (str, Mapping)):
            raise TransformationError(
                "generated files must map paths to text or file operations"
            )
        relative = PurePosixPath(path) if isinstance(path, str) else PurePosixPath(".")
        if (
            not path
            or "\\" in path
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise TransformationError(
                "generated file path escapes the staged workspace"
            )
        content = value if isinstance(value, str) else value.get("content")
        if not isinstance(content, str):
            raise TransformationError(f"generated file {path!r} has no text content")
        if redact_text(content) != content:
            raise TransformationError(
                f"generated file {path!r} contains secret-like material"
            )
        total += len(content.encode("utf-8"))
        if total > 64 * 1024 * 1024:
            raise TransformationError("change set exceeds the byte policy")
        result[path] = content
    return result
