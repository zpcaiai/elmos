import pytest
from pathlib import Path
from elmos_teaching_subsystem.code_explainer import CodeExplainer

def test_code_explainer(tmp_path):
    ce = CodeExplainer()
    f = tmp_path / "main.py"
    res = ce.explain_file(f)
    assert res.file_path == str(f)
    assert res.language == "py"
