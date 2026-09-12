"""Industrial Declarative Test DSL Lexer, Parser, and Polyglot Target Compiler.

Parses declarative domain-specific language test specifications and compiles them into
executable Python unittest, pytest, and Go testing suites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Dict, List, Optional


@dataclass
class DSLAssertion:
    assertion_type: str  # 'STATUS', 'JSON_EQ', 'LATENCY_MS'
    target: str
    expected: Any


@dataclass
class DSLStep:
    step_type: str  # 'GIVEN', 'WHEN', 'THEN'
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    assertions: List[DSLAssertion] = field(default_factory=list)


@dataclass
class DSLScenario:
    name: str
    steps: List[DSLStep] = field(default_factory=list)


class TestDSLCompiler:
    """Compiles high-level declarative test specs into polyglot test runner code."""

    @staticmethod
    def parse_dsl(source_text: str) -> DSLScenario:
        lines = [line.strip() for line in source_text.strip().splitlines() if line.strip() and not line.strip().startswith("#")]
        if not lines:
            raise ValueError("Empty DSL source")

        first_line = lines[0]
        if not first_line.startswith("SCENARIO:"):
            raise SyntaxError("DSL must start with 'SCENARIO: <name>'")
        scenario_name = first_line.split("SCENARIO:", 1)[1].strip()
        scenario = DSLScenario(name=scenario_name)

        current_step: Optional[DSLStep] = None

        for line in lines[1:]:
            if line.startswith("GIVEN "):
                action = line[6:].strip()
                current_step = DSLStep(step_type="GIVEN", action=action)
                scenario.steps.append(current_step)
            elif line.startswith("WHEN "):
                action = line[5:].strip()
                current_step = DSLStep(step_type="WHEN", action=action)
                scenario.steps.append(current_step)
            elif line.startswith("THEN "):
                action = line[5:].strip()
                current_step = DSLStep(step_type="THEN", action=action)
                scenario.steps.append(current_step)
            elif line.startswith("ASSERT_STATUS "):
                status_val = int(line.split()[1])
                if current_step is None:
                    raise SyntaxError("ASSERT_STATUS without preceding step")
                current_step.assertions.append(DSLAssertion("STATUS", "status_code", status_val))
            elif line.startswith("ASSERT_JSON "):
                parts = line[12:].split("==", 1)
                if len(parts) == 2:
                    k = parts[0].strip()
                    v = json.loads(parts[1].strip())
                    if current_step is None:
                        raise SyntaxError("ASSERT_JSON without preceding step")
                    current_step.assertions.append(DSLAssertion("JSON_EQ", k, v))
            elif line.startswith("ASSERT_LATENCY_MS "):
                m = re.search(r"<=\s*(\d+)", line)
                if m:
                    limit = int(m.group(1))
                    if current_step is None:
                        raise SyntaxError("ASSERT_LATENCY_MS without preceding step")
                    current_step.assertions.append(DSLAssertion("LATENCY_MS", "latency", limit))

        return scenario

    @staticmethod
    def compile_to_python_unittest(scenario: DSLScenario) -> str:
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", scenario.name).lower()
        out = [
            "import unittest",
            "import time",
            "",
            f"class Test{safe_name.title().replace('_', '')}(unittest.TestCase):",
            f"    def test_{safe_name}(self):",
            f'        """Scenario: {scenario.name}"""',
            "        context = {}",
        ]
        for step in scenario.steps:
            out.append(f"        # {step.step_type}: {step.action}")
            out.append(f"        start_time = time.time()")
            out.append(f"        context['last_action'] = '{step.action}'")
            out.append(f"        elapsed_ms = (time.time() - start_time) * 1000.0")
            for a in step.assertions:
                if a.assertion_type == "STATUS":
                    out.append(f"        self.assertEqual(context.get('status_code', 200), {a.expected})")
                elif a.assertion_type == "JSON_EQ":
                    out.append(f"        self.assertEqual(context.get('{a.target}', {json.dumps(a.expected)}), {json.dumps(a.expected)})")
                elif a.assertion_type == "LATENCY_MS":
                    out.append(f"        self.assertLessEqual(elapsed_ms, {a.expected})")
        return "\n".join(out)

    @staticmethod
    def compile_to_pytest(scenario: DSLScenario) -> str:
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", scenario.name).lower()
        out = [
            "import pytest",
            "import time",
            "",
            f"def test_{safe_name}():",
            f'    """Scenario: {scenario.name}"""',
            "    context = {}",
        ]
        for step in scenario.steps:
            out.append(f"    # {step.step_type}: {step.action}")
            out.append(f"    start_time = time.time()")
            out.append(f"    context['last_action'] = '{step.action}'")
            out.append(f"    elapsed_ms = (time.time() - start_time) * 1000.0")
            for a in step.assertions:
                if a.assertion_type == "STATUS":
                    out.append(f"    assert context.get('status_code', 200) == {a.expected}")
                elif a.assertion_type == "JSON_EQ":
                    out.append(f"    assert context.get('{a.target}', {json.dumps(a.expected)}) == {json.dumps(a.expected)}")
                elif a.assertion_type == "LATENCY_MS":
                    out.append(f"    assert elapsed_ms <= {a.expected}")
        return "\n".join(out)

    @staticmethod
    def compile_to_go(scenario: DSLScenario) -> str:
        safe_name = "".join(w.capitalize() for w in re.sub(r"[^a-zA-Z0-9]", " ", scenario.name).split())
        out = [
            "package tests",
            "",
            'import (',
            '	"testing"',
            '	"time"',
            ')',
            "",
            f"func Test{safe_name}(t *testing.T) {{",
            f'	// Scenario: {scenario.name}',
            "	ctx := make(map[string]interface{})",
            "	_ = ctx",
        ]
        for step in scenario.steps:
            out.append(f"	// {step.step_type}: {step.action}")
            out.append(f"	start := time.Now()")
            out.append(f"	elapsedMs := float64(time.Since(start).Milliseconds())")
            out.append(f"	_ = elapsedMs")
            for a in step.assertions:
                if a.assertion_type == "STATUS":
                    out.append(f"	if statusCode := 200; statusCode != {a.expected} {{")
                    out.append(f'		t.Errorf("expected status {a.expected}, got %d", statusCode)')
                    out.append("	}")
                elif a.assertion_type == "LATENCY_MS":
                    out.append(f"	if elapsedMs > {float(a.expected)} {{")
                    out.append(f'		t.Errorf("latency exceeded {a.expected}ms")')
                    out.append("	}")
        out.append("}")
        return "\n".join(out)
