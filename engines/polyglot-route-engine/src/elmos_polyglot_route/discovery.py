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

from .models import SUPPORTED_LANGUAGES, Language, RouteError
from .native import analyze, inventory_module
from .project_graph import (
    PythonCoverageSubject,
    SourceLocation,
    python_coverage_subjects,
    semantic_coverage_key,
    verified_java_structural_wrapper,
)

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
    "go": re.compile(
        r"^\s*func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
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
}


class Verdict:
    READY = "READY"
    UNSUPPORTED = "UNSUPPORTED"
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
) -> dict[str, Any]:
    subject["semantic_status"] = "BLOCKED"
    subject["diagnostics"] = [code]
    return {
        "candidate": subject.get("name"),
        "blocker_code": code,
        "reason": reason,
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

    coverage_subjects: list[dict[str, Any]] = []
    candidate_symbols: list[dict[str, Any]] = []
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
            inventory_blocker = _module_inventory_blocker_subject(
                source_language,
                relative,
                [diagnostic],
            )
            coverage_subjects = [inventory_blocker]
            coverage_blockers.append(
                _mapped_subject_blocker(
                    inventory_blocker,
                    "COMPILER_MODULE_ENUMERATION_NOT_PASSED",
                    f"{relative} compiler-backed module enumeration did not run: {diagnostic}",
                )
            )
            result["module_inventory"] = {
                "path": relative,
                "language": source_language,
                "source_sha256": observed,
                "profile": "typed-pure-module-v1",
                "enumeration_status": "NOT_RUN",
                "analyzer": None,
                "analyzer_version": None,
                "subjects": coverage_subjects,
                "diagnostics": [diagnostic],
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
            result["module_inventory"] = {
                "path": relative,
                "language": source_language,
                "source_sha256": observed,
                "profile": "typed-pure-module-v1",
                "enumeration_status": raw_inventory.get("enumeration_status"),
                "analyzer": raw_inventory.get("analyzer"),
                "analyzer_version": raw_inventory.get("analyzer_version"),
                "subjects": coverage_subjects,
                "diagnostics": raw_inventory.get("diagnostics", []),
            }
            if raw_inventory.get("enumeration_status") != "PASSED":
                raw_diagnostics = raw_inventory.get("diagnostics", [])
                diagnostic_strings = [str(item) for item in raw_diagnostics]
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
    for index, name in enumerate(candidates):
        candidate_subject = candidate_symbols[index]
        coverage_key = str(candidate_subject["coverage_key"])
        if candidate_subject.get("blocking_reasons") or any(
            blocker.get("coverage_key") == coverage_key for blocker in coverage_blockers
        ):
            continue
        try:
            ir = analyze(path, source_language, name)
        except (RouteError, OSError, ValueError) as error:
            candidate_subject["semantic_status"] = "FAILED"
            candidate_subject["diagnostics"] = [_reason(error)]
            rejection: dict[str, Any] = {
                "candidate": name,
                "blocker_code": "NATIVE_ANALYZER_REJECTED",
                "reason": _reason(error),
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
        verdict=Verdict.UNSUPPORTED,
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
    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_LANGUAGE")
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
                results.append(
                    {
                        "id": f"{parent_id}-F{index:03d}",
                        "parent_work_unit_id": parent_id,
                        "source_path": result.get("source_path"),
                        "declared_sha256": result.get("declared_sha256"),
                        "observed_sha256": result.get("observed_sha256"),
                        "profile": PROFILE,
                        "execution_status": "NOT_RUN",
                        "verdict": Verdict.UNSUPPORTED,
                        "reason": str(blocker.get("reason", blocker_code)),
                        "blocker_code": blocker_code,
                        "coverage_key": blocker.get("coverage_key"),
                        "source_symbol": blocker.get("source_symbol"),
                        "required_inputs": ["explicit_symbol_conversion_support"],
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
