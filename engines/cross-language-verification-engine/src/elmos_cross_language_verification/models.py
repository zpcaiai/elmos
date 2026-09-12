from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Language(enum.Enum):
    JAVA = "java"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    KOTLIN = "kotlin"
    SWIFT = "swift"
    CPP = "cpp"
    RUBY = "ruby"
    PHP = "php"


@dataclass
class TestCase:
    test_id: str
    name: str
    input_data: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    timeout_seconds: int = 30


@dataclass
class TestSuite:
    suite_id: str
    name: str
    source_language: Language
    target_language: Language
    test_cases: list[TestCase] = field(default_factory=list)


@dataclass
class ExecutionResult:
    test_id: str
    language: Language
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    success: bool
    output_data: dict[str, Any] | None = None


@dataclass
class ComparisonResult:
    test_id: str
    source_result: ExecutionResult
    target_result: ExecutionResult
    match: bool
    diff_summary: str | None = None


@dataclass
class VerificationReport:
    suite_id: str
    total: int
    passed: int
    failed: int
    skipped: int
    results: list[ComparisonResult]
    summary: str
    timestamp: float


@dataclass
class LanguagePair:
    source: Language
    target: Language
    supported: bool
    notes: str = ""
