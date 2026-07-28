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
        except SyntaxError:
            return []
        return [
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
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


def discover_unit(
    repository_root: Path,
    unit: dict[str, Any],
    source_language: Language,
) -> dict[str, Any]:
    """Classify one work unit against the bounded profile."""
    relative = str(unit.get("source_path", ""))
    if not relative or relative.startswith("/") or ".." in relative.split("/"):
        raise RouteError(f"WORK_UNIT_PATH_UNSAFE:{relative}")
    path = (repository_root / relative).resolve()
    if not str(path).startswith(str(repository_root.resolve())):
        raise RouteError(f"WORK_UNIT_PATH_ESCAPES_REPOSITORY:{relative}")

    result: dict[str, Any] = {
        "id": unit.get("id"),
        "source_path": relative,
        "declared_sha256": unit.get("source_sha256"),
        "profile": PROFILE,
        "execution_status": "NOT_RUN",
    }

    if path.is_symlink() or not path.is_file():
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

    candidates = propose_candidates(content, source_language)
    result["candidates"] = candidates
    if not candidates:
        result.update(
            verdict=Verdict.NO_CANDIDATE_DECLARATION,
            reason="No top-level declaration matched the bounded profile shape.",
        )
        return result

    rejections: list[dict[str, str]] = []
    eligible: list[dict[str, Any]] = []
    for name in candidates:
        try:
            ir = analyze(path, source_language, name)
        except (RouteError, OSError, ValueError) as error:
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
