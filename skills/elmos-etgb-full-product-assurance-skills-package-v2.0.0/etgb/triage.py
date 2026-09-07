from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any, Iterable


FAILURE_CLASSES = [
    "source-baseline-failure",
    "environment-dependency",
    "authority-security",
    "budget-quota",
    "checkpoint-recovery",
    "transform-generate-planning",
    "target-build",
    "behavior-mismatch",
    "state-transaction-mismatch",
    "security-regression",
    "performance-regression",
    "unsupported-undisclosed",
    "harness-oracle-defect",
    "unknown",
]


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
        return explicit
    text_parts = [str(result.get("status", ""))]
    for oracle in result.get("oracle_results", []):
        text_parts.extend(str(oracle.get(key, "")) for key in ("type", "reason", "message", "error_type"))
    text = " ".join(text_parts).lower()
    rules = [
        ("source-baseline-failure", ["source baseline", "baseline broken"]),
        ("authority-security", ["permission", "authority", "fencing", "sandbox", "secret"]),
        ("budget-quota", ["budget", "quota", "credit", "token limit"]),
        ("checkpoint-recovery", ["checkpoint", "resume", "recovery", "compensation"]),
        ("environment-dependency", ["unavailable", "dependency", "registry", "docker", "environment"]),
        ("target-build", ["compile", "build", "linker", "syntax error"]),
        ("state-transaction-mismatch", ["transaction", "rollback", "state", "side-effect", "row mismatch"]),
        ("security-regression", ["authorization", "authentication", "csrf", "privilege", "tenant leak"]),
        ("performance-regression", ["latency", "throughput", "memory", "performance"]),
        ("unsupported-undisclosed", ["unsupported", "silent deletion", "manual intervention"]),
        ("harness-oracle-defect", ["oracle conflict", "harness error", "test defect"]),
        ("behavior-mismatch", ["mismatch", "different result", "semantic"]),
        ("transform-generate-planning", ["generation", "translation", "planning"]),
    ]
    for label, needles in rules:
        if any(needle in text for needle in needles):
            return label
    return "unknown"


def failure_signature(result: dict[str, Any]) -> str:
    classification = classify_failure(result)
    messages: list[str] = []
    for oracle in result.get("oracle_results", []):
        messages.append(
            normalize_message(" ".join(str(oracle.get(key, "")) for key in ("type", "reason", "message", "error_type")))
        )
    material = {
        "classification": classification,
        "business_line": result.get("business_line"),
        "case_id": result.get("case_id"),
        "messages": sorted(set(messages)),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()[:20]


def cluster_failures(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        if result.get("status") == "passed":
            continue
        clusters[failure_signature(result)].append(result)
    payload: list[dict[str, Any]] = []
    for signature, rows in sorted(clusters.items(), key=lambda item: (-len(item[1]), item[0])):
        classes = Counter(classify_failure(row) for row in rows)
        payload.append(
            {
                "signature": signature,
                "count": len(rows),
                "failure_class": classes.most_common(1)[0][0],
                "case_ids": sorted({row.get("case_id") for row in rows}),
                "business_lines": sorted({row.get("business_line") for row in rows}),
                "example": rows[0],
            }
        )
    return {"cluster_count": len(payload), "failed_result_count": sum(x["count"] for x in payload), "clusters": payload}
