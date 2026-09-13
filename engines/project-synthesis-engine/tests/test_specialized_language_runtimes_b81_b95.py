"""Tests for Specialized Language Runtimes & Cross-Compilation Verification Harness (B81-B95)."""

from __future__ import annotations

from elmos_project_synthesis.specialized_language_harness import (
    SpecializedEvaluationSummary,
    SpecializedLanguageHarness,
    run_specialized_language_evaluation,
)


def test_specialized_language_harness_loads_all_180_skills():
    harness = SpecializedLanguageHarness()
    assert len(harness.registry) == 180
    assert len(harness.registry.batches) == 15

    for b in range(81, 96):
        skills = harness.registry.get_batch(b)
        assert len(skills) == 12, f"Batch {b} does not have 12 skills"


def test_specialized_language_harness_executes_all_15_batches():
    harness = SpecializedLanguageHarness()
    total_skills, batch_receipts = harness.execute_all_skills()

    assert total_skills == 180
    assert len(batch_receipts) == 15
    for r in batch_receipts:
        assert r["skills_executed"] == 12
        assert r["status"] == "LOCAL_EXECUTED"
        assert r["receipt_digest"].startswith("sha256:")


def test_specialized_language_harness_loads_1090_verification_cases():
    harness = SpecializedLanguageHarness()
    b81_count, b66_count, all_cases = harness.load_test_cases()

    assert b81_count == 640
    assert b66_count == 450
    assert len(all_cases) == 1090


def test_specialized_language_full_evaluation_summary():
    summary = run_specialized_language_evaluation()

    assert isinstance(summary, SpecializedEvaluationSummary)
    assert summary.batches_covered == 15
    assert summary.total_skills_bound == 180
    assert summary.skills_executed == 180
    assert summary.total_test_cases == 1090
    assert summary.b81_95_cases_evaluated == 640
    assert summary.b66_80_cases_evaluated == 450
    assert summary.execution_status == "LOCAL_EXECUTED"
    assert summary.gate_decision == "LOCAL_PASSED"
    assert summary.certification_status == "NOT_CERTIFIED"
    assert summary.external_evidence_status == "NOT_RUN"
    assert summary.evidence_digest.startswith("sha256:")
