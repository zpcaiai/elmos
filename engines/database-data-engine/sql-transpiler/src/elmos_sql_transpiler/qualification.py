from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import TranspileRequest
from .profiles import exact_profiles
from .transpiler import transpile

_REQUIRED_CORPUS_KINDS = frozenset({"development", "negative", "holdout", "representative"})


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("corpus must be a JSON object")
    return value


def run_qualification(paths: Iterable[Path]) -> dict[str, Any]:
    corpora = [_load(path) for path in paths]
    kinds = {str(corpus.get("kind")) for corpus in corpora}
    missing = _REQUIRED_CORPUS_KINDS - kinds
    if missing:
        raise ValueError(f"required corpus kinds are missing: {sorted(missing)}")

    profile_ids = tuple(profile.id for profile in exact_profiles())
    eligible = 0
    syntax_ready = 0
    negative_total = 0
    negative_blocked = 0
    failures: list[dict[str, Any]] = []
    case_results: list[dict[str, Any]] = []
    route_corpus_kinds: dict[str, set[str]] = {}
    route_positive_counts: dict[str, int] = {}
    route_ready_counts: dict[str, int] = {}

    for corpus in corpora:
        kind = str(corpus["kind"])
        cases = corpus.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError(f"{kind} corpus must contain cases")
        for case in cases:
            source_profile = str(case["sourceProfile"])
            targets = case.get("targets", ["*"])
            selected_targets = (
                [item for item in profile_ids if item != source_profile]
                if targets == ["*"]
                else [str(item) for item in targets]
            )
            for target_profile in selected_targets:
                request = TranspileRequest(
                    query_id=str(case["id"]),
                    source_profile=source_profile,
                    target_profile=target_profile,
                    sql=str(case["sql"]),
                )
                result = transpile(request)
                expected = str(case.get("expected", "SYNTAX_READY"))
                if kind == "negative":
                    negative_total += 1
                    if result.state == "BLOCKED":
                        negative_blocked += 1
                    else:
                        failures.append(
                            {
                                "caseId": case["id"],
                                "targetProfile": target_profile,
                                "reason": "negative case did not fail closed",
                            }
                        )
                else:
                    eligible += 1
                    route_id = f"{source_profile}--to--{target_profile}"
                    route_corpus_kinds.setdefault(route_id, set()).add(kind)
                    route_positive_counts[route_id] = route_positive_counts.get(route_id, 0) + 1
                    if result.state == "SYNTAX_READY":
                        syntax_ready += 1
                        route_ready_counts[route_id] = route_ready_counts.get(route_id, 0) + 1
                    else:
                        failures.append(
                            {
                                "caseId": case["id"],
                                "targetProfile": target_profile,
                                "reason": result.diagnostics[0].code,
                            }
                        )
                if result.state != expected:
                    failures.append(
                        {
                            "caseId": case["id"],
                            "targetProfile": target_profile,
                            "reason": f"expected {expected}, received {result.state}",
                        }
                    )
                case_results.append(
                    {
                        "corpus": kind,
                        "caseId": case["id"],
                        "sourceProfile": source_profile,
                        "targetProfile": target_profile,
                        "state": result.state,
                        "sourceExecution": "NOT_RUN",
                        "targetExecution": "NOT_RUN",
                        "resultEquivalence": "NOT_RUN",
                    }
                )

    syntax_rate = syntax_ready / eligible if eligible else 0.0
    negative_rate = negative_blocked / negative_total if negative_total else 0.0
    syntax_goal_met = syntax_rate >= 0.995
    negative_gate_met = negative_rate == 1.0
    expected_routes = {
        f"{source}--to--{target}"
        for source in profile_ids
        for target in profile_ids
        if source != target
    }
    required_positive_kinds = {"development", "holdout", "representative"}
    route_coverage_failures = []
    for route_id in sorted(expected_routes):
        missing_kinds = required_positive_kinds - route_corpus_kinds.get(route_id, set())
        total = route_positive_counts.get(route_id, 0)
        ready = route_ready_counts.get(route_id, 0)
        rate = ready / total if total else 0.0
        if missing_kinds or total < 5 or rate < 0.995:
            route_coverage_failures.append(
                {
                    "routeId": route_id,
                    "missingCorpusKinds": sorted(missing_kinds),
                    "positiveCases": total,
                    "syntaxSuccessRate": rate,
                }
            )
    route_coverage_met = not route_coverage_failures
    failures.extend(
        {
            "caseId": None,
            "targetProfile": None,
            "reason": f"route coverage failed: {item['routeId']}",
        }
        for item in route_coverage_failures
    )
    return {
        "schemaVersion": "1.0",
        "syntax": {
            "eligible": eligible,
            "ready": syntax_ready,
            "successRate": syntax_rate,
            "goal": 0.995,
            "goalMet": syntax_goal_met,
        },
        "negative": {
            "total": negative_total,
            "blocked": negative_blocked,
            "failClosedRate": negative_rate,
            "required": 1.0,
            "gateMet": negative_gate_met,
        },
        "corpusKinds": sorted(kinds),
        "routeCount": len(profile_ids) * (len(profile_ids) - 1),
        "routeCoverage": {
            "covered": len(expected_routes) - len(route_coverage_failures),
            "required": len(expected_routes),
            "minimumPositiveCasesPerRoute": 5,
            "requiredCorpusKinds": sorted(required_positive_kinds),
            "gateMet": route_coverage_met,
            "failures": route_coverage_failures,
        },
        "failures": failures,
        "caseResults": case_results,
        "localDecision": (
            "READY_FOR_ENGINE_EXECUTION"
            if syntax_goal_met and negative_gate_met and route_coverage_met and not failures
            else "BLOCKED"
        ),
        "sourceExecution": "NOT_RUN",
        "targetExecution": "NOT_RUN",
        "resultEquivalence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
