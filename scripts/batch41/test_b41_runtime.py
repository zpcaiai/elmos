"""Unit and contract tests for all 20 Batch 41 Migration Knowledge & Prediction skills."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/batch41"))

from b41_skill_runtime import B41SkillRuntime


@pytest.fixture
def runtime():
    return B41SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 20
    for s in runtime.SKILLS:
        assert s.startswith("b41-")


def test_b41_migration_knowledge_factory(runtime):
    res = runtime.dispatch("b41-migration-knowledge-factory", "init", {})
    assert res["status"] == "KNOWLEDGE_FACTORY_INITIALIZED"
    assert res["ready"] is True
    assert "graph-ontology" in res["flywheel_components"]


def test_b41_knowledge_graph_ontology(runtime):
    res = runtime.dispatch("b41-knowledge-graph-ontology", "compile", {})
    assert res["status"] == "ONTOLOGY_COMPILED"
    assert "AntiPattern" in res["entity_types"]


def test_b41_migration_entity_relations(runtime):
    res = runtime.dispatch("b41-migration-entity-relations", "relate", {"source_entity": "SpringSecurity-v4"})
    assert res["status"] == "ENTITY_RELATION_EXTRACTED"
    assert res["confidence_score"] >= 0.95


def test_b41_migration_run_ingestion(runtime):
    res = runtime.dispatch("b41-migration-run-ingestion", "ingest", {"run_id": "run-01"})
    assert res["status"] == "RUN_INGESTED_TO_KNOWLEDGE_BASE"
    assert res["anonymization_applied"] is True


def test_b41_pattern_antipattern_extraction(runtime):
    res = runtime.dispatch("b41-pattern-antipattern-extraction", "mine", {})
    assert res["status"] == "PATTERN_MINED"
    assert res["frequency_observed"] > 0


def test_b41_recipe_mapping_recommendation(runtime):
    res = runtime.dispatch("b41-recipe-mapping-recommendation", "recommend", {})
    assert res["status"] == "RECIPES_RECOMMENDED"
    assert len(res["recommended_recipes"]) == 3


def test_b41_diagnostic_root_cause_recommendation(runtime):
    res = runtime.dispatch("b41-diagnostic-root-cause-recommendation", "diagnose", {})
    assert res["status"] == "DIAGNOSTIC_RECOMMENDED"
    assert res["confidence"] >= 0.95


def test_b41_effort_duration_cost_prediction(runtime):
    res = runtime.dispatch("b41-effort-duration-cost-prediction", "predict", {"lines_of_code": 50000})
    assert res["status"] == "EFFORT_PREDICTED"
    assert res["predicted_cost_usd"] > 0


def test_b41_migration_risk_prediction(runtime):
    res = runtime.dispatch("b41-migration-risk-prediction", "predict", {"modules_count": 10})
    assert res["status"] == "RISK_PREDICTION_CALCULATED"
    assert res["risk_tier"] == "LOW_MEDIUM"


def test_b41_automation_buildgreen_prediction(runtime):
    res = runtime.dispatch("b41-automation-buildgreen-prediction", "predict", {})
    assert res["status"] == "BUILDGREEN_PREDICTED"
    assert res["repair_loop_converge_probability"] >= 0.95


def test_b41_target_stack_recommendation(runtime):
    res = runtime.dispatch("b41-target-stack-recommendation", "recommend", {})
    assert res["status"] == "STACK_RECOMMENDED"
    assert "Go 1.23" in res["recommended_target_stack"]["language"]


def test_b41_similar_project_retrieval(runtime):
    res = runtime.dispatch("b41-similar-project-retrieval", "search", {})
    assert res["status"] == "SIMILAR_PROJECTS_RETRIEVED"
    assert len(res["top_k_matches"]) == 2


def test_b41_knowledge_confidence_provenance(runtime):
    res = runtime.dispatch("b41-knowledge-confidence-provenance", "verify", {})
    assert res["status"] == "PROVENANCE_CONFIRMED"
    assert res["content_hash"].startswith("sha256:")


def test_b41_knowledge_freshness_versioning(runtime):
    res = runtime.dispatch("b41-knowledge-freshness-versioning", "check", {})
    assert res["status"] == "KNOWLEDGE_FRESHNESS_VERIFIED"
    assert res["is_fresh"] is True


def test_b41_human_curation_governance(runtime):
    res = runtime.dispatch("b41-human-curation-governance", "record", {})
    assert res["status"] == "CURATION_RECORDED"
    assert res["regression_safety_reviewed"] is True


def test_b41_holdout_feedback_calibration(runtime):
    res = runtime.dispatch("b41-holdout-feedback-calibration", "calibrate", {})
    assert res["status"] == "CALIBRATION_CERTIFIED"
    assert res["well_calibrated"] is True


def test_b41_privacy_preserving_learning(runtime):
    res = runtime.dispatch("b41-privacy-preserving-learning", "sanitize", {})
    assert res["status"] == "PRIVACY_PRESERVED"
    assert res["pii_redacted"] is True


def test_b41_knowledge_isolation(runtime):
    res = runtime.dispatch("b41-knowledge-isolation", "test_isolation", {})
    assert res["status"] == "TENANT_ISOLATION_VERIFIED"
    assert res["cross_tenant_query_blocked"] is True


def test_b41_knowledge_marketplace_sharing(runtime):
    res = runtime.dispatch("b41-knowledge-marketplace-sharing", "share", {})
    assert res["status"] == "PACK_SHARED_TO_MARKETPLACE"
    assert res["author_revenue_split_percent"] == 70


def test_b41_knowledge_flywheel_gate(runtime):
    res = runtime.dispatch("b41-knowledge-flywheel-gate", "evaluate", {
        "knowledgeProvenanceCoverageRate": 0.98,
        "privacyIsolationPassRate": 1.0,
        "predictionCalibrationPassRate": 1.0,
    })
    assert res["passed"] is True
    assert res["status"] == "GATE_PASSED"

    res_fail = runtime.dispatch("b41-knowledge-flywheel-gate", "evaluate", {
        "knowledgeProvenanceCoverageRate": 0.88,
        "privacyIsolationPassRate": 1.0,
        "predictionCalibrationPassRate": 1.0,
    })
    assert res_fail["passed"] is False
    assert res_fail["status"] == "GATE_REJECTED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b41-non-existent-skill", "check")
