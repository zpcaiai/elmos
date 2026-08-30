"""Governed ecosystem and learning primitives; promotion is never automatic."""

from __future__ import annotations

import math
import statistics
import uuid
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .errors import ContractError
from .models import digest, relative_path, require_mapping, require_string, utc_now
from .security import redact


def _status(value: Any) -> str:
    return str(value).upper()


def package_registry(manifest: Mapping[str, Any], components: Any, lock: Any, signature: Any, tests: Any) -> dict[str, Any]:
    name = require_string(manifest.get("name"), "package_manifest.name")
    version = require_string(manifest.get("version"), "package_manifest.version")
    raw_components = components if isinstance(components, list) else []
    catalog = []
    paths: set[str] = set()
    for item in raw_components:
        row = require_mapping(item, "components[]")
        path = relative_path(row.get("path"), "components[].path")
        if path in paths:
            raise ContractError("PACKAGE_INVALID", f"duplicate component path: {path}")
        paths.add(path)
        permissions = row.get("permissions", {})
        if not isinstance(permissions, Mapping):
            raise ContractError("PACKAGE_INVALID", "component permissions must be an object")
        wildcard = any("*" in str(value) for value in permissions.values())
        catalog.append({"id": require_string(row.get("id"), "components[].id"), "path": path, "digest": row.get("digest"), "permissions": dict(permissions), "wildcard_permission": wildcard})
    dependency_lock = require_mapping(lock or {}, "dependency_lock") if lock is not None else {}
    signature_valid = isinstance(signature, Mapping) and bool(signature.get("valid")) and bool(signature.get("key_id"))
    test_rows = tests if isinstance(tests, list) else []
    tests_pass = bool(test_rows) and all(_status(item.get("status")) in {"PASS", "PASSED"} for item in test_rows if isinstance(item, Mapping))
    permission_pass = not any(item["wildcard_permission"] for item in catalog)
    state = "REGISTERED" if signature_valid and tests_pass and permission_pass else "BLOCKED"
    package = {"package_id": f"{name}@{version}", "name": name, "version": version, "content_hash": digest({"manifest": manifest, "components": catalog, "lock": dependency_lock}), "state": state, "immutable": True, "registered_at": utc_now()}
    return {"registered_package": package, "component_catalog": catalog, "install_plan": {"status": "READY" if state == "REGISTERED" else "NOT_READY", "order": [item["id"] for item in catalog]}, "permission_review": {"status": "PASS" if permission_pass else "FAIL", "wildcards": [item["id"] for item in catalog if item["wildcard_permission"]]}, "upgrade_plan": {"status": "PLANNED", "rollback_version": manifest.get("previous_version"), "dependency_lock_hash": digest(dependency_lock)}}


def demonstration(demo: Mapping[str, Any], artifacts: Any, annotations: Any, privacy: Mapping[str, Any]) -> dict[str, Any]:
    if _status(demo.get("status")) not in {"VALIDATED", "PASS", "PASSED"}:
        raise ContractError("DEMONSTRATION_UNSTABLE", "only a validated demonstration can produce a Skill draft")
    private_markers = privacy.get("private_markers", ["tenant", "customer", "internal", "credential"]) if isinstance(privacy, Mapping) else []
    raw_steps = demo.get("steps", [])
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ContractError("DEMONSTRATION_UNSTABLE", "demonstration must contain steps")
    redacted_steps = []
    for step in raw_steps:
        value = redact(step)
        if any(marker.casefold() in str(value).casefold() for marker in private_markers):
            value = {"redacted": True, "reason": "privacy policy marker"}
        redacted_steps.append(value)
    draft = {"id": "skill-draft:" + str(uuid.uuid4()), "name": demo.get("name", "derived-skill"), "version": "0.1.0", "trigger": demo.get("trigger", "explicit capability match"), "steps": redacted_steps, "status": "DRAFT", "source_demo_hash": digest(demo)}
    return {"skill_draft": draft, "trigger_examples": {"positive": list(demo.get("positive_triggers", [])), "negative": list(demo.get("negative_triggers", []))}, "reusable_scripts": [redact(item) for item in artifacts if isinstance(item, Mapping) and item.get("kind") == "script"] if isinstance(artifacts, list) else [], "references": [redact(item) for item in annotations] if isinstance(annotations, list) else [], "regression_fixtures": {"positive": [digest(item) for item in demo.get("positive_cases", [])], "negative": [digest(item) for item in demo.get("negative_cases", [])]}}


def improvement(incidents: Any, corrections: Any, findings: Any, telemetry: Any, benchmarks: Any) -> dict[str, Any]:
    rows = [item for item in (incidents if isinstance(incidents, list) else []) if isinstance(item, Mapping)]
    all_rows = rows + [item for item in (corrections if isinstance(corrections, list) else []) if isinstance(item, Mapping)] + [item for item in (findings if isinstance(findings, list) else []) if isinstance(item, Mapping)]
    clusters: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in all_rows:
        key = str(row.get("code", row.get("category", "unclassified"))).casefold()
        clusters[key].append(row)
    cluster_rows = [{"cluster_id": key, "count": len(values), "sample_hashes": [digest(item) for item in values[:5]], "severity": max((str(item.get("severity", "P2")) for item in values), default="P2")} for key, values in sorted(clusters.items())]
    best = [item for item in (benchmarks if isinstance(benchmarks, list) else []) if isinstance(item, Mapping) and _status(item.get("status")) in {"PASS", "PASSED"}]
    return {"improvement_candidate": {"id": "improvement:" + str(uuid.uuid4()), "status": "PROPOSED", "clusters": [row["cluster_id"] for row in cluster_rows], "requires_curator": True, "before_after_evidence": bool(best)}, "failure_cluster": cluster_rows, "reproducer": {"status": "STABLE" if cluster_rows and all(item["count"] >= 1 for item in cluster_rows) else "NOT_RUN", "fixtures": [digest(item) for item in all_rows[:20]]}, "regression_test": {"status": "PROPOSED", "cases": [digest(item) for item in all_rows]}, "curation_decision": {"decision": "PENDING", "production_promotion": False, "reason": "automatic improvement cannot enter production"}}


def arena(task_set: Any, candidates: Any, environments: Any, budgets: Any, protocol: Mapping[str, Any]) -> dict[str, Any]:
    tasks = [item for item in (task_set if isinstance(task_set, list) else []) if isinstance(item, Mapping)]
    agents = [item for item in (candidates if isinstance(candidates, list) else []) if isinstance(item, Mapping)]
    if len(agents) < 2 or not tasks:
        raise ContractError("INSUFFICIENT_RUNS", "arena needs at least two candidates and one task")
    runs = []
    for task in tasks:
        for agent in agents:
            score = float(agent.get("quality", task.get("quality", 0)))
            runs.append({"run_id": str(uuid.uuid4()), "candidate_id": require_string(agent.get("id"), "agent_candidates[].id"), "task_id": str(task.get("id", digest(task))), "environment_hash": digest(environments), "budget_hash": digest(budgets), "score": score, "status": "PASS" if score >= float(protocol.get("pass_score", .5)) else "FAIL"})
    grouped: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        grouped[run["candidate_id"]].append(run["score"])
    means = {key: statistics.fmean(value) for key, value in grouped.items()}
    ordered = sorted(means, key=lambda key: (-means[key], key))
    pairs = [{"winner": ordered[index], "loser": ordered[index + 1], "margin": means[ordered[index]] - means[ordered[index + 1]]} for index in range(len(ordered) - 1)]
    return {"arena_runs": runs, "pairwise_results": pairs, "quality_cost_frontier": [{"candidate_id": key, "quality": means[key], "cost": next((float(item.get("cost", 0)) for item in agents if item.get("id") == key), 0)} for key in ordered], "failure_analysis": {"failed_runs": [run for run in runs if run["status"] == "FAIL"]}, "promotion_candidate": {"candidate_id": ordered[0], "status": "CANDIDATE", "requires_independent_review": True}}


def elo(arena_results: Any, production: Any, taxonomy: Any, costs: Any) -> dict[str, Any]:
    rows = [item for item in (arena_results if isinstance(arena_results, list) else []) if isinstance(item, Mapping)]
    scores: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        candidate = str(row.get("candidate_id", "unknown"))
        segment = str(row.get("task_segment", "default"))
        scores[(candidate, segment)].append(1.0 if _status(row.get("status")) in {"PASS", "PASSED"} else 0.0)
    ratings = []
    for (candidate, segment), values in sorted(scores.items()):
        win_rate = statistics.fmean(values)
        rating = 1000 + (win_rate - .5) * 400
        uncertainty = 200 / math.sqrt(len(values))
        ratings.append({"candidate_id": candidate, "task_segment": segment, "rating": round(rating, 4), "uncertainty": round(uncertainty, 4), "sample_count": len(values)})
    return {"elo_ratings": ratings, "confidence_intervals": [{"candidate_id": item["candidate_id"], "low": item["rating"] - 1.96 * item["uncertainty"], "high": item["rating"] + 1.96 * item["uncertainty"]} for item in ratings], "segment_ratings": {item["task_segment"]: [value for value in ratings if value["task_segment"] == item["task_segment"]] for item in ratings}, "routing_recommendations": [{"task_segment": item["task_segment"], "candidate_id": item["candidate_id"], "requires_fresh_eval": item["sample_count"] < 20} for item in ratings], "drift_alerts": [] if not production else [{"status": "REQUIRES_CALIBRATION", "reason": "production evaluation is advisory until independently verified"}]}


def gym(repositories: Any, specs: Any, images: Any, contracts: Any, chaos: Any) -> dict[str, Any]:
    repos = [item for item in (repositories if isinstance(repositories, list) else []) if isinstance(item, Mapping)]
    tasks = [item for item in (specs if isinstance(specs, list) else []) if isinstance(item, Mapping)]
    runs = []
    for repo in repos:
        for task in tasks:
            runs.append({"run_id": str(uuid.uuid4()), "repository_id": repo.get("id", digest(repo)), "task_id": task.get("id", digest(task)), "fixed_image_hash": digest(images), "expected_contract_hash": digest(contracts), "status": "NOT_RUN", "external_execution": False})
    return {"gym_runs": runs, "golden_artifacts": [], "scorecards": [{"repository_id": repo.get("id", digest(repo)), "status": "NOT_RUN", "reason": "native runner not supplied"} for repo in repos], "regression_trends": {"status": "NOT_RUN", "samples": len(runs)}, "commercial_readiness": {"status": "NOT_CERTIFIED", "required": ["repeatability", "chaos", "customer_acceptance", "P05_DEPLOYMENT_COMPLETE"], "chaos_scenarios": len(chaos) if isinstance(chaos, list) else 0}}
