#!/usr/bin/env python3
"""Bounded, deterministic domain execution for Precision Migration Skills.

The engine executes structured algorithms selected by an immutable Skill
identity.  It never executes commands supplied by repository content and it
does not pretend that structured local execution is a native toolchain run.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from scripts.precision_migration.contracts import ContractRegistry
from scripts.precision_migration.runtime import canonical_digest
from scripts.precision_migration.trust import verify_content_reference

MAX_ASSETS = 16
MAX_TEXT = 8 * 1024 * 1024


class DomainExecutionError(ValueError):
    pass


def _write(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        raise DomainExecutionError(f"refusing to overwrite domain artifact: {path}")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(encoded)
    return {
        "uri": path.resolve().as_uri(),
        "digest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
        "media_type": "application/json",
    }


def _asset_path(uri: Any) -> Path:
    if not isinstance(uri, str):
        raise DomainExecutionError("asset URI must be a string")
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise DomainExecutionError("domain assets must use local file URIs")
    return Path(unquote(parsed.path))


def _assets(request: dict[str, Any], roots: tuple[Path, ...]) -> tuple[list[Any], list[dict[str, Any]]]:
    references = request.get("inputs", {}).get("assets", [])
    if not isinstance(references, list) or not 1 <= len(references) <= MAX_ASSETS:
        raise DomainExecutionError(f"domain execution requires 1..{MAX_ASSETS} content-addressed assets")
    payloads: list[Any] = []
    observations: list[dict[str, Any]] = []
    for index, reference in enumerate(references):
        try:
            observed = verify_content_reference(reference, roots)
            path = _asset_path(reference.get("uri"))
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise DomainExecutionError(f"asset[{index}] failed verification: {exc}") from exc
        if len(raw) > MAX_TEXT:
            raise DomainExecutionError(f"asset[{index}] exceeds the domain input budget")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"source_text": raw.decode("utf-8", errors="replace")}
        payloads.append(payload)
        observations.append({
            key: observed[key]
            for key in ("digest", "size_bytes", "media_type")
        })
    return payloads, observations


def _primary(payloads: list[Any]) -> dict[str, Any]:
    payload = payloads[0]
    if not isinstance(payload, dict):
        raise DomainExecutionError("primary domain asset must decode to an object")
    return payload


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainExecutionError(f"{label} must be numeric")
    return float(value)


def _decision(payloads: list[Any], _: dict[str, Any]) -> dict[str, Any]:
    payload = _primary(payloads)
    candidates = payload.get("candidates")
    criteria = payload.get("criteria")
    if not isinstance(candidates, list) or not candidates or not isinstance(criteria, dict) or not criteria:
        raise DomainExecutionError("decision execution requires candidates and criteria")
    weights = {name: _number(value, f"criteria.{name}") for name, value in criteria.items()}
    if any(weight < 0 for weight in weights.values()) or sum(weights.values()) <= 0:
        raise DomainExecutionError("decision criteria weights must be non-negative with positive total")
    scored = []
    all_names = set(weights)
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str):
            raise DomainExecutionError(f"candidates[{index}] requires id")
        metrics = candidate.get("metrics")
        if not isinstance(metrics, dict):
            raise DomainExecutionError(f"candidates[{index}].metrics must be an object")
        missing = sorted(all_names - set(metrics))
        score = sum(weights[name] * _number(metrics.get(name, 0), f"candidates[{index}].metrics.{name}") for name in weights)
        scored.append({"id": candidate["id"], "score": round(score / sum(weights.values()), 8), "missing_criteria": missing})
    scored.sort(key=lambda item: (-item["score"], item["id"]))
    confidence = max(0.0, 1.0 - sum(len(item["missing_criteria"]) for item in scored) / (len(scored) * len(weights)))
    return {"operation": "decision", "ranking": scored, "recommended": scored[0]["id"], "confidence": round(confidence, 8), "requires_human_review": confidence < 1.0}


def _walk(value: Any, path: str = "$") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [{"path": path, "type": type(value).__name__}]
    if isinstance(value, dict):
        for key in sorted(value):
            rows.extend(_walk(value[key], f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_walk(item, f"{path}[{index}]"))
    return rows


def _inspect(payloads: list[Any], _: dict[str, Any]) -> dict[str, Any]:
    payload = _primary(payloads)
    source = payload.get("source_text", "")
    if not isinstance(source, str):
        raise DomainExecutionError("source_text must be a string")
    identifiers = sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", source)))
    manifests = sorted(set(re.findall(r"(?:package\.json|pyproject\.toml|pom\.xml|go\.mod|Cargo\.toml|Dockerfile)", source)))
    return {
        "operation": "inspect",
        "json_paths": _walk(payload),
        "source": {"bytes": len(source.encode("utf-8")), "lines": len(source.splitlines()), "identifier_count": len(identifiers), "identifiers": identifiers[:1000]},
        "detected_manifests": manifests,
        "record_count": len(payload.get("records", [])) if isinstance(payload.get("records"), list) else 0,
    }


def _model(payloads: list[Any], _: dict[str, Any]) -> dict[str, Any]:
    payload = _primary(payloads)
    records = payload.get("records")
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise DomainExecutionError("model execution requires records[]")
    nodes: dict[str, dict[str, Any]] = {}
    edges = []
    for index, record in enumerate(records):
        identity = record.get("id")
        if not isinstance(identity, str) or not identity or identity in nodes:
            raise DomainExecutionError(f"records[{index}] has a missing or duplicate id")
        nodes[identity] = {key: value for key, value in sorted(record.items()) if key != "depends_on"}
    for record in records:
        for dependency in record.get("depends_on", []):
            if dependency not in nodes:
                raise DomainExecutionError(f"record {record['id']} references unknown dependency {dependency}")
            edges.append({"from": record["id"], "to": dependency})
    return {"operation": "model", "nodes": [nodes[key] for key in sorted(nodes)], "edges": sorted(edges, key=lambda item: (item["from"], item["to"])), "invariants": {"unique_ids": True, "closed_references": True}}


def _path_parent(document: Any, path: list[Any]) -> tuple[Any, Any]:
    if not path:
        raise DomainExecutionError("operation path must not be empty")
    current = document
    for part in path[:-1]:
        if isinstance(current, dict) and isinstance(part, str) and part in current or isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
            current = current[part]
        else:
            raise DomainExecutionError(f"operation path does not exist: {path}")
    return current, path[-1]


def _transform(payloads: list[Any], _: dict[str, Any]) -> dict[str, Any]:
    payload = _primary(payloads)
    if "document" not in payload or not isinstance(payload.get("operations"), list):
        raise DomainExecutionError("transform execution requires document and operations[]")
    document = copy.deepcopy(payload["document"])
    audit = []
    for index, operation in enumerate(payload["operations"]):
        if not isinstance(operation, dict) or operation.get("op") not in {"set", "remove", "rename", "assert"}:
            raise DomainExecutionError(f"operations[{index}] is unsupported")
        path = operation.get("path")
        if not isinstance(path, list) or any(not isinstance(item, (str, int)) or isinstance(item, bool) for item in path):
            raise DomainExecutionError(f"operations[{index}].path is invalid")
        parent, key = _path_parent(document, path)
        action = operation["op"]
        if action == "set":
            if isinstance(parent, dict) and isinstance(key, str):
                before = parent.get(key)
                parent[key] = copy.deepcopy(operation.get("value"))
            elif isinstance(parent, list) and isinstance(key, int) and 0 <= key < len(parent):
                before = parent[key]
                parent[key] = copy.deepcopy(operation.get("value"))
            else:
                raise DomainExecutionError(f"operations[{index}] cannot set path")
        elif action == "remove":
            if isinstance(parent, dict) and isinstance(key, str) and key in parent or isinstance(parent, list) and isinstance(key, int) and 0 <= key < len(parent):
                before = parent.pop(key)
            else:
                raise DomainExecutionError(f"operations[{index}] cannot remove path")
        elif action == "rename":
            destination = operation.get("to")
            if not isinstance(parent, dict) or not isinstance(key, str) or key not in parent or not isinstance(destination, str) or destination in parent:
                raise DomainExecutionError(f"operations[{index}] cannot rename path")
            before = parent.pop(key)
            parent[destination] = before
        else:
            if isinstance(parent, dict) and isinstance(key, str):
                before = parent.get(key)
            elif isinstance(parent, list) and isinstance(key, int) and 0 <= key < len(parent):
                before = parent[key]
            else:
                raise DomainExecutionError(f"operations[{index}] cannot assert path")
            if before != operation.get("equals"):
                raise DomainExecutionError(f"operations[{index}] assertion failed")
        audit.append({"index": index, "op": action, "path": path, "before_digest": canonical_digest(before)})
    return {"operation": "transform", "result": document, "audit": audit, "changed": bool(audit), "rollback": list(reversed(audit))}


def _compare(payloads: list[Any], _: dict[str, Any]) -> dict[str, Any]:
    payload = _primary(payloads)
    if "source" not in payload or "target" not in payload:
        raise DomainExecutionError("comparison requires source and target")
    source_paths = {item["path"]: item["type"] for item in _walk(payload["source"])}
    target_paths = {item["path"]: item["type"] for item in _walk(payload["target"])}
    different = []
    for path in sorted(set(source_paths) | set(target_paths)):
        if source_paths.get(path) != target_paths.get(path):
            different.append({"path": path, "source_type": source_paths.get(path), "target_type": target_paths.get(path)})
    equivalent = payload["source"] == payload["target"]
    return {"operation": "compare", "equivalent": equivalent, "structural_differences": different, "source_digest": canonical_digest(payload["source"]), "target_digest": canonical_digest(payload["target"])}


def _value_at(document: Any, path: list[Any]) -> Any:
    current = document
    for part in path:
        if isinstance(current, dict) and isinstance(part, str) and part in current or isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
            current = current[part]
        else:
            raise DomainExecutionError(f"assertion path does not exist: {path}")
    return current


def _validate(payloads: list[Any], _: dict[str, Any]) -> dict[str, Any]:
    payload = _primary(payloads)
    assertions = payload.get("assertions")
    document = payload.get("document")
    if not isinstance(assertions, list) or not assertions:
        raise DomainExecutionError("validation execution requires assertions[]")
    checks = []
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict) or assertion.get("operator") not in {"equals", "not_equals", "contains", "lte", "gte"}:
            raise DomainExecutionError(f"assertions[{index}] is invalid")
        path = assertion.get("path")
        if not isinstance(path, list):
            raise DomainExecutionError(f"assertions[{index}].path is invalid")
        actual, expected, operator = _value_at(document, path), assertion.get("expected"), assertion["operator"]
        passed = {
            "equals": actual == expected,
            "not_equals": actual != expected,
            "contains": expected in actual if isinstance(actual, (str, list, dict)) else False,
            "lte": isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual <= expected,
            "gte": isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual >= expected,
        }[operator]
        checks.append({"index": index, "path": path, "operator": operator, "outcome": "PASS" if passed else "FAIL"})
    return {"operation": "validate", "decision": "PASS" if all(item["outcome"] == "PASS" for item in checks) else "FAIL", "checks": checks}


def _plan(payloads: list[Any], contract: dict[str, Any]) -> dict[str, Any]:
    payload = _primary(payloads)
    units = payload.get("records")
    if not isinstance(units, list) or any(not isinstance(item, dict) for item in units):
        raise DomainExecutionError("planning requires records[]")
    by_id = {item.get("id"): item for item in units if isinstance(item.get("id"), str)}
    if len(by_id) != len(units):
        raise DomainExecutionError("planning records require unique ids")
    remaining, completed, waves = set(by_id), set(), []
    while remaining:
        ready = sorted(identity for identity in remaining if set(by_id[identity].get("depends_on", [])) <= completed)
        if not ready:
            raise DomainExecutionError("planning dependencies contain a cycle or unknown identity")
        waves.append(ready)
        completed.update(ready)
        remaining.difference_update(ready)
    return {"operation": "plan", "waves": waves, "contract_workflow": contract["workflow"], "all_dependencies_resolved": True}


def _govern(payloads: list[Any], _: dict[str, Any]) -> dict[str, Any]:
    payload = _primary(payloads)
    controls = payload.get("controls")
    if not isinstance(controls, list) or any(not isinstance(item, dict) for item in controls):
        raise DomainExecutionError("governance execution requires controls[]")
    checks = []
    for index, control in enumerate(controls):
        name, required, state = control.get("name"), control.get("required"), control.get("state")
        if not isinstance(name, str) or not isinstance(required, bool) or state not in {"PASS", "FAIL", "NOT_RUN"}:
            raise DomainExecutionError(f"controls[{index}] is invalid")
        checks.append({"name": name, "state": state, "blocking": required and state != "PASS"})
    blockers = [item["name"] for item in checks if item["blocking"]]
    return {"operation": "govern", "decision": "PASS" if not blockers else "BLOCK", "checks": checks, "blockers": blockers}


def _observe(payloads: list[Any], _: dict[str, Any]) -> dict[str, Any]:
    payload = _primary(payloads)
    metrics, thresholds = payload.get("metrics"), payload.get("thresholds")
    if not isinstance(metrics, dict) or not isinstance(thresholds, dict) or not thresholds:
        raise DomainExecutionError("observation requires metrics and thresholds")
    checks = []
    for name, threshold in sorted(thresholds.items()):
        value = _number(metrics.get(name), f"metrics.{name}")
        maximum = _number(threshold, f"thresholds.{name}")
        checks.append({"metric": name, "value": value, "maximum": maximum, "outcome": "PASS" if value <= maximum else "FAIL"})
    return {"operation": "observe", "decision": "PASS" if all(item["outcome"] == "PASS" for item in checks) else "BLOCK", "checks": checks}


OPERATIONS: dict[str, Callable[[list[Any], dict[str, Any]], dict[str, Any]]] = {
    "decision": _decision,
    "inspect": _inspect,
    "model": _model,
    "transform": _transform,
    "compare": _compare,
    "validate": _validate,
    "plan": _plan,
    "govern": _govern,
    "observe": _observe,
}

_CONTRACTS: ContractRegistry | None = None


def _contracts() -> ContractRegistry:
    global _CONTRACTS
    if _CONTRACTS is None:
        _CONTRACTS = ContractRegistry.load()
    return _CONTRACTS


def operation_for(batch: int, source_skill: str) -> str:
    name = source_skill.lower()
    if batch in {1, 3, 4, 36, 40} or any(token in name for token in ("decision", "selector", "ranker", "estimator", "score")):
        return "decision"
    if batch in {5, 14, 17, 19, 28} or any(token in name for token in ("inventory", "discovery", "detector", "scanner", "analyzer", "parser", "recovery", "extractor", "indexer")):
        return "inspect"
    if batch in {8, 9, 10, 33} or any(token in name for token in ("-ir", "-model", "graph", "tree", "state-machine")):
        return "model"
    if batch in {12, 15, 18, 20, 21, 22, 23, 24, 25, 26, 27} or any(token in name for token in ("converter", "rewriter", "lowering", "generator", "migration", "transformation")):
        return "transform"
    if batch in {30, 31} or any(token in name for token in ("comparator", "differential", "equivalence", "diff")):
        return "compare"
    if batch in {29, 32, 34, 35} or any(token in name for token in ("validator", "validation", "test", "proof", "fuzz", "checking", "obligation")):
        return "validate"
    if batch in {2, 6, 11, 13, 37, 38, 39} or any(token in name for token in ("planner", "orchestrator", "decomposer", "registry", "compiler")):
        return "plan"
    if batch in {7, 44} or any(token in name for token in ("security", "policy", "audit", "license", "isolation", "rbac", "sandbox")):
        return "govern"
    if batch == 43 or any(token in name for token in ("monitor", "learning", "calibration", "drift")):
        return "observe"
    return "inspect"


def execute_domain_skill(
    request: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    *,
    evidence_roots: tuple[Path, ...],
    **_: Any,
) -> dict[str, Any]:
    expected = f"domain-skill-v2:{entry['source_skill']}"
    if entry.get("handler_id") != expected or entry.get("kind") != "skill":
        raise DomainExecutionError("domain handler identity mismatch")
    contracts = _contracts()
    contract = contracts.by_skill.get(entry["skill"])
    if contract is None or contract.get("source_skill") != entry.get("source_skill"):
        raise DomainExecutionError("domain handler contract binding mismatch")
    payloads, observations = _assets(request, evidence_roots)
    operation = operation_for(int(entry["batch"]), str(entry["source_skill"]))
    result = OPERATIONS[operation](payloads, contract)
    body = {
        "schema_version": 1,
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "source_skill": entry["source_skill"],
        "batch": entry["batch"],
        "handler_id": entry["handler_id"],
        "operation": operation,
        "contract_digest": contract["contract_digest"],
        "input_evidence": observations,
        "result": result,
        "execution_scope": "BOUNDED_STRUCTURED_LOCAL",
        "native_toolchain_execution": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "production_execution": "NOT_RUN",
        "limitations": [
            "This result covers the bounded structured algorithm only.",
            "Native toolchain, customer workload, independent review, and production evidence require separate execution.",
        ],
    }
    body["result_digest"] = canonical_digest(body)
    artifact = _write(output_dir / "domain-execution.json", body)
    return {"execution_state": "LOCAL_EXECUTED", "artifacts": [artifact], "exit_code": 0}
