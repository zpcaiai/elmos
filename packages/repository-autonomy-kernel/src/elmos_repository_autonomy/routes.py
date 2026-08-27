"""The three package golden-route definitions as executable planning data."""

from __future__ import annotations

from typing import Any

GOLDEN_ROUTES: dict[str, dict[str, Any]] = {
    "spring-legacy-modernization": {"title": "Spring Legacy Modernization Golden Route", "mandatory_gates": ["route-baseline-build", "route-api-contract", "route-transaction-semantics", "route-security", "route-database-rehearsal", "route-shadow-runtime", "route-rollback"]},
    "cross-language-semantic-rewrite": {"title": "Cross-Language Semantic Rewrite Golden Route", "mandatory_gates": ["source-baseline", "ir-validation", "target-build", "contract-equivalence", "differential-runtime", "performance-envelope", "rollback"]},
    "repository-scale-refactor": {"title": "Repository-Scale Refactor Golden Route", "mandatory_gates": ["repository-census", "changegraph-traceability", "parallel-write-isolation", "full-validation-dag", "security", "chaos-recovery", "deployment-complete"]},
}

FAILURE_INJECTION = ["executor-crash", "network-interruption", "duplicate-delivery", "stale-worker-return", "user-pause-resume", "prompt-injection-in-repository"]


def route_definition(route_id: str) -> dict[str, Any]:
    if route_id not in GOLDEN_ROUTES:
        raise KeyError(route_id)
    return {"id": route_id, "version": "2.0.0", "release_gate": "P05_DEPLOYMENT_COMPLETE", "failure_injection": list(FAILURE_INJECTION), **GOLDEN_ROUTES[route_id]}
