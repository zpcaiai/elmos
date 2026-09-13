#!/usr/bin/env python3
"""Pytest suite for TstSkillRuntime (82 strict test suite skills)."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/test-suite"))

from tst_skill_runtime import TstSkillRuntime, TstExecutionResult


@pytest.fixture
def runtime():
    return TstSkillRuntime(ROOT)


def test_tst_skills_enumeration(runtime):
    assert len(runtime.all_skills) == 82
    assert len(runtime.b1_37_catalog) == 52
    assert len(runtime.b38_45_catalog) == 30


def test_batch1_37_orchestrator(runtime):
    res = runtime.execute("tst-strict-suite-orchestrator")
    assert isinstance(res, TstExecutionResult)
    assert res.skill == "tst-strict-suite-orchestrator"
    assert res.status == "SUCCESS"
    assert res.local_handler_status == "PASSED"
    assert res.external_evidence_status == "LOCAL_EXECUTED"
    assert res.certification_status == "NOT_CERTIFIED"
    assert len(res.case_ids) == 6
    assert res.details["anti_cheat"]["fake_evidence_rejected"] is True


def test_batch38_45_orchestrator(runtime):
    res = runtime.execute("tst-b38-45-strict-suite-orchestrator")
    assert isinstance(res, TstExecutionResult)
    assert res.skill == "tst-b38-45-strict-suite-orchestrator"
    assert res.status == "SUCCESS"
    assert res.local_handler_status == "PASSED"
    assert res.external_evidence_status == "LOCAL_EXECUTED"
    assert res.certification_status == "NOT_CERTIFIED"
    assert len(res.case_ids) == 8
    assert res.details["suite_source"] == "batch38-45-strict"


@pytest.mark.parametrize("skill_name", [
    # Batch 1-37 representative skills
    "tst-b01-secure-repository-intake",
    "tst-b02-semantic-adapters-psp",
    "tst-b03-unified-ir",
    "tst-b04-target-skeleton",
    "tst-b05-method-lowering",
    "tst-b06-dependency-api-mapping",
    "tst-b07-framework-mapping",
    "tst-b08-bounded-repair-loop",
    "tst-b09-behavior-equivalence",
    "tst-b10-production-hardening",
    "tst-b11-release-data-cutover-retirement",
    "tst-b12-enterprise-platformization",
    "tst-b13-commercial-onboarding-poc-support",
    "tst-b14-plg-community-localization",
    "tst-b15-company-operating-system",
    "tst-b16-ai-native-workforce",
    "tst-b17-vertical-solution-factory",
    "tst-b18-ma-group-migration",
    "tst-b19-productization-blueprint",
    "tst-b20-executable-scaffold",
    "tst-b21-real-repository-vertical-slice",
    "tst-b22-semantic-hardening",
    "tst-b23-spring-to-aspnet",
    "tst-b24-build-test-repair",
    "tst-b25-high-confidence-behavior-poc",
    "tst-b26-private-runner-security",
    "tst-b27-incremental-production-factory",
    "tst-b28-organization-talent",
    "tst-b29-multi-language-routes",
    "tst-b30-multi-framework-version",
    "tst-b31-database-data-platform",
    "tst-b32-client-modernization",
    "tst-b33-cloud-iac-devops",
    "tst-b34-portfolio-scale",
    "tst-b35-advanced-formal-verification",
    "tst-b36-ide-cli-pr-experience",
    "tst-b37-extension-marketplace-closure",
    # Batch 38-45 representative skills
    "tst-b38-deployment-upgrade-lifecycle",
    "tst-b39-global-sre-operations",
    "tst-b40-supply-chain-compliance",
    "tst-b41-knowledge-flywheel",
    "tst-b42-agent-factory",
    "tst-b43-product-lifecycle-lts",
    "tst-b44-finops-economics",
    "tst-b45-mature-product-certification",
    "tst-agent-adversarial-permission-runaway",
    "tst-airgap-offline-update-revocation",
    "tst-api-event-sdk-runner-compatibility",
    "tst-chaos-dr-recovery",
    "tst-observability-slo-incident",
])
def test_each_strict_test_skill(runtime, skill_name):
    res = runtime.execute(skill_name)
    assert isinstance(res, TstExecutionResult)
    assert res.skill == skill_name
    assert res.status == "SUCCESS"
    assert res.local_handler_status == "PASSED"
    assert res.external_evidence_status == "LOCAL_EXECUTED"
    assert res.certification_status == "NOT_CERTIFIED"
    assert len(res.case_ids) > 0
    assert len(res.evidence["suite_digest"]) == 64


def test_unknown_skill_raises(runtime):
    with pytest.raises(ValueError, match="Unknown test suite skill"):
        runtime.execute("tst-completely-fake-nonexistent-skill")
