"""Turn repository work units into concrete, evidence-bearing verdicts.

The inventory step can only say a source file exists. Discovery answers the
question that actually determines whether a repository can be migrated: for
each file, is there a declaration the bounded route profile can lower, and if
not, exactly which construct blocks it?

The split of responsibility here is deliberate. CPython's AST inventories
Python, while each other supported language must supply a whole-file inventory
from its native compiler/parser frontend. The existing named-function analyzer
then decides whether every enumerated callable fits the bounded route profile.
The legacy declaration scanner remains a proposal-only public helper; it never
establishes repository completeness.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import stat
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from .models import (
    REPOSITORY_SURFACE_LANGUAGES,
    Language,
    RouteError,
    repository_language_lifecycle,
)
from .project_graph import (
    PythonCoverageSubject,
    SourceLocation,
    python_coverage_subjects,
    semantic_coverage_key,
    verified_java_structural_wrapper,
)
from .react_repository import (
    react_project_descriptor,
    verify_react_repository_project,
)
from .repository import javascript_esm_descriptor
from .source_analyzer import analyze_many, inventory_module

SCHEMA_VERSION = "1.0.0"
PROFILE = "typed-pure-function-v1"
MAX_CANDIDATES_PER_FILE = 40
MAX_FILE_BYTES = 2 * 1024 * 1024

# Bounded declaration scanners. These only propose names; the authoritative
# accept/reject decision is always made by the native analyzer below.
_DECLARATION_PATTERNS: dict[str, re.Pattern[str]] = {
    "java": re.compile(
        r"^\s*(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?"
        r"(?:int|long|double|float|boolean|String)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
        re.MULTILINE,
    ),
    "csharp": re.compile(
        r"^\s*(?:public|internal|protected|private)?\s*(?:static\s+)?"
        r"(?:int|long|double|float|bool|string)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "typescript": re.compile(
        r"^\s*(?:export\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
        re.MULTILINE,
    ),
    "react": re.compile(
        r"^\s*(?:export\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
        re.MULTILINE,
    ),
    "javascript": re.compile(
        r"^\s*export\s+function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
        re.MULTILINE,
    ),
    "go": re.compile(
        r"^\s*func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "kotlin": re.compile(
        r"^\s*(?:(?:public|internal|private|protected|tailrec|operator|infix)\s+)*"
        r"fun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "flutter": re.compile(
        r"^\s*(?:(?:external)\s+)?(?:int|double|bool|String)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "rust": re.compile(
        r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+|unsafe\s+|extern\s+\"C\"\s+)*"
        r"fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "cpp": re.compile(
        r"^\s*(?:(?:static|inline|constexpr)\s+)*"
        r"(?:std::int64_t|int64_t|long\s+long|long|int|double|bool|std::string)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "objc": re.compile(
        r"^\s*(?:(?:static|inline)\s+)*"
        r"(?:long\s+long|long|int|double|BOOL|NSString\s*\*)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "swift": re.compile(
        r"^\s*(?:(?:public|internal|private|fileprivate|open|static|class|final)\s+)*"
        r"func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    # PHP identifiers admit bytes 0x80-0xFF, so the class is wider than ASCII.
    # `function` is matched case-insensitively because PHP keywords are, and a
    # lone `function` with no name is an anonymous closure, which the name group
    # refuses. `&` before the name is a by-reference return, still a function
    # declaration. `static function` at file scope is not legal PHP, so the
    # prefix set is deliberately narrower than Swift's.
    "php": re.compile(
        r"^\s*(?i:function)\s+&?\s*([A-Za-z_\x80-\xff][A-Za-z0-9_\x80-\xff]*)\s*\(",
        re.MULTILINE,
    ),
}


class Verdict:
    READY = "READY"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_RUN = "NOT_RUN"
    NO_CANDIDATE_DECLARATION = "NO_CANDIDATE_DECLARATION"
    UNREADABLE = "UNREADABLE"


def propose_candidates(source: bytes, language: Language) -> list[str]:
    """Propose declaration names worth submitting to the native analyzer."""
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        return []
    if language == "python":
        try:
            tree = ast.parse(text)
        except (RecursionError, SyntaxError, ValueError):
            return []
        return [
            subject.name
            for subject in python_coverage_subjects(tree, "<candidate-source>")
            if subject.candidate
        ][:MAX_CANDIDATES_PER_FILE]
    pattern = _DECLARATION_PATTERNS.get(language)
    if pattern is None:
        return []
    seen: list[str] = []
    for match in pattern.finditer(text):
        name = match.group(1)
        # Constructors and control-flow keywords are never migratable
        # declarations; drop them before paying for a native analysis.
        if name in {"if", "for", "while", "switch", "catch", "return", "new"}:
            continue
        if name not in seen:
            seen.append(name)
        if len(seen) >= MAX_CANDIDATES_PER_FILE:
            break
    return seen


def _reason(error: Exception) -> str:
    detail = str(error).strip()
    if not detail:
        return type(error).__name__
    return detail[:300]


_COMMON_SOURCE_REJECTION_CODES = frozenset(
    {
        "UNSUPPORTED_EXPRESSION",
        "UNSUPPORTED_OPERATOR",
        "UNSUPPORTED_STATEMENT",
        "UNSUPPORTED_TYPE",
    }
)
_SOURCE_REJECTION_CODES: dict[Language, frozenset[str]] = {
    "python": frozenset(
        {
            "ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET",
            "CONDITION_MUST_BE_BOOLEAN",
            "DUPLICATE_PARAMETER",
            "LET_NAME_ALREADY_BOUND",
            "LET_TYPE_MISMATCH",
            "OPERAND_TYPE_MISMATCH",
            "PYTHON_ANNOTATED_DECLARATION_WITHOUT_VALUE",
            "PYTHON_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET",
            "PYTHON_FLOORED_MODULO_OUTSIDE_CERTIFIED_SUBSET",
            "PYTHON_PARAMETER_TYPE_REQUIRED",
            "PYTHON_RETURN_TYPE_REQUIRED",
            "PYTHON_TRUE_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET",
            "PYTHON_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET",
            "PYTHON_UNSUPPORTED_EXPRESSION",
            "PYTHON_UNSUPPORTED_LOCAL_TYPE",
            "PYTHON_UNSUPPORTED_STATEMENT",
            "RETURN_TYPE_MISMATCH",
            "STRING_ORDERING_OUTSIDE_CERTIFIED_SUBSET",
            "UNDECLARED_NAME",
        }
    ),
    "java": frozenset(
        {
            "JAVA_BOXED_NULLABLE_TYPE_OUTSIDE_CERTIFIED_SUBSET",
            "JAVA_EXACT_ARITHMETIC_TYPE_OUTSIDE_CERTIFIED_SUBSET",
            "JAVA_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET",
            "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET",
            "JAVA_INTERFACE_STRING_OUTSIDE_CERTIFIED_SUBSET",
            "JAVA_METHOD_SHAPE_OUTSIDE_CERTIFIED_SUBSET",
            "JAVA_NULL_LITERAL_OUTSIDE_CERTIFIED_SUBSET",
            "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET",
            "JAVA_UNSUPPORTED_EXPRESSION",
            "JAVA_UNSUPPORTED_OPERATOR",
            "JAVA_UNSUPPORTED_STATEMENT",
            "JAVA_UNSUPPORTED_TYPE",
        }
    ),
    "csharp": frozenset(
        {
            "CSHARP_BLOCK_BODY_REQUIRED",
            "CSHARP_EXACT_ARITHMETIC_TYPE_OUTSIDE_CERTIFIED_SUBSET",
            "CSHARP_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET",
            "CSHARP_UNSUPPORTED_EXPRESSION",
            "CSHARP_UNSUPPORTED_OPERATOR",
            "CSHARP_UNSUPPORTED_STATEMENT",
            "CSHARP_UNSUPPORTED_TYPE",
        }
    ),
    "typescript": frozenset(
        {
            "TYPESCRIPT_DESTRUCTURED_PARAMETER_UNSUPPORTED",
            "TYPESCRIPT_EXPLICIT_TYPE_REQUIRED",
            "TYPESCRIPT_FUNCTION_BODY_REQUIRED",
            "TYPESCRIPT_NEGATIVE_ZERO_LITERAL_UNSUPPORTED",
            "TYPESCRIPT_NON_FINITE_LITERAL_UNSUPPORTED",
            "TYPESCRIPT_RETURN_EXPRESSION_REQUIRED",
            "TYPESCRIPT_UNARY_MINUS_LITERAL_REQUIRED",
            "TYPESCRIPT_UNSUPPORTED_EXPRESSION",
            "TYPESCRIPT_UNSUPPORTED_OPERATOR",
            "TYPESCRIPT_UNSUPPORTED_STATEMENT",
            "TYPESCRIPT_UNSUPPORTED_TYPE",
        }
    ),
    "javascript": frozenset(
        {
            "JAVASCRIPT_ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET",
            "JAVASCRIPT_DUPLICATE_FUNCTION",
            "JAVASCRIPT_EXACT_JSDOC_TAG_SET_REQUIRED",
            "JAVASCRIPT_EXACT_JSDOC_TYPE_REQUIRED",
            "JAVASCRIPT_EXPRESSION_UNSUPPORTED",
            "JAVASCRIPT_FUNCTION_BODY_REQUIRED",
            "JAVASCRIPT_FUNCTION_SHAPE_UNSUPPORTED",
            "JAVASCRIPT_INTEGER_LITERAL_OUTSIDE_SAFE_SUBSET",
            "JAVASCRIPT_JSDOC_PARAMETER_ORDER_INVALID",
            "JAVASCRIPT_JSDOC_RETURN_INVALID",
            "JAVASCRIPT_MODULE_IMPORT_EXPORT_OUTSIDE_CERTIFIED_SUBSET",
            "JAVASCRIPT_NAMED_EXPORT_REQUIRED",
            "JAVASCRIPT_NEGATIVE_ZERO_LITERAL_UNSUPPORTED",
            "JAVASCRIPT_NON_FINITE_LITERAL_UNSUPPORTED",
            "JAVASCRIPT_OPERATOR_UNSUPPORTED",
            "JAVASCRIPT_PARAMETER_SHAPE_UNSUPPORTED",
            "JAVASCRIPT_PARSE_DIAGNOSTICS",
            "JAVASCRIPT_STATEMENT_UNSUPPORTED",
            "JAVASCRIPT_TOP_LEVEL_STATEMENT_OUTSIDE_CERTIFIED_SUBSET",
        }
    ),
    "go": frozenset(
        {
            "GO_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET",
            "GO_GENERIC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET",
            "GO_IF_INIT_OUTSIDE_CERTIFIED_SUBSET",
            "GO_INVALID_LITERAL",
            "GO_ONE_NAME_PER_PARAMETER_REQUIRED",
            "GO_RETURN_EXPRESSION_REQUIRED",
            "GO_SINGLE_RETURN_TYPE_REQUIRED",
            "GO_UNSUPPORTED_EXPRESSION",
            "GO_UNSUPPORTED_LITERAL",
            "GO_UNSUPPORTED_OPERATOR",
            "GO_UNSUPPORTED_STATEMENT",
            "GO_UNSUPPORTED_TYPE",
        }
    ),
    "rust": frozenset(
        {
            "RUST_ATTRIBUTE_OUTSIDE_CERTIFIED_SUBSET",
            "RUST_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET",
            "RUST_FUNCTION_QUALIFIER_OUTSIDE_CERTIFIED_SUBSET",
            "RUST_GENERIC_OR_VARIADIC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET",
            "RUST_INVALID_FLOAT",
            "RUST_INVALID_INTEGER",
            "RUST_INVALID_PATH",
            "RUST_METHOD_OUTSIDE_CERTIFIED_SUBSET",
            "RUST_PARAMETER_IDENTIFIER_REQUIRED",
            "RUST_RETURN_EXPRESSION_REQUIRED",
            "RUST_RETURN_TYPE_REQUIRED",
            "RUST_UNSUPPORTED_EXPRESSION",
            "RUST_UNSUPPORTED_LITERAL",
            "RUST_UNSUPPORTED_OPERATOR",
            "RUST_UNSUPPORTED_STATEMENT",
            "RUST_UNSUPPORTED_TYPE",
        }
    ),
    "cpp": frozenset(
        {
            "AMBIGUOUS_FUNCTION_DEFINITION",
            "CPP_BOOLEAN_INTEGER_COERCION_OUTSIDE_CERTIFIED_SUBSET",
            "CPP_BOOLEAN_LITERAL_TYPE_MISMATCH",
            "CPP_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET",
            "CPP_FUNCTION_BODY_REQUIRED",
            "CPP_FUNCTION_SEMANTIC_MARKERS_OUTSIDE_CERTIFIED_SUBSET",
            "CPP_INTEGER_FUNCTION_RETURN_REQUIRED",
            "CPP_INTEGER_RETURN_EXPRESSION_REQUIRED",
            "CPP_INTEGER_SPELLING_OUTSIDE_EXACT_PROFILE",
            "CPP_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET",
            "CPP_PARAMETER_NAME_REQUIRED",
            "CPP_STRING_CONSTRUCTION_OUTSIDE_CERTIFIED_SUBSET",
            "CPP_UNSUPPORTED_EXPRESSION",
            "CPP_UNSUPPORTED_OPERATOR",
            "CPP_UNSUPPORTED_STATEMENT",
            "CPP_UNSUPPORTED_TYPE",
            "SOURCE_DIAGNOSTICS_BLOCK_ANALYSIS",
        }
    ),
    "objc": frozenset(
        {
            "AMBIGUOUS_FUNCTION_DEFINITION",
            "OBJC_BOOLEAN_INTEGER_COERCION_OUTSIDE_CERTIFIED_SUBSET",
            "OBJC_BOOLEAN_LITERAL_TYPE_MISMATCH",
            "OBJC_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET",
            "OBJC_FUNCTION_BODY_REQUIRED",
            "OBJC_FUNCTION_SEMANTIC_MARKERS_OUTSIDE_CERTIFIED_SUBSET",
            "OBJC_INTEGER_FUNCTION_RETURN_REQUIRED",
            "OBJC_INTEGER_RETURN_EXPRESSION_REQUIRED",
            "OBJC_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET",
            "OBJC_PARAMETER_NAME_REQUIRED",
            "OBJC_STRING_POINTER_COMPARISON_OUTSIDE_CERTIFIED_SUBSET",
            "OBJC_UNSUPPORTED_EXPRESSION",
            "OBJC_UNSUPPORTED_OPERATOR",
            "OBJC_UNSUPPORTED_STATEMENT",
            "OBJC_UNSUPPORTED_TYPE",
            "SOURCE_DIAGNOSTICS_BLOCK_ANALYSIS",
        }
    ),
    "swift": frozenset(
        {
            "ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_CALL_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_DEFAULT_ARGUMENT_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_EXACT_ARITHMETIC_TYPE_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_EXPLICIT_RETURN_TYPE_REQUIRED",
            "SWIFT_EXPLICIT_TYPE_REQUIRED",
            "SWIFT_EXPRESSION_TYPE_UNRESOLVED",
            "SWIFT_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_FUNCTION_BODY_REQUIRED",
            "SWIFT_GENERIC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE",
            "SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_OPTIONAL_TYPE_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_PARAMETER_NAME_REQUIRED",
            "SWIFT_RETURN_WITHOUT_VALUE",
            "SWIFT_STRING_INTERPOLATION_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_THROWING_FUNCTION_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_UNSIGNED_TYPE_OUTSIDE_CERTIFIED_SUBSET",
            "SWIFT_UNSUPPORTED_CONDITION",
            "SWIFT_UNSUPPORTED_EXPRESSION",
            "SWIFT_UNSUPPORTED_FLOAT_LITERAL",
            "SWIFT_UNSUPPORTED_OPERATOR",
            "SWIFT_UNSUPPORTED_STATEMENT",
            "SWIFT_UNSUPPORTED_TYPE",
        }
    ),
    "php": frozenset(
        {
            "PHP_BY_REFERENCE_PARAMETER_OUTSIDE_CERTIFIED_SUBSET",
            "PHP_CLOSURE_OUTSIDE_CERTIFIED_SUBSET",
            "PHP_DEFAULT_ARGUMENT_OUTSIDE_CERTIFIED_SUBSET",
            "PHP_DYNAMIC_TYPE_OUTSIDE_CERTIFIED_SUBSET",
            "PHP_EXPLICIT_PARAMETER_TYPE_REQUIRED",
            "PHP_EXPLICIT_RETURN_TYPE_REQUIRED",
            "PHP_INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE",
            "PHP_LOOSE_COMPARISON_OUTSIDE_CERTIFIED_SUBSET",
            "PHP_NULLABLE_TYPE_OUTSIDE_CERTIFIED_SUBSET",
            "PHP_REFERENCE_RETURN_OUTSIDE_CERTIFIED_SUBSET",
            "PHP_STRICT_TYPES_DECLARATION_REQUIRED",
            "PHP_STRING_INTERPOLATION_OUTSIDE_CERTIFIED_SUBSET",
            "PHP_UNION_TYPE_OUTSIDE_CERTIFIED_SUBSET",
            "PHP_UNSUPPORTED_CONDITION",
            "PHP_UNSUPPORTED_EXPRESSION",
            "PHP_UNSUPPORTED_OPERATOR",
            "PHP_UNSUPPORTED_STATEMENT",
            "PHP_UNSUPPORTED_TYPE",
            "PHP_VARIADIC_PARAMETER_OUTSIDE_CERTIFIED_SUBSET",
        }
    ),
    "kotlin": frozenset(
        {
            "KOTLIN_BLOCK_BODY_REQUIRED",
            "KOTLIN_DEFAULT_ARGUMENT_UNSUPPORTED",
            "KOTLIN_DELEGATED_LOCAL_OUTSIDE_CERTIFIED_SUBSET",
            "KOTLIN_EXPLICIT_TYPE_REQUIRED",
            "KOTLIN_FUNCTION_NAME_AMBIGUOUS",
            "KOTLIN_GENERIC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET",
            "KOTLIN_IF_BLOCK_BODY_REQUIRED",
            "KOTLIN_IF_CONDITION_REQUIRED",
            "KOTLIN_IF_THEN_REQUIRED",
            "KOTLIN_INVALID_ESCAPE",
            "KOTLIN_INVALID_LITERAL",
            "KOTLIN_LABELED_RETURN_UNSUPPORTED",
            "KOTLIN_LOCAL_INITIALIZER_REQUIRED",
            "KOTLIN_LOCAL_NAME_REQUIRED",
            "KOTLIN_MUTABLE_LOCAL_OUTSIDE_CERTIFIED_SUBSET",
            "KOTLIN_NON_FINITE_LITERAL",
            "KOTLIN_PARAMETER_NAME_REQUIRED",
            "KOTLIN_RETURN_EXPRESSION_REQUIRED",
            "KOTLIN_STRING_INTERPOLATION_UNSUPPORTED",
            "KOTLIN_SUSPEND_FUNCTION_UNSUPPORTED",
            "KOTLIN_UNSUPPORTED_EXPRESSION",
            "KOTLIN_UNSUPPORTED_OPERATOR",
            "KOTLIN_UNSUPPORTED_STATEMENT",
            "KOTLIN_UNSUPPORTED_TYPE",
            "KOTLIN_VARARG_UNSUPPORTED",
        }
    ),
    "react": frozenset(
        {
            "FUNCTION_NOT_FOUND",
            "REACT_COERCIVE_EQUALITY_UNSUPPORTED",
            "REACT_COMPONENT_SEMANTICS_UNSUPPORTED",
            "REACT_EXPLICIT_TYPE_REQUIRED",
            "REACT_FREE_NAME_UNSUPPORTED",
            "REACT_FUNCTION_AMBIGUOUS",
            "REACT_FUNCTION_BODY_REQUIRED",
            "REACT_FUNCTION_MODIFIER_UNSUPPORTED",
            "REACT_FUNCTION_RETURN_NOT_TOTAL",
            "REACT_FUNCTION_SHAPE_UNSUPPORTED",
            "REACT_HOOK_SEMANTICS_UNSUPPORTED",
            "REACT_IF_CONDITION_TYPE_MISMATCH",
            "REACT_IMPORT_BOUND_SEMANTICS_UNSUPPORTED",
            "REACT_MODULE_STATEMENT_UNSUPPORTED",
            "REACT_NEGATIVE_ZERO_LITERAL_UNSUPPORTED",
            "REACT_NON_FINITE_LITERAL_UNSUPPORTED",
            "REACT_OPERAND_TYPE_MISMATCH",
            "REACT_PARAMETER_NAME_DUPLICATE",
            "REACT_PARAMETER_SHAPE_UNSUPPORTED",
            "REACT_PARSE_ERROR",
            "REACT_RETURN_TYPE_MISMATCH",
            "REACT_ROUTE_PROFILE_UNSUPPORTED",
            "REACT_UI_SEMANTICS_UNSUPPORTED",
            "REACT_UNARY_MINUS_LITERAL_REQUIRED",
            "REACT_UNSUPPORTED_OPERATOR",
            "REACT_UNSUPPORTED_TYPE",
        }
    ),
    "flutter": frozenset(
        {
            "DART_BLOCK_BODY_REQUIRED",
            "DART_CONDITION_MUST_BE_BOOLEAN",
            "DART_DIRECTIVE_UNSUPPORTED",
            "DART_DUPLICATE_PARAMETER",
            "DART_ELSE_BLOCK_BODY_REQUIRED",
            "DART_EXPLICIT_LOCAL_TYPE_REQUIRED",
            "DART_EXPLICIT_PARAMETER_TYPE_REQUIRED",
            "DART_EXPLICIT_RETURN_TYPE_REQUIRED",
            "DART_EXTERNAL_OR_AUGMENT_FUNCTION_UNSUPPORTED",
            "DART_FUNCTION_ANNOTATION_UNSUPPORTED",
            "DART_FUNCTION_BODY_EMPTY",
            "DART_GENERIC_FUNCTION_UNSUPPORTED",
            "DART_IF_BLOCK_BODY_REQUIRED",
            "DART_IF_CASE_UNSUPPORTED",
            "DART_INTEGER_LITERAL_OUT_OF_RANGE",
            "DART_INTEGER_TRUE_DIVISION_OUTSIDE_CERTIFIED_SUBSET",
            "DART_LANGUAGE_VERSION_OVERRIDE_UNSUPPORTED",
            "DART_LOCAL_INITIALIZER_REQUIRED",
            "DART_LOCAL_MUST_BE_FINAL",
            "DART_LOCAL_NAME_ALREADY_BOUND",
            "DART_LOCAL_TYPE_MISMATCH",
            "DART_MODULE_DECLARATION_UNSUPPORTED",
            "DART_NON_FINITE_LITERAL_UNSUPPORTED",
            "DART_ONE_LOCAL_PER_DECLARATION_REQUIRED",
            "DART_OPERAND_TYPE_MISMATCH",
            "DART_PARAMETER_LIST_REQUIRED",
            "DART_PARAMETER_NAME_REQUIRED",
            "DART_PARAMETER_SHAPE_UNSUPPORTED",
            "DART_PARSE_FAILED",
            "DART_PROPERTY_FUNCTION_UNSUPPORTED",
            "DART_RETURN_EXPRESSION_REQUIRED",
            "DART_RETURN_TYPE_MISMATCH",
            "DART_SCRIPT_TAG_UNSUPPORTED",
            "DART_TRUNCATING_DIVISION_REQUIRES_INTEGER_OPERANDS",
            "DART_UNARY_MINUS_LITERAL_REQUIRED",
            "DART_UNDECLARED_NAME",
            "DART_UNSUPPORTED_EXPRESSION",
            "DART_UNSUPPORTED_OPERATOR",
            "DART_UNSUPPORTED_STATEMENT",
            "DART_UNSUPPORTED_TYPE",
            "FLUTTER_UI_OR_EFFECTFUL_CALL_UNSUPPORTED",
            "FLUTTER_UI_SEMANTICS_UNSUPPORTED",
        }
    ),
}
_WRAPPED_NATIVE_DOMAIN_ERROR = re.compile(
    r"\ANATIVE_ANALYZER_FAILED:(?P<executable>/[^:\r\n]+):"
    r"(?P<detail>[A-Z][A-Z0-9_]*(?::[A-Za-z0-9_.:<>=/+,\-]+)*)\Z"
)


def _analyzer_failure_verdict(error: Exception, language: Language) -> str:
    """Separate completed source rejection from analyzer non-execution.

    Native analyzers sometimes wrap a precise source-domain rejection inside
    ``NATIVE_ANALYZER_FAILED:<executable>:<code>``.  Only the explicit,
    compiler-backed source rejection vocabulary below is semantic evidence.
    Integrity, toolchain, filesystem, timeout, malformed-output, and unknown
    failures mean analysis did not run to a trustworthy conclusion.
    """

    if not isinstance(error, RouteError):
        return Verdict.NOT_RUN
    diagnostic = str(error)
    if diagnostic.startswith("NATIVE_ANALYZER_FAILED:"):
        wrapped = _WRAPPED_NATIVE_DOMAIN_ERROR.fullmatch(diagnostic)
        if wrapped is None:
            return Verdict.NOT_RUN
        diagnostic = wrapped.group("detail")
    primary_code = diagnostic.partition(":")[0]
    if re.fullmatch(r"[A-Z][A-Z0-9_]*", primary_code) is None:
        return Verdict.NOT_RUN
    allowed = _COMMON_SOURCE_REJECTION_CODES | _SOURCE_REJECTION_CODES[language]
    return Verdict.UNSUPPORTED if primary_code in allowed else Verdict.NOT_RUN


def _python_subject_inventory(content: bytes, relative: str) -> tuple[PythonCoverageSubject, ...]:
    try:
        tree = ast.parse(content, filename=relative)
    except (RecursionError, SyntaxError, ValueError):
        return ()
    return python_coverage_subjects(tree, relative)


def _subject_blocker(
    subject: PythonCoverageSubject,
    code: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "candidate": subject.name,
        "blocker_code": code,
        "reason": reason,
        "coverage_key": subject.coverage_key,
        "source_symbol": subject.to_mapping(),
    }


def _mapped_subject_blocker(
    subject: dict[str, Any],
    code: str,
    reason: str,
    *,
    verdict: str = Verdict.UNSUPPORTED,
) -> dict[str, Any]:
    subject["semantic_status"] = "NOT_RUN" if verdict == Verdict.NOT_RUN else "BLOCKED"
    subject["diagnostics"] = [code]
    return {
        "candidate": subject.get("name"),
        "blocker_code": code,
        "reason": reason,
        "verdict": verdict,
        "coverage_key": subject.get("coverage_key"),
        "source_symbol": subject,
    }


def _location_from_byte_span(
    content: bytes,
    relative: str,
    source_span: object,
) -> SourceLocation:
    if not isinstance(source_span, dict):
        return SourceLocation(relative)
    start = source_span.get("start_byte")
    end = source_span.get("end_byte")
    if (
        source_span.get("file") != Path(relative).name
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end <= start
        or end > len(content)
    ):
        raise RouteError(f"MODULE_INVENTORY_SPAN_INVALID:{relative}")

    def line_column(offset: int) -> tuple[int, int]:
        prefix = content[:offset]
        line = prefix.count(b"\n") + 1
        last_newline = prefix.rfind(b"\n")
        return line, offset if last_newline < 0 else offset - last_newline - 1

    start_line, start_column = line_column(start)
    end_line, end_column = line_column(end)
    return SourceLocation(relative, start_line, start_column, end_line, end_column)


def _native_subject_mapping(
    raw: dict[str, Any],
    language: Language,
    relative: str,
    content: bytes,
) -> dict[str, Any]:
    name = raw.get("name")
    qualified_name = raw.get("qualified_name")
    declaration_kind = raw.get("declaration_kind")
    analyzable = raw.get("analyzable")
    occurrence = raw.get("occurrence")
    signature = raw.get("signature")
    if (
        not isinstance(name, str)
        or not isinstance(qualified_name, str)
        or not isinstance(declaration_kind, str)
        or not isinstance(analyzable, bool)
        or not isinstance(occurrence, int)
        or not isinstance(signature, dict)
    ):
        raise RouteError(f"MODULE_INVENTORY_SUBJECT_INVALID:{relative}")
    subject_kind = "function" if analyzable else "module-obligation"
    location = _location_from_byte_span(content, relative, raw.get("source_span"))
    blockers = [] if analyzable else ["NATIVE_MODULE_DECLARATION_CONVERSION_UNCOVERED"]
    coverage_key = semantic_coverage_key(
        language,
        relative,
        subject_kind,
        qualified_name,
        occurrence,
    )
    return {
        "coverage_key": coverage_key,
        "path": relative,
        "language": language,
        "name": name,
        "qualified_name": qualified_name,
        "subject_kind": subject_kind,
        "declaration_kind": declaration_kind,
        "occurrence": occurrence,
        "scope_depth": 0,
        "parent_coverage_key": None,
        "source_location": location.to_mapping(),
        "source_span": raw.get("source_span"),
        "source_signature": signature,
        "candidate": analyzable,
        "blocking_reasons": blockers,
        "semantic_status": "NOT_RUN" if analyzable else "BLOCKED",
        "diagnostics": [],
    }


def _module_inventory_blocker_subject(
    language: Language,
    relative: str,
    diagnostics: list[str],
) -> dict[str, Any]:
    coverage_key = semantic_coverage_key(
        language,
        relative,
        "module-inventory",
        "<module-inventory>",
        1,
    )
    return {
        "coverage_key": coverage_key,
        "path": relative,
        "language": language,
        "name": "<module-inventory>",
        "qualified_name": "<module-inventory>",
        "subject_kind": "module-inventory",
        "declaration_kind": "compiler-module-inventory",
        "occurrence": 1,
        "scope_depth": 0,
        "parent_coverage_key": None,
        "source_location": SourceLocation(relative).to_mapping(),
        "source_span": None,
        "source_signature": {},
        "candidate": False,
        "blocking_reasons": ["COMPILER_MODULE_ENUMERATION_NOT_PASSED"],
        "semantic_status": "NOT_RUN",
        "diagnostics": diagnostics,
    }


def _read_work_unit_source(
    repository_root: Path,
    relative: str,
) -> tuple[Path, bytes] | None:
    """Resolve and read a work-unit path without following any symlink component."""

    if repository_root.is_symlink() or not repository_root.is_dir():
        raise RouteError("REPOSITORY_DIRECTORY_INVALID")
    root = repository_root.resolve(strict=True)
    parts = PurePosixPath(relative).parts
    unresolved = root
    for part in parts:
        unresolved /= part
        if unresolved.is_symlink():
            raise RouteError(f"WORK_UNIT_PATH_SYMLINK_REJECTED:{relative}")
    try:
        resolved = unresolved.resolve(strict=True)
        resolved.relative_to(root)
    except FileNotFoundError:
        return None
    except ValueError as error:
        raise RouteError(f"WORK_UNIT_PATH_ESCAPES_REPOSITORY:{relative}") from error

    no_follow = int(getattr(os, "O_NOFOLLOW", 0))
    directory_flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | no_follow
    current_fd = os.open(root, directory_flags)
    try:
        for directory in parts[:-1]:
            next_fd = os.open(directory, directory_flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | no_follow, dir_fd=current_fd)
        try:
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode):
                raise RouteError(f"WORK_UNIT_SOURCE_NOT_REGULAR:{relative}")
            if before.st_size > MAX_FILE_BYTES:
                raise RouteError(f"WORK_UNIT_SOURCE_TOO_LARGE:{relative}")
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(file_fd, min(remaining, 64 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
            after = os.fstat(file_fd)
            if (
                before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns
                or len(content) != before.st_size
            ):
                raise RouteError(f"WORK_UNIT_CONTENT_CHANGED:{relative}")
        finally:
            os.close(file_fd)
    except OSError as error:
        raise RouteError(f"WORK_UNIT_SOURCE_OPEN_UNSAFE:{relative}") from error
    finally:
        os.close(current_fd)
    return resolved, content


def discover_unit(
    repository_root: Path,
    unit: dict[str, Any],
    source_language: Language,
) -> dict[str, Any]:
    """Classify one work unit against the bounded profile."""
    relative = str(unit.get("source_path", ""))
    if not relative or relative.startswith("/") or ".." in relative.split("/"):
        raise RouteError(f"WORK_UNIT_PATH_UNSAFE:{relative}")

    result: dict[str, Any] = {
        "id": unit.get("id"),
        "source_path": relative,
        "declared_sha256": unit.get("source_sha256"),
        "profile": PROFILE,
        "execution_status": "NOT_RUN",
    }

    source = _read_work_unit_source(repository_root, relative)
    if source is None:
        result.update(verdict=Verdict.UNREADABLE, reason="SOURCE_FILE_MISSING_OR_SYMLINK", candidates=[])
        return result
    path, content = source
    observed = hashlib.sha256(content).hexdigest()
    result["observed_sha256"] = observed
    if unit.get("source_sha256") and unit["source_sha256"] != observed:
        # The plan is content addressed. A changed file invalidates the whole
        # decomposition rather than being silently re-discovered.
        raise RouteError(f"WORK_UNIT_CONTENT_CHANGED:{relative}")
    if source_language == "javascript":
        descriptor = javascript_esm_descriptor(path, repository_root)
        if descriptor != unit.get("javascript_esm_descriptor"):
            raise RouteError(f"JAVASCRIPT_ESM_DESCRIPTOR_CHANGED:{relative}")
        if descriptor is not None:
            result["javascript_esm_descriptor"] = descriptor
    if source_language == "react":
        descriptor = react_project_descriptor(repository_root)
        if descriptor != unit.get("react_project_descriptor"):
            raise RouteError(f"REACT_PROJECT_DESCRIPTOR_CHANGED:{relative}")
        result["react_project_descriptor"] = descriptor

    coverage_subjects: list[dict[str, Any]] = []
    candidate_symbols: list[dict[str, Any]] = []
    compiler_candidate_enumeration: tuple[bool, str | None] | None = None
    coverage_blockers: list[dict[str, Any]] = []
    if source_language == "python":
        python_subjects = _python_subject_inventory(content, relative)
        coverage_subjects = [subject.to_mapping() for subject in python_subjects]
        python_candidate_subjects = [subject for subject in python_subjects if subject.candidate]
        candidate_symbols = [subject.to_mapping() for subject in python_candidate_subjects]
        for subject in python_subjects:
            for blocker_code in subject.blocking_reasons:
                coverage_blockers.append(
                    _subject_blocker(
                        subject,
                        blocker_code,
                        (
                            f"{subject.qualified_name} is not covered by the bounded "
                            f"{PROFILE} converter: {blocker_code}."
                        ),
                    )
                )
        for subject in python_candidate_subjects[MAX_CANDIDATES_PER_FILE:]:
            coverage_blockers.append(
                _subject_blocker(
                    subject,
                    "PYTHON_CANDIDATE_LIMIT_EXCEEDED",
                    (
                        f"{subject.qualified_name} exceeds the bounded per-file candidate limit "
                        f"of {MAX_CANDIDATES_PER_FILE}."
                    ),
                )
            )
        duplicate_names = {
            name
            for name, count in Counter(str(subject["name"]) for subject in candidate_symbols).items()
            if count > 1
        }
        for subject in python_subjects:
            if subject.candidate and subject.name in duplicate_names:
                coverage_blockers.append(
                    _subject_blocker(
                        subject,
                        "PYTHON_DUPLICATE_TOP_LEVEL_FUNCTION_NAME",
                        (
                            f"{subject.qualified_name} occurrence {subject.occurrence} cannot be "
                            "selected unambiguously by the native analyzer."
                        ),
                    )
                )
    else:
        try:
            raw_inventory = inventory_module(path, source_language)
        except (RouteError, OSError, ValueError) as error:
            diagnostic = _reason(error)
            blocker_verdict = _analyzer_failure_verdict(error, source_language)
            enumeration_status = "FAILED" if blocker_verdict == Verdict.UNSUPPORTED else "NOT_RUN"
            inventory_blocker = _module_inventory_blocker_subject(
                source_language,
                relative,
                [diagnostic],
            )
            coverage_subjects = [inventory_blocker]
            coverage_blockers.append(
                _mapped_subject_blocker(
                    inventory_blocker,
                    (
                        "COMPILER_MODULE_ENUMERATION_REJECTED_SOURCE"
                        if blocker_verdict == Verdict.UNSUPPORTED
                        else "COMPILER_MODULE_ENUMERATION_NOT_PASSED"
                    ),
                    (
                        f"{relative} compiler-backed module enumeration rejected the source: "
                        f"{diagnostic}"
                        if blocker_verdict == Verdict.UNSUPPORTED
                        else f"{relative} compiler-backed module enumeration did not run: {diagnostic}"
                    ),
                    verdict=blocker_verdict,
                )
            )
            result["module_inventory"] = {
                "path": relative,
                "language": source_language,
                "source_sha256": observed,
                "profile": "typed-pure-module-v1",
                "enumeration_status": enumeration_status,
                "analyzer": None,
                "analyzer_version": None,
                "subjects": coverage_subjects,
                "diagnostics": [diagnostic],
                **(
                    {"javascript_esm_descriptor": result["javascript_esm_descriptor"]}
                    if "javascript_esm_descriptor" in result
                    else {}
                ),
            }
        else:
            raw_subjects = raw_inventory.get("subjects")
            if not isinstance(raw_subjects, list):
                raise RouteError(f"MODULE_INVENTORY_SUBJECTS_INVALID:{relative}")
            coverage_subjects = [
                _native_subject_mapping(subject, source_language, relative, content)
                for subject in raw_subjects
                if isinstance(subject, dict)
            ]
            if len(coverage_subjects) != len(raw_subjects):
                raise RouteError(f"MODULE_INVENTORY_SUBJECTS_INVALID:{relative}")
            if (
                source_language == "java"
                and raw_inventory.get("enumeration_status") == "PASSED"
            ):
                wrapper_verification = verified_java_structural_wrapper(
                    coverage_subjects,
                    relative,
                )
                if wrapper_verification is not None:
                    wrapper = next(
                        subject
                        for subject in coverage_subjects
                        if subject["declaration_kind"] == "top-level-class-wrapper"
                    )
                    wrapper["subject_kind"] = "structural-wrapper"
                    wrapper["coverage_key"] = semantic_coverage_key(
                        "java",
                        relative,
                        "structural-wrapper",
                        str(wrapper["qualified_name"]),
                        int(wrapper["occurrence"]),
                    )
                    wrapper["blocking_reasons"] = []
                    wrapper["semantic_status"] = "PASSED"
                    wrapper["diagnostics"] = []
                    wrapper["structural_wrapper_verification"] = wrapper_verification
            raw_diagnostics = raw_inventory.get("diagnostics")
            if not isinstance(raw_diagnostics, list):
                raise RouteError(f"MODULE_INVENTORY_DIAGNOSTICS_INVALID:{relative}")
            diagnostic_strings: list[str] = []
            for diagnostic_item in raw_diagnostics:
                if not isinstance(diagnostic_item, str):
                    raise RouteError(f"MODULE_INVENTORY_DIAGNOSTICS_INVALID:{relative}")
                diagnostic_strings.append(diagnostic_item)
            result["module_inventory"] = {
                "path": relative,
                "language": source_language,
                "source_sha256": observed,
                "profile": "typed-pure-module-v1",
                "enumeration_status": raw_inventory.get("enumeration_status"),
                "analyzer": raw_inventory.get("analyzer"),
                "analyzer_version": raw_inventory.get("analyzer_version"),
                "subjects": coverage_subjects,
                "diagnostics": diagnostic_strings,
                **(
                    {"javascript_esm_descriptor": result["javascript_esm_descriptor"]}
                    if "javascript_esm_descriptor" in result
                    else {}
                ),
            }
            if raw_inventory.get("enumeration_status") != "PASSED":
                inventory_blocker = _module_inventory_blocker_subject(
                    source_language,
                    relative,
                    diagnostic_strings,
                )
                coverage_subjects.append(inventory_blocker)
                coverage_blockers.append(
                    _mapped_subject_blocker(
                        inventory_blocker,
                        "COMPILER_MODULE_ENUMERATION_NOT_PASSED",
                        (
                            f"{relative} compiler-backed module enumeration returned "
                            f"{raw_inventory.get('enumeration_status')}."
                        ),
                    )
                )
            candidate_symbols = [
                native_subject
                for native_subject in coverage_subjects
                if native_subject["candidate"] is True
            ]
            if raw_inventory.get("enumeration_status") == "PASSED":
                compiler_candidate_enumeration = (
                    len(candidate_symbols) <= MAX_CANDIDATES_PER_FILE,
                    None
                    if len(candidate_symbols) <= MAX_CANDIDATES_PER_FILE
                    else "FUNCTION_INVENTORY_LIMIT_EXCEEDED",
                )
            for native_subject in coverage_subjects:
                already_blocked = any(
                    blocker.get("coverage_key") == native_subject["coverage_key"]
                    for blocker in coverage_blockers
                )
                if (
                    native_subject["candidate"] is False
                    and native_subject.get("subject_kind") != "structural-wrapper"
                    and not already_blocked
                ):
                    blocking_reasons = native_subject.get("blocking_reasons", [])
                    blocker_code = (
                        str(blocking_reasons[0])
                        if isinstance(blocking_reasons, list) and blocking_reasons
                        else "NATIVE_MODULE_DECLARATION_CONVERSION_UNCOVERED"
                    )
                    coverage_blockers.append(
                        _mapped_subject_blocker(
                            native_subject,
                            blocker_code,
                            (
                                f"{native_subject['qualified_name']} "
                                f"({native_subject['declaration_kind']}) is outside "
                                "typed-pure-module-v1."
                            ),
                        )
                    )
            for native_subject in candidate_symbols[MAX_CANDIDATES_PER_FILE:]:
                coverage_blockers.append(
                    _mapped_subject_blocker(
                        native_subject,
                        "NATIVE_MODULE_CANDIDATE_LIMIT_EXCEEDED",
                        (
                            f"{native_subject['qualified_name']} exceeds the bounded per-file "
                            f"candidate limit of {MAX_CANDIDATES_PER_FILE}."
                        ),
                    )
                )
            duplicate_names = {
                name
                for name, count in Counter(
                    str(native_subject["name"]) for native_subject in candidate_symbols
                ).items()
                if count > 1
            }
            for native_subject in candidate_symbols:
                if native_subject["name"] in duplicate_names:
                    coverage_blockers.append(
                        _mapped_subject_blocker(
                            native_subject,
                            "NATIVE_DUPLICATE_FUNCTION_NAME_NOT_SELECTABLE",
                            (
                                f"{native_subject['qualified_name']} occurrence "
                                f"{native_subject['occurrence']} cannot be selected unambiguously "
                                "by the named-function analyzer."
                            ),
                        )
                    )
    candidates = [str(subject["name"]) for subject in candidate_symbols[:MAX_CANDIDATES_PER_FILE]]
    result["candidates"] = candidates
    # The functional-conversion denominator must use a compiler-backed
    # declaration inventory whenever one is available.  Native inventories
    # are the authoritative whole-file frontends for non-Python languages;
    # falling back to the proposal-only regex scanner manufactured an UNKNOWN
    # obligation for every otherwise exact native module.
    if compiler_candidate_enumeration is not None:
        _inventory_complete, _inventory_reason = compiler_candidate_enumeration
    else:
        _inventory_names, _inventory_complete, _inventory_reason = _candidate_inventory(
            content, source_language
        )
    result["candidate_enumeration_complete"] = _inventory_complete
    result["candidate_enumeration_reason"] = _inventory_reason
    result["coverage_subject_count"] = len(coverage_subjects)
    result["coverage_blockers"] = coverage_blockers
    if not candidates:
        result.update(
            verdict=Verdict.NO_CANDIDATE_DECLARATION,
            reason="No top-level declaration matched the bounded profile shape.",
        )
        return result

    rejections: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    analyzer_execution_not_run = False

    def _candidate_blocked(subject: Any) -> bool:
        key = str(subject["coverage_key"])
        return bool(subject.get("blocking_reasons")) or any(
            blocker.get("coverage_key") == key for blocker in coverage_blockers
        )

    # One analyzer process for the whole file where the language supports it,
    # instead of one per candidate.  `analyze_many` is required to return, for
    # every name, exactly what `analyze` would have returned for that name --
    # and falls back to per-function invocation whenever it cannot guarantee
    # that -- so the decision loop below is untouched and simply reads its
    # answer out of the map instead of making the call itself.
    #
    # The loop still stops at the first NOT_RUN verdict, so a batch can analyze
    # candidates whose answers are then discarded.  That is a little extra work
    # inside one already-running process and changes no outcome; analyzing
    # lazily to avoid it would mean one process per candidate again, which is
    # the cost this exists to remove.
    analyzed = analyze_many(
        path,
        source_language,
        [name for index, name in enumerate(candidates) if not _candidate_blocked(candidate_symbols[index])],
    )

    for index, name in enumerate(candidates):
        candidate_subject = candidate_symbols[index]
        coverage_key = str(candidate_subject["coverage_key"])
        if _candidate_blocked(candidate_subject):
            continue
        try:
            outcome = analyzed[name]
            if isinstance(outcome, BaseException):
                raise outcome
            ir = outcome
        except (RouteError, OSError, ValueError) as error:
            diagnostic = _reason(error)
            if _analyzer_failure_verdict(error, source_language) == Verdict.NOT_RUN:
                # A trustworthy module decision requires every otherwise
                # analyzable symbol to complete under the same sealed analyzer
                # environment.  Discard earlier READY/semantic conclusions and
                # make the whole analyzable file explicitly replayable.
                eligible.clear()
                rejections.clear()
                for unresolved_subject in candidate_symbols[:MAX_CANDIDATES_PER_FILE]:
                    unresolved_coverage_key = str(unresolved_subject["coverage_key"])
                    if unresolved_subject.get("blocking_reasons") or any(
                        blocker.get("coverage_key") == unresolved_coverage_key
                        for blocker in coverage_blockers
                    ):
                        continue
                    for stale_key in ("semantic_signature", "analyzer", "analyzer_version"):
                        unresolved_subject.pop(stale_key, None)
                    rejections.append(
                        _mapped_subject_blocker(
                            unresolved_subject,
                            "NATIVE_ANALYZER_EXECUTION_NOT_PASSED",
                            (
                                f"{relative} native analysis did not reach a trustworthy "
                                f"conclusion and must be replayed: {diagnostic}"
                            ),
                            verdict=Verdict.NOT_RUN,
                        )
                    )
                analyzer_execution_not_run = True
                break
            candidate_subject["semantic_status"] = "FAILED"
            candidate_subject["diagnostics"] = [diagnostic]
            rejection: dict[str, Any] = {
                "candidate": name,
                "blocker_code": "NATIVE_ANALYZER_REJECTED",
                "reason": diagnostic,
                "coverage_key": coverage_key,
                "source_symbol": candidate_subject,
            }
            rejections.append(rejection)
            continue
        if len(ir.functions) != 1 or ir.diagnostics:
            diagnostics = list(ir.diagnostics) or ["EXACTLY_ONE_FUNCTION_REQUIRED"]
            candidate_subject["semantic_status"] = "FAILED"
            candidate_subject["diagnostics"] = diagnostics
            rejection = {
                "candidate": name,
                "blocker_code": (
                    "NATIVE_ANALYZER_DIAGNOSTICS"
                    if ir.diagnostics
                    else "EXACTLY_ONE_FUNCTION_REQUIRED"
                ),
                "reason": ";".join(diagnostics),
                "coverage_key": coverage_key,
                "source_symbol": candidate_subject,
            }
            rejections.append(rejection)
            continue
        function = ir.functions[0]
        if function.name != name:
            raise RouteError(f"MODULE_INVENTORY_ANALYZER_SYMBOL_MISMATCH:{relative}:{name}")
        candidate_subject["semantic_status"] = "PASSED"
        candidate_subject["diagnostics"] = []
        candidate_subject["semantic_signature"] = function.signature_mapping()
        candidate_subject["analyzer"] = ir.analyzer
        candidate_subject["analyzer_version"] = ir.analyzer_version
        candidate: dict[str, Any] = {
            "function_name": function.name,
            "parameters": [parameter.to_mapping() for parameter in function.parameters],
            "return_type": function.return_type,
            "parameter_count": len(function.parameters),
            "analyzer": ir.analyzer,
            "analyzer_version": ir.analyzer_version,
            "coverage_key": coverage_key,
            "source_symbol": candidate_subject,
        }
        eligible.append(candidate)

    if len(eligible) == 1 and not rejections and not coverage_blockers:
        eligible_function = eligible[0]
        result.update(
            verdict=Verdict.READY,
            **eligible_function,
            rejected_candidates=rejections,
            required_inputs=["behavior_cases_json"],
        )
        return result
    if eligible:
        result.update(
            verdict=Verdict.UNSUPPORTED,
            reason=(
                "MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION"
                if len(eligible) > 1 and not rejections and not coverage_blockers
                else "PARTIAL_SYMBOL_COVERAGE_REQUIRES_EXPLICIT_PARTITION"
            ),
            eligible_candidates=eligible,
            rejected_candidates=rejections,
            coverage_blockers=coverage_blockers,
            required_inputs=["function_partition_manifest", "behavior_cases_json_per_function"],
        )
        return result

    result.update(
        verdict=(
            Verdict.NOT_RUN
            if analyzer_execution_not_run
            or (
                coverage_blockers
                and all(blocker.get("verdict") == Verdict.NOT_RUN for blocker in coverage_blockers)
            )
            else Verdict.UNSUPPORTED
        ),
        reason="No candidate declaration stayed inside the bounded profile.",
        rejected_candidates=rejections,
        coverage_blockers=coverage_blockers,
    )
    return result


def discover_repository(
    plan: dict[str, Any],
    repository_root: Path,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Classify every work unit in a repository route plan."""
    source_language = plan.get("source_language")
    target_language = plan.get("target_language")
    if source_language not in REPOSITORY_SURFACE_LANGUAGES or target_language not in REPOSITORY_SURFACE_LANGUAGES:
        raise RouteError("UNSUPPORTED_LANGUAGE")
    language_lifecycle = repository_language_lifecycle(source_language, target_language)
    if (
        language_lifecycle is None
        or plan.get("language_lifecycle") != language_lifecycle
    ):
        raise RouteError("REPOSITORY_PLAN_LANGUAGE_LIFECYCLE_INVALID")
    if plan.get("kind") != "elmos.repository-route-plan":
        raise RouteError("REPOSITORY_PLAN_KIND_INVALID")
    if plan.get("execution_status") != "NOT_RUN":
        raise RouteError("REPOSITORY_PLAN_ALREADY_CLAIMS_EXECUTION")
    units = plan.get("work_units")
    if not isinstance(units, list) or not units:
        raise RouteError("REPOSITORY_PLAN_WORK_UNITS_REQUIRED")
    if repository_root.is_symlink() or not repository_root.is_dir():
        raise RouteError("REPOSITORY_DIRECTORY_INVALID")
    root = repository_root.resolve(strict=True)

    selected = units if limit is None else units[:limit]
    _preflight_inventory(units, root, source_language, limit=limit)
    react_descriptor: dict[str, Any] | None = None
    react_project_verification: dict[str, Any] | None = None
    react_project_source_paths: list[str] | None = None
    if source_language == "react":
        declared_descriptor = plan.get("react_project_descriptor")
        if not isinstance(declared_descriptor, dict):
            raise RouteError("REACT_PROJECT_DESCRIPTOR_REQUIRED")
        react_descriptor = react_project_descriptor(root)
        if react_descriptor != declared_descriptor or any(
            not isinstance(unit, dict)
            or unit.get("react_project_descriptor") != declared_descriptor
            for unit in units
        ):
            raise RouteError("REACT_PROJECT_DESCRIPTOR_CHANGED")
        react_project_source_paths = [
            str(unit.get("source_path", "")) for unit in selected
        ]
        react_project_verification = verify_react_repository_project(
            root,
            react_project_source_paths,
            react_descriptor,
        )
    file_results = [discover_unit(root, unit, source_language) for unit in selected]
    results: list[dict[str, Any]] = []
    for result in file_results:
        eligible = result.get("eligible_candidates")
        blockers: list[dict[str, Any]] = []
        rejected = result.get("rejected_candidates")
        coverage_blockers = result.get("coverage_blockers")
        if isinstance(rejected, list):
            blockers.extend(item for item in rejected if isinstance(item, dict))
        if isinstance(coverage_blockers, list):
            blockers.extend(item for item in coverage_blockers if isinstance(item, dict))

        if isinstance(eligible, list) and eligible:
            parent_id = str(result.get("id", ""))
            for index, candidate in enumerate(eligible, start=1):
                if not isinstance(candidate, dict):
                    raise RouteError("DISCOVERY_ELIGIBLE_CANDIDATE_INVALID")
                unit_id = parent_id if len(eligible) == 1 else f"{parent_id}-F{index:03d}"
                results.append(
                    {
                        "id": unit_id,
                        "parent_work_unit_id": parent_id,
                        "source_path": result.get("source_path"),
                        "declared_sha256": result.get("declared_sha256"),
                        "observed_sha256": result.get("observed_sha256"),
                        **(
                            {"javascript_esm_descriptor": result["javascript_esm_descriptor"]}
                            if "javascript_esm_descriptor" in result
                            else {}
                        ),
                        "profile": PROFILE,
                        "execution_status": "NOT_RUN",
                        "verdict": Verdict.READY,
                        **candidate,
                        "rejected_candidates": [],
                        "required_inputs": ["behavior_cases_json"],
                    }
                )
            if not blockers:
                continue

        if blockers:
            parent_id = str(result.get("id", ""))
            blocker_start = len(eligible) + 1 if isinstance(eligible, list) else 1
            for index, blocker in enumerate(blockers, start=blocker_start):
                blocker_code = str(blocker.get("blocker_code", "SOURCE_CANDIDATE_CONVERSION_UNCOVERED"))
                blocker_verdict = blocker.get("verdict", Verdict.UNSUPPORTED)
                if blocker_verdict not in {Verdict.UNSUPPORTED, Verdict.NOT_RUN}:
                    raise RouteError("DISCOVERY_BLOCKER_VERDICT_INVALID")
                results.append(
                    {
                        "id": f"{parent_id}-F{index:03d}",
                        "parent_work_unit_id": parent_id,
                        "source_path": result.get("source_path"),
                        "declared_sha256": result.get("declared_sha256"),
                        "observed_sha256": result.get("observed_sha256"),
                        **(
                            {"javascript_esm_descriptor": result["javascript_esm_descriptor"]}
                            if "javascript_esm_descriptor" in result
                            else {}
                        ),
                        "profile": PROFILE,
                        "execution_status": "NOT_RUN",
                        "verdict": blocker_verdict,
                        "reason": str(blocker.get("reason", blocker_code)),
                        "blocker_code": blocker_code,
                        "coverage_key": blocker.get("coverage_key"),
                        "source_symbol": blocker.get("source_symbol"),
                        "required_inputs": (
                            ["restore_analyzer_execution_and_replay"]
                            if blocker_verdict == Verdict.NOT_RUN
                            else ["explicit_symbol_conversion_support"]
                        ),
                    }
                )
            continue
        results.append(result)
    counts: dict[str, int] = {}
    for result in results:
        counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1

    ready = counts.get(Verdict.READY, 0)
    coverage_subject_count = sum(
        int(result.get("coverage_subject_count", 0))
        for result in file_results
        if isinstance(result.get("coverage_subject_count"), int)
    )
    coverage_blocker_count = sum(
        1
        for result in results
        if result.get("verdict") != Verdict.READY and isinstance(result.get("coverage_key"), str)
    )
    candidate_obligation_count = sum(
        1
        for result in results
        if result.get("verdict") != Verdict.READY and isinstance(result.get("blocker_code"), str)
    )
    module_inventories = [
        inventory
        for result in file_results
        if isinstance((inventory := result.get("module_inventory")), dict)
    ]
    module_inventory_status_counts = {status: 0 for status in ("FAILED", "NOT_RUN", "PASSED")}
    for inventory in module_inventories:
        status = inventory.get("enumeration_status")
        if not isinstance(status, str) or status not in module_inventory_status_counts:
            raise RouteError("MODULE_INVENTORY_STATUS_INVALID")
        module_inventory_status_counts[status] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-discovery-report",
        "status": "DISCOVERED",
        "repository_ref": plan.get("repository_ref"),
        "snapshot_sha256": plan.get("snapshot_sha256"),
        "repository_scale": plan.get("repository_scale"),
        "repository_limits": plan.get("repository_limits"),
        "route_id": plan.get("route_id"),
        "source_language": source_language,
        "target_language": target_language,
        "language_lifecycle": language_lifecycle,
        "profile": PROFILE,
        "planned_file_count": len(units),
        "work_unit_count": len(results),
        "discovered_file_count": len(file_results),
        "discovered_count": len(results),
        "verdict_counts": counts,
        "ready_count": ready,
        "coverage_subject_count": coverage_subject_count,
        "coverage_blocker_count": coverage_blocker_count,
        "candidate_obligation_count": candidate_obligation_count,
        "module_inventory_count": len(module_inventories),
        "module_inventory_status_counts": module_inventory_status_counts,
        "module_inventories": module_inventories,
        "react_project_descriptor": react_descriptor,
        "react_project_source_paths": react_project_source_paths,
        "react_project_verification": react_project_verification,
        "results": results,
        # Discovery decides eligibility only. Nothing here has been translated,
        # compiled, or replayed, so every execution status stays NOT_RUN.
        "execution_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Discovery classifies eligibility only; no translation is executed.",
            "A READY verdict still requires an independent behavior-case corpus per unit.",
            "Every compiler-indexed declaration or module effect requires a READY/PASSED unit or an explicit blocker.",
            "Repository-wide success cannot be inferred from per-unit eligibility.",
        ],
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    if output.exists():
        raise RouteError("DISCOVERY_OUTPUT_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


MAX_INVENTORY_CANDIDATES_PER_FILE = 10_000

MAX_REPOSITORY_FUNCTIONAL_OBLIGATIONS = 10_000

class _PythonFunctionInventory(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.names: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast visitor contract
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.names.append(".".join([*self.scope, node.name]))
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast visitor contract
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802 - ast visitor contract
        self._visit_function(node)

def _candidate_inventory(source: bytes, language: Language) -> tuple[list[str], bool, str | None]:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        return [], False, "SOURCE_NOT_UTF8"
    if language == "python":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return [], False, "PYTHON_AST_PARSE_FAILED"
        inventory = _PythonFunctionInventory()
        inventory.visit(tree)
        complete = len(inventory.names) <= MAX_INVENTORY_CANDIDATES_PER_FILE
        return (
            inventory.names[:MAX_INVENTORY_CANDIDATES_PER_FILE],
            complete,
            None if complete else "FUNCTION_INVENTORY_LIMIT_EXCEEDED",
        )
    pattern = _DECLARATION_PATTERNS.get(language)
    if pattern is None:
        return [], False, "FUNCTION_INVENTORY_SCANNER_UNAVAILABLE"
    names: list[str] = []
    for match in pattern.finditer(text):
        name = match.group(1)
        # Constructors and control-flow keywords are never migratable
        # declarations; drop them before paying for a native analysis.
        if name in {"if", "for", "while", "switch", "catch", "return", "new"}:
            continue
        names.append(name)
        if len(names) >= MAX_INVENTORY_CANDIDATES_PER_FILE:
            break
    # These declaration scans only propose compiler work. They are not a
    # complete project feature inventory, so the report keeps an UNKNOWN
    # obligation in its denominator until a compiler inventory is available.
    return names, False, "DECLARATION_SCAN_NOT_COMPILER_COMPLETE"

def _preflight_inventory(
    units: list[dict[str, Any]],
    root: Path,
    source_language: Language,
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    selected = units if limit is None else units[:limit]
    inventory: list[dict[str, Any]] = []
    obligation_lower_bound = 0
    for unit in selected:
        relative = str(unit.get("source_path", ""))
        if (
            not relative
            or relative.startswith("/")
            or "\\" in relative
            or ".." in relative.split("/")
            or any(ord(character) < 32 or ord(character) == 127 for character in relative)
        ):
            raise RouteError(f"WORK_UNIT_PATH_UNSAFE:{relative}")
        candidate = root / relative
        current = root
        for component in Path(relative).parts:
            current /= component
            if current.is_symlink():
                raise RouteError(f"WORK_UNIT_SOURCE_MISSING_OR_UNSAFE:{relative}")
        try:
            source_path = candidate.resolve(strict=True)
            source_path.relative_to(root)
        except (FileNotFoundError, ValueError) as error:
            raise RouteError(f"WORK_UNIT_PATH_ESCAPES_REPOSITORY:{relative}") from error
        if source_path.is_symlink() or not source_path.is_file() or source_path.stat().st_size > MAX_FILE_BYTES:
            raise RouteError(f"WORK_UNIT_SOURCE_MISSING_OR_UNSAFE:{relative}")
        before = source_path.stat(follow_symlinks=False)
        content = source_path.read_bytes()
        after = source_path.stat(follow_symlinks=False)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(content) != before.st_size
        ):
            raise RouteError(f"WORK_UNIT_CONTENT_CHANGED_DURING_READ:{relative}")
        observed = hashlib.sha256(content).hexdigest()
        if unit.get("source_sha256") and unit["source_sha256"] != observed:
            raise RouteError(f"WORK_UNIT_CONTENT_CHANGED:{relative}")
        candidates, complete, reason_code = _candidate_inventory(content, source_language)
        obligation_lower_bound += len(candidates) + (0 if candidates and complete else 1)
        if obligation_lower_bound > MAX_REPOSITORY_FUNCTIONAL_OBLIGATIONS:
            raise RouteError(
                f"FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED:{MAX_REPOSITORY_FUNCTIONAL_OBLIGATIONS + 1}"
            )
        inventory.append(
            {
                "id": unit.get("id"),
                "source_path": relative,
                "declared_sha256": unit.get("source_sha256"),
                "observed_sha256": observed,
                "candidates": candidates,
                "candidate_enumeration_complete": complete,
                "candidate_enumeration_reason": reason_code,
            }
        )
    return inventory

def inventory_repository_incident(
    plan: dict[str, Any],
    repository_root: Path,
    incident_reason: str,
) -> dict[str, Any]:
    """Create a no-execution discovery envelope after a safe inventory.

    This is only for runner/toolchain/analyzer incidents. It never turns a
    candidate into READY and never handles source-path, digest, or TOCTOU
    errors, which remain hard integrity failures.
    """
    source_language = plan.get("source_language")
    target_language = plan.get("target_language")
    units = plan.get("work_units")
    if source_language not in REPOSITORY_SURFACE_LANGUAGES or target_language not in REPOSITORY_SURFACE_LANGUAGES:
        raise RouteError("UNSUPPORTED_LANGUAGE")
    if plan.get("kind") != "elmos.repository-route-plan" or plan.get("execution_status") != "NOT_RUN":
        raise RouteError("REPOSITORY_PLAN_KIND_INVALID")
    if not isinstance(units, list) or not units:
        raise RouteError("REPOSITORY_PLAN_WORK_UNITS_REQUIRED")
    if repository_root.is_symlink() or not repository_root.is_dir():
        raise RouteError("REPOSITORY_DIRECTORY_INVALID")
    root = repository_root.resolve(strict=True)
    inventory = _preflight_inventory(units, root, source_language, limit=None)
    reason = _reason(RouteError(incident_reason))
    reason_code = incident_reason.split(":", 1)[0]
    results: list[dict[str, Any]] = []
    for item in inventory:
        candidates = list(item["candidates"])
        result = {
            **item,
            "profile": PROFILE,
            "execution_status": "NOT_RUN",
            "verdict": Verdict.UNSUPPORTED if candidates else Verdict.NO_CANDIDATE_DECLARATION,
            "reason": reason,
            "rejected_candidates": [
                {"candidate": candidate, "reason": reason_code}
                for candidate in candidates
            ],
        }
        results.append(result)
    counts: dict[str, int] = {}
    for result in results:
        verdict = str(result["verdict"])
        counts[verdict] = counts.get(verdict, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-discovery-report",
        "status": "BLOCKED",
        "repository_ref": plan.get("repository_ref"),
        "snapshot_sha256": plan.get("snapshot_sha256"),
        "route_id": plan.get("route_id"),
        "source_language": source_language,
        "target_language": target_language,
        "profile": PROFILE,
        "work_unit_count": len(units),
        "discovered_count": len(results),
        "verdict_counts": counts,
        "ready_count": 0,
        "results": results,
        "analysis_incident": {"reason_code": reason_code, "reason": reason},
        "execution_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Only declaration inventory completed; native analysis, translation and behavior replay did not run.",
            "No candidate is READY until the exact analyzer/toolchain incident is remediated and replayed.",
        ],
    }
