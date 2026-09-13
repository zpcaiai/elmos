from __future__ import annotations

from elmos_teaching_subsystem.teaching_scenarios import (
    create_onboarding_scenario,
    create_architecture_review_scenario,
    ScenarioCategory,
    TeachingEngine
)

def test_create_onboarding():
    scen = create_onboarding_scenario(".")
    assert scen.category == ScenarioCategory.ONBOARDING
    assert len(scen.steps) == 1

def test_create_arch_review():
    scen = create_architecture_review_scenario(".")
    assert scen.category == ScenarioCategory.ARCHITECTURE_REVIEW
    assert len(scen.steps) == 0

def test_teaching_engine():
    engine = TeachingEngine()
    scen = create_onboarding_scenario(".")
    assert "onboard-1" in engine.orchestrate(scen)
    assert engine.track_progress("sid")["status"] == "in_progress"
