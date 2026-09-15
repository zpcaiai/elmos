from __future__ import annotations

from elmos_project_synthesis.incremental_merger import (
    merge_file_content,
    merge_python_ast_augmentations,
)


def test_ast_preserves_user_added_functions() -> None:
    # User added a custom function without any comment markers
    user_file = '''import math

def calculate_norm(x: float, y: float) -> float:
    return math.sqrt(x * x + y * y)

def custom_user_loss(pred: float, target: float) -> float:
    """Special loss added by researcher."""
    return abs(pred - target) ** 1.5
'''

    # Upstream regenerated the template (e.g. added docstring or type improvement)
    new_template = '''import math

def calculate_norm(x: float, y: float) -> float:
    """Calculate Euclidean L2 norm."""
    return math.sqrt(x * x + y * y)
'''

    merged, preserved = merge_python_ast_augmentations(user_file, new_template)
    assert "custom_user_loss" in preserved
    assert "custom_user_loss" in merged
    assert "Special loss added by researcher." in merged
    assert "Calculate Euclidean L2 norm." in merged


def test_ast_preserves_user_added_classes_via_merge_file_content() -> None:
    existing = '''class BasePipeline:
    def run(self):
        pass

class CustomFeatureExtractor:
    def extract(self, data):
        return [len(data)]
'''

    new_gen = '''class BasePipeline:
    def run(self):
        print("Base running")
'''

    res = merge_file_content(existing, new_gen, filename="pipeline.py")
    assert "ast:CustomFeatureExtractor" in res.preserved_regions
    assert "CustomFeatureExtractor" in res.merged_content
    assert "Base running" in res.merged_content
    assert res.has_changes is True
