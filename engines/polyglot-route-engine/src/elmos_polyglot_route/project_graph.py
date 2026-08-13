"""Fail-closed, content-addressed project discovery for polyglot repositories.

The route engine needs a repository model before it can schedule file-level
translation.  This module deliberately limits its claims:

* every in-scope filesystem entry is classified and content addressed;
* Python declarations and static imports are indexed by CPython's AST;
* JSON, TOML, and XML descriptors are parsed by real format parsers; and
* the other eight source languages remain ``NOT_RUN`` unless a matching,
  compiler-backed whole-module inventory is supplied by discovery.

In particular, source text is never searched with regular expressions to
invent symbols or imports.  An unclassified file, unreadable entry, unsupported
descriptor, unresolved import, or unavailable semantic index creates a
diagnostic obligation and keeps ``repository_complete`` false.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import stat
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final, cast

from .models import RouteError
from .repository import javascript_esm_descriptor

SCHEMA_VERSION: Final = "1.0.0"
DISCOVERY_PROFILE: Final = "static-project-graph-v1"
MAX_FILES: Final = 10_000
MAX_FILE_BYTES: Final = 2 * 1024 * 1024
MAX_REPOSITORY_BYTES: Final = 128 * 1024 * 1024
MAX_XML_ELEMENTS: Final = 50_000


class ProjectGraphError(ValueError):
    """The requested repository cannot be scanned inside the bounded policy."""


class FileRole(StrEnum):
    SOURCE = "source"
    TEST = "test"
    BUILD_DESCRIPTOR = "build-descriptor"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


class EdgeKind(StrEnum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    BUILD_DEPENDENCY = "build-dependency"
    TEST = "test"
    RESOURCE = "resource"


class EvidenceStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    NOT_RUN = "NOT_RUN"


SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = (
    "cpp",
    "csharp",
    "go",
    "java",
    "javascript",
    "objc",
    "python",
    "rust",
    "swift",
    "typescript",
)

_SOURCE_EXTENSIONS: Final[dict[str, str]] = {
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".java": "java",
    ".cjs": "javascript",
    ".js": "javascript",
    ".mjs": "javascript",
    ".m": "objc",
    ".mm": "objc",
    ".py": "python",
    ".rs": "rust",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
}

_IGNORED_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".venv",
        "__pycache__",
        "bin",
        "build",
        "dist",
        "node_modules",
        "obj",
        "target",
        "vendor",
    }
)

_BUILD_DESCRIPTOR_NAMES: Final[frozenset[str]] = frozenset(
    {
        "build.gradle",
        "build.gradle.kts",
        "build.sbt",
        "cargo.lock",
        "cargo.toml",
        "cmakelists.txt",
        "composer.json",
        "directory.build.props",
        "directory.build.targets",
        "directory.packages.props",
        "go.mod",
        "go.sum",
        "gradle.properties",
        "makefile",
        "meson.build",
        "module.bazel",
        "jsconfig.json",
        "package-lock.json",
        "package.json",
        "package.resolved",
        "package.swift",
        "packages.lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pom.xml",
        "pyproject.toml",
        "requirements.txt",
        "settings.gradle",
        "settings.gradle.kts",
        "tsconfig.json",
        "uv.lock",
        "workspace",
        "yarn.lock",
    }
)

_BUILD_DESCRIPTOR_SUFFIXES: Final[tuple[str, ...]] = (
    ".csproj",
    ".fsproj",
    ".sln",
    ".vcxproj",
    ".vbproj",
)

_RESOURCE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".avsc",
        ".bmp",
        ".conf",
        ".css",
        ".csv",
        ".env",
        ".gif",
        ".graphql",
        ".graphqls",
        ".html",
        ".ico",
        ".ini",
        ".jpeg",
        ".jpg",
        ".json",
        ".jsonl",
        ".lock",
        ".md",
        ".pem",
        ".png",
        ".properties",
        ".proto",
        ".rst",
        ".scss",
        ".sql",
        ".svg",
        ".toml",
        ".txt",
        ".wasm",
        ".webp",
        ".xml",
        ".yaml",
        ".yml",
    }
)

_RESOURCE_NAMES: Final[frozenset[str]] = frozenset(
    {
        ".dockerignore",
        ".editorconfig",
        ".env",
        ".gitattributes",
        ".gitignore",
        "license",
        "notice",
        "readme",
    }
)

_TEST_DIRECTORIES: Final[frozenset[str]] = frozenset({"__tests__", "spec", "specs", "test", "tests"})
_SOURCE_ROOTS: Final[frozenset[str]] = frozenset({"app", "lib", "python", "src"})
_STRUCTURED_SUFFIXES: Final[frozenset[str]] = frozenset({".json", ".toml", ".xml"})


@dataclass(frozen=True)
class SourceLocation:
    path: str
    start_line: int | None = None
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None

    def to_mapping(self) -> dict[str, object]:
        return {
            "path": self.path,
            "start_line": self.start_line,
            "start_column": self.start_column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }


@dataclass(frozen=True)
class PythonCoverageSubject:
    """One exact Python declaration/effect that whole-repository conversion must cover."""

    path: str
    name: str
    qualified_name: str
    subject_kind: str
    declaration_kind: str
    occurrence: int
    scope_depth: int
    parent_coverage_key: str | None
    source_location: SourceLocation
    candidate: bool
    blocking_reasons: tuple[str, ...]

    @property
    def coverage_key(self) -> str:
        return semantic_coverage_key(
            "python",
            self.path,
            self.subject_kind,
            self.qualified_name,
            self.occurrence,
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "coverage_key": self.coverage_key,
            "path": self.path,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "subject_kind": self.subject_kind,
            "declaration_kind": self.declaration_kind,
            "occurrence": self.occurrence,
            "scope_depth": self.scope_depth,
            "parent_coverage_key": self.parent_coverage_key,
            "source_location": self.source_location.to_mapping(),
            "candidate": self.candidate,
            "blocking_reasons": list(self.blocking_reasons),
        }


def semantic_coverage_key(
    language: str,
    path: str,
    subject_kind: str,
    qualified_name: str,
    occurrence: int,
) -> str:
    if language not in SUPPORTED_LANGUAGES or occurrence < 1:
        raise ProjectGraphError("SEMANTIC_COVERAGE_IDENTITY_INVALID")
    identity = "\x00".join(
        (
            "semantic-coverage-v2",
            language,
            path,
            subject_kind,
            qualified_name,
            str(occurrence),
        )
    ).encode("utf-8")
    return f"{language}:sha256:{hashlib.sha256(identity).hexdigest()}"


_JAVA_STRUCTURAL_WRAPPER_SIGNATURE: Final[dict[str, object]] = {
    "type_kind": "CLASS",
    "visibility": "public",
    "storage": "top-level",
    "modifiers": ["final", "public"],
    "final": True,
    "abstract": False,
    "extends": "",
    "implements": [],
    "type_parameters": [],
    "annotations": [],
    "permits": [],
}


def _java_subject_signature(subject: Mapping[str, object]) -> Mapping[str, object] | None:
    signature = subject.get("source_signature")
    if isinstance(signature, Mapping):
        return signature
    signature = subject.get("signature")
    return signature if isinstance(signature, Mapping) else None


def _java_subject_span(
    subject: Mapping[str, object],
    source_file: str,
) -> tuple[int, int] | None:
    span = subject.get("source_span")
    if not isinstance(span, Mapping) or span.get("file") != PurePosixPath(source_file).name:
        return None
    start = span.get("start_byte")
    end = span.get("end_byte")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        return None
    return start, end


def verified_java_structural_wrapper(
    subjects: Sequence[Mapping[str, object]],
    source_file: str,
) -> dict[str, object] | None:
    """Recognize only the exact Java class shell used by the bounded profile.

    Comments are intentionally absent from the compiler inventory, so arbitrary
    leading comments do not affect this decision. Everything with Java
    semantics remains compiler-indexed: an attribute, inheritance clause,
    field, initializer, constructor, nested type, second top-level type, or a
    method outside the class span makes the shell ineligible for structural
    treatment. The caller must then retain the original conversion blocker.
    """

    wrappers = [
        subject
        for subject in subjects
        if subject.get("declaration_kind") == "top-level-class-wrapper"
    ]
    if len(wrappers) != 1:
        return None
    wrapper = wrappers[0]
    expected_name = PurePosixPath(source_file).stem
    wrapper_candidate = wrapper.get("candidate", wrapper.get("analyzable"))
    if (
        wrapper.get("name") != expected_name
        or wrapper.get("qualified_name") != expected_name
        or wrapper.get("occurrence") != 1
        or wrapper_candidate is not False
        or dict(_java_subject_signature(wrapper) or {}) != _JAVA_STRUCTURAL_WRAPPER_SIGNATURE
    ):
        return None
    wrapper_span = _java_subject_span(wrapper, source_file)
    if wrapper_span is None:
        return None
    wrapper_start, wrapper_end = wrapper_span

    members: list[dict[str, object]] = []
    forbidden_kinds = {
        "constructor",
        "field",
        "instance-initializer",
        "nested-type",
        "static-initializer",
        "top-level-type-obligation",
    }
    for subject in subjects:
        if subject is wrapper:
            continue
        declaration_kind = subject.get("declaration_kind")
        if declaration_kind in forbidden_kinds:
            return None
        if declaration_kind != "method":
            continue
        name = subject.get("name")
        qualified_name = subject.get("qualified_name")
        occurrence = subject.get("occurrence")
        member_span = _java_subject_span(subject, source_file)
        signature = _java_subject_signature(subject)
        if (
            not isinstance(name, str)
            or not isinstance(qualified_name, str)
            or qualified_name != f"{expected_name}.{name}"
            or not isinstance(occurrence, int)
            or occurrence < 1
            or member_span is None
            or signature is None
            or not (wrapper_start <= member_span[0] and member_span[1] <= wrapper_end)
        ):
            return None
        candidate = subject.get("candidate", subject.get("analyzable"))
        if candidate is True and signature.get("static") is not True:
            return None
        members.append(
            {
                "name": name,
                "qualified_name": qualified_name,
                "declaration_kind": "method",
                "occurrence": occurrence,
                "source_span": dict(cast(Mapping[str, object], subject["source_span"])),
            }
        )

    def member_sort_key(item: Mapping[str, object]) -> tuple[int, str]:
        span = cast(Mapping[str, object], item["source_span"])
        start = span["start_byte"]
        if not isinstance(start, int):
            raise ProjectGraphError("JAVA_STRUCTURAL_WRAPPER_MEMBER_SPAN_INVALID")
        return start, str(item["qualified_name"])

    return {
        "status": "EXACT_AND_CLOSED",
        "profile": "java-top-level-class-structural-wrapper-v1",
        "file": source_file,
        "name": expected_name,
        "source_span": dict(cast(Mapping[str, object], wrapper["source_span"])),
        "member_span_status": "ALL_METHODS_CONTAINED",
        "member_subjects": sorted(members, key=member_sort_key),
    }


@dataclass(frozen=True)
class _ScannedFile:
    path: str
    role: FileRole
    language: str | None
    content: bytes | None
    sha256: str | None
    byte_count: int | None
    read_status: EvidenceStatus


@dataclass(frozen=True)
class _Dependency:
    ecosystem: str
    name: str
    constraint: str | None
    scope: str


@dataclass(frozen=True)
class _DescriptorIssue:
    code: str
    message: str
    status: EvidenceStatus
    required_evidence: str


@dataclass(frozen=True)
class _ParsedDescriptor:
    parser: str
    dependencies: tuple[_Dependency, ...]
    issues: tuple[_DescriptorIssue, ...]


class _DuplicateJsonKey(ValueError):
    pass


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _stable_id(kind: str, repository_ref: str, *identity: str) -> str:
    payload = "\x00".join((SCHEMA_VERSION, repository_ref, kind, *identity)).encode("utf-8")
    return f"elmos:{kind}:sha256:{_sha256_bytes(payload)}"


def _edge_id(repository_ref: str, kind: EdgeKind, source_id: str, target_id: str, discriminator: str) -> str:
    return _stable_id("edge", repository_ref, kind, source_id, target_id, discriminator)


def _normalise_repository_ref(repository_ref: str) -> str:
    value = repository_ref.strip()
    if not value or len(value) > 512:
        raise ProjectGraphError("REPOSITORY_REF_INVALID")
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise ProjectGraphError("REPOSITORY_REF_INVALID")
    return value


def _is_build_descriptor(relative: PurePosixPath) -> bool:
    name = relative.name.lower()
    return name in _BUILD_DESCRIPTOR_NAMES or name.endswith(_BUILD_DESCRIPTOR_SUFFIXES)


def _is_test_path(relative: PurePosixPath) -> bool:
    lower_parts = tuple(part.lower() for part in relative.parts[:-1])
    stem = relative.stem.lower()
    return any(part in _TEST_DIRECTORIES for part in lower_parts) or stem.startswith("test_") or stem.endswith("_test")


def _classify(relative: PurePosixPath) -> tuple[FileRole, str | None]:
    if _is_build_descriptor(relative):
        return FileRole.BUILD_DESCRIPTOR, None
    language = _SOURCE_EXTENSIONS.get(relative.suffix.lower())
    if language is not None:
        return (FileRole.TEST if _is_test_path(relative) else FileRole.SOURCE), language
    name = relative.name.lower()
    if relative.suffix.lower() in _RESOURCE_EXTENSIONS or name in _RESOURCE_NAMES:
        return FileRole.RESOURCE, None
    return FileRole.UNKNOWN, None


def _stable_read(path: Path) -> bytes:
    flags = os.O_RDONLY
    no_follow = cast(int, getattr(os, "O_NOFOLLOW", 0))
    flags |= no_follow
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ProjectGraphError("ENTRY_NOT_REGULAR_FILE")
        if before.st_size > MAX_FILE_BYTES:
            raise ProjectGraphError("FILE_SIZE_LIMIT_EXCEEDED")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        stable = (
            before.st_dev == after.st_dev
            and before.st_ino == after.st_ino
            and before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
            and before.st_ctime_ns == after.st_ctime_ns
            and len(content) == before.st_size
        )
        if not stable:
            raise ProjectGraphError("FILE_CHANGED_DURING_READ")
        return content
    finally:
        os.close(descriptor)


def _walk_repository(root: Path) -> tuple[list[_ScannedFile], list[tuple[str, str]]]:
    scanned: list[_ScannedFile] = []
    inventory_issues: list[tuple[str, str]] = []
    total_bytes = 0

    def on_error(error: OSError) -> None:
        filename = error.filename or "."
        try:
            relative = Path(filename).resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            relative = str(filename)
        inventory_issues.append((relative, f"DIRECTORY_SCAN_FAILED:{type(error).__name__}"))

    for current, directories, files in os.walk(root, topdown=True, followlinks=False, onerror=on_error):
        current_path = Path(current)
        safe_directories: list[str] = []
        for directory in sorted(directories):
            candidate = current_path / directory
            directory_relative = candidate.relative_to(root).as_posix()
            if directory in _IGNORED_DIRECTORIES:
                inventory_issues.append((directory_relative, "IGNORED_DIRECTORY_SCOPE_NOT_VERIFIED"))
                continue
            if candidate.is_symlink():
                inventory_issues.append((directory_relative, "DIRECTORY_SYMLINK_NOT_FOLLOWED"))
                continue
            safe_directories.append(directory)
        directories[:] = safe_directories

        for name in sorted(files):
            if len(scanned) >= MAX_FILES:
                raise ProjectGraphError("REPOSITORY_FILE_LIMIT_EXCEEDED")
            path = current_path / name
            file_relative = PurePosixPath(path.relative_to(root).as_posix())
            role, language = _classify(file_relative)
            if path.is_symlink():
                scanned.append(
                    _ScannedFile(
                        path=file_relative.as_posix(),
                        role=FileRole.UNKNOWN,
                        language=None,
                        content=None,
                        sha256=None,
                        byte_count=None,
                        read_status=EvidenceStatus.NOT_RUN,
                    )
                )
                inventory_issues.append((file_relative.as_posix(), "FILE_SYMLINK_NOT_READ"))
                continue
            try:
                content = _stable_read(path)
            except (OSError, ProjectGraphError) as error:
                scanned.append(
                    _ScannedFile(
                        path=file_relative.as_posix(),
                        role=role,
                        language=language,
                        content=None,
                        sha256=None,
                        byte_count=None,
                        read_status=EvidenceStatus.NOT_RUN,
                    )
                )
                inventory_issues.append((file_relative.as_posix(), f"FILE_READ_FAILED:{type(error).__name__}:{error}"))
                continue
            total_bytes += len(content)
            if total_bytes > MAX_REPOSITORY_BYTES:
                raise ProjectGraphError("REPOSITORY_BYTE_LIMIT_EXCEEDED")
            scanned.append(
                _ScannedFile(
                    path=file_relative.as_posix(),
                    role=role,
                    language=language,
                    content=content,
                    sha256=_sha256_bytes(content),
                    byte_count=len(content),
                    read_status=EvidenceStatus.PASSED,
                )
            )

    scanned.sort(key=lambda item: item.path)
    inventory_issues.sort()
    return scanned, inventory_issues


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"JSON_NON_FINITE_NUMBER_FORBIDDEN:{value}")


def _parse_json(content: bytes) -> object:
    text = content.decode("utf-8-sig")
    return cast(
        object,
        json.loads(
            text,
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        ),
    )


def _parse_toml(content: bytes) -> object:
    return cast(object, tomllib.loads(content.decode("utf-8")))


def _parse_xml(content: bytes) -> ET.Element:
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("XML_DTD_OR_ENTITY_FORBIDDEN")
    root = ET.fromstring(content)  # noqa: S314 -- bounded input; DTD/entities are rejected above.
    if sum(1 for _ in root.iter()) > MAX_XML_ELEMENTS:
        raise ValueError("XML_ELEMENT_LIMIT_EXCEEDED")
    return root


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return cast(Mapping[str, object], value)
    return None


def _sequence(value: object) -> Sequence[object] | None:
    if isinstance(value, list):
        return cast(Sequence[object], value)
    return None


def _pep508_name(requirement: str) -> str | None:
    value = requirement.strip()
    if not value:
        return None
    end = 0
    while end < len(value) and (value[end].isalnum() or value[end] in "-_."):
        end += 1
    name = value[:end]
    if not name or not name[0].isalnum() or not name[-1].isalnum():
        return None
    if end < len(value) and value[end] not in "[ (<>=!~@;":
        return None
    return name.lower().replace("_", "-").replace(".", "-")


def _dependency_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        mapping = _mapping(value)
        if mapping is None:
            return None
        return json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return None


def _json_dependencies(document: object, name: str) -> tuple[list[_Dependency], list[_DescriptorIssue]]:
    dependencies: list[_Dependency] = []
    issues: list[_DescriptorIssue] = []
    root = _mapping(document)
    if root is None:
        return dependencies, [
            _DescriptorIssue(
                "BUILD_DESCRIPTOR_ROOT_INVALID",
                f"{name} must contain a JSON object at its root.",
                EvidenceStatus.FAILED,
                "Correct the descriptor and rerun discovery.",
            )
        ]
    if name not in {"package.json", "package-lock.json", "packages.lock.json", "composer.json"}:
        return dependencies, issues

    scopes: tuple[tuple[str, str], ...]
    if name == "composer.json":
        scopes = (("require", "runtime"), ("require-dev", "development"))
        ecosystem = "composer"
    elif name == "packages.lock.json":
        scopes = (("dependencies", "locked"),)
        ecosystem = "nuget"
    else:
        scopes = (
            ("dependencies", "runtime"),
            ("devDependencies", "development"),
            ("peerDependencies", "peer"),
            ("optionalDependencies", "optional"),
        )
        ecosystem = "npm"

    for field, scope in scopes:
        raw_dependencies = root.get(field)
        if raw_dependencies is None:
            continue
        dependency_map = _mapping(raw_dependencies)
        if dependency_map is None:
            issues.append(
                _DescriptorIssue(
                    "BUILD_DEPENDENCY_SECTION_INVALID",
                    f"{name}:{field} is not an object.",
                    EvidenceStatus.UNKNOWN,
                    f"Provide schema-valid {field} dependency metadata.",
                )
            )
            continue
        for dependency_name, raw_constraint in sorted(dependency_map.items()):
            constraint = _dependency_value(raw_constraint)
            if constraint is None:
                issues.append(
                    _DescriptorIssue(
                        "BUILD_DEPENDENCY_VALUE_UNSUPPORTED",
                        f"{name}:{field}:{dependency_name} has an unsupported value.",
                        EvidenceStatus.UNKNOWN,
                        "Provide a string or object dependency constraint.",
                    )
                )
                continue
            dependencies.append(_Dependency(ecosystem, dependency_name, constraint, scope))
    return dependencies, issues


def _toml_dependencies(document: object, name: str) -> tuple[list[_Dependency], list[_DescriptorIssue]]:
    dependencies: list[_Dependency] = []
    issues: list[_DescriptorIssue] = []
    root = _mapping(document)
    if root is None:
        return dependencies, [
            _DescriptorIssue(
                "BUILD_DESCRIPTOR_ROOT_INVALID",
                f"{name} must contain a TOML table at its root.",
                EvidenceStatus.FAILED,
                "Correct the descriptor and rerun discovery.",
            )
        ]

    if name == "pyproject.toml":
        project = _mapping(root.get("project"))
        if project is not None:
            raw_dependencies = _sequence(project.get("dependencies"))
            if project.get("dependencies") is not None and raw_dependencies is None:
                issues.append(
                    _DescriptorIssue(
                        "BUILD_DEPENDENCY_SECTION_INVALID",
                        "pyproject.toml:project.dependencies is not an array.",
                        EvidenceStatus.UNKNOWN,
                        "Provide a PEP 621 dependency array.",
                    )
                )
            for raw in raw_dependencies or ():
                if not isinstance(raw, str) or (dependency_name := _pep508_name(raw)) is None:
                    issues.append(
                        _DescriptorIssue(
                            "PEP508_REQUIREMENT_UNPARSED",
                            "A project dependency could not be assigned a stable package identity.",
                            EvidenceStatus.UNKNOWN,
                            "Provide a valid PEP 508 requirement or compiler/package-manager evidence.",
                        )
                    )
                    continue
                dependencies.append(_Dependency("pypi", dependency_name, raw, "runtime"))
            optional = _mapping(project.get("optional-dependencies"))
            if optional is not None:
                for group, group_values in sorted(optional.items()):
                    entries = _sequence(group_values)
                    if entries is None:
                        issues.append(
                            _DescriptorIssue(
                                "BUILD_DEPENDENCY_SECTION_INVALID",
                                f"pyproject.toml:optional-dependencies:{group} is not an array.",
                                EvidenceStatus.UNKNOWN,
                                "Provide a PEP 621 optional dependency array.",
                            )
                        )
                        continue
                    for raw in entries:
                        if not isinstance(raw, str) or (dependency_name := _pep508_name(raw)) is None:
                            issues.append(
                                _DescriptorIssue(
                                    "PEP508_REQUIREMENT_UNPARSED",
                                    f"Optional dependency group {group} contains an invalid requirement.",
                                    EvidenceStatus.UNKNOWN,
                                    "Provide a valid PEP 508 requirement.",
                                )
                            )
                            continue
                        dependencies.append(_Dependency("pypi", dependency_name, raw, f"optional:{group}"))

        tool = _mapping(root.get("tool"))
        poetry = _mapping(tool.get("poetry")) if tool is not None else None
        poetry_dependencies = _mapping(poetry.get("dependencies")) if poetry is not None else None
        if poetry_dependencies is not None:
            for dependency_name, raw_constraint in sorted(poetry_dependencies.items()):
                if dependency_name.lower() == "python":
                    continue
                constraint = _dependency_value(raw_constraint)
                if constraint is None:
                    issues.append(
                        _DescriptorIssue(
                            "BUILD_DEPENDENCY_VALUE_UNSUPPORTED",
                            f"pyproject.toml:tool.poetry.dependencies:{dependency_name} is unsupported.",
                            EvidenceStatus.UNKNOWN,
                            "Provide a string or object Poetry dependency constraint.",
                        )
                    )
                    continue
                dependencies.append(_Dependency("pypi", dependency_name, constraint, "runtime"))

    if name in {"cargo.toml", "cargo.lock"}:
        for field, scope in (
            ("dependencies", "runtime"),
            ("dev-dependencies", "development"),
            ("build-dependencies", "build"),
        ):
            section = _mapping(root.get(field))
            if section is None:
                continue
            for dependency_name, raw_constraint in sorted(section.items()):
                constraint = _dependency_value(raw_constraint)
                if constraint is None:
                    issues.append(
                        _DescriptorIssue(
                            "BUILD_DEPENDENCY_VALUE_UNSUPPORTED",
                            f"{name}:{field}:{dependency_name} is unsupported.",
                            EvidenceStatus.UNKNOWN,
                            "Provide a string or TOML table Cargo dependency.",
                        )
                    )
                    continue
                dependencies.append(_Dependency("cargo", dependency_name, constraint, scope))
        if name == "cargo.toml":
            workspace = _mapping(root.get("workspace"))
            workspace_dependencies = _mapping(workspace.get("dependencies")) if workspace is not None else None
            if workspace_dependencies is not None:
                for dependency_name, raw_constraint in sorted(workspace_dependencies.items()):
                    constraint = _dependency_value(raw_constraint)
                    if constraint is not None:
                        dependencies.append(_Dependency("cargo", dependency_name, constraint, "workspace"))
        else:
            packages = _sequence(root.get("package"))
            for package in packages or ():
                package_map = _mapping(package)
                if package_map is None or not isinstance(package_map.get("name"), str):
                    issues.append(
                        _DescriptorIssue(
                            "CARGO_LOCK_PACKAGE_INVALID",
                            "Cargo.lock contains a package without a stable name.",
                            EvidenceStatus.UNKNOWN,
                            "Regenerate Cargo.lock with a supported Cargo version.",
                        )
                    )
                    continue
                version = package_map.get("version")
                constraint = version if isinstance(version, str) else None
                dependencies.append(_Dependency("cargo", cast(str, package_map["name"]), constraint, "locked"))
    return dependencies, issues


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_child_text(element: ET.Element, child_name: str) -> str | None:
    for child in element:
        if _xml_local_name(child.tag) == child_name and child.text is not None:
            value = child.text.strip()
            return value or None
    return None


def _xml_dependencies(root: ET.Element, name: str) -> tuple[list[_Dependency], list[_DescriptorIssue]]:
    dependencies: list[_Dependency] = []
    issues: list[_DescriptorIssue] = []
    if name == "pom.xml":
        for element in root.iter():
            if _xml_local_name(element.tag) != "dependency":
                continue
            group = _xml_child_text(element, "groupId")
            artifact = _xml_child_text(element, "artifactId")
            if group is None or artifact is None:
                issues.append(
                    _DescriptorIssue(
                        "MAVEN_DEPENDENCY_IDENTITY_MISSING",
                        "pom.xml contains a dependency without groupId/artifactId.",
                        EvidenceStatus.UNKNOWN,
                        "Provide exact Maven dependency coordinates.",
                    )
                )
                continue
            version = _xml_child_text(element, "version")
            scope = _xml_child_text(element, "scope") or "compile"
            dependencies.append(_Dependency("maven", f"{group}:{artifact}", version, scope))
    elif name.endswith((".csproj", ".fsproj", ".vbproj")) or name == "directory.packages.props":
        for element in root.iter():
            if _xml_local_name(element.tag) not in {"PackageReference", "PackageVersion"}:
                continue
            dependency_name = element.attrib.get("Include") or element.attrib.get("Update")
            if dependency_name is None:
                issues.append(
                    _DescriptorIssue(
                        "NUGET_DEPENDENCY_IDENTITY_MISSING",
                        f"{name} contains a package reference without Include/Update.",
                        EvidenceStatus.UNKNOWN,
                        "Provide an exact NuGet package identity.",
                    )
                )
                continue
            version = element.attrib.get("Version") or _xml_child_text(element, "Version")
            dependencies.append(_Dependency("nuget", dependency_name, version, "package-reference"))
    return dependencies, issues


def _descriptor_format(relative: PurePosixPath) -> str | None:
    name = relative.name.lower()
    suffix = relative.suffix.lower()
    if suffix == ".json" or name == "package.resolved":
        return "json"
    if suffix == ".toml" or name in {"cargo.lock", "poetry.lock", "uv.lock"}:
        return "toml"
    if suffix == ".xml" or name.endswith((".csproj", ".fsproj", ".vbproj", ".vcxproj")) or name.endswith(".props"):
        return "xml"
    return None


def _descriptor_semantics_supported(relative: PurePosixPath, descriptor_format: str) -> bool:
    name = relative.name.lower()
    if descriptor_format == "json":
        return name in {"composer.json", "package.json"}
    if descriptor_format == "toml":
        return name in {"cargo.lock", "cargo.toml", "pyproject.toml"}
    return name == "pom.xml" or name == "directory.packages.props" or name.endswith((".csproj", ".fsproj", ".vbproj"))


def _parse_descriptor(file: _ScannedFile) -> _ParsedDescriptor:
    if file.content is None:
        return _ParsedDescriptor(
            "none",
            (),
            (
                _DescriptorIssue(
                    "BUILD_DESCRIPTOR_NOT_READ",
                    f"{file.path} was not safely read.",
                    EvidenceStatus.NOT_RUN,
                    "Provide readable regular-file evidence and rerun discovery.",
                ),
            ),
        )
    relative = PurePosixPath(file.path)
    descriptor_format = _descriptor_format(relative)
    if descriptor_format is None:
        return _ParsedDescriptor(
            "unavailable",
            (),
            (
                _DescriptorIssue(
                    "BUILD_DESCRIPTOR_PARSER_UNAVAILABLE",
                    f"No exact parser is configured for {file.path}.",
                    EvidenceStatus.NOT_RUN,
                    "Run a native build-tool or compiler-backed descriptor indexer.",
                ),
            ),
        )
    try:
        if descriptor_format == "json":
            document = _parse_json(file.content)
            dependencies, issues = _json_dependencies(document, relative.name.lower())
            parser = "python-json"
        elif descriptor_format == "toml":
            document = _parse_toml(file.content)
            dependencies, issues = _toml_dependencies(document, relative.name.lower())
            parser = "python-tomllib"
        else:
            document = _parse_xml(file.content)
            dependencies, issues = _xml_dependencies(document, relative.name.lower())
            parser = "python-xml-elementtree-bounded"
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
        ET.ParseError,
        RecursionError,
        ValueError,
    ) as error:
        return _ParsedDescriptor(
            descriptor_format,
            (),
            (
                _DescriptorIssue(
                    "BUILD_DESCRIPTOR_PARSE_FAILED",
                    f"{file.path} failed {descriptor_format} parsing: {type(error).__name__}.",
                    EvidenceStatus.FAILED,
                    "Correct the descriptor or provide exact native parser evidence.",
                ),
            ),
        )
    if not _descriptor_semantics_supported(relative, descriptor_format):
        issues.append(
            _DescriptorIssue(
                "BUILD_DESCRIPTOR_SEMANTIC_INDEX_NOT_RUN",
                f"{file.path} passed {descriptor_format} syntax parsing but its build schema is not indexed.",
                EvidenceStatus.NOT_RUN,
                "Run the pinned native build-tool indexer and bind exact dependency evidence.",
            )
        )
    return _ParsedDescriptor(parser, tuple(dependencies), tuple(issues))


def _validate_structured_resource(file: _ScannedFile) -> _DescriptorIssue | None:
    if file.content is None:
        return None
    suffix = PurePosixPath(file.path).suffix.lower()
    if suffix not in _STRUCTURED_SUFFIXES:
        return None
    try:
        if suffix == ".json":
            _parse_json(file.content)
        elif suffix == ".toml":
            _parse_toml(file.content)
        else:
            _parse_xml(file.content)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
        ET.ParseError,
        RecursionError,
        ValueError,
    ) as error:
        return _DescriptorIssue(
            "STRUCTURED_RESOURCE_PARSE_FAILED",
            f"{file.path} failed real {suffix[1:].upper()} parsing: {type(error).__name__}.",
            EvidenceStatus.FAILED,
            "Correct the structured resource and rerun discovery.",
        )
    return None


def _module_name(path: str) -> str:
    relative = PurePosixPath(path)
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or "<repository-root>"


def _module_aliases(module_name: str) -> frozenset[str]:
    parts = module_name.split(".")
    aliases = {module_name}
    if parts and parts[0] in _SOURCE_ROOTS and len(parts) > 1:
        aliases.add(".".join(parts[1:]))
    return frozenset(aliases)


def _source_location(path: str, node: ast.AST | None = None) -> SourceLocation:
    if node is None:
        return SourceLocation(path=path)
    return SourceLocation(
        path=path,
        start_line=getattr(node, "lineno", None),
        start_column=getattr(node, "col_offset", None),
        end_line=getattr(node, "end_lineno", None),
        end_column=getattr(node, "end_col_offset", None),
    )


def _python_function_blockers(
    statement: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    nested: bool,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if nested:
        blockers.append("PYTHON_NESTED_SYMBOL_CONVERSION_UNCOVERED")
    if isinstance(statement, ast.AsyncFunctionDef):
        blockers.append("PYTHON_ASYNC_FUNCTION_CONVERSION_UNCOVERED")
    arguments = statement.args
    if (
        arguments.posonlyargs
        or arguments.vararg is not None
        or arguments.kwonlyargs
        or arguments.kwarg is not None
        or arguments.defaults
        or any(default is not None for default in arguments.kw_defaults)
        or bool(getattr(statement, "type_params", ()))
    ):
        blockers.append("PYTHON_FUNCTION_SIGNATURE_CONVERSION_UNCOVERED")
    if statement.decorator_list:
        blockers.append("PYTHON_DECORATED_SYMBOL_CONVERSION_UNCOVERED")
    return tuple(blockers)


def python_coverage_subjects(tree: ast.Module, path: str) -> tuple[PythonCoverageSubject, ...]:
    """Inventory Python declarations and module effects with exact AST identities.

    Top-level functions remain conversion candidates. Classes, nested symbols,
    definition-time signature/decorator semantics, and executable module-body
    statements are explicit blockers rather than silently disappearing from a
    file-level READY result.
    """

    subjects: list[PythonCoverageSubject] = []
    occurrences: dict[tuple[str, str], int] = {}

    def next_occurrence(subject_kind: str, qualified_name: str) -> int:
        key = (subject_kind, qualified_name)
        occurrence = occurrences.get(key, 0) + 1
        occurrences[key] = occurrence
        return occurrence

    def visit(
        body: Iterable[ast.stmt],
        scope: tuple[str, ...],
        parent_coverage_key: str | None,
    ) -> None:
        for index, statement in enumerate(body):
            if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                subject_kind = "class" if isinstance(statement, ast.ClassDef) else "function"
                declaration_kind = (
                    "class"
                    if isinstance(statement, ast.ClassDef)
                    else "async-function"
                    if isinstance(statement, ast.AsyncFunctionDef)
                    else "function"
                )
                qualified_name = ".".join((*scope, statement.name))
                occurrence = next_occurrence(subject_kind, qualified_name)
                blockers: tuple[str, ...]
                if isinstance(statement, ast.ClassDef):
                    class_blockers = ["PYTHON_CLASS_SYMBOL_CONVERSION_UNCOVERED"]
                    if scope:
                        class_blockers.append("PYTHON_NESTED_SYMBOL_CONVERSION_UNCOVERED")
                    if statement.decorator_list or statement.bases or statement.keywords:
                        class_blockers.append("PYTHON_CLASS_DEFINITION_EFFECTS_UNCOVERED")
                    blockers = tuple(class_blockers)
                else:
                    blockers = _python_function_blockers(statement, nested=bool(scope))
                subject = PythonCoverageSubject(
                    path=path,
                    name=statement.name,
                    qualified_name=qualified_name,
                    subject_kind=subject_kind,
                    declaration_kind=declaration_kind,
                    occurrence=occurrence,
                    scope_depth=len(scope),
                    parent_coverage_key=parent_coverage_key,
                    source_location=_source_location(path, statement),
                    candidate=subject_kind == "function" and not scope,
                    blocking_reasons=blockers,
                )
                subjects.append(subject)
                visit(statement.body, (*scope, statement.name), subject.coverage_key)
                continue

            if scope:
                continue
            if isinstance(statement, ast.Pass):
                continue
            if (
                index == 0
                and isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                continue
            statement_kind = type(statement).__name__
            qualified_name = f"<module>.{statement_kind}"
            occurrence = next_occurrence("top-level-effect", qualified_name)
            subjects.append(
                PythonCoverageSubject(
                    path=path,
                    name=statement_kind,
                    qualified_name=qualified_name,
                    subject_kind="top-level-effect",
                    declaration_kind=statement_kind,
                    occurrence=occurrence,
                    scope_depth=0,
                    parent_coverage_key=None,
                    source_location=_source_location(path, statement),
                    candidate=False,
                    blocking_reasons=("PYTHON_TOP_LEVEL_EFFECT_CONVERSION_UNCOVERED",),
                )
            )

    visit(tree.body, (), None)
    return tuple(subjects)


def _symbol_nodes(
    tree: ast.Module,
    path: str,
    module_id: str,
    repository_ref: str,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    tuple[PythonCoverageSubject, ...],
]:
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    subjects = python_coverage_subjects(tree, path)
    node_ids: dict[str, str] = {}
    for subject in subjects:
        node_kind = "effect" if subject.subject_kind == "top-level-effect" else "symbol"
        identity_kind = "effect" if node_kind == "effect" else "symbol"
        node_id = _stable_id(
            identity_kind,
            repository_ref,
            path,
            subject.subject_kind,
            subject.qualified_name,
            str(subject.occurrence),
        )
        node_ids[subject.coverage_key] = node_id
        nodes.append(
            {
                "id": node_id,
                "kind": node_kind,
                "name": subject.name,
                "path": path,
                "language": "python",
                "source_location": subject.source_location.to_mapping(),
                "attributes": {
                    **subject.to_mapping(),
                    "semantic_index_status": EvidenceStatus.PASSED,
                    "semantic_indexer": "cpython-ast",
                    "conversion_coverage_requirement": "REQUIRED",
                },
            }
        )

    for subject in subjects:
        node_id = node_ids[subject.coverage_key]
        parent_id = (
            node_ids.get(subject.parent_coverage_key, module_id)
            if subject.parent_coverage_key is not None
            else module_id
        )
        edges.append(
            {
                "id": _edge_id(
                    repository_ref,
                    EdgeKind.CONTAINS,
                    parent_id,
                    node_id,
                    subject.coverage_key,
                ),
                "kind": EdgeKind.CONTAINS,
                "source": parent_id,
                "target": node_id,
                "source_location": subject.source_location.to_mapping(),
                "evidence_status": EvidenceStatus.PASSED,
                "attributes": {"indexer": "cpython-ast"},
            }
        )
    return nodes, edges, subjects


def _absolute_import_name(
    module_name: str,
    imported: str | None,
    level: int,
    *,
    package_module: bool,
) -> str | None:
    if level == 0:
        return imported
    module_parts = module_name.split(".")
    package_parts = module_parts if package_module else module_parts[:-1]
    if level > len(package_parts) + 1:
        return None
    keep = len(package_parts) - level + 1
    base = package_parts[:keep]
    if imported:
        base.extend(imported.split("."))
    return ".".join(base) or None


def _import_records(
    tree: ast.Module,
    module_name: str,
    *,
    package_module: bool,
) -> list[tuple[str, ast.AST]]:
    imports: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _absolute_import_name(
                module_name,
                node.module,
                node.level,
                package_module=package_module,
            )
            if base is None:
                imports.append((f"<unresolved-relative:{node.level}>", node))
            elif node.module is None:
                imports.extend((f"{base}.{alias.name}" if base else alias.name, node) for alias in node.names)
            else:
                imports.append((base, node))
    return imports


def _has_dynamic_import(tree: ast.Module) -> ast.Call | None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            return node
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "importlib"
        ):
            return node
    return None


def _diagnostic(
    repository_ref: str,
    code: str,
    message: str,
    location: SourceLocation,
    status: EvidenceStatus,
    required_evidence: str,
    *,
    node_id: str | None = None,
) -> dict[str, object]:
    obligation_id = _stable_id(
        "diagnostic-obligation",
        repository_ref,
        code,
        location.path,
        str(location.start_line),
        node_id or "",
    )
    return {
        "id": obligation_id,
        "kind": "diagnostic-obligation",
        "code": code,
        "message": message,
        "node_id": node_id,
        "source_location": location.to_mapping(),
        "verification_status": status,
        "required_evidence": required_evidence,
        "blocks_repository_complete": True,
    }


def _node(
    node_id: str,
    kind: str,
    name: str,
    path: str | None,
    language: str | None,
    attributes: Mapping[str, object],
) -> dict[str, object]:
    return {
        "id": node_id,
        "kind": kind,
        "name": name,
        "path": path,
        "language": language,
        "attributes": dict(attributes),
    }


def _edge(
    repository_ref: str,
    kind: EdgeKind,
    source_id: str,
    target_id: str,
    location: SourceLocation,
    discriminator: str,
    attributes: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": _edge_id(repository_ref, kind, source_id, target_id, discriminator),
        "kind": kind,
        "source": source_id,
        "target": target_id,
        "source_location": location.to_mapping(),
        "evidence_status": EvidenceStatus.PASSED,
        "attributes": dict(attributes or {}),
    }


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _project_graph_digest(payload: Mapping[str, object]) -> str:
    return _sha256_bytes(_canonical_json_bytes(payload))


def _unique_items(items: Iterable[dict[str, object]], kind: str) -> list[dict[str, object]]:
    unique: dict[str, dict[str, object]] = {}
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            raise ProjectGraphError(f"{kind.upper()}_ID_INVALID")
        previous = unique.get(item_id)
        if previous is not None and previous != item:
            raise ProjectGraphError(f"{kind.upper()}_ID_COLLISION:{item_id}")
        unique[item_id] = item
    return [unique[item_id] for item_id in sorted(unique)]


def verify_project_graph(graph: Mapping[str, object]) -> bool:
    """Verify the graph's content address without trusting its claimed ID."""
    claimed = graph.get("graph_sha256")
    graph_id = graph.get("graph_id")
    if not isinstance(claimed, str) or graph_id != f"elmos:project-graph:sha256:{claimed}":
        return False
    payload = {key: value for key, value in graph.items() if key not in {"graph_id", "graph_sha256"}}
    return _project_graph_digest(payload) == claimed


def _semantic_inventory_by_path(
    semantic_discovery: Mapping[str, object] | None,
    repository_ref: str,
    scanned: Sequence[_ScannedFile],
) -> dict[str, Mapping[str, object]]:
    if semantic_discovery is None:
        return {}
    if (
        semantic_discovery.get("kind") != "elmos.repository-discovery-report"
        or semantic_discovery.get("repository_ref") != repository_ref
        or semantic_discovery.get("profile") != "typed-pure-function-v1"
    ):
        raise ProjectGraphError("SEMANTIC_DISCOVERY_IDENTITY_INVALID")
    source_language = semantic_discovery.get("source_language")
    if source_language not in SUPPORTED_LANGUAGES:
        raise ProjectGraphError("SEMANTIC_DISCOVERY_LANGUAGE_INVALID")
    raw_inventories = semantic_discovery.get("module_inventories")
    if not isinstance(raw_inventories, list):
        raise ProjectGraphError("SEMANTIC_DISCOVERY_INVENTORIES_INVALID")
    scanned_by_path = {file.path: file for file in scanned}
    inventories: dict[str, Mapping[str, object]] = {}
    for raw in raw_inventories:
        if not isinstance(raw, Mapping):
            raise ProjectGraphError("SEMANTIC_DISCOVERY_INVENTORY_INVALID")
        path = raw.get("path")
        language = raw.get("language")
        status = raw.get("enumeration_status")
        subjects = raw.get("subjects")
        diagnostics = raw.get("diagnostics")
        if not isinstance(path, str):
            raise ProjectGraphError("SEMANTIC_DISCOVERY_INVENTORY_INVALID")
        file = scanned_by_path.get(path)
        if (
            file is None
            or language != source_language
            or file.language != language
            or language == "python"
            or raw.get("source_sha256") != file.sha256
            or raw.get("profile") != "typed-pure-module-v1"
            or status not in {"FAILED", "NOT_RUN", "PASSED"}
            or not isinstance(subjects, list)
            or not isinstance(diagnostics, list)
            or path in inventories
        ):
            raise ProjectGraphError("SEMANTIC_DISCOVERY_INVENTORY_INVALID")
        inventories[path] = raw
    return inventories


def _inventory_source_location(subject: Mapping[str, object], path: str) -> SourceLocation:
    raw = subject.get("source_location")
    if not isinstance(raw, Mapping) or raw.get("path") != path:
        raise ProjectGraphError("SEMANTIC_DISCOVERY_LOCATION_INVALID")
    values: list[int | None] = []
    for name in ("start_line", "start_column", "end_line", "end_column"):
        value = raw.get(name)
        if value is not None and (not isinstance(value, int) or value < 0):
            raise ProjectGraphError("SEMANTIC_DISCOVERY_LOCATION_INVALID")
        values.append(value)
    return SourceLocation(path, *values)


def _inventory_subject_nodes(
    inventory: Mapping[str, object],
    path: str,
    language: str,
    module_id: str,
    repository_ref: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    raw_subjects = inventory.get("subjects")
    if not isinstance(raw_subjects, list):
        raise ProjectGraphError("SEMANTIC_DISCOVERY_SUBJECTS_INVALID")
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    coverage_keys: set[str] = set()
    structural_wrappers = [
        raw
        for raw in raw_subjects
        if isinstance(raw, Mapping) and raw.get("subject_kind") == "structural-wrapper"
    ]
    if structural_wrappers:
        wrapper_verification = verified_java_structural_wrapper(
            [cast(Mapping[str, object], raw) for raw in raw_subjects],
            path,
        )
        if (
            language != "java"
            or inventory.get("enumeration_status") != "PASSED"
            or len(structural_wrappers) != 1
            or wrapper_verification is None
            or structural_wrappers[0].get("structural_wrapper_verification")
            != wrapper_verification
        ):
            raise ProjectGraphError("SEMANTIC_DISCOVERY_STRUCTURAL_WRAPPER_INVALID")
    for raw in raw_subjects:
        if not isinstance(raw, Mapping):
            raise ProjectGraphError("SEMANTIC_DISCOVERY_SUBJECT_INVALID")
        name = raw.get("name")
        qualified_name = raw.get("qualified_name")
        subject_kind = raw.get("subject_kind")
        declaration_kind = raw.get("declaration_kind")
        occurrence = raw.get("occurrence")
        coverage_key = raw.get("coverage_key")
        candidate = raw.get("candidate")
        blockers = raw.get("blocking_reasons")
        semantic_status = raw.get("semantic_status")
        subject_diagnostics = raw.get("diagnostics")
        if (
            not isinstance(name, str)
            or not isinstance(qualified_name, str)
            or not isinstance(subject_kind, str)
            or not isinstance(declaration_kind, str)
            or not isinstance(occurrence, int)
            or not isinstance(coverage_key, str)
            or not isinstance(candidate, bool)
            or not isinstance(blockers, list)
            or any(not isinstance(item, str) for item in blockers)
            or semantic_status not in {"BLOCKED", "FAILED", "NOT_RUN", "PASSED"}
            or not isinstance(subject_diagnostics, list)
            or any(not isinstance(item, str) for item in subject_diagnostics)
            or raw.get("language") != language
            or raw.get("path") != path
            or coverage_key
            != semantic_coverage_key(language, path, subject_kind, qualified_name, occurrence)
            or coverage_key in coverage_keys
        ):
            raise ProjectGraphError("SEMANTIC_DISCOVERY_SUBJECT_INVALID")
        coverage_keys.add(coverage_key)
        location = _inventory_source_location(raw, path)
        structural_wrapper = subject_kind == "structural-wrapper"
        if structural_wrapper and (
            candidate is not False
            or blockers
            or semantic_status != "PASSED"
            or subject_diagnostics
        ):
            raise ProjectGraphError("SEMANTIC_DISCOVERY_STRUCTURAL_WRAPPER_INVALID")
        node_kind = "symbol" if subject_kind == "function" else "effect"
        node_id = _stable_id(
            node_kind,
            repository_ref,
            path,
            language,
            subject_kind,
            qualified_name,
            str(occurrence),
        )
        attributes = dict(raw)
        attributes.update(
            {
                "semantic_index_status": EvidenceStatus.PASSED,
                "semantic_indexer": inventory.get("analyzer") or "compiler-module-inventory",
                "conversion_coverage_requirement": (
                    "NOT_REQUIRED_STRUCTURAL_WRAPPER"
                    if structural_wrapper
                    else "REQUIRED"
                ),
            }
        )
        nodes.append(
            {
                "id": node_id,
                "kind": node_kind,
                "name": name,
                "path": path,
                "language": language,
                "source_location": location.to_mapping(),
                "attributes": attributes,
            }
        )
        edges.append(
            _edge(
                repository_ref,
                EdgeKind.CONTAINS,
                module_id,
                node_id,
                location,
                coverage_key,
                {"indexer": inventory.get("analyzer") or "compiler-module-inventory"},
            )
        )
        if not structural_wrapper and (blockers or semantic_status != "PASSED"):
            code = (
                str(blockers[0])
                if blockers
                else "NATIVE_SYMBOL_SEMANTIC_ANALYSIS_NOT_PASSED"
            )
            status = {
                "FAILED": EvidenceStatus.FAILED,
                "NOT_RUN": EvidenceStatus.NOT_RUN,
            }.get(str(semantic_status), EvidenceStatus.UNKNOWN)
            detail = ";".join(str(item) for item in subject_diagnostics) or str(semantic_status)
            diagnostics.append(
                _diagnostic(
                    repository_ref,
                    code,
                    f"{path}:{qualified_name} is not fully covered: {detail}.",
                    location,
                    status,
                    (
                        "Provide one exact compiler-indexed READY conversion unit that PASSED, "
                        "or retain this subject as an explicit repository blocker."
                    ),
                    node_id=node_id,
                )
            )
    return nodes, edges, diagnostics


def build_project_graph(
    repository: Path,
    repository_ref: str,
    semantic_discovery: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build a deterministic graph for one bounded, local repository snapshot.

    This function has no external effects and never follows symlinks.  The
    returned graph is repository-complete only when every entry is classified,
    read, and supported by the configured parser/index evidence.
    """
    safe_ref = _normalise_repository_ref(repository_ref)
    if repository.is_symlink() or not repository.is_dir():
        raise ProjectGraphError("REPOSITORY_DIRECTORY_INVALID")
    root = repository.resolve(strict=True)
    scanned, inventory_issues = _walk_repository(root)
    javascript_descriptors: dict[str, dict[str, object]] = {}
    scanned_by_path = {file.path: file for file in scanned}
    for file in scanned:
        if file.language != "javascript" or file.read_status != EvidenceStatus.PASSED:
            continue
        try:
            javascript_descriptor = javascript_esm_descriptor(root / file.path, root)
        except RouteError as error:
            raise ProjectGraphError(str(error)) from error
        if javascript_descriptor is None:
            continue
        descriptor_file = scanned_by_path.get(str(javascript_descriptor["path"]))
        if (
            descriptor_file is None
            or descriptor_file.read_status != EvidenceStatus.PASSED
            or descriptor_file.sha256 != javascript_descriptor["sha256"]
            or descriptor_file.byte_count != javascript_descriptor["bytes"]
        ):
            raise ProjectGraphError("JAVASCRIPT_ESM_DESCRIPTOR_GRAPH_BINDING_INVALID")
        javascript_descriptors[file.path] = javascript_descriptor
    semantic_inventories = _semantic_inventory_by_path(semantic_discovery, safe_ref, scanned)
    repository_id = _stable_id("repository", safe_ref, safe_ref)
    nodes: list[dict[str, object]] = [
        _node(
            repository_id,
            "repository",
            safe_ref,
            None,
            None,
            {"discovery_profile": DISCOVERY_PROFILE},
        )
    ]
    edges: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    file_ids: dict[str, str] = {}
    module_ids: dict[str, str] = {}
    module_names: dict[str, str] = {}
    python_trees: dict[str, ast.Module] = {}
    dependency_nodes: dict[tuple[str, str], str] = {}
    role_counts = {role.value: 0 for role in FileRole}
    language_counts = {language: 0 for language in SUPPORTED_LANGUAGES}

    for file in scanned:
        file_id = _stable_id("file", safe_ref, file.path)
        file_ids[file.path] = file_id
        role_counts[file.role] += 1
        if file.language is not None:
            language_counts[file.language] += 1
        file_attributes: dict[str, object] = {
            "role": file.role,
            "sha256": file.sha256,
            "byte_count": file.byte_count,
            "read_status": file.read_status,
        }
        if file.path in javascript_descriptors:
            file_attributes["javascript_esm_descriptor"] = javascript_descriptors[file.path]
        migration_obligation = {
            FileRole.BUILD_DESCRIPTOR: (
                "BUILD_DESCRIPTOR_MIGRATION_NOT_RUN",
                "build descriptor",
            ),
            FileRole.RESOURCE: ("RESOURCE_MIGRATION_NOT_RUN", "resource"),
            FileRole.TEST: ("TEST_ARTIFACT_MIGRATION_NOT_RUN", "test artifact"),
        }.get(file.role)
        if migration_obligation is not None:
            file_attributes["migration_status"] = EvidenceStatus.NOT_RUN
        nodes.append(_node(file_id, "file", PurePosixPath(file.path).name, file.path, file.language, file_attributes))
        location = SourceLocation(file.path, start_line=1, start_column=0)
        edges.append(_edge(safe_ref, EdgeKind.CONTAINS, repository_id, file_id, location, file.path))
        if file.role == FileRole.TEST:
            edges.append(_edge(safe_ref, EdgeKind.TEST, repository_id, file_id, location, file.path))
        elif file.role == FileRole.RESOURCE:
            edges.append(_edge(safe_ref, EdgeKind.RESOURCE, repository_id, file_id, location, file.path))

        if file.read_status != EvidenceStatus.PASSED:
            diagnostics.append(
                _diagnostic(
                    safe_ref,
                    "FILE_NOT_SAFELY_READ",
                    f"{file.path} has no verified content bytes.",
                    location,
                    EvidenceStatus.NOT_RUN,
                    "Provide a readable, stable, non-symlink regular file and rerun discovery.",
                    node_id=file_id,
                )
            )
        if file.role == FileRole.UNKNOWN:
            diagnostics.append(
                _diagnostic(
                    safe_ref,
                    "FILE_CLASSIFICATION_UNKNOWN",
                    f"{file.path} has no declared source, descriptor, test, or resource classification.",
                    location,
                    EvidenceStatus.UNKNOWN,
                    "Add an exact file classifier or explicitly exclude the path by versioned policy.",
                    node_id=file_id,
                )
            )
        if migration_obligation is not None:
            migration_code, artifact_label = migration_obligation
            diagnostics.append(
                _diagnostic(
                    safe_ref,
                    migration_code,
                    (
                        f"{file.path} is a {artifact_label} whose target copy/mapping and "
                        "target-side validation have not run."
                    ),
                    location,
                    EvidenceStatus.NOT_RUN,
                    (
                        "Produce a content-addressed target artifact mapping, retain the bytes "
                        "when appropriate, and validate it in the assembled target project."
                    ),
                    node_id=file_id,
                )
            )

        if file.language is not None:
            module_name = _module_name(file.path)
            module_id = _stable_id("module", safe_ref, file.path, module_name)
            module_ids[file.path] = module_id
            module_names[file.path] = module_name
            semantic_status = EvidenceStatus.NOT_RUN
            semantic_indexer = "compiler-index-required"
            if file.language == "python" and file.content is not None:
                try:
                    tree = ast.parse(file.content, filename=file.path)
                except (RecursionError, SyntaxError, ValueError) as error:
                    semantic_status = EvidenceStatus.FAILED
                    semantic_indexer = "cpython-ast"
                    error_location = SourceLocation(
                        file.path,
                        start_line=getattr(error, "lineno", None),
                        start_column=getattr(error, "offset", None),
                    )
                    diagnostics.append(
                        _diagnostic(
                            safe_ref,
                            "PYTHON_AST_PARSE_FAILED",
                            f"{file.path} failed CPython AST parsing: {type(error).__name__}.",
                            error_location,
                            EvidenceStatus.FAILED,
                            "Correct the Python syntax/encoding and rerun the AST index.",
                            node_id=module_id,
                        )
                    )
                else:
                    semantic_status = EvidenceStatus.PASSED
                    semantic_indexer = "cpython-ast"
                    python_trees[file.path] = tree
            elif file.language != "python" and file.path not in semantic_inventories:
                diagnostics.append(
                    _diagnostic(
                        safe_ref,
                        "COMPILER_SEMANTIC_INDEX_NOT_RUN",
                        f"{file.path} is {file.language}; no compiler-backed index was supplied.",
                        location,
                        EvidenceStatus.NOT_RUN,
                        f"Run the pinned {file.language} compiler indexer and bind its source map evidence.",
                        node_id=module_id,
                    )
                )
            elif file.language != "python":
                inventory = semantic_inventories[file.path]
                inventory_status = inventory.get("enumeration_status")
                semantic_status = (
                    EvidenceStatus.PASSED
                    if inventory_status == "PASSED"
                    else EvidenceStatus.FAILED
                    if inventory_status == "FAILED"
                    else EvidenceStatus.NOT_RUN
                )
                semantic_indexer = str(inventory.get("analyzer") or "compiler-module-inventory")
                if inventory_status != "PASSED":
                    raw_diagnostics = inventory.get("diagnostics")
                    detail = (
                        ";".join(str(item) for item in raw_diagnostics)
                        if isinstance(raw_diagnostics, list) and raw_diagnostics
                        else str(inventory_status)
                    )
                    diagnostics.append(
                        _diagnostic(
                            safe_ref,
                            "COMPILER_MODULE_ENUMERATION_NOT_PASSED",
                            f"{file.path} compiler module enumeration is {inventory_status}: {detail}.",
                            location,
                            semantic_status,
                            "Correct the source/toolchain failure and rerun the pinned compiler indexer.",
                            node_id=module_id,
                        )
                    )
            nodes.append(
                _node(
                    module_id,
                    "module",
                    module_name,
                    file.path,
                    file.language,
                    {
                        "file_id": file_id,
                        "semantic_index_status": semantic_status,
                        "semantic_indexer": semantic_indexer,
                    },
                )
            )
            edges.append(_edge(safe_ref, EdgeKind.CONTAINS, file_id, module_id, location, module_name))

    for path, reason in inventory_issues:
        diagnostics.append(
            _diagnostic(
                safe_ref,
                "INVENTORY_ENTRY_NOT_READ",
                f"{path}: {reason}",
                SourceLocation(path),
                EvidenceStatus.NOT_RUN,
                "Remove the unsafe entry or provide an authorized, stable inventory mechanism.",
                node_id=file_ids.get(path),
            )
        )

    for path, inventory in sorted(semantic_inventories.items()):
        semantic_file = next((item for item in scanned if item.path == path), None)
        if semantic_file is None or semantic_file.language is None:
            raise ProjectGraphError("SEMANTIC_DISCOVERY_INVENTORY_INVALID")
        subject_nodes, subject_edges, subject_diagnostics = _inventory_subject_nodes(
            inventory,
            path,
            semantic_file.language,
            module_ids[path],
            safe_ref,
        )
        nodes.extend(subject_nodes)
        edges.extend(subject_edges)
        diagnostics.extend(subject_diagnostics)

    for file in scanned:
        file_id = file_ids[file.path]
        location = SourceLocation(file.path)
        if file.role == FileRole.BUILD_DESCRIPTOR:
            parsed_descriptor = _parse_descriptor(file)
            for node in nodes:
                if node["id"] == file_id:
                    attributes = cast(dict[str, object], node["attributes"])
                    attributes["descriptor_parser"] = parsed_descriptor.parser
                    attributes["descriptor_parse_status"] = (
                        EvidenceStatus.PASSED
                        if parsed_descriptor.parser.startswith("python-")
                        else parsed_descriptor.issues[0].status
                    )
                    attributes["descriptor_semantic_status"] = (
                        EvidenceStatus.PASSED if not parsed_descriptor.issues else parsed_descriptor.issues[0].status
                    )
                    break
            for issue in parsed_descriptor.issues:
                diagnostics.append(
                    _diagnostic(
                        safe_ref,
                        issue.code,
                        issue.message,
                        location,
                        issue.status,
                        issue.required_evidence,
                        node_id=file_id,
                    )
                )
            for dependency in parsed_descriptor.dependencies:
                dependency_key = (dependency.ecosystem, dependency.name)
                dependency_id = dependency_nodes.get(dependency_key)
                if dependency_id is None:
                    dependency_id = _stable_id("dependency", safe_ref, dependency.ecosystem, dependency.name)
                    dependency_nodes[dependency_key] = dependency_id
                    nodes.append(
                        _node(
                            dependency_id,
                            "dependency",
                            dependency.name,
                            None,
                            None,
                            {"ecosystem": dependency.ecosystem},
                        )
                    )
                discriminator = f"{file.path}:{dependency.scope}:{dependency.constraint or ''}"
                edges.append(
                    _edge(
                        safe_ref,
                        EdgeKind.BUILD_DEPENDENCY,
                        file_id,
                        dependency_id,
                        location,
                        discriminator,
                        {"constraint": dependency.constraint, "scope": dependency.scope},
                    )
                )
        elif file.role == FileRole.RESOURCE:
            resource_issue = _validate_structured_resource(file)
            if resource_issue is not None:
                diagnostics.append(
                    _diagnostic(
                        safe_ref,
                        resource_issue.code,
                        resource_issue.message,
                        location,
                        resource_issue.status,
                        resource_issue.required_evidence,
                        node_id=file_id,
                    )
                )

    alias_to_paths: dict[str, list[str]] = {}
    for path, module_name in module_names.items():
        if path not in python_trees:
            continue
        for alias in _module_aliases(module_name):
            alias_to_paths.setdefault(alias, []).append(path)

    for path, tree in sorted(python_trees.items()):
        module_id = module_ids[path]
        module_name = module_names[path]
        symbol_nodes, symbol_edges, coverage_subjects = _symbol_nodes(tree, path, module_id, safe_ref)
        nodes.extend(symbol_nodes)
        edges.extend(symbol_edges)
        subject_node_ids = {
            cast(str, cast(dict[str, object], node["attributes"])["coverage_key"]): cast(str, node["id"])
            for node in symbol_nodes
        }
        for subject in coverage_subjects:
            for blocker_code in subject.blocking_reasons:
                diagnostics.append(
                    _diagnostic(
                        safe_ref,
                        blocker_code,
                        (
                            f"{path}:{subject.qualified_name} cannot be silently omitted by "
                            f"{DISCOVERY_PROFILE}."
                        ),
                        subject.source_location,
                        EvidenceStatus.UNKNOWN,
                        (
                            "Provide an exact READY/PASSED conversion unit with source trace, "
                            "or retain this subject as an explicit repository blocker."
                        ),
                        node_id=subject_node_ids[subject.coverage_key],
                    )
                )
        for imported_name, import_node in _import_records(
            tree,
            module_name,
            package_module=PurePosixPath(path).stem == "__init__",
        ):
            location = _source_location(path, import_node)
            candidates = alias_to_paths.get(imported_name, [])
            if len(candidates) == 1:
                target_id = module_ids[candidates[0]]
                resolution = "internal-exact"
            elif imported_name.split(".", 1)[0] in sys.stdlib_module_names:
                stdlib_name = imported_name.split(".", 1)[0]
                dependency_key = ("python-stdlib", stdlib_name)
                target_id = dependency_nodes.get(dependency_key, "")
                if not target_id:
                    target_id = _stable_id("dependency", safe_ref, "python-stdlib", stdlib_name)
                    dependency_nodes[dependency_key] = target_id
                    nodes.append(
                        _node(
                            target_id,
                            "dependency",
                            stdlib_name,
                            None,
                            "python",
                            {"ecosystem": "python-stdlib"},
                        )
                    )
                resolution = "stdlib-exact"
            else:
                dependency_key = ("python-import", imported_name)
                target_id = dependency_nodes.get(dependency_key, "")
                if not target_id:
                    target_id = _stable_id("dependency", safe_ref, "python-import", imported_name)
                    dependency_nodes[dependency_key] = target_id
                    nodes.append(
                        _node(
                            target_id,
                            "unresolved-import",
                            imported_name,
                            None,
                            "python",
                            {"ecosystem": "python-import", "resolution_status": EvidenceStatus.UNKNOWN},
                        )
                    )
                resolution = "unresolved"
                diagnostics.append(
                    _diagnostic(
                        safe_ref,
                        "PYTHON_IMPORT_TARGET_UNKNOWN",
                        (
                            f"{path} imports {imported_name}, which did not resolve to one exact internal "
                            "or stdlib module."
                        ),
                        location,
                        EvidenceStatus.UNKNOWN,
                        (
                            "Bind the import to an exact package/module producer using package-manager "
                            "or compiler evidence."
                        ),
                        node_id=module_id,
                    )
                )
            edges.append(
                _edge(
                    safe_ref,
                    EdgeKind.IMPORTS,
                    module_id,
                    target_id,
                    location,
                    f"{path}:{imported_name}:{location.start_line}",
                    {"import": imported_name, "resolution": resolution},
                )
            )
        dynamic_import = _has_dynamic_import(tree)
        if dynamic_import is not None:
            diagnostics.append(
                _diagnostic(
                    safe_ref,
                    "PYTHON_DYNAMIC_IMPORT_REQUIRES_EVIDENCE",
                    f"{path} contains a dynamic import call that static AST resolution cannot close.",
                    _source_location(path, dynamic_import),
                    EvidenceStatus.UNKNOWN,
                    "Provide runtime import tracing or a compiler-backed closed-world module map.",
                    node_id=module_id,
                )
            )

    nodes = _unique_items(nodes, "node")
    edges = _unique_items(edges, "edge")
    diagnostics = _unique_items(diagnostics, "diagnostic")
    snapshot_lines = [
        f"{file.path}\x00{file.sha256 or 'NOT_READ'}\x00{file.role}\x00{file.language or ''}" for file in scanned
    ]
    snapshot_lines.extend(
        f"{path}\x00EXCLUDED_NOT_READ\x00{reason}" for path, reason in inventory_issues
    )
    snapshot_sha256 = _sha256_bytes("\n".join(snapshot_lines).encode("utf-8"))
    repository_complete = not diagnostics and len(scanned) == sum(role_counts.values())
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.content-addressed-project-graph",
        "discovery_profile": DISCOVERY_PROFILE,
        "repository_ref": safe_ref,
        "repository_id": repository_id,
        "snapshot_sha256": snapshot_sha256,
        "snapshot_consistency": "PER_FILE_STABLE_READ_NON_ATOMIC",
        "javascript_esm_descriptors": [
            {"source_path": path, **descriptor}
            for path, descriptor in sorted(javascript_descriptors.items())
        ],
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "indexers": {
            "python": {
                "name": "cpython-ast",
                "runtime_version": (f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
                "status": EvidenceStatus.PASSED,
            },
            "other_languages": {
                "languages": [language for language in SUPPORTED_LANGUAGES if language != "python"],
                "status": (
                    EvidenceStatus.PASSED
                    if semantic_inventories
                    and all(
                        inventory.get("enumeration_status") == "PASSED"
                        for inventory in semantic_inventories.values()
                    )
                    else EvidenceStatus.NOT_RUN
                ),
                "module_inventory_count": len(semantic_inventories),
            },
        },
        "repository_complete": repository_complete,
        "completeness_status": "COMPLETE" if repository_complete else "INCOMPLETE",
        "inventory": {
            "file_count": len(scanned),
            "classified_file_count": sum(role_counts.values()),
            "role_counts": role_counts,
            "language_counts": language_counts,
            "ignored_directory_policy": sorted(_IGNORED_DIRECTORIES),
            "excluded_count": len(inventory_issues),
            "excluded_entries": [
                {
                    "path": path,
                    "reason": reason,
                    "verification_status": EvidenceStatus.NOT_RUN,
                }
                for path, reason in inventory_issues
            ],
            "limits": {
                "maximum_files": MAX_FILES,
                "maximum_file_bytes": MAX_FILE_BYTES,
                "maximum_repository_bytes": MAX_REPOSITORY_BYTES,
            },
        },
        "nodes": nodes,
        "edges": edges,
        "diagnostic_obligations": diagnostics,
        "execution_status": EvidenceStatus.NOT_RUN,
        "external_verification_status": EvidenceStatus.NOT_RUN,
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Repository completeness is scoped to static-project-graph-v1, not behavioral equivalence.",
            "Non-Python semantic closure is accepted only from a matching pinned compiler module inventory.",
            "Runtime calls, reflection, generated code, and deployment consumers require separate evidence sources.",
        ],
    }
    digest = _project_graph_digest(payload)
    return {
        **payload,
        "graph_sha256": digest,
        "graph_id": f"elmos:project-graph:sha256:{digest}",
    }


def write_project_graph(graph: Mapping[str, object], output: Path) -> None:
    """Write one verified graph without overwriting existing evidence."""
    if not verify_project_graph(graph):
        raise ProjectGraphError("PROJECT_GRAPH_DIGEST_INVALID")
    if output.exists():
        raise ProjectGraphError("PROJECT_GRAPH_OUTPUT_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
