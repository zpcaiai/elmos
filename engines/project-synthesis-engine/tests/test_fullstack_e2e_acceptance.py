"""Integration test for fullstack end-to-end acceptance runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_e2e_module() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "run_fullstack_e2e_acceptance.py"
    spec = importlib.util.spec_from_file_location("run_fullstack_e2e_acceptance", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fullstack_e2e_runner_execution() -> None:
    module = load_e2e_module()
    exit_code = module.main([])
    assert exit_code == 0
