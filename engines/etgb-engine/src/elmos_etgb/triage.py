"""Deterministic failure classification and clustering."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from .canonical import digest_json


FAILURE_CLASSES = ("source-baseline-failure", "environment-dependency", "authority-security", "budget-quota", "checkpoint-recovery", "transform-generate-planning", "target-build", "behavior-mismatch", "state-transaction-mismatch", "security-regression", "performance-regression", "unsupported-undisclosed", "harness-oracle-defect", "unknown")


def normalize_message(message: str) -> str:
    value = message.lower()
    value = re.sub(r"0x[0-9a-f]+", "<hex>", value)
    value = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<uuid>", value)
    value = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", value)
    value = re.sub(r"/[^\s:]+", "<path>", value)
    return re.sub(r"\s+", " ", value).strip()[:500]


def classify_failure(result: dict[str, Any]) -> str:
    explicit = result.get("failure_class")
    if explicit in FAILURE_CLASSES:
        return str(explicit)
    text = " ".join([str(result.get("status", ""))] + [str(oracle.get(key, "")) for oracle in result.get("oracle_results", []) for key in ("type", "reason", "message", "error_type")]).lower()
    rules = (("source-baseline-failure", ("source baseline", "baseline broken")), ("authority-security", ("permission", "authority", "fencing", "sandbox", "secret")), ("budget-quota", ("budget", "quota", "credit", "token limit")), ("checkpoint-recovery", ("checkpoint", "resume", "recovery", "compensation")), ("environment-dependency", ("unavailable", "dependency", "registry", "docker", "environment")), ("target-build", ("compile", "build", "linker", "syntax error")), ("state-transaction-mismatch", ("transaction", "rollback", "state", "side-effect", "row mismatch")), ("security-regression", ("authorization", "authentication", "csrf", "privilege", "tenant leak")), ("performance-regression", ("latency", "throughput", "memory", "performance")), ("unsupported-undisclosed", ("unsupported", "silent deletion", "manual intervention")), ("harness-oracle-defect", ("oracle conflict", "harness error", "test defect")), ("behavior-mismatch", ("mismatch", "different result", "semantic")), ("transform-generate-planning", ("generation", "translation", "planning")))
    for name, needles in rules:
        if any(needle in text for needle in needles):
            return name
    return "unknown"


def failure_signature(result: dict[str, Any]) -> str:
    messages = sorted({normalize_message(" ".join(str(oracle.get(key, "")) for key in ("type", "reason", "message", "error_type"))) for oracle in result.get("oracle_results", [])})
    return digest_json({"classification": classify_failure(result), "business_line": result.get("business_line"), "messages": messages})[7:27]


def cluster_failures(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        if result.get("status") != "passed":
            clusters[failure_signature(result)].append(result)
    output = []
    for signature, rows in sorted(clusters.items(), key=lambda item: (-len(item[1]), item[0])):
        classes = Counter(classify_failure(row) for row in rows)
        output.append({"signature": signature, "count": len(rows), "failure_class": classes.most_common(1)[0][0], "case_ids": sorted({row.get("case_id") for row in rows}), "business_lines": sorted({row.get("business_line") for row in rows}), "example": rows[0]})
    return {"cluster_count": len(output), "failed_result_count": sum(item["count"] for item in output), "clusters": output}
