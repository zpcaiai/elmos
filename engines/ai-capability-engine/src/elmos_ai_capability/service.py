"""Service API layer for AI Capability Enhancement engine."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Any, Mapping, Sequence

from .runtime import AICapabilityRuntime, SkillExecutionResult
from .golden_routes import GoldenRouteEngine, GoldenRouteResult
from .workflows import WorkflowEngine, WorkflowExecutionResult
from .database import MigrationManager, MigrationResult
from .policies import PolicyEngine, PolicyEvaluationResult
from .kernel import (
    FeatureRequirement,
    TargetProfile,
    NegotiationResult,
    negotiate,
    compare_traces,
    certify,
    CertificationInput,
    ProofResult,
)


class AICapabilityService:
    """Enterprise service orchestrator exposing capability operations."""

    def __init__(self) -> None:
        self.runtime = AICapabilityRuntime()
        self.golden_routes = GoldenRouteEngine()
        self.workflows = WorkflowEngine()
        self.migrations = MigrationManager()
        self.policies = PolicyEngine()

    def run_skill(self, skill_name: str, inputs: Mapping[str, Any]) -> SkillExecutionResult:
        return self.runtime.execute_skill(skill_name, inputs)

    def run_golden_route(self, route_name: str, context: Mapping[str, Any] | None = None) -> GoldenRouteResult:
        return self.golden_routes.execute_route(route_name, context)

    def run_workflow(self, workflow_name: str, context: Mapping[str, Any] | None = None) -> WorkflowExecutionResult:
        return self.workflows.execute_workflow(workflow_name, context)

    def validate_database_migrations(self) -> dict[str, MigrationResult]:
        return self.migrations.validate_all_migrations()

    def evaluate_policy(self, policy_name: str, context: Mapping[str, Any]) -> PolicyEvaluationResult:
        return self.policies.evaluate_policy(policy_name, context)

    def negotiate_capabilities(self, reqs: Sequence[Mapping[str, Any]], profiles: Sequence[Mapping[str, Any]]) -> NegotiationResult:
        typed_reqs = [
            FeatureRequirement(
                name=r["name"],
                critical=r.get("critical", True),
                accepted_statuses=frozenset(r.get("acceptedStatuses", ["supported", "conditional", "external-runtime", "external-policy"])),
            )
            for r in reqs
        ]
        typed_profiles = [
            TargetProfile(
                target=p["target"],
                features=p["features"],
                exact_version=p["exactVersion"],
                adapter_digest=p["adapterDigest"],
            )
            for p in profiles
        ]
        return negotiate(typed_reqs, typed_profiles)
