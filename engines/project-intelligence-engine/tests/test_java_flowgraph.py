"""Unit tests for Java method control-flow graphs."""

from __future__ import annotations

from collections import Counter
import unittest

from elmos_project_intelligence.java_flowgraph import java_function_control_flow
from elmos_project_intelligence.python_structure import ORIGIN_PARSED, ORIGIN_REGEX
from elmos_project_intelligence.runtime import dispatch_skill
from test_flowgraph import _file
from test_runtime import base_inputs, request


JAVA_SOURCE = """
public class OrderService {
    public int handle(int amount, boolean rush) {
        if (amount <= 0) {
            return 0;
        }
        int total = 0;
        for (int item : items) {
            total += item;
        }
        while (rush) {
            rush = false;
        }
        try {
            save(total);
        } catch (IOException exc) {
            throw new IllegalStateException(exc);
        }
        return total;
    }

    // comment with if (fake) { return; }
    public void other() {
        String query = "if (ignored) { return; }";
    }
}
"""


class JavaControlFlowTests(unittest.TestCase):
    def test_if_for_and_while_are_distinct_drawable_shapes(self) -> None:
        graph = java_function_control_flow(JAVA_SOURCE, "handle")
        self.assertIsNotNone(graph)
        assert graph is not None
        kinds = Counter(node["kind"] for node in graph["nodes"])
        self.assertGreaterEqual(kinds["decision"], 1)
        self.assertGreaterEqual(kinds["loop"], 2)
        self.assertIn("start", kinds)
        self.assertIn("end", kinds)
        self.assertTrue(
            any("amount" in str(node["label"]) for node in graph["nodes"] if node["kind"] == "decision"),
            graph["nodes"],
        )
        self.assertTrue(
            any(edge["kind"] == "loop-back" for edge in graph["edges"]),
            graph["edges"],
        )
        self.assertTrue(
            any(edge["kind"] == "exception" for edge in graph["edges"]),
            graph["edges"],
        )

    def test_comments_and_string_literals_do_not_invent_branches(self) -> None:
        graph = java_function_control_flow(JAVA_SOURCE, "other")
        self.assertIsNotNone(graph)
        assert graph is not None
        kinds = Counter(node["kind"] for node in graph["nodes"])
        self.assertEqual(kinds["decision"], 0)
        self.assertEqual(kinds["loop"], 0)

    def test_missing_method_is_an_empty_parsed_graph(self) -> None:
        graph = java_function_control_flow(JAVA_SOURCE, "absent")
        self.assertIsNotNone(graph)
        assert graph is not None
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["diagnostics"], ["function not found: absent"])

    def test_unbalanced_braces_are_a_parse_failure(self) -> None:
        self.assertIsNone(
            java_function_control_flow("class X { void handle() { if (x) { }", "handle")
        )

    def test_duplicate_methods_draw_the_first_and_say_so(self) -> None:
        source = (
            "class X {\n"
            "  void handle() { if (a) { return; } }\n"
            "  void handle(int x) { while (x > 0) { x--; } }\n"
            "}\n"
        )
        graph = java_function_control_flow(source, "handle")
        self.assertIsNotNone(graph)
        assert graph is not None
        self.assertTrue(any("2 definitions named handle" in item for item in graph["diagnostics"]))
        kinds = Counter(node["kind"] for node in graph["nodes"])
        self.assertGreaterEqual(kinds["decision"], 1)
        self.assertEqual(kinds["loop"], 0)


class JavaFlowDiscoveryTests(unittest.TestCase):
    def _dispatch(self, text: str) -> dict:
        inputs = base_inputs()
        inputs["files"] = [_file("src/main/java/OrderService.java", text)]
        inputs["path"] = "src/main/java/OrderService.java"
        inputs["flow_function"] = "handle"
        return dispatch_skill("elmos-flow-discovery", request(inputs))

    def test_java_control_flow_is_origin_parsed(self) -> None:
        result = self._dispatch(JAVA_SOURCE)
        control = [item for item in result["outputs"]["flows"] if item["kind"] == "control-flow"]
        self.assertEqual(len(control), 1)
        self.assertEqual(control[0]["origin"], ORIGIN_PARSED)
        self.assertEqual(control[0]["parse_status"], "PASSED")
        kinds = Counter(node["kind"] for node in control[0]["nodes"])
        self.assertGreaterEqual(kinds["decision"], 1)
        self.assertGreaterEqual(kinds["loop"], 2)

    def test_java_parse_failure_is_origin_regex(self) -> None:
        result = self._dispatch("class X { void handle() { if (x) { }")
        control = [item for item in result["outputs"]["flows"] if item["kind"] == "control-flow"]
        self.assertEqual(len(control), 1)
        self.assertEqual(control[0]["origin"], ORIGIN_REGEX)
        self.assertEqual(control[0]["parse_status"], "FAILED")
        self.assertEqual(control[0]["nodes"], [])


class LineageAndTopologyOriginTests(unittest.TestCase):
    def test_lineage_and_topology_mark_regex_origin(self) -> None:
        lineage = dispatch_skill("elmos-data-architecture-lineage", request())
        self.assertTrue(lineage["outputs"]["assets"])
        self.assertTrue(
            all(item["origin"] == ORIGIN_REGEX for item in lineage["outputs"]["assets"])
        )
        topology = dispatch_skill("elmos-api-event-topology", request())
        self.assertTrue(topology["outputs"]["endpoints"])
        self.assertTrue(topology["outputs"]["events"])
        self.assertTrue(
            all(item["origin"] == ORIGIN_REGEX for item in topology["outputs"]["endpoints"])
        )
        self.assertTrue(
            all(item["origin"] == ORIGIN_REGEX for item in topology["outputs"]["events"])
        )


if __name__ == "__main__":
    unittest.main()
