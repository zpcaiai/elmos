"""Turn repository work units into concrete, evidence-bearing verdicts.

The inventory step can only say a source file exists. Discovery answers the
question that actually determines whether a repository can be migrated: for
each file, is there a declaration the bounded route profile can lower, and if
not, exactly which construct blocks it?

The split of responsibility here is deliberate. Candidate *names* are proposed
cheaply -- by CPython's AST for Python and by a bounded declaration scan for the
other three languages -- but a candidate is never accepted on that basis. The
verdict always comes from the same compiler-backed analyzer the migration
itself uses, so a proposal the scanner misses degrades to
``NO_CANDIDATE_DECLARATION`` and never to a false ``READY``.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .models import SUPPORTED_LANGUAGES, Language, RouteError
from .native import analyze

SCHEMA_VERSION = "1.0.0"
PROFILE = "typed-pure-function-v1"
MAX_CANDIDATES_PER_FILE = 40
MAX_INVENTORY_CANDIDATES_PER_FILE = 10_000
MAX_REPOSITORY_FUNCTIONAL_OBLIGATIONS = 10_000
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
        r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+|async\s+|unsafe\s+|extern\s+)*fn\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "cpp": re.compile(
        r"^\s*(?:(?:inline|static|constexpr)\s+)*(?:std::)?"
        r"(?:int64_t|int32_t|int|long|double|float|bool|string)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "objc": re.compile(
        r"^\s*(?:(?:static|inline)\s+)*(?:long\s+long|long|int|double|float|BOOL|NSString\s*\*)\s*"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "swift": re.compile(
        r"^\s*(?:(?:public|internal|private|fileprivate|open|static|class)\s+)*func\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
}


class Verdict:
    READY = "READY"
    UNSUPPORTED = "UNSUPPORTED"
    NO_CANDIDATE_DECLARATION = "NO_CANDIDATE_DECLARATION"
    UNREADABLE = "UNREADABLE"


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


def propose_candidates(source: bytes, language: Language) -> list[str]:
    """Return the bounded inventory used to propose native analysis work."""
    return _candidate_inventory(source, language)[0]


def _reason(error: Exception) -> str:
    detail = str(error).strip()
    if not detail:
        return type(error).__name__
    return detail[:300]


def _reportable_analysis_failure(error: RouteError) -> bool:
    """Separate bounded semantic rejection from runner/toolchain failure."""
    reason = str(error)
    return not reason.startswith(
        (
            "EXACT_TOOLCHAIN_",
            "NATIVE_ANALYZER_FAILED",
            "NATIVE_ANALYZER_CONTRACT_INVALID",
            "NATIVE_ANALYZER_INVALID_JSON",
            "NATIVE_ANALYZER_OBJECT_REQUIRED",
            "NATIVE_ANALYZER_TIMEOUT",
            "SOURCE_FILE_UNSAFE_OR_TOO_LARGE",
            "SWIFT_ANALYZER_BUILD_FAILED",
            "SWIFT_ANALYZER_BUILD_TIMEOUT",
            "TYPESCRIPT_ANALYZER_BUILD_FAILED",
            "TYPESCRIPT_ANALYZER_BUILD_TIMEOUT",
        )
    )


def discover_unit(
    repository_root: Path,
    unit: dict[str, Any],
    source_language: Language,
) -> dict[str, Any]:
    """Classify one work unit against the bounded profile."""
    relative = str(unit.get("source_path", ""))
    if not relative or relative.startswith("/") or ".." in relative.split("/"):
        raise RouteError(f"WORK_UNIT_PATH_UNSAFE:{relative}")
    root = repository_root.resolve(strict=True)
    candidate = root / relative
    result: dict[str, Any] = {
        "id": unit.get("id"),
        "source_path": relative,
        "declared_sha256": unit.get("source_sha256"),
        "profile": PROFILE,
        "execution_status": "NOT_RUN",
    }
    current = root
    for component in Path(relative).parts:
        current /= component
        if current.is_symlink():
            result.update(verdict=Verdict.UNREADABLE, reason="SOURCE_FILE_MISSING_OR_SYMLINK", candidates=[])
            return result
    try:
        path = candidate.resolve(strict=True)
    except FileNotFoundError:
        result.update(verdict=Verdict.UNREADABLE, reason="SOURCE_FILE_MISSING_OR_SYMLINK", candidates=[])
        return result
    try:
        path.relative_to(root)
    except ValueError as error:
        raise RouteError(f"WORK_UNIT_PATH_ESCAPES_REPOSITORY:{relative}") from error

    if not path.is_file():
        result.update(verdict=Verdict.UNREADABLE, reason="SOURCE_FILE_MISSING_OR_SYMLINK", candidates=[])
        return result
    if path.stat().st_size > MAX_FILE_BYTES:
        result.update(verdict=Verdict.UNREADABLE, reason="SOURCE_FILE_TOO_LARGE", candidates=[])
        return result

    content = path.read_bytes()
    observed = hashlib.sha256(content).hexdigest()
    result["observed_sha256"] = observed
    if unit.get("source_sha256") and unit["source_sha256"] != observed:
        # The plan is content addressed. A changed file invalidates the whole
        # decomposition rather than being silently re-discovered.
        raise RouteError(f"WORK_UNIT_CONTENT_CHANGED:{relative}")

    candidates, enumeration_complete, enumeration_reason = _candidate_inventory(content, source_language)
    result["candidates"] = candidates
    result["candidate_enumeration_complete"] = enumeration_complete
    result["candidate_enumeration_reason"] = enumeration_reason
    if not candidates:
        result.update(
            verdict=Verdict.NO_CANDIDATE_DECLARATION,
            reason=enumeration_reason or "No function declaration matched the bounded profile shape.",
        )
        return result

    rejections: list[dict[str, str]] = []
    eligible: list[dict[str, Any]] = []
    for index, name in enumerate(candidates):
        if index >= MAX_CANDIDATES_PER_FILE:
            rejections.append({"candidate": name, "reason": "CANDIDATE_ANALYSIS_LIMIT_EXCEEDED"})
            continue
        if source_language == "python" and "." in name:
            rejections.append({"candidate": name, "reason": "PYTHON_NON_TOP_LEVEL_FUNCTION_OUTSIDE_PROFILE"})
            continue
        try:
            ir = analyze(path, source_language, name)
        except RouteError as error:
            if not _reportable_analysis_failure(error):
                raise
            rejections.append({"candidate": name, "reason": _reason(error)})
            continue
        if len(ir.functions) != 1:
            rejections.append({"candidate": name, "reason": "EXACTLY_ONE_FUNCTION_REQUIRED"})
            continue
        function = ir.functions[0]
        eligible.append(
            {
                "function_name": function.name,
                "parameters": [parameter.to_mapping() for parameter in function.parameters],
                "return_type": function.return_type,
                "parameter_count": len(function.parameters),
                "analyzer": ir.analyzer,
                "analyzer_version": ir.analyzer_version,
            }
        )

    if len(eligible) == 1:
        eligible_function = eligible[0]
        result.update(
            verdict=Verdict.READY,
            **eligible_function,
            rejected_candidates=rejections,
            required_inputs=["behavior_cases_json"],
        )
        return result
    if len(eligible) > 1:
        result.update(
            verdict=Verdict.UNSUPPORTED,
            reason="MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION",
            eligible_candidates=eligible,
            rejected_candidates=rejections,
            required_inputs=[
                "function_partition_manifest",
                "behavior_cases_json_per_function",
            ],
        )
        return result

    result.update(
        verdict=Verdict.UNSUPPORTED,
        reason="No candidate declaration stayed inside the bounded profile.",
        rejected_candidates=rejections,
    )
    return result


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
    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
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

    # Capacity is checked from the declaration inventory before the native
    # analyzer loop. A single repository conversion is deliberately bounded;
    # larger estates must be split into separately content-addressed campaigns.
    selected = units if limit is None else units[:limit]
    _preflight_inventory(units, root, source_language, limit=limit)
    results = [discover_unit(root, unit, source_language) for unit in selected]
    counts: dict[str, int] = {}
    for result in results:
        counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1

    ready = counts.get(Verdict.READY, 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-discovery-report",
        "status": "DISCOVERED",
        "repository_ref": plan.get("repository_ref"),
        "snapshot_sha256": plan.get("snapshot_sha256"),
        "route_id": plan.get("route_id"),
        "source_language": source_language,
        "target_language": target_language,
        "profile": PROFILE,
        "work_unit_count": len(units),
        "discovered_count": len(results),
        "verdict_counts": counts,
        "ready_count": ready,
        "results": results,
        # Discovery decides eligibility only. Nothing here has been translated,
        # compiled, or replayed, so every execution status stays NOT_RUN.
        "execution_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Discovery classifies eligibility only; no translation is executed.",
            "A READY verdict still requires an independent behavior-case corpus per unit.",
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
