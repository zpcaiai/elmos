from __future__ import annotations

from elmos_teaching_subsystem.project_analyzer import (
    ArchitecturePatternRecognizer,
    ProjectAnalysisService,
    TechStackFingerprinter
)

def test_architecture_pattern_recognizer():
    rec = ArchitecturePatternRecognizer()
    res = rec.analyze({})
    assert "MVC" in res
    assert "Layered" in res

def test_tech_stack_fingerprinter():
    rec = TechStackFingerprinter()
    res = rec.analyze({})
    assert res["language"] == "Python"
    assert res["framework"] == "ELMOS"

def test_project_analysis_service():
    svc = ProjectAnalysisService()
    report = svc.analyze_project({})
    assert "MVC" in report.patterns
    assert report.tech_stack["language"] == "Python"
    assert len(report.hotspots) == 1
    assert len(report.ownership) == 1
    assert len(report.apis) == 1
    assert len(report.dependencies) == 1
