from __future__ import annotations

import pytest
from elmos_teaching_subsystem.cli import main

def test_cli_help(capsys):
    assert main([]) == 1
    
def test_cli_diagram(capsys):
    assert main(["diagram", "--type", "ARCHITECTURE"]) == 0

def test_cli_analyze(capsys):
    assert main(["analyze", "--dir", "."]) == 0
