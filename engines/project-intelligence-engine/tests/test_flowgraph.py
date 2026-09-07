"""Behavioural tests for parser-backed structure and control-flow diagrams.

These assert the *shape of the answer*, not that a function returns the keys
it was written to return.  Where a count is asserted the graph was derived by
hand first and the expectation written down before the code was run.
"""

from __future__ import annotations

from collections import Counter
import unittest

from elmos_project_intelligence.domain import _imports, _symbols
from elmos_project_intelligence.flowgraph import function_control_flow
from elmos_project_intelligence.python_structure import (
    ORIGIN_PARSED,
    ORIGIN_REGEX,
    module_structure,
)
from elmos_project_intelligence.runtime import dispatch_skill

from test_runtime import base_inputs, request, sha


def _file(path: str, text: str) -> dict[str, object]:
    return {"path": path, "text": text, "sha256": sha(text)}


def _targets(edges: list[dict], source: str, kind: str) -> list[str]:
    return [e["target"] for e in edges if e["source"] == source and e["kind"] == kind]


def _incoming(edges: list[dict], target: str) -> list[dict]:
    return [e for e in edges if e["target"] == target]


# The function every structural assertion below is hand-derived from.
#
#   start -> for            (loop)
#   for  --each-->  if      (decision)
#   if   --true-->  continue --continue--> for   (back-edge)
#   if   --false--> merge   -> g(x) --repeat--> for   (back-edge)
#   for  --done-->  loop exit -> return 1 --return--> end
#
# nodes: start, end, loop, "loop exit" merge, if-merge, decision,
#        continue, g(x), return  = 9
# edges: 2 loop-back, 1 loop-body, 1 loop-exit, 2 branch, 4 flow = 10
HAND_CHECKED = """
def f(xs):
    for x in xs:
        if x:
            continue
        g(x)
    return 1
"""


class ControlFlowWalkTests(unittest.TestCase):
    def test_hand_checked_function_matches_the_derived_graph_exactly(self) -> None:
        graph = function_control_flow(HAND_CHECKED, "f")
        assert graph is not None
        nodes = graph["nodes"]
        edges = graph["edges"]

        self.assertEqual(
            Counter(node["kind"] for node in nodes),
            Counter(
                {
                    "start": 1,
                    "end": 1,
                    "loop": 1,
                    "merge": 2,
                    "decision": 1,
                    "process": 3,
                }
            ),
        )
        self.assertEqual(
            Counter(edge["kind"] for edge in edges),
            Counter(
                {
                    "flow": 4,
                    "branch": 2,
                    "loop-back": 2,
                    "loop-body": 1,
                    "loop-exit": 1,
                }
            ),
        )

        loop = next(node for node in nodes if node["kind"] == "loop")
        back = [
            edge
            for edge in edges
            if edge["kind"] == "loop-back" and edge["target"] == loop["id"]
        ]
        self.assertEqual(
            len(back),
            2,
            "the fall-through end of the body and the continue both loop back",
        )
        self.assertEqual(sorted(edge["label"] for edge in back), ["continue", "repeat"])

        decision = next(node for node in nodes if node["kind"] == "decision")
        self.assertEqual(
            sorted(
                edge["label"]
                for edge in edges
                if edge["source"] == decision["id"] and edge["kind"] == "branch"
            ),
            ["false", "true"],
        )

    def test_nested_if_for_while_try_produces_a_well_formed_graph(self) -> None:
        source = """
def handle(items):
    total = 0
    if not items:
        return None
    for item in items:
        if item < 0:
            continue
        total += item
    while total > 100:
        total -= 10
    try:
        risky(total)
    except ValueError:
        total = 0
    except KeyError:
        raise
    finally:
        log(total)
    with open("f") as fh:
        fh.write(str(total))
    return total
"""
        graph = function_control_flow(source, "handle")
        assert graph is not None
        nodes = graph["nodes"]
        edges = graph["edges"]
        by_id = {node["id"]: node for node in nodes}

        kinds = Counter(node["kind"] for node in nodes)
        # Two source `if`s -> two decisions. Nothing else creates one.
        self.assertEqual(kinds["decision"], 2)
        # One `for` and one `while` -> two loops.
        self.assertEqual(kinds["loop"], 2)
        self.assertEqual(kinds["start"], 1)
        self.assertEqual(kinds["end"], 1)

        # Every loop is entered, repeated and left.
        for loop in (node for node in nodes if node["kind"] == "loop"):
            self.assertTrue(
                _targets(edges, loop["id"], "loop-body")
                or any(
                    edge["source"] == loop["id"] and edge["kind"] == "loop-back"
                    for edge in edges
                ),
                f"loop {loop['label']} never enters a body",
            )
            self.assertEqual(
                len(_targets(edges, loop["id"], "loop-exit")),
                1,
                f"loop {loop['label']} must have exactly one exit",
            )
            self.assertTrue(
                [
                    edge
                    for edge in edges
                    if edge["kind"] == "loop-back" and edge["target"] == loop["id"]
                ],
                f"loop {loop['label']} has no back-edge",
            )

        # Every decision forks exactly true/false.
        for decision in (node for node in nodes if node["kind"] == "decision"):
            self.assertEqual(
                sorted(
                    edge["label"]
                    for edge in edges
                    if edge["source"] == decision["id"] and edge["kind"] == "branch"
                ),
                ["false", "true"],
            )

        # The two handlers are reached from the try by an exception edge.
        exception_labels = sorted(
            edge["label"] for edge in edges if edge["kind"] == "exception"
        )
        self.assertIn("except ValueError", exception_labels)
        self.assertIn("except KeyError", exception_labels)
        # `raise` inside a handler leaves through the terminal node.
        self.assertIn("raise", exception_labels)

        # No dangling endpoints.
        for edge in edges:
            self.assertIn(edge["source"], by_id)
            self.assertIn(edge["target"], by_id)

        # Everything is reachable from start, so nothing was orphaned.
        start = next(node for node in nodes if node["kind"] == "start")
        seen = {start["id"]}
        frontier = [start["id"]]
        while frontier:
            current = frontier.pop()
            for edge in edges:
                if edge["source"] == current and edge["target"] not in seen:
                    seen.add(edge["target"])
                    frontier.append(edge["target"])
        self.assertEqual(
            sorted(seen),
            sorted(by_id),
            "every control-flow node must be reachable from start",
        )

    def test_merge_point_joins_both_branches_of_an_if(self) -> None:
        graph = function_control_flow(
            "def f(a):\n    if a:\n        x = 1\n    else:\n        x = 2\n    return x\n",
            "f",
        )
        assert graph is not None
        merges = [node for node in graph["nodes"] if node["kind"] == "merge"]
        self.assertEqual(len(merges), 1)
        self.assertEqual(
            len(_incoming(graph["edges"], merges[0]["id"])),
            2,
            "a two-armed if must merge two incoming paths",
        )

    def test_unparseable_source_returns_none_rather_than_an_empty_graph(self) -> None:
        self.assertIsNone(function_control_flow("def (", "f"))

    def test_missing_function_is_reported_not_silently_empty(self) -> None:
        graph = function_control_flow("x = 1\n", "absent")
        assert graph is not None
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["diagnostics"], ["function not found: absent"])


class ParsedStructureTests(unittest.TestCase):
    def test_parser_finds_what_the_line_regex_structurally_cannot(self) -> None:
        source = (
            "import os\n"
            "from . import sibling\n"
            "if TYPE_CHECKING:\n"
            "    class Conditional:\n"
            "        pass\n"
            "class Outer:\n"
            "    async def run(self):\n"
            "        pass\n"
        )
        files = [_file("src/a.py", source)]

        symbols = _symbols(files)
        self.assertTrue(all(item["origin"] == ORIGIN_PARSED for item in symbols))
        by_name = {item["name"]: item for item in symbols}
        self.assertEqual(by_name["run"]["kind"], "async-function")
        self.assertEqual(by_name["run"]["qualified_name"], "Outer.run")
        self.assertIn("Conditional", by_name, "a nested class must still be found")
        self.assertEqual(by_name["src/a.py"]["kind"], "module")

        imports = _imports(files)
        self.assertEqual(
            sorted(item["to"] for item in imports),
            [".", "os"],
            "the relative import the regex never matched must appear",
        )
        self.assertTrue(all(item["origin"] == ORIGIN_PARSED for item in imports))

    def test_unparseable_python_falls_back_to_regex_and_says_so(self) -> None:
        # Valid declarations followed by a syntax error: the fallback must
        # still produce facts, and must mark them as regex-derived.
        source = "import os\nclass Widget:\n    def go(self):\n        pass\ndef (\n"
        self.assertIsNone(module_structure(source, "src/half.py"))

        files = [_file("src/half.py", source)]
        symbols = _symbols(files)
        self.assertTrue(symbols, "fallback must not silently yield nothing")
        self.assertTrue(all(item["origin"] == ORIGIN_REGEX for item in symbols))
        self.assertEqual(sorted(item["name"] for item in symbols), ["Widget", "go"])

        imports = _imports(files)
        self.assertEqual([item["to"] for item in imports], ["os"])
        self.assertTrue(all(item["origin"] == ORIGIN_REGEX for item in imports))

    def test_non_python_files_keep_the_regex_vocabulary(self) -> None:
        files = [_file("src/x.ts", 'import "lodash"\nexport class T {}\n')]
        symbols = _symbols(files)
        self.assertEqual([item["kind"] for item in symbols], ["class"])
        self.assertEqual([item["origin"] for item in symbols], [ORIGIN_REGEX])
        self.assertEqual([item["origin"] for item in _imports(files)], [ORIGIN_REGEX])


class FlowDiscoveryDispatchTests(unittest.TestCase):
    SOURCE = (
        "def handle(items):\n"
        "    if not items:\n"
        "        return None\n"
        "    for item in items:\n"
        "        total = item\n"
        "    return total\n"
    )

    def _dispatch(self, text: str) -> dict:
        inputs = base_inputs()
        inputs["files"] = [_file("src/app.py", text)]
        inputs["path"] = "src/app.py"
        inputs["flow_function"] = "handle"
        return dispatch_skill("elmos-flow-discovery", request(inputs))

    def test_control_flow_is_returned_without_widening_the_output_contract(
        self,
    ) -> None:
        result = self._dispatch(self.SOURCE)
        self.assertEqual(result["state"], "PARTIAL_LOCAL_EXECUTED")
        self.assertEqual(
            sorted(result["outputs"]), ["flows", "unknown_runtime_branches"]
        )
        # The capability did not become complete just because it can now draw
        # a branch: which branch actually runs is still unobserved.
        self.assertIs(result["outputs"]["unknown_runtime_branches"], True)
        self.assertEqual(result["unavailable"], ["runtime-path-observations"])

        flows = result["outputs"]["flows"]
        control = [item for item in flows if item["kind"] == "control-flow"]
        self.assertEqual(len(control), 1)
        self.assertEqual(control[0]["parse_status"], "PASSED")
        self.assertEqual(control[0]["origin"], ORIGIN_PARSED)
        self.assertEqual(
            Counter(node["kind"] for node in control[0]["nodes"])["decision"], 1
        )
        self.assertEqual(
            Counter(node["kind"] for node in control[0]["nodes"])["loop"], 1
        )

    def test_import_flows_are_unchanged_when_no_function_is_named(self) -> None:
        inputs = base_inputs()
        result = dispatch_skill("elmos-flow-discovery", request(inputs))
        flows = result["outputs"]["flows"]
        self.assertTrue(flows)
        self.assertTrue(all(item["kind"] == "import" for item in flows))
        self.assertTrue(all(item["confidence"] == "INFERRED" for item in flows))

    def test_unparseable_target_reports_failure_not_an_empty_graph(self) -> None:
        result = self._dispatch("def handle(:\n")
        control = [
            item
            for item in result["outputs"]["flows"]
            if item["kind"] == "control-flow"
        ]
        self.assertEqual(len(control), 1)
        self.assertEqual(control[0]["parse_status"], "FAILED")
        self.assertEqual(control[0]["origin"], ORIGIN_REGEX)
        self.assertEqual(control[0]["nodes"], [])
        self.assertEqual(control[0]["diagnostics"], ["source did not parse"])


class ControlFlowRenderingTests(unittest.TestCase):
    def _render(self, nodes: list[dict], edges: list[dict]) -> str:
        compile_inputs = base_inputs()
        compile_inputs.pop("diagram_spec", None)
        compile_inputs["nodes"] = nodes
        compile_inputs["edges"] = edges
        compile_inputs["diagram_type"] = "control-flow"
        compiled = dispatch_skill("elmos-diagram-spec-engine", request(compile_inputs))
        self.assertEqual(compiled["code"], "DIAGRAM_SPEC_COMPILED")

        render_inputs = base_inputs()
        render_inputs["diagram_spec"] = compiled["outputs"]["diagram_spec"]
        rendered = dispatch_skill("elmos-diagram-rendering", request(render_inputs))
        self.assertEqual(rendered["code"], "SAFE_MERMAID_RENDERED")
        return rendered["outputs"]["content"]

    def test_control_flow_kinds_render_as_distinct_mermaid_shapes(self) -> None:
        content = self._render(
            [
                {"id": "s", "label": "start", "kind": "start"},
                {"id": "d", "label": "ready", "kind": "decision"},
                {"id": "l", "label": "for row", "kind": "loop"},
                {"id": "m", "label": "merge", "kind": "merge"},
                {"id": "p", "label": "work", "kind": "process"},
                {"id": "e", "label": "end", "kind": "end"},
            ],
            [
                {"id": "e1", "source": "s", "target": "d", "kind": "flow"},
                {
                    "id": "e2",
                    "source": "d",
                    "target": "l",
                    "kind": "branch",
                    "label": "true",
                },
                {
                    "id": "e3",
                    "source": "d",
                    "target": "m",
                    "kind": "branch",
                    "label": "false",
                },
                {
                    "id": "e4",
                    "source": "l",
                    "target": "l",
                    "kind": "loop-back",
                    "label": "repeat",
                },
                {"id": "e5", "source": "m", "target": "p", "kind": "flow"},
                {"id": "e6", "source": "p", "target": "e", "kind": "flow"},
            ],
        )

        # A decision is a diamond, not a rectangle.
        self.assertRegex(content, r'\n  n\d\{"ready"\}')
        # A loop is a subroutine box.
        self.assertRegex(content, r'\n  n\d\[\["for row"\]\]')
        # start/end are stadiums, merge is a circle, process stays a rectangle.
        self.assertRegex(content, r'\n  n\d\(\["start"\]\)')
        self.assertRegex(content, r'\n  n\d\(\["end"\]\)')
        self.assertRegex(content, r'\n  n\d\(\("merge"\)\)')
        self.assertRegex(content, r'\n  n\d\["work"\]')

    def test_labelled_edges_render_with_their_label(self) -> None:
        content = self._render(
            [
                {"id": "d", "label": "ready", "kind": "decision"},
                {"id": "a", "label": "yes", "kind": "process"},
                {"id": "b", "label": "no", "kind": "process"},
            ],
            [
                {
                    "id": "e1",
                    "source": "d",
                    "target": "a",
                    "kind": "branch",
                    "label": "true",
                },
                {
                    "id": "e2",
                    "source": "d",
                    "target": "b",
                    "kind": "branch",
                    "label": "false",
                },
            ],
        )
        self.assertRegex(content, r"\n  n\d -->\|true\| n\d")
        self.assertRegex(content, r"\n  n\d -->\|false\| n\d")

    def test_unlabelled_edges_keep_the_plain_arrow(self) -> None:
        content = self._render(
            [
                {"id": "a", "label": "one", "kind": "process"},
                {"id": "b", "label": "two", "kind": "process"},
            ],
            [{"id": "e1", "source": "a", "target": "b", "kind": "flow"}],
        )
        self.assertIn("  n0 --> n1", content)
        self.assertNotIn("|", content)

    def test_edge_labels_are_sanitized_like_node_labels(self) -> None:
        """Both layers refuse an injected edge label, independently.

        The spec compiler rejects it outright, because a control character
        cannot be an identifier. A spec that reaches the renderer some other
        way is still sanitized there, so neither layer relies on the other.
        """

        injection = 'true| n9["injected"]\n  n9 --> n0'

        compile_inputs = base_inputs()
        compile_inputs.pop("diagram_spec", None)
        compile_inputs["nodes"] = [
            {"id": "a", "label": "one", "kind": "decision"},
            {"id": "b", "label": "two", "kind": "process"},
        ]
        compile_inputs["edges"] = [
            {
                "id": "e1",
                "source": "a",
                "target": "b",
                "kind": "branch",
                "label": injection,
            }
        ]
        compiled = dispatch_skill("elmos-diagram-spec-engine", request(compile_inputs))
        self.assertEqual(compiled["state"], "BLOCKED")

        # Now hand the renderer the spec directly.
        render_inputs = base_inputs()
        render_inputs["diagram_spec"] = {
            "schema_version": 1,
            "diagram_id": sha("edge-label-injection"),
            "type": "control-flow",
            "project_id": "project-a",
            "revision_id": "abc123",
            "nodes": [
                {"id": "a", "label": "one", "kind": "decision"},
                {"id": "b", "label": "two", "kind": "process"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "a",
                    "target": "b",
                    "kind": "branch",
                    "label": injection,
                }
            ],
        }
        rendered = dispatch_skill("elmos-diagram-rendering", request(render_inputs))
        content = rendered["outputs"]["content"]
        self.assertEqual(rendered["code"], "SAFE_MERMAID_RENDERED")
        # header + two nodes + one edge. The injected text is still present
        # as inert words inside the label; what matters is that it could not
        # become a statement of its own.
        self.assertEqual(
            len(content.splitlines()),
            4,
            "an injected edge label must not add a statement",
        )
        self.assertEqual(content.count("|"), 2, "exactly one label delimiter pair")
        self.assertNotIn('n9["', content, "the label must not declare a node")
        self.assertNotIn("-->|true|", content, "the label must not close early")
        self.assertEqual(
            len([line for line in content.splitlines() if "-->" in line]),
            1,
            "the label must not create a second edge",
        )
        self.assertIn("diagram-labels-normalized", rendered["warnings"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
