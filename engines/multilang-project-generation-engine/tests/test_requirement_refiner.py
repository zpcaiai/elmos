import pytest
from elmos_multilang_project_generation.requirement_refiner import RequirementRefiner

def test_requirement_refiner():
    psir = {
        "entities": [
            {"name": "User", "fields": [{"name": "id", "is_primary_key": True}]}
        ]
    }
    refiner = RequirementRefiner()
    report = refiner.refine(psir)
    assert len(report.issues) == 0
    assert len(report.suggestions) > 0
