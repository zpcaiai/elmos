import pytest
from pathlib import Path
from elmos_teaching_subsystem.learning_path import LearningPathRecommender

def test_learning_path(tmp_path):
    rec = LearningPathRecommender()
    path = rec.recommend_onboarding_path(tmp_path, "backend")
    assert path.title == "Onboarding for backend"
    assert len(path.steps) > 0
