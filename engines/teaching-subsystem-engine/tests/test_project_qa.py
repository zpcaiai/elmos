import pytest
from pathlib import Path
from elmos_teaching_subsystem.project_qa import CodeChunk, CodebaseIndex, ProjectQAService

def test_codebase_index(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("def my_function():\n    pass")
    
    idx = CodebaseIndex()
    idx.index_directory(tmp_path)
    
    assert idx.total_docs == 1
    res = idx.search("my_function")
    assert len(res) > 0

def test_qa_service(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("class MyClass: pass")
    
    svc = ProjectQAService(tmp_path)
    ans = svc.ask("MyClass")
    assert "MyClass" in ans.answer_context
