"""Tests for Policy, Security, and Data Governance Engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from elmos_router_industrial.domain.contracts import (
    BudgetEnvelope,
    CapabilityLease,
    DataClassification,
    ExecutionLane,
    ModelDescriptor,
    ModelLifecycle,
    ProviderDeployment,
    ProviderDescriptor,
    RouteRequest,
    TaskClass,
    VerifiedSecurityContext,
)
from elmos_router_industrial.policy.engine import PolicyEngine, redact_sensitive_data

CONFIGS_DIR = Path(__file__).resolve().parents[4] / "skills/subskills/elmos-router-industrial-skillpack/configs"
if not CONFIGS_DIR.exists():
    CONFIGS_DIR = Path("/Users/stephen/.gemini/antigravity/brain/28d35f92-a69f-4629-8da0-fdda5777b2c7/scratch/elmos-router-industrial-skillpack/configs")


class TestPolicyEngine(unittest.TestCase):
    def setUp(self) -> None:
        with open(CONFIGS_DIR / "policy.example.yaml", "r", encoding="utf-8") as f:
            self.policy_engine = PolicyEngine.from_yaml(f.read())

        self.model = ModelDescriptor(
            alias="strategic-coding-high",
            family="coding-reasoning",
            lifecycle=ModelLifecycle.STABLE,
            capabilities={"coding": 0.98, "reasoning": 0.95},
            maxContextTokens=128_000,
            maxOutputTokens=4096,
            supportsToolCalling=True,
            supportsStructuredOutput=True,
        )
        self.provider = ProviderDescriptor(
            id="openai-direct",
            type="NATIVE",
            credentialRef="secret://providers/openai",
            enabled=True,
            supportedRegions=("us", "eu"),
            prohibitsTraining=True,
        )
        self.deployment = ProviderDeployment(
            id="strategic-coding-high-openai-native",
            modelAlias="strategic-coding-high",
            providerId="openai-direct",
            lane=ExecutionLane.NATIVE_DIRECT,
            actualModel="gpt-4o",
            enabled=True,
            regions=("us",),
            priceInputPer1k=0.003,
            priceOutputPer1k=0.015,
        )
        self.base_request = RouteRequest(
            tenantId="tenant_finance",
            taskId="task_001",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.CODE_GENERATION,
            dataClassification=(DataClassification.INTERNAL,),
            securityContextRef="sec_ref",
            capabilityLeaseRef="lease_ref",
            budgetEnvelope=BudgetEnvelope("USD", 10.0),
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
            idempotencyKey="idem_001",
        )

    def test_fail_closed_on_missing_classification(self) -> None:
        req = RouteRequest(
            tenantId="tenant_finance",
            taskId="task_001",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.CODE_GENERATION,
            dataClassification=(),  # empty
            securityContextRef="sec_ref",
            capabilityLeaseRef="lease_ref",
            budgetEnvelope=BudgetEnvelope("USD", 10.0),
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
            idempotencyKey="idem_001",
        )
        res = self.policy_engine.evaluate(req, self.model, self.provider, self.deployment)
        self.assertFalse(res.eligible)
        self.assertTrue(any("Missing data classification" in r for r in res.denialReasons))

    def test_secret_bearing_restrictions(self) -> None:
        # SECRET_BEARING forbids OpenRouter lane
        openrouter_dep = ProviderDeployment(
            id="openrouter-dep",
            modelAlias="strategic-coding-high",
            providerId="openrouter",
            lane=ExecutionLane.OPENROUTER,
            actualModel="anthropic/claude-3.5-sonnet",
            enabled=True,
        )
        req = RouteRequest(
            tenantId="tenant_finance",
            taskId="task_001",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.CODE_GENERATION,
            dataClassification=(DataClassification.SECRET_BEARING,),
            securityContextRef="sec_ref",
            capabilityLeaseRef="lease_ref",
            budgetEnvelope=BudgetEnvelope("USD", 10.0),
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
            idempotencyKey="idem_001",
        )
        res = self.policy_engine.evaluate(req, self.model, self.provider, openrouter_dep)
        self.assertFalse(res.eligible)
        self.assertTrue(any("OpenRouter lane strictly forbidden" in r for r in res.denialReasons))

    def test_context_window_limit_rejection(self) -> None:
        req = RouteRequest(
            tenantId="tenant_finance",
            taskId="task_001",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.CODE_GENERATION,
            dataClassification=(DataClassification.INTERNAL,),
            securityContextRef="sec_ref",
            capabilityLeaseRef="lease_ref",
            budgetEnvelope=BudgetEnvelope("USD", 10.0),
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
            idempotencyKey="idem_001",
            maxInputTokens=100_000,
            expectedOutputTokens=30_000,  # total 130k > 128k maxContextTokens
        )
        res = self.policy_engine.evaluate(req, self.model, self.provider, self.deployment)
        self.assertFalse(res.eligible)
        self.assertTrue(any("exceed model max context tokens" in r for r in res.denialReasons))

    def test_budget_hard_ceiling_rejection(self) -> None:
        req = RouteRequest(
            tenantId="tenant_finance",
            taskId="task_001",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.CODE_GENERATION,
            dataClassification=(DataClassification.INTERNAL,),
            securityContextRef="sec_ref",
            capabilityLeaseRef="lease_ref",
            budgetEnvelope=BudgetEnvelope("USD", 0.0001),  # tiny budget
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
            idempotencyKey="idem_001",
            maxInputTokens=10_000,
            expectedOutputTokens=5_000,
        )
        res = self.policy_engine.evaluate(req, self.model, self.provider, self.deployment)
        self.assertFalse(res.eligible)
        self.assertTrue(any("exceeds budget hard ceiling" in r for r in res.denialReasons))

    def test_sensitive_data_redaction(self) -> None:
        data = {
            "model": "gpt-4o",
            "api_key": "sk-supersecret123456",
            "nested": {
                "bearer_token": "token_abcdef",
                "safe_field": "public_data",
            },
            "array": [{"auth_token": "secret_xyz"}, "normal_text"],
        }
        redacted = redact_sensitive_data(data)
        self.assertEqual(redacted["api_key"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["bearer_token"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["safe_field"], "public_data")
        self.assertEqual(redacted["array"][0]["auth_token"], "[REDACTED]")
        self.assertEqual(redacted["array"][1], "normal_text")


if __name__ == "__main__":
    unittest.main()
