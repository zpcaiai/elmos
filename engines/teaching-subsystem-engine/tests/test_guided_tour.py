from __future__ import annotations

from elmos_teaching_subsystem.guided_tour import (
    GuidedTourEngine, TourScenario, TourStep
)

def test_generate_architecture_tour():
    engine = GuidedTourEngine()
    tour = engine.generate_architecture_tour(".", {})
    assert tour.scenario_type == TourScenario.ARCHITECTURE_OVERVIEW
    assert len(tour.steps) == 1
    assert tour.steps[0].target_file == "main.py"

def test_generate_dataflow_tour():
    engine = GuidedTourEngine()
    tour = engine.generate_dataflow_tour(".", {})
    assert tour.scenario_type == TourScenario.DATA_FLOW_WALKTHROUGH
    assert len(tour.steps) == 0

def test_generate_custom_tour():
    engine = GuidedTourEngine()
    steps = [TourStep("s1", "T", "D", "f.py", [1])]
    tour = engine.generate_custom_tour(steps)
    assert tour.scenario_type == TourScenario.CUSTOM
    assert len(tour.steps) == 1

def test_get_tour_progress():
    engine = GuidedTourEngine()
    prog = engine.get_tour_progress("arch-1")
    assert prog["status"] == "in_progress"
