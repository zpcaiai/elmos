"""Change-impact planning and stable, digest-bound shards."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .canonical import digest_json
from .risk import select_risk_plan
from .validation import load_cases


def changed_paths(root: Path, changed_from: str) -> list[str]:
    result = subprocess.run(["git", "diff", "--name-only", f"{changed_from}...HEAD", "--"], cwd=root, text=True, capture_output=True, check=False)
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()}) if result.returncode == 0 else []


def affected_lines(paths: list[str]) -> set[str]:
    lines: set[str] = set()
    for path in paths:
        value = path.lower()
        if any(token in value for token in ("spring", "struts", "servlet", "java-modern")): lines.add("spring-modernization")
        if any(token in value for token in ("translate", "language", "semantic-ir", "frontend", "native")): lines.add("cross-language")
        if any(token in value for token in ("generator", "scaffold", "requirement", "template")): lines.add("project-generation")
        if any(token in value for token in ("sql", "dialect", "routine", "database")): lines.add("sql-conversion")
        if any(token in value for token in ("sandbox", "harness", "executor", "cache", "billing", "tenant", "checkpoint", "evidence", "oracle", "scheduler", "policy")):
            lines.update({"spring-modernization", "cross-language", "project-generation", "sql-conversion", "cross-cutting"})
    return lines


def stable_shards(
    case_ids: Iterable[str],
    shard_count: int,
    *,
    scope_digest: str = "sha256:" + "0" * 64,
    candidate_digest: str | None = None,
) -> list[dict[str, Any]]:
    """Partition exact case identities into digest-bound, replayable shards."""

    if shard_count < 1:
        raise ValueError("shard_count must be at least 1")
    if not isinstance(scope_digest, str) or not scope_digest.startswith("sha256:") or len(scope_digest) != 71:
        raise ValueError("scope_digest must be sha256:<64 hex>")
    if candidate_digest is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_digest):
        raise ValueError("candidate_digest must be sha256:<64 hex>")
    buckets: list[list[str]] = [[] for _ in range(shard_count)]
    for case_id in sorted(str(value) for value in case_ids):
        routing_key = f"{case_id}|{scope_digest}|{candidate_digest or ''}".encode("utf-8")
        buckets[int(hashlib.sha256(routing_key).hexdigest(), 16) % shard_count].append(case_id)
    shards: list[dict[str, Any]] = []
    for index, values in enumerate(buckets):
        if not values:
            continue
        shard = {
            "schema_version": "1.0",
            "shard_id": index,
            "shard_count": shard_count,
            "case_count": len(values),
            "case_ids": values,
            "scope_digest": scope_digest,
            "candidate_digest": candidate_digest,
        }
        shard["shard_digest"] = "sha256:" + digest_json(shard)
        shards.append(shard)
    return shards


def build_plan(root: Path, changed_from: str | None = None, *, history_path: Path | None = None, max_cases: int = 500, seed: int = 17, shard_count: int = 8, candidate_digest: str | None = None, profile: str | None = None) -> dict[str, Any]:
    paths = changed_paths(root, changed_from) if changed_from else []
    lines = affected_lines(paths)
    fallback = bool(changed_from and not paths)
    if fallback:
        lines = {"spring-modernization", "cross-language", "project-generation", "sql-conversion", "cross-cutting"}
    historical = []
    if history_path and history_path.exists():
        historical = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    all_cases = load_cases(root)
    if profile in {"release", "golden"}:
        if candidate_digest is None or not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_digest):
            raise ValueError("complete release/golden plans require a frozen candidate digest")
        case_ids = sorted(str(case["id"]) for case in all_cases if profile in case.get("profiles", []))
        selected_case_ids = set(case_ids)
        risk = {
            "schema_version": "1.1",
            "selection_policy": f"complete-{profile}-scope-v1",
            "seed": seed,
            "affected_business_lines": sorted({str(case.get("business_line")) for case in all_cases if str(case["id"]) in selected_case_ids}),
            "case_ids": case_ids,
            "selections": [],
        }
    else:
        risk = select_risk_plan(all_cases, affected_lines=lines, historical_results=historical, max_cases=max_cases, seed=seed)
    plan = {**risk, "profile": profile, "changed_from": changed_from, "changed_paths": paths, "diff_fallback_all_lines": fallback, "candidate_digest": candidate_digest}
    plan.pop("plan_digest", None)
    plan["scope_digest"] = "sha256:" + digest_json(plan)
    plan["shards"] = stable_shards(plan["case_ids"], shard_count, scope_digest=plan["scope_digest"], candidate_digest=candidate_digest)
    plan["plan_digest"] = "sha256:" + digest_json(plan)
    return plan


def validate_plan(plan: Any) -> list[str]:
    """Validate full plan integrity, shard coverage, and candidate binding."""

    if not isinstance(plan, dict):
        return ["plan must be an object"]
    errors: list[str] = []
    case_ids = plan.get("case_ids")
    shards = plan.get("shards")
    if not isinstance(case_ids, list) or any(not isinstance(value, str) or not value for value in case_ids):
        errors.append("plan case_ids must be a string array")
        case_ids = []
    if len(case_ids) != len(set(case_ids)):
        errors.append("plan case_ids contain duplicates")
    if plan.get("profile") in {"release", "golden"} and (not isinstance(plan.get("candidate_digest"), str) or re.fullmatch(r"sha256:[0-9a-f]{64}", plan["candidate_digest"]) is None):
        errors.append("release/golden plan candidate_digest is missing or invalid")
    expected_scope = {key: value for key, value in plan.items() if key not in {"scope_digest", "shards", "plan_digest"}}
    expected_scope_digest = "sha256:" + digest_json(expected_scope)
    if plan.get("scope_digest") != expected_scope_digest:
        errors.append("plan scope_digest mismatch")
    expected_plan = {key: value for key, value in plan.items() if key != "plan_digest"}
    if plan.get("plan_digest") != "sha256:" + digest_json(expected_plan):
        errors.append("plan plan_digest mismatch")
    if not isinstance(shards, list) or not shards:
        errors.append("plan requires non-empty shards")
        return errors
    observed: list[str] = []
    shard_ids: set[int] = set()
    declared_counts: set[int] = set()
    for shard in shards:
        if not isinstance(shard, dict):
            errors.append("plan shard must be an object")
            continue
        unsigned = {key: value for key, value in shard.items() if key != "shard_digest"}
        if shard.get("shard_digest") != "sha256:" + digest_json(unsigned):
            errors.append(f"shard digest mismatch: {shard.get('shard_id')}")
        shard_id = shard.get("shard_id")
        shard_count = shard.get("shard_count")
        values = shard.get("case_ids")
        if not isinstance(shard_id, int) or isinstance(shard_id, bool) or shard_id < 0 or shard_id in shard_ids:
            errors.append(f"invalid or duplicate shard_id: {shard_id}")
        else:
            shard_ids.add(shard_id)
        if isinstance(shard_count, int) and not isinstance(shard_count, bool):
            declared_counts.add(shard_count)
        else:
            errors.append(f"invalid shard_count: {shard_count}")
        if shard.get("scope_digest") != plan.get("scope_digest") or shard.get("candidate_digest") != plan.get("candidate_digest"):
            errors.append(f"shard binding mismatch: {shard_id}")
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            errors.append(f"invalid shard case_ids: {shard_id}")
            continue
        if shard.get("case_count") != len(values):
            errors.append(f"shard case_count mismatch: {shard_id}")
        observed.extend(values)
    if len(declared_counts) != 1 or (declared_counts and any(shard_id >= next(iter(declared_counts)) for shard_id in shard_ids)):
        errors.append("shard_count declarations are inconsistent")
    if sorted(observed) != sorted(case_ids):
        errors.append("shards do not form an exact, duplicate-free case partition")
    return errors


def select_plan_shard(plan: Any, shard_id: int) -> set[str]:
    errors = validate_plan(plan)
    if errors:
        raise ValueError("invalid plan: " + "; ".join(errors))
    matches = [shard for shard in plan["shards"] if shard["shard_id"] == shard_id]
    if len(matches) != 1:
        raise ValueError(f"plan does not contain shard_id {shard_id}")
    return set(matches[0]["case_ids"])
