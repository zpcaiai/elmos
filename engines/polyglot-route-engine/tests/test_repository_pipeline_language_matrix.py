"""Functional coverage for the complete local repository route matrix.

This suite deliberately exercises repository execution rather than route-pack
certification.  Every ordered pair receives a fresh three-file source
repository, independent behavior cases for each work unit, and a fresh output
directory.  A local pass must therefore cover source execution, translation,
target execution, assembly, and the whole-target-project build without
upgrading the route's external or certification status.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import zipfile
from decimal import Decimal
from itertools import product
from pathlib import Path, PurePosixPath
from typing import Any, cast

import pytest

from elmos_polyglot_route.models import SUPPORTED_LANGUAGES, Language
from elmos_polyglot_route.pipeline import (
    ARTIFACT_MANIFEST_NAME,
    ARTIFACT_NAME,
    REPORT_NAME,
    run_repository_pipeline,
)

DIRECTED_LANGUAGE_PAIRS: tuple[tuple[Language, Language], ...] = tuple(
    (source, target) for source, target in product(SUPPORTED_LANGUAGES, repeat=2) if source != target
)
MEDIUM_LANGUAGE_RING: tuple[tuple[Language, Language], ...] = tuple(
    (source, SUPPORTED_LANGUAGES[(index + 1) % len(SUPPORTED_LANGUAGES)])
    for index, source in enumerate(SUPPORTED_LANGUAGES)
)

_SMALL_MAXIMUM_BYTES = 8 * 1024 * 1024
_MEDIUM_MAXIMUM_BYTES = 64 * 1024 * 1024
_FILE_MAXIMUM_BYTES = 2 * 1024 * 1024
_MEDIUM_COMMENT_BYTES_PER_FILE = 1_700_000
_PHP_PROFILE_PREAMBLE = "<?php\n\ndeclare(strict_types=1);\n\n"
_ASSEMBLY_AUXILIARY_INPUTS: dict[Language, tuple[str, ...]] = {
    "python": ("src/elmos_generated/__init__.py",),
    "flutter": ("lib/main.dart",),
}

_BEHAVIOR_CASES: tuple[list[dict[str, object]], ...] = (
    [
        {"args": [2, 3], "expected": 5},
        {"args": [-4, 1], "expected": -3},
    ],
    [
        {"args": [3, 4], "expected": 12},
        {"args": [-2, 5], "expected": -10},
    ],
    [
        {"args": [9, 4], "expected": 5},
        {"args": [-2, -3], "expected": 1},
    ],
)
_MEDIUM_BEHAVIOR_CASES: dict[str, list[dict[str, object]]] = {
    "add": _BEHAVIOR_CASES[0],
    "maximum": [
        {"args": [2, 3], "expected": 3},
        {"args": [-4, -1], "expected": -1},
    ],
    "minimum": [
        {"args": [2, 3], "expected": 2},
        {"args": [-4, -1], "expected": -4},
    ],
    "multiply": _BEHAVIOR_CASES[1],
    "subtract": _BEHAVIOR_CASES[2],
}

_BINARY64_NEGATIVE_ZERO = -0.0
_BINARY64_MAXIMUM_FINITE = 1.7976931348623157e308
_BINARY64_MINIMUM_POSITIVE_SUBNORMAL = 5e-324
_JAVASCRIPT_TYPESCRIPT_REQUIRED_FP64 = {
    "8000000000000000",
    "7fefffffffffffff",
    "0000000000000001",
}
_JAVASCRIPT_TYPESCRIPT_BEHAVIOR_CASES: dict[str, list[dict[str, object]]] = {
    "choose": [
        {
            "args": [_BINARY64_NEGATIVE_ZERO, _BINARY64_MINIMUM_POSITIVE_SUBNORMAL, True],
            "expected": _BINARY64_NEGATIVE_ZERO,
        },
        {
            "args": [_BINARY64_MAXIMUM_FINITE, _BINARY64_MINIMUM_POSITIVE_SUBNORMAL, False],
            "expected": _BINARY64_MINIMUM_POSITIVE_SUBNORMAL,
        },
    ],
    "greater": [
        {
            "args": [_BINARY64_MAXIMUM_FINITE, _BINARY64_MINIMUM_POSITIVE_SUBNORMAL],
            "expected": True,
        },
        {
            "args": [_BINARY64_NEGATIVE_ZERO, _BINARY64_MINIMUM_POSITIVE_SUBNORMAL],
            "expected": False,
        },
    ],
    "identity": [
        {"args": [_BINARY64_NEGATIVE_ZERO], "expected": _BINARY64_NEGATIVE_ZERO},
        {"args": [_BINARY64_MAXIMUM_FINITE], "expected": _BINARY64_MAXIMUM_FINITE},
        {
            "args": [_BINARY64_MINIMUM_POSITIVE_SUBNORMAL],
            "expected": _BINARY64_MINIMUM_POSITIVE_SUBNORMAL,
        },
    ],
    "minimum": [
        {
            "args": [_BINARY64_MINIMUM_POSITIVE_SUBNORMAL, _BINARY64_MAXIMUM_FINITE],
            "expected": _BINARY64_MINIMUM_POSITIVE_SUBNORMAL,
        },
        {
            "args": [_BINARY64_NEGATIVE_ZERO, _BINARY64_MAXIMUM_FINITE],
            "expected": _BINARY64_NEGATIVE_ZERO,
        },
    ],
    "nonnegative": [
        {"args": [_BINARY64_NEGATIVE_ZERO], "expected": True},
        {"args": [_BINARY64_MINIMUM_POSITIVE_SUBNORMAL], "expected": True},
    ],
}

_SOURCE_FILES: dict[Language, tuple[tuple[str, str], ...]] = {
    "java": (
        (
            "Add.java",
            "public final class Add {\n    public static long add(long left, long right) { return left + right; }\n}\n",
        ),
        (
            "Multiply.java",
            "public final class Multiply {\n"
            "    public static long multiply(long left, long right) { return left * right; }\n"
            "}\n",
        ),
        (
            "Subtract.java",
            "public final class Subtract {\n"
            "    public static long subtract(long left, long right) { return left - right; }\n"
            "}\n",
        ),
    ),
    "python": (
        ("add.py", "def add(left: int, right: int) -> int:\n    return left + right\n"),
        (
            "multiply.py",
            "def multiply(left: int, right: int) -> int:\n    return left * right\n",
        ),
        (
            "subtract.py",
            "def subtract(left: int, right: int) -> int:\n    return left - right\n",
        ),
    ),
    "csharp": (
        (
            "Add.cs",
            "public static class Add\n"
            "{\n"
            "    public static long add(long left, long right) { return left + right; }\n"
            "}\n",
        ),
        (
            "Multiply.cs",
            "public static class Multiply\n"
            "{\n"
            "    public static long multiply(long left, long right) { return left * right; }\n"
            "}\n",
        ),
        (
            "Subtract.cs",
            "public static class Subtract\n"
            "{\n"
            "    public static long subtract(long left, long right) { return left - right; }\n"
            "}\n",
        ),
    ),
    "typescript": (
        (
            "add.ts",
            "export function add(left: number, right: number): number {\n  return left + right;\n}\n",
        ),
        (
            "multiply.ts",
            "export function multiply(left: number, right: number): number {\n  return left * right;\n}\n",
        ),
        (
            "subtract.ts",
            "export function subtract(left: number, right: number): number {\n  return left - right;\n}\n",
        ),
    ),
    "javascript": (
        (
            "add.mjs",
            "/**\n"
            " * @param {integer} left\n"
            " * @param {integer} right\n"
            " * @returns {integer}\n"
            " */\n"
            "export function add(left, right) {\n"
            "  return left + right;\n"
            "}\n",
        ),
        (
            "multiply.mjs",
            "/**\n"
            " * @param {integer} left\n"
            " * @param {integer} right\n"
            " * @returns {integer}\n"
            " */\n"
            "export function multiply(left, right) {\n"
            "  return left * right;\n"
            "}\n",
        ),
        (
            "subtract.mjs",
            "/**\n"
            " * @param {integer} left\n"
            " * @param {integer} right\n"
            " * @returns {integer}\n"
            " */\n"
            "export function subtract(left, right) {\n"
            "  return left - right;\n"
            "}\n",
        ),
    ),
    "go": (
        (
            "add.go",
            "package sample\n\nfunc add(left int64, right int64) int64 {\n\treturn left + right\n}\n",
        ),
        (
            "multiply.go",
            "package sample\n\nfunc multiply(left int64, right int64) int64 {\n\treturn left * right\n}\n",
        ),
        (
            "subtract.go",
            "package sample\n\nfunc subtract(left int64, right int64) int64 {\n\treturn left - right\n}\n",
        ),
    ),
    "rust": (
        ("add.rs", "fn add(left: i64, right: i64) -> i64 {\n    return left + right;\n}\n"),
        (
            "multiply.rs",
            "fn multiply(left: i64, right: i64) -> i64 {\n    return left * right;\n}\n",
        ),
        (
            "subtract.rs",
            "fn subtract(left: i64, right: i64) -> i64 {\n    return left - right;\n}\n",
        ),
    ),
    "cpp": (
        (
            "add.cpp",
            "#include <cstdint>\n\nstd::int64_t add(std::int64_t left, std::int64_t right) { return left + right; }\n",
        ),
        (
            "multiply.cpp",
            "#include <cstdint>\n\n"
            "std::int64_t multiply(std::int64_t left, std::int64_t right) { return left * right; }\n",
        ),
        (
            "subtract.cpp",
            "#include <cstdint>\n\n"
            "std::int64_t subtract(std::int64_t left, std::int64_t right) { return left - right; }\n",
        ),
    ),
    "objc": (
        ("add.m", "long long add(long long left, long long right) { return left + right; }\n"),
        (
            "multiply.m",
            "long long multiply(long long left, long long right) { return left * right; }\n",
        ),
        (
            "subtract.m",
            "long long subtract(long long left, long long right) { return left - right; }\n",
        ),
    ),
    "swift": (
        (
            "add.swift",
            "func add(_ left: Int64, _ right: Int64) -> Int64 {\n    return left + right\n}\n",
        ),
        (
            "multiply.swift",
            "func multiply(_ left: Int64, _ right: Int64) -> Int64 {\n    return left * right\n}\n",
        ),
        (
            "subtract.swift",
            "func subtract(_ left: Int64, _ right: Int64) -> Int64 {\n    return left - right\n}\n",
        ),
    ),
    "php": (
        (
            "add.php",
            "<?php\n\ndeclare(strict_types=1);\n\n"
            "function add(int $left, int $right): int { return $left + $right; }\n",
        ),
        (
            "multiply.php",
            "<?php\n\ndeclare(strict_types=1);\n\n"
            "function multiply(int $left, int $right): int { return $left * $right; }\n",
        ),
        (
            "subtract.php",
            "<?php\n\ndeclare(strict_types=1);\n\n"
            "function subtract(int $left, int $right): int { return $left - $right; }\n",
        ),
    ),
    "kotlin": (
        (
            "add.kt",
            "fun add(left: Long, right: Long): Long {\n    return left + right\n}\n",
        ),
        (
            "multiply.kt",
            "fun multiply(left: Long, right: Long): Long {\n    return left * right\n}\n",
        ),
        (
            "subtract.kt",
            "fun subtract(left: Long, right: Long): Long {\n    return left - right\n}\n",
        ),
    ),
    "react": (
        (
            "add.tsx",
            "export function add(left: number, right: number): number {\n  return left + right\n}\n",
        ),
        (
            "multiply.tsx",
            "export function multiply(left: number, right: number): number {\n  return left * right\n}\n",
        ),
        (
            "subtract.tsx",
            "export function subtract(left: number, right: number): number {\n  return left - right\n}\n",
        ),
    ),
    "flutter": (
        (
            "add.dart",
            "int add(int left, int right) => left + right;\n",
        ),
        (
            "multiply.dart",
            "int multiply(int left, int right) => left * right;\n",
        ),
        (
            "subtract.dart",
            "int subtract(int left, int right) => left - right;\n",
        ),
    ),
}

_MEDIUM_EXTRA_SOURCE_FILES: dict[Language, tuple[tuple[str, str], ...]] = {
    "java": (
        (
            "Maximum.java",
            "public final class Maximum {\n"
            "    public static long maximum(long left, long right) {\n"
            "        if (left > right) { return left; }\n"
            "        return right;\n"
            "    }\n"
            "}\n",
        ),
        (
            "Minimum.java",
            "public final class Minimum {\n"
            "    public static long minimum(long left, long right) {\n"
            "        if (left < right) { return left; }\n"
            "        return right;\n"
            "    }\n"
            "}\n",
        ),
    ),
    "python": (
        (
            "maximum.py",
            "def maximum(left: int, right: int) -> int:\n    if left > right:\n        return left\n    return right\n",
        ),
        (
            "minimum.py",
            "def minimum(left: int, right: int) -> int:\n    if left < right:\n        return left\n    return right\n",
        ),
    ),
    "csharp": (
        (
            "Maximum.cs",
            "public static class Maximum\n"
            "{\n"
            "    public static long maximum(long left, long right)\n"
            "    {\n"
            "        if (left > right) { return left; }\n"
            "        return right;\n"
            "    }\n"
            "}\n",
        ),
        (
            "Minimum.cs",
            "public static class Minimum\n"
            "{\n"
            "    public static long minimum(long left, long right)\n"
            "    {\n"
            "        if (left < right) { return left; }\n"
            "        return right;\n"
            "    }\n"
            "}\n",
        ),
    ),
    "typescript": (
        (
            "maximum.ts",
            "export function maximum(left: number, right: number): number {\n"
            "  if (left > right) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
        (
            "minimum.ts",
            "export function minimum(left: number, right: number): number {\n"
            "  if (left < right) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
    ),
    "javascript": (
        (
            "maximum.mjs",
            "/**\n"
            " * @param {integer} left\n"
            " * @param {integer} right\n"
            " * @returns {integer}\n"
            " */\n"
            "export function maximum(left, right) {\n"
            "  if (left > right) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
        (
            "minimum.mjs",
            "/**\n"
            " * @param {integer} left\n"
            " * @param {integer} right\n"
            " * @returns {integer}\n"
            " */\n"
            "export function minimum(left, right) {\n"
            "  if (left < right) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
    ),
    "go": (
        (
            "maximum.go",
            "package sample\n\nfunc maximum(left int64, right int64) int64 {\n"
            "\tif left > right { return left }\n"
            "\treturn right\n"
            "}\n",
        ),
        (
            "minimum.go",
            "package sample\n\nfunc minimum(left int64, right int64) int64 {\n"
            "\tif left < right { return left }\n"
            "\treturn right\n"
            "}\n",
        ),
    ),
    "rust": (
        (
            "maximum.rs",
            "fn maximum(left: i64, right: i64) -> i64 {\n    if left > right { return left; }\n    return right;\n}\n",
        ),
        (
            "minimum.rs",
            "fn minimum(left: i64, right: i64) -> i64 {\n    if left < right { return left; }\n    return right;\n}\n",
        ),
    ),
    "cpp": (
        (
            "maximum.cpp",
            "#include <cstdint>\n\n"
            "std::int64_t maximum(std::int64_t left, std::int64_t right) {\n"
            "    if (left > right) { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
        (
            "minimum.cpp",
            "#include <cstdint>\n\n"
            "std::int64_t minimum(std::int64_t left, std::int64_t right) {\n"
            "    if (left < right) { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
    ),
    "objc": (
        (
            "maximum.m",
            "long long maximum(long long left, long long right) {\n"
            "    if (left > right) { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
        (
            "minimum.m",
            "long long minimum(long long left, long long right) {\n"
            "    if (left < right) { return left; }\n"
            "    return right;\n"
            "}\n",
        ),
    ),
    "swift": (
        (
            "maximum.swift",
            "func maximum(_ left: Int64, _ right: Int64) -> Int64 {\n"
            "    if left > right { return left }\n"
            "    return right\n"
            "}\n",
        ),
        (
            "minimum.swift",
            "func minimum(_ left: Int64, _ right: Int64) -> Int64 {\n"
            "    if left < right { return left }\n"
            "    return right\n"
            "}\n",
        ),
    ),
    "kotlin": (
        (
            "Maximum.kt",
            "fun maximum(left: Long, right: Long): Long {\n"
            "    if (left > right) { return left }\n"
            "    return right\n"
            "}\n",
        ),
        (
            "Minimum.kt",
            "fun minimum(left: Long, right: Long): Long {\n"
            "    if (left < right) { return left }\n"
            "    return right\n"
            "}\n",
        ),
    ),
    "react": (
        (
            "maximum.tsx",
            "export function maximum(left: number, right: number): number {\n"
            "  if (left > right) { return left }\n"
            "  return right\n"
            "}\n",
        ),
        (
            "minimum.tsx",
            "export function minimum(left: number, right: number): number {\n"
            "  if (left < right) { return left }\n"
            "  return right\n"
            "}\n",
        ),
    ),
    "flutter": (
        (
            "maximum.dart",
            "int maximum(int left, int right) => left > right ? left : right;\n",
        ),
        (
            "minimum.dart",
            "int minimum(int left, int right) => left < right ? left : right;\n",
        ),
    ),
    "php": (
        (
            "maximum.php",
            "<?php\n\ndeclare(strict_types=1);\n\n"
            "function maximum(int $left, int $right): int {\n"
            "    if ($left > $right) { return $left; }\n"
            "    return $right;\n"
            "}\n",
        ),
        (
            "minimum.php",
            "<?php\n\ndeclare(strict_types=1);\n\n"
            "function minimum(int $left, int $right): int {\n"
            "    if ($left < $right) { return $left; }\n"
            "    return $right;\n"
            "}\n",
        ),
    ),
}

_JAVASCRIPT_TYPESCRIPT_SOURCE_FILES: dict[Language, tuple[tuple[str, str], ...]] = {
    "typescript": (
        (
            "choose.ts",
            "export function choose(left: number, right: number, takeLeft: boolean): number {\n"
            "  if (takeLeft) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
        (
            "greater.ts",
            "export function greater(left: number, right: number): boolean {\n  return left > right;\n}\n",
        ),
        (
            "identity.ts",
            "export function identity(value: number): number { return value; }\n",
        ),
    ),
    "javascript": (
        (
            "choose.mjs",
            "/**\n"
            " * @param {number} left\n"
            " * @param {number} right\n"
            " * @param {boolean} takeLeft\n"
            " * @returns {number}\n"
            " */\n"
            "export function choose(left, right, takeLeft) {\n"
            "  if (takeLeft) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
        (
            "greater.mjs",
            "/**\n"
            " * @param {number} left\n"
            " * @param {number} right\n"
            " * @returns {boolean}\n"
            " */\n"
            "export function greater(left, right) {\n"
            "  return left > right;\n"
            "}\n",
        ),
        (
            "identity.mjs",
            "/**\n"
            " * @param {number} value\n"
            " * @returns {number}\n"
            " */\n"
            "export function identity(value) { return value; }\n",
        ),
    ),
}

_JAVASCRIPT_TYPESCRIPT_MEDIUM_EXTRA_SOURCE_FILES: dict[Language, tuple[tuple[str, str], ...]] = {
    "typescript": (
        (
            "minimum.ts",
            "export function minimum(left: number, right: number): number {\n"
            "  if (left < right) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
        (
            "nonnegative.ts",
            "export function nonnegative(value: number): boolean { return value >= 0; }\n",
        ),
    ),
    "javascript": (
        (
            "minimum.mjs",
            "/**\n"
            " * @param {number} left\n"
            " * @param {number} right\n"
            " * @returns {number}\n"
            " */\n"
            "export function minimum(left, right) {\n"
            "  if (left < right) { return left; }\n"
            "  return right;\n"
            "}\n",
        ),
        (
            "nonnegative.mjs",
            "/**\n"
            " * @param {number} value\n"
            " * @returns {boolean}\n"
            " */\n"
            "export function nonnegative(value) { return value >= 0; }\n",
        ),
    ),
}


def _is_javascript_typescript_pair(
    source_language: Language,
    target_language: Language,
) -> bool:
    return {source_language, target_language} == {"javascript", "typescript"}


def _route_source_files(
    source_language: Language,
    target_language: Language,
) -> tuple[tuple[str, str], ...]:
    if _is_javascript_typescript_pair(source_language, target_language):
        return _JAVASCRIPT_TYPESCRIPT_SOURCE_FILES[source_language]
    return _SOURCE_FILES[source_language]


def _route_medium_source_files(
    source_language: Language,
    target_language: Language,
) -> tuple[tuple[str, str], ...]:
    if _is_javascript_typescript_pair(source_language, target_language):
        return (
            *_JAVASCRIPT_TYPESCRIPT_SOURCE_FILES[source_language],
            *_JAVASCRIPT_TYPESCRIPT_MEDIUM_EXTRA_SOURCE_FILES[source_language],
        )
    return (*_SOURCE_FILES[source_language], *_MEDIUM_EXTRA_SOURCE_FILES[source_language])


def _route_behavior_cases(
    source_language: Language,
    target_language: Language,
    name: str,
    default: list[dict[str, object]],
) -> list[dict[str, object]]:
    if _is_javascript_typescript_pair(source_language, target_language):
        return _JAVASCRIPT_TYPESCRIPT_BEHAVIOR_CASES[Path(name).stem.lower()]
    return default


def _assert_javascript_typescript_fixture_contract() -> None:
    pair_directions = {
        ("javascript", "typescript"),
        ("typescript", "javascript"),
    }
    for source_language, target_language in DIRECTED_LANGUAGE_PAIRS:
        selected = _route_source_files(source_language, target_language)
        if (source_language, target_language) in pair_directions:
            assert selected == _JAVASCRIPT_TYPESCRIPT_SOURCE_FILES[source_language]
        else:
            assert selected == _SOURCE_FILES[source_language]

    observed_fp64 = {
        _fp64_hex(expected)
        for behavior_cases in _JAVASCRIPT_TYPESCRIPT_BEHAVIOR_CASES.values()
        for behavior_case in behavior_cases
        if isinstance((expected := behavior_case["expected"]), float)
    }
    assert observed_fp64 == _JAVASCRIPT_TYPESCRIPT_REQUIRED_FP64
    for source_language in ("javascript", "typescript"):
        small = _JAVASCRIPT_TYPESCRIPT_SOURCE_FILES[source_language]
        medium = sorted(
            _route_medium_source_files(
                source_language, "typescript" if source_language == "javascript" else "javascript"
            )
        )
        assert len(small) == 3
        assert len(medium) == 5
        assert [name for name, _ in small] == sorted(name for name, _ in small)
        assert all(len(_JAVASCRIPT_TYPESCRIPT_BEHAVIOR_CASES[Path(name).stem.lower()]) >= 2 for name, _ in medium)
        assert all(
            token not in content
            for _, content in medium
            for token in (
                "return left + right",
                "return left - right",
                "return left * right",
                "return left / right",
                "return left % right",
            )
        )
        assert all(
            len(_medium_comment_filler(source_language).encode("utf-8")) + len(content.encode("utf-8"))
            < _FILE_MAXIMUM_BYTES
            for _, content in medium
        )
    assert 5 * _MEDIUM_COMMENT_BYTES_PER_FILE > _SMALL_MAXIMUM_BYTES


def _write_repository_and_cases(
    root: Path,
    source_language: Language,
    target_language: Language,
) -> tuple[Path, Path]:
    repository = root / "repository"
    cases = root / "cases"
    repository.mkdir()
    cases.mkdir()

    source_files = _route_source_files(source_language, target_language)
    assert len(source_files) == 3
    assert [name for name, _ in source_files] == sorted(name for name, _ in source_files)
    for index, ((name, content), behavior_cases) in enumerate(
        zip(source_files, _BEHAVIOR_CASES, strict=True),
        start=1,
    ):
        behavior_cases = _route_behavior_cases(
            source_language,
            target_language,
            name,
            behavior_cases,
        )
        (repository / name).write_text(content, encoding="utf-8")
        (cases / f"WU-{index:05d}.json").write_text(
            json.dumps(behavior_cases, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return repository, cases


def _medium_comment_filler(language: Language) -> str:
    prefix = "# " if language == "python" else "// "
    line = prefix + ("x" * 92) + "\n"
    repetitions = (_MEDIUM_COMMENT_BYTES_PER_FILE + len(line) - 1) // len(line)
    filler = line * repetitions
    assert len(filler.encode("utf-8")) >= _MEDIUM_COMMENT_BYTES_PER_FILE
    return filler


def _medium_source_with_filler(language: Language, content: str) -> str:
    filler = _medium_comment_filler(language)
    if language != "php":
        return filler + content
    assert content.startswith(_PHP_PROFILE_PREAMBLE)
    return _PHP_PROFILE_PREAMBLE + filler + content[len(_PHP_PROFILE_PREAMBLE) :]


def _write_medium_repository_and_cases(
    root: Path,
    source_language: Language,
    target_language: Language,
) -> tuple[Path, Path]:
    repository = root / "repository"
    cases = root / "cases"
    repository.mkdir()
    cases.mkdir()

    source_files = sorted(_route_medium_source_files(source_language, target_language))
    assert len(source_files) == 5
    for index, (name, content) in enumerate(source_files, start=1):
        source = _medium_source_with_filler(source_language, content)
        source_bytes = source.encode("utf-8")
        assert len(source_bytes) < _FILE_MAXIMUM_BYTES
        function_name = Path(name).stem.lower()
        behavior_cases = _route_behavior_cases(
            source_language,
            target_language,
            name,
            _MEDIUM_BEHAVIOR_CASES.get(function_name, []),
        )
        assert len(behavior_cases) >= 2
        (repository / name).write_bytes(source_bytes)
        (cases / f"WU-{index:05d}.json").write_text(
            json.dumps(behavior_cases, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return repository, cases


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _prefixed_sha256(content: bytes) -> str:
    return "sha256:" + _sha256(content)


def _fp64_hex(value: float) -> str:
    assert math.isfinite(value)
    return struct.pack(">d", value).hex()


def _assert_fp64_observation_evidence(
    observations: object,
    behavior_cases: list[object],
) -> set[str]:
    assert isinstance(observations, list)
    assert len(observations) == len(behavior_cases)
    observed: set[str] = set()
    for index, (observation, behavior_case) in enumerate(zip(observations, behavior_cases, strict=True)):
        assert isinstance(observation, dict)
        assert isinstance(behavior_case, dict)
        expected = behavior_case.get("expected")
        if not isinstance(expected, float):
            continue
        expected_raw = _fp64_hex(expected)
        assert observation.get("case_id") == index
        assert observation.get("status") == "RETURNED"
        assert observation.get("encoding") == "fp64-hex"
        assert observation.get("raw") == expected_raw
        value = observation.get("value")
        assert isinstance(value, float)
        assert _fp64_hex(value) == expected_raw
        observed.add(expected_raw)
    return observed


def _relative_regular_file(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    assert relative
    assert not pure.is_absolute()
    assert ".." not in pure.parts
    assert "\\" not in relative
    assert pure.as_posix() == relative
    path = root.joinpath(*pure.parts)
    assert not path.is_symlink()
    assert path.is_file()
    return path


def _canonical_json_value(value: object) -> tuple[str, object]:
    if value is None:
        return ("null", None)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, int):
        return ("number", Decimal(value).normalize())
    if isinstance(value, float):
        assert math.isfinite(value)
        return ("number", Decimal(str(value)).normalize())
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return ("array", tuple(_canonical_json_value(item) for item in value))
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        return (
            "object",
            tuple(sorted((key, _canonical_json_value(item)) for key, item in value.items())),
        )
    raise AssertionError(f"non-JSON observation value: {type(value).__name__}")


def _semantic_observation_set(
    observations: object,
) -> set[tuple[int, str, tuple[str, object]]]:
    assert isinstance(observations, list)
    normalized: set[tuple[int, str, tuple[str, object]]] = set()
    for observation in observations:
        assert isinstance(observation, dict)
        case_id = observation.get("case_id")
        status = observation.get("status")
        assert isinstance(case_id, int)
        assert isinstance(status, str)
        normalized.add(
            (
                case_id,
                status,
                _canonical_json_value(observation.get("value")),
            )
        )
    assert len(normalized) == len(observations)
    return normalized


def _assert_batch_evidence_closure(
    output: Path,
    cases: Path,
    source_language: Language,
    target_language: Language,
    expected_unit_count: int,
) -> dict[str, Any]:
    batch_root = output / "batch"
    batch = cast(
        dict[str, Any],
        json.loads((batch_root / "batch-report.json").read_text(encoding="utf-8")),
    )
    assert batch["kind"] == "elmos.repository-batch-report"
    assert batch["status"] == "COMPLETE"
    assert batch["route_id"] == f"{source_language}-to-{target_language}"
    assert batch["source_language"] == source_language
    assert batch["target_language"] == target_language
    assert batch["work_unit_count"] == expected_unit_count
    assert batch["status_counts"] == {"PASSED": expected_unit_count}
    units = batch["units"]
    assert isinstance(units, list)
    expected_ids = {f"WU-{index:05d}" for index in range(1, expected_unit_count + 1)}
    assert {unit["id"] for unit in units} == expected_ids
    source_fp64: set[str] = set()
    target_fp64: set[str] = set()

    for unit in units:
        unit_id = unit["id"]
        assert unit["status"] == "PASSED"
        assert unit["evidence_path"] == f"units/{unit_id}/route-evidence.json"
        evidence_path = _relative_regular_file(batch_root, unit["evidence_path"])
        evidence_bytes = evidence_path.read_bytes()
        assert unit["evidence_sha256"] == _prefixed_sha256(evidence_bytes)
        evidence = json.loads(evidence_bytes)

        target_path = _relative_regular_file(batch_root / "units" / unit_id, unit["target_path"])
        target_bytes = target_path.read_bytes()
        assert unit["target_sha256"] == _prefixed_sha256(target_bytes)
        assert evidence["target"]["path"] == unit["target_path"]
        assert evidence["target"]["sha256"] == unit["target_sha256"]
        assert evidence["source"]["path"] == unit["source_path"]
        assert evidence["source"]["language"] == source_language
        assert evidence["target"]["language"] == target_language
        assert evidence["route"] == f"{source_language}-to-{target_language}"
        assert evidence["status"] == "PASSED_LOCAL_UNCERTIFIED"

        case_payload = json.loads((cases / f"{unit_id}.json").read_text(encoding="utf-8"))
        assert isinstance(case_payload, list)
        case_count = len(case_payload)
        assert case_count > 0
        assert unit["behavior_case_count"] == case_count
        assert evidence["behavior_case_count"] == case_count
        source_validation = evidence["source_validation"]
        target_validation = evidence["validation"]
        assert source_validation["status"] == "PASSED"
        assert target_validation["status"] == "PASSED"
        assert source_validation["case_count"] == case_count
        assert target_validation["case_count"] == case_count

        behavior = evidence["behavior_equivalence"]
        assert behavior["status"] == "PASSED"
        assert behavior["case_count"] == case_count
        assert behavior["pass_count"] == case_count
        assert behavior["source_runtime_passed"] is True
        assert behavior["target_runtime_passed"] is True
        assert behavior["oracle_conflict_count"] == 0
        behavior_path = _relative_regular_file(
            batch_root / "units" / unit_id,
            behavior["artifact_path"],
        )
        behavior_bytes = behavior_path.read_bytes()
        assert behavior["artifact_sha256"] == _prefixed_sha256(behavior_bytes)
        behavior_artifact = json.loads(behavior_bytes)
        assert behavior_artifact["status"] == "PASSED"
        assert behavior_artifact["case_count"] == case_count
        assert behavior_artifact["pass_count"] == case_count
        assert behavior_artifact["source_runtime_passed"] is True
        assert behavior_artifact["target_runtime_passed"] is True
        assert behavior_artifact["oracle_conflict_count"] == 0
        assert behavior_artifact["counterexample_count"] == 0
        assert behavior_artifact["counterexamples"] == []

        source_observations = _semantic_observation_set(source_validation["observations"])
        target_observations = _semantic_observation_set(target_validation["observations"])
        expected_observations = {
            (
                index,
                "RETURNED",
                _canonical_json_value(case["expected"]),
            )
            for index, case in enumerate(case_payload)
        }
        assert source_observations == target_observations == expected_observations
        if _is_javascript_typescript_pair(source_language, target_language):
            source_fp64.update(
                _assert_fp64_observation_evidence(
                    source_validation["observations"],
                    case_payload,
                )
            )
            target_fp64.update(
                _assert_fp64_observation_evidence(
                    target_validation["observations"],
                    case_payload,
                )
            )
        assert evidence["external_certification_status"] == "NOT_RUN"
        assert evidence["certification_status"] == "EXPERIMENTAL"
    if _is_javascript_typescript_pair(source_language, target_language):
        assert source_fp64 == target_fp64 == _JAVASCRIPT_TYPESCRIPT_REQUIRED_FP64
    return batch


def _assert_assembly_closure(
    output: Path,
    batch: dict[str, Any],
    source_language: Language,
    target_language: Language,
    expected_unit_count: int,
) -> dict[str, Any]:
    assembled = output / "assembled"
    manifest = cast(
        dict[str, Any],
        json.loads((assembled / "assembly-manifest.json").read_text(encoding="utf-8")),
    )
    assert manifest["kind"] == "elmos.repository-assembly-report"
    assert manifest["status"] == "ASSEMBLED"
    assert manifest["route_id"] == f"{source_language}-to-{target_language}"
    assert manifest["source_language"] == source_language
    assert manifest["target_language"] == target_language
    assert manifest["batch_status"] == "COMPLETE"
    assert manifest["included_unit_count"] == expected_unit_count
    assert manifest["excluded_unit_count"] == 0
    assert manifest["excluded_units"] == []
    assert manifest["build_verification_status"] == "PASSED"
    assert manifest["build_verification"]["toolchain_language"] == target_language
    assert manifest["build_verification"]["toolchain_version"]
    assert manifest["build_verification"]["commands"]
    assert manifest["external_verification_status"] == "NOT_RUN"
    assert manifest["certification_status"] == "NOT_CERTIFIED"

    batch_units = {unit["id"]: unit for unit in batch["units"]}
    included_units = manifest["included_units"]
    assert {unit["id"] for unit in included_units} == set(batch_units)
    assembled_paths: set[str] = set()
    for included in included_units:
        unit = batch_units[included["id"]]
        assembled_path = included["assembled_path"]
        assert assembled_path not in assembled_paths
        assembled_paths.add(assembled_path)
        assert included["source_path"] == unit["source_path"]
        assert included["function_name"] == unit["function_name"]
        assert included["source_sha256"] == unit["checkpoint_identity"]["source_sha256"]
        assert included["target_sha256"] == unit["target_sha256"]

    expected_build_inputs = {
        *assembled_paths,
        *manifest["build_files"],
        *_ASSEMBLY_AUXILIARY_INPUTS.get(target_language, ()),
    }
    build_inputs = manifest["build_inputs"]
    assert manifest["build_input_count"] == len(build_inputs) == len(expected_build_inputs)
    assert [build_input["path"] for build_input in build_inputs] == sorted(expected_build_inputs)
    observed_build_inputs: dict[str, tuple[int, str]] = {}
    for build_input in build_inputs:
        relative = build_input["path"]
        assert relative not in observed_build_inputs
        content = _relative_regular_file(assembled, relative).read_bytes()
        binding = (len(content), _prefixed_sha256(content))
        assert build_input["bytes"] == binding[0]
        assert build_input["sha256"] == binding[1]
        observed_build_inputs[relative] = binding
    assert set(observed_build_inputs) == expected_build_inputs
    for included in included_units:
        assert observed_build_inputs[included["assembled_path"]] == (
            included["assembled_bytes"],
            included["assembled_sha256"],
        )
    return manifest


def _assert_artifact_closure(
    output: Path,
    report: dict[str, Any],
    assembly_manifest: dict[str, Any],
) -> None:
    manifest_path = output / ARTIFACT_MANIFEST_NAME
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["kind"] == "elmos.repository-migration-artifact-manifest"
    assert manifest["status"] == report["status"]
    assert manifest["route_id"] == report["route_id"]
    assert manifest["repository_complete"] == report["repository_complete"]
    assert manifest["repository_execution_status"] == report["repository_execution_status"]
    assert manifest["external_verification_status"] == "NOT_RUN"
    assert manifest["certification_status"] == "NOT_CERTIFIED"

    declared: dict[str, tuple[int, str]] = {}
    for entry in manifest["files"]:
        relative = entry["path"]
        assert relative not in declared
        content = _relative_regular_file(output, relative).read_bytes()
        binding = (len(content), _sha256(content))
        assert entry["bytes"] == binding[0]
        assert entry["sha256"] == binding[1]
        declared[relative] = binding
    controls = {
        ARTIFACT_NAME,
        f"{ARTIFACT_NAME}.tmp",
        ARTIFACT_MANIFEST_NAME,
        REPORT_NAME,
    }
    observed_paths = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file() and not path.is_symlink() and path.relative_to(output).as_posix() not in controls
    }
    assert set(declared) == observed_paths

    archive_path = output / ARTIFACT_NAME
    archive_bytes = archive_path.read_bytes()
    assert report["artifact"] == {
        "path": ARTIFACT_NAME,
        "bytes": len(archive_bytes),
        "sha256": _sha256(archive_bytes),
    }
    archive_bindings = {
        **declared,
        ARTIFACT_MANIFEST_NAME: (len(manifest_bytes), _sha256(manifest_bytes)),
    }
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        assert len(infos) == len({info.filename for info in infos})
        assert not any(info.is_dir() for info in infos)
        assert {info.filename for info in infos} == set(archive_bindings)
        for info in infos:
            content = archive.read(info)
            expected_bytes, expected_sha256 = archive_bindings[info.filename]
            assert info.file_size == expected_bytes == len(content)
            assert _sha256(content) == expected_sha256
        assert archive.read(ARTIFACT_MANIFEST_NAME) == manifest_bytes

        assembly_relative = "assembled/assembly-manifest.json"
        embedded_assembly_bytes = archive.read(assembly_relative)
        assert json.loads(embedded_assembly_bytes) == assembly_manifest
        assert archive_bindings[assembly_relative] == (
            len(embedded_assembly_bytes),
            _sha256(embedded_assembly_bytes),
        )
        for build_input in assembly_manifest["build_inputs"]:
            relative = f"assembled/{build_input['path']}"
            content = archive.read(relative)
            assert archive_bindings[relative] == (len(content), _sha256(content))
            assert build_input["bytes"] == len(content)
            assert build_input["sha256"] == _prefixed_sha256(content)


def test_directed_language_pair_matrix_contains_every_ordered_pair_once() -> None:
    # Live repository execution is exactly the governed active matrix. The
    # lower-level repository inventory surface retains JavaScript only for
    # explicit archived replay and must never expand this executable matrix.
    assert len(SUPPORTED_LANGUAGES) == 13
    assert "javascript" not in SUPPORTED_LANGUAGES
    assert len(DIRECTED_LANGUAGE_PAIRS) == 156
    assert len(set(DIRECTED_LANGUAGE_PAIRS)) == 156
    assert set(DIRECTED_LANGUAGE_PAIRS) == {
        (source, target)
        for source in SUPPORTED_LANGUAGES
        for target in SUPPORTED_LANGUAGES
        if source != target
    }
    _assert_javascript_typescript_fixture_contract()


def test_medium_language_ring_covers_every_source_and_target_once() -> None:
    assert len(MEDIUM_LANGUAGE_RING) == 13
    assert len(set(MEDIUM_LANGUAGE_RING)) == 13
    assert all(source != target for source, target in MEDIUM_LANGUAGE_RING)
    assert {source for source, _ in MEDIUM_LANGUAGE_RING} == set(SUPPORTED_LANGUAGES)
    assert {target for _, target in MEDIUM_LANGUAGE_RING} == set(SUPPORTED_LANGUAGES)
    content = _SOURCE_FILES["php"][0][1]
    source = _medium_source_with_filler("php", content)

    assert source.startswith(_PHP_PROFILE_PREAMBLE + "// ")
    assert source.count("<?php") == 1
    assert source.count("declare(strict_types=1);") == 1
    assert source.endswith(content[len(_PHP_PROFILE_PREAMBLE) :])


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    DIRECTED_LANGUAGE_PAIRS,
    ids=lambda language: language,
)
def test_repository_pipeline_converts_three_file_repository_for_every_directed_pair(
    tmp_path: Path,
    source_language: Language,
    target_language: Language,
) -> None:
    repository, cases = _write_repository_and_cases(tmp_path, source_language, target_language)
    output = tmp_path / "output"

    report = run_repository_pipeline(
        repository,
        f"local:functional-matrix/{source_language}-to-{target_language}",
        source_language,
        target_language,
        cases,
        output,
    )
    plan = json.loads((output / "repository-route-plan.json").read_text(encoding="utf-8"))

    assert plan["repository_scale"] == "small"
    assert plan["file_count"] == 3
    assert plan["source_file_count"] == 3
    assert 0 < plan["source_bytes"] <= _SMALL_MAXIMUM_BYTES
    assert len(plan["work_units"]) == 3
    assert all(0 < unit["source_bytes"] < _FILE_MAXIMUM_BYTES for unit in plan["work_units"])
    assert report["route_id"] == f"{source_language}-to-{target_language}"
    assert report["repository_scale"] == "small"
    assert report["work_unit_count"] == 3
    assert report["ready_count"] == 3
    assert report["unit_batch_status"] == "COMPLETE"
    assert report["status_counts"] == {"PASSED": 3}
    assert report["included_unit_count"] == 3
    assert report["build_verification"]["status"] == "PASSED"
    assert report["project_graph"]["repository_complete"] is True
    assert report["project_graph"]["completeness_status"] == "COMPLETE"
    assert report["project_graph"]["obligation_count"] == 0
    assert report["conversion_coverage"]["inventory_status"] == "PASSED"
    assert report["conversion_coverage"]["status"] == "PASSED"
    assert report["conversion_coverage"]["complete"] is True
    assert report["conversion_coverage"]["subject_count"] == 3
    assert report["conversion_coverage"]["status_counts"] == {
        "BLOCKED": 0,
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 3,
        "UNKNOWN": 0,
    }
    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["repository_execution_status"] == "PASSED_LOCAL"
    assert report["local_execution_evidence"] == "PASSED"
    assert report["independent_verification_status"] == "NOT_RUN"
    assert report["certification_status"] == "NOT_CERTIFIED"
    batch = _assert_batch_evidence_closure(output, cases, source_language, target_language, 3)
    assembly = _assert_assembly_closure(output, batch, source_language, target_language, 3)
    _assert_artifact_closure(output, report, assembly)


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    DIRECTED_LANGUAGE_PAIRS,
    ids=lambda language: language,
)
def test_repository_pipeline_converts_medium_repository_for_every_directed_pair(
    tmp_path: Path,
    source_language: Language,
    target_language: Language,
) -> None:
    repository, cases = _write_medium_repository_and_cases(
        tmp_path,
        source_language,
        target_language,
    )
    output = tmp_path / "output"

    report = run_repository_pipeline(
        repository,
        f"local:medium-functional-matrix/{source_language}-to-{target_language}",
        source_language,
        target_language,
        cases,
        output,
    )
    plan = json.loads((output / "repository-route-plan.json").read_text(encoding="utf-8"))

    assert plan["repository_scale"] == "medium"
    assert plan["file_count"] == 5
    assert plan["source_file_count"] == 5
    assert _SMALL_MAXIMUM_BYTES < plan["source_bytes"] <= _MEDIUM_MAXIMUM_BYTES
    assert len(plan["work_units"]) == 5
    assert all(0 < unit["source_bytes"] < _FILE_MAXIMUM_BYTES for unit in plan["work_units"])
    assert report["route_id"] == f"{source_language}-to-{target_language}"
    assert report["repository_scale"] == "medium"
    assert report["work_unit_count"] == 5
    assert report["ready_count"] == 5
    assert report["unit_batch_status"] == "COMPLETE"
    assert report["status_counts"] == {"PASSED": 5}
    assert report["included_unit_count"] == 5
    assert report["build_verification"]["status"] == "PASSED"
    assert report["project_graph"]["repository_complete"] is True
    assert report["project_graph"]["completeness_status"] == "COMPLETE"
    assert report["project_graph"]["obligation_count"] == 0
    assert report["conversion_coverage"]["inventory_status"] == "PASSED"
    assert report["conversion_coverage"]["status"] == "PASSED"
    assert report["conversion_coverage"]["complete"] is True
    assert report["conversion_coverage"]["subject_count"] == 5
    assert report["conversion_coverage"]["status_counts"] == {
        "BLOCKED": 0,
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 5,
        "UNKNOWN": 0,
    }
    assert report["status"] == "COMPLETE"
    assert report["repository_complete"] is True
    assert report["repository_execution_status"] == "PASSED_LOCAL"
    assert report["local_execution_evidence"] == "PASSED"
    assert report["independent_verification_status"] == "NOT_RUN"
    assert report["certification_status"] == "NOT_CERTIFIED"
    batch = _assert_batch_evidence_closure(output, cases, source_language, target_language, 5)
    assembly = _assert_assembly_closure(output, batch, source_language, target_language, 5)
    _assert_artifact_closure(output, report, assembly)


def test_repository_pending_languages_are_refused_by_the_repository_surface(tmp_path: Path) -> None:
    """Declared in the matrix, refused here -- and refused on both sides.

    Single-unit analyzer readiness and whole-repository readiness are separate
    axes. This assertion prevents the former from silently promoting the latter.
    """

    from elmos_polyglot_route.models import (
        PENDING_REPOSITORY_LANGUAGES,
        RouteError,
        is_routed_pair,
    )
    from elmos_polyglot_route.repository import plan_repository

    assert not set(PENDING_REPOSITORY_LANGUAGES) & set(REPOSITORY_SURFACE_LANGUAGES)
    repository = tmp_path / "repository"
    repository.mkdir()
    for language in PENDING_REPOSITORY_LANGUAGES:
        # Routed at the matrix level ...
        assert is_routed_pair(language, "python")
        assert is_routed_pair("python", language)
        # ... and refused at the execution boundary, in both directions.
        with pytest.raises(RouteError, match="^UNSUPPORTED_LANGUAGE$"):
            plan_repository(repository, f"local:{language}", language, "python")
        with pytest.raises(RouteError, match="^UNSUPPORTED_LANGUAGE$"):
            plan_repository(repository, f"local:{language}", "python", language)
