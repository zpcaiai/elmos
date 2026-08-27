from __future__ import annotations
import json
import re
from typing import Any

class CounterexampleError(ValueError):
    pass

def _safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"cex_{cleaned}"
    return cleaned

def to_scenario_dsl(counterexample: dict[str, Any]) -> str:
    required = {"id","obligationId","kind","witness","violatedProperty"}
    missing = required - counterexample.keys()
    if missing:
        raise CounterexampleError(f"missing fields: {sorted(missing)}")
    return (
        f"scenario {_safe_identifier(counterexample['id'])}\n"
        f"obligation {counterexample['obligationId']}\n"
        f"kind {counterexample['kind']}\n"
        f"given {json.dumps(counterexample['witness'], ensure_ascii=False, sort_keys=True)}\n"
        f"expect_violation {json.dumps(counterexample['violatedProperty'], ensure_ascii=False)}\n"
    )

def to_pytest(counterexample: dict[str, Any], callable_name: str = "subject") -> str:
    scenario = to_scenario_dsl(counterexample)
    witness = json.dumps(counterexample["witness"], ensure_ascii=False, sort_keys=True)
    test_name = _safe_identifier(f"test_{counterexample['id']}")
    comment = "\n".join(f"# {line}" for line in scenario.rstrip().splitlines())
    return (
        f"# Generated from {counterexample['obligationId']}\n"
        f"# Scenario:\n{comment}\n"
        "import pytest\n\n"
        f"def {test_name}():\n"
        f"    witness = {witness}\n"
        f"    result = {callable_name}(witness)\n"
        f"    assert result['property_holds'], {counterexample['violatedProperty']!r}\n"
    )
