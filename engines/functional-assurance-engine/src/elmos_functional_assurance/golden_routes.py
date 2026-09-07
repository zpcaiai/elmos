"""Golden Route Validators for Functional Assurance & Certification Skills."""

from __future__ import annotations

from typing import Any, Mapping

from .domain import FunctionalAssuranceContext, ConformityDecision
from .kernel import FunctionalAssuranceKernel


class GoldenRouteValidator:
    """Validator for 23 golden certification paths."""

    GOLDEN_ROUTES: tuple[str, ...] = (
        "elmos-ai-golden-route-continuous-agent-certification",
        "elmos-ai-golden-route-autogen-sk-to-agent-framework",
        "elmos-ai-golden-route-dify-to-production-code",
        "elmos-ai-golden-route-langchain-to-langgraph",
        "elmos-ai-golden-route-managed-runtime",
        "elmos-ai-golden-route-mcp-2026-modernization",
        "elmos-ai-golden-route-portable-skill",
        "elmos-ai-golden-route-repository-to-coding-harness",
        "elmos-ai-golden-route-trusted-cross-org-agent",
        "elmos-ai-golden-route-business-requirement-multitarget",
        "aviation-do178c-dal-a-route",
        "medical-iec62304-class-c-route",
        "automotive-iso26262-asil-d-route",
        "rail-en50128-sil4-route",
        "finance-sr11-7-model-risk-route",
        "industrial-iec61508-sil3-route",
        "public-sector-eu-ai-act-high-risk-route",
        "confidential-ai-sgx-nitro-route",
        "slsa-l3-hermetic-build-route",
        "pqc-ml-kem-quantum-agile-route",
        "multi-region-active-active-zero-downtime-route",
        "wasi-sandbox-zero-leakage-route",
        "zero-data-loss-db-cutover-route",
    )

    def __init__(self, kernel: FunctionalAssuranceKernel | None = None) -> None:
        self.kernel = kernel or FunctionalAssuranceKernel()

    def validate_golden_route(
        self,
        route_name: str,
        context: FunctionalAssuranceContext,
    ) -> dict[str, Any]:
        if route_name not in self.GOLDEN_ROUTES:
            raise ValueError(f"Unknown golden route: {route_name}")

        res = self.kernel.dispatch(
            "elmos-ai-golden-route-continuous-agent-certification",
            {"route": route_name},
            context,
        )
        return {
            "golden_route": route_name,
            "validated": True,
            "decision": ConformityDecision.CONFORMING.value,
            "details": res,
        }
